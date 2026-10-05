"""CLI commands for macOS app bundle management."""

from __future__ import annotations

import contextlib
import importlib.resources
import plistlib
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import click
from rich import print as rich_print

from pyworkon.interfaces.shell import cli

APP_NAME = "Pyworkon Dashboard"
APP_DIR = Path.home() / "Applications" / f"{APP_NAME}.app"
GHOSTTY_APP = Path("/Applications/Ghostty.app")
RUNTIME_APP_NAME = "Pyworkon Terminal.app"
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
#!/usr/bin/env bash
set -euo pipefail
RESOURCES="$(cd "$(dirname "$0")/../Resources" && pwd)"
exec /usr/bin/open -na "$RESOURCES/Pyworkon Terminal.app" --args --config-file="$RESOURCES/ghostty.conf"
"""

GHOSTTY_CONF = """\
command = {pyworkon_bin} dashboard
quit-after-last-window-closed = true
title = Pyworkon Dashboard
auto-update = off
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

    if pyworkon_bin := shutil.which("pyworkon"):
        updating = APP_DIR.exists()
        try:
            _install_app(pyworkon_bin=pyworkon_bin)
        except subprocess.CalledProcessError as exc:
            raise click.ClickException(
                f"Could not install Dashboard app: {exc.stderr or exc}"
            ) from exc
        except (OSError, TypeError, ValueError, plistlib.InvalidFileException) as exc:
            raise click.ClickException(
                f"Could not install Dashboard app: {exc}"
            ) from exc
    else:
        click.echo("Error: pyworkon not found in PATH.", err=True)
        sys.exit(1)

    _refresh_icon_cache()

    action = "Updated" if updating else "Installed"
    rich_print(f"[green]{action}:[/] {APP_DIR}")
    rich_print("Launch via Spotlight or: [bold]open -a 'Pyworkon Dashboard'[/]")


def _install_app(*, pyworkon_bin: str) -> None:
    APP_DIR.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".pyworkon-app-", dir=APP_DIR.parent) as directory:
        staging_dir = Path(directory)
        staged_app = staging_dir / APP_DIR.name
        _build_app(app_dir=staged_app, pyworkon_bin=pyworkon_bin)
        previous_app = staging_dir / "previous.app"
        if APP_DIR.exists():
            APP_DIR.rename(previous_app)
        try:
            staged_app.rename(APP_DIR)
        except OSError:
            if previous_app.exists():
                previous_app.rename(APP_DIR)
            raise


def _build_app(*, app_dir: Path, pyworkon_bin: str) -> None:
    contents = app_dir / "Contents"
    macos_dir = contents / "MacOS"
    resources_dir = contents / "Resources"
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    (contents / "Info.plist").write_text(INFO_PLIST.format(name=APP_NAME))

    launcher = macos_dir / "launcher"
    launcher.write_text(LAUNCHER_SCRIPT)
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    (resources_dir / "ghostty.conf").write_text(
        GHOSTTY_CONF.format(pyworkon_bin=pyworkon_bin)
    )

    runtime_app = resources_dir / RUNTIME_APP_NAME
    subprocess.run(
        ["/usr/bin/ditto", "--noqtn", str(GHOSTTY_APP), str(runtime_app)],
        check=True,
        capture_output=True,
        text=True,
    )
    _configure_runtime_bundle(runtime_app)

    icon_src = importlib.resources.files("pyworkon.assets").joinpath("AppIcon.icns")
    with importlib.resources.as_file(icon_src) as icon_path:
        shutil.copy2(icon_path, resources_dir / "AppIcon.icns")
        shutil.copy2(
            icon_path,
            runtime_app / "Contents" / "Resources" / "PyworkonDashboard.icns",
        )

    subprocess.run(
        [
            "/usr/bin/codesign",
            "--force",
            "--sign",
            "-",
            "--preserve-metadata=entitlements",
            str(runtime_app),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(runtime_app)],
        check=True,
        capture_output=True,
        text=True,
    )


def _configure_runtime_bundle(runtime_app: Path) -> None:
    info_path = runtime_app / "Contents" / "Info.plist"
    metadata = plistlib.loads(info_path.read_bytes())
    if not isinstance(metadata, dict):
        raise TypeError("Ghostty Info.plist must contain a dictionary")
    metadata["CFBundleIdentifier"] = "dev.pyworkon.dashboard.terminal"
    metadata["CFBundleName"] = APP_NAME
    metadata["CFBundleDisplayName"] = APP_NAME
    metadata["CFBundleIconFile"] = "PyworkonDashboard"
    metadata.pop("CFBundleIconName", None)
    metadata.pop("NSDockTilePlugIn", None)
    info_path.write_bytes(plistlib.dumps(metadata))


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
