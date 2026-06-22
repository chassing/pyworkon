"""CLI command for setting agent status via daemon."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import click

from pyworkon.daemon.client import require_daemon
from pyworkon.interfaces.shell import cli

_CLAUDE_SESSIONS_DIR = Path.home() / ".claude" / "sessions"


def _resolve_agent_name() -> str:
    """Resolve agent name from Claude Code session file matching current cwd."""
    cwd = str(Path.cwd())
    for session_file in _CLAUDE_SESSIONS_DIR.glob("*.json"):
        try:
            with session_file.open() as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("cwd") == cwd and data.get("status") in {"busy", "idle", "waiting"}:
            return data.get("name") or f"claude-{data.get('pid', '?')}"
    return "claude"


def _get_tmux_session() -> str | None:
    """Get the current tmux session name."""
    result = subprocess.run(
        ["tmux", "display-message", "-p", "#{session_name}"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or None


@cli.command()
@click.option(
    "--name", default=None, help="Agent name (auto-detected from Claude Code session)"
)
@click.option("--status", default=None, help="Agent status emoji")
@click.option("--clear", is_flag=True, help="Clear agent status")
def agent(name: str | None, status: str | None, *, clear: bool) -> None:
    """Set or clear agent status in the daemon."""
    session = _get_tmux_session()
    if not session:
        click.echo("Not inside tmux", err=True)
        sys.exit(1)

    client = require_daemon()
    try:
        if clear:
            client.clear_agent(session, name=name)
            return
        if not status:
            click.echo("--status required (or use --clear)", err=True)
            sys.exit(1)
        resolved_name = name or _resolve_agent_name()
        client.set_agent(session=session, name=resolved_name, status=status)
    finally:
        client.close()
