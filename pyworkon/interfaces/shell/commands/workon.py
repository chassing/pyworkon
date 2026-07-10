import os
import sys

import click
from rich import print as rich_print

from pyworkon.daemon.client import require_daemon
from pyworkon.interfaces.shell import cli
from pyworkon.interfaces.shell.command import PyworkonCommand


def project_completion(
    ctx: click.Context, command: PyworkonCommand, argument: click.Argument
) -> list[str]:
    if argument.name == "project_id":
        client = require_daemon()
        try:
            return [p.id for p in client.list_projects(local=True)]
        finally:
            client.close()
    return []


def project_id_completion(
    ctx: click.Context, param: click.ParamType, incomplete: str
) -> list[str]:
    client = require_daemon()
    try:
        return [
            p.id
            for p in client.list_projects(local=True)
            if p.id.startswith(incomplete)
        ]
    finally:
        client.close()


@cli.command(completion_callback=project_completion)
@click.option("--command", "-c", help="Command to execute after entering the project")
@click.option(
    "--title", "-t", help="Title for the project session (if supported by the terminal)"
)
@click.argument("project_id", shell_complete=project_id_completion)
def workon(
    project_id: str, command: str | None = None, title: str | None = None
) -> None:
    """Enter a project."""
    if not project_id:
        rich_print("[b red]Please provide a project ID or an URL to a repository![/]")
        return

    pane_id = os.environ.get("TMUX_PANE")
    client = require_daemon()
    try:
        project = client.get_project(project_id)
        if not project:
            rich_print(f"[b red]Project not found: {project_id}[/]")
            sys.exit(1)
        client.open_project(project_id, pane_id=pane_id)
        project.enter(command, title)
    finally:
        client.close_project(project_id, pane_id=pane_id)
        client.close()
