"""Tier 3 — App composition tests (no daemon connection)."""

from __future__ import annotations

from unittest.mock import patch

from textual.containers import VerticalScroll
from textual.widgets import Footer

from pyworkon.interfaces.tui.dashboard import DashboardApp
from pyworkon.interfaces.tui.popup import PopupApp


async def test_dashboard_app_composes() -> None:
    app = DashboardApp()
    with patch.object(app, "_listen_daemon"):
        async with app.run_test():
            assert len(app.query(VerticalScroll)) == 1
            assert len(app.query(Footer)) == 1


async def test_popup_app_composes() -> None:
    app = PopupApp()
    with patch.object(app, "_listen_daemon"):
        async with app.run_test():
            assert len(app.query(VerticalScroll)) == 1
            assert len(app.query(Footer)) == 1
