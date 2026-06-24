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
            "pyworkon.daemon.tmux_mgr.tmux_manager.kill_session", new_callable=AsyncMock
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
        patch(
            "pyworkon.daemon.tmux_mgr.tmux_manager.kill_session", new_callable=AsyncMock
        ),
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
        patch(
            "pyworkon.daemon.tmux_mgr.tmux_manager.kill_session", new_callable=AsyncMock
        ),
    ):
        cmd = Command(cmd=CommandType.KILL_SESSION, session="my-session")
        await _collect_responses(daemon, cmd)

    assert daemon._plain_sessions == ["scratch", "notes"]


async def test_switch_session_missing_session(daemon: Daemon) -> None:
    cmd = Command(cmd=CommandType.SWITCH_SESSION)
    responses = await _collect_responses(daemon, cmd)
    assert responses == [(ResponseType.ERROR, "session required")]


async def test_switch_session_attach(daemon: Daemon) -> None:
    with patch(
        "pyworkon.daemon.tmux_mgr.tmux_manager.attach_session", new_callable=AsyncMock
    ) as mock_attach:
        cmd = Command(cmd=CommandType.SWITCH_SESSION, session="my-session")
        responses = await _collect_responses(daemon, cmd)

    assert responses == [(ResponseType.OK, None)]
    mock_attach.assert_awaited_once_with("my-session")


async def test_switch_session_select_pane(daemon: Daemon) -> None:
    with patch(
        "pyworkon.daemon.tmux_mgr.tmux_manager.select_pane", new_callable=AsyncMock
    ) as mock_select:
        cmd = Command(
            cmd=CommandType.SWITCH_SESSION, session="my-session", pane_id="%5"
        )
        responses = await _collect_responses(daemon, cmd)

    assert responses == [(ResponseType.OK, None)]
    mock_select.assert_awaited_once_with("my-session", "%5")


async def test_enter_project_missing_id(daemon: Daemon) -> None:
    cmd = Command(cmd=CommandType.ENTER_PROJECT)
    responses = await _collect_responses(daemon, cmd)
    assert responses == [(ResponseType.ERROR, "project_id required")]


async def test_enter_project_not_found(daemon: Daemon) -> None:
    cmd = Command(cmd=CommandType.ENTER_PROJECT, project_id="github/unknown/repo")
    responses = await _collect_responses(daemon, cmd)
    assert responses == [(ResponseType.ERROR, "Project not found: github/unknown/repo")]


async def test_enter_project_success(daemon: Daemon) -> None:
    project = Project(id="github/owner/repo")
    daemon._project_mgr.get = MagicMock(return_value=project)

    with patch(
        "pyworkon.daemon.tmux_mgr.tmux_manager.enter", new_callable=AsyncMock
    ) as mock_enter:
        cmd = Command(cmd=CommandType.ENTER_PROJECT, project_id="github/owner/repo")
        responses = await _collect_responses(daemon, cmd)

    assert responses == [(ResponseType.OK, None)]
    mock_enter.assert_awaited_once_with(project)


def test_build_sidebar_state_includes_review_prs(daemon: Daemon) -> None:
    daemon._review_prs = {
        "github/app-sre/automated-actions": [
            {
                "number": 610,
                "title": "Fix bug",
                "url": "https://github.com/app-sre/automated-actions/pull/610",
                "author": "bot",
                "is_draft": False,
            }
        ]
    }
    state = daemon._build_sidebar_state()
    assert state["review_prs"] == daemon._review_prs


async def test_map_review_prs_to_forks(daemon: Daemon) -> None:
    upstream_prs = [
        {
            "number": 610,
            "title": "Fix bug",
            "url": "https://example.com/pr/610",
            "author": "bot",
            "is_draft": False,
        }
    ]
    daemon._review_prs = {"github/upstream-org/repo": upstream_prs}

    fork_project = Project(id="github/my-fork/repo")
    daemon._project_mgr.list = MagicMock(return_value=[fork_project])

    with patch.object(
        Project,
        "get_upstream_owner_repo",
        new_callable=AsyncMock,
        return_value="upstream-org/repo",
    ):
        await daemon._map_review_prs_to_forks()

    assert daemon._review_prs["github/my-fork/repo"] is upstream_prs
    assert daemon._review_prs["github/upstream-org/repo"] is upstream_prs


async def test_map_review_prs_to_forks_no_match(daemon: Daemon) -> None:
    daemon._review_prs = {"github/other-org/other-repo": [{"number": 1}]}

    fork_project = Project(id="github/my-fork/repo")
    daemon._project_mgr.list = MagicMock(return_value=[fork_project])

    with patch.object(
        Project,
        "get_upstream_owner_repo",
        new_callable=AsyncMock,
        return_value="upstream-org/repo",
    ):
        await daemon._map_review_prs_to_forks()

    assert "github/my-fork/repo" not in daemon._review_prs


async def test_map_review_prs_to_forks_skips_non_forks(daemon: Daemon) -> None:
    daemon._review_prs = {"github/org/repo": [{"number": 1}]}

    project = Project(id="github/org/repo")
    daemon._project_mgr.list = MagicMock(return_value=[project])

    with patch.object(
        Project,
        "get_upstream_owner_repo",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await daemon._map_review_prs_to_forks()

    assert len(daemon._review_prs) == 1


async def test_poll_tmux_cleans_stale_null_session_entries(daemon: Daemon) -> None:
    daemon._open_projects["github/owner/repo|%5"] = OpenProject(
        project_id="github/owner/repo",
        pane_id="%5",
        session=None,
    )

    with (
        patch(
            "pyworkon.daemon.tmux_mgr.tmux_manager.list_sessions_with_project_id",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "pyworkon.daemon.tmux_mgr.tmux_manager.list_sessions",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        await daemon._poll_tmux()

    assert "github/owner/repo|%5" not in daemon._open_projects
    daemon._git_watcher.unwatch.assert_called_once_with("github/owner/repo")


async def test_poll_tmux_preserves_null_session_with_active_project(
    daemon: Daemon,
) -> None:
    daemon._open_projects["github/owner/repo|%5"] = OpenProject(
        project_id="github/owner/repo",
        pane_id="%5",
        session=None,
    )

    project = Project(id="github/owner/repo")
    daemon._project_mgr.get = MagicMock(return_value=project)

    with (
        patch(
            "pyworkon.daemon.tmux_mgr.tmux_manager.list_sessions_with_project_id",
            new_callable=AsyncMock,
            return_value=[("my-session", "github/owner/repo")],
        ),
        patch(
            "pyworkon.daemon.tmux_mgr.tmux_manager.list_sessions",
            new_callable=AsyncMock,
            return_value=["my-session"],
        ),
        patch.object(
            Project,
            "get_current_branch",
            new_callable=AsyncMock,
            return_value="main",
        ),
        patch.object(
            Project,
            "has_uncommitted_changes",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        await daemon._poll_tmux()

    assert "github/owner/repo|%5" in daemon._open_projects
    op = daemon._open_projects["github/owner/repo|%5"]
    assert op.session == "my-session"
