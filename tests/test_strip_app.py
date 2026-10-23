"""Tests for the strip's HTML rendering (icon + font injection) and window setup."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import ClassVar
from unittest.mock import MagicMock

import pytest

from pyworkon.icons import DASHBOARD_ICONS
from pyworkon.interfaces.strip import app as app_module
from pyworkon.interfaces.strip.app import _build_windows, _render_strip_html
from pyworkon.interfaces.strip.dock_geometry import StripLayout
from pyworkon.interfaces.strip.native import POPUP_MAX_WIDTH, POPUP_MIN_WIDTH


@dataclass
class _FakeScreen:
    x: int = 0
    y: int = 0
    width: int = 1920
    height: int = 1080


def _make_layout(
    screen: _FakeScreen, *, mode: str = "full_width", height: int = 56
) -> StripLayout:
    return StripLayout(
        mode=mode,  # type: ignore[arg-type]
        screen=screen,  # type: ignore[arg-type]
        x=screen.x,
        y=screen.y,
        width=screen.width,
        height=height,
    )


def test_build_windows_never_allows_either_window_to_become_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`focus=False` is what makes pywebview's own `canBecomeKeyWindow` always return `False`.

    Regression test: `focus=True` previously let every real click on a chip
    key the window, which silently steals keyboard focus from whatever app
    (e.g. a terminal) the user is actually working in, regardless of the
    strip's own app never activating. Applies to the strip and popup windows
    -- the popup window delivers real clicks too (e.g. for PR links). The
    project picker is the one deliberate exception (see `bridge.py`'s
    `open_project_picker()`): it hosts a real search box, so it needs
    `focus=True`.
    """
    screen = _FakeScreen()
    calls: list[dict[str, object]] = []

    def fake_create_window(*_args: object, **kwargs: object) -> MagicMock:
        calls.append(kwargs)
        return MagicMock()

    monkeypatch.setattr(app_module.webview, "create_window", fake_create_window)

    _build_windows(MagicMock(), layout=_make_layout(screen), auto_hide=False)

    assert len(calls) == 3
    strip_call, popup_call, picker_call = calls
    assert strip_call["focus"] is False
    assert popup_call["focus"] is False
    assert picker_call["focus"] is True


def test_build_windows_binds_the_bridge_to_all_three_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    screen = _FakeScreen()
    windows = [MagicMock(), MagicMock(), MagicMock()]

    monkeypatch.setattr(
        app_module.webview, "create_window", lambda *_a, **_kw: windows.pop(0)
    )
    bridge = MagicMock()
    layout = _make_layout(screen)

    window, popup_window, picker_window = _build_windows(
        bridge, layout=layout, auto_hide=False
    )

    bridge.bind.assert_called_once_with(
        window, popup_window, picker_window, layout=layout, collapsed=False
    )


def test_build_windows_positions_the_strip_flush_with_the_screen_bottom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for the `create_window(x=, y=)` coordinate conversion.

    `create_window`'s `(x, y)` is screen-relative and top-down (confirmed by
    reading `webview/platforms/cocoa.py`'s `move()`), unlike `native.py`'s
    `resize_frame()`, which takes true absolute AppKit coordinates directly.
    A non-zero `layout.x` (beside-dock mode) or non-primary screen must not
    be double-counted.
    """
    screen = _FakeScreen(x=3840, y=518, width=3000, height=1169)
    calls: list[dict[str, object]] = []

    def fake_create_window(*_args: object, **kwargs: object) -> MagicMock:
        calls.append(kwargs)
        return MagicMock()

    monkeypatch.setattr(app_module.webview, "create_window", fake_create_window)
    layout = StripLayout(
        mode="beside_dock",  # type: ignore[arg-type]
        screen=screen,  # type: ignore[arg-type]
        x=4840.0,
        y=518.0,
        width=992.0,
        height=84,
    )

    _build_windows(MagicMock(), layout=layout, auto_hide=False)

    strip_call = calls[0]
    assert strip_call["x"] == 4840 - 3840  # layout.x - screen.x
    assert strip_call["y"] == 1169 - 84  # screen.height - height
    assert strip_call["width"] == 992


def test_render_strip_html_injects_icons() -> None:
    html = _render_strip_html(is_popup=False, mode="full_width")

    assert "/*__PYWORKON_ICONS__*/" not in html
    assert json.dumps(DASHBOARD_ICONS) in html


def test_render_strip_html_injects_font_as_base64() -> None:
    html = _render_strip_html(is_popup=False, mode="full_width")

    assert "__PYWORKON_FONT_BASE64__" not in html
    assert "data:font/woff2;base64," in html


def test_render_strip_html_is_cacheable_and_deterministic() -> None:
    assert _render_strip_html(is_popup=False, mode="full_width") == _render_strip_html(
        is_popup=False, mode="full_width"
    )


def test_render_strip_html_injects_is_popup_flag() -> None:
    strip_html = _render_strip_html(is_popup=False, mode="full_width")
    popup_html = _render_strip_html(is_popup=True, mode="full_width")

    assert "__PYWORKON_IS_POPUP__" not in strip_html
    assert "const IS_POPUP_WINDOW = false;" in strip_html
    assert "const IS_POPUP_WINDOW = true;" in popup_html


def test_render_strip_html_injects_strip_mode() -> None:
    beside_dock_html = _render_strip_html(is_popup=False, mode="beside_dock")
    full_width_html = _render_strip_html(is_popup=False, mode="full_width")

    assert "__PYWORKON_STRIP_MODE__" not in beside_dock_html
    assert '"beside_dock"' in beside_dock_html
    assert '"full_width"' in full_width_html


def test_render_strip_html_injects_popup_width_bounds() -> None:
    html = _render_strip_html(is_popup=True, mode="full_width")

    assert "__PYWORKON_POPUP_MIN_WIDTH__" not in html
    assert "__PYWORKON_POPUP_MAX_WIDTH__" not in html
    assert f'Number("{POPUP_MIN_WIDTH}")' in html
    assert f'Number("{POPUP_MAX_WIDTH}")' in html


class _FakeThread:
    """Records `threading.Thread(...)` construction instead of actually running it."""

    instances: ClassVar[list[_FakeThread]] = []

    def __init__(
        self, *, target: object, kwargs: dict[str, object], daemon: bool
    ) -> None:
        self.target = target
        self.kwargs = kwargs
        self.daemon = daemon
        self.started = False
        _FakeThread.instances.append(self)

    def start(self) -> None:
        self.started = True


def _get_on_screen_change(fake_appkit: MagicMock) -> object:
    observer = fake_appkit.NSNotificationCenter.defaultCenter.return_value
    (_name, _obj, _queue, block), _kwargs = (
        observer.addObserverForName_object_queue_usingBlock_.call_args
    )
    return block


def _bind_watch_screen_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[object, MagicMock]:
    # macOS-only -- absent on Linux CI, where `pywebview` installs without its
    # Cocoa backend deps. `app.py` imports `AppKit` lazily, so merely importing
    # this module doesn't fail -- but `monkeypatch.setattr(app_module,
    # "AppKit", fake_appkit)` below does a `getattr` first (to record the
    # value to restore later), which *forces* that lazy import to resolve.
    # Skip up front instead of failing with `ModuleNotFoundError`, matching
    # `tests/test_strip_dock_geometry.py`'s module-level guard -- scoped to
    # just this test since every other test in this file is AppKit-free.
    pytest.importorskip("AppKit")
    _FakeThread.instances = []
    fake_appkit = MagicMock()
    monkeypatch.setattr(app_module, "AppKit", fake_appkit)
    monkeypatch.setattr(app_module, "threading", MagicMock(Thread=_FakeThread))
    monkeypatch.setattr(app_module.time, "sleep", lambda _seconds: None)
    bridge = MagicMock()
    app_module._watch_screen_changes(bridge)
    return _get_on_screen_change(fake_appkit), bridge


def test_watch_screen_changes_suppresses_notifications_while_a_recompute_is_in_flight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A recompute's own Dock-autohide toggle must not restart the cycle.

    Regression test: toggling Dock auto-hide changes `visibleFrame`, which
    itself fires `NSApplicationDidChangeScreenParametersNotification` --
    `bridge.py`'s `recompute_and_apply_layout()` toggles the Dock up to twice
    per call (restore, then re-apply for "full_width"), and without
    suppression, a bounded simulation showed this snowballs into a runaway,
    self-sustaining stream of recomputes (six still pending after five
    cycles) from a single external event. No clock mocking here, unlike an
    earlier time-window-based version of this suppression -- a slow
    recompute must stay suppressed for as long as it's actually running, not
    just for a fixed duration that a sluggish `osascript` call could outlast.
    """
    on_screen_change, bridge = _bind_watch_screen_changes(monkeypatch)

    on_screen_change(None)
    assert len(_FakeThread.instances) == 1

    # Arrives while the first recompute is still "in flight" (its thread was
    # scheduled but hasn't been run yet) -- must not schedule a second one,
    # regardless of how much time this takes.
    on_screen_change(None)
    assert len(_FakeThread.instances) == 1
    assert bridge.recompute_and_apply_layout.call_count == 0


def test_watch_screen_changes_coalesces_a_pending_notification_into_one_trailing_recompute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A notification that arrives mid-recompute must not be dropped.

    Regression test: a time-window-based version of this suppression simply
    discarded any notification arriving within the window, with no trailing
    recompute afterward -- a genuinely new external event in quick succession
    (e.g. swapping which external monitor is plugged in) left the strip on
    stale geometry indefinitely, since nothing scheduled a follow-up. Whether
    the coalesced notification was self-generated or a real second change,
    exactly one trailing recompute must run once the in-flight one finishes.
    """
    on_screen_change, bridge = _bind_watch_screen_changes(monkeypatch)

    on_screen_change(None)
    on_screen_change(None)  # coalesced instead of dropped -- see above
    assert len(_FakeThread.instances) == 1

    # Simulate the background thread actually running its target.
    instance = _FakeThread.instances[0]
    instance.target(**instance.kwargs)

    assert bridge.recompute_and_apply_layout.call_count == 2


def test_watch_screen_changes_handles_a_fresh_notification_after_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Once a recompute cycle fully settles, a later notification starts a new one."""
    on_screen_change, bridge = _bind_watch_screen_changes(monkeypatch)

    on_screen_change(None)
    instance = _FakeThread.instances[0]
    instance.target(**instance.kwargs)  # settles: nothing was pending
    assert bridge.recompute_and_apply_layout.call_count == 1

    on_screen_change(None)

    assert len(_FakeThread.instances) == 2


def test_watch_screen_changes_waits_briefly_before_declaring_itself_settled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A delayed self-echo must get a chance to arrive before `busy` clears.

    Regression test: a real Dock-autohide toggle's own notification doesn't
    necessarily land the instant `recompute_and_apply_layout()` returns --
    checking `pending` immediately afterward, with no pause at all, can miss
    it, incorrectly declaring the cycle settled right before its own echo
    arrives and (seeing `busy` already cleared) starts a brand new,
    unnecessary cycle instead of being coalesced into this one.
    """
    on_screen_change, _bridge = _bind_watch_screen_changes(monkeypatch)
    sleep_calls: list[float] = []
    monkeypatch.setattr(app_module.time, "sleep", sleep_calls.append)

    on_screen_change(None)
    instance = _FakeThread.instances[0]
    instance.target(**instance.kwargs)

    assert sleep_calls == [app_module._SCREEN_CHANGE_SETTLE_SECONDS]


def test_watch_screen_changes_caps_a_sustained_coalescing_storm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A storm of real notifications must not be able to loop forever.

    Regression test: observed in practice after waking a laptop from sleep
    and logging back in -- a burst of genuinely new screen-change
    notifications (display reattaching, login window dismissing, Dock
    relaunching) kept arriving faster than each recompute's own settle pause,
    so an uncapped coalescing loop kept running indefinitely, visibly
    flickering the real Dock between hidden and shown on every iteration
    until the strip was restarted. Each iteration's own `compute_strip_
    layout()` measurement can also be transiently wrong this early after
    wake (e.g. the Dock process or Accessibility tree not fully back up
    yet) -- capping the loop means a bad reading can only get "stuck" for
    one capped burst, not forever, since the very next notification starts a
    fresh one that can measure correctly once the system has settled.
    """
    on_screen_change, bridge = _bind_watch_screen_changes(monkeypatch)

    def _a_fresh_notification_arrives_mid_recompute(**_kwargs: object) -> None:
        on_screen_change(None)

    bridge.recompute_and_apply_layout.side_effect = (
        _a_fresh_notification_arrives_mid_recompute
    )

    on_screen_change(None)
    instance = _FakeThread.instances[0]
    instance.target(**instance.kwargs)

    assert (
        bridge.recompute_and_apply_layout.call_count
        == app_module._MAX_COALESCED_SCREEN_CHANGE_RECOMPUTES
    )
