"""Tests for Daemon (_build_sidebar_state, _on_branch_change, _on_dirty_change)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pyworkon.daemon.models import AgentInfo, OpenProject
from pyworkon.daemon.project_mgr import Project
from pyworkon.daemon.server import Daemon


@pytest.fixture
def daemon() -> Daemon:
    """Create a Daemon with mocked ProjectManager and GitWatcher."""
    with (
        patch("pyworkon.daemon.server.Daemon._create_git_watcher") as mock_gw,
        patch("pyworkon.daemon.project_mgr.ProjectManager.__init__", return_value=None),
    ):
        mock_gw.return_value = MagicMock()
        d = Daemon()
        d._project_mgr.list = MagicMock(return_value=[])
        d._project_mgr.get = MagicMock(side_effect=KeyError)
        return d


def test_build_sidebar_state_empty(daemon: Daemon) -> None:
    state = daemon._build_sidebar_state()
    assert state["sessions"] == []
    assert state["plain_sessions"] == []
    assert state["projects"] == []


def test_build_sidebar_state_with_open_project(daemon: Daemon) -> None:
    project = Project(id="github/owner/repo")
    daemon._project_mgr.get = MagicMock(return_value=project)
    daemon._project_mgr.list = MagicMock(return_value=[project])
    daemon._open_projects["github/owner/repo|default"] = OpenProject(
        project_id="github/owner/repo",
        pane_id=None,
        session="my-session",
        branch="feature",
        is_dirty=True,
        agents=[AgentInfo(name="claude", status="working")],
    )

    state = daemon._build_sidebar_state()

    assert len(state["sessions"]) == 1
    session = state["sessions"][0]
    assert session["session_name"] == "my-session"
    assert session["branch"] == "feature"
    assert session["is_dirty"] is True
    assert session["agents"] == [{"name": "claude", "status": "working"}]
    assert session["project"]["id"] == "github/owner/repo"
    assert state["projects"] == []


def test_build_sidebar_state_plain_sessions(daemon: Daemon) -> None:
    daemon._plain_sessions = ["scratch", "notes"]
    state = daemon._build_sidebar_state()
    assert state["plain_sessions"] == ["notes", "scratch"]


def test_build_sidebar_state_unattached_projects(daemon: Daemon) -> None:
    project = Project(id="github/owner/repo")
    daemon._project_mgr.list = MagicMock(return_value=[project])

    state = daemon._build_sidebar_state()
    assert len(state["projects"]) == 1
    assert state["projects"][0]["id"] == "github/owner/repo"


async def test_on_branch_change(daemon: Daemon) -> None:
    project = Project(id="github/owner/repo")
    daemon._project_mgr.get = MagicMock(return_value=project)
    daemon._open_projects["github/owner/repo|default"] = OpenProject(
        project_id="github/owner/repo",
        pane_id=None,
        session="sess",
        branch="old-branch",
    )

    with (
        patch.object(
            Project,
            "get_current_branch",
            new_callable=AsyncMock,
            return_value="new-branch",
        ),
        patch.object(
            Project,
            "has_uncommitted_changes",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        await daemon._on_branch_change("github/owner/repo")

    op = daemon._open_projects["github/owner/repo|default"]
    assert op.branch == "new-branch"
    assert op.is_dirty is True
    assert op.pr_data is None
    assert op.pr_fetched_at < 1e-9


async def test_on_dirty_change(daemon: Daemon) -> None:
    project = Project(id="github/owner/repo")
    daemon._project_mgr.get = MagicMock(return_value=project)
    daemon._open_projects["github/owner/repo|default"] = OpenProject(
        project_id="github/owner/repo",
        pane_id=None,
        session="sess",
        branch="main",
        is_dirty=False,
    )

    with patch.object(
        Project, "has_uncommitted_changes", new_callable=AsyncMock, return_value=True
    ):
        await daemon._on_dirty_change("github/owner/repo")

    op = daemon._open_projects["github/owner/repo|default"]
    assert op.is_dirty is True
