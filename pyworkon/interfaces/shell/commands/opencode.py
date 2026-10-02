"""CLI commands for the bundled OpenCode integration."""

from __future__ import annotations

import importlib.resources
import os
from pathlib import Path

import click

from pyworkon.interfaces.shell import cli

_PLUGIN_FILES = ("tui.ts", "status.ts")


@cli.group()
def opencode() -> None:
    """Manage the OpenCode integration."""


@opencode.command()
def install() -> None:
    """Install or refresh the bundled plugin in OpenCode's global plugin directory."""
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    destination = config_home / "opencode" / "plugins" / "pyworkon"
    resources = importlib.resources.files("pyworkon.assets").joinpath("opencode")
    try:
        destination.mkdir(parents=True, exist_ok=True)
        for filename in _PLUGIN_FILES:
            (destination / filename).write_bytes(
                resources.joinpath(filename).read_bytes()
            )
    except OSError as error:
        raise click.ClickException(
            f"Could not install OpenCode plugin: {error}"
        ) from error
    click.echo(f"Installed OpenCode plugin: {destination}")
    click.echo("Restart OpenCode to load the plugin.")
