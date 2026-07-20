"""Tests for parse_sidebar_state — converts a typed daemon payload to sidebar models."""

from __future__ import annotations

from pyworkon.daemon.models import (
    AgentInfo,
    CICheck,
    PRInfo,
    PRState,
    PRStatus,
    ReviewPR,
)
from pyworkon.daemon.project_mgr import Project
from pyworkon.daemon.protocol import SessionState, SidebarStatePayload
from pyworkon.interfaces.tui.data import parse_sidebar_state


def _payload(**kwargs: object) -> SidebarStatePayload:
    defaults: dict[str, object] = {
        "sessions": [],
        "plain_sessions": [],
        "projects": [],
        "review_prs": {},
    }
    return SidebarStatePayload(**{**defaults, **kwargs})


def test_empty_state() -> None:
    sessions, projects, plain, review_prs = parse_sidebar_state(_payload())
    assert sessions == []
    assert projects == []
    assert plain == []
    assert review_prs == {}


def test_single_session() -> None:
    state = _payload(
        sessions=[
            SessionState(
                session_name="my-session",
                project=Project(id="github/owner/repo"),
                branch="main",
                is_dirty=False,
                pane_id="%1",
            )
        ]
    )
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


def test_session_with_pr() -> None:
    pr = PRInfo(
        number=42,
        title="Fix bug",
        status=PRStatus.SUCCESS,
        state=PRState.OPEN,
        url="https://github.com/owner/repo/pull/42",
        ci_checks=[
            CICheck(name="build", status=PRStatus.SUCCESS),
            CICheck(
                name="test", status=PRStatus.FAILURE, url="https://ci.example.com/2"
            ),
        ],
    )
    state = _payload(
        sessions=[
            SessionState(
                session_name="my-session",
                project=Project(id="github/owner/repo"),
                pr=pr,
            )
        ]
    )
    sessions, _, _, _ = parse_sidebar_state(state)
    assert len(sessions) == 1
    result_pr = sessions[0].pr
    assert result_pr is not None
    assert result_pr.number == 42
    assert result_pr.title == "Fix bug"
    assert result_pr.status == PRStatus.SUCCESS
    assert result_pr.state == PRState.OPEN
    assert len(result_pr.ci_checks) == 2
    assert result_pr.ci_checks[1].url == "https://ci.example.com/2"


def test_session_with_agents() -> None:
    agents = [
        AgentInfo(pid=1, name="bot-a", status="idle"),
        AgentInfo(pid=2, name="bot-b", status="working"),
    ]
    state = _payload(
        sessions=[
            SessionState(
                session_name="my-session",
                project=Project(id="github/owner/repo"),
                agents=agents,
            )
        ]
    )
    sessions, _, _, _ = parse_sidebar_state(state)
    assert len(sessions) == 1
    assert len(sessions[0].agents) == 2
    assert sessions[0].agents[0].name == "bot-a"
    assert sessions[0].agents[0].status == "idle"
    assert sessions[0].agents[1].name == "bot-b"


def test_session_dirty_and_no_branch() -> None:
    state = _payload(
        sessions=[
            SessionState(
                session_name="dev",
                project=Project(id="github/owner/repo"),
                is_dirty=True,
            )
        ]
    )
    sessions, _, _, _ = parse_sidebar_state(state)
    assert len(sessions) == 1
    assert sessions[0].is_dirty is True
    assert sessions[0].branch is None


def test_projects_list() -> None:
    state = _payload(
        projects=[
            Project(id="github/owner/repo"),
            Project(id="gitlab/team/service"),
        ]
    )
    _, projects, _, _ = parse_sidebar_state(state)
    assert len(projects) == 2
    assert projects[0].id == "github/owner/repo"
    assert projects[1].id == "gitlab/team/service"


def test_plain_sessions() -> None:
    state = _payload(plain_sessions=["scratch", "notes"])
    _, _, plain, _ = parse_sidebar_state(state)
    assert plain == ["scratch", "notes"]


def test_review_prs_pass_through() -> None:
    prs = [ReviewPR(number=1, title="Add X", url="https://x", author="alice")]
    state = _payload(review_prs={"github/owner/repo": prs})
    _, _, _, review_prs = parse_sidebar_state(state)
    assert review_prs == {"github/owner/repo": prs}


def test_multiple_sessions() -> None:
    state = _payload(
        sessions=[
            SessionState(
                session_name="s1",
                project=Project(id="github/owner/repo"),
                branch="main",
            ),
            SessionState(
                session_name="s2", project=Project(id="gitlab/x/y"), branch="dev"
            ),
        ]
    )
    sessions, _, _, _ = parse_sidebar_state(state)
    assert len(sessions) == 2
    assert sessions[0].session_name == "s1"
    assert sessions[1].session_name == "s2"
    assert sessions[1].project.id == "gitlab/x/y"
