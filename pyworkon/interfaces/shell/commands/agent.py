"""CLI command for setting agent status via daemon."""

from __future__ import annotations

import os
import subprocess
import sys

import click

from pyworkon.daemon.client import require_daemon
from pyworkon.interfaces.shell import cli


def _resolve_agent_name() -> str:
    """Derive agent name from parent PID (the Claude Code process running this hook)."""
    return f"claude-{os.getppid()}"


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
            resolved_name = name or _resolve_agent_name()
            client.clear_agent(session, name=resolved_name)
            return
        if not status:
            click.echo("--status required (or use --clear)", err=True)
            sys.exit(1)
        resolved_name = name or _resolve_agent_name()
        client.set_agent(session=session, name=resolved_name, status=status)
    finally:
        client.close()
