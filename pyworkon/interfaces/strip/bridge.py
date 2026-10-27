"""JS-callable Python API exposed to the strip webview via pywebview's `js_api`.

Session-action wrappers mirror `interfaces/tui/base.py`'s `BaseApp` static
methods -- duplicated rather than imported, since the strip is an independent
interface (like `relay`) that has no dependency on Textual.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
lazy import contextlib
lazy import json
lazy import subprocess
lazy import sys
lazy import threading
lazy import webbrowser

lazy from PyObjCTools import AppHelper

from pyworkon.config import user_cache_dir
from pyworkon.daemon.client import DaemonClient, DaemonNotRunningError
lazy from pyworkon.config import Config
lazy from pyworkon.interfaces.strip.hover_monitor import HoverMonitor
lazy from pyworkon.interfaces.strip.native import (
    MENU_WIDTH,
    PICKER_WIDTH,
    capture_frontmost_app,
    hide_menu_window,
    hide_picker_window,
    hide_popup_window,
    move_picker_window,
    reactivate_app,
    resize_and_position_menu_window,
    resize_frame,
    show_menu_window,
    show_picker_window,
)

if TYPE_CHECKING:
    from webview import Window

    from pyworkon.interfaces.strip.dock_geometry import StripLayout, StripMode

STRIP_HEIGHT = 56
COLLAPSED_HEIGHT = 10
# Gap between the picker window and the strip's top/right edges it's anchored
# to -- mirrors the small screen-edge margins `hover_monitor.py` uses for the
# same kind of "float just above/beside something" positioning.
_PICKER_SCREEN_MARGIN = 8.0
# Same idea for the context menu -- keeps a right-click near the screen's
# right edge from pushing part of the fixed-width menu off-screen.
_MENU_SCREEN_MARGIN = 8.0

_OSASCRIPT = "/usr/bin/osascript"
# Crash-safe record of the Dock auto-hide value to restore -- see
# `recover_dock_autohide_from_unclean_shutdown()` for why this can't just
# live in memory (`StripBridge._dock_autohide_overridden_from`) alone.
_DOCK_AUTOHIDE_ORIGINAL_MARKER = user_cache_dir / "strip_dock_autohide_original"


def _dock_autohide_enabled() -> bool:
    result = subprocess.run(
        [
            _OSASCRIPT,
            "-e",
            'tell application "System Events" to get autohide of dock preferences',
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() == "true"


def _set_dock_autohide(*, enabled: bool) -> None:
    """Toggle the real macOS Dock's auto-hide, so the strip doesn't overlap it.

    Uses System Events rather than `defaults write ... && killall Dock` so the
    Dock doesn't visibly flash/restart.
    """
    value = "true" if enabled else "false"
    subprocess.run(
        [
            _OSASCRIPT,
            "-e",
            f'tell application "System Events" to set autohide of dock preferences to {value}',
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def recover_dock_autohide_from_unclean_shutdown() -> None:
    """Undo a previous run's un-restored Dock auto-hide override, if any.

    Must be called once, from `start_strip()`, *before* the first
    `compute_strip_layout()` call. `StripBridge._sync_dock_autohide_for_mode()`
    only knows how to restore the user's real original Dock auto-hide value
    while its own `_dock_autohide_overridden_from` is non-`None` -- in-memory
    state that's gone the instant the process exits, cleanly or not. A clean
    exit ("Quit strip") always reaches `start_strip()`'s `finally:` block,
    which restores it. A `SIGKILL` (`pkill -9`, a crash, the OS going down)
    does not -- Python's `finally:` blocks never run, so the real Dock is left
    auto-hidden exactly as "full_width" mode forces it.

    Confirmed via live debug logging to be a real, reproducible, **permanent**
    bug, not just a cosmetic leftover: the next launch's very first
    `_sync_dock_autohide_for_mode("full_width")` call (if `config.strip_mode`
    is persisted as "full_width", which it would be right after a session
    that was stuck there) sees `_dock_autohide_overridden_from is None` (a
    brand new `StripBridge`) and captures *the Dock's current, already-
    forced-true* setting via `_dock_autohide_enabled()` as if it were the
    user's genuine original preference. From that point on, every
    `restore_dock_autohide()` call "restores" to that same wrong (`true`)
    value -- which is also why this produces *zero* visible Dock flashing:
    every toggle is true -> true, never actually showing the Dock. This class
    of bug cannot be fixed by retrying -- it has to be prevented from
    poisoning the baseline in the first place.

    The fix: persist the *real* original value to `_DOCK_AUTOHIDE_ORIGINAL
    _MARKER` the moment it's first captured (see `_sync_dock_autohide_for_mode()`),
    remove it the moment it's cleanly restored. Finding it still present at
    the next launch means the previous run never got that far -- use the
    persisted value (not the Dock's current, possibly-still-forced setting)
    to restore the real preference right now, before anything else runs.
    """
    if not _DOCK_AUTOHIDE_ORIGINAL_MARKER.exists():
        return
    original = _DOCK_AUTOHIDE_ORIGINAL_MARKER.read_text().strip() == "true"
    _set_dock_autohide(enabled=original)
    _DOCK_AUTOHIDE_ORIGINAL_MARKER.unlink(missing_ok=True)


class StripBridge:
    """Session actions callable from the strip's JavaScript side."""

    def __init__(self) -> None:
        self._window: Window | None = None
        self._popup_window: Window | None = None
        self._picker_window: Window | None = None
        self._menu_window: Window | None = None
        self._layout: StripLayout | None = None
        self._collapsed = False
        self._hover_monitor: HoverMonitor | None = None
        # Whichever app was frontmost right before `open_project_picker()`
        # gave the picker real keyboard focus -- `None` whenever the picker
        # isn't currently open. See `close_project_picker()`/
        # `on_picker_lost_focus()` for why only *one* of those two paths
        # ever reactivates it.
        self._picker_captured_app: Any = None
        # The Dock auto-hide value to restore once we leave "full_width" mode
        # (or quit) -- `None` means we haven't overridden it right now.
        self._dock_autohide_overridden_from: bool | None = None
        # pywebview spawns a new thread per `js_api` call (`js_bridge_call()`)
        # -- guards against two near-simultaneous `toggle_mode()` clicks (or
        # `toggle_mode()` racing shutdown's `restore_dock_autohide()`) from
        # interleaving and corrupting the remembered "original" Dock setting.
        # Reentrant because `toggle_mode()` calls `update_layout()`, which
        # itself calls `_sync_dock_autohide_for_mode()`, while already
        # holding it.
        self._dock_autohide_lock = threading.RLock()

    def bind(
        self,
        window: Window,
        popup_window: Window,
        picker_window: Window,
        menu_window: Window,
        *,
        layout: StripLayout,
        collapsed: bool,
    ) -> None:
        self._window = window
        self._popup_window = popup_window
        self._picker_window = picker_window
        self._menu_window = menu_window
        self._layout = layout
        self._collapsed = collapsed
        self._hover_monitor = HoverMonitor(window, popup_window)
        self._hover_monitor.start()
        self._sync_dock_autohide_for_mode(layout.mode)

    def update_layout(self, layout: StripLayout) -> None:
        """Apply a freshly computed layout -- called from `bind()` and `toggle_mode()`.

        Resizes the strip window to the new placement (keeping the current
        collapsed/expanded state), tells both windows' JS which mode is now
        active (via the `body.beside-dock` CSS class `strip.html` sets), and
        brings the real Dock's auto-hide setting in line with the new mode,
        same as `start_strip()` does once at startup -- a resulting
        "full_width" strip can otherwise end up with the Dock left visible,
        covering the chips in the middle of the screen.
        """
        self._layout = layout
        self._resize_to(COLLAPSED_HEIGHT if self._collapsed else layout.height)
        script = (
            f"window.setStripMode && window.setStripMode({json.dumps(layout.mode)})"
        )
        for window in (self._window, self._popup_window):
            if window is not None:
                with contextlib.suppress(Exception):
                    window.evaluate_js(script)
        self._sync_dock_autohide_for_mode(layout.mode)

    def _sync_dock_autohide_for_mode(self, mode: StripMode) -> None:
        """Enable Dock auto-hide for "full_width", restore it when leaving that mode.

        Only "full_width" ever needs the Dock auto-hidden -- "beside_dock"
        never overlaps it. Tracks the pre-override value so repeated manual
        toggles (full_width -> beside_dock -> full_width again, via
        `toggle_mode()`) always restore the user's *original* setting, not
        whatever the previous override happened to leave behind. Serialized
        via `_dock_autohide_lock` -- see `__init__()`'s comment for why.

        Persists the captured original to `_DOCK_AUTOHIDE_ORIGINAL_MARKER`
        the moment it's captured, removes it the moment it's restored -- see
        `recover_dock_autohide_from_unclean_shutdown()` for why an unclean
        shutdown (`SIGKILL`, a crash) while that file still exists must never
        be treated as "the Dock's current setting is the real original" on
        the next launch.
        """
        with self._dock_autohide_lock:
            if mode == "full_width":
                if self._dock_autohide_overridden_from is None:
                    self._dock_autohide_overridden_from = _dock_autohide_enabled()
                    _DOCK_AUTOHIDE_ORIGINAL_MARKER.write_text(
                        "true" if self._dock_autohide_overridden_from else "false"
                    )
                    _set_dock_autohide(enabled=True)
            elif self._dock_autohide_overridden_from is not None:
                _set_dock_autohide(enabled=self._dock_autohide_overridden_from)
                self._dock_autohide_overridden_from = None
                _DOCK_AUTOHIDE_ORIGINAL_MARKER.unlink(missing_ok=True)

    def restore_dock_autohide(self, *, timeout: float | None = None) -> None:
        """Restore the Dock auto-hide setting we overrode, if any.

        Called on shutdown, and also at the start of `toggle_mode()` -- a
        no-op if there's no active override. Serialized via
        `_dock_autohide_lock` by default (`timeout=None` blocks indefinitely,
        same as the plain `with` statement this replaced).

        `start_strip()`'s shutdown path passes a short `timeout` instead: a
        background `toggle_mode()` call can get stuck forever inside
        `update_layout()`'s `evaluate_js()` call if the windows are destroyed
        mid-call (e.g. "Quit strip" racing a menu-triggered toggle) -- the
        main thread's run loop that would eventually signal that pending
        callback back is already gone, so that thread never returns, and
        it's still holding this very lock. Without a
        bounded timeout here, shutdown's `finally:` block would hang on the
        same lock forever, and the process would never reach `os._exit(0)`.
        A stuck thread can only be holding the lock *after* its own
        `restore_dock_autohide()` call already completed (that happens
        before `update_layout()`'s `evaluate_js()` call, not during it), so
        `_dock_autohide_overridden_from` is already `None` by the time this
        could matter in practice -- the best-effort restore below (run even
        if the lock couldn't be acquired) exists so a hypothetical future
        caller can't silently hang either, not because this path is expected
        to have real work left to do.
        """
        acquired = self._dock_autohide_lock.acquire(
            timeout=timeout if timeout is not None else -1
        )
        try:
            if self._dock_autohide_overridden_from is not None:
                _set_dock_autohide(enabled=self._dock_autohide_overridden_from)
                self._dock_autohide_overridden_from = None
                _DOCK_AUTOHIDE_ORIGINAL_MARKER.unlink(missing_ok=True)
        finally:
            if acquired:
                self._dock_autohide_lock.release()

    def toggle_mode(self) -> None:
        """Flip between "full_width" and "beside_dock" by restarting the strip.

        The strip's right-click "Switch mode" menu item -- the *only* way the
        layout mode ever changes now. See `dock_geometry.py`'s module
        docstring for why there's no automatic re-evaluation anymore (an
        earlier design watched for screen/wake/Dock events and continuously
        retried measurement in the background; it proved impossible to make
        reliable against a real Thunderbolt dock's sleep/wake and monitor
        hotplug behavior). Once set, the mode stays exactly as chosen --
        through sleep, wake, monitor plug/unplug, anything -- until the user
        explicitly switches it again.

        Does **not** try to measure and apply the new layout live, in this
        already-running process -- confirmed live, repeatedly, that doing so
        is unreliable in ways that took several rounds to even characterize
        (a `dock_geometry._dock_pid()` lookup that silently failed only once
        the app's own windows were up, then a genuine Dock-reveal-animation
        timing race once that was fixed). `start_strip()`'s own initial
        `compute_strip_layout()` call, in contrast, has been 100% reliable
        throughout this entire investigation -- it always runs before any
        window exists, in a clean process, with nothing else competing for
        the Dock's Accessibility state. So: persist the new mode and restart
        the whole process, reusing that already-proven-reliable path instead
        of trying to make live remeasurement work.

        Restores the real Dock auto-hide setting *before* relaunching: the
        new process's first `compute_strip_layout()` call needs the real
        Dock already in its genuine state, not still forced hidden from this
        process's "full_width" override, to measure "beside_dock" correctly.

        Saves through a *freshly re-read* `Config()` instance, not the
        module-level `config` singleton -- that singleton is the snapshot
        loaded when this process started, and `Config.save()` serializes the
        *entire* object. Writing it straight back out would silently revert
        any other setting the user edited in `config.yaml` while the strip
        was running (confirmed: changing `sidebar_refresh_interval` on disk
        while the strip stayed up, then switching modes, reverted it back).
        Re-reading first picks up whatever is on disk *right now* for every
        other field, so only `strip_mode` actually changes.
        """
        if self._layout is None:
            return
        new_mode: StripMode = (
            "beside_dock" if self._layout.mode == "full_width" else "full_width"
        )
        self.restore_dock_autohide()
        fresh_config = Config()
        fresh_config.strip_mode = new_mode
        fresh_config.save()
        pyworkon_bin = Path(sys.executable).parent / "pyworkon"
        args = [str(pyworkon_bin), "strip"]
        if self._collapsed:
            args.append("--auto-hide")
        subprocess.Popen(args, start_new_session=True)
        self.quit()

    def update_chip_rects(self, rects: list[dict[str, Any]]) -> None:
        if self._hover_monitor is not None:
            self._hover_monitor.set_chip_rects(rects)

    def show_context_menu(
        self, items_json: str, click_x: float, click_y: float
    ) -> None:
        """Show the right-click context menu in its own window, anchored at the real click position.

        `items_json` is a JS-side-built JSON array (`[{label, action, danger},
        ...]`), passed straight through unmodified -- content stays owned by
        `strip.html`, this just renders it into a *different* window and
        positions that window. `click_x`/`click_y` are the triggering
        `contextmenu` DOM event's own `clientX`/`clientY` -- page-relative,
        top-left-origin CSS pixels within the *strip* window (the only window
        with a context menu handler).

        A genuinely separate window, not a `<div>` inside the strip's own tiny
        window -- confirmed live (a real screenshot) that the strip window
        (only `STRIP_HEIGHT`, 56px, tall in full-width mode) clips a
        multi-item menu, and temporarily growing the *strip's own* window to
        fit was tried and explicitly rejected (visibly resizing the whole
        strip just to show a menu). See `native.py`'s `prepare_menu_window()`
        for the full reasoning, matching `prepare_popup_window()`'s existing
        pattern for the hover-detail popup.

        An earlier version grabbed `AppKit.NSEvent.mouseLocation()` here
        instead of taking click coordinates as a parameter -- confirmed live
        that this reads a noticeably *stale* mouse position: this method runs
        on pywebview's own per-`js_api`-call thread, and by the time it's
        even called, it still has a *blocking* `evaluate_js()` round-trip
        into the menu window ahead of it (to render and measure content
        height) before it would get around to querying "the current mouse
        position" -- more than enough time for the mouse to have moved
        between the actual click and that query, which showed up as "the
        menu opens far from the cursor." Taking the click position from the
        triggering DOM event itself instead (`strip.html`'s `clientX`/
        `clientY`, captured synchronously in the same handler that builds
        `items_json`) removes that gap entirely. Converted to absolute,
        bottom-left-origin AppKit screen coordinates the same way
        `hover_monitor.py`'s `_popup_screen_position()` converts a chip's own
        page-relative rect: `abs_x = strip_frame.x + click_x`,
        `abs_y = strip_frame.y + (strip_frame.height - click_y)`. The menu's
        *bottom-left* corner is anchored exactly there -- AppKit's
        `NSMakeRect(x, y, ...)` already treats `(x, y)` as a rect's
        bottom-left origin, so the menu extends up and to the right from the
        click, matching how the strip's own bottom-docked position leaves no
        room to extend downward.

        Content is rendered and measured in the menu window's own page first
        (`window.__showContextMenu()`, returning the measured height, the
        same "measure via a blocking `evaluate_js()` call" pattern
        `hover_monitor.py`'s `_process()` already uses for the popup), then
        the window is resized+positioned *while still hidden*, then shown --
        in that order, so there's nothing visible yet for a mid-resize
        rendering gap to show through.

        `abs_x` is clamped to the screen's own width -- a right-click near
        the screen's right edge would otherwise always extend the
        fixed-width menu off-screen to the right (anchoring purely at the
        click, with nothing to keep it on-screen), clipping its labels.
        Mirrors `_picker_screen_position()`'s own screen-edge clamp.

        Registering the shown window with the hover monitor is itself
        scheduled via `AppHelper.callAfter`, not called directly -- both
        `resize_and_position_menu_window()` and `show_menu_window()` only
        *queue* their native calls on the main thread's run loop and return
        immediately, so the window may not actually be visible yet by the
        time this method would otherwise register it. A hover-monitor poll
        tick landing in that gap would see `native.isVisible()` still
        `False` and (wrongly) treat that as "already dismissed," forgetting
        to track the window at all -- the menu would then never auto-dismiss
        once actually shown, since `set_context_menu_window()` was never
        called with a recognized window again afterward.
        `AppHelper.callAfter` preserves call order, so queuing the
        registration the same way guarantees it only runs once the native
        show has actually completed.
        """
        if self._window is None or self._menu_window is None:
            return
        with contextlib.suppress(Exception):
            strip_native = self._window.native
            menu_native = self._menu_window.native
            if strip_native is None or menu_native is None:
                return
            height = self._menu_window.evaluate_js(
                f"window.__showContextMenu({items_json})"
            )
            if not height:
                return
            strip_frame = strip_native.frame()
            abs_x = strip_frame.origin.x + click_x
            screen = strip_native.screen()
            if screen is not None:
                screen_frame = screen.frame()
                min_x = screen_frame.origin.x + _MENU_SCREEN_MARGIN
                max_x = (
                    screen_frame.origin.x
                    + screen_frame.size.width
                    - MENU_WIDTH
                    - _MENU_SCREEN_MARGIN
                )
                abs_x = max(min_x, min(abs_x, max_x))
            abs_y = strip_frame.origin.y + (strip_frame.size.height - click_y)
            resize_and_position_menu_window(
                menu_native, abs_x, abs_y, MENU_WIDTH, float(height)
            )
            show_menu_window(menu_native)
            hover_monitor = self._hover_monitor
            menu_window = self._menu_window
            if hover_monitor is not None:
                AppHelper.callAfter(hover_monitor.set_context_menu_window, menu_window)

    def hide_context_menu(self) -> None:
        """Hide the context menu window -- called on an explicit item click or click-away."""
        if self._hover_monitor is not None:
            self._hover_monitor.set_context_menu_window(None)
        if self._menu_window is None:
            return
        with contextlib.suppress(Exception):
            menu_native = self._menu_window.native
            if menu_native is not None:
                hide_menu_window(menu_native)

    def hide_popup(self) -> None:
        """Hide the popup window on the popup page's own request.

        Normally `hover_monitor.py`'s poll loop is the only thing that
        shows/hides the popup, driven purely by mouse position -- this is
        the one exception: `strip.html`'s `updateState()` calls this when a
        daemon-pushed state update shows the session its popup is currently
        displaying no longer exists (e.g. the session was killed). Without
        it, a popup whose session disappeared would stay open indefinitely
        if the mouse happens to be resting on the popup itself, since
        `_mouse_over_popup_window()` treats that as "stay open" and nothing
        else would ever tell it otherwise. `hover_monitor.py`'s own
        `_hovered` state self-corrects within a few poll ticks afterward,
        since `isVisible()` (checked before "stay open") now reads `False`.
        """
        if self._popup_window is None:
            return
        with contextlib.suppress(Exception):
            popup_native = self._popup_window.native
            if popup_native is not None:
                hide_popup_window(popup_native)

    def switch_session(self, session_name: str) -> None:
        with (
            contextlib.suppress(DaemonNotRunningError, ConnectionError, OSError),
            DaemonClient() as client,
        ):
            client.switch_session(session_name)

    def kill_session(self, session_name: str) -> None:
        with (
            contextlib.suppress(DaemonNotRunningError, ConnectionError, OSError),
            DaemonClient() as client,
        ):
            client.kill_session(session_name)

    def open_url(self, url: str) -> None:
        webbrowser.open(url)

    def open_project_picker(self, *, switcher_mode: bool = False) -> None:
        """Show the project picker, giving it real keyboard focus.

        The ONE deliberate exception to "the strip must never take focus"
        (see `native.py`'s `prepare_window()`) -- scoped to this separate,
        normally-hidden third window; the strip and hover-popup windows stay
        exactly as focus-proof as before. Captures whichever app is
        frontmost right now so `close_project_picker()` can hand it back the
        instant the picker closes.

        `switcher_mode` distinguishes the two callers: the "+" chip (`False`,
        the default -- a project-centric merged list with an "Open" badge on
        already-running ones, see `picker.html`) vs. `toggle_project_picker()`
        (`True` -- a universal switcher grouping plain/open sessions above
        closed projects, matching the old Textual popup's section order).
        Passed straight through to the picker page via `__onPickerShown()`.
        """
        if self._picker_window is None or self._window is None:
            return
        # Must happen before anything else: `hover_monitor.py`'s background
        # poll thread checks "did we just become frontmost" every ~30ms and,
        # by design, immediately un-does it if so -- the watchdog that keeps
        # an accidental chip-click activation from sticking. Left running
        # while we *intentionally* make ourselves frontmost below, it fights
        # that within one tick and the picker never actually gets to keep
        # focus, let alone let the user type into it.
        if self._hover_monitor is not None:
            self._hover_monitor.set_reclaim_suspended(suspended=True)
        self._picker_captured_app = capture_frontmost_app()
        with contextlib.suppress(Exception):
            strip_native = self._window.native
            picker_native = self._picker_window.native
            if strip_native is None or picker_native is None:
                return
            x, y = self._picker_screen_position(strip_native)
            move_picker_window(picker_native, x, y)
            show_picker_window(picker_native)
        self._set_picker_button_open(is_open=True)
        if self._picker_window is not None:
            with contextlib.suppress(Exception):
                # Clears any leftover filter text from the last time it was
                # open and focuses the search input -- `show_picker_window()`
                # only makes the *window* key, it doesn't put the page's own
                # focus on any particular element within it.
                self._picker_window.evaluate_js(
                    "window.__onPickerShown && window.__onPickerShown("
                    f"{json.dumps(switcher_mode)})"
                )

    def _picker_screen_position(self, strip_native: Any) -> tuple[float, float]:
        """Anchor the picker to the strip window's top-right corner.

        The "+" chip that opens the picker is always the strip's rightmost
        element, so anchoring to the strip's own right edge approximates
        "near the button" without needing a separately JS-reported button
        rect -- mirrors `hover_monitor.py`'s own screen-edge-margin
        conventions for this kind of "float just above/beside something"
        positioning, just simplified since the picker's size never changes
        (see `native.py`'s `PICKER_WIDTH`/`PICKER_HEIGHT`).
        """
        frame = strip_native.frame()
        x = frame.origin.x + frame.size.width - PICKER_WIDTH - _PICKER_SCREEN_MARGIN
        x = max(frame.origin.x, x)
        y = frame.origin.y + frame.size.height + _PICKER_SCREEN_MARGIN
        return x, y

    def close_project_picker(self) -> None:
        """Hide the picker and hand focus back to whatever had it before opening.

        For an *explicit* close (the user selected a project, or pressed
        Escape) -- see `on_picker_lost_focus()` for the separate click-away
        path, which must never reactivate anything.
        """
        self._hide_picker()
        reactivate_app(self._picker_captured_app)
        self._picker_captured_app = None

    def on_picker_lost_focus(self) -> None:
        """The picker's `NSWindowDidResignKeyNotification` callback (see `native.py`).

        Fires for an explicit close too (hiding a window makes it resign
        key first) -- harmless, since this only ever hides (idempotent) and
        never reactivates anything. Reactivating unconditionally here would
        be wrong specifically for the click-away case: the user's own click
        already made some *other* app frontmost, and reactivating our
        captured (now-stale) app would fight that fresh click.
        """
        self._hide_picker()
        self._picker_captured_app = None

    def _hide_picker(self) -> None:
        if self._picker_window is not None:
            with contextlib.suppress(Exception):
                picker_native = self._picker_window.native
                if picker_native is not None:
                    hide_picker_window(picker_native)
        self._set_picker_button_open(is_open=False)
        # Resume the watchdog `open_project_picker()` suspended -- from here
        # on, this process being frontmost again means a click accidentally
        # activated it, not the picker legitimately holding focus, so it
        # should go right back to handing focus away as usual.
        if self._hover_monitor is not None:
            self._hover_monitor.set_reclaim_suspended(suspended=False)

    def _set_picker_button_open(self, *, is_open: bool) -> None:
        """Keep the strip's own "+"/close toggle chip in sync with the picker's real state.

        Needed because the picker can close *without* a strip-side click at
        all (click-away, via `on_picker_lost_focus()`) -- the strip's JS has
        no other way to find out, same pattern `update_layout()` already
        uses for `window.setStripMode()`.
        """
        if self._window is None:
            return
        with contextlib.suppress(Exception):
            self._window.evaluate_js(
                f"window.__setPickerOpen && window.__setPickerOpen({json.dumps(is_open)})"
            )

    def toggle_project_picker(self) -> None:
        """Toggle the project picker open/closed -- the global hotkey's callback target.

        Mirrors `strip.html`'s own "+" button toggle logic (`if (pickerOpen)
        close else open`), just decided from the Python side instead of JS,
        since the hotkey has no DOM click event to carry that state.
        `isVisible()` is a plain read, safe from any thread (same pattern as
        `hover_monitor.py`'s `_mouse_over_popup_window()`).
        """
        if self._picker_window is None:
            return
        with contextlib.suppress(Exception):
            picker_native = self._picker_window.native
            if picker_native is not None and picker_native.isVisible():
                self.close_project_picker()
            else:
                self.open_project_picker(switcher_mode=True)

    def switch_session_from_picker(self, session_name: str) -> None:
        """Switch to an already-open session and close the picker right away.

        Mirrors `enter_project()`'s ordering (close first, then make the
        daemon call) for the same reason. `switch_session()` itself is left
        untouched -- it's also called directly for strip chip clicks, which
        have no picker to close.
        """
        self.close_project_picker()
        self.switch_session(session_name)

    def enter_project(self, project_id: str) -> None:
        """Open a session for `project_id` and close the picker right away.

        Closes the picker *before* the (potentially slow -- tmux session
        creation, `tmuxp load`, hooks) daemon call, not after: this method is
        already running on its own background thread (every `js_api` call
        gets one, see `pywebview`'s `js_bridge_call()`), so the daemon call
        below never blocks the UI either way -- but closing first means the
        user sees the picker disappear immediately on Enter/click, instead of
        it sitting open for however long `ENTER_PROJECT` takes to answer.
        """
        self.close_project_picker()
        with (
            contextlib.suppress(DaemonNotRunningError, ConnectionError, OSError),
            DaemonClient() as client,
        ):
            client.enter_project(project_id)

    def quit(self) -> None:
        """Close the strip's windows.

        The strip is frameless and has no Dock icon or menu bar, so there's
        no OS-native way to quit it -- this is the only one. Closing the
        windows this way (rather than an external `kill`/`pkill`) lets
        `start_strip()`'s `finally` run, restoring the user's original Dock
        auto-hide setting; a `SIGTERM` to the process cannot reach Python code
        blocked inside pywebview's native run loop. All four windows must be
        destroyed -- `webview.start()` only returns once every window it
        created has closed, so leaving the popup, picker, or context-menu
        window open would leave the process hanging.
        """
        if self._menu_window is not None:
            self._menu_window.destroy()
        if self._picker_window is not None:
            self._picker_window.destroy()
        if self._popup_window is not None:
            self._popup_window.destroy()
        if self._window is not None:
            self._window.destroy()

    def toggle_collapse(self) -> None:
        if self._window is None or self._layout is None:
            return
        self._collapsed = not self._collapsed
        self._resize_to(COLLAPSED_HEIGHT if self._collapsed else self._layout.height)
        # Collapsing mid-hover would otherwise leave the popup open and
        # floating above a now-hidden strip.
        if self._popup_window is not None:
            with contextlib.suppress(Exception):
                popup_native = self._popup_window.native
                if popup_native is not None:
                    hide_popup_window(popup_native)

    def _resize_to(self, height: int) -> None:
        if self._window is None or self._layout is None:
            return
        with contextlib.suppress(Exception):
            native = self._window.native
            if native is None:
                return
            resize_frame(
                native, self._layout.x, self._layout.y, self._layout.width, height
            )
