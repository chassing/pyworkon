from asgiref.sync import async_to_sync
from nubia import (
    argument,
    command,
)
from rich import print

from ....exceptions import ProjectNotFound
from ....project import project_manager


async def _project_list(*args, **kwargs) -> list[str]:
    return [str(project.id) for project in await project_manager.list() if not project.is_local]


@command("clone")
@argument(
    "project_id", name="id", description="Project ID or URL to repository", choices=async_to_sync(_project_list)()
)
async def clone(project_id: str):
    """Clone a project."""
    if not project_id:
        print("[b red]Please provide a project ID or an URL to a repository![/]")
        return

    try:
        await project_manager.clone(project_id)
    except ProjectNotFound:
        print(f"[b red]Project '{project_id}' does not exist[/]")
        return
