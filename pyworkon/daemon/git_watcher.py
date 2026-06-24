"""Watch project directories for git branch changes and working tree modifications."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from watchfiles import awatch

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

log = logging.getLogger(__name__)
logging.getLogger("watchfiles").setLevel(logging.WARNING)

_GIT_HEAD = "/.git/HEAD"
_GIT_INDEX = "/.git/index"
_GIT_REFS_HEADS = "/.git/refs/heads/"


def _project_filter(change: object, path: str) -> bool:
    """Include .git/HEAD, .git/index, and branch refs; exclude rest of .git/."""
    if path.endswith((_GIT_HEAD, _GIT_INDEX)):
        return True
    if _GIT_REFS_HEADS in path:
        return True
    if "/.git/" in path:
        return False
    from watchfiles import Change, DefaultFilter

    return DefaultFilter()(Change(change), path)  # type: ignore[arg-type]


class GitWatcher:
    """Watches project directories for branch and working tree changes."""

    def __init__(
        self,
        on_branch_change: Callable[[str], Awaitable[None]],
        on_dirty_change: Callable[[str], Awaitable[None]],
    ) -> None:
        self._on_branch_change = on_branch_change
        self._on_dirty_change = on_dirty_change
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def watch(self, project_id: str, project_home: Path) -> None:
        """Start watching a project directory."""
        if project_id in self._tasks:
            return
        if not (project_home / ".git").is_dir():
            return
        self._tasks[project_id] = asyncio.create_task(
            self._watch_loop(project_id, project_home)
        )
        log.info("Watching: %s", project_id)

    async def unwatch(self, project_id: str) -> None:
        """Stop watching a project."""
        if task := self._tasks.pop(project_id, None):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            log.info("Unwatched: %s", project_id)

    async def stop(self) -> None:
        """Stop all watches."""
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    async def _watch_loop(self, project_id: str, project_home: Path) -> None:

        try:
            async for changes in awatch(
                project_home, watch_filter=_project_filter, step=100
            ):
                paths = {p for _, p in changes}
                if any(p.endswith(_GIT_HEAD) for p in paths):
                    await self._on_branch_change(project_id)
                if any(not p.endswith((_GIT_HEAD, _GIT_INDEX)) for p in paths) or any(
                    p.endswith(_GIT_INDEX) for p in paths
                ):
                    await self._on_dirty_change(project_id)
        except FileNotFoundError:
            log.debug("Project dir removed: %s", project_id)
