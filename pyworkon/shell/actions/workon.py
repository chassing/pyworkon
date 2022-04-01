import re
import subprocess

from asgiref.sync import async_to_sync

from ...config import config
from ...exceptions import ProjectNotFound
from ...project import Project
from ...utils import url_to_project_id
from ._completer import completer


async def test() -> list[Project]:
    return [Project("github/chassing/pyworkon"), Project("github/org/foobar"), Project("gitlab/chassing/juppi")]


async def _project_list(*args, **kwargs) -> list[str]:
    return [str(project.id) for project in await test()]


# help_text = """Bootstrap and enter a project. Optionally enter it on a build host matching the given ARCH.

# PROJECT can be:

#     * A NuDev project name - see nudev4 project list

#     * A git repository url, e.g. https://github.com/python/cpython.git

# ARCH can be one of the following:

# \b
# {}

# Reenter current PROJECT on different ARCH:

# If you are inside a project and want to enter it on a different ARCH, you can call workon again and leave out the PROJECT argument as a shortcut.
# """.format(
#     "\n".join([f"    * {gi}" + (f" (alias for {OSES[gi].name})" if gi != OSES[gi].name else "") for gi in ["gi7"]])
# )


@completer.action("workon")
@completer.param(async_to_sync(_project_list))
async def workon(project_id: str):
    """Bootstrap and enter a project."""

    if re.match(r"https?://", project_id):
        # hack other github/bitbucket/gitlab repositories :)
        repo_url = project_id
        project_id = url_to_project_id(repo_url)
        project = Project(id=project_id, repository_url=repo_url)
    else:
        try:
            project = await Project.get(project_id)
        except ProjectNotFound:
            print(f"[b red]Project '{project_id}' does not exist[/]")
            return

    await project.enter()
