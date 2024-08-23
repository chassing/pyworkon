import click
from rich import print as rich_print

from pyworkon.interfaces.shell import cli
from pyworkon.interfaces.shell.command import PyworkonCommand
from pyworkon.project import project_manager


def project_completion(
    ctx: click.Context, command: PyworkonCommand, argument: click.Argument
) -> list[str]:
    if argument.name == "project_id":
        return [project.id for project in project_manager.list(local=True)]

    return []


@cli.command(completion_callback=project_completion)
@click.argument("project_id")
def workon(project_id: str) -> None:
    """Enter a project."""
    if not project_id:
        rich_print("[b red]Please provide a project ID or an URL to a repository![/]")
        return

    project_manager.enter(project_id)
