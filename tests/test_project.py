"""Tests for Project git methods (get_current_branch, has_uncommitted_changes, get_default_branch)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pyworkon.config import config
from pyworkon.daemon.project_mgr import Project


@pytest.fixture
def project(tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Project:
    """Create a Project whose project_home points at the temporary git repo."""
    monkeypatch.setattr(config, "workspace_dir", tmp_git_repo.parent)
    return Project(id=tmp_git_repo.name)


async def test_get_current_branch_main(project: Project) -> None:
    result = await project.get_current_branch()
    assert result == "main"


async def test_get_current_branch_after_checkout(project: Project) -> None:
    subprocess.run(
        ["git", "-C", str(project.project_home), "checkout", "-b", "feature"],
        check=True,
        capture_output=True,
    )
    result = await project.get_current_branch()
    assert result == "feature"


async def test_has_uncommitted_changes_clean(project: Project) -> None:
    assert await project.has_uncommitted_changes() is False


async def test_has_uncommitted_changes_modified_tracked(project: Project) -> None:
    (project.project_home / "README.md").write_text("modified")
    assert await project.has_uncommitted_changes() is True


async def test_has_uncommitted_changes_untracked_only(project: Project) -> None:
    (project.project_home / "new_file.txt").write_text("untracked")
    assert await project.has_uncommitted_changes() is False


async def test_get_default_branch(project: Project) -> None:
    repo = str(project.project_home)
    subprocess.run(
        ["git", "-C", repo, "remote", "add", "origin", repo],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", repo, "fetch", "origin"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            repo,
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
            "refs/remotes/origin/main",
        ],
        check=True,
        capture_output=True,
    )
    result = await project.get_default_branch()
    assert result == "main"


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("get_current_branch", None),
        ("has_uncommitted_changes", False),
        ("get_default_branch", None),
    ],
)
async def test_non_local_project_returns_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    expected: object,
) -> None:
    monkeypatch.setattr(config, "workspace_dir", tmp_path)
    project = Project(id="nonexistent")
    result = await getattr(project, method)()
    assert result == expected
