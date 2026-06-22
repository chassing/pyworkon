from rich import print as rich_print
from rich.table import Table

from pyworkon.config import config
from pyworkon.daemon.client import require_daemon
from pyworkon.daemon.protocol import ResponseType
from pyworkon.interfaces.shell import cli


@cli.group()
def provider() -> None:
    """Provider related commands."""


@provider.command()
def sync() -> None:
    """Fetch projects from configured providers and cache them locally."""
    client = require_daemon()
    try:
        for resp in client.sync_providers():
            if resp.type == ResponseType.PROGRESS:
                rich_print(f"[blue]{resp.msg}[/]")
            elif resp.type == ResponseType.ERROR:
                rich_print(f"[red]{resp.msg}[/]")
            elif resp.type == ResponseType.OK:
                rich_print("[green]Done.[/]")
    finally:
        client.close()


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
