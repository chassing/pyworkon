"""CLI command for setting agent status via daemon."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path

import click

from pyworkon.daemon.client import require_daemon
from pyworkon.interfaces.shell import cli

_MAX_PROCESS_TREE_HOPS = 5
_PS_PPID_COMM_FIELD_COUNT = 2
_AGENT_PROCESS_NAMES = {"claude", "codex", "opencode"}


def _find_process(process_names: set[str]) -> tuple[int, str | None]:
    """Walk up the process tree to find an ancestor with a matching name.

    Agent hooks can run via a transient shell, so the direct parent may not be
    the stable agent process. Fall back to the direct parent PID if none is
    found within a few hops.
    """
    start_pid = os.getppid()
    pid = start_pid
    for _ in range(_MAX_PROCESS_TREE_HOPS):
        result = subprocess.run(
            ["ps", "-o", "ppid=,comm=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=False,
        )
        parts = result.stdout.split(maxsplit=1)
        if len(parts) != _PS_PPID_COMM_FIELD_COUNT:
            return start_pid, None
        ppid_str, comm = parts
        process_name = comm.strip().rsplit("/", 1)[-1].casefold()
        if process_name in process_names:
            return pid, process_name
        pid = int(ppid_str)
    return start_pid, None


def _find_agent_process() -> tuple[int, str | None]:
    """Find the Claude Code, Codex, or OpenCode process that launched this hook."""
    return _find_process(_AGENT_PROCESS_NAMES)


def _process_cwd(pid: int) -> Path | None:
    """Resolve a process's current working directory (Linux `/proc`, macOS `lsof`)."""
    proc_cwd = Path(f"/proc/{pid}/cwd")
    with contextlib.suppress(OSError):
        if proc_cwd.exists():
            return proc_cwd.resolve()
    result = subprocess.run(
        ["lsof", "-a", "-d", "cwd", "-p", str(pid), "-Fn"],
        capture_output=True,
        text=True,
        check=False,
    )
    for line in result.stdout.splitlines():
        if line.startswith("n"):
            return Path(line[1:])
    return None


def _find_active_transcript(cwd: Path) -> Path | None:
    """Find the most recently written Claude Code session transcript for `cwd`.

    A running session can move to a new session ID (e.g. after compaction)
    without changing the process's command line, so the most recently
    modified transcript in the project's directory is the best signal for
    "the session this process is currently in".
    """
    project_dir = Path.home() / ".claude" / "projects" / str(cwd).replace("/", "-")
    matches = list(project_dir.glob("*.jsonl"))
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def _extract_latest_transcript_field(
    transcript: Path, *, entry_type: str, field: str
) -> str | None:
    """Return the most recent value of `field` from entries of type `entry_type`."""
    for line in reversed(_read_lines(transcript)):
        with contextlib.suppress(json.JSONDecodeError):
            entry = json.loads(line)
            value = entry.get(field)
            if entry.get("type") == entry_type and isinstance(value, str) and value:
                return value
    return None


def _resolve_agent_name(pid: int, *, agent_type: str = "claude") -> str:
    """Resolve Claude's transcript name or use the agent type and PID."""
    if agent_type == "claude" and (
        (cwd := _process_cwd(pid))
        and (transcript := _find_active_transcript(cwd))
        and (
            (
                name := _extract_latest_transcript_field(
                    transcript, entry_type="agent-name", field="agentName"
                )
            )
            or (
                name := _extract_latest_transcript_field(
                    transcript, entry_type="ai-title", field="aiTitle"
                )
            )
        )
    ):
        return name
    return f"{agent_type}-{pid}"


def _get_tmux_session() -> str | None:
    """Get the current tmux session name.

    Requires the `TMUX` env var (set by tmux for processes actually running
    inside a pane). Without it, `tmux display-message` still succeeds by
    falling back to the server's ambient "current" session (e.g. whichever
    session a client last attached to) — misattributing status from a
    headless/background process (no real pane) to an unrelated project.
    """
    if not os.environ.get("TMUX"):
        return None
    command = ["tmux", "display-message", "-p"]
    if pane := os.environ.get("TMUX_PANE"):
        command.extend(["-t", pane])
    result = subprocess.run(
        [*command, "#{session_name}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or None


@cli.command()
@click.option("--name", default=None, help="Agent name (auto-detected when available)")
@click.option("--status", default=None, help="Agent status: idle, working, waiting")
@click.option(
    "--pid",
    type=click.IntRange(min=1),
    default=None,
    help="Stable agent process ID (auto-detected by default)",
)
@click.option("--clear", is_flag=True, help="Clear agent status")
def agent(
    name: str | None, status: str | None, pid: int | None, *, clear: bool
) -> None:
    """Set or clear agent status in the daemon."""
    session = _get_tmux_session()
    if not session:
        click.echo("Not inside tmux", err=True)
        sys.exit(1)

    detected_pid, agent_type = _find_agent_process()
    pid = pid or detected_pid
    agent_type = agent_type or "claude"
    client = require_daemon()
    try:
        if clear:
            client.clear_agent(session, pid=pid)
            return
        if not status:
            click.echo("--status required (or use --clear)", err=True)
            sys.exit(1)
        resolved_name = name or _resolve_agent_name(pid, agent_type=agent_type)
        client.set_agent(session=session, pid=pid, name=resolved_name, status=status)
    finally:
        client.close()
