"""Tests for parse_sidebar_state — converts daemon dicts to typed models."""

from __future__ import annotations

from typing import Any

import pytest

from pyworkon.interfaces.tui.data import parse_sidebar_state
from pyworkon.interfaces.tui.models import PRState, PRStatus


@pytest.fixture
def minimal_project_data() -> dict[str, Any]:
    return {"id": "github/owner/repo"}


@pytest.fixture
def session_data(minimal_project_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_name": "my-session",
        "project": minimal_project_data,
        "branch": "main",
        "is_dirty": False,
        "pane_id": "%1",
    }


def test_empty_state() -> None:
    sessions, projects, plain, _ = parse_sidebar_state({})
    assert sessions == []
    assert projects == []
    assert plain == []


def test_empty_lists() -> None:
    sessions, projects, plain, _ = parse_sidebar_state({
        "sessions": [],
        "projects": [],
        "plain_sessions": [],
    })
    assert sessions == []
    assert projects == []
    assert plain == []


def test_single_session(session_data: dict[str, Any]) -> None:
    state = {"sessions": [session_data]}
    sessions, _projects, _plain, _ = parse_sidebar_state(state)
    assert len(sessions) == 1
    s = sessions[0]
    assert s.session_name == "my-session"
    assert s.project.id == "github/owner/repo"
    assert s.branch == "main"
    assert s.is_dirty is False
    assert s.pane_id == "%1"
    assert s.pr is None
    assert s.agents == []


def test_session_with_pr(session_data: dict[str, Any]) -> None:
    session_data["pr"] = {
        "number": 42,
        "title": "Fix bug",
        "status": "success",
        "state": "open",
        "url": "https://github.com/owner/repo/pull/42",
        "review_status": "approved",
        "is_draft": False,
        "ci_checks": [
            {"name": "build", "status": "success"},
            {"name": "test", "status": "failure", "url": "https://ci.example.com/2"},
        ],
    }
    state = {"sessions": [session_data]}
    sessions, _, _, _ = parse_sidebar_state(state)
    assert len(sessions) == 1
    pr = sessions[0].pr
    assert pr is not None
    assert pr.number == 42
    assert pr.title == "Fix bug"
    assert pr.status == PRStatus.SUCCESS
    assert pr.state == PRState.OPEN
    assert len(pr.ci_checks) == 2
    assert pr.ci_checks[1].url == "https://ci.example.com/2"


def test_session_with_agents(session_data: dict[str, Any]) -> None:
    session_data["agents"] = [
        {"name": "bot-a", "status": "idle"},
        {"name": "bot-b", "status": "working"},
    ]
    state = {"sessions": [session_data]}
    sessions, _, _, _ = parse_sidebar_state(state)
    assert len(sessions) == 1
    assert len(sessions[0].agents) == 2
    assert sessions[0].agents[0].name == "bot-a"
    assert sessions[0].agents[0].status == "idle"
    assert sessions[0].agents[1].name == "bot-b"


def test_session_dirty_and_no_branch(minimal_project_data: dict[str, Any]) -> None:
    state = {
        "sessions": [
            {
                "session_name": "dev",
                "project": minimal_project_data,
                "is_dirty": True,
            }
        ]
    }
    sessions, _, _, _ = parse_sidebar_state(state)
    assert len(sessions) == 1
    assert sessions[0].is_dirty is True
    assert sessions[0].branch is None


def test_projects_list(minimal_project_data: dict[str, Any]) -> None:
    state = {
        "projects": [
            minimal_project_data,
            {"id": "gitlab/team/service"},
        ]
    }
    _, projects, _, _ = parse_sidebar_state(state)
    assert len(projects) == 2
    assert projects[0].id == "github/owner/repo"
    assert projects[1].id == "gitlab/team/service"


def test_plain_sessions() -> None:
    state = {"plain_sessions": ["scratch", "notes"]}
    _, _, plain, _ = parse_sidebar_state(state)
    assert plain == ["scratch", "notes"]


def test_malformed_project_skipped() -> None:
    state = {
        "sessions": [
            {"session_name": "bad", "project": {}},
            {"session_name": "ok", "project": {"id": "github/a/b"}},
        ]
    }
    sessions, _, _, _ = parse_sidebar_state(state)
    assert len(sessions) == 1
    assert sessions[0].session_name == "ok"


def test_malformed_project_in_projects_list_skipped() -> None:
    state = {
        "projects": [
            {},
            {"id": "github/good/one"},
        ]
    }
    _, projects, _, _ = parse_sidebar_state(state)
    assert len(projects) == 1
    assert projects[0].id == "github/good/one"


def test_multiple_sessions(minimal_project_data: dict[str, Any]) -> None:
    state = {
        "sessions": [
            {"session_name": "s1", "project": minimal_project_data, "branch": "main"},
            {"session_name": "s2", "project": {"id": "gitlab/x/y"}, "branch": "dev"},
        ]
    }
    sessions, _, _, _ = parse_sidebar_state(state)
    assert len(sessions) == 2
    assert sessions[0].session_name == "s1"
    assert sessions[1].session_name == "s2"
    assert sessions[1].project.id == "gitlab/x/y"
