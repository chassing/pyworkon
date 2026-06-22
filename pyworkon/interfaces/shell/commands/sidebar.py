import asyncio
import sys

import click

from pyworkon.config import config
from pyworkon.interfaces.shell import cli
from pyworkon.tmux_mgr import tmux_manager


@cli.group(invoke_without_command=True)
@click.pass_context
def sidebar(ctx: click.Context) -> None:
    """Sidebar TUI for pyworkon tmux sessions."""
    if ctx.invoked_subcommand is None:
        from pyworkon.sidebar.app import SidebarApp

        app = SidebarApp()
        app.run()


@cli.command()
def popup() -> None:
    """Project switcher popup (exits after selection)."""
    from pyworkon.sidebar.app import SidebarApp

    app = SidebarApp(popup=True)
    app.run()


@cli.command()
def dashboard() -> None:
    """Read-only dashboard showing all open sessions."""
    from pyworkon.sidebar.app import SidebarApp

    app = SidebarApp(dashboard=True)
    app.run()


@sidebar.command()
@click.option(
    "--no-focus", is_flag=True, help="Don't focus the sidebar pane after creation"
)
def toggle(*, no_focus: bool) -> None:
    """Toggle the sidebar pane in the current tmux window."""
    asyncio.run(_toggle(no_focus=no_focus))


async def _toggle(*, no_focus: bool) -> None:
    if pane_id := await tmux_manager.find_sidebar_pane():
        await tmux_manager.kill_pane(pane_id)
        await _remove_hooks()
        return

    new_pane = await tmux_manager.split_window(
        cmd="pyworkon sidebar",
        width=config.sidebar_width,
        title="sidebar",
        no_focus=no_focus,
    )
    if not new_pane:
        click.echo("Failed to create sidebar pane", err=True)
        sys.exit(1)

    await tmux_manager.set_pane_variable(new_pane, "@pyworkon_sidebar", "1")
    await _install_hooks()


async def _install_hooks() -> None:
    """Install tmux hooks to auto-create sidebar in new windows."""
    if session := await tmux_manager.get_current_session():
        await tmux_manager.set_session_variable(
            session, "@pyworkon_sidebar_active", "1"
        )
        await tmux_manager.set_hook(
            session,
            "after-new-window",
            'run-shell "pyworkon sidebar toggle --no-focus"',
        )


async def _remove_hooks() -> None:
    """Remove sidebar tmux hooks."""
    if session := await tmux_manager.get_current_session():
        await tmux_manager.set_session_variable(
            session, "@pyworkon_sidebar_active", "0"
        )
        await tmux_manager.unset_hook(session, "after-new-window")
