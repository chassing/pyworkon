"""Tests for TUI models — PRInfo, SessionInfo, CICheck, enums."""

from __future__ import annotations

import pytest

from pyworkon.daemon.models import AgentInfo, CICheck, PRReviewStatus, PRState, PRStatus
from pyworkon.interfaces.tui.models import PlainSession
from tests.conftest import make_pr_info, make_session_info


@pytest.mark.parametrize(
    ("member", "value"),
    [
        (PRStatus.SUCCESS, "success"),
        (PRStatus.FAILURE, "failure"),
        (PRStatus.PENDING, "pending"),
        (PRStatus.NONE, "none"),
    ],
)
def test_pr_status_values(member: PRStatus, value: str) -> None:
    assert member == value


@pytest.mark.parametrize(
    ("member", "value"),
    [
        (PRState.OPEN, "open"),
        (PRState.CLOSED, "closed"),
        (PRState.MERGED, "merged"),
    ],
)
def test_pr_state_values(member: PRState, value: str) -> None:
    assert member == value


@pytest.mark.parametrize(
    ("member", "value"),
    [
        (PRReviewStatus.APPROVED, "approved"),
        (PRReviewStatus.CHANGES_REQUESTED, "changes_requested"),
        (PRReviewStatus.PENDING, "pending"),
        (PRReviewStatus.NONE, "none"),
    ],
)
def test_pr_review_status_values(member: PRReviewStatus, value: str) -> None:
    assert member == value


def test_ci_check_creation() -> None:
    check = CICheck(
        name="ci/build", status=PRStatus.SUCCESS, url="https://ci.example.com/1"
    )
    assert check.name == "ci/build"
    assert check.status == PRStatus.SUCCESS
    assert check.url == "https://ci.example.com/1"


def test_ci_check_url_defaults_to_none() -> None:
    check = CICheck(name="lint", status=PRStatus.PENDING)
    assert check.url is None


def test_pr_info_defaults() -> None:
    pr = make_pr_info()
    assert pr.number == 42
    assert pr.title == "Fix auth middleware"
    assert pr.status == PRStatus.SUCCESS
    assert pr.state == PRState.OPEN
    assert pr.review_status == PRReviewStatus.NONE
    assert pr.is_draft is False
    assert pr.ci_checks == []


def test_pr_info_all_fields() -> None:
    checks = [
        CICheck(name="build", status=PRStatus.SUCCESS),
        CICheck(name="test", status=PRStatus.FAILURE, url="https://ci.example.com/2"),
    ]
    pr = make_pr_info(
        number=99,
        title="Add feature X",
        status=PRStatus.FAILURE,
        state=PRState.MERGED,
        url="https://github.com/o/r/pull/99",
        review_status=PRReviewStatus.APPROVED,
        is_draft=True,
        ci_checks=checks,
    )
    assert pr.number == 99
    assert pr.title == "Add feature X"
    assert pr.status == PRStatus.FAILURE
    assert pr.state == PRState.MERGED
    assert pr.review_status == PRReviewStatus.APPROVED
    assert pr.is_draft is True
    assert len(pr.ci_checks) == 2
    assert pr.ci_checks[0].name == "build"
    assert pr.ci_checks[1].url == "https://ci.example.com/2"


def test_pr_info_is_draft_field() -> None:
    pr_draft = make_pr_info(is_draft=True)
    pr_normal = make_pr_info(is_draft=False)
    assert pr_draft.is_draft is True
    assert pr_normal.is_draft is False


def test_pr_info_with_ci_checks() -> None:
    checks = [
        CICheck(name="lint", status=PRStatus.SUCCESS),
        CICheck(name="test", status=PRStatus.PENDING),
    ]
    pr = make_pr_info(ci_checks=checks)
    assert len(pr.ci_checks) == 2
    assert pr.ci_checks[0].status == PRStatus.SUCCESS
    assert pr.ci_checks[1].status == PRStatus.PENDING


def test_agent_info() -> None:
    agent = AgentInfo(name="copilot", status="working")
    assert agent.name == "copilot"
    assert agent.status == "working"


def test_session_info_with_defaults() -> None:
    session = make_session_info()
    assert session.session_name == "test-session"
    assert session.project.id == "github/owner/repo"
    assert session.branch == "main"
    assert session.is_dirty is False
    assert session.pr is None
    assert session.agents == []
    assert session.is_current is False


def test_session_info_with_pr_and_agents() -> None:
    pr = make_pr_info(number=10, title="WIP")
    agents = [
        AgentInfo(name="bot-a", status="idle"),
        AgentInfo(name="bot-b", status="working"),
    ]
    session = make_session_info(
        session_name="dev",
        branch="feature/x",
        is_dirty=True,
        pr=pr,
        agents=agents,
        is_current=True,
    )
    assert session.session_name == "dev"
    assert session.branch == "feature/x"
    assert session.is_dirty is True
    assert session.pr is not None
    assert session.pr.number == 10
    assert len(session.agents) == 2
    assert session.is_current is True


def test_plain_session_dataclass() -> None:
    ps = PlainSession(name="scratch")
    assert ps.name == "scratch"
