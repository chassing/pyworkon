from typing import Union

from nubia import (
    argument,
    command,
    context,
)
from pydantic import HttpUrl
from rich.prompt import Prompt
from rich.table import Table

from ....config import (
    Provider,
    ProviderType,
    config,
)
from ....project import project_manager
from ....providers import get_default_url
from ..plugin import ShellContext


@command("provider")
class ProviderCommand:
    """Provider related command."""

    def __init__(self):
        self._ctx: ShellContext = context.get_context()

    @command
    @argument("provider", description="Provider name", choices=[p.name for p in config.providers] + ["all"])
    async def sync(self, provider: str):
        """Fetch projects from configured providers and cache them locally."""
        if provider == "all":
            providers = config.providers
        else:
            providers = [p for p in config.providers if p.name == provider]

        with self._ctx.progress_spinner() as progress:
            sync_task = progress.add_task("Sync", total=len(providers))
            for p in providers:
                self._ctx.print(f"Fetching projects from {p.name}", printer=progress.console.print)
                await project_manager.sync(p)
                progress.advance(sync_task)

    @command("list")
    async def ls(self):
        """List all configured providers."""
        table = Table(title="Providers")
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="magenta")
        table.add_column("API")
        table.add_column("User")
        for p in config.providers:
            table.add_row(p.name, p.type.value, p.api_url, p.username)
        self._ctx.print(table)

    @command
    @argument("name", description="Provider Name")
    @argument("provider_type", name="type", description="Provider Type", choices=[pt for pt in ProviderType])
    @argument("username", description="Username")
    @argument("api_url", description="API URL to self-hosted instance")
    async def add(self, name: str, provider_type: ProviderType, username: str, api_url: Union[HttpUrl, None] = None):
        """Configure an additional project provider."""
        if name in [p.name for p in config.providers]:
            self._ctx.print(f"[b red]{name=} already in use. Choose another one![/]")
            return 1
        if not api_url:
            api_url = get_default_url(provider_type)

        password = Prompt.ask("Enter Password/Personal Access Token")
        provider = Provider(name=name, type=provider_type, api_url=api_url, username=username, password=password)
        config.providers.append(provider)
        config.save()
        await self.sync(provider=name)
        self._ctx.print(f"[green]New project provider {name=} has been added to the configuration.[/]")
        if self._ctx.is_interactive:
            self._ctx.print("Restart your shell to refresh caches!")

    @command
    @argument("name", description="Provider Name", choices=[p.name for p in config.providers])
    async def rm(self, name: str):
        """Remove a project provider."""
        for i, provider in enumerate(list(config.providers)):
            if provider.name == name:
                await project_manager.remove_projects(provider=provider)
                del config.providers[i]
                break

        config.save()
        self._ctx.print(f"[green]Provider {name=} and cached projects have been removed from the configuration.[/]")
        if self._ctx.is_interactive:
            self._ctx.print("Restart your shell to refresh caches!")
