"""CLI commands for the pyworkon daemon."""

from __future__ import annotations

import os
import sys

import click
from rich import print as rich_print

from pyworkon.daemon.client import DaemonClient, DaemonNotRunningError
from pyworkon.daemon.server import PID_FILE, SOCKET_PATH
from pyworkon.interfaces.shell import cli


@cli.group()
def daemon() -> None:
    """Manage the pyworkon daemon."""


@daemon.command()
@click.option("--debug", is_flag=True, help="Run in foreground with debug logging")
@click.option(
    "--foreground", is_flag=True, help="Run in foreground (for launchd/systemd)"
)
def start(*, debug: bool, foreground: bool) -> None:
    """Start the daemon in the background."""
    if _is_running():
        rich_print("[yellow]Daemon is already running.[/]")
        return

    from pyworkon.daemon.server import run_daemon

    if debug or foreground:
        run_daemon(debug=debug)
        return

    pid = os.fork()
    if pid > 0:
        rich_print(f"[green]Daemon started (PID {pid}).[/]")
        return

    os.setsid()
    sys.stdin.close()
    run_daemon()


@daemon.command()
def stop() -> None:
    """Stop the running daemon."""
    try:
        with DaemonClient() as client:
            client.shutdown()
        rich_print("[green]Daemon stopped.[/]")
    except DaemonNotRunningError:
        rich_print("[yellow]Daemon is not running.[/]")


@daemon.command()
def status() -> None:
    """Show daemon status."""
    if not _is_running():
        rich_print("[red]Daemon is not running.[/]")
        sys.exit(1)

    try:
        with DaemonClient() as client:
            info = client.status()
        rich_print(f"[green]Daemon running[/] (PID {info.get('pid', '?')})")
        rich_print(f"  Open projects: {info.get('open_projects', 0)}")
        rich_print(f"  Total projects: {info.get('total_projects', 0)}")
    except DaemonNotRunningError:
        rich_print("[red]Daemon is not running.[/]")
        sys.exit(1)


@daemon.command()
@click.argument("message")
@click.option(
    "--level",
    type=click.Choice(["information", "warning", "error"]),
    default="information",
    help="Notification severity level",
)
def notify(message: str, level: str) -> None:
    """Send a notification to all dashboard/sidebar subscribers."""
    try:
        with DaemonClient() as client:
            client.send_notification(message, level=level)
    except DaemonNotRunningError:
        rich_print("[yellow]Daemon is not running.[/]")
        sys.exit(1)


def _is_running() -> bool:
    """Check if the daemon is running via PID file and socket."""
    if not PID_FILE.exists():
        return False
    pid = int(PID_FILE.read_text().strip())
    try:
        os.kill(pid, 0)
    except OSError:
        PID_FILE.unlink(missing_ok=True)
        return False
    return SOCKET_PATH.exists()
