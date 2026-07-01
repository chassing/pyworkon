"""Clickable label that opens a URL in the browser."""

from __future__ import annotations

import webbrowser
from typing import Any

from textual.widgets import Label


class PRLink(Label):
    """Clickable PR/MR number or check name that opens the URL in the browser."""

    DEFAULT_CSS = """
    PRLink:hover {
        text-style: bold;
        pointer: pointer;
    }
    """

    def __init__(
        self, text: str = "", *, url: str | None = None, **kwargs: Any
    ) -> None:
        super().__init__(text, **kwargs)
        self.pr_url = url

    def on_click(self) -> None:
        """Open the URL in the default browser."""
        if self.pr_url:
            webbrowser.open(self.pr_url)
