"""Tests for the strip's JS-callable Python bridge."""

from __future__ import annotations

import threading
import time
from typing import Self
from unittest.mock import MagicMock

import pytest

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
def fake_dock_autohide(monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    """Fake out real `osascript`/System Events calls.

    `bind()`'s default "full_width" layout would otherwise toggle the
    *real* Dock auto-hide on every test run, which must never happen
    outside an explicit, asked-for real-environment test.
    """
    state = {"enabled": False}
    monkeypatch.setattr(
        bridge_module, "_dock_autohide_enabled", lambda: state["enabled"]
    )

    def _set(*, enabled: bool) -> None:
        state["enabled"] = enabled

    monkeypatch.setattr(bridge_module, "_set_dock_autohide", _set)
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

    bridge.bind(window, popup_window, layout=_make_layout(), collapsed=False)  # type: ignore[arg-type]

    fake_hover_monitor.assert_called_once_with(window, popup_window)
    fake_hover_monitor.return_value.start.assert_called_once()


def test_update_chip_rects_forwards_to_the_hover_monitor(
    fake_hover_monitor: MagicMock,
) -> None:
    bridge = StripBridge()
    window = _FakeWindow()
    popup_window = _FakeWindow()
    bridge.bind(window, popup_window, layout=_make_layout(), collapsed=False)  # type: ignore[arg-type]
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
    bridge.bind(window, popup_window, layout=_make_layout(), collapsed=False)  # type: ignore[arg-type]

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
    bridge.bind(window, popup_window, layout=layout, collapsed=False)  # type: ignore[arg-type]

    bridge.toggle_collapse()
    assert _last_frame_rect(window) == (0, 0, 1920, COLLAPSED_HEIGHT)

    bridge.toggle_collapse()
    assert _last_frame_rect(window) == (0, 0, 1920, STRIP_HEIGHT)


def test_toggle_collapse_hides_the_popup_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Collapsing mid-hover shouldn't leave the popup floating above a hidden strip."""
    hide_calls: list[object] = []
    monkeypatch.setattr(bridge_module, "hide_popup_window", hide_calls.append)
    bridge = StripBridge()
    window = _FakeWindow()
    popup_window = _FakeWindow()
    bridge.bind(window, popup_window, layout=_make_layout(), collapsed=False)  # type: ignore[arg-type]

    bridge.toggle_collapse()

    assert hide_calls == [popup_window.native]


def test_update_layout_resizes_the_strip_to_the_new_placement() -> None:
    bridge = StripBridge()
    window = _FakeWindow()
    popup_window = _FakeWindow()
    bridge.bind(window, popup_window, layout=_make_layout(), collapsed=False)  # type: ignore[arg-type]

    bridge.update_layout(
        _make_layout(mode="beside_dock", x=2694, y=0, width=1146, height=84)
    )

    assert _last_frame_rect(window) == (2694, 0, 1146, 84)


def test_update_layout_keeps_the_collapsed_height() -> None:
    """A screen change mid-collapse shouldn't un-collapse the strip."""
    bridge = StripBridge()
    window = _FakeWindow()
    popup_window = _FakeWindow()
    bridge.bind(window, popup_window, layout=_make_layout(), collapsed=True)  # type: ignore[arg-type]

    bridge.update_layout(
        _make_layout(mode="beside_dock", x=2694, y=0, width=1146, height=84)
    )

    assert _last_frame_rect(window) == (2694, 0, 1146, COLLAPSED_HEIGHT)


def test_update_layout_pushes_the_new_mode_to_both_windows() -> None:
    bridge = StripBridge()
    window = _FakeWindow()
    popup_window = _FakeWindow()
    bridge.bind(window, popup_window, layout=_make_layout(), collapsed=False)  # type: ignore[arg-type]

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
        layout=_make_layout(mode="full_width"),
        collapsed=False,
    )
    assert fake_dock_autohide["enabled"] is True  # overridden on

    bridge.update_layout(_make_layout(mode="beside_dock"))

    assert fake_dock_autohide["enabled"] is False  # restored to the original off


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
        layout=_make_layout(mode="full_width"),
        collapsed=False,
    )
    assert fake_dock_autohide["enabled"] is True

    bridge.restore_dock_autohide()

    assert fake_dock_autohide["enabled"] is False


def test_recompute_and_apply_layout_serializes_concurrent_calls(
    fake_dock_autohide: dict[str, bool],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for a real race across concurrent screen-change threads.

    Without serializing the whole restore -> measure -> apply sequence, two
    threads can both read "no override yet" before either writes it, each
    capturing the *other's* in-flight change as if it were the user's real
    original Dock setting -- an original `False` could come back as `True`
    after "restoration". Proven here directly: `_dock_autohide_enabled()` is
    made deliberately slow, and concurrently-launched threads must never
    have more than one of them inside the critical section at once.
    """
    bridge = StripBridge()
    bridge.bind(
        _FakeWindow(),  # type: ignore[arg-type]
        _FakeWindow(),  # type: ignore[arg-type]
        layout=_make_layout(mode="beside_dock"),
        collapsed=False,
    )

    active = 0
    max_concurrent = 0
    counter_lock = threading.Lock()

    def slow_enabled() -> bool:
        nonlocal active, max_concurrent
        with counter_lock:
            active += 1
            max_concurrent = max(max_concurrent, active)
        time.sleep(0.05)
        with counter_lock:
            active -= 1
        return fake_dock_autohide["enabled"]

    monkeypatch.setattr(bridge_module, "_dock_autohide_enabled", slow_enabled)
    monkeypatch.setattr(
        bridge_module,
        "compute_strip_layout",
        lambda **_kwargs: _make_layout(mode="full_width"),
    )

    threads = [
        threading.Thread(
            target=bridge.recompute_and_apply_layout, kwargs={"full_width_height": 56}
        )
        for _ in range(5)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert max_concurrent == 1
    # Only the *first* thread to actually run should have captured anything
    # -- every later thread finds an override already in place and does
    # nothing further, exactly as `_sync_dock_autohide_for_mode()` intends.
    assert fake_dock_autohide["enabled"] is True


def test_restore_dock_autohide_does_not_hang_forever_if_the_lock_is_stuck(
    fake_dock_autohide: dict[str, bool],
) -> None:
    """Regression test: shutdown must never hang on a permanently-stuck worker.

    A background `recompute_and_apply_layout()` call can get stuck forever
    inside `update_layout()`'s `evaluate_js()` call if the windows are
    destroyed mid-call (e.g. "Quit strip" racing a screen-change recompute)
    -- the main thread's run loop that would eventually signal the pending
    callback back is already gone. That thread still holds
    `_dock_autohide_lock` the whole time it's stuck. Without a bounded
    timeout, `start_strip()`'s shutdown `finally: bridge.restore_dock
    _autohide()` would block on that same lock forever, and the process
    would never reach `os._exit(0)`.
    """
    fake_dock_autohide["enabled"] = False
    bridge = StripBridge()
    bridge.bind(
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
