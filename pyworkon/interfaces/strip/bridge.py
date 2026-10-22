"""JS-callable Python API exposed to the strip webview via pywebview's `js_api`.

Session-action wrappers mirror `interfaces/tui/base.py`'s `BaseApp` static
methods -- duplicated rather than imported, since the strip is an independent
interface (like `relay`) that has no dependency on Textual.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
lazy import contextlib
lazy import json
lazy import subprocess
lazy import threading
lazy import webbrowser

from pyworkon.daemon.client import DaemonClient, DaemonNotRunningError
lazy from pyworkon.interfaces.strip.dock_geometry import compute_strip_layout
lazy from pyworkon.interfaces.strip.hover_monitor import HoverMonitor
lazy from pyworkon.interfaces.strip.native import (
    PICKER_WIDTH,
    capture_frontmost_app,
    hide_picker_window,
    hide_popup_window,
    move_picker_window,
    reactivate_app,
    resize_frame,
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

_OSASCRIPT = "/usr/bin/osascript"


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


class StripBridge:
    """Session actions callable from the strip's JavaScript side."""

    def __init__(self) -> None:
        self._window: Window | None = None
        self._popup_window: Window | None = None
        self._picker_window: Window | None = None
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
        # `NSApplicationDidChangeScreenParametersNotification` can fire more
        # than once for a single hardware change, each spawning its own
        # background thread (see `app.py`'s `_watch_screen_changes()`).
        # Without serializing, two threads can both read
        # `_dock_autohide_overridden_from` as `None` before either writes it,
        # each capturing "the current Dock setting" as the value to restore
        # later -- but by the time the second thread's `_set_dock_autohide()`
        # call runs, the *first* thread may have already changed it, so the
        # second thread captures the first thread's override as if it were
        # the user's real original setting. Reentrant because
        # `recompute_and_apply_layout()` calls `restore_dock_autohide()`
        # and `update_layout()` (which itself calls
        # `_sync_dock_autohide_for_mode()`) while already holding it.
        self._dock_autohide_lock = threading.RLock()

    def bind(
        self,
        window: Window,
        popup_window: Window,
        picker_window: Window,
        *,
        layout: StripLayout,
        collapsed: bool,
    ) -> None:
        self._window = window
        self._popup_window = popup_window
        self._picker_window = picker_window
        self._layout = layout
        self._collapsed = collapsed
        self._hover_monitor = HoverMonitor(window, popup_window)
        self._hover_monitor.start()
        self._sync_dock_autohide_for_mode(layout.mode)

    def update_layout(self, layout: StripLayout) -> None:
        """Re-apply a freshly recomputed layout -- e.g. after a display is connected/disconnected.

        Resizes the strip window to the new placement (keeping the current
        collapsed/expanded state), tells both windows' JS which mode is now
        active (via the `body.beside-dock` CSS class `strip.html` sets), and
        brings the real Dock's auto-hide setting in line with the new mode --
        a mode transition at runtime (e.g. disconnecting the external monitor
        a "beside_dock" layout was anchored to) needs the exact same Dock
        management `start_strip()` does once at startup, or a resulting
        "full_width" strip can end up with the Dock left visible, covering
        the chips in the middle of the screen.
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
        never overlaps it. Tracks the pre-override value so repeated
        transitions (e.g. monitor unplugged, replugged, unplugged again)
        always restore the user's *original* setting, not whatever the
        previous override happened to leave behind. Serialized via
        `_dock_autohide_lock` -- see `__init__()`'s comment for why.
        """
        with self._dock_autohide_lock:
            if mode == "full_width":
                if self._dock_autohide_overridden_from is None:
                    self._dock_autohide_overridden_from = _dock_autohide_enabled()
                    _set_dock_autohide(enabled=True)
            elif self._dock_autohide_overridden_from is not None:
                _set_dock_autohide(enabled=self._dock_autohide_overridden_from)
                self._dock_autohide_overridden_from = None

    def restore_dock_autohide(self, *, timeout: float | None = None) -> None:
        """Restore the Dock auto-hide setting we overrode, if any.

        Called on shutdown, and also before every layout remeasurement (see
        `recompute_and_apply_layout()`) -- a no-op if there's no active
        override. Serialized via `_dock_autohide_lock` by default (`timeout
        =None` blocks indefinitely, same as the plain `with` statement this
        replaced).

        `start_strip()`'s shutdown path passes a short `timeout` instead: a
        background `recompute_and_apply_layout()` call can get stuck forever
        inside `update_layout()`'s `evaluate_js()` call if the windows are
        destroyed mid-call (e.g. "Quit strip" racing a screen-change
        recompute) -- the main thread's run loop that would eventually
        signal that pending callback back is already gone, so that thread
        never returns, and it's still holding this very lock. Without a
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
        finally:
            if acquired:
                self._dock_autohide_lock.release()

    def recompute_and_apply_layout(self, *, full_width_height: int) -> None:
        """Atomically restore, remeasure, and re-apply the strip's layout.

        The whole restore -> `compute_strip_layout()` -> `update_layout()`
        sequence runs under `_dock_autohide_lock` so a second, concurrent
        screen-change notification can never interleave with this one and
        corrupt the remembered "original" Dock setting (see `__init__()`'s
        comment). Restoring first matters on its own too: `compute_strip
        _layout()` measures the Dock's reserved height via `NSScreen
        .visibleFrame()`, which reports zero while the Dock is auto-hidden
        -- including when *we're* the ones currently forcing it hidden for
        "full_width" mode. Without restoring the real setting first, every
        recomputation while already in "full_width" would see that
        self-inflicted zero and conclude "beside_dock isn't possible" again,
        forever -- even after reconnecting a monitor with plenty of room.
        """
        with self._dock_autohide_lock:
            self.restore_dock_autohide()
            layout = compute_strip_layout(full_width_height=full_width_height)
            self.update_layout(layout)

    def update_chip_rects(self, rects: list[dict[str, Any]]) -> None:
        if self._hover_monitor is not None:
            self._hover_monitor.set_chip_rects(rects)

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

    def open_project_picker(self) -> None:
        """Show the "open a new session" project picker, giving it real keyboard focus.

        The ONE deliberate exception to "the strip must never take focus"
        (see `native.py`'s `prepare_window()`) -- scoped to this separate,
        normally-hidden third window; the strip and hover-popup windows stay
        exactly as focus-proof as before. Captures whichever app is
        frontmost right now so `close_project_picker()` can hand it back the
        instant the picker closes.
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
                    "window.__onPickerShown && window.__onPickerShown()"
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
        blocked inside pywebview's native run loop. All three windows must be
        destroyed -- `webview.start()` only returns once every window it
        created has closed, so leaving the (separate, since the two-window
        popup redesign) popup or picker window open would leave the process
        hanging.
        """
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
