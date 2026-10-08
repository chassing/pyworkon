"""CLI commands for bundled agent integrations and skills."""

from __future__ import annotations

import importlib.resources
import os
from pathlib import Path
from typing import TYPE_CHECKING

import click

from pyworkon.interfaces.shell import cli

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable

_PLUGIN_FILES = ("tui.ts", "status.ts")


@cli.group()
def agentic() -> None:
    """Manage agent integrations and bundled skills."""


@agentic.group()
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


@agentic.command()
def skills_install() -> None:
    """Install or refresh every bundled skill in global agent skill directories."""
    resources = importlib.resources.files("pyworkon.assets").joinpath("skills")
    home = Path.home()
    destinations = [home / ".agents" / "skills"]
    if (claude_skills := home / ".claude" / "skills").is_dir():
        destinations.append(claude_skills)

    try:
        skills = sorted(
            (
                resource
                for resource in resources.iterdir()
                if resource.is_dir() and resource.joinpath("SKILL.md").is_file()
            ),
            key=lambda resource: resource.name,
        )
        if not skills:
            raise click.ClickException("No bundled agent skills found")
        for destination in destinations:
            for skill in skills:
                _copy_skill(source=skill, destination=destination / skill.name)
                click.echo(f"Installed agent skill: {destination / skill.name}")
    except OSError as error:
        raise click.ClickException(
            f"Could not install agent skills: {error}"
        ) from error


def _copy_skill(*, source: Traversable, destination: Path) -> None:
    if destination.is_symlink():
        raise OSError(f"Refusing to overwrite symlink: {destination}")
    if source.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        for resource in source.iterdir():
            _copy_skill(source=resource, destination=destination / resource.name)
        return
    destination.write_bytes(source.read_bytes())
