"""Shared test fixtures."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pyworkon.daemon.models import (
    AgentInfo,
    CICheck,
    PRInfo,
    PRReviewStatus,
    PRState,
    PRStatus,
)
from pyworkon.daemon.project_mgr import Project
from pyworkon.interfaces.tui.models import SessionInfo


def make_pr_info(
    *,
    number: int = 42,
    title: str = "Fix auth middleware",
    status: PRStatus = PRStatus.SUCCESS,
    state: PRState = PRState.OPEN,
    url: str = "https://github.com/owner/repo/pull/42",
    review_status: PRReviewStatus = PRReviewStatus.NONE,
    is_draft: bool = False,
    ci_checks: list[CICheck] | None = None,
) -> PRInfo:
    """Create a PRInfo with sensible defaults."""
    return PRInfo(
        number=number,
        title=title,
        status=status,
        state=state,
        url=url,
        review_status=review_status,
        is_draft=is_draft,
        ci_checks=ci_checks or [],
    )


def make_session_info(
    *,
    session_name: str = "test-session",
    project_id: str = "github/owner/repo",
    branch: str | None = "main",
    is_dirty: bool = False,
    pr: PRInfo | None = None,
    agents: list[AgentInfo] | None = None,
    is_current: bool = False,
) -> SessionInfo:
    """Create a SessionInfo with sensible defaults."""
    return SessionInfo(
        session_name=session_name,
        project=Project(id=project_id),
        branch=branch,
        is_dirty=is_dirty,
        pr=pr,
        agents=agents or [],
        is_current=is_current,
    )


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository with an initial commit."""
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    (tmp_path / "README.md").write_text("# test")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "."],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    return tmp_path


@pytest.fixture
def project(tmp_git_repo: Path) -> Project:
    """Create a Project pointing at a temporary git repo."""
    return Project(id=f"test/{tmp_git_repo.name}", repository_url=None)
