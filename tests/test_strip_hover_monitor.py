"""Tests for the strip's focus-free hover tracking (polled mouse position)."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from pyworkon.interfaces.strip import hover_monitor as hover_monitor_module
from pyworkon.interfaces.strip.hover_monitor import HoverMonitor
from pyworkon.interfaces.strip.native import (
    POPUP_MAX_HEIGHT,
    POPUP_MAX_WIDTH,
    POPUP_MIN_WIDTH,
)

# macOS-only (pyobjc) -- absent on Linux CI, where `pywebview` installs
# without its Cocoa backend deps. `importorskip` both binds the name and
# skips the whole module cleanly, instead of a plain `from X import Y`
# failing at collection time.
AppHelper = pytest.importorskip("PyObjCTools.AppHelper")


@pytest.fixture(autouse=True)
def _run_call_after_synchronously(monkeypatch: pytest.MonkeyPatch) -> None:
    """`AppHelper.callAfter` only fires once a Cocoa run loop is pumping; run it inline instead."""
    monkeypatch.setattr(AppHelper, "callAfter", lambda func, *a, **kw: func(*a, **kw))


CHIP_RECT = {
    "session_name": "s1",
    "left": 10.0,
    "top": 0.0,
    "width": 100.0,
    "height": 56.0,
}
OTHER_CHIP_RECT = {
    "session_name": "s2",
    "left": 120.0,
    "top": 0.0,
    "width": 100.0,
    "height": 56.0,
}


@dataclass
class _FakePoint:
    x: float
    y: float


@dataclass
class _FakeSize:
    width: float
    height: float


@dataclass
class _FakeFrame:
    origin: _FakePoint
    size: _FakeSize


@pytest.fixture
def fake_appkit(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock()
    monkeypatch.setattr(hover_monitor_module, "AppKit", fake)
    return fake


def _set_mouse(fake_appkit: MagicMock, x: float, y: float) -> None:
    fake_appkit.NSEvent.mouseLocation.return_value = _FakePoint(x, y)


def _mouse(fake_appkit: MagicMock) -> _FakePoint:
    return fake_appkit.NSEvent.mouseLocation()


def _make_monitor(
    fake_appkit: MagicMock,
    *,
    window_width: float = 1000,
    window_height: float = 56,
    window_x: float = 0,
    window_y: float = 0,
    screen_width: float = 1920,
    screen_height: float = 1200,
    popup_visible: bool = False,
    popup_frame: _FakeFrame | None = None,
) -> HoverMonitor:
    window = MagicMock()
    window.native.frame.return_value = _FakeFrame(
        origin=_FakePoint(window_x, window_y),
        size=_FakeSize(window_width, window_height),
    )
    window.native.screen.return_value.frame.return_value = _FakeFrame(
        origin=_FakePoint(0, 0), size=_FakeSize(screen_width, screen_height)
    )
    popup_window = MagicMock()
    popup_window.native.isVisible.return_value = popup_visible
    popup_window.native.frame.return_value = popup_frame or _FakeFrame(
        origin=_FakePoint(0, 0), size=_FakeSize(0, 0)
    )
    return HoverMonitor(window, popup_window)


def test_hit_test_finds_chip_under_mouse(fake_appkit: MagicMock) -> None:
    monitor = _make_monitor(fake_appkit)
    monitor.set_chip_rects([CHIP_RECT])
    _set_mouse(fake_appkit, x=50, y=56 - 20)  # inside chip, Cocoa bottom-left origin

    assert monitor._hit_test(_mouse(fake_appkit)) == "s1"


def test_hit_test_returns_none_outside_window(fake_appkit: MagicMock) -> None:
    monitor = _make_monitor(fake_appkit)
    monitor.set_chip_rects([CHIP_RECT])
    _set_mouse(fake_appkit, x=-10, y=-10)  # below/left of the window entirely

    assert monitor._hit_test(_mouse(fake_appkit)) is None


def test_hit_test_returns_none_when_window_native_is_missing(
    fake_appkit: MagicMock,
) -> None:
    window = MagicMock()
    window.native = None
    popup_window = MagicMock()
    popup_window.native.isVisible.return_value = False
    monitor = HoverMonitor(window, popup_window)
    monitor.set_chip_rects([CHIP_RECT])
    _set_mouse(fake_appkit, x=50, y=36)

    assert monitor._hit_test(_mouse(fake_appkit)) is None


def test_hit_test_tolerates_small_jitter_just_outside_a_chip(
    fake_appkit: MagicMock,
) -> None:
    """A few px of margin stops sub-pixel mouse jitter at an edge from flapping hover."""
    monitor = _make_monitor(fake_appkit)
    monitor.set_chip_rects([CHIP_RECT])
    # 2px to the left of the chip's left edge (left=10) -- within tolerance.
    _set_mouse(fake_appkit, x=8, y=36)

    assert monitor._hit_test(_mouse(fake_appkit)) == "s1"


def test_hit_test_keep_current_when_mouse_over_visible_popup_window(
    fake_appkit: MagicMock,
) -> None:
    """Checked against the popup window's own native frame, not a CSS-reported rect.

    Unlike the old single-window design, the popup's screen position is
    something Python itself sets (`position_and_show_popup_window()`), so
    there's no need for `strip.html` to report it back.
    """
    popup_frame = _FakeFrame(origin=_FakePoint(500, 56), size=_FakeSize(360, 320))
    monitor = _make_monitor(fake_appkit, popup_visible=True, popup_frame=popup_frame)
    monitor.set_chip_rects([CHIP_RECT])
    _set_mouse(fake_appkit, x=600, y=200)  # inside the popup window's frame

    assert monitor._hit_test(_mouse(fake_appkit)) == hover_monitor_module._KEEP_CURRENT


def test_hit_test_ignores_popup_window_when_not_visible(
    fake_appkit: MagicMock,
) -> None:
    popup_frame = _FakeFrame(origin=_FakePoint(500, 56), size=_FakeSize(360, 320))
    monitor = _make_monitor(fake_appkit, popup_visible=False, popup_frame=popup_frame)
    monitor.set_chip_rects([CHIP_RECT])
    _set_mouse(
        fake_appkit, x=600, y=200
    )  # would be inside the popup frame, but it's hidden

    assert monitor._hit_test(_mouse(fake_appkit)) is None


def test_poll_once_calls_hover_enter_on_first_hit(fake_appkit: MagicMock) -> None:
    monitor = _make_monitor(fake_appkit)
    monitor.set_chip_rects([CHIP_RECT])
    monitor._popup_window.evaluate_js.return_value = [360, 100]
    _set_mouse(fake_appkit, x=50, y=36)

    monitor._poll_once(_mouse(fake_appkit))

    monitor._popup_window.evaluate_js.assert_called_once_with(
        'window.__showPopupFor("s1", 984.0)'
    )
    assert monitor._hovered == "s1"


def test_poll_once_debounces_leaving_a_chip(fake_appkit: MagicMock) -> None:
    """A single missed tick must not immediately close the popup.

    Natural mouse micro-jitter (or a chip's rect shifting for one tick while a
    daemon-pushed re-render reflows the row) would otherwise flap the hover
    state shut and immediately back open. Leaving only commits after
    `_LEAVE_DEBOUNCE_TICKS` consecutive misses.
    """
    monitor = _make_monitor(fake_appkit)
    monitor.set_chip_rects([CHIP_RECT])
    monitor._hovered = "s1"
    _set_mouse(fake_appkit, x=500, y=36)  # far from the chip, still inside the window

    for _ in range(hover_monitor_module._LEAVE_DEBOUNCE_TICKS - 1):
        monitor._poll_once(_mouse(fake_appkit))
    assert monitor._hovered == "s1"

    monitor._poll_once(_mouse(fake_appkit))

    assert monitor._hovered is None


def test_poll_once_resets_the_miss_streak_once_back_on_the_chip(
    fake_appkit: MagicMock,
) -> None:
    monitor = _make_monitor(fake_appkit)
    monitor.set_chip_rects([CHIP_RECT])
    monitor._hovered = "s1"
    _set_mouse(fake_appkit, x=500, y=36)
    monitor._poll_once(_mouse(fake_appkit))  # one miss, not yet committed

    _set_mouse(fake_appkit, x=50, y=36)  # back on the chip
    monitor._poll_once(_mouse(fake_appkit))

    assert monitor._hovered == "s1"
    assert monitor._miss_streak == 0


def test_poll_once_does_not_repeat_calls_for_the_same_chip(
    fake_appkit: MagicMock,
) -> None:
    monitor = _make_monitor(fake_appkit)
    monitor.set_chip_rects([CHIP_RECT])
    monitor._hovered = "s1"
    _set_mouse(fake_appkit, x=50, y=36)

    monitor._poll_once(_mouse(fake_appkit))

    monitor._popup_window.evaluate_js.assert_not_called()


def test_poll_once_switches_directly_between_chips(fake_appkit: MagicMock) -> None:
    monitor = _make_monitor(fake_appkit)
    monitor.set_chip_rects([CHIP_RECT, OTHER_CHIP_RECT])
    monitor._hovered = "s1"
    monitor._popup_window.evaluate_js.return_value = [360, 100]
    _set_mouse(fake_appkit, x=150, y=36)  # inside the second chip

    monitor._poll_once(_mouse(fake_appkit))

    monitor._popup_window.evaluate_js.assert_called_once_with(
        'window.__showPopupFor("s2", 984.0)'
    )
    assert monitor._hovered == "s2"


def test_poll_once_keeps_popup_open_when_mouse_moves_onto_popup_window(
    fake_appkit: MagicMock,
) -> None:
    popup_frame = _FakeFrame(origin=_FakePoint(0, 60), size=_FakeSize(360, 320))
    monitor = _make_monitor(fake_appkit, popup_visible=True, popup_frame=popup_frame)
    monitor.set_chip_rects([CHIP_RECT])
    monitor._hovered = "s1"
    _set_mouse(fake_appkit, x=50, y=200)  # inside the popup window, not any chip

    monitor._poll_once(_mouse(fake_appkit))

    monitor._popup_window.evaluate_js.assert_not_called()
    assert monitor._hovered == "s1"


def test_reclaim_activation_reactivates_the_last_other_app_when_we_are_frontmost(
    fake_appkit: MagicMock,
) -> None:
    """`deactivate()` was confirmed (via diagnostic logging) to never take effect.

    Explicitly reactivating a specific other app is the targeted replacement.
    """
    monitor = _make_monitor(fake_appkit)
    other_app = MagicMock()
    other_app.processIdentifier.return_value = 222
    _set_frontmost(fake_appkit, other_app)
    monitor._reclaim_activation_if_stolen()  # records `other_app` as "last other app"

    ourselves = MagicMock()
    ourselves.processIdentifier.return_value = 111
    _set_frontmost(fake_appkit, ourselves)
    monitor._reclaim_activation_if_stolen()

    other_app.activateWithOptions_.assert_called_once_with(0)


def _set_frontmost(fake_appkit: MagicMock, app: MagicMock) -> None:
    fake_appkit.NSWorkspace.sharedWorkspace.return_value.frontmostApplication.return_value = app
    fake_appkit.NSRunningApplication.currentApplication.return_value.processIdentifier.return_value = 111


def test_reclaim_activation_does_nothing_when_a_different_app_is_already_frontmost(
    fake_appkit: MagicMock,
) -> None:
    monitor = _make_monitor(fake_appkit)
    other_app = MagicMock()
    other_app.processIdentifier.return_value = 222
    _set_frontmost(fake_appkit, other_app)

    monitor._reclaim_activation_if_stolen()

    other_app.activateWithOptions_.assert_not_called()


def test_reclaim_activation_does_nothing_without_a_known_other_app_yet(
    fake_appkit: MagicMock,
) -> None:
    monitor = _make_monitor(fake_appkit)
    ourselves = MagicMock()
    ourselves.processIdentifier.return_value = 111
    _set_frontmost(fake_appkit, ourselves)

    monitor._reclaim_activation_if_stolen()  # must not raise -- no `_last_other_app` yet


def test_process_none_hides_the_popup_window(fake_appkit: MagicMock) -> None:
    monitor = _make_monitor(fake_appkit)

    monitor._process(None)

    hide_calls = monitor._popup_window.native.orderOut_
    hide_calls.assert_called_once_with(None)
    monitor._popup_window.evaluate_js.assert_not_called()


def test_process_hides_the_popup_when_the_target_cannot_render(
    fake_appkit: MagicMock,
) -> None:
    """A plain tmux session's `__showPopupFor()` returns `null` -- no popup to show.

    Regression test: moving directly from a project chip (popup already
    open) to a plain-session chip must hide the previous popup, not leave
    the prior project's stale content floating beside the wrong chip.
    """
    monitor = _make_monitor(fake_appkit)
    monitor._popup_window.evaluate_js.return_value = None

    monitor._process("0-main")

    hide_calls = monitor._popup_window.native.orderOut_
    hide_calls.assert_called_once_with(None)


def test_process_session_name_renders_resizes_then_shows_in_order(
    fake_appkit: MagicMock,
) -> None:
    """Content and sizing must land before the window becomes visible.

    `evaluate_js()` blocks until the script actually runs and returns the
    measured `[width, height]`; `resize_and_position_popup_window()` must
    then happen *before* `show_popup_window()` -- resizing a still-hidden
    window has no flash risk, but showing it before it's the right
    size/content would.
    """
    monitor = _make_monitor(fake_appkit)
    monitor.set_chip_rects([CHIP_RECT])
    calls: list[str] = []
    monitor._popup_window.evaluate_js.side_effect = lambda _script: (
        calls.append("js") or [420, 180]
    )
    monitor._popup_window.native.setFrame_display_.side_effect = lambda *_a: (
        calls.append("resize")
    )
    monitor._popup_window.native.orderFrontRegardless.side_effect = lambda: (
        calls.append("show")
    )

    monitor._process("s1")

    assert calls == ["js", "resize", "show"]
    monitor._popup_window.evaluate_js.assert_called_once_with(
        'window.__showPopupFor("s1", 984.0)'
    )
    frame, _redisplay = monitor._popup_window.native.setFrame_display_.call_args[0]
    assert frame.size.width == 420
    assert frame.size.height == 180


def test_process_session_name_clamps_the_measured_height_to_available_screen_space(
    fake_appkit: MagicMock,
) -> None:
    """The popup's height cap is the real space above the strip, not a fixed guess.

    Mirrors `clamp_popup_width()` already measuring against the content's own
    natural width -- a hardcoded `POPUP_MAX_HEIGHT` either forced a needless
    scrollbar on a tall popup that would have fit fine on a tall screen, or
    risked running off the top of a short one. The strip always sits flush
    with the screen's bottom edge, so the space between the strip's own top
    edge and the screen's top edge is exactly what's free for the popup.
    """
    monitor = _make_monitor(
        fake_appkit, window_height=56, window_y=0, screen_height=600
    )
    monitor.set_chip_rects([CHIP_RECT])
    monitor._popup_window.evaluate_js.return_value = [420, 10_000]  # absurdly tall

    monitor._process("s1")

    frame, _redisplay = monitor._popup_window.native.setFrame_display_.call_args[0]
    expected_max = 600 - 56 - hover_monitor_module._SCREEN_EDGE_MARGIN
    assert frame.size.height == expected_max


def test_process_session_name_falls_back_to_fixed_max_height_without_a_screen(
    fake_appkit: MagicMock,
) -> None:
    """No determinable screen (e.g. mid reconfiguration) falls back to the fixed cap."""
    monitor = _make_monitor(fake_appkit)
    monitor.set_chip_rects([CHIP_RECT])
    monitor._window.native.screen.return_value = None
    monitor._popup_window.evaluate_js.return_value = [420, 10_000]  # absurdly tall

    monitor._process("s1")

    frame, _redisplay = monitor._popup_window.native.setFrame_display_.call_args[0]
    assert frame.size.height == POPUP_MAX_HEIGHT


def test_process_session_name_clamps_the_measured_width_to_the_strips_own_span(
    fake_appkit: MagicMock,
) -> None:
    """The popup's width cap is the strip's own horizontal span, not a fixed guess.

    Mirrors `_max_popup_height()` -- a hardcoded `POPUP_MAX_WIDTH` keeps
    getting hit again by whatever the next, slightly-longer real-world CI
    check name turns out to be, forcing an orphaned single-word second line.
    """
    monitor = _make_monitor(fake_appkit, window_width=600)
    monitor.set_chip_rects([CHIP_RECT])
    monitor._popup_window.evaluate_js.return_value = [5_000, 180]  # absurdly wide

    monitor._process("s1")

    frame, _redisplay = monitor._popup_window.native.setFrame_display_.call_args[0]
    expected_max = 600 - 2 * hover_monitor_module._SCREEN_EDGE_MARGIN
    assert frame.size.width == expected_max


def test_max_popup_width_falls_back_to_fixed_max_width_without_a_strip_window(
    fake_appkit: MagicMock,
) -> None:
    monitor = _make_monitor(fake_appkit)
    monitor._window.native = None

    assert monitor._max_popup_width() == POPUP_MAX_WIDTH


def test_process_session_name_clamps_a_too_narrow_measured_width(
    fake_appkit: MagicMock,
) -> None:
    monitor = _make_monitor(fake_appkit)
    monitor.set_chip_rects([CHIP_RECT])
    monitor._popup_window.evaluate_js.return_value = [10, 180]  # absurdly narrow

    monitor._process("s1")

    frame, _redisplay = monitor._popup_window.native.setFrame_display_.call_args[0]
    assert frame.size.width == POPUP_MIN_WIDTH


def test_popup_screen_position_anchors_above_the_strip_window(
    fake_appkit: MagicMock,
) -> None:
    monitor = _make_monitor(fake_appkit, window_x=0, window_y=2104, window_height=56)
    monitor.set_chip_rects([CHIP_RECT])

    x, y = monitor._popup_screen_position("s1", 360)

    assert y == 2104 + 56
    assert x == 2104 * 0 + 10  # strip origin.x (0) + chip.left (10)


def test_popup_screen_position_anchors_above_the_chip_not_the_strip_window(
    fake_appkit: MagicMock,
) -> None:
    """A centered (not top-aligned) chip within a taller strip still gets a flush popup.

    Anchoring to the *window's* top edge instead would leave a visible gap
    of the strip's own background between the popup and the chip itself --
    regression test for `beside_dock` mode, where the strip's height matches
    the real Dock's (can exceed a chip's own natural height), and `#strip`
    uses `align-items: center` (see strip.html), leaving space above the chip.
    """
    monitor = _make_monitor(fake_appkit, window_x=0, window_y=2104, window_height=84)
    monitor.set_chip_rects([
        {
            "session_name": "s1",
            "left": 10.0,
            "top": 12.0,
            "width": 100.0,
            "height": 60.0,
        }
    ])

    x, y = monitor._popup_screen_position("s1", 360)

    assert y == 2104 + (84 - 12)  # window origin.y + (window height - chip.top)
    assert x == 10


def test_popup_screen_position_clamps_to_the_left_screen_edge(
    fake_appkit: MagicMock,
) -> None:
    monitor = _make_monitor(fake_appkit, window_x=0, window_width=1000)
    monitor.set_chip_rects([
        {"session_name": "s1", "left": 0.0, "top": 0.0, "width": 100.0, "height": 56.0}
    ])

    x, _y = monitor._popup_screen_position("s1", 360)

    assert x == hover_monitor_module._SCREEN_EDGE_MARGIN


def test_popup_screen_position_clamps_to_the_right_screen_edge(
    fake_appkit: MagicMock,
) -> None:
    monitor = _make_monitor(fake_appkit, window_x=0, window_width=1000)
    monitor.set_chip_rects([
        {
            "session_name": "s1",
            "left": 990.0,  # would push a 360px-wide popup off-screen
            "top": 0.0,
            "width": 100.0,
            "height": 56.0,
        }
    ])

    x, _y = monitor._popup_screen_position("s1", 360)

    assert x == 1000 - 360 - hover_monitor_module._SCREEN_EDGE_MARGIN


def test_popup_screen_position_clamp_depends_on_the_actual_popup_width(
    fake_appkit: MagicMock,
) -> None:
    """A wider popup must clamp further from the edge than a narrower one."""
    monitor = _make_monitor(fake_appkit, window_x=0, window_width=1000)
    monitor.set_chip_rects([
        {
            "session_name": "s1",
            "left": 990.0,
            "top": 0.0,
            "width": 100.0,
            "height": 56.0,
        }
    ])

    x, _y = monitor._popup_screen_position("s1", 700)

    assert x == 1000 - 700 - hover_monitor_module._SCREEN_EDGE_MARGIN


def test_popup_screen_position_returns_none_when_strip_native_is_missing(
    fake_appkit: MagicMock,
) -> None:
    monitor = _make_monitor(fake_appkit)
    monitor.set_chip_rects([CHIP_RECT])
    monitor._window.native = None

    assert monitor._popup_screen_position("s1", 360) is None


def test_start_spawns_a_daemon_polling_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    window = MagicMock()
    popup_window = MagicMock()
    monitor = HoverMonitor(window, popup_window)
    captured: dict[str, object] = {}

    class _FakeThread:
        def __init__(self, *, target: object, daemon: bool) -> None:
            captured["target"] = target
            captured["daemon"] = daemon

        def start(self) -> None:
            captured["started"] = True

    monkeypatch.setattr(hover_monitor_module.threading, "Thread", _FakeThread)

    monitor.start()

    assert captured["target"] == monitor._poll_loop
    assert captured["daemon"] is True
    assert captured["started"] is True
