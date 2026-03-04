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


def project_id_completion(
    ctx: click.Context, param: click.ParamType, incomplete: str
) -> list[str]:
    return [
        project.id
        for project in project_manager.list(local=True)
        if project.id.startswith(incomplete)
    ]


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

    project_manager.enter(project_id, command, title)
