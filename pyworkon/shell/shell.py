import asyncio

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout

from ..config import config
from .actions import completer


class PyWorkonShell:
    def __init__(self) -> None:
        pass

    async def _run(self):
        session = PromptSession(
            config.prompt_sign,
            completer=completer,
            complete_in_thread=True,
            history=FileHistory(config.history_file),
            auto_suggest=AutoSuggestFromHistory(),
        )
        while True:
            with patch_stdout():
                prompt_result = await session.prompt_async()
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
