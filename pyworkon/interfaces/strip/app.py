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

lazy import webview

from pyworkon.daemon.client import DaemonClient, DaemonNotRunningError
from pyworkon.daemon.protocol import SidebarStatePayload
from pyworkon.icons import DASHBOARD_ICONS
from pyworkon.interfaces.strip.bridge import (
    COLLAPSED_HEIGHT,
    STRIP_HEIGHT,
    StripBridge,
    recover_dock_autohide_from_unclean_shutdown,
)
from pyworkon.interfaces.strip.schema import to_strip_payload
lazy from pyworkon.config import config
lazy from pyworkon.interfaces.strip.dock_geometry import compute_strip_layout
lazy from pyworkon.interfaces.strip.hotkey import register_hotkey
lazy from pyworkon.interfaces.strip.native import (
    MENU_WIDTH,
    PICKER_HEIGHT,
    PICKER_WIDTH,
    POPUP_MAX_HEIGHT,
    POPUP_MAX_WIDTH,
    POPUP_MIN_HEIGHT,
    POPUP_MIN_WIDTH,
    hide_from_dock,
    prepare_menu_window,
    prepare_picker_window,
    prepare_popup_window,
    prepare_window,
    resize_frame,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from webview import Window

    from pyworkon.interfaces.strip.dock_geometry import StripLayout, StripMode
    from pyworkon.interfaces.strip.schema import StripStatePayload

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


def _render_picker_html() -> str:
    """Render `picker.html` -- the "open a new session" project picker's own page.

    A genuinely separate static file, not a third mode on `strip.html`: the
    strip and hover-popup share that file because their content overlaps
    heavily and neither ever receives keyboard events, but the picker's whole
    reason to exist is keyboard interaction (typing, arrow keys, Enter,
    Escape) that must never reach the other two windows. Needs the same
    icon/font injection as the strip (GitHub/GitLab marks, the embedded
    webfont) but none of its `is_popup`/`mode` placeholders, since this
    window has no shared-file gating to seed.
    """
    template = (STATIC_DIR / "picker.html").read_text(encoding="utf-8")
    template = template.replace(_ICONS_PLACEHOLDER, json.dumps(DASHBOARD_ICONS))
    return template.replace(_FONT_PLACEHOLDER, _font_base64())


def _render_menu_html() -> str:
    """Render `menu.html` -- the right-click context menu's own page.

    No icon/font injection needed, unlike `strip.html`/`picker.html`: the
    menu is plain text items only, built and passed in explicitly by
    `bridge.py`'s `show_context_menu()` -- there is no daemon state or
    Nerd Font glyph involved.
    """
    return (STATIC_DIR / "menu.html").read_text(encoding="utf-8")


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
) -> tuple[Window, Window, Window, Window]:
    """Create the strip's pywebview window and its three separate child windows.

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

    The picker is a *third* window, for the "open a new session" project
    picker -- and the one deliberate exception to "never take focus": it
    passes `focus=True` (not `focus=False`) so it can host a real, typed
    search box. See `native.py`'s `prepare_picker_window()` and `bridge.py`'s
    `open_project_picker()`/`close_project_picker()` for how focus is handed
    back the instant it closes.

    The menu is a *fourth* window, for the right-click context menu -- see
    `native.py`'s `prepare_menu_window()` for why it needs its own window
    (same reasoning as the popup) and why it stays `focus=False` (unlike the
    picker -- a context menu has no actual need of real keyboard focus, and
    making it key would risk the exact keystroke-stealing regression this
    whole function's own docstring describes).
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
    picker_window = webview.create_window(
        "pyworkon-strip-picker",
        html=_render_picker_html(),
        js_api=bridge,
        screen=layout.screen,
        # Position is irrelevant at creation time -- always moved
        # (`bridge.py`'s `open_project_picker()`) before it's ever shown, and
        # it starts hidden (`prepare_picker_window()`).
        x=0,
        y=0,
        width=PICKER_WIDTH,
        height=PICKER_HEIGHT,
        frameless=True,
        easy_drag=False,
        on_top=True,
        transparent=True,
        vibrancy=False,
        focus=True,
        resizable=False,
        shadow=False,
        text_select=True,
    )
    if picker_window is None:
        msg = "pywebview failed to create the strip's project picker window"
        raise RuntimeError(msg)
    menu_window = webview.create_window(
        "pyworkon-strip-menu",
        html=_render_menu_html(),
        js_api=bridge,
        screen=layout.screen,
        # Position/size are irrelevant at creation time -- always moved and
        # resized (`bridge.py`'s `show_context_menu()`) before it's ever
        # shown, and it starts hidden (`prepare_menu_window()`).
        x=0,
        y=0,
        width=MENU_WIDTH,
        height=POPUP_MIN_HEIGHT,
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
    if menu_window is None:
        msg = "pywebview failed to create the strip's context menu window"
        raise RuntimeError(msg)
    bridge.bind(
        window,
        popup_window,
        picker_window,
        menu_window,
        layout=layout,
        collapsed=auto_hide,
    )
    return window, popup_window, picker_window, menu_window


def _finalize_native_window(
    window: Window,
    popup_window: Window,
    picker_window: Window,
    menu_window: Window,
    layout: StripLayout,
    *,
    height: int,
    on_picker_lost_focus: Callable[[], None],
) -> None:
    """One-time native setup for all four windows, then an initial strip resize."""
    with contextlib.suppress(Exception):
        native = window.native
        if native is not None:
            prepare_window(native)
            resize_frame(native, layout.x, layout.y, layout.width, height)
    with contextlib.suppress(Exception):
        popup_native = popup_window.native
        if popup_native is not None:
            prepare_popup_window(popup_native)
    with contextlib.suppress(Exception):
        picker_native = picker_window.native
        if picker_native is not None:
            prepare_picker_window(picker_native, on_picker_lost_focus)
    with contextlib.suppress(Exception):
        menu_native = menu_window.native
        if menu_native is not None:
            prepare_menu_window(menu_native)
    hide_from_dock()


def _push_state(
    window: Window,
    popup_window: Window,
    picker_window: Window,
    payload: StripStatePayload,
) -> None:
    script = f"updateState({payload.model_dump_json()})"
    window.evaluate_js(script)
    popup_window.evaluate_js(script)
    picker_window.evaluate_js(script)


def _run_daemon_session(
    window: Window, popup_window: Window, picker_window: Window
) -> None:
    client = DaemonClient()
    try:
        client.connect()
    except DaemonNotRunningError, ConnectionError, OSError:
        return
    try:
        for resp in client.subscribe(["state"], full=True):
            if isinstance(resp.data, SidebarStatePayload):
                _push_state(
                    window, popup_window, picker_window, to_strip_payload(resp.data)
                )
    except ConnectionError, OSError:
        pass
    finally:
        client.close()


def _listen_daemon(
    window: Window,
    popup_window: Window,
    picker_window: Window,
    menu_window: Window,
    bridge: StripBridge,
    layout: StripLayout,
    height: int,
) -> None:
    """Entry point for `webview.start()`'s background thread.

    This thread is started before pywebview's own `create_window()` calls on
    the main thread, so none of the four windows may be shown yet -- wait
    for every `shown` event before touching their frames, or our own
    positioning would race pywebview's initial placement and could be
    clobbered by it.

    Also registers `config.strip_hotkey` (default `ctrl+option+space`) as a
    global macOS hotkey toggling the project picker -- see `hotkey.py` for
    why this is Carbon-based rather than an `NSEvent` monitor. Wrapped in
    `contextlib.suppress(Exception)` so a malformed `strip_hotkey` config
    value (or `""`, disabling it) can't take down this whole background
    thread and silently kill the daemon-subscribe loop below it.
    """
    window.events.shown.wait(15)
    popup_window.events.shown.wait(15)
    picker_window.events.shown.wait(15)
    menu_window.events.shown.wait(15)
    _finalize_native_window(
        window,
        popup_window,
        picker_window,
        menu_window,
        layout,
        height=height,
        on_picker_lost_focus=bridge.on_picker_lost_focus,
    )
    if config.strip_hotkey:
        with contextlib.suppress(Exception):
            register_hotkey(config.strip_hotkey, bridge.toggle_project_picker)
    while True:
        _run_daemon_session(window, popup_window, picker_window)
        time.sleep(_RECONNECT_DELAY_SECS)


def start_strip(*, auto_hide: bool = False) -> None:
    """Launch the strip window and block until it's closed.

    Computes the strip's layout once at startup for whichever mode
    `config.strip_mode` persists (`"full_width"` by default) --
    `dock_geometry.compute_strip_layout()` no longer decides *between* modes
    on its own. An earlier design tried to automatically detect and
    continuously re-verify whether "beside_dock" was possible (watching for
    screen/wake/Dock-autohide changes and retrying measurement in the
    background) -- torn out after it proved impossible to make reliable
    against a real Thunderbolt dock's sleep/wake and monitor hotplug
    behavior (the Dock's own Accessibility state and auto-hide preference
    could not be measured consistently enough, no matter the retry schedule).
    The mode is now a plain, user-controlled setting: the strip's right-click
    context menu's "Switch mode" item (`StripBridge.toggle_mode()`) is the
    *only* way it ever changes, and it stays exactly as set -- through sleep,
    wake, monitor plug/unplug, anything -- until the user explicitly switches
    it again.

    Only "full_width" auto-hides the real Dock for the strip's lifetime -- it
    occupies the same screen real estate there, so leaving the Dock shown
    would make the two visibly overlap -- restoring whatever the user had set
    beforehand on exit. In "beside_dock" mode, the Dock stays exactly as the
    user has it.

    `recover_dock_autohide_from_unclean_shutdown()` runs first, before the
    very first `compute_strip_layout()` call -- see its own docstring for why
    a previous run's `SIGKILL`/crash while overriding the real Dock auto-hide
    setting must be cleaned up before anything else measures the Dock, not
    after.
    """
    recover_dock_autohide_from_unclean_shutdown()
    layout = compute_strip_layout(
        mode=config.strip_mode, full_width_height=STRIP_HEIGHT
    )
    bridge = StripBridge()
    try:
        window, popup_window, picker_window, menu_window = _build_windows(
            bridge, layout=layout, auto_hide=auto_hide
        )
        height = COLLAPSED_HEIGHT if auto_hide else layout.height
        webview.start(
            _listen_daemon,
            [
                window,
                popup_window,
                picker_window,
                menu_window,
                bridge,
                layout,
                height,
            ],
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
