"""Tier 3 — App composition tests (no daemon connection)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from unittest.mock import patch

from textual.containers import VerticalScroll
from textual.widgets import Footer

from pyworkon.daemon.client import DaemonNotRunningError
from pyworkon.daemon.project_mgr import Project
from pyworkon.daemon.protocol import (
    EventResponse,
    ResponseUnion,
    SessionState,
    SidebarStatePayload,
)
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


def _make_state(session_name: str) -> SidebarStatePayload:
    return SidebarStatePayload(
        sessions=[
            SessionState(session_name=session_name, project=Project(id="github/o/r"))
        ],
        plain_sessions=[],
        projects=[],
        review_prs={},
    )


class _OneShotDaemonClient:
    """Fake client: connects fine, yields one state event, then disconnects (EOF)."""

    def __init__(self, session_name: str = "session-a") -> None:
        self._session_name = session_name

    def connect(self) -> None:
        pass

    def close(self) -> None:
        pass

    def subscribe(
        self, events: list[str], *, full: bool = True
    ) -> Iterator[EventResponse]:
        yield EventResponse(event="state", data=_make_state(self._session_name))


async def test_run_daemon_session_updates_state_once() -> None:
    """_run_daemon_session applies one pushed state update, then returns on EOF."""
    app = DashboardApp()
    with (
        patch.object(app, "_listen_daemon"),
        patch(
            "pyworkon.interfaces.tui.base.DaemonClient",
            lambda: _OneShotDaemonClient("session-a"),
        ),
    ):
        async with app.run_test():
            # _run_daemon_session uses call_from_thread, which requires running
            # off the app's own thread (same as the real worker does).
            await asyncio.to_thread(app._run_daemon_session)
            assert [s.session_name for s in app._all_items] == ["session-a"]
            assert app._notification_client is None


class _RestartingDaemonClient:
    """Fake client: each successive connect() yields a different session, then EOF.

    Simulates the daemon restarting between subscription cycles — the real
    `DaemonClient.subscribe()` returns cleanly (EOF) when the peer closes the socket.
    After two cycles, further connects fail (daemon "not running yet"), so the
    background worker settles into a harmless retry loop instead of racing the
    test's teardown with more UI updates.
    """

    _connect_count = 0

    def connect(self) -> None:
        type(self)._connect_count += 1
        if type(self)._connect_count > 2:
            raise DaemonNotRunningError

    def close(self) -> None:
        pass

    def subscribe(
        self, events: list[str], *, full: bool = True
    ) -> Iterator[ResponseUnion]:
        yield EventResponse(
            event="state", data=_make_state(f"session-{self._connect_count}")
        )


async def test_listen_daemon_reconnects_after_daemon_restart() -> None:
    """The background worker must reconnect after the daemon drops the connection."""
    _RestartingDaemonClient._connect_count = 0
    app = DashboardApp()
    app._RECONNECT_DELAY_SECS = 0.01
    with patch("pyworkon.interfaces.tui.base.DaemonClient", _RestartingDaemonClient):
        async with app.run_test():
            for _ in range(200):
                if [s.session_name for s in app._all_items] == ["session-2"]:
                    break
                await asyncio.sleep(0.01)
            assert [s.session_name for s in app._all_items] == ["session-2"]
