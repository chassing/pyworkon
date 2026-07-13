"""CLI commands for the pyworkon daemon."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import click
from rich import print as rich_print

from pyworkon.config import user_cache_dir
from pyworkon.daemon.client import DaemonClient, DaemonNotRunningError
from pyworkon.daemon.server import PID_FILE, SOCKET_PATH
from pyworkon.interfaces.shell import cli

LAUNCH_AGENT_LABEL = "com.pyworkon.daemon"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST_PATH = LAUNCH_AGENTS_DIR / f"{LAUNCH_AGENT_LABEL}.plist"

LAUNCH_AGENT_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{pyworkon_bin}</string>
        <string>daemon</string>
        <string>start</string>
        <string>--foreground</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{path}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{stdout_log}</string>
    <key>StandardErrorPath</key>
    <string>{stderr_log}</string>
</dict>
</plist>
"""


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
        rich_print(f"[green]Daemon running[/] (PID {info.pid})")
        rich_print(f"  Open projects: {info.open_projects}")
        rich_print(f"  Total projects: {info.total_projects}")
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


@daemon.command()
def install() -> None:
    """Install a LaunchAgent to auto-start the daemon at login (macOS only)."""
    if sys.platform != "darwin":
        click.echo("Error: this command is only available on macOS.", err=True)
        sys.exit(1)

    pyworkon_bin = shutil.which("pyworkon")
    if not pyworkon_bin:
        click.echo("Error: pyworkon not found in PATH.", err=True)
        sys.exit(1)

    updating = PLIST_PATH.exists()
    if updating:
        _launchctl_bootout()

    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(
        LAUNCH_AGENT_PLIST.format(
            label=LAUNCH_AGENT_LABEL,
            pyworkon_bin=pyworkon_bin,
            path=os.environ.get("PATH", ""),
            stdout_log=user_cache_dir / "daemon-launchd.stdout.log",
            stderr_log=user_cache_dir / "daemon-launchd.stderr.log",
        )
    )

    result = subprocess.run(
        ["launchctl", "bootstrap", _launchctl_domain(), str(PLIST_PATH)],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        click.echo(
            f"Error: launchctl bootstrap failed: {result.stderr.strip()}", err=True
        )
        sys.exit(1)

    action = "Updated" if updating else "Installed"
    rich_print(f"[green]{action}:[/] {PLIST_PATH}")
    rich_print(f"Daemon binary: {pyworkon_bin}")
    rich_print("The daemon will now start automatically at login.")


@daemon.command()
def uninstall() -> None:
    """Remove the pyworkon daemon LaunchAgent (macOS only)."""
    if sys.platform != "darwin":
        click.echo("Error: this command is only available on macOS.", err=True)
        sys.exit(1)

    if not PLIST_PATH.exists():
        rich_print("[yellow]LaunchAgent not installed.[/]")
        return

    _launchctl_bootout()
    PLIST_PATH.unlink()
    rich_print(f"[green]Removed:[/] {PLIST_PATH}")


def _launchctl_domain() -> str:
    return f"gui/{os.getuid()}"


def _launchctl_bootout() -> None:
    """Unload the LaunchAgent if currently loaded (no-op if it isn't)."""
    subprocess.run(
        ["launchctl", "bootout", f"{_launchctl_domain()}/{LAUNCH_AGENT_LABEL}"],  # noqa: S607
        capture_output=True,
        check=False,
    )


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
