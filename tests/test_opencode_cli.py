"""Tests for installing the bundled OpenCode plugin."""

from __future__ import annotations

import importlib
import importlib.resources
from pathlib import Path

import pytest
from click.testing import CliRunner

from pyworkon.interfaces.shell import PyworkonContext, cli

importlib.import_module("pyworkon.interfaces.shell.commands")


@pytest.fixture
def plugin_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("TMUX", raising=False)
    return tmp_path


def test_opencode_runtime_is_available_as_package_resources() -> None:
    resources = importlib.resources.files("pyworkon.assets").joinpath("opencode")

    assert resources.joinpath("tui.ts").is_file()
    assert resources.joinpath("status.ts").is_file()


@pytest.mark.parametrize("custom_xdg", [False, True])
def test_opencode_install_uses_bundled_resources(
    monkeypatch: pytest.MonkeyPatch, plugin_home: Path, *, custom_xdg: bool
) -> None:
    config_home = plugin_home / ("custom config" if custom_xdg else ".config")
    if custom_xdg:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    config_dir = config_home / "opencode"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "cli.json"
    config_file.write_text('{"terminal":{"title":false}}\n')

    result = CliRunner().invoke(cli, ["opencode", "install"], obj=PyworkonContext())

    assert result.exit_code == 0, result.output
    destination = config_dir / "plugins" / "pyworkon"
    resources = importlib.resources.files("pyworkon.assets").joinpath("opencode")
    assert sorted(path.name for path in destination.iterdir()) == [
        "status.ts",
        "tui.ts",
    ]
    for filename in ("status.ts", "tui.ts"):
        assert (destination / filename).read_bytes() == resources.joinpath(
            filename
        ).read_bytes()
    assert str(destination) in result.output
    assert config_file.read_text() == '{"terminal":{"title":false}}\n'


def test_opencode_install_refreshes_only_owned_plugin_files(plugin_home: Path) -> None:
    destination = plugin_home / ".config" / "opencode" / "plugins" / "pyworkon"
    destination.mkdir(parents=True)
    (destination / "tui.ts").write_text("old plugin")
    (destination / "notes.txt").write_text("user notes")

    result = CliRunner().invoke(cli, ["opencode", "install"], obj=PyworkonContext())

    assert result.exit_code == 0, result.output
    assert (destination / "tui.ts").read_bytes() == (
        importlib.resources
        .files("pyworkon.assets")
        .joinpath("opencode", "tui.ts")
        .read_bytes()
    )
    assert (destination / "notes.txt").read_text() == "user notes"


def test_opencode_install_reports_filesystem_errors(plugin_home: Path) -> None:
    (plugin_home / ".config").write_text("not a directory")

    result = CliRunner().invoke(cli, ["opencode", "install"], obj=PyworkonContext())

    assert result.exit_code == 1
    assert "Error: Could not install OpenCode plugin:" in result.output
