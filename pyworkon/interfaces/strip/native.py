"""Direct AppKit window control, bypassing pywebview's default titled-window constraints.

`webview.Window.native` is a `WindowHost` -- a real `NSWindow` subclass that
pywebview creates even for `frameless=True` windows, since it still carries
`NSWindowStyleMaskTitled` (its titlebar is just visually hidden, so it can
still be dragged back on-screen via the OS's usual safety net). That titled
style mask makes AppKit's `constrainFrameRect:toScreen:` silently push any
sufficiently short frame away from the screen edge -- the opposite of what a
Dock-replacement strip wants. Dropping to a pure `NSWindowStyleMaskBorderless`
style mask disables that constraint entirely. AppKit also requires window
mutations to happen on the main thread, which `webview.start()`'s background
thread is not, so every mutation here is marshaled via
`PyObjCTools.AppHelper.callAfter`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
lazy import threading

lazy import AppKit
lazy from PyObjCTools import AppHelper

if TYPE_CHECKING:
    from collections.abc import Callable

# NSWindowStyleMaskBorderless -- plain borderless, no other bits. The window
# must never become key at all (see `prepare_window()` below for why); that's
# guaranteed one layer up, by `app.py`'s `webview.create_window(..., focus=False)`
# call, which pywebview's own `WindowHost.canBecomeKeyWindow` honors directly
# -- no style-mask trick is needed here on top of that.
_BORDERLESS = 0
# NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorStationary
_ALL_SPACES_STATIONARY = (1 << 0) | (1 << 4)
# The real Dock runs at CG window layer 20. One below that keeps the strip
# above ordinary app windows (Normal=0) while still yielding to the Dock
# itself when the user hovers the screen edge to reveal it -- the opposite of
# `NSStatusWindowLevel` (25), which would otherwise always cover the Dock.
_BELOW_DOCK_LEVEL = 19
_ACCESSORY_POLICY = 1  # NSApplicationActivationPolicyAccessory
_REDISPLAY_IMMEDIATELY = True
_ACCEPT_MOUSE_MOVED_EVENTS = True

# Native size of the hover-detail popup's own window (see
# `prepare_popup_window()` below for why it's a separate window). Both
# dimensions are dynamic, each clamped between its own min/max bounds: see
# `clamp_popup_height()`/`clamp_popup_width()` and `hover_monitor.py`'s
# `_process()`. A fixed width was tried first -- too wide made trivial
# popups (just a branch name, no PR) look comically oversized; too narrow
# wrapped long CI check names (e.g. "Red Hat Konflux / automated-actions
# -main-enterprise-contract / automated-actions-cli-main") across multiple
# lines even when actually un-wrapping them would easily fit on typical
# screens.
POPUP_MIN_WIDTH = 280
POPUP_MAX_WIDTH = 820
POPUP_MIN_HEIGHT = 100
POPUP_MAX_HEIGHT = 480


def clamp_popup_height(height: float, max_height: float = POPUP_MAX_HEIGHT) -> float:
    """Clamp a JS-measured content height into a sane on-screen range.

    Too short looks visually broken for a near-empty popup (e.g. a plain
    tmux session with no branch/PR/agent data). `max_height` defaults to the
    fixed `POPUP_MAX_HEIGHT`, but `hover_monitor.py` normally passes its own
    `_max_popup_height()` instead -- the real, screen-aware amount of room
    between the strip's top edge and the screen's own top edge is almost
    always a better bound than one arbitrary fixed number for every display,
    the same way `clamp_popup_width()` already measures against the
    content's own natural width rather than guessing a single fixed size.
    """
    return max(POPUP_MIN_HEIGHT, min(height, max_height))


def clamp_popup_width(width: float, max_width: float = POPUP_MAX_WIDTH) -> float:
    """Clamp a JS-measured content width into a sane on-screen range.

    Too narrow looks cramped for a near-empty popup. `max_width` defaults to
    the fixed `POPUP_MAX_WIDTH`, but `hover_monitor.py` normally passes its
    own `_max_popup_width()` instead -- a fixed cap keeps getting hit again by
    whatever the next, slightly-longer real-world CI check name turns out to
    be (Konflux pipeline names in particular can run long), forcing an
    orphaned single-word second line instead of fitting on one. The real,
    screen-aware amount of horizontal room is almost always a better bound,
    the same way `clamp_popup_height()` already measures against the real
    space above the strip rather than guessing a single fixed size.
    """
    return max(POPUP_MIN_WIDTH, min(width, max_width))


def prepare_window(native: Any) -> None:
    """One-time setup: run exactly once per window, right after it's shown.

    The window must never become key, not even through a genuine user click:
    becoming key diverts keyboard input to that window regardless of whether
    its *owning app* is active, which silently steals keystrokes away from
    whatever app (e.g. a terminal) the user is actually working in. An
    earlier version used `NSWindowStyleMaskNonactivatingPanel` plus a
    programmatic `makeKeyAndOrderFront_()` call specifically to let a real
    click key the window without activating the app, in order to get native
    WKWebView hover (which requires a key window) -- that's exactly what
    caused the keystroke-stealing bug: *every* click keyed the window, not
    just a first/special one.

    The actual fix lives one layer up, in `app.py`'s
    `webview.create_window(..., focus=False)` call: pywebview's own
    `WindowHost.canBecomeKeyWindow` (`webview/platforms/cocoa.py`) returns
    exactly that `focus` value, so `focus=False` makes the window structurally
    unable to become key through *any* path -- not this module's calls, not
    pywebview's own `first_show()`/`show()` calls, and not a real click. The
    style mask can therefore drop back to plain `NSWindowStyleMaskBorderless`
    (`_BORDERLESS`) -- the nonactivating-panel bit's only purpose was enabling
    that click-to-key path, which is no longer wanted at all.

    Ordinary mouse *clicks* still work without any of this: `WKWebView`
    overrides `acceptsFirstMouse:` to return `YES` by default, so a real click
    is delivered to the page's DOM as a normal event regardless of key status
    -- that's a separate AppKit mechanism from becoming key. Only continuous
    hover tracking (`mouseover`/`mouseout`) is gated on key status, which is
    why `hover_monitor.py`'s focus-free global mouse monitor remains the only
    way the hover popup can work. `orderFrontRegardless()` (not
    `makeKeyAndOrderFront_()`) makes the window visible/frontmost without even
    attempting to key it. `setAcceptsMouseMovedEvents_` is left set --
    harmless, even though hover is driven externally now.

    Re-applying `setStyleMask_` on every resize (as an earlier version of this
    module did) resets the WKWebView's transparent-background flag that
    pywebview configures once at window-creation time, which otherwise makes
    the window render an opaque gray/white fill the first time it's resized
    taller. Keep this separate from `resize_frame()` so repeated resizes (for
    `show_popup()`/`hide_popup()`/`toggle_collapse()`) never touch it again.
    """

    def _apply() -> None:
        native.setStyleMask_(_BORDERLESS)
        native.setCollectionBehavior_(_ALL_SPACES_STATIONARY)
        native.setLevel_(_BELOW_DOCK_LEVEL)
        native.setAcceptsMouseMovedEvents_(_ACCEPT_MOUSE_MOVED_EVENTS)
        native.orderFrontRegardless()

    AppHelper.callAfter(_apply)


def resize_frame(native: Any, x: float, y: float, width: float, height: int) -> None:
    """Resize and reposition `native`'s frame to `(x, y, width, height)`.

    `(x, y, width)` come from `dock_geometry.StripLayout` -- in
    `"full_width"` mode this spans the whole screen as before, but in
    `"beside_dock"` mode it's whatever's free beside the Dock's icon area,
    which can be anywhere on the screen's bottom edge, not just `x=0`.
    `toggle_collapse()` only ever changes `height`, re-passing the same
    `x`/`y`/`width` from the current layout.

    Passes `display=True` (immediate redisplay) deliberately, even though an
    earlier version tried `display=False` as a best-effort mitigation for a
    one-frame blank flash during resize. That turned out to be the *wrong*
    fix and was reverted: deferring the redisplay also appears to defer the
    WKWebView's own internal relayout (and therefore its JS-visible `resize`
    event, and therefore `reportChipRects()`'s report of each chip's new
    on-screen position -- see `strip.html`), while `native.frame()` reflects
    the new size immediately regardless of the `display` flag. That reopened
    the exact same stale-rect race the resize-triggered `reportChipRects()`
    call was meant to fix in the first place, just narrowed to the deferred-
    redraw window instead of lasting forever -- confirmed via diagnostic
    logging showing the same chip's hover state flapping open/closed
    repeatedly, consistent with the rect staleness being timing-dependent
    rather than fixed outright.

    A later attempt masked the resize behind a brief `setAlphaValue_` dip
    (hide, resize, reveal) to hide a reported one-frame flash on
    `hide_popup()`'s shrink. **Reverted**: it made things visibly worse --
    the whole window blanking out on *every* resize, both grow and shrink,
    is a much more noticeable flicker than whatever the original artifact
    was. Confirmed by direct user report, not assumed. Don't retry this
    specific approach; the cosmetic flash is currently unresolved and lower
    priority than the functional bugs this module already fixes.
    """

    def _apply() -> None:
        frame = AppKit.NSMakeRect(x, y, width, height)
        native.setFrame_display_(frame, _REDISPLAY_IMMEDIATELY)

    AppHelper.callAfter(_apply)


def hide_from_dock() -> None:
    """Drop the Dock tile / Cmd+Tab entry, once the window no longer needs it.

    Must run *after* `prepare_window()`/`resize_frame()` -- empirically (back
    when the window still briefly became key on creation, before `focus=False`
    made that impossible outright), switching to
    `NSApplicationActivationPolicyAccessory` any earlier left the window
    permanently unable to receive hover events. Hover no longer depends on
    key-window status at all (see `hover_monitor.py`), but this ordering is
    kept as-is since it's already verified safe and there's no reason to
    re-test it.
    """

    def _apply() -> None:
        AppKit.NSApplication.sharedApplication().setActivationPolicy_(_ACCESSORY_POLICY)

    AppHelper.callAfter(_apply)


def prepare_popup_window(native: Any) -> None:
    """One-time setup for the hover-detail popup's own, separate window.

    The popup used to be rendered by growing the *strip's own* window taller
    (`resize_frame()` to a fixed expanded height). Confirmed via a
    frame-by-frame screen recording that this makes the window briefly, fully
    transparent (the desktop wallpaper visibly showed through for ~2 frames)
    during the native resize -- consistent with WKWebView's own rendering
    being asynchronous and out-of-process from the window itself, which no
    amount of synchronous `display:`/alpha/CSS tricks on the *window* side
    can reliably wait for (three independent attempts at exactly that were
    all tried and reverted -- see `resize_frame()`'s docstring and the "whole
    strip flashing" bullet in `strip.html`'s AGENTS.md section). Giving the
    popup its own window that only ever moves, resizes-while-still-hidden,
    and shows/hides (`resize_and_position_popup_window()`/
    `show_popup_window()`/`hide_popup_window()` below) means the strip's own
    window never needs to resize for hover at all, which sidesteps the
    problem instead of trying to mask it. The popup window itself *does*
    resize (for dynamic height, see `clamp_popup_height()`), but always while
    still hidden -- there's nothing visible to flash yet at that point.

    Deliberately starts hidden via `orderOut_()` (not `orderFrontRegardless()`
    -- compare `prepare_window()`) since it should only become visible when a
    chip is actually hovered.
    """

    def _apply() -> None:
        native.setStyleMask_(_BORDERLESS)
        native.setCollectionBehavior_(_ALL_SPACES_STATIONARY)
        native.setLevel_(_BELOW_DOCK_LEVEL)
        native.orderOut_(None)

    AppHelper.callAfter(_apply)


def resize_and_position_popup_window(
    native: Any, x: float, y: float, width: float, height: float
) -> None:
    """Resize and move the popup window -- always called *before* showing it.

    `(x, y)` is the AppKit bottom-left-origin screen position of the window's
    own origin (not a CSS top-left point) -- `hover_monitor.py` computes this
    from the hovered chip's rect plus the strip window's own frame, with `y`
    fixed regardless of `height` so the window's bottom edge stays anchored
    just above the strip and only its top edge moves as it grows/shrinks.

    Unlike `resize_frame()` (the strip window), resizing here never risks the
    WKWebView-relayout-lag flash that module's docstring describes: this is
    only ever called while the window is still hidden (`show_popup_window()`
    is a separate call, made afterward) -- there's nothing visible yet for a
    mid-resize rendering gap to show through.
    """

    def _apply() -> None:
        frame = AppKit.NSMakeRect(x, y, width, height)
        native.setFrame_display_(frame, _REDISPLAY_IMMEDIATELY)

    AppHelper.callAfter(_apply)


def show_popup_window(native: Any) -> None:
    def _apply() -> None:
        native.orderFrontRegardless()

    AppHelper.callAfter(_apply)


def hide_popup_window(native: Any) -> None:
    def _apply() -> None:
        native.orderOut_(None)

    AppHelper.callAfter(_apply)


# Fixed size for the "open a new session" project picker window -- unlike the
# hover popup (arbitrary PR/check content), this is always just a search box
# plus a scrollable list, so only *position* needs setting per open, never
# size. Sidesteps the whole WKWebView-relayout-resize-flash class of problems
# `resize_and_position_popup_window()` above has to work around.
PICKER_WIDTH = 340
PICKER_HEIGHT = 440


def prepare_picker_window(native: Any, on_resign_key: Callable[[], None]) -> None:
    """One-time setup for the "open a new session" project picker's own window.

    Unlike every other window in this module, the picker *must* become key --
    it hosts a real text input for live search, which needs genuine keyboard
    focus to receive typed characters at all. This is the one, deliberately
    narrow exception to "the strip must never take focus" (see
    `prepare_window()`): a separate window that doesn't exist most of the
    time, created only on demand, with focus always handed back the instant
    it closes (see `bridge.py`'s `open_project_picker()`/
    `close_project_picker()`).

    `on_resign_key` fires whenever this window stops being key, for *any*
    reason -- an explicit close (which already hides it directly, see
    `bridge.py`'s `close_project_picker()`) or the user clicking a different
    real app while the picker is open, which doesn't go through our own close
    path at all. Firing it redundantly on an already-hidden window is
    harmless; see `bridge.py`'s `on_picker_lost_focus()` for why *this* path
    specifically must never also try to reactivate anything (that would fight
    whatever the user just clicked).

    **The notification block hands `on_resign_key` off to a brand-new
    background thread instead of calling it inline.** `NSNotificationCenter`
    delivers to a block-based observer synchronously, on whatever thread
    posts the notification -- for a window resigning key, that's always
    AppKit's main thread (confirmed the hard way: this used to call
    `on_resign_key()` directly here, which hung the entire app on every close
    and on every click into the picker's own filter field, since clicking
    into an already-key window's text field still routes through the same
    resign/become-key machinery). `on_resign_key` ultimately reaches
    `bridge.py`'s `_hide_picker()`, which calls `Window.evaluate_js()`, and
    pywebview implements that as `AppHelper.callAfter(eval); semaphore
    .acquire()` -- a blocking wait for a callback that can only run once the
    main thread's own run loop is free to process it. Calling that *from* the
    main thread is a guaranteed deadlock: the thread blocks on the semaphore
    and can never get back to its own run loop to unblock itself. This is the
    exact same class of bug `app.py`'s `_watch_screen_changes()` documents
    and fixes the same way -- a plain background thread, not run inline.

    Starts hidden via `orderOut_()`, same as `prepare_popup_window()` --
    should only become visible when the user explicitly opens it.
    """

    def _apply() -> None:
        native.setStyleMask_(_BORDERLESS)
        native.setCollectionBehavior_(_ALL_SPACES_STATIONARY)
        native.setLevel_(_BELOW_DOCK_LEVEL)
        native.orderOut_(None)

        def _handle_resign_key(_notification: Any) -> None:
            threading.Thread(target=on_resign_key, daemon=True).start()

        AppKit.NSNotificationCenter.defaultCenter().addObserverForName_object_queue_usingBlock_(
            "NSWindowDidResignKeyNotification",
            native,
            None,
            _handle_resign_key,
        )

    AppHelper.callAfter(_apply)


def move_picker_window(native: Any, x: float, y: float) -> None:
    """Reposition the picker window -- called every time before showing it.

    Only position, never size (see `PICKER_WIDTH`/`PICKER_HEIGHT` above).
    """

    def _apply() -> None:
        native.setFrameOrigin_(AppKit.NSMakePoint(x, y))

    AppHelper.callAfter(_apply)


def show_picker_window(native: Any) -> None:
    """Show the picker *and* make it key -- the one place in this module that wants that.

    `makeKeyAndOrderFront_()`, not `orderFrontRegardless()` (compare
    `show_popup_window()` above): the whole point of this window is to
    receive real keyboard input, which requires key status.

    Also explicitly activates our own process first, via the same
    `NSRunningApplication.activateWithOptions_` call `reactivate_app()` below
    uses for *other* apps. `makeKeyAndOrderFront_()` alone only makes the
    *window* key -- `hover_monitor.py`'s own docstring already documents that
    becoming key and the *application* activating are two separate AppKit
    mechanisms. For an `NSApplicationActivationPolicyAccessory` process (see
    `hide_from_dock()`) that's never genuinely foreground, a key window on an
    inactive app doesn't reliably receive real keyboard routing -- manual
    testing showed the filter input never actually got keyboard focus, and
    the first click after opening only activated the app instead of
    registering as a real click on a project row (a second click was needed).
    Explicitly activating first, the same direct way `reactivate_app()`
    already does for handing focus *back*, fixes both.
    """

    def _apply() -> None:
        AppKit.NSRunningApplication.currentApplication().activateWithOptions_(0)
        native.makeKeyAndOrderFront_(None)

    AppHelper.callAfter(_apply)


def hide_picker_window(native: Any) -> None:
    def _apply() -> None:
        native.orderOut_(None)

    AppHelper.callAfter(_apply)


def capture_frontmost_app() -> Any:
    """Snapshot whichever app is frontmost right now, to reactivate later.

    A plain read, not a mutation -- safe to call directly without
    `AppHelper.callAfter`, mirroring `hover_monitor.py`'s own direct
    (un-marshaled) read of this same kind of state from its background
    thread. Called right before `show_picker_window()` ever gives our own
    process focus, so this reliably captures the user's *real*
    previously-active app (a terminal, a browser, ...), never us.
    """
    return AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()


def reactivate_app(app: Any) -> None:
    """Hand frontmost status back to `app` (from `capture_frontmost_app()`).

    No-op for `None` -- nothing was captured (e.g. the picker was never
    actually opened). `activateWithOptions_` is a real mutation, so this
    needs the same `AppHelper.callAfter` marshaling as every other AppKit
    call in this module, unlike the plain read above.
    """
    if app is None:
        return

    def _apply() -> None:
        app.activateWithOptions_(0)

    AppHelper.callAfter(_apply)
