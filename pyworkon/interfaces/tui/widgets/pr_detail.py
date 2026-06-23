"""PR/MR detail widget: title, link, state, review status, CI check failures."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label

from pyworkon.interfaces.tui import icons
from pyworkon.interfaces.tui.models import PRReviewStatus, PRState, PRStatus
from pyworkon.interfaces.tui.widgets.pr_link import PRLink

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from pyworkon.interfaces.tui.models import PRInfo

_PR_STATUS_ICONS: dict[PRStatus, str] = {
    PRStatus.SUCCESS: icons.PR_CI_SUCCESS,
    PRStatus.FAILURE: icons.PR_CI_FAILURE,
    PRStatus.PENDING: icons.PR_CI_PENDING,
    PRStatus.NONE: "",
}

_PR_STATE_ICONS: dict[PRState, str] = {
    PRState.OPEN: icons.PR_STATE_OPEN,
    PRState.CLOSED: icons.PR_STATE_CLOSED,
    PRState.MERGED: icons.PR_STATE_MERGED,
}

_PR_REVIEW_ICONS: dict[PRReviewStatus, str] = {
    PRReviewStatus.APPROVED: icons.PR_REVIEW_APPROVED,
    PRReviewStatus.CHANGES_REQUESTED: icons.PR_REVIEW_CHANGES_REQUESTED,
    PRReviewStatus.PENDING: icons.PR_REVIEW_PENDING,
    PRReviewStatus.NONE: "",
}


class PRDetail(Widget):
    """Multi-line PR/MR display with title, link, state, review, and CI checks."""

    DEFAULT_CSS = """
    PRDetail {
        height: auto;
    }
    PRDetail .detail-row {
        padding-left: 2;
        height: 1;
    }
    PRDetail .detail-icon {
        width: 3;
    }
    PRDetail .detail-icon.--pr {
        color: $accent;
    }
    PRDetail .detail-row.--ci-failure {
        background: $error 15%;
    }
    PRDetail .detail-row.--ci-failure-row {
        padding-left: 7;
    }
    PRDetail .detail-left {
        width: 1fr;
        color: $text-muted;
        overflow: hidden;
    }
    PRDetail .detail-left.--pr-link {
        color: $accent;
        text-style: underline;
    }
    PRDetail .detail-left.--ci-check-link {
        color: $error;
        text-style: underline;
    }
    PRDetail .detail-right {
        width: auto;
        color: $text;
    }
    """

    title_text: reactive[str] = reactive("")
    review_text: reactive[str] = reactive("")
    link_text: reactive[str] = reactive("")
    state_text: reactive[str] = reactive("")
    ci_failure: reactive[bool] = reactive(default=False)
    failed_checks: reactive[tuple[tuple[str, str], ...]] = reactive(())

    def __init__(self, *, show_ci_checks: bool = True, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._show_ci_checks = show_ci_checks
        self._pr_url: str | None = None

    def update(self, pr: PRInfo | None, owner_repo: str) -> None:
        """Update with new PR data."""
        if pr:
            prefix = "\\[Draft] " if pr.is_draft else ""
            self.title_text = f"{prefix}{pr.title}"
            self.review_text = (
                "" if pr.is_draft else _PR_REVIEW_ICONS.get(pr.review_status, "")
            )
            self.link_text = f"{owner_repo}#{pr.number}"
            self._pr_url = pr.url
            failed = [
                (c.name, c.url or "")
                for c in pr.ci_checks
                if c.status == PRStatus.FAILURE
            ]
            self.ci_failure = bool(failed)
            if failed:
                self.state_text = icons.PR_CI_FAILURE
            elif pr.status == PRStatus.PENDING:
                self.state_text = icons.PR_CI_PENDING
            elif pr.is_draft:
                self.state_text = icons.PR_STATE_DRAFT
            else:
                self.state_text = _PR_STATE_ICONS.get(pr.state, "")
            self.failed_checks = tuple(failed) if self._show_ci_checks else ()
            self.display = True
        else:
            self.title_text = ""
            self.review_text = ""
            self.link_text = ""
            self.state_text = ""
            self.ci_failure = False
            self.failed_checks = ()
            self._pr_url = None
            self.display = False

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Label(icons.ICON_PR, classes="detail-icon --pr"),
            Label(self.title_text, id="spr-title", classes="detail-left"),
            Label(
                self.review_text, id="spr-review", classes="detail-right", markup=True
            ),
            id="row-pr-title",
            classes="detail-row",
        )
        yield Horizontal(
            Label("", classes="detail-icon"),
            PRLink(
                self.link_text,
                url=self._pr_url,
                id="spr-link",
                classes="detail-left --pr-link",
            ),
            Label(self.state_text, id="spr-state", classes="detail-right", markup=True),
            id="row-pr-link",
            classes="detail-row",
        )
        if self._show_ci_checks:
            for name, url in self.failed_checks:
                yield Horizontal(
                    PRLink(
                        name, url=url or None, classes="detail-left --ci-check-link"
                    ),
                    classes="detail-row --ci-failure-row",
                )

    def watch_title_text(self, value: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#spr-title", Label).update(value)

    def watch_review_text(self, value: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#spr-review", Label).update(value)

    def watch_link_text(self, value: str) -> None:
        with contextlib.suppress(Exception):
            pr_link = self.query_one("#spr-link", PRLink)
            pr_link.update(value)
            pr_link.pr_url = self._pr_url

    def watch_state_text(self, value: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#spr-state", Label).update(value)

    def watch_ci_failure(self, value: bool) -> None:  # noqa: FBT001
        with contextlib.suppress(Exception):
            self.query_one("#row-pr-link").set_class(value, "--ci-failure")

    def watch_failed_checks(self, value: tuple[tuple[str, str], ...]) -> None:
        if not self.is_mounted or not self._show_ci_checks:
            return
        for widget in self.query(".--ci-failure-row"):
            widget.remove()
        for name, url in value:
            self.mount(
                Horizontal(
                    PRLink(
                        name, url=url or None, classes="detail-left --ci-check-link"
                    ),
                    classes="detail-row --ci-failure-row",
                )
            )
