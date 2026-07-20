"""Tests for agent name resolution in the `pyworkon agent` CLI command."""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

import pytest

# `pyworkon.interfaces.shell.commands.__init__` does `from .agent import agent`,
# which shadows the `agent` submodule attribute on the package with the Click
# command object. Import the submodule explicitly to bypass that shadowing.
agent_cli = importlib.import_module("pyworkon.interfaces.shell.commands.agent")


def _completed(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_find_claude_pid_walks_up_to_claude_ancestor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shell-wrapper hop (sh) sits between the hook process and `claude`."""
    monkeypatch.setattr(agent_cli.os, "getppid", lambda: 41118)
    ps_output_by_pid = {
        41118: "39666 sh\n",
        39666: "39612 claude\n",
    }

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        pid = int(cmd[cmd.index("-p") + 1])
        return _completed(ps_output_by_pid[pid])

    monkeypatch.setattr(agent_cli.subprocess, "run", fake_run)

    assert agent_cli._find_claude_pid() == 39666


def test_find_claude_pid_falls_back_when_no_claude_ancestor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If no ancestor is named `claude` within the hop limit, use the direct parent."""
    monkeypatch.setattr(agent_cli.os, "getppid", lambda: 100)

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        pid = int(cmd[cmd.index("-p") + 1])
        return _completed(f"{pid + 1} bash\n")

    monkeypatch.setattr(agent_cli.subprocess, "run", fake_run)

    assert agent_cli._find_claude_pid() == 100


def test_find_claude_pid_falls_back_on_unreadable_ps_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_cli.os, "getppid", lambda: 100)
    monkeypatch.setattr(agent_cli.subprocess, "run", lambda *_a, **_k: _completed(""))

    assert agent_cli._find_claude_pid() == 100


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
