from asgiref.sync import async_to_sync

from ....exceptions import ProjectNotFound
from ....project import project_manager
from ._completer import completer


async def _project_list(*args, **kwargs) -> list[str]:
    return [str(project.id) for project in await project_manager.list()]


@completer.action("workon")
@completer.param(async_to_sync(_project_list))
async def workon(project_id__or__url: str):
    """Bootstrap and enter a project."""
    try:
        await project_manager.enter(project_id__or__url)
    except ProjectNotFound:
        print(f"[b red]Project '{project_id__or__url}' does not exist[/]")
        return
