"""Tests for agent name resolution in the `pyworkon agent` CLI command."""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from pyworkon.daemon.client import DaemonClient

# `pyworkon.interfaces.shell.commands.__init__` does `from .agent import agent`,
# which shadows the `agent` submodule attribute on the package with the Click
# command object. Import the submodule explicitly to bypass that shadowing.
agent_cli = importlib.import_module("pyworkon.interfaces.shell.commands.agent")


def _completed(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


@pytest.mark.parametrize("agent_type", ["claude", "codex", "opencode"])
def test_find_agent_process_walks_up_to_agent_ancestor(
    monkeypatch: pytest.MonkeyPatch,
    agent_type: str,
) -> None:
    """A shell-wrapper hop sits between the hook and the stable agent process."""
    monkeypatch.setattr(agent_cli.os, "getppid", lambda: 41118)
    ps_output_by_pid = {
        41118: "39666 sh\n",
        39666: f"39612 /opt/bin/{agent_type}\n",
    }

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        pid = int(cmd[cmd.index("-p") + 1])
        return _completed(ps_output_by_pid.get(pid, ""))

    monkeypatch.setattr(agent_cli.subprocess, "run", fake_run)

    assert agent_cli._find_agent_process() == (39666, agent_type)


def test_find_agent_process_falls_back_when_no_agent_ancestor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If no ancestor is named `claude` within the hop limit, use the direct parent."""
    monkeypatch.setattr(agent_cli.os, "getppid", lambda: 100)

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        pid = int(cmd[cmd.index("-p") + 1])
        return _completed(f"{pid + 1} bash\n")

    monkeypatch.setattr(agent_cli.subprocess, "run", fake_run)

    assert agent_cli._find_agent_process() == (100, None)


def test_find_agent_process_falls_back_on_unreadable_ps_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_cli.os, "getppid", lambda: 100)
    monkeypatch.setattr(agent_cli.subprocess, "run", lambda *_a, **_k: _completed(""))

    assert agent_cli._find_agent_process() == (100, None)


def test_process_cwd_uses_proc_when_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_proc_cwd = tmp_path / "proc-cwd-target"
    fake_proc_cwd.mkdir()
    real_exists = Path.exists
    real_resolve = Path.resolve

    def fake_exists(self: Path) -> bool:
        if str(self) == "/proc/100/cwd":
            return True
        return real_exists(self)

    def fake_resolve(self: Path, *, strict: bool = False) -> Path:
        if str(self) == "/proc/100/cwd":
            return fake_proc_cwd.resolve()
        return real_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "resolve", fake_resolve)

    assert agent_cli._process_cwd(100) == fake_proc_cwd.resolve()


def test_process_cwd_falls_back_to_lsof(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agent_cli.subprocess,
        "run",
        lambda *_a, **_k: _completed("p100\nfcwd\nn/Users/cassing/workspace/foo\n"),
    )

    assert agent_cli._process_cwd(100) == Path("/Users/cassing/workspace/foo")


def test_process_cwd_returns_none_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_cli.subprocess, "run", lambda *_a, **_k: _completed(""))

    assert agent_cli._process_cwd(100) is None


def test_find_active_transcript_picks_most_recently_modified(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(agent_cli.Path, "home", lambda: tmp_path)
    cwd = Path("/Users/cassing/workspace/github/chassing/pyworkon")
    project_dir = tmp_path / ".claude" / "projects" / str(cwd).replace("/", "-")
    project_dir.mkdir(parents=True)

    older = project_dir / "older.jsonl"
    older.write_text("{}\n")
    newer = project_dir / "newer.jsonl"
    newer.write_text("{}\n")
    # Ensure a distinguishable, deterministic mtime ordering.
    older_stat = older.stat()
    os_module = agent_cli.__dict__.get("os")
    if os_module is not None:
        os_module.utime(older, (older_stat.st_atime, older_stat.st_mtime - 100))

    assert agent_cli._find_active_transcript(cwd) == newer


def test_find_active_transcript_no_project_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(agent_cli.Path, "home", lambda: tmp_path)

    assert agent_cli._find_active_transcript(Path("/nonexistent/project")) is None


def test_extract_latest_transcript_field_returns_most_recent_value(
    tmp_path: Path,
) -> None:
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        '{"type":"agent-name","agentName":"qontract-utils-ocm-client"}\n'
        '{"type":"assistant","message":{}}\n'
        '{"type":"agent-name","agentName":"ocm-cluster-discovery-endpoint"}\n'
    )

    assert (
        agent_cli._extract_latest_transcript_field(
            transcript, entry_type="agent-name", field="agentName"
        )
        == "ocm-cluster-discovery-endpoint"
    )


def test_extract_latest_transcript_field_missing_type(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    transcript.write_text('{"type":"ai-title","aiTitle":"my-session"}\n')

    assert (
        agent_cli._extract_latest_transcript_field(
            transcript, entry_type="agent-name", field="agentName"
        )
        is None
    )


def test_extract_latest_transcript_field_missing_file(tmp_path: Path) -> None:
    assert (
        agent_cli._extract_latest_transcript_field(
            tmp_path / "missing.jsonl", entry_type="agent-name", field="agentName"
        )
        is None
    )


def test_extract_latest_transcript_field_skips_malformed_lines(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        '{"type":"agent-name","agentName":"real-name"}\nnot json at all {{{\n'
    )

    assert (
        agent_cli._extract_latest_transcript_field(
            transcript, entry_type="agent-name", field="agentName"
        )
        == "real-name"
    )


def test_resolve_agent_name_prefers_agent_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_cli, "_process_cwd", lambda _pid: Path("/some/project"))
    monkeypatch.setattr(
        agent_cli, "_find_active_transcript", lambda _cwd: Path("/fake/session.jsonl")
    )

    def fake_extract(_transcript: Path, *, entry_type: str, field: str) -> str | None:
        if entry_type == "agent-name":
            return "ocm-cluster-discovery-endpoint"
        return "should-not-be-used"

    monkeypatch.setattr(agent_cli, "_extract_latest_transcript_field", fake_extract)

    assert agent_cli._resolve_agent_name(10185) == "ocm-cluster-discovery-endpoint"


def test_resolve_agent_name_falls_back_to_ai_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_cli, "_process_cwd", lambda _pid: Path("/some/project"))
    monkeypatch.setattr(
        agent_cli, "_find_active_transcript", lambda _cwd: Path("/fake/session.jsonl")
    )

    def fake_extract(_transcript: Path, *, entry_type: str, field: str) -> str | None:
        if entry_type == "ai-title":
            return "resolve-claude-session-title"
        return None

    monkeypatch.setattr(agent_cli, "_extract_latest_transcript_field", fake_extract)

    assert agent_cli._resolve_agent_name(10185) == "resolve-claude-session-title"


@pytest.mark.parametrize(
    ("cwd", "transcript"),
    [
        (None, None),
        (Path("/some/project"), None),
    ],
)
def test_resolve_agent_name_falls_back_to_pid(
    monkeypatch: pytest.MonkeyPatch, cwd: Path | None, transcript: Path | None
) -> None:
    monkeypatch.setattr(agent_cli, "_process_cwd", lambda _pid: cwd)
    monkeypatch.setattr(agent_cli, "_find_active_transcript", lambda _cwd: transcript)
    monkeypatch.setattr(
        agent_cli, "_extract_latest_transcript_field", lambda *_a, **_k: None
    )

    assert agent_cli._resolve_agent_name(10185) == "claude-10185"


def test_get_tmux_session_returns_none_when_not_inside_tmux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reproduce the cross-project agent leak.

    A headless/background process has no TMUX env var — `tmux display-message`
    would otherwise silently fall back to whatever session the server considers
    "current" (e.g. the client's last-attached session), misattributing agent
    status to an unrelated project. Absence of TMUX must short-circuit before
    that ambient lookup ever runs.
    """
    monkeypatch.delenv("TMUX", raising=False)

    def fake_run(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        msg = "tmux display-message must not be called when TMUX is unset"
        raise AssertionError(msg)

    monkeypatch.setattr(agent_cli.subprocess, "run", fake_run)

    assert agent_cli._get_tmux_session() is None


def test_get_tmux_session_returns_session_when_inside_tmux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TMUX", "tmux-server-socket,1234,0")
    monkeypatch.setattr(
        agent_cli.subprocess, "run", lambda *_a, **_k: _completed("pyworkon\n")
    )

    assert agent_cli._get_tmux_session() == "pyworkon"


def test_get_tmux_session_targets_originating_pane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TMUX", "tmux-server-socket,1234,0")
    monkeypatch.setenv("TMUX_PANE", "%42")
    run = Mock(return_value=_completed("origin-project\n"))
    monkeypatch.setattr(agent_cli.subprocess, "run", run)

    assert agent_cli._get_tmux_session() == "origin-project"
    run.assert_called_once_with(
        ["tmux", "display-message", "-p", "-t", "%42", "#{session_name}"],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def agent_client(monkeypatch: pytest.MonkeyPatch) -> Mock:
    client = Mock(spec=DaemonClient)
    monkeypatch.setattr(agent_cli, "require_daemon", lambda: client)
    monkeypatch.setattr(agent_cli, "_get_tmux_session", lambda: "project")
    monkeypatch.setattr(agent_cli, "_find_agent_process", lambda: (123, "opencode"))
    return client


@pytest.mark.parametrize("clear", [False, True])
def test_agent_explicit_pid_survives_transient_hook_processes(
    agent_client: Mock,
    *,
    clear: bool,
) -> None:
    args = ["--pid", "456"]
    args.extend(
        ["--clear"] if clear else ["--name", "My session", "--status", "working"]
    )

    result = CliRunner().invoke(agent_cli.agent, args)

    assert result.exit_code == 0, result.output
    if clear:
        agent_client.clear_agent.assert_called_once_with("project", pid=456)
    else:
        agent_client.set_agent.assert_called_once_with(
            session="project",
            pid=456,
            name="My session",
            status="working",
        )
    agent_client.close.assert_called_once_with()


def test_agent_auto_detects_opencode(agent_client: Mock) -> None:
    result = CliRunner().invoke(agent_cli.agent, ["--status", "idle"])

    assert result.exit_code == 0, result.output
    agent_client.set_agent.assert_called_once_with(
        session="project",
        pid=123,
        name="opencode-123",
        status="idle",
    )


@pytest.mark.parametrize("pid", ["0", "-1", "not-a-pid"])
def test_agent_rejects_invalid_explicit_pid(agent_client: Mock, pid: str) -> None:
    result = CliRunner().invoke(agent_cli.agent, ["--pid", pid, "--status", "idle"])

    assert result.exit_code == 2
    agent_client.set_agent.assert_not_called()


def test_resolve_agent_name_falls_back_to_pid_when_no_field_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_cli, "_process_cwd", lambda _pid: Path("/some/project"))
    monkeypatch.setattr(
        agent_cli, "_find_active_transcript", lambda _cwd: Path("/fake/session.jsonl")
    )
    monkeypatch.setattr(
        agent_cli, "_extract_latest_transcript_field", lambda *_a, **_k: None
    )

    assert agent_cli._resolve_agent_name(10185) == "claude-10185"
