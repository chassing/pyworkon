"""Global mouse-position hover tracking, so the strip's popup works without focus.

A background, non-active window's WKWebView never receives continuous
mouse-moved events from AppKit -- that's gated on the window being *key*, and
the window must never become key (see `native.py`). The strip must never take
or request focus at all, so native `:hover`/`mouseover` detection can't be
relied on to open the popup on its own.

Instead, a background thread polls `NSEvent.mouseLocation()` (current global
cursor position in screen coordinates) on a short fixed interval and does its
own point-in-rect hit-testing against the chip rectangles `strip.html` reports
after each render, driving the separate popup window via direct native calls
(`native.py`'s `resize_and_position_popup_window()`/`show_popup_window()`/
`hide_popup_window()`) and `evaluate_js()` instead of relying on the DOM's own
hover events.

An earlier version used an `NSEvent` global *event monitor*
(`addGlobalMonitorForEventsMatchingMask:handler:`) instead of polling. That
requires Accessibility permission (System Settings > Privacy & Security >
Accessibility) and, worse, turned out to be an unreliable way to get timely
mouse-moved callbacks for a never-active, `NSApplicationActivationPolicyAccessory`
process in practice: hover sometimes fired instantly, sometimes only after a
multi-second delay, and occasionally not at all until the mouse moved onto a
*different* chip (consistent with macOS's App Nap throttling -- or with the
observer process's own TCC permission bookkeeping getting confused across
relaunches -- deprioritizing a background accessory app's event-handling run
loop). Plain `NSEvent.mouseLocation()` polling needs no special permission at
all (confirmed against real-world precedent: e.g. the `sketchybar-toggle`
macOS utility polls it at 60Hz from a background daemon with zero
entitlements) and removes the whole class of "was this event actually
delivered, and when" uncertainty -- every tick is a fresh, synchronous read of
where the cursor actually is right now.

Since the polling loop already runs on its own dedicated background thread
(not AppKit's main thread), it's safe to call the blocking `evaluate_js()`
directly from it -- no separate queue/consumer-thread split is needed the way
it would be from a main-thread-delivered event callback.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
lazy import contextlib
lazy import json

lazy import AppKit
lazy from PyObjCTools import AppHelper

lazy from pyworkon.interfaces.strip.native import (
    POPUP_MAX_HEIGHT,
    POPUP_MAX_WIDTH,
    POPUP_MIN_HEIGHT,
    POPUP_MIN_WIDTH,
    clamp_popup_height,
    clamp_popup_width,
    hide_popup_window,
    resize_and_position_popup_window,
    show_popup_window,
)

if TYPE_CHECKING:
    from webview import Window

# 30ms feels instant to a human (well under the ~100ms perceptible-delay
# threshold) while being a negligible amount of background CPU work -- each
# tick is just a `mouseLocation()` read plus a handful of dict lookups.
_POLL_INTERVAL_SECONDS = 0.03
# Require this many consecutive "missed" ticks (~90ms) before actually
# treating the mouse as having left a chip -- see `_poll_once()`.
_LEAVE_DEBOUNCE_TICKS = 3
# Sentinel meaning "still within the currently-open popup" -- unlike a real
# session name or None (nothing hovered), this must not change `_hovered` or
# trigger any `evaluate_js()` call, since the popup should stay open while the
# mouse is on it.
_KEEP_CURRENT = "\x00keep\x00"
# Small tolerance added to every chip rect's hit-test bounds. Natural
# sub-pixel mouse jitter sitting right at a chip's edge would otherwise rapidly
# flap the hover state in and out.
_HIT_MARGIN = 4.0
# Keep the popup window this far from the screen's edges -- on the X axis,
# the strip window's left/right screen edges (mirrors the old CSS clamping,
# `Math.max(8, Math.min(...))`, that used to run inside the strip's own
# page); on the Y axis, the screen's top edge (see `_max_popup_height()`).
_SCREEN_EDGE_MARGIN = 8.0


@dataclass
class _Rect:
    left: float
    top: float
    width: float
    height: float

    def contains(self, x: float, y: float) -> bool:
        return (
            self.left - _HIT_MARGIN <= x <= self.left + self.width + _HIT_MARGIN
            and self.top - _HIT_MARGIN <= y <= self.top + self.height + _HIT_MARGIN
        )


class HoverMonitor:
    """Drives the strip's hover popup window from polled mouse position, not native hover."""

    def __init__(self, window: Window, popup_window: Window) -> None:
        self._window = window
        self._popup_window = popup_window
        self._chip_rects: dict[str, _Rect] = {}
        self._hovered: str | None = None
        self._miss_streak = 0
        self._last_other_app: Any = None

    def start(self) -> None:
        threading.Thread(target=self._poll_loop, daemon=True).start()

    def set_chip_rects(self, rects: list[dict[str, Any]]) -> None:
        self._chip_rects = {
            r["session_name"]: _Rect(r["left"], r["top"], r["width"], r["height"])
            for r in rects
        }

    def _poll_loop(self) -> None:
        """Runs forever on its own thread: safe to block on `evaluate_js()` here.

        An uncaught exception here would silently kill this thread forever --
        no more hover for the rest of the process's life, with nothing in the
        UI to indicate why. `evaluate_js()` reaching into a WKWebView that's
        mid-navigation is exactly the kind of best-effort call that can
        occasionally fail transiently; swallow it and keep going.
        """
        while True:
            with contextlib.suppress(Exception):
                self._reclaim_activation_if_stolen()
                self._poll_once(AppKit.NSEvent.mouseLocation())
            time.sleep(_POLL_INTERVAL_SECONDS)

    def _reclaim_activation_if_stolen(self) -> None:
        """Hand frontmost status back immediately if this process ever gets it.

        Confirmed via diagnostic logging that a real click on the strip makes
        this process the system's frontmost one even though the window itself
        correctly never becomes key (`focus=False`, see `native.py`, prevents
        that part) -- becoming key and the *application* activating are two
        separate AppKit mechanisms, and nothing in this codebase controls the
        second one directly (it's standard default click-handling behavior,
        not something reachable through a public, override-able hook).

        The first version of this watchdog called `NSApplication.deactivate()`
        -- confirmed via logging that this has *no effect whatsoever* here:
        `isActive()` kept reading `True` on every single tick, forever, for
        the entire session, even well before any click. `deactivate()` just
        resigns active status without a specific target to hand it to, and
        apparently has nothing valid to fall back to for a never-really-
        foreground `NSApplicationActivationPolicyAccessory` process -- macOS
        14+'s "cooperative activation" changes are a documented source of
        exactly this kind of silently-ignored activation-state call. Explicitly
        re-activating a *specific* other app (whichever one was genuinely
        frontmost most recently, tracked in `_last_other_app`) is a much more
        direct ask and reliably takes effect instead.
        """

        def _apply() -> None:
            workspace = AppKit.NSWorkspace.sharedWorkspace()
            frontmost = workspace.frontmostApplication()
            our_pid = (
                AppKit.NSRunningApplication.currentApplication().processIdentifier()
            )
            if frontmost is None:
                return
            if frontmost.processIdentifier() == our_pid:
                if self._last_other_app is not None:
                    self._last_other_app.activateWithOptions_(0)
            else:
                self._last_other_app = frontmost

        AppHelper.callAfter(_apply)

    def _poll_once(self, mouse: Any) -> None:
        target = self._hit_test(mouse)
        if target == _KEEP_CURRENT:
            self._miss_streak = 0
            return
        if target == self._hovered:
            self._miss_streak = 0
            return
        if target is None:
            # Debounce leaving specifically: a single transient miss (natural
            # mouse micro-jitter, or a chip's rect shifting for one tick while
            # a daemon-pushed re-render reflows the row) would otherwise close
            # the popup immediately and reopen it a moment later.
            # Switching directly to a *different* chip is never debounced.
            self._miss_streak += 1
            if self._miss_streak < _LEAVE_DEBOUNCE_TICKS:
                return
        self._miss_streak = 0
        self._hovered = target
        self._process(target)

    def _hit_test(self, mouse: Any) -> str | None:
        if self._mouse_over_popup_window(mouse):
            return _KEEP_CURRENT
        point = self._local_point(mouse)
        if point is None:
            return None
        x, y = point
        for session_name, rect in self._chip_rects.items():
            if rect.contains(x, y):
                return session_name
        return None

    def _mouse_over_popup_window(self, mouse: Any) -> bool:
        """Is the mouse over the (separate, native) popup window right now?

        Checked directly against the popup window's own native frame (always
        in absolute screen coordinates, same as `mouse`) rather than a
        CSS-reported rect -- unlike the old single-window design, the popup's
        on-screen position is something *we* set (`position_and_show_popup_window()`),
        not something `strip.html`'s JS needs to report back.
        """
        native = self._popup_window.native
        if native is None or not native.isVisible():
            return False
        frame = native.frame()
        return (
            frame.origin.x <= mouse.x <= frame.origin.x + frame.size.width
            and frame.origin.y <= mouse.y <= frame.origin.y + frame.size.height
        )

    def _local_point(self, mouse: Any) -> tuple[float, float] | None:
        """Mouse position in webview-local, top-left-origin CSS pixel coordinates."""
        native = self._window.native
        if native is None:
            return None
        frame = native.frame()
        x = mouse.x - frame.origin.x
        y_from_bottom = mouse.y - frame.origin.y
        if not (0 <= x <= frame.size.width and 0 <= y_from_bottom <= frame.size.height):
            return None
        return x, frame.size.height - y_from_bottom

    def _process(self, target: str | None) -> None:
        if target is None:
            popup_native = self._popup_window.native
            if popup_native is not None:
                hide_popup_window(popup_native)
            return
        # Render content and measure its size first, then resize+position
        # (still hidden), then finally show -- in that order:
        # `evaluate_js()` blocks until the script actually runs and returns
        # `__showPopupFor()`'s measured `[width, height]`, while
        # `resize_and_position_popup_window()`/`show_popup_window()` only
        # schedule their native calls. Resizing *before* showing means
        # there's nothing visible yet for a mid-resize rendering gap to show
        # through (see `native.py`'s `resize_and_position_popup_window()`);
        # showing before content lands would instead risk a flash of stale
        # (previous-hover, or empty) content.
        max_width = self._max_popup_width()
        raw_size = self._popup_window.evaluate_js(
            f"window.__showPopupFor({json.dumps(target)}, {json.dumps(max_width)})"
        )
        if not raw_size:
            # `__showPopupFor()` returns `null` for a session it doesn't know
            # how to render (e.g. a plain tmux session, which has no popup at
            # all) -- don't show an empty window for it, and explicitly hide
            # it if one was already open (e.g. moving directly from a
            # project chip to a plain-session chip): without this, the
            # previous project's popup content stays visible, now floating
            # beside the wrong chip, since nothing else here tells it to hide.
            popup_native = self._popup_window.native
            if popup_native is not None:
                hide_popup_window(popup_native)
            return
        raw_width, raw_height = raw_size
        width = clamp_popup_width(float(raw_width), max_width)
        height = clamp_popup_height(float(raw_height), self._max_popup_height())
        position = self._popup_screen_position(target, width)
        if position is not None:
            popup_native = self._popup_window.native
            if popup_native is not None:
                x, y = position
                resize_and_position_popup_window(popup_native, x, y, width, height)
                show_popup_window(popup_native)

    def _max_popup_height(self) -> float:
        """How tall the popup can grow before it would run off the top of the screen.

        The popup's `y` origin always sits at the strip window's top edge
        (see `_popup_screen_position()`) and grows *upward* from there, so
        the space between the strip's top edge and the screen's own top edge
        is exactly what's free. A fixed cap (the old, constant
        `POPUP_MAX_HEIGHT`) either forced a needless scrollbar on content
        that would have comfortably fit on a tall screen, or could in
        principle still run off a short one -- mirrors
        `_popup_screen_position()`'s own screen-edge-aware clamping on the X
        axis, just applied to the Y axis instead. Falls back to the fixed
        `POPUP_MAX_HEIGHT` when the strip's current screen can't be
        determined (no native window yet, or no screen -- e.g. mid
        reconfiguration).
        """
        strip_native = self._window.native
        if strip_native is None:
            return POPUP_MAX_HEIGHT
        screen = strip_native.screen()
        if screen is None:
            return POPUP_MAX_HEIGHT
        screen_frame = screen.frame()
        strip_frame = strip_native.frame()
        screen_top = screen_frame.origin.y + screen_frame.size.height
        strip_top = strip_frame.origin.y + strip_frame.size.height
        available = screen_top - strip_top - _SCREEN_EDGE_MARGIN
        return max(POPUP_MIN_HEIGHT, available)

    def _max_popup_width(self) -> float:
        """How wide the popup can grow before it would run off the strip's own span.

        Bound by the strip window's own horizontal extent, matching
        `_popup_screen_position()`'s existing X-axis clamp (which already
        keeps the popup within that same span) -- a fixed cap (the old
        constant `POPUP_MAX_WIDTH`) keeps getting hit again by whatever the
        next, slightly-longer real-world CI check name turns out to be
        (Konflux pipeline names in particular run long), forcing an orphaned
        single-word second line instead of fitting on one. Falls back to the
        fixed `POPUP_MAX_WIDTH` when the strip's own frame isn't available.
        """
        strip_native = self._window.native
        if strip_native is None:
            return POPUP_MAX_WIDTH
        strip_frame = strip_native.frame()
        available = strip_frame.size.width - 2 * _SCREEN_EDGE_MARGIN
        return max(POPUP_MIN_WIDTH, available)

    def _popup_screen_position(
        self, session_name: str, popup_width: float
    ) -> tuple[float, float] | None:
        """Absolute screen position (AppKit bottom-left origin) for the popup window.

        Anchored to the hovered chip's left and *top* edge, clamped so it
        never runs off either side of the screen -- mirrors the clamping
        `strip.html` used to do in CSS when the popup lived inside the
        strip's own page. `popup_width` is this specific popup's own freshly
        measured (and clamped) width, not a fixed constant, since the
        right-edge clamp depends on how wide *this* popup actually is.

        `y` anchors to the *chip's own* top edge, not the strip window's --
        `#strip` centers chips vertically (`align-items: center`), and in
        `beside_dock` mode the strip's own height (the real Dock's height)
        can noticeably exceed a chip's natural height, leaving empty strip
        background above the chip. Anchoring to the window's top edge put
        the popup flush against the *window*, with that same empty space
        now sitting visibly between the popup and the chip underneath it --
        anchoring to the chip's own top edge instead closes that gap
        regardless of how the chip is aligned within the strip. `chip.top`
        is a CSS top-down offset from the strip window's own top (see
        `reportChipRects()`'s `getBoundingClientRect()`), so converting to
        AppKit's bottom-up coordinates is `window_top - chip.top`, i.e.
        `strip_frame.origin.y + (strip_frame.size.height - chip.top)`.
        """
        chip = self._chip_rects.get(session_name)
        strip_native = self._window.native
        if chip is None or strip_native is None:
            return None
        strip_frame = strip_native.frame()
        x = strip_frame.origin.x + chip.left
        min_x = strip_frame.origin.x + _SCREEN_EDGE_MARGIN
        max_x = (
            strip_frame.origin.x
            + strip_frame.size.width
            - popup_width
            - _SCREEN_EDGE_MARGIN
        )
        x = max(min_x, min(x, max_x))
        y = strip_frame.origin.y + (strip_frame.size.height - chip.top)
        return x, y
