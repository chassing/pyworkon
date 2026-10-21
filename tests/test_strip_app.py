"""Tests for the strip's HTML rendering (icon + font injection) and window setup."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar
from unittest.mock import MagicMock

from pyworkon.interfaces.relay.icons import DASHBOARD_ICONS
from pyworkon.interfaces.strip import app as app_module
from pyworkon.interfaces.strip.app import _build_windows, _render_strip_html
from pyworkon.interfaces.strip.dock_geometry import StripLayout
from pyworkon.interfaces.strip.native import POPUP_MAX_WIDTH, POPUP_MIN_WIDTH

if TYPE_CHECKING:
    import pytest


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
    strip's own app never activating. Applies to both windows -- the popup
    window delivers real clicks too (e.g. for PR links).
    """
    screen = _FakeScreen()
    calls: list[dict[str, object]] = []

    def fake_create_window(*_args: object, **kwargs: object) -> MagicMock:
        calls.append(kwargs)
        return MagicMock()

    monkeypatch.setattr(app_module.webview, "create_window", fake_create_window)

    _build_windows(MagicMock(), layout=_make_layout(screen), auto_hide=False)

    assert len(calls) == 2
    assert all(call["focus"] is False for call in calls)


def test_build_windows_binds_the_bridge_to_both_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    screen = _FakeScreen()
    windows = [MagicMock(), MagicMock()]

    monkeypatch.setattr(
        app_module.webview, "create_window", lambda *_a, **_kw: windows.pop(0)
    )
    bridge = MagicMock()
    layout = _make_layout(screen)

    window, popup_window = _build_windows(bridge, layout=layout, auto_hide=False)

    bridge.bind.assert_called_once_with(
        window, popup_window, layout=layout, collapsed=False
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


def test_watch_screen_changes_debounces_rapid_self_triggered_notifications(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A recompute's own Dock-autohide toggle must not restart the cycle.

    Regression test: toggling Dock auto-hide changes `visibleFrame`, which
    itself fires `NSApplicationDidChangeScreenParametersNotification` --
    `bridge.py`'s `recompute_and_apply_layout()` toggles the Dock up to twice
    per call (restore, then re-apply for "full_width"), and without
    debouncing, a bounded simulation showed this snowballs into a runaway,
    self-sustaining stream of recomputes (six still pending after five
    cycles) from a single external event.
    """
    _FakeThread.instances = []
    fake_appkit = MagicMock()
    monkeypatch.setattr(app_module, "AppKit", fake_appkit)
    monkeypatch.setattr(app_module, "threading", MagicMock(Thread=_FakeThread))
    clock = {"now": 1000.0}
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock["now"])
    bridge = MagicMock()

    app_module._watch_screen_changes(bridge)
    on_screen_change = _get_on_screen_change(fake_appkit)

    on_screen_change(None)
    assert len(_FakeThread.instances) == 1

    # A self-generated notification (from this cycle's own Dock toggle)
    # arrives almost immediately afterward -- must not schedule another.
    clock["now"] += 0.05
    on_screen_change(None)
    assert len(_FakeThread.instances) == 1

    # A genuinely new external event, well after the debounce window, must
    # still be handled.
    clock["now"] += app_module._SCREEN_CHANGE_DEBOUNCE_SECONDS + 0.1
    on_screen_change(None)
    assert len(_FakeThread.instances) == 2
