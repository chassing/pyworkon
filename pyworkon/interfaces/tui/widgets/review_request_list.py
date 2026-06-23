"""Review request list widget: shows PRs where the user is a requested reviewer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label

from pyworkon.interfaces.tui import icons
from pyworkon.interfaces.tui.widgets.pr_link import PRLink

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from pyworkon.interfaces.tui.models import ReviewPR


class ReviewRequestList(Widget):
    """Displays PRs requesting review from the authenticated user."""

    DEFAULT_CSS = """
    ReviewRequestList {
        height: auto;
    }
    ReviewRequestList .detail-row {
        padding-left: 2;
        height: 1;
    }
    ReviewRequestList .review-header {
        padding-left: 2;
        height: 1;
    }
    ReviewRequestList .review-header-icon {
        width: 3;
        color: $warning;
    }
    ReviewRequestList .review-header-text {
        width: 1fr;
        color: $text-muted;
    }
    ReviewRequestList .detail-icon {
        width: 3;
        color: $warning;
    }
    ReviewRequestList .detail-left {
        width: 1fr;
        color: $text-muted;
        overflow: hidden;
    }
    ReviewRequestList .detail-left.--review-link {
        color: $accent;
        text-style: underline;
    }
    ReviewRequestList .detail-right {
        width: auto;
        color: $text-muted;
    }
    """

    review_data: reactive[tuple[tuple[str, str, str | None, str], ...]] = reactive(())

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    def update(self, review_prs: list[ReviewPR]) -> None:
        """Update with new review PR data."""
        self.review_data = tuple(
            (pr.title, f"#{pr.number}", pr.url, pr.author) for pr in review_prs
        )
        self.display = bool(self.review_data)

    def compose(self) -> ComposeResult:
        if self.review_data:
            yield Horizontal(
                Label(icons.ICON_REVIEW_REQUEST, classes="review-header-icon"),
                Label(
                    f"Reviews requested ({len(self.review_data)})",
                    classes="review-header-text",
                ),
                classes="review-header",
            )
            for title, number, url, author in self.review_data:
                yield Horizontal(
                    Label("", classes="detail-icon"),
                    PRLink(
                        f"{title} ({number})",
                        url=url,
                        classes="detail-left --review-link",
                    ),
                    Label(author, classes="detail-right"),
                    classes="detail-row --review-row",
                )

    async def watch_review_data(
        self, value: tuple[tuple[str, str, str | None, str], ...]
    ) -> None:
        if not self.is_mounted:
            return
        await self.recompose()
