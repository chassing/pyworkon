"""Tests for the strip's JS-callable Python bridge."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Self
from unittest.mock import MagicMock

import pytest
import yaml

from pyworkon import config as config_module
from pyworkon.config import Config
from pyworkon.interfaces.strip import bridge as bridge_module
from pyworkon.interfaces.strip.bridge import COLLAPSED_HEIGHT, STRIP_HEIGHT, StripBridge
from pyworkon.interfaces.strip.dock_geometry import StripLayout

# macOS-only (pyobjc) -- absent on Linux CI, where `pywebview` installs
# without its Cocoa backend deps. `importorskip` both binds the name and
# skips the whole module cleanly, instead of a plain `from X import Y`
# failing at collection time.
AppHelper = pytest.importorskip("PyObjCTools.AppHelper")


@pytest.fixture(autouse=True)
def _run_call_after_synchronously(monkeypatch: pytest.MonkeyPatch) -> None:
    """`AppHelper.callAfter` only fires once a Cocoa run loop is pumping; run it inline instead."""
    monkeypatch.setattr(AppHelper, "callAfter", lambda func, *a, **kw: func(*a, **kw))


@pytest.fixture(autouse=True)
def fake_hover_monitor(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Fake out the global mouse monitor `bind()` otherwise starts for real.

    A real OS-level side effect (and a leaked monitor, since nothing ever
    removes it) that has no business happening for every test calling `bind()`.
    """
    fake_cls = MagicMock()
    monkeypatch.setattr(bridge_module, "HoverMonitor", fake_cls)
    return fake_cls


@pytest.fixture(autouse=True)
def fake_dock_autohide(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> dict[str, bool]:
    """Fake out real `osascript`/System Events calls.

    `bind()`'s default "full_width" layout would otherwise toggle the
    *real* Dock auto-hide on every test run, which must never happen
    outside an explicit, asked-for real-environment test. Also redirects
    `_DOCK_AUTOHIDE_ORIGINAL_MARKER` to `tmp_path` -- otherwise every test
    exercising `_sync_dock_autohide_for_mode()`/`restore_dock_autohide()`
    would write/unlink a real file under the real user cache dir.
    """
    state = {"enabled": False}
    monkeypatch.setattr(
        bridge_module, "_dock_autohide_enabled", lambda: state["enabled"]
    )

    def _set(*, enabled: bool) -> None:
        state["enabled"] = enabled

    monkeypatch.setattr(bridge_module, "_set_dock_autohide", _set)
    monkeypatch.setattr(
        bridge_module,
        "_DOCK_AUTOHIDE_ORIGINAL_MARKER",
        tmp_path / "strip_dock_autohide_original",
    )
    return state


class _RecordingDaemonClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def switch_session(self, session_name: str) -> None:
        self.calls.append(("switch_session", session_name))

    def kill_session(self, session_name: str) -> None:
        self.calls.append(("kill_session", session_name))

    def enter_project(self, project_id: str) -> None:
        self.calls.append(("enter_project", project_id))


def _make_layout(
    *,
    mode: str = "full_width",
    x: float = 0,
    y: float = 0,
    width: float = 1920,
    height: int = STRIP_HEIGHT,
) -> StripLayout:
    return StripLayout(
        mode=mode, screen=MagicMock(), x=x, y=y, width=width, height=height
    )  # type: ignore[arg-type]


class _FakeWindow:
    def __init__(self) -> None:
        self.native = MagicMock()
        self.destroy = MagicMock()
        self.evaluate_js = MagicMock()
        # Real numbers, not a bare MagicMock -- `_picker_screen_position()`
        # does arithmetic on `.frame().origin`/`.size`, which would otherwise
        # raise `TypeError` (silently swallowed by `open_project_picker()`'s
        # `contextlib.suppress(Exception)` -- confirmed the hard way: without
        # this, `move_picker_window`/`show_picker_window` never got called at
        # all, with no visible error).
        frame = MagicMock()
        frame.origin.x = 0.0
        frame.origin.y = 0.0
        frame.size.width = 1920.0
        frame.size.height = 56.0
        self.native.frame.return_value = frame
        # Same reasoning for `.screen().frame()` -- `show_context_menu()`'s
        # screen-edge clamp does arithmetic on it too, which a bare
        # `MagicMock` would silently fail on inside its own
        # `contextlib.suppress(Exception)` block, confirmed the same way.
        screen_frame = MagicMock()
        screen_frame.origin.x = 0.0
        screen_frame.origin.y = 0.0
        screen_frame.size.width = 1920.0
        screen_frame.size.height = 1080.0
        self.native.screen.return_value.frame.return_value = screen_frame


def test_switch_session_calls_daemon_client(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _RecordingDaemonClient()
    monkeypatch.setattr(bridge_module, "DaemonClient", lambda: recorder)

    StripBridge().switch_session("my-session")

    assert recorder.calls == [("switch_session", "my-session")]


def test_kill_session_calls_daemon_client(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _RecordingDaemonClient()
    monkeypatch.setattr(bridge_module, "DaemonClient", lambda: recorder)

    StripBridge().kill_session("my-session")

    assert recorder.calls == [("kill_session", "my-session")]


def test_open_url_delegates_to_webbrowser(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(bridge_module.webbrowser, "open", opened.append)

    StripBridge().open_url("https://example.com")

    assert opened == ["https://example.com"]


def test_toggle_collapse_without_bound_window_is_noop() -> None:
    StripBridge().toggle_collapse()  # must not raise


def test_quit_without_bound_window_is_noop() -> None:
    StripBridge().quit()  # must not raise


def test_bind_creates_and_starts_a_hover_monitor(
    fake_hover_monitor: MagicMock,
) -> None:
    bridge = StripBridge()
    window = _FakeWindow()
    popup_window = _FakeWindow()

    bridge.bind(
        window,
        popup_window,
        _FakeWindow(),
        _FakeWindow(),
        layout=_make_layout(),
        collapsed=False,
    )  # type: ignore[arg-type]

    fake_hover_monitor.assert_called_once_with(window, popup_window)
    fake_hover_monitor.return_value.start.assert_called_once()


def test_update_chip_rects_forwards_to_the_hover_monitor(
    fake_hover_monitor: MagicMock,
) -> None:
    bridge = StripBridge()
    window = _FakeWindow()
    popup_window = _FakeWindow()
    bridge.bind(
        window,
        popup_window,
        _FakeWindow(),
        _FakeWindow(),
        layout=_make_layout(),
        collapsed=False,
    )  # type: ignore[arg-type]
    rects = [{"session_name": "s1", "left": 0, "top": 0, "width": 10, "height": 10}]

    bridge.update_chip_rects(rects)

    fake_hover_monitor.return_value.set_chip_rects.assert_called_once_with(rects)


def test_update_chip_rects_without_bound_window_is_noop() -> None:
    StripBridge().update_chip_rects([])  # must not raise


def test_quit_destroys_both_windows() -> None:
    """`webview.start()` only returns once every window it created has closed."""
    bridge = StripBridge()
    window = _FakeWindow()
    popup_window = _FakeWindow()
    bridge.bind(
        window,
        popup_window,
        _FakeWindow(),
        _FakeWindow(),
        layout=_make_layout(),
        collapsed=False,
    )  # type: ignore[arg-type]

    bridge.quit()

    window.destroy.assert_called_once()
    popup_window.destroy.assert_called_once()


def _last_frame_rect(window: _FakeWindow) -> tuple[float, float, float, float]:
    frame, _redisplay = window.native.setFrame_display_.call_args[0]
    return (frame.origin.x, frame.origin.y, frame.size.width, frame.size.height)


def test_toggle_collapse_shrinks_then_expands() -> None:
    bridge = StripBridge()
    window = _FakeWindow()
    popup_window = _FakeWindow()
    layout = _make_layout(x=0, y=0, width=1920, height=STRIP_HEIGHT)
    bridge.bind(
        window,
        popup_window,
        _FakeWindow(),
        _FakeWindow(),
        layout=layout,
        collapsed=False,
    )  # type: ignore[arg-type]

    bridge.toggle_collapse()
    assert _last_frame_rect(window) == (0, 0, 1920, COLLAPSED_HEIGHT)

    bridge.toggle_collapse()
    assert _last_frame_rect(window) == (0, 0, 1920, STRIP_HEIGHT)


def test_show_context_menu_without_bound_windows_is_noop() -> None:
    StripBridge().show_context_menu("[]", 0.0, 0.0)  # must not raise


def test_hide_context_menu_without_bound_window_is_noop() -> None:
    StripBridge().hide_context_menu()  # must not raise


def test_show_context_menu_renders_positions_and_shows_the_menu_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The menu's bottom-left corner must land exactly at the real click position.

    Not the popup's own chip-relative anchoring (see `hover_monitor.py`'s
    `_popup_screen_position()`) -- the menu "starts there": `click_x`/
    `click_y` (the triggering DOM event's own page-relative `clientX`/
    `clientY`, top-left origin) are converted into absolute, bottom-left
    AppKit screen coordinates via the *strip* window's own native frame
    (`_FakeWindow`'s default frame is origin (0, 0), size (1920, 56)), then
    used as the new window's rect's bottom-left origin directly. Not
    `AppKit.NSEvent.mouseLocation()` -- confirmed live that re-querying the
    "current" mouse position later (after a blocking round-trip into the
    menu window to measure its content) reads a stale, moved-on position.
    """
    bridge = StripBridge()
    _window, _popup_window, _picker_window, menu_window = _bind_with_fakes(bridge)
    menu_window.evaluate_js.return_value = 120
    resize_calls: list[tuple[object, float, float, float, float]] = []
    monkeypatch.setattr(
        bridge_module,
        "resize_and_position_menu_window",
        lambda native, x, y, w, h: resize_calls.append((native, x, y, w, h)),
    )
    show_calls: list[object] = []
    monkeypatch.setattr(bridge_module, "show_menu_window", show_calls.append)

    bridge.show_context_menu('[{"label": "Quit strip", "action": "quit"}]', 400.0, 10.0)

    (script,) = menu_window.evaluate_js.call_args[0]
    assert "__showContextMenu" in script
    assert resize_calls == [
        (menu_window.native, 400.0, 46.0, bridge_module.MENU_WIDTH, 120.0)
    ]
    assert show_calls == [menu_window.native]


def test_show_context_menu_registers_the_window_with_the_hover_monitor(
    monkeypatch: pytest.MonkeyPatch,
    fake_hover_monitor: MagicMock,
) -> None:
    bridge = StripBridge()
    _window, _popup_window, _picker_window, menu_window = _bind_with_fakes(bridge)
    menu_window.evaluate_js.return_value = 120
    monkeypatch.setattr(
        bridge_module, "resize_and_position_menu_window", lambda *_a: None
    )
    monkeypatch.setattr(bridge_module, "show_menu_window", lambda *_a: None)

    bridge.show_context_menu("[]", 0.0, 0.0)

    fake_hover_monitor.return_value.set_context_menu_window.assert_called_once_with(
        menu_window
    )


def test_show_context_menu_does_not_show_when_measured_height_is_falsy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed/empty `evaluate_js()` measurement must not show a garbage-sized window."""
    bridge = StripBridge()
    _window, _popup_window, _picker_window, menu_window = _bind_with_fakes(bridge)
    menu_window.evaluate_js.return_value = None
    show_calls: list[object] = []
    monkeypatch.setattr(bridge_module, "show_menu_window", show_calls.append)

    bridge.show_context_menu("[]", 0.0, 0.0)

    assert show_calls == []


def test_hide_context_menu_hides_the_window_and_clears_the_hover_monitor(
    monkeypatch: pytest.MonkeyPatch, fake_hover_monitor: MagicMock
) -> None:
    bridge = StripBridge()
    _window, _popup_window, _picker_window, menu_window = _bind_with_fakes(bridge)
    hide_calls: list[object] = []
    monkeypatch.setattr(bridge_module, "hide_menu_window", hide_calls.append)

    bridge.hide_context_menu()

    assert hide_calls == [menu_window.native]
    fake_hover_monitor.return_value.set_context_menu_window.assert_called_once_with(
        None
    )


def test_toggle_collapse_hides_the_popup_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Collapsing mid-hover shouldn't leave the popup floating above a hidden strip."""
    hide_calls: list[object] = []
    monkeypatch.setattr(bridge_module, "hide_popup_window", hide_calls.append)
    bridge = StripBridge()
    window = _FakeWindow()
    popup_window = _FakeWindow()
    bridge.bind(
        window,
        popup_window,
        _FakeWindow(),
        _FakeWindow(),
        layout=_make_layout(),
        collapsed=False,
    )  # type: ignore[arg-type]

    bridge.toggle_collapse()

    assert hide_calls == [popup_window.native]


def test_update_layout_resizes_the_strip_to_the_new_placement() -> None:
    bridge = StripBridge()
    window = _FakeWindow()
    popup_window = _FakeWindow()
    bridge.bind(
        window,
        popup_window,
        _FakeWindow(),
        _FakeWindow(),
        layout=_make_layout(),
        collapsed=False,
    )  # type: ignore[arg-type]

    bridge.update_layout(
        _make_layout(mode="beside_dock", x=2694, y=0, width=1146, height=84)
    )

    assert _last_frame_rect(window) == (2694, 0, 1146, 84)


def test_update_layout_keeps_the_collapsed_height() -> None:
    """A screen change mid-collapse shouldn't un-collapse the strip."""
    bridge = StripBridge()
    window = _FakeWindow()
    popup_window = _FakeWindow()
    bridge.bind(
        window,
        popup_window,
        _FakeWindow(),
        _FakeWindow(),
        layout=_make_layout(),
        collapsed=True,
    )  # type: ignore[arg-type]

    bridge.update_layout(
        _make_layout(mode="beside_dock", x=2694, y=0, width=1146, height=84)
    )

    assert _last_frame_rect(window) == (2694, 0, 1146, COLLAPSED_HEIGHT)


def test_update_layout_pushes_the_new_mode_to_both_windows() -> None:
    bridge = StripBridge()
    window = _FakeWindow()
    popup_window = _FakeWindow()
    bridge.bind(
        window,
        popup_window,
        _FakeWindow(),
        _FakeWindow(),
        layout=_make_layout(),
        collapsed=False,
    )  # type: ignore[arg-type]

    bridge.update_layout(_make_layout(mode="beside_dock"))

    for evaluate_js in (window.evaluate_js, popup_window.evaluate_js):
        evaluate_js.assert_called_once()
        (script,) = evaluate_js.call_args[0]
        assert "beside_dock" in script


def test_bind_enables_dock_autohide_for_full_width_mode(
    fake_dock_autohide: dict[str, bool],
) -> None:
    fake_dock_autohide["enabled"] = False
    bridge = StripBridge()

    bridge.bind(
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        layout=_make_layout(mode="full_width"),
        collapsed=False,
    )

    assert fake_dock_autohide["enabled"] is True


def test_bind_leaves_dock_autohide_alone_for_beside_dock_mode(
    fake_dock_autohide: dict[str, bool],
) -> None:
    fake_dock_autohide["enabled"] = False
    bridge = StripBridge()

    bridge.bind(
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        layout=_make_layout(mode="beside_dock"),
        collapsed=False,
    )

    assert fake_dock_autohide["enabled"] is False


def test_update_layout_enables_dock_autohide_when_falling_back_to_full_width(
    fake_dock_autohide: dict[str, bool],
) -> None:
    """Regression test for disconnecting the monitor a beside-dock layout was on.

    The resulting full-width mode must still hide the Dock, exactly like a
    full-width session that started out that way from the beginning.
    """
    fake_dock_autohide["enabled"] = False
    bridge = StripBridge()
    bridge.bind(
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        layout=_make_layout(mode="beside_dock"),
        collapsed=False,
    )
    assert fake_dock_autohide["enabled"] is False

    bridge.update_layout(_make_layout(mode="full_width"))

    assert fake_dock_autohide["enabled"] is True


def test_update_layout_restores_the_original_setting_when_returning_to_beside_dock(
    fake_dock_autohide: dict[str, bool],
) -> None:
    """The *original* value must come back, not a hardcoded "off".

    A user who already had Dock auto-hide on before the strip ever touched
    it must still have it on afterward.
    """
    fake_dock_autohide["enabled"] = True  # user's own setting, before any override
    bridge = StripBridge()
    bridge.bind(
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        layout=_make_layout(mode="full_width"),
        collapsed=False,
    )
    assert fake_dock_autohide["enabled"] is True  # unchanged -- already matched

    bridge.update_layout(_make_layout(mode="beside_dock"))

    assert fake_dock_autohide["enabled"] is True


def test_update_layout_restores_the_original_off_value(
    fake_dock_autohide: dict[str, bool],
) -> None:
    fake_dock_autohide["enabled"] = False
    bridge = StripBridge()
    bridge.bind(
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        layout=_make_layout(mode="full_width"),
        collapsed=False,
    )
    assert fake_dock_autohide["enabled"] is True  # overridden on

    bridge.update_layout(_make_layout(mode="beside_dock"))

    assert fake_dock_autohide["enabled"] is False  # restored to the original off


def test_bind_writes_the_crash_safe_marker_for_full_width_mode() -> None:
    """Regression test for the "stuck full-width forever, never flashes" bug.

    Confirmed live (via debug logging against a real running process): a
    `SIGKILL`/crash while overridden leaves the marker on disk; the *next*
    launch's first "full_width" capture must not blindly trust the Dock's
    current (already-forced) setting as if it were the user's real original
    -- see `recover_dock_autohide_from_unclean_shutdown()`. That recovery can
    only work if the marker is actually written the moment the override
    happens, which this test covers.
    """
    marker = bridge_module._DOCK_AUTOHIDE_ORIGINAL_MARKER
    assert not marker.exists()
    bridge = StripBridge()

    bridge.bind(
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        layout=_make_layout(mode="full_width"),
        collapsed=False,
    )

    assert marker.read_text() == "false"


def test_update_layout_removes_the_marker_on_clean_restore() -> None:
    """A clean transition back out of "full_width" must clear the marker too.

    Otherwise the *next* process launch would wrongly think the previous run
    crashed mid-override and "recover" a value that was already correctly
    restored.
    """
    marker = bridge_module._DOCK_AUTOHIDE_ORIGINAL_MARKER
    bridge = StripBridge()
    bridge.bind(
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        layout=_make_layout(mode="full_width"),
        collapsed=False,
    )
    assert marker.exists()

    bridge.update_layout(_make_layout(mode="beside_dock"))

    assert not marker.exists()


def test_restore_dock_autohide_removes_the_marker(
    fake_dock_autohide: dict[str, bool],
) -> None:
    """The shutdown path (`restore_dock_autohide()`) must also clear the marker."""
    marker = bridge_module._DOCK_AUTOHIDE_ORIGINAL_MARKER
    bridge = StripBridge()
    bridge.bind(
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        layout=_make_layout(mode="full_width"),
        collapsed=False,
    )
    assert marker.exists()

    bridge.restore_dock_autohide()

    assert not marker.exists()


def test_repeated_transitions_recapture_a_fresh_previous_value_each_time(
    fake_dock_autohide: dict[str, bool],
) -> None:
    """Each new "full_width" entry must capture the value right then.

    Not reuse a stale value left over from an earlier override/restore cycle.
    """
    fake_dock_autohide["enabled"] = False
    bridge = StripBridge()
    bridge.bind(
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        layout=_make_layout(mode="full_width"),
        collapsed=False,
    )
    bridge.update_layout(_make_layout(mode="beside_dock"))
    assert fake_dock_autohide["enabled"] is False  # restored

    # User manually turns Dock auto-hide on while beside-dock is active.
    fake_dock_autohide["enabled"] = True
    bridge.update_layout(_make_layout(mode="full_width"))
    assert fake_dock_autohide["enabled"] is True  # already on, no-op

    bridge.update_layout(_make_layout(mode="beside_dock"))

    assert fake_dock_autohide["enabled"] is True  # restored to the *new* original


def test_restore_dock_autohide_is_a_noop_without_an_override(
    fake_dock_autohide: dict[str, bool],
) -> None:
    fake_dock_autohide["enabled"] = False
    bridge = StripBridge()
    bridge.bind(
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        layout=_make_layout(mode="beside_dock"),
        collapsed=False,
    )

    bridge.restore_dock_autohide()

    assert fake_dock_autohide["enabled"] is False


def test_restore_dock_autohide_restores_on_shutdown(
    fake_dock_autohide: dict[str, bool],
) -> None:
    fake_dock_autohide["enabled"] = False
    bridge = StripBridge()
    bridge.bind(
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        layout=_make_layout(mode="full_width"),
        collapsed=False,
    )
    assert fake_dock_autohide["enabled"] is True

    bridge.restore_dock_autohide()

    assert fake_dock_autohide["enabled"] is False


def test_toggle_mode_without_bound_window_is_noop() -> None:
    StripBridge().toggle_mode()  # must not raise


def test_toggle_mode_flips_full_width_to_beside_dock_and_relaunches(
    fake_dock_autohide: dict[str, bool],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The strip's right-click "Switch mode" item -- the only way the mode ever changes now.

    Does not try to measure/apply the new layout live, in-process -- see
    `toggle_mode()`'s own docstring for why that turned out to be unreliable
    across several rounds of live debugging. Instead: restore the real Dock
    auto-hide setting, persist the new mode, and restart the whole process,
    reusing `start_strip()`'s own initial measurement.
    """
    bridge = StripBridge()
    bridge.bind(
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        layout=_make_layout(mode="full_width"),
        collapsed=False,
    )
    fake_config = MagicMock(strip_mode="full_width")
    monkeypatch.setattr(bridge_module, "Config", lambda: fake_config)
    popen_calls: list[list[str]] = []
    monkeypatch.setattr(
        bridge_module.subprocess,
        "Popen",
        lambda args, **_kwargs: popen_calls.append(args),
    )

    bridge.toggle_mode()

    assert fake_config.strip_mode == "beside_dock"
    fake_config.save.assert_called_once()
    assert len(popen_calls) == 1
    assert popen_calls[0][-1] == "strip"
    assert "--auto-hide" not in popen_calls[0]


def test_toggle_mode_flips_beside_dock_to_full_width_and_relaunches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = StripBridge()
    bridge.bind(
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        layout=_make_layout(mode="beside_dock"),
        collapsed=False,
    )
    fake_config = MagicMock(strip_mode="beside_dock")
    monkeypatch.setattr(bridge_module, "Config", lambda: fake_config)
    popen_calls: list[list[str]] = []
    monkeypatch.setattr(
        bridge_module.subprocess,
        "Popen",
        lambda args, **_kwargs: popen_calls.append(args),
    )

    bridge.toggle_mode()

    assert fake_config.strip_mode == "full_width"
    fake_config.save.assert_called_once()
    assert len(popen_calls) == 1


def test_toggle_mode_restores_dock_autohide_before_relaunching(
    fake_dock_autohide: dict[str, bool],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The new process's own startup measurement needs the real Dock already un-hidden.

    Otherwise its first `compute_strip_layout(mode="beside_dock")` call would
    see the Dock still forced hidden by *this* process's "full_width"
    override and immediately fall back to "full_width" again.
    """
    bridge = StripBridge()
    bridge.bind(
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        layout=_make_layout(mode="full_width"),
        collapsed=False,
    )
    assert fake_dock_autohide["enabled"] is True  # forced on by bind()
    monkeypatch.setattr(bridge_module, "Config", MagicMock())
    monkeypatch.setattr(bridge_module.subprocess, "Popen", lambda *_a, **_kw: None)

    bridge.toggle_mode()

    assert fake_dock_autohide["enabled"] is False  # restored to the real original


def test_toggle_mode_preserves_collapsed_state_across_relaunch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = StripBridge()
    bridge.bind(
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        layout=_make_layout(mode="full_width"),
        collapsed=True,
    )
    monkeypatch.setattr(bridge_module, "Config", MagicMock())
    popen_calls: list[list[str]] = []
    monkeypatch.setattr(
        bridge_module.subprocess,
        "Popen",
        lambda args, **_kwargs: popen_calls.append(args),
    )

    bridge.toggle_mode()

    assert "--auto-hide" in popen_calls[0]


def test_toggle_mode_destroys_all_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    window, popup_window, picker_window, menu_window = (
        _FakeWindow(),
        _FakeWindow(),
        _FakeWindow(),
        _FakeWindow(),
    )
    bridge = StripBridge()
    bridge.bind(
        window,  # type: ignore[arg-type]
        popup_window,  # type: ignore[arg-type]
        picker_window,  # type: ignore[arg-type]
        menu_window,  # type: ignore[arg-type]
        layout=_make_layout(mode="full_width"),
        collapsed=False,
    )
    monkeypatch.setattr(bridge_module, "Config", MagicMock())
    monkeypatch.setattr(bridge_module.subprocess, "Popen", lambda *_a, **_kw: None)

    bridge.toggle_mode()

    window.destroy.assert_called_once()
    popup_window.destroy.assert_called_once()
    picker_window.destroy.assert_called_once()
    menu_window.destroy.assert_called_once()


def test_toggle_mode_does_not_overwrite_concurrent_config_edits(
    fake_dock_autohide: dict[str, bool],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Regression test: `toggle_mode()` must not clobber unrelated settings.

    `config` is the snapshot loaded once at process startup; `Config.save()`
    serializes the *entire* instance. Saving through that stale singleton
    would silently revert any other field the user edited in `config.yaml`
    on disk while the strip stayed running -- reproduced here by changing
    `sidebar_refresh_interval` on disk (simulating a concurrent edit) *after*
    binding the bridge, then confirming it survives a mode switch. Uses the
    real `Config`/`yaml` round-trip (not a mock) since the bug is in exactly
    that round-trip.
    """
    settings_path = tmp_path / "config.yaml"
    monkeypatch.setitem(Config.model_config, "yaml_file", settings_path)
    # Defense in depth: `Config.save()` now reads its write target from
    # `model_config["yaml_file"]` (patched above), but redirecting the
    # module-level `user_config_file` too means a future regression there
    # still can't reach the real on-disk config from this test -- see
    # `pyworkon.config.Config.save()`'s own docstring for why this matters.
    monkeypatch.setattr(config_module, "user_config_file", settings_path)
    settings_path.write_text(
        yaml.dump({"sidebar_refresh_interval": 5, "strip_mode": "full_width"}),
        encoding="utf-8",
    )
    bridge = StripBridge()
    bridge.bind(
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        layout=_make_layout(mode="full_width"),
        collapsed=False,
    )
    # Concurrent edit, made on disk while the strip is already running.
    settings_path.write_text(
        yaml.dump({"sidebar_refresh_interval": 30, "strip_mode": "full_width"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(bridge_module.subprocess, "Popen", lambda *_a, **_kw: None)

    bridge.toggle_mode()

    saved = yaml.safe_load(settings_path.read_text(encoding="utf-8"))
    assert saved["sidebar_refresh_interval"] == 30
    assert saved["strip_mode"] == "beside_dock"


def test_restore_dock_autohide_does_not_hang_forever_if_the_lock_is_stuck(
    fake_dock_autohide: dict[str, bool],
) -> None:
    """Regression test: shutdown must never hang on a permanently-stuck worker.

    A background `toggle_mode()` call can get stuck forever inside
    `update_layout()`'s `evaluate_js()` call if the windows are destroyed
    mid-call (e.g. "Quit strip" racing a menu-triggered toggle) -- the main
    thread's run loop that would eventually signal the pending callback back
    is already gone. That thread still holds `_dock_autohide_lock` the whole
    time it's stuck. Without a bounded timeout, `start_strip()`'s shutdown
    `finally: bridge.restore_dock_autohide()` would block on that same lock
    forever, and the process would never reach `os._exit(0)`.
    """
    fake_dock_autohide["enabled"] = False
    bridge = StripBridge()
    bridge.bind(
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        layout=_make_layout(mode="full_width"),
        collapsed=False,
    )
    assert fake_dock_autohide["enabled"] is True  # overridden on

    release_event = threading.Event()

    def hold_lock_forever() -> None:
        with bridge._dock_autohide_lock:
            release_event.wait(timeout=5)

    holder = threading.Thread(target=hold_lock_forever, daemon=True)
    holder.start()
    time.sleep(0.05)  # ensure the holder thread acquires the lock first

    start = time.monotonic()
    bridge.restore_dock_autohide(timeout=0.3)
    elapsed = time.monotonic() - start

    release_event.set()
    holder.join(timeout=2)

    assert elapsed < 1.0  # must not hang forever
    assert fake_dock_autohide["enabled"] is False  # restored anyway, best-effort


def _bind_with_fakes(
    bridge: StripBridge,
) -> tuple[_FakeWindow, _FakeWindow, _FakeWindow, _FakeWindow]:
    window = _FakeWindow()
    popup_window = _FakeWindow()
    picker_window = _FakeWindow()
    menu_window = _FakeWindow()
    bridge.bind(
        window,
        popup_window,
        picker_window,
        menu_window,
        layout=_make_layout(),
        collapsed=False,
    )  # type: ignore[arg-type]
    return window, popup_window, picker_window, menu_window


def test_quit_destroys_the_picker_window_too() -> None:
    bridge = StripBridge()
    _window, _popup_window, picker_window, _menu_window = _bind_with_fakes(bridge)

    bridge.quit()

    picker_window.destroy.assert_called_once()


def test_quit_destroys_the_menu_window_too() -> None:
    bridge = StripBridge()
    _window, _popup_window, _picker_window, menu_window = _bind_with_fakes(bridge)

    bridge.quit()

    menu_window.destroy.assert_called_once()


def test_open_project_picker_captures_the_frontmost_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = StripBridge()
    _bind_with_fakes(bridge)
    captured = object()
    monkeypatch.setattr(bridge_module, "capture_frontmost_app", lambda: captured)
    monkeypatch.setattr(bridge_module, "move_picker_window", lambda *_args: None)
    monkeypatch.setattr(bridge_module, "show_picker_window", lambda *_args: None)

    bridge.open_project_picker()

    assert bridge._picker_captured_app is captured


def test_open_project_picker_moves_and_shows_the_picker_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = StripBridge()
    _window, _popup_window, picker_window, _menu_window = _bind_with_fakes(bridge)
    monkeypatch.setattr(bridge_module, "capture_frontmost_app", lambda: None)
    move_calls: list[object] = []
    show_calls: list[object] = []
    monkeypatch.setattr(
        bridge_module,
        "move_picker_window",
        lambda native, _x, _y: move_calls.append(native),
    )
    monkeypatch.setattr(bridge_module, "show_picker_window", show_calls.append)

    bridge.open_project_picker()

    assert move_calls == [picker_window.native]
    assert show_calls == [picker_window.native]


def test_open_project_picker_syncs_the_toggle_button_to_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = StripBridge()
    window, _popup_window, _picker_window, _menu_window = _bind_with_fakes(bridge)
    monkeypatch.setattr(bridge_module, "capture_frontmost_app", lambda: None)
    monkeypatch.setattr(bridge_module, "move_picker_window", lambda *_args: None)
    monkeypatch.setattr(bridge_module, "show_picker_window", lambda *_args: None)

    bridge.open_project_picker()

    (script,) = window.evaluate_js.call_args[0]
    assert "__setPickerOpen(true)" in script


def test_close_project_picker_hides_and_reactivates_the_captured_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The explicit-close path (select a project, press Escape) must hand focus back."""
    bridge = StripBridge()
    _window, _popup_window, picker_window, _menu_window = _bind_with_fakes(bridge)
    captured = object()
    monkeypatch.setattr(bridge_module, "capture_frontmost_app", lambda: captured)
    monkeypatch.setattr(bridge_module, "move_picker_window", lambda *_args: None)
    monkeypatch.setattr(bridge_module, "show_picker_window", lambda *_args: None)
    hide_calls: list[object] = []
    reactivate_calls: list[object] = []
    monkeypatch.setattr(bridge_module, "hide_picker_window", hide_calls.append)
    monkeypatch.setattr(bridge_module, "reactivate_app", reactivate_calls.append)
    bridge.open_project_picker()

    bridge.close_project_picker()

    assert hide_calls == [picker_window.native]
    assert reactivate_calls == [captured]
    assert bridge._picker_captured_app is None


def test_close_project_picker_syncs_the_toggle_button_to_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = StripBridge()
    window, _popup_window, _picker_window, _menu_window = _bind_with_fakes(bridge)
    monkeypatch.setattr(bridge_module, "hide_picker_window", lambda *_args: None)
    monkeypatch.setattr(bridge_module, "reactivate_app", lambda *_args: None)

    bridge.close_project_picker()

    (script,) = window.evaluate_js.call_args[0]
    assert "__setPickerOpen(false)" in script


def test_on_picker_lost_focus_hides_without_reactivating_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The click-away path must NOT reactivate the captured app.

    Regression guard: the user's own click already made some *other* real
    app frontmost -- reactivating our stale captured app here would fight
    that fresh click and steal focus right back from whatever the user just
    clicked into.
    """
    bridge = StripBridge()
    _window, _popup_window, picker_window, _menu_window = _bind_with_fakes(bridge)
    captured = object()
    monkeypatch.setattr(bridge_module, "capture_frontmost_app", lambda: captured)
    monkeypatch.setattr(bridge_module, "move_picker_window", lambda *_args: None)
    monkeypatch.setattr(bridge_module, "show_picker_window", lambda *_args: None)
    hide_calls: list[object] = []
    reactivate_calls: list[object] = []
    monkeypatch.setattr(bridge_module, "hide_picker_window", hide_calls.append)
    monkeypatch.setattr(bridge_module, "reactivate_app", reactivate_calls.append)
    bridge.open_project_picker()

    bridge.on_picker_lost_focus()

    assert hide_calls == [picker_window.native]
    assert reactivate_calls == []
    assert bridge._picker_captured_app is None


def test_on_picker_lost_focus_syncs_the_toggle_button_to_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = StripBridge()
    window, _popup_window, _picker_window, _menu_window = _bind_with_fakes(bridge)
    monkeypatch.setattr(bridge_module, "hide_picker_window", lambda *_args: None)

    bridge.on_picker_lost_focus()

    (script,) = window.evaluate_js.call_args[0]
    assert "__setPickerOpen(false)" in script


def test_enter_project_calls_daemon_client(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _RecordingDaemonClient()
    monkeypatch.setattr(bridge_module, "DaemonClient", lambda: recorder)

    StripBridge().enter_project("github/owner/repo")

    assert recorder.calls == [("enter_project", "github/owner/repo")]


def test_enter_project_closes_the_picker(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _RecordingDaemonClient()
    monkeypatch.setattr(bridge_module, "DaemonClient", lambda: recorder)
    bridge = StripBridge()
    _window, _popup_window, picker_window, _menu_window = _bind_with_fakes(bridge)
    hide_calls: list[object] = []
    monkeypatch.setattr(bridge_module, "hide_picker_window", hide_calls.append)
    monkeypatch.setattr(bridge_module, "reactivate_app", lambda *_args: None)

    bridge.enter_project("github/owner/repo")

    assert hide_calls == [picker_window.native]
