"""Tests for the standalone macOS Dashboard launcher."""

from __future__ import annotations

import importlib
import importlib.resources
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from pyworkon.interfaces.shell import PyworkonContext, cli

app_module = importlib.import_module("pyworkon.interfaces.shell.commands.app")


@pytest.fixture
def bundle_commands(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Copy the fixture runtime, but never sign or launch real applications."""
    mock_run = MagicMock(side_effect=_run_bundle_command)
    monkeypatch.setattr(app_module.subprocess, "run", mock_run)
    return mock_run


@pytest.fixture
def dashboard_app(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bundle_commands: MagicMock
) -> Path:
    """Isolate app installation from the user's applications and Dock."""
    app_dir = tmp_path / "Applications" / "Pyworkon Dashboard.app"
    ghostty_app = tmp_path / "Applications" / "Ghostty Test.app"
    ghostty_bin = ghostty_app / "Contents" / "MacOS" / "ghostty"
    ghostty_bin.parent.mkdir(parents=True)
    ghostty_bin.write_bytes(b"native-runtime")
    (ghostty_app / "Contents" / "Info.plist").write_bytes(
        plistlib.dumps({
            "CFBundleExecutable": "ghostty",
            "CFBundleIdentifier": "com.mitchellh.ghostty",
            "CFBundleName": "Ghostty",
            "CFBundleDisplayName": "Ghostty",
            "CFBundleIconFile": "Ghostty",
            "CFBundleIconName": "Ghostty",
            "NSDockTilePlugIn": "DockTilePlugin.plugin",
            "NSHighResolutionCapable": True,
            "NSAppleEventsUsageDescription": "Allow automation",
            "LSEnvironment": {"GHOSTTY_MAC_LAUNCH_SOURCE": "app"},
        })
    )
    resources = ghostty_app / "Contents" / "Resources"
    resources.mkdir()
    (resources / "theme-data").write_text("native resources")
    (resources / "theme-link").symlink_to("theme-data")
    monkeypatch.setattr(app_module, "APP_DIR", app_dir)
    monkeypatch.setattr(app_module, "GHOSTTY_APP", ghostty_app)
    monkeypatch.setattr(app_module, "GHOSTTY_BIN", ghostty_bin)
    monkeypatch.setattr(app_module.sys, "platform", "darwin")
    monkeypatch.setattr(
        app_module.shutil, "which", MagicMock(return_value="/usr/local/bin/pyworkon")
    )
    monkeypatch.setattr(app_module, "_refresh_icon_cache", MagicMock())
    return app_dir


@pytest.mark.parametrize("existing", [False, True])
def test_app_install_launches_ghostty_through_launch_services(
    dashboard_app: Path, *, existing: bool
) -> None:
    launcher = dashboard_app / "Contents" / "MacOS" / "launcher"
    if existing:
        launcher.parent.mkdir(parents=True)
        launcher.write_text("old launcher\n")

    result = CliRunner().invoke(cli, ["app", "install"], obj=PyworkonContext())

    assert result.exit_code == 0, result.output
    script = launcher.read_text()
    assert shlex.split(script.splitlines()[-1]) == [
        "exec",
        "/usr/bin/open",
        "-na",
        "$RESOURCES/Pyworkon Terminal.app",
    ]
    assert 'RESOURCES="$(cd "$(dirname "$0")/../Resources" && pwd)"' in script
    assert 'export XDG_CONFIG_HOME="$RESOURCES/ghostty-config"' in script
    assert launcher.stat().st_mode & 0o111 == 0o111
    resources = dashboard_app / "Contents" / "Resources"
    config_lines = (resources / "ghostty.conf").read_text().splitlines()
    assert shlex.split(config_lines[0].removeprefix("command = "))[-2:] == [
        "/usr/local/bin/pyworkon",
        "dashboard",
    ]
    assert "auto-update = off" in config_lines
    assert not any(line.startswith("macos-icon =") for line in config_lines)
    assert not any(line.startswith("macos-custom-icon =") for line in config_lines)
    assert (resources / "AppIcon.icns").read_bytes() == (
        importlib.resources
        .files("pyworkon.assets")
        .joinpath("AppIcon.icns")
        .read_bytes()
    )
    runtime = resources / "Pyworkon Terminal.app"
    info = plistlib.loads((runtime / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleIdentifier"] == "dev.pyworkon.dashboard.terminal"
    assert info["CFBundleExecutable"] == "ghostty"
    assert info["CFBundleName"] == "Pyworkon Dashboard"
    assert info["CFBundleDisplayName"] == "Pyworkon Dashboard"
    assert info["CFBundleIconFile"] == "PyworkonDashboard"
    assert "CFBundleIconName" not in info
    assert "NSDockTilePlugIn" not in info
    assert info["NSHighResolutionCapable"] is True
    assert info["NSAppleEventsUsageDescription"] == "Allow automation"
    assert (
        runtime / "Contents" / "MacOS" / "ghostty"
    ).read_bytes() == b"native-runtime"
    runtime_resources = runtime / "Contents" / "Resources"
    assert (runtime_resources / "PyworkonDashboard.icns").read_bytes() == (
        resources / "AppIcon.icns"
    ).read_bytes()
    assert (runtime_resources / "theme-link").is_symlink()
    assert (runtime_resources / "theme-link").read_text() == "native resources"
    original_info = plistlib.loads(
        (app_module.GHOSTTY_APP / "Contents" / "Info.plist").read_bytes()
    )
    assert original_info["CFBundleIdentifier"] == "com.mitchellh.ghostty"
    assert original_info["NSDockTilePlugIn"] == "DockTilePlugin.plugin"


def test_app_install_signs_only_the_copied_runtime(
    dashboard_app: Path, bundle_commands: MagicMock
) -> None:
    result = CliRunner().invoke(cli, ["app", "install"], obj=PyworkonContext())
    assert result.exit_code == 0, result.output
    commands = [call.args[0] for call in bundle_commands.call_args_list]
    assert len(commands) == 3
    assert commands[0][:3] == ["/usr/bin/ditto", "--noqtn", str(app_module.GHOSTTY_APP)]
    assert commands[1][:-1] == [
        "/usr/bin/codesign",
        "--force",
        "--sign",
        "-",
        "--preserve-metadata=entitlements",
    ]
    assert commands[1][-1] == commands[0][-1]
    assert commands[1][-1].endswith("/Resources/Pyworkon Terminal.app")
    assert not commands[1][-1].startswith(str(app_module.GHOSTTY_APP))
    assert commands[2] == [
        "/usr/bin/codesign",
        "--verify",
        "--deep",
        "--strict",
        commands[1][-1],
    ]


@pytest.mark.parametrize("xdg_home", [None, "custom configuration"])
def test_runtime_launch_without_outer_wrapper_loads_dashboard_configuration(
    dashboard_app: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    xdg_home: str | None,
) -> None:
    original_xdg_home = str(tmp_path / xdg_home) if xdg_home else ""
    if xdg_home:
        monkeypatch.setenv("XDG_CONFIG_HOME", original_xdg_home)
    else:
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    result = CliRunner().invoke(cli, ["app", "install"], obj=PyworkonContext())
    assert result.exit_code == 0, result.output
    resources = dashboard_app / "Contents" / "Resources"
    runtime_contents = resources / "Pyworkon Terminal.app" / "Contents"
    info = plistlib.loads((runtime_contents / "Info.plist").read_bytes())
    assert info["CFBundleExecutable"] == "ghostty"
    assert info["LSEnvironment"]["GHOSTTY_MAC_LAUNCH_SOURCE"] == "app"
    config_home = Path(info["LSEnvironment"]["XDG_CONFIG_HOME"])
    assert config_home == resources / "ghostty-config"
    config_lines = (config_home / "ghostty" / "config.ghostty").read_text().splitlines()
    xdg_dir = Path(original_xdg_home or Path.home() / ".config") / "ghostty"
    assert config_lines == [
        f"config-file = ?{xdg_dir / 'config'}",
        f"config-file = ?{xdg_dir / 'config.ghostty'}",
        "config-file = ../../ghostty.conf",
    ]


@pytest.mark.skipif(
    sys.platform != "darwin"
    or not Path("/Applications/Ghostty.app/Contents/MacOS/ghostty").is_file(),
    reason="Requires macOS and an installed Ghostty runtime",
)
def test_real_runtime_configuration_and_entitlements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "Pyworkon Dashboard.app"
    monkeypatch.setattr(app_module, "APP_DIR", bundle)
    app_module._install_app(pyworkon_bin="/usr/local/bin/pyworkon")
    runtime = bundle / "Contents" / "Resources" / "Pyworkon Terminal.app"
    info = plistlib.loads((runtime / "Contents" / "Info.plist").read_bytes())
    result = subprocess.run(
        [str(runtime / "Contents" / "MacOS" / "ghostty"), "+show-config"],
        env=os.environ | info["LSEnvironment"],
        check=True,
        capture_output=True,
        text=True,
    )
    config_lines = result.stdout.splitlines()
    command_line = next(line for line in config_lines if line.startswith("command = "))
    assert shlex.split(command_line.removeprefix("command = "))[-2:] == [
        "/usr/local/bin/pyworkon",
        "dashboard",
    ]
    assert "title = Pyworkon Dashboard" in config_lines
    assert "auto-update = off" in config_lines
    original = subprocess.run(
        [
            "/usr/bin/codesign",
            "--display",
            "--entitlements",
            ":-",
            str(app_module.GHOSTTY_BIN),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    copied = subprocess.run(
        [
            "/usr/bin/codesign",
            "--display",
            "--entitlements",
            ":-",
            str(runtime / "Contents" / "MacOS" / "ghostty"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert plistlib.loads(copied.stdout.encode()) == plistlib.loads(
        original.stdout.encode()
    )


@pytest.mark.parametrize("xdg_home", [None, "custom configuration"])
def test_dashboard_command_restores_original_configuration_environment(
    dashboard_app: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    xdg_home: str | None,
) -> None:
    original_xdg_home = str(tmp_path / xdg_home) if xdg_home else ""
    if xdg_home:
        monkeypatch.setenv("XDG_CONFIG_HOME", original_xdg_home)
    else:
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    command = tmp_path / "pyworkon-command"
    command.write_text(
        '#!/usr/bin/env bash\nset -euo pipefail\nprintf "%s\\n" "${XDG_CONFIG_HOME-unset}" "$@"\n'
    )
    command.chmod(0o755)
    monkeypatch.setattr(
        app_module.shutil, "which", MagicMock(return_value=str(command))
    )
    result = CliRunner().invoke(cli, ["app", "install"], obj=PyworkonContext())
    assert result.exit_code == 0, result.output
    resources = dashboard_app / "Contents" / "Resources"
    info = plistlib.loads(
        (resources / "Pyworkon Terminal.app" / "Contents" / "Info.plist").read_bytes()
    )
    command_line = (resources / "ghostty.conf").read_text().splitlines()[0]
    with subprocess.Popen(
        shlex.split(command_line.removeprefix("command = ")),
        env=os.environ | info["LSEnvironment"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        stdout, stderr = process.communicate(timeout=10)
    assert process.returncode == 0, stderr
    assert stdout.splitlines() == [original_xdg_home or "unset", "dashboard"]


@pytest.mark.parametrize(
    ("program", "operation"),
    [
        ("/usr/bin/ditto", "--noqtn"),
        ("/usr/bin/codesign", "--force"),
        ("/usr/bin/codesign", "--verify"),
    ],
)
def test_app_install_preserves_existing_bundle_when_build_fails(
    dashboard_app: Path, bundle_commands: MagicMock, program: str, operation: str
) -> None:
    dashboard_app.mkdir(parents=True)
    (dashboard_app / "existing-file").write_text("keep this bundle")

    def fail_signing(
        args: Sequence[str], *, check: bool, capture_output: bool, text: bool
    ) -> subprocess.CompletedProcess[str]:
        if args[:2] == [program, operation]:
            raise subprocess.CalledProcessError(
                returncode=1, cmd=args, stderr="bundle build failed"
            )
        return _run_bundle_command(
            args, check=check, capture_output=capture_output, text=text
        )

    bundle_commands.side_effect = fail_signing
    result = CliRunner().invoke(cli, ["app", "install"], obj=PyworkonContext())
    assert result.exit_code == 1
    assert "bundle build failed" in result.output
    assert (dashboard_app / "existing-file").read_text() == "keep this bundle"
    assert sorted(path.name for path in dashboard_app.iterdir()) == ["existing-file"]


def test_app_install_restores_existing_bundle_when_publication_fails(
    dashboard_app: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dashboard_app.mkdir(parents=True)
    (dashboard_app / "existing-file").write_text("keep this bundle")
    rename = Path.rename

    def fail_publication(path: Path, target: Path) -> Path:
        if path.name == dashboard_app.name and path.parent != dashboard_app.parent:
            raise OSError("publication failed")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_publication)
    result = CliRunner().invoke(cli, ["app", "install"], obj=PyworkonContext())
    assert result.exit_code == 1
    assert "publication failed" in result.output
    assert (dashboard_app / "existing-file").read_text() == "keep this bundle"


def test_app_install_reports_invalid_runtime_metadata(dashboard_app: Path) -> None:
    (app_module.GHOSTTY_APP / "Contents" / "Info.plist").write_bytes(
        plistlib.dumps(["invalid metadata"])
    )
    result = CliRunner().invoke(cli, ["app", "install"], obj=PyworkonContext())
    assert result.exit_code == 1
    assert "Ghostty Info.plist must contain a dictionary" in result.output
    assert not dashboard_app.exists()


def _run_bundle_command(
    args: Sequence[str], *, check: bool, capture_output: bool, text: bool
) -> subprocess.CompletedProcess[str]:
    assert check
    assert capture_output
    assert text
    if args[0] == "/usr/bin/ditto":
        shutil.copytree(args[-2], args[-1], symlinks=True)
    return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
