# add github username PAT
# list
# remove

# from asgiref.sync import async_to_sync

from rich.progress import Progress, SpinnerColumn, BarColumn, TimeElapsedColumn

from ....config import config
from ....project import project_manager
from ._completer import completer

provider_group = completer.group("provider", display_meta="Provider commands")


def _available_providers(*args, **kwargs) -> list[str]:
    return [p.name for p in config.providers] + ["all"]


@provider_group.action("sync", display_meta="Fetch projects from configured providers and cache them locally.")
@completer.param(_available_providers)
async def sync(provider: str = "all"):
    """."""
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
