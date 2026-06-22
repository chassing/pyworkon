"""Tests for Daemon (_build_sidebar_state, _on_branch_change, _on_dirty_change, _cmd_kill_session)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pyworkon.daemon.models import AgentInfo, OpenProject
from pyworkon.daemon.project_mgr import Project
from pyworkon.daemon.protocol import Command, CommandType, ResponseType
from pyworkon.daemon.server import Daemon


@pytest.fixture
def daemon() -> Daemon:
    """Create a Daemon with mocked ProjectManager and GitWatcher."""
    with (
        patch("pyworkon.daemon.server.Daemon._create_git_watcher") as mock_gw,
        patch("pyworkon.daemon.project_mgr.ProjectManager.__init__", return_value=None),
    ):
        mock_gw.return_value = MagicMock(unwatch=AsyncMock())
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


async def _collect_responses(
    daemon: Daemon, cmd: Command
) -> list[tuple[ResponseType, str | None]]:
    """Collect all responses from a daemon command handler."""
    return [(resp.type, resp.msg) async for resp in daemon._dispatch(cmd)]


async def test_kill_session_missing_session(daemon: Daemon) -> None:
    cmd = Command(cmd=CommandType.KILL_SESSION)
    responses = await _collect_responses(daemon, cmd)
    assert responses == [(ResponseType.ERROR, "session required")]


async def test_kill_session_not_pyworkon_owned(daemon: Daemon) -> None:
    daemon._plain_sessions = ["foreign-session"]
    notifications: list[tuple[str, str]] = []
    daemon._broadcast = lambda level, msg: notifications.append((level, msg))  # type: ignore[assignment]

    with patch.object(
        Daemon, "_is_pyworkon_session", new_callable=AsyncMock, return_value=False
    ):
        cmd = Command(cmd=CommandType.KILL_SESSION, session="foreign-session")
        responses = await _collect_responses(daemon, cmd)

    assert responses == [(ResponseType.OK, None)]
    assert len(notifications) == 1
    assert notifications[0][0] == "warning"
    assert "foreign-session" in notifications[0][1]
    assert "foreign-session" in daemon._plain_sessions


async def test_kill_session_owned_session(daemon: Daemon) -> None:
    daemon._open_projects["github/owner/repo|tmux"] = OpenProject(
        project_id="github/owner/repo",
        pane_id=None,
        session="my-session",
        branch="main",
    )
    daemon._open_projects["github/owner/repo|%5"] = OpenProject(
        project_id="github/owner/repo",
        pane_id="%5",
        session="my-session",
        branch="main",
    )
    daemon._plain_sessions = ["other-session"]
    pushed_events: list[str] = []
    daemon._push_event = lambda event, _data, **_kw: pushed_events.append(event)  # type: ignore[assignment]

    with (
        patch.object(
            Daemon, "_is_pyworkon_session", new_callable=AsyncMock, return_value=True
        ),
        patch(
            "pyworkon.tmux_mgr.tmux_manager.kill_session", new_callable=AsyncMock
        ) as mock_kill,
    ):
        cmd = Command(cmd=CommandType.KILL_SESSION, session="my-session")
        responses = await _collect_responses(daemon, cmd)

    assert responses == [(ResponseType.OK, None)]
    mock_kill.assert_awaited_once_with("my-session")
    assert "github/owner/repo|tmux" not in daemon._open_projects
    assert "github/owner/repo|%5" not in daemon._open_projects
    daemon._git_watcher.unwatch.assert_called_once_with("github/owner/repo")
    assert "state" in pushed_events


async def test_kill_session_preserves_git_watcher_for_remaining_project(
    daemon: Daemon,
) -> None:
    daemon._open_projects["github/owner/repo|tmux"] = OpenProject(
        project_id="github/owner/repo",
        pane_id=None,
        session="session-a",
        branch="main",
    )
    daemon._open_projects["github/owner/repo|other-session"] = OpenProject(
        project_id="github/owner/repo",
        pane_id=None,
        session="session-b",
        branch="main",
    )

    with (
        patch.object(
            Daemon, "_is_pyworkon_session", new_callable=AsyncMock, return_value=True
        ),
        patch("pyworkon.tmux_mgr.tmux_manager.kill_session", new_callable=AsyncMock),
    ):
        cmd = Command(cmd=CommandType.KILL_SESSION, session="session-a")
        await _collect_responses(daemon, cmd)

    assert "github/owner/repo|tmux" not in daemon._open_projects
    assert "github/owner/repo|other-session" in daemon._open_projects
    daemon._git_watcher.unwatch.assert_not_called()


async def test_kill_session_removes_plain_session(daemon: Daemon) -> None:
    daemon._plain_sessions = ["scratch", "my-session", "notes"]

    with (
        patch.object(
            Daemon, "_is_pyworkon_session", new_callable=AsyncMock, return_value=True
        ),
        patch("pyworkon.tmux_mgr.tmux_manager.kill_session", new_callable=AsyncMock),
    ):
        cmd = Command(cmd=CommandType.KILL_SESSION, session="my-session")
        await _collect_responses(daemon, cmd)

    assert daemon._plain_sessions == ["scratch", "notes"]
