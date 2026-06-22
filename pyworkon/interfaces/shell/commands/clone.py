import click
from rich import print as rich_print

from pyworkon.daemon.client import require_daemon
from pyworkon.daemon.protocol import ResponseType
from pyworkon.interfaces.shell import cli
from pyworkon.interfaces.shell.command import PyworkonCommand


def project_completion(
    ctx: click.Context, command: PyworkonCommand, argument: click.Argument
) -> list[str]:
    if argument.name == "project_id":
        client = require_daemon()
        try:
            return [p["id"] for p in client.list_projects(local=False)]
        finally:
            client.close()
    return []


@cli.command(completion_callback=project_completion)
@click.argument("project_id")
def clone(project_id: str) -> None:
    """Clone a project."""
    if not project_id:
        rich_print("[b red]Please provide a project ID or an URL to a repository![/]")
        return

    client = require_daemon()
    try:
        for resp in client.clone_project(project_id):
            if resp.type == ResponseType.PROGRESS:
                rich_print(f"[blue]{resp.msg}[/]")
            elif resp.type == ResponseType.ERROR:
                rich_print(f"[red]{resp.msg}[/]")
            elif resp.type == ResponseType.OK:
                rich_print("[green]Done.[/]")
    finally:
        client.close()
