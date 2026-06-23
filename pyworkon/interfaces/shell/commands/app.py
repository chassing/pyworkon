"""CLI commands for macOS app bundle management."""

from __future__ import annotations

import contextlib
import importlib.resources
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import click
from rich import print as rich_print

from pyworkon.interfaces.shell import cli

APP_NAME = "Pyworkon Dashboard"
APP_DIR = Path.home() / "Applications" / f"{APP_NAME}.app"
GHOSTTY_APP = Path("/Applications/Ghostty.app")
LSREGISTER = Path(
    "/System/Library/Frameworks/CoreServices.framework"
    "/Frameworks/LaunchServices.framework/Support/lsregister"
)

INFO_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>{name}</string>
    <key>CFBundleDisplayName</key>
    <string>{name}</string>
    <key>CFBundleIdentifier</key>
    <string>dev.pyworkon.dashboard</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
"""

GHOSTTY_BIN = GHOSTTY_APP / "Contents" / "MacOS" / "ghostty"

LAUNCHER_SCRIPT = """\
#!/bin/bash
RESOURCES="$(cd "$(dirname "$0")/../Resources" && pwd)"
exec {ghostty_bin} --config-file="$RESOURCES/ghostty.conf"
"""

GHOSTTY_CONF = """\
command = {pyworkon_bin} dashboard
quit-after-last-window-closed = true
title = Pyworkon Dashboard
window-width = 150
window-height = 58
window-position-x = 0
window-position-y = 0
"""


@cli.group()
def app() -> None:
    """Manage the macOS app bundle."""


@app.command()
def install() -> None:
    """Install Pyworkon Dashboard as a macOS app in ~/Applications."""
    if sys.platform != "darwin":
        click.echo("Error: this command is only available on macOS.", err=True)
        sys.exit(1)

    if not GHOSTTY_BIN.exists():
        click.echo("Error: Ghostty.app not found in /Applications.", err=True)
        sys.exit(1)

    pyworkon_bin = shutil.which("pyworkon")
    if not pyworkon_bin:
        click.echo("Error: pyworkon not found in PATH.", err=True)
        sys.exit(1)

    updating = APP_DIR.exists()

    contents = APP_DIR / "Contents"
    macos_dir = contents / "MacOS"
    resources_dir = contents / "Resources"
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    (contents / "Info.plist").write_text(INFO_PLIST.format(name=APP_NAME))

    launcher = macos_dir / "launcher"
    launcher.write_text(LAUNCHER_SCRIPT.format(ghostty_bin=GHOSTTY_BIN))
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    (resources_dir / "ghostty.conf").write_text(
        GHOSTTY_CONF.format(pyworkon_bin=pyworkon_bin)
    )

    icon_src = importlib.resources.files("pyworkon.assets").joinpath("AppIcon.icns")
    with importlib.resources.as_file(icon_src) as icon_path:
        shutil.copy2(icon_path, resources_dir / "AppIcon.icns")

    _refresh_icon_cache()

    action = "Updated" if updating else "Installed"
    rich_print(f"[green]{action}:[/] {APP_DIR}")
    rich_print("Launch via Spotlight or: [bold]open -a 'Pyworkon Dashboard'[/]")


def _refresh_icon_cache() -> None:
    """Force macOS to re-read the app icon."""
    with contextlib.suppress(subprocess.CalledProcessError, FileNotFoundError):
        subprocess.run(
            [str(LSREGISTER), "-f", str(APP_DIR)],
            check=True,
            capture_output=True,
        )
    with contextlib.suppress(subprocess.CalledProcessError, FileNotFoundError):
        subprocess.run(["/usr/bin/killall", "Dock"], check=True, capture_output=True)


@app.command()
def uninstall() -> None:
    """Remove the Pyworkon Dashboard macOS app."""
    if not APP_DIR.exists():
        rich_print("[yellow]App not installed.[/]")
        return

    shutil.rmtree(APP_DIR)
    rich_print(f"[green]Removed:[/] {APP_DIR}")
