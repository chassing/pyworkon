"""Tests for GitWatcher lifecycle (watch, unwatch, stop) and project filter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from watchfiles import Change

from pyworkon.daemon.git_watcher import GitWatcher, _project_filter


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/repo/.git/HEAD", True),
        ("/repo/.git/index", True),
        ("/repo/.git/refs/heads/main", True),
        ("/repo/.git/refs/heads/feature/foo", True),
        ("/repo/.git/refs/remotes/origin/main", False),
        ("/repo/.git/objects/ab/cdef1234", False),
        ("/repo/.git/logs/HEAD", False),
        ("/repo/.git/index.lock", False),
        ("/repo/.git/COMMIT_EDITMSG", False),
        ("/repo/src/main.py", True),
        ("/repo/.github/workflows/ci.yml", True),
    ],
)
def test_project_filter(path: str, expected: bool) -> None:
    assert _project_filter(Change.modified, path) is expected


@pytest.fixture
def watcher() -> GitWatcher:
    return GitWatcher(
        on_branch_change=AsyncMock(),
        on_dirty_change=AsyncMock(),
    )


async def test_watch_valid_git_dir(watcher: GitWatcher, tmp_git_repo: Path) -> None:
    await watcher.watch("proj-1", tmp_git_repo)
    assert "proj-1" in watcher._tasks
    await watcher.stop()


async def test_watch_non_git_dir(watcher: GitWatcher, tmp_path: Path) -> None:
    await watcher.watch("proj-1", tmp_path)
    assert "proj-1" not in watcher._tasks


async def test_watch_idempotent(watcher: GitWatcher, tmp_git_repo: Path) -> None:
    await watcher.watch("proj-1", tmp_git_repo)
    task = watcher._tasks["proj-1"]
    await watcher.watch("proj-1", tmp_git_repo)
    assert watcher._tasks["proj-1"] is task
    assert len(watcher._tasks) == 1
    await watcher.stop()


async def test_unwatch_cancels_task(watcher: GitWatcher, tmp_git_repo: Path) -> None:
    await watcher.watch("proj-1", tmp_git_repo)
    task = watcher._tasks["proj-1"]
    await watcher.unwatch("proj-1")
    assert "proj-1" not in watcher._tasks
    assert task.cancelled()


async def test_unwatch_nonexistent_is_noop(watcher: GitWatcher) -> None:
    await watcher.unwatch("does-not-exist")
    assert len(watcher._tasks) == 0


async def test_stop_cancels_all(watcher: GitWatcher, tmp_git_repo: Path) -> None:
    second_repo = tmp_git_repo.parent / "repo2"
    second_repo.mkdir()
    (second_repo / ".git").mkdir()

    await watcher.watch("proj-1", tmp_git_repo)
    await watcher.watch("proj-2", second_repo)
    assert len(watcher._tasks) == 2

    await watcher.stop()
    assert len(watcher._tasks) == 0
