import click
from rich import print as rich_print
from rich.table import Table

from pyworkon.config import config
from pyworkon.interfaces.shell import cli
from pyworkon.project import project_manager


@cli.group()
def provider() -> None:
    """Provider reladed commands."""


@provider.command()
@click.pass_context
def sync(ctx: click.Context) -> None:
    """Fetch projects from configured providers and cache them locally."""
    with ctx.obj.progress_spinner() as progress:
        progress.add_task("Fetching projects")
        project_manager.sync()


@provider.command()
def ls() -> None:
    """List all configured providers."""
    table = Table(title="Providers")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("API")
    table.add_column("User")
    for p in config.providers:
        table.add_row(p.name, p.type.value, str(p.api_url), p.username)
    rich_print(table)
