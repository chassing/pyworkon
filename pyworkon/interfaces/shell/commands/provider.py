from nubia import argument, command
from rich.progress import BarColumn, Progress, SpinnerColumn, TimeElapsedColumn

from ....config import config
from ....project import project_manager


def _available_providers(*args, **kwargs) -> list[str]:
    return [p.name for p in config.providers] + ["all"]


@command("provider")
class ProviderCommand:
    """Provider related command."""

    @command
    @argument("provider", description="Provider name", choices=_available_providers())
    async def sync(self, provider: str):
        """Fetch projects from configured providers and cache them locally."""
        if provider == "all":
            providers = config.providers
        else:
            providers = [p for p in config.providers if p.name == provider]

        with Progress(
            SpinnerColumn(),
            "[progress.description]{task.description}",
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            TimeElapsedColumn(),
        ) as progress:
            sync_task = progress.add_task("Sync", total=len(providers))
            for p in providers:
                progress.console.print(f"Fetching projects from {p.name}")
                await project_manager.sync(p)
                progress.advance(sync_task)

    @command
    async def add(self, name: str):
        """Add new provider"""
        print(f"add: {name=}")
