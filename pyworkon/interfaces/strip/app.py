"""Slim strip dashboard: a frameless always-on-top bar docked at the screen bottom.

Replaces the macOS Dock (set the Dock to auto-hide) with a thin row of session
chips, rendered inside a WKWebView via pywebview. No HTTP server, no
WebSocket -- the daemon's `SUBSCRIBE` stream is pushed straight into the page
via `Window.evaluate_js()`, and chip clicks call back into Python through
pywebview's `js_api` bridge (`StripBridge`).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING
lazy import base64
lazy import contextlib
lazy import importlib.resources
lazy import json
lazy import os
lazy import threading

lazy import AppKit
lazy import webview

from pyworkon.daemon.client import DaemonClient, DaemonNotRunningError
from pyworkon.daemon.protocol import SidebarStatePayload
from pyworkon.interfaces.relay.icons import DASHBOARD_ICONS
from pyworkon.interfaces.strip.bridge import COLLAPSED_HEIGHT, STRIP_HEIGHT, StripBridge
from pyworkon.interfaces.strip.schema import to_strip_payload
lazy from pyworkon.interfaces.strip.dock_geometry import compute_strip_layout
lazy from pyworkon.interfaces.strip.native import (
    POPUP_MAX_HEIGHT,
    POPUP_MAX_WIDTH,
    POPUP_MIN_WIDTH,
    hide_from_dock,
    prepare_popup_window,
    prepare_window,
    resize_frame,
)

if TYPE_CHECKING:
    from webview import Window

    from pyworkon.interfaces.strip.dock_geometry import StripLayout, StripMode

STATIC_DIR = Path(__file__).parent / "static"
_RECONNECT_DELAY_SECS = 1.0
_ICONS_PLACEHOLDER = "/*__PYWORKON_ICONS__*/"
_FONT_PLACEHOLDER = "__PYWORKON_FONT_BASE64__"
_IS_POPUP_PLACEHOLDER = "__PYWORKON_IS_POPUP__"
_STRIP_MODE_PLACEHOLDER = "__PYWORKON_STRIP_MODE__"
_POPUP_MIN_WIDTH_PLACEHOLDER = "__PYWORKON_POPUP_MIN_WIDTH__"
_POPUP_MAX_WIDTH_PLACEHOLDER = "__PYWORKON_POPUP_MAX_WIDTH__"


def _font_base64() -> str:
    font_bytes = (
        importlib.resources
        .files("pyworkon.interfaces.relay")
        .joinpath("static", "fonts", "pyworkon-icons.woff2")
        .read_bytes()
    )
    return base64.b64encode(font_bytes).decode("ascii")


def _render_strip_html(*, is_popup: bool, mode: StripMode) -> str:
    """Render `strip.html`, shared by both the strip window and the popup window.

    `is_popup` controls which half of the page is active (see the
    `__PYWORKON_IS_POPUP__`-gated CSS/JS in `strip.html`) -- the strip window
    renders the chip row and drives the popup window externally; the popup
    window only ever renders its own `#popup` div, filling its entire
    (separate, fixed-size) native window. See `native.py`'s
    `prepare_popup_window()` for why the popup lives in its own window
    instead of growing the strip's.

    `mode` seeds the initial `body.beside-dock` CSS class (see
    `dock_geometry.StripLayout.mode`) -- `bridge.update_layout()` can still
    switch it later via `window.setStripMode()` if a screen change flips the
    mode mid-session.

    `POPUP_MIN_WIDTH`/`POPUP_MAX_WIDTH` are injected too, so `strip.html`'s
    own width measurement (`__showPopupFor()`) clamps to the exact same
    bounds `clamp_popup_width()` enforces authoritatively on the Python
    side, rather than a separately hardcoded, easy-to-drift-out-of-sync copy.
    """
    template = (STATIC_DIR / "strip.html").read_text(encoding="utf-8")
    template = template.replace(_ICONS_PLACEHOLDER, json.dumps(DASHBOARD_ICONS))
    template = template.replace(_FONT_PLACEHOLDER, _font_base64())
    template = template.replace(_IS_POPUP_PLACEHOLDER, "true" if is_popup else "false")
    template = template.replace(_STRIP_MODE_PLACEHOLDER, mode)
    template = template.replace(_POPUP_MIN_WIDTH_PLACEHOLDER, str(POPUP_MIN_WIDTH))
    return template.replace(_POPUP_MAX_WIDTH_PLACEHOLDER, str(POPUP_MAX_WIDTH))


def _initial_create_coords(layout: StripLayout, height: int) -> tuple[int, int]:
    """Convert `layout`'s absolute placement into `create_window(x=, y=)`'s own convention.

    `layout` uses absolute AppKit (bottom-left-origin) coordinates.
    Confirmed by reading `webview/platforms/cocoa.py`: unlike `native.py`'s
    `resize_frame()` (which calls `NSMakeRect` directly with true, absolute
    AppKit coordinates), `create_window(x=, y=)` goes through pywebview's own
    `move()` on window creation, which treats `(x, y)` as **screen-relative,
    top-down** (`y=0` is that screen's own top edge, increasing downward) --
    `flipped_y = screen.size.height - y`, then
    `setFrameTopLeftPoint_(screen.origin + (x, flipped_y))`. The strip window
    is always meant to sit flush with `layout.screen`'s bottom edge
    (`layout.y == layout.screen.y`), so solving for `(x, y)` that reproduces
    `layout.x`/`layout.screen.y` after that transform reduces to:
    `create_x = layout.x - layout.screen.x`, `create_y = screen.height - height`.

    This only matters for the strip window's *initial* placement -- the
    immediately following `resize_frame()` call in `_finalize_native_window()`
    sets the window's real, final frame directly via `NSMakeRect`, bypassing
    this conversion entirely. Getting this wrong would only show up as a
    transient, incorrectly-placed flash before that correction, not a lasting
    bug -- but it's easy to get right, so there's no reason to leave it wrong.
    """
    screen = layout.screen
    create_x = round(layout.x - screen.x)
    create_y = round(screen.height - height)
    return create_x, create_y


def _build_windows(
    bridge: StripBridge, *, layout: StripLayout, auto_hide: bool
) -> tuple[Window, Window]:
    """Create the strip's pywebview window and its separate hover-popup window.

    `focus=False` is load-bearing, not a default left alone, for *both*
    windows: pywebview's own `WindowHost.canBecomeKeyWindow`
    (`webview/platforms/cocoa.py`) returns exactly this `focus` value, so
    `focus=False` makes a window structurally unable to ever become key --
    not through our own code, not through pywebview's own
    `first_show()`/`show()` calls, and not through a real user click. Becoming
    key diverts keyboard input to that window regardless of whether its owning
    app is active, which is what silently stole keystrokes away from whatever
    app (e.g. a terminal) the user was actually working in on every chip
    click, back when this was `focus=True` plus a
    `NSWindowStyleMaskNonactivatingPanel` style mask (see `native.py`'s
    `prepare_window()`). Ordinary clicks still reach the page normally even
    with `focus=False`, since `WKWebView` overrides `acceptsFirstMouse:` to
    return `YES` regardless of key status -- only continuous hover tracking
    needs key status, which `hover_monitor.py` already works around.

    The popup is a second, separate window (not part of the strip's own,
    resizable frame) -- see `native.py`'s `prepare_popup_window()` for why: a
    frame-by-frame screen recording confirmed growing the strip's own window
    to make room for the popup made it briefly, fully transparent (the
    desktop showed through) during the resize, and nothing on the native or
    CSS side fixed that. A window that only ever moves and shows/hides, never
    resizes, sidesteps the problem instead.
    """
    height = COLLAPSED_HEIGHT if auto_hide else layout.height
    create_x, create_y = _initial_create_coords(layout, height)
    window = webview.create_window(
        "pyworkon-strip",
        html=_render_strip_html(is_popup=False, mode=layout.mode),
        js_api=bridge,
        screen=layout.screen,
        x=create_x,
        y=create_y,
        width=round(layout.width),
        height=height,
        frameless=True,
        easy_drag=False,
        on_top=True,
        transparent=True,
        vibrancy=False,
        focus=False,
        resizable=False,
        shadow=False,
        text_select=False,
    )
    if window is None:
        msg = "pywebview failed to create the strip window"
        raise RuntimeError(msg)
    popup_window = webview.create_window(
        "pyworkon-strip-popup",
        html=_render_strip_html(is_popup=True, mode=layout.mode),
        js_api=bridge,
        screen=layout.screen,
        # The popup's initial position is irrelevant -- it's always moved
        # (`hover_monitor.py`'s `resize_and_position_popup_window()`) before
        # it's ever shown, so a trivial screen-relative (0, 0) is fine; no
        # need for `_initial_create_coords()`'s conversion here.
        x=0,
        y=0,
        # Initial size is otherwise irrelevant -- `hover_monitor.py` always
        # resizes (to fit content, each dimension clamped between its own
        # `POPUP_MIN_*`/`POPUP_MAX_*` bounds) and repositions this window
        # before ever showing it, and it starts hidden
        # (`prepare_popup_window()`). `POPUP_MAX_WIDTH`/`POPUP_MAX_HEIGHT`
        # are just safe, large-enough-to-never-matter defaults.
        width=POPUP_MAX_WIDTH,
        height=POPUP_MAX_HEIGHT,
        frameless=True,
        easy_drag=False,
        on_top=True,
        transparent=True,
        vibrancy=False,
        focus=False,
        resizable=False,
        shadow=False,
        text_select=True,
    )
    if popup_window is None:
        msg = "pywebview failed to create the strip's popup window"
        raise RuntimeError(msg)
    bridge.bind(window, popup_window, layout=layout, collapsed=auto_hide)
    return window, popup_window


def _finalize_native_window(
    window: Window, popup_window: Window, layout: StripLayout, *, height: int
) -> None:
    """One-time native setup for both windows, then an initial strip resize."""
    with contextlib.suppress(Exception):
        native = window.native
        if native is not None:
            prepare_window(native)
            resize_frame(native, layout.x, layout.y, layout.width, height)
    with contextlib.suppress(Exception):
        popup_native = popup_window.native
        if popup_native is not None:
            prepare_popup_window(popup_native)
    hide_from_dock()


def _run_daemon_session(window: Window, popup_window: Window) -> None:
    client = DaemonClient()
    try:
        client.connect()
    except DaemonNotRunningError, ConnectionError, OSError:
        return
    try:
        for resp in client.subscribe(["state"], full=True):
            if isinstance(resp.data, SidebarStatePayload):
                payload = to_strip_payload(resp.data)
                script = f"updateState({payload.model_dump_json()})"
                window.evaluate_js(script)
                popup_window.evaluate_js(script)
    except ConnectionError, OSError:
        pass
    finally:
        client.close()


def _watch_screen_changes(bridge: StripBridge) -> None:
    """Recompute and re-apply the strip's layout whenever the screen setup changes.

    Covers external-monitor connect/disconnect and the Dock resizing or
    moving -- `NSApplicationDidChangeScreenParametersNotification` fires for
    both (confirmed empirically: toggling Dock auto-hide alone changes
    `visibleFrame`, which triggers it). `NSNotificationCenter` delivers to a
    block-based observer **synchronously, on whatever thread posts it** --
    for this particular notification, that's AppKit's main thread. That
    matters because `bridge.update_layout()` calls `Window.evaluate_js()`,
    which pywebview implements as `AppHelper.callAfter(eval); semaphore
    .acquire()` (see `webview/platforms/cocoa.py`) -- a blocking wait for a
    callback that can only run once the main thread's run loop is free to
    process it. Calling that *from* the main thread is a guaranteed
    deadlock: the thread blocks on the semaphore and can never get back to
    its own run loop to unblock itself. `hover_monitor.py`'s poll thread
    gets this right by construction (it's never the main thread); this
    callback isn't, so the actual update work is handed off to a plain
    background thread instead of running inline.

    macOS can post this notification more than once for a single hardware
    change, each spawning its own background thread here -- `StripBridge
    .recompute_and_apply_layout()` serializes the whole restore/measure/
    apply sequence internally so concurrent threads can't interleave and
    corrupt the remembered Dock auto-hide setting.

    **The toggle itself is also exactly the kind of change this notification
    fires for** -- `recompute_and_apply_layout()` can toggle the real Dock
    auto-hide setting up to twice per call (restore the user's original
    value, then re-apply the override for "full_width"), and each real
    toggle changes `visibleFrame`, posting *another* notification. An earlier
    version suppressed any notification arriving within a fixed time window
    of the last one -- that's wrong in both directions: a slow recompute
    (e.g. a sluggish `osascript` call) can let its own self-generated
    notification land *outside* the window, restarting the whole cycle; and a
    genuinely new external event landing *inside* the window (two real
    changes in quick succession, e.g. swapping which external monitor is
    plugged in) was silently dropped with no trailing recompute, leaving the
    strip's geometry stale until some unrelated third event happened to come
    along. A `busy`/`pending` pair fixes both, independent of timing: while a
    recompute is in flight, *any* further notification (self-generated or
    real) only sets `pending` instead of starting a second thread; once the
    in-flight recompute returns, it immediately loops and runs exactly one
    more time if `pending` was set, then stops -- coalescing however many
    notifications arrived during the run into a single trailing recompute
    that reflects the latest state, rather than dropping them. `_on_screen_
    change` runs synchronously on the main thread (see above) but `_run_
    recompute` doesn't, so the shared state is a dict guarded by `lock`.
    """
    lock = threading.Lock()
    state = {"busy": False, "pending": False}

    def _run_recompute() -> None:
        while True:
            bridge.recompute_and_apply_layout(full_width_height=STRIP_HEIGHT)
            with lock:
                if not state["pending"]:
                    state["busy"] = False
                    return
                state["pending"] = False

    def _on_screen_change(_notification: object) -> None:
        with lock:
            if state["busy"]:
                state["pending"] = True
                return
            state["busy"] = True
        threading.Thread(target=_run_recompute, kwargs={}, daemon=True).start()

    AppKit.NSNotificationCenter.defaultCenter().addObserverForName_object_queue_usingBlock_(
        "NSApplicationDidChangeScreenParametersNotification",
        None,
        None,
        _on_screen_change,
    )


def _listen_daemon(
    window: Window,
    popup_window: Window,
    bridge: StripBridge,
    layout: StripLayout,
    height: int,
) -> None:
    """Entry point for `webview.start()`'s background thread.

    This thread is started before pywebview's own `create_window()` calls on
    the main thread, so neither window may be shown yet -- wait for both
    `shown` events before touching their frames, or our own positioning would
    race pywebview's initial placement and could be clobbered by it.
    """
    window.events.shown.wait(15)
    popup_window.events.shown.wait(15)
    _finalize_native_window(window, popup_window, layout, height=height)
    _watch_screen_changes(bridge)
    while True:
        _run_daemon_session(window, popup_window)
        time.sleep(_RECONNECT_DELAY_SECS)


def start_strip(*, auto_hide: bool = False) -> None:
    """Launch the strip window and block until it's closed.

    Computes the strip's layout once at startup (`dock_geometry
    .compute_strip_layout()`): beside the Dock's icon area when there's
    enough room, otherwise falling back to the original full-width behavior.
    Only the full-width fallback auto-hides the real Dock for the strip's
    lifetime -- it occupies the same screen real estate there, so leaving the
    Dock shown would make the two visibly overlap -- restoring whatever the
    user had set beforehand on exit. In beside-dock mode, the Dock stays
    exactly as the user has it. `StripBridge` owns this for the whole
    session, not just at startup/shutdown -- see `bridge.py`'s
    `_sync_dock_autohide_for_mode()` -- since a runtime mode change (e.g. an
    external monitor a "beside_dock" layout was anchored to gets
    disconnected) needs the exact same management applied again.
    """
    layout = compute_strip_layout(full_width_height=STRIP_HEIGHT)
    bridge = StripBridge()
    try:
        window, popup_window = _build_windows(
            bridge, layout=layout, auto_hide=auto_hide
        )
        height = COLLAPSED_HEIGHT if auto_hide else layout.height
        webview.start(
            _listen_daemon,
            [window, popup_window, bridge, layout, height],
            debug=False,
        )
    finally:
        # A bounded timeout, not the default indefinite wait -- see
        # `restore_dock_autohide()`'s own docstring for why a stuck
        # background recompute can hold `_dock_autohide_lock` forever once
        # its windows are gone, and why shutdown must not hang on it too.
        bridge.restore_dock_autohide(timeout=2.0)
    # `webview.start()`'s own background thread (running `_listen_daemon`'s
    # `while True` daemon-subscribe loop) is never marked `daemon=True` --
    # that's pywebview's own thread creation, outside our control -- so once
    # the window closes (e.g. via "Quit strip"), the interpreter would
    # otherwise wait forever for that thread to finish on its own, which it
    # never does. Force the process to actually end here.
    os._exit(0)
