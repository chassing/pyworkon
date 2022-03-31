import asyncio

from asgiref.sync import async_to_sync
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import ThreadedCompleter
from prompt_toolkit.patch_stdout import patch_stdout

from ..project import Project
from .action_completer import completer


async def test() -> list[Project]:
    return [Project("github/chassing/pyworkon"), Project("github/org/foobar"), Project("gitlab/chassing/juppi")]


async def _project_list(*args, **kwargs) -> list[str]:
    print("here")
    return [str(project.id) for project in await test()]


@completer.action("workon")
@completer.param(async_to_sync(_project_list))
async def _workon_action(project_id: str):
    print(project_id)


class PyWorkonShell:
    def __init__(self) -> None:
        pass

    async def _run(self):
        session = PromptSession()
        while True:
            with patch_stdout():
                prompt_result = await session.prompt_async("🖖🏻", completer=ThreadedCompleter(completer))
            try:
                await completer.run_action_async(prompt_result)
            except ValueError:
                ...

    @classmethod
    def run(cls, **kwargs):
        """Run the app."""

        async def run_app() -> None:
            app = cls(**kwargs)
            await app._run()

        asyncio.run(run_app())
