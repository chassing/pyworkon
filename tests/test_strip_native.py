"""Tests for the strip's direct AppKit window control."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pyworkon.interfaces.strip import native as native_module
from pyworkon.interfaces.strip.native import (
    POPUP_MAX_HEIGHT,
    POPUP_MIN_HEIGHT,
    clamp_popup_height,
    hide_from_dock,
    hide_popup_window,
    prepare_popup_window,
    prepare_window,
    resize_and_position_popup_window,
    resize_frame,
    show_popup_window,
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


@pytest.fixture
def fake_appkit(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Avoid invoking real `NSApplication` methods (e.g. actually activating the test process)."""
    fake = MagicMock()
    monkeypatch.setattr(native_module, "AppKit", fake)
    return fake


def test_prepare_window_never_activates_the_app(fake_appkit: MagicMock) -> None:
    """The strip must never steal focus -- `activateIgnoringOtherApps_` would."""
    native = MagicMock()

    prepare_window(native)

    app = fake_appkit.NSApplication.sharedApplication.return_value
    app.activateIgnoringOtherApps_.assert_not_called()


def test_prepare_window_orders_front_without_ever_keying(
    fake_appkit: MagicMock,
) -> None:
    """The window must never become key -- not even via this one-time call.

    `focus=False` (passed to `webview.create_window()` in `app.py`) already
    makes pywebview's own `canBecomeKeyWindow` return `False` unconditionally,
    so this uses `orderFrontRegardless()` (show, don't key) instead of
    `makeKeyAndOrderFront_()`.
    """
    native = MagicMock()

    prepare_window(native)

    native.orderFrontRegardless.assert_called_once_with()
    native.makeKeyAndOrderFront_.assert_not_called()


def test_prepare_window_accepts_mouse_moved_events(fake_appkit: MagicMock) -> None:
    native = MagicMock()

    prepare_window(native)

    (accepts,) = native.setAcceptsMouseMovedEvents_.call_args[0]
    assert accepts is True


def test_prepare_window_uses_plain_borderless_style_mask(
    fake_appkit: MagicMock,
) -> None:
    """Plain borderless (0) -- no nonactivating-panel bit needed anymore.

    That bit's only purpose was letting a real click key the window (without
    activating the app); now that the window can never become key at all
    (`focus=False`, see `app.py`), it's unnecessary.
    """
    native = MagicMock()

    prepare_window(native)

    native.setStyleMask_.assert_called_once_with(0)


def test_prepare_window_keeps_window_on_all_spaces(fake_appkit: MagicMock) -> None:
    native = MagicMock()

    prepare_window(native)

    native.setCollectionBehavior_.assert_called_once_with((1 << 0) | (1 << 4))


def test_prepare_window_sets_level_below_the_dock(fake_appkit: MagicMock) -> None:
    native = MagicMock()

    prepare_window(native)

    # The real Dock runs at CG window layer 20; one below lets it cover the
    # strip when revealed instead of the strip always covering the Dock.
    native.setLevel_.assert_called_once_with(19)


def test_prepare_window_never_touches_the_frame(fake_appkit: MagicMock) -> None:
    native = MagicMock()

    prepare_window(native)

    native.setFrame_display_.assert_not_called()


def test_resize_frame_sets_requested_rect() -> None:
    native = MagicMock()

    resize_frame(native, 0, 0, 1920, 56)

    frame, redisplay = native.setFrame_display_.call_args[0]
    assert (frame.origin.x, frame.origin.y, frame.size.width, frame.size.height) == (
        0,
        0,
        1920,
        56,
    )
    # `display=True`: deferred redisplay was tried and reverted -- it also
    # deferred the WKWebView's own relayout, reopening a stale-chip-rect race.
    # See `resize_frame()`'s docstring.
    assert redisplay is True


def test_resize_frame_respects_a_non_zero_origin() -> None:
    """E.g. beside-dock mode, or a non-primary screen -- not just `(0, 0)`."""
    native = MagicMock()

    resize_frame(native, 3840, 518, 1800, 10)

    frame, _redisplay = native.setFrame_display_.call_args[0]
    assert (frame.origin.x, frame.origin.y, frame.size.width, frame.size.height) == (
        3840,
        518,
        1800,
        10,
    )


def test_resize_frame_never_touches_style_mask() -> None:
    """Re-applying the style mask on every resize reset WKWebView's transparency once."""
    native = MagicMock()

    resize_frame(native, 0, 0, 1920, 56)

    native.setStyleMask_.assert_not_called()
    native.setCollectionBehavior_.assert_not_called()
    native.setLevel_.assert_not_called()


def test_hide_from_dock_sets_accessory_activation_policy(
    fake_appkit: MagicMock,
) -> None:
    hide_from_dock()

    app = fake_appkit.NSApplication.sharedApplication.return_value
    app.setActivationPolicy_.assert_called_once_with(1)


def test_prepare_popup_window_starts_hidden(fake_appkit: MagicMock) -> None:
    """Unlike the strip window, the popup starts hidden -- only a hovered chip shows it."""
    native = MagicMock()

    prepare_popup_window(native)

    native.orderOut_.assert_called_once_with(None)
    native.orderFrontRegardless.assert_not_called()


def test_prepare_popup_window_uses_plain_borderless_style_mask(
    fake_appkit: MagicMock,
) -> None:
    native = MagicMock()

    prepare_popup_window(native)

    native.setStyleMask_.assert_called_once_with(0)


def test_prepare_popup_window_keeps_window_on_all_spaces(
    fake_appkit: MagicMock,
) -> None:
    native = MagicMock()

    prepare_popup_window(native)

    native.setCollectionBehavior_.assert_called_once_with((1 << 0) | (1 << 4))


def test_prepare_popup_window_sets_level_below_the_dock(
    fake_appkit: MagicMock,
) -> None:
    native = MagicMock()

    prepare_popup_window(native)

    native.setLevel_.assert_called_once_with(19)


def test_prepare_popup_window_never_touches_the_frame(
    fake_appkit: MagicMock,
) -> None:
    native = MagicMock()

    prepare_popup_window(native)

    native.setFrameOrigin_.assert_not_called()
    native.setFrame_display_.assert_not_called()


def test_resize_and_position_popup_window_sets_frame() -> None:
    native = MagicMock()

    resize_and_position_popup_window(native, 120.0, 2104.0, 360.0, 180.0)

    frame, redisplay = native.setFrame_display_.call_args[0]
    assert (frame.origin.x, frame.origin.y, frame.size.width, frame.size.height) == (
        120.0,
        2104.0,
        360.0,
        180.0,
    )
    assert redisplay is True


def test_resize_and_position_popup_window_never_shows_it() -> None:
    """Resizing and showing are deliberately separate calls.

    Resizing always happens first, while the window is still hidden -- no
    visible flash risk, unlike the strip window's own resize.
    """
    native = MagicMock()

    resize_and_position_popup_window(native, 0.0, 0.0, 360.0, 180.0)

    native.orderFrontRegardless.assert_not_called()


def test_show_popup_window_orders_front_without_resizing() -> None:
    native = MagicMock()

    show_popup_window(native)

    native.orderFrontRegardless.assert_called_once_with()
    native.setFrame_display_.assert_not_called()


def test_hide_popup_window_orders_out() -> None:
    native = MagicMock()

    hide_popup_window(native)

    native.orderOut_.assert_called_once_with(None)


def test_clamp_popup_height_clamps_to_minimum() -> None:
    assert clamp_popup_height(10) == POPUP_MIN_HEIGHT


def test_clamp_popup_height_clamps_to_maximum() -> None:
    assert clamp_popup_height(10_000) == POPUP_MAX_HEIGHT


def test_clamp_popup_height_passes_through_values_in_range() -> None:
    assert clamp_popup_height(250) == 250
