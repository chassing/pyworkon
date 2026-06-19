import json
import os
import sys
from pathlib import Path

import click

from pyworkon.config import config
from pyworkon.interfaces.shell import cli
from pyworkon.tmux_mgr import tmux_manager

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


@cli.group(invoke_without_command=True)
@click.option("--popup", is_flag=True, help="Run in popup mode (exit after selection)")
@click.pass_context
def sidebar(ctx: click.Context, *, popup: bool) -> None:
    """Sidebar TUI for pyworkon tmux sessions."""
    if ctx.invoked_subcommand is None:
        from pyworkon.sidebar.app import SidebarApp

        app = SidebarApp(popup=popup)
        app.run()


@sidebar.command()
@click.option(
    "--no-focus", is_flag=True, help="Don't focus the sidebar pane after creation"
)
def toggle(*, no_focus: bool) -> None:
    """Toggle the sidebar pane in the current tmux window."""
    if pane_id := tmux_manager.find_sidebar_pane():
        tmux_manager.kill_pane(pane_id)
        _remove_hooks()
        return

    new_pane = tmux_manager.split_window(
        cmd="pyworkon sidebar",
        width=config.sidebar_width,
        title="sidebar",
        no_focus=no_focus,
    )
    if not new_pane:
        click.echo("Failed to create sidebar pane", err=True)
        sys.exit(1)

    tmux_manager.set_pane_variable(new_pane, "@pyworkon_sidebar", "1")
    _install_hooks()


@sidebar.command()
@click.option(
    "--name",
    default=None,
    help="Agent name (auto-detected from Claude Code session if omitted)",
)
@click.option("--status", default=None, help="Agent status emoji")
@click.option("--clear", is_flag=True, help="Clear agent status from current window")
def agent(name: str | None, status: str | None, *, clear: bool) -> None:
    """Set or clear agent status on the tmux window containing the current pane."""
    target = os.environ.get("TMUX_PANE")
    if not target:
        click.echo("Not inside tmux", err=True)
        sys.exit(1)
    if clear:
        tmux_manager.unset_window_variable(target, "@pyworkon_agent_name")
        tmux_manager.unset_window_variable(target, "@pyworkon_agent_status")
        return
    if not status:
        click.echo("--status is required (or use --clear)", err=True)
        sys.exit(1)
    resolved_name = name or _resolve_agent_name()
    tmux_manager.set_window_variable(target, "@pyworkon_agent_name", resolved_name)
    tmux_manager.set_window_variable(target, "@pyworkon_agent_status", status)


def _install_hooks() -> None:
    """Install tmux hooks to auto-create sidebar in new windows."""
    if session := tmux_manager.get_current_session():
        tmux_manager.set_session_variable(session, "@pyworkon_sidebar_active", "1")
        tmux_manager.set_hook(
            session,
            "after-new-window",
            'run-shell "pyworkon sidebar toggle --no-focus"',
        )


def _remove_hooks() -> None:
    """Remove sidebar tmux hooks."""
    if session := tmux_manager.get_current_session():
        tmux_manager.set_session_variable(session, "@pyworkon_sidebar_active", "0")
        tmux_manager.unset_hook(session, "after-new-window")
