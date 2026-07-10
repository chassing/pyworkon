"""PR/MR detail widget: title, link, state, review status, CI check failures."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from rich.spinner import Spinner
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label

from pyworkon.interfaces.tui import icons
from pyworkon.interfaces.tui.models import PRReviewStatus, PRState, PRStatus
from pyworkon.interfaces.tui.widgets.pr_link import PRLink

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.timer import Timer

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
        width: 2;
    }
    PRDetail .detail-icon.--pr {
        color: $accent;
    }
    PRDetail .detail-row.--ci-failure {
        background: $error 15%;
    }
    PRDetail .detail-row.--ci-check-row {
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
    PRDetail .detail-left.--ci-check-failure {
        color: $error;
        text-style: underline;
    }
    PRDetail .detail-left.--ci-check-pending {
        color: $warning;
    }
    PRDetail .detail-left.--ci-check-success {
        color: $success;
    }
    PRDetail .detail-right {
        width: auto;
        color: $text;
    }
    PRDetail.--draft {
        opacity: 0.6;
    }
    """

    title_text: reactive[str] = reactive("")
    review_text: reactive[str] = reactive("")
    link_text: reactive[str] = reactive("")
    state_text: reactive[str] = reactive("")
    ci_failure: reactive[bool] = reactive(default=False)
    ci_checks: reactive[tuple[tuple[str, str, str], ...]] = reactive(())

    def __init__(self, *, show_ci_checks: bool = True, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._show_ci_checks = show_ci_checks
        self._pr_url: str | None = None
        self._spinner = Spinner(icons.PR_CI_PENDING_SPINNER, style="yellow")
        self._spinner_timer: Timer | None = None
        self._is_pending_state: bool = False

    def update(self, pr: PRInfo | None, owner_repo: str) -> None:
        """Update with new PR data."""
        if pr:
            prefix = "\\[Draft] " if pr.is_draft else ""
            self.title_text = f"{prefix}{pr.title}"
            self.review_text = (
                "" if pr.is_draft else _PR_REVIEW_ICONS.get(pr.review_status, "")
            )
            self._pr_url = pr.url
            self.link_text = f"{owner_repo}#{pr.number}"
            has_failure = any(c.status == PRStatus.FAILURE for c in pr.ci_checks)
            self.ci_failure = has_failure
            self._is_pending_state = (
                not has_failure and not pr.is_draft and pr.status == PRStatus.PENDING
            )
            if has_failure:
                self.state_text = icons.PR_CI_FAILURE
            elif self._is_pending_state:
                self.state_text = icons.PR_CI_PENDING
            elif pr.is_draft:
                self.state_text = icons.PR_STATE_DRAFT
            else:
                self.state_text = _PR_STATE_ICONS.get(pr.state, "")
            self.ci_checks = (
                tuple((c.name, c.url or "", c.status.value) for c in pr.ci_checks)
                if self._show_ci_checks
                else ()
            )
            self.set_class(pr.is_draft, "--draft")
            self.display = True
        else:
            self._pr_url = None
            self._is_pending_state = False
            self.remove_class("--draft")
            self.title_text = ""
            self.review_text = ""
            self.link_text = ""
            self.state_text = ""
            self.ci_failure = False
            self.ci_checks = ()
            self.display = False
        self._manage_spinner()

    def compose(self) -> ComposeResult:
        state_classes = "detail-right"
        state_content: str | Spinner
        if self._is_pending_state:
            state_classes += " --ci-pending"
            state_content = self._spinner
        else:
            state_content = self.state_text

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
            Label(state_content, id="spr-state", classes=state_classes, markup=True),
            id="row-pr-link",
            classes="detail-row --ci-failure" if self.ci_failure else "detail-row",
        )
        if self._show_ci_checks:
            for name, url, status in self.ci_checks:
                if status == PRStatus.PENDING.value:
                    icon_content: str | Spinner = self._spinner
                    extra_class = " --ci-pending"
                else:
                    icon_content = _PR_STATUS_ICONS.get(PRStatus(status), "")
                    extra_class = ""
                yield Horizontal(
                    PRLink(
                        name,
                        url=url or None,
                        classes=f"detail-left --ci-check-{status}",
                    ),
                    Label(
                        icon_content,
                        classes=f"detail-right{extra_class}",
                        markup=True,
                    ),
                    classes="detail-row --ci-check-row",
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
            label = self.query_one("#spr-state", Label)
            if self._is_pending_state:
                label.update(self._spinner)
                label.add_class("--ci-pending")
            else:
                label.update(value)
                label.remove_class("--ci-pending")

    def watch_ci_failure(self, value: bool) -> None:  # noqa: FBT001
        with contextlib.suppress(Exception):
            self.query_one("#row-pr-link").set_class(value, "--ci-failure")

    async def watch_ci_checks(self, value: tuple[tuple[str, str, str], ...]) -> None:
        if not self.is_mounted or not self._show_ci_checks:
            return
        await self.recompose()

    def _manage_spinner(self) -> None:
        """Start or stop the spinner timer based on pending CI state."""
        has_pending = self._is_pending_state or any(
            status == PRStatus.PENDING.value for _, _, status in self.ci_checks
        )
        if has_pending and self._spinner_timer is None:
            self._spinner_timer = self.set_interval(1 / 12, self._tick_spinner)
        elif not has_pending and self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None

    def _tick_spinner(self) -> None:
        """Update all pending CI labels with the current spinner frame."""
        with contextlib.suppress(Exception):
            for label in self.query(Label).filter(".--ci-pending"):
                label.update(self._spinner)
