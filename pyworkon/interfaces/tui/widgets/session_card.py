"""Session card widget: composes header, branch, PR detail, and agent list."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.widget import Widget

from pyworkon.interfaces.tui.widgets.agent_list import AgentList
from pyworkon.interfaces.tui.widgets.branch_row import BranchRow
from pyworkon.interfaces.tui.widgets.pr_detail import PRDetail
from pyworkon.interfaces.tui.widgets.review_request_list import ReviewRequestList
from pyworkon.interfaces.tui.widgets.session_header import SessionHeader

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from pyworkon.interfaces.tui.models import SessionInfo


class SessionCard(Widget):
    """Displays a complete session with header, branch, PR, and agents."""

    DEFAULT_CSS = """
    SessionCard {
        height: auto;
        padding: 0 1 0 1;
    }
    SessionCard.--highlight {
        background: $surface-lighten-1;
    }
    SessionCard.--current-session {
        border-left: tall $success;
        padding-left: 1;
    }
    """

    def __init__(
        self,
        session: SessionInfo,
        *,
        show_ci_checks: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.session = session
        self._show_ci_checks = show_ci_checks

    def compose(self) -> ComposeResult:
        if self.session.is_current:
            self.add_class("--current-session")
        yield SessionHeader(self.session)
        yield BranchRow(self.session)
        yield PRDetail(show_ci_checks=self._show_ci_checks)
        yield ReviewRequestList()
        yield AgentList()

    def on_mount(self) -> None:
        """Push initial PR, review request, and agent data after mount."""
        self.query_one(PRDetail).update(
            self.session.pr, self.session.project.owner_repo
        )
        self.query_one(ReviewRequestList).update(self.session.review_prs)
        self.query_one(AgentList).update(self.session.agents)

    def update_session(self, session: SessionInfo) -> None:
        """Update all child widgets with new session data."""
        self.session = session
        self.set_class(session.is_current, "--current-session")
        if not self.children:
            return
        self.query_one(SessionHeader).update(session)
        self.query_one(BranchRow).update(session)
        self.query_one(PRDetail).update(session.pr, session.project.owner_repo)
        self.query_one(ReviewRequestList).update(session.review_prs)
        self.query_one(AgentList).update(session.agents)
