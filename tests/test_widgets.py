"""Tier 3 — Textual widget tests using run_test()."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from pyworkon.daemon.models import AgentInfo, CICheck, PRStatus
from pyworkon.interfaces.tui import icons
from pyworkon.interfaces.tui.widgets.agent_list import AgentList
from pyworkon.interfaces.tui.widgets.branch_row import BranchRow
from pyworkon.interfaces.tui.widgets.pr_detail import PRDetail
from pyworkon.interfaces.tui.widgets.session_card import SessionCard
from pyworkon.interfaces.tui.widgets.session_header import SessionHeader
from tests.conftest import make_pr_info, make_session_info


class WidgetTestApp(App[None]):
    """Minimal app that mounts a single widget for testing."""

    def __init__(self, widget: object) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SessionHeader
# ---------------------------------------------------------------------------


async def test_session_header_renders_name() -> None:
    session = make_session_info(session_name="my-app", project_id="github/acme/my-app")
    widget = SessionHeader(session)
    app = WidgetTestApp(widget)
    async with app.run_test():
        assert "my-app" in widget.name_text


# ---------------------------------------------------------------------------
# BranchRow
# ---------------------------------------------------------------------------


async def test_branch_row_renders_branch_name() -> None:
    session = make_session_info(branch="feature/login")
    widget = BranchRow(session)
    app = WidgetTestApp(widget)
    async with app.run_test():
        assert widget.branch_text == "feature/login"


async def test_branch_row_hidden_when_no_branch() -> None:
    session = make_session_info(branch=None)
    widget = BranchRow(session)
    app = WidgetTestApp(widget)
    async with app.run_test():
        assert widget.display is False


async def test_branch_row_visible_when_branch_set() -> None:
    session = make_session_info(branch="main")
    widget = BranchRow(session)
    app = WidgetTestApp(widget)
    async with app.run_test():
        assert widget.display is True


async def test_branch_row_dirty_indicator() -> None:
    session = make_session_info(branch="main", is_dirty=True)
    widget = BranchRow(session)
    app = WidgetTestApp(widget)
    async with app.run_test():
        assert widget.dirty_text == icons.BRANCH_DIRTY


async def test_branch_row_clean_no_dirty_indicator() -> None:
    session = make_session_info(branch="main", is_dirty=False)
    widget = BranchRow(session)
    app = WidgetTestApp(widget)
    async with app.run_test():
        assert widget.dirty_text == ""


# ---------------------------------------------------------------------------
# PRDetail
# ---------------------------------------------------------------------------


async def test_pr_detail_renders_title() -> None:
    pr = make_pr_info(title="Add OAuth support", number=99)
    widget = PRDetail(show_ci_checks=True)
    app = WidgetTestApp(widget)
    async with app.run_test():
        widget.update(pr, "acme/repo")
        await app._animator.wait_for_idle()
        assert widget.title_text == "Add OAuth support"


async def test_pr_detail_renders_link() -> None:
    pr = make_pr_info(number=99)
    widget = PRDetail(show_ci_checks=True)
    app = WidgetTestApp(widget)
    async with app.run_test():
        widget.update(pr, "acme/repo")
        await app._animator.wait_for_idle()
        assert widget.link_text == "acme/repo#99"


async def test_pr_detail_hidden_when_no_pr() -> None:
    widget = PRDetail(show_ci_checks=True)
    app = WidgetTestApp(widget)
    async with app.run_test():
        widget.update(None, "acme/repo")
        await app._animator.wait_for_idle()
        assert widget.display is False


async def test_pr_detail_visible_when_pr_set() -> None:
    pr = make_pr_info()
    widget = PRDetail(show_ci_checks=True)
    app = WidgetTestApp(widget)
    async with app.run_test():
        widget.update(pr, "acme/repo")
        await app._animator.wait_for_idle()
        assert widget.display is True


async def test_pr_detail_draft_prefix() -> None:
    pr = make_pr_info(title="WIP feature", is_draft=True)
    widget = PRDetail(show_ci_checks=True)
    app = WidgetTestApp(widget)
    async with app.run_test():
        widget.update(pr, "acme/repo")
        await app._animator.wait_for_idle()
        assert "[Draft]" in widget.title_text
        assert "WIP feature" in widget.title_text


async def test_pr_detail_ci_checks_shown() -> None:
    checks = [
        CICheck(name="lint", status=PRStatus.FAILURE, url="https://ci/lint"),
        CICheck(name="test", status=PRStatus.SUCCESS, url="https://ci/test"),
    ]
    pr = make_pr_info(ci_checks=checks, status=PRStatus.FAILURE)
    widget = PRDetail(show_ci_checks=True)
    app = WidgetTestApp(widget)
    async with app.run_test() as pilot:
        widget.update(pr, "acme/repo")
        await pilot.pause()
        check_rows = app.query(".--ci-check-row")
        assert len(check_rows) == 2


async def test_pr_detail_ci_checks_hidden_when_disabled() -> None:
    checks = [
        CICheck(name="lint", status=PRStatus.FAILURE, url="https://ci/lint"),
    ]
    pr = make_pr_info(ci_checks=checks, status=PRStatus.FAILURE)
    widget = PRDetail(show_ci_checks=False)
    app = WidgetTestApp(widget)
    async with app.run_test():
        widget.update(pr, "acme/repo")
        await app._animator.wait_for_idle()
        check_rows = app.query(".--ci-check-row")
        assert len(check_rows) == 0


# ---------------------------------------------------------------------------
# AgentList
# ---------------------------------------------------------------------------


async def test_agent_list_renders_rows() -> None:
    agents = [
        AgentInfo(name="claude-1", status="working"),
        AgentInfo(name="claude-2", status="idle"),
    ]
    widget = AgentList()
    app = WidgetTestApp(widget)
    async with app.run_test() as pilot:
        widget.update(agents)
        await pilot.pause()
        rows = app.query(".--agent-row")
        assert len(rows) == 2


async def test_agent_list_hidden_when_empty() -> None:
    widget = AgentList()
    app = WidgetTestApp(widget)
    async with app.run_test():
        widget.update([])
        await app._animator.wait_for_idle()
        assert widget.display is False


async def test_agent_list_visible_when_agents_present() -> None:
    agents = [AgentInfo(name="agent-a", status="working")]
    widget = AgentList()
    app = WidgetTestApp(widget)
    async with app.run_test():
        widget.update(agents)
        await app._animator.wait_for_idle()
        assert widget.display is True


# ---------------------------------------------------------------------------
# SessionCard
# ---------------------------------------------------------------------------


async def test_session_card_composes_sub_widgets() -> None:
    pr = make_pr_info()
    agents = [AgentInfo(name="agent-1", status="idle")]
    session = make_session_info(branch="develop", pr=pr, agents=agents)
    app = WidgetTestApp(SessionCard(session, show_ci_checks=True))
    async with app.run_test():
        assert len(app.query(SessionHeader)) == 1
        assert len(app.query(BranchRow)) == 1
        assert len(app.query(PRDetail)) == 1
        assert len(app.query(AgentList)) == 1


async def test_session_card_current_session_class() -> None:
    session = make_session_info(is_current=True)
    widget = SessionCard(session)
    app = WidgetTestApp(widget)
    async with app.run_test():
        assert widget.has_class("--current-session")


async def test_session_card_not_current_no_class() -> None:
    session = make_session_info(is_current=False)
    widget = SessionCard(session)
    app = WidgetTestApp(widget)
    async with app.run_test():
        assert not widget.has_class("--current-session")


@pytest.mark.parametrize("show_ci", [True, False])
async def test_session_card_passes_show_ci_checks(show_ci: bool) -> None:
    session = make_session_info()
    widget = SessionCard(session, show_ci_checks=show_ci)
    app = WidgetTestApp(widget)
    async with app.run_test():
        pr_detail = app.query_one(PRDetail)
        assert pr_detail._show_ci_checks is show_ci
