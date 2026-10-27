"""Compute the strip's on-screen placement for the given, already-decided mode.

The strip's original behavior (see `app.py`) replaces the Dock entirely:
auto-hide it, take the full screen width. On a large-enough display there's
no need for that trade-off -- the strip can sit directly beside the Dock's
own icon area, matching its height, so neither ever overlaps a window nor
the other.

`compute_strip_layout()` does **not** decide which mode to use -- the mode
(`"full_width"` or `"beside_dock"`) is a plain, user-controlled setting
persisted in `config.strip_mode`, changed only via the strip's right-click
"Switch mode" menu item (`StripBridge.toggle_mode()`). An earlier design had
this module decide automatically, re-verifying on every screen/wake/Dock
event via a background watcher -- torn out after it proved impossible to
make reliable against a real Thunderbolt dock's sleep/wake and monitor
hotplug behavior; the Dock's own Accessibility/auto-hide state could not be
measured consistently enough for any retry schedule to be trustworthy. This
module now only answers "where exactly, for the mode I've already been
told to use" -- called once at startup and once per manual mode switch,
never on a timer or in response to any notification.

Two pieces of information are needed, from two different APIs:

1. **The Dock's reserved height** -- from `NSScreen.frame()` vs
   `NSScreen.visibleFrame()`. A Dock that isn't auto-hidden reserves a
   margin at its edge (bottom -- the only orientation this module
   supports); the difference between the two rects is exactly that
   reservation. Confirmed empirically: with Dock auto-hide *on*, this
   reports zero -- "beside the Dock" only makes sense when auto-hide is
   off in the first place, which is this mode's whole premise.

2. **The Dock's actual icon-area bounds**, not just its reserved height --
   `visibleFrame` reserves the Dock's *full screen width* as a margin band,
   even though the icons are horizontally centered and much narrower.
   Confirmed via `CGWindowListCopyWindowInfo`: the Dock's own on-screen
   "window" is reported as the full screen size, not a tight bounding box
   around the icons -- that API cannot answer "where does the icon cluster
   actually start/end." The only API that can is the Accessibility API
   (`AXUIElement`): the Dock process exposes exactly one `AXList` child
   (confirmed live on this machine) whose `AXPosition`/`AXSize` attributes
   are the icon area's tight bounding box.

The AX functions are called directly via `ctypes` against the HIServices
sub-framework rather than adding `pyobjc-framework-ApplicationServices` as a
new dependency -- the small, stable surface needed here
(`AXIsProcessTrusted`, `AXUIElementCreateApplication`,
`AXUIElementCopyAttributeValue`, `AXValueGetValue`, plus a couple of
CoreFoundation helpers to build/read `CFString`/`CFArray` values) was
confirmed working against the real Dock process on this machine.

**Coordinate systems, and why they matter across multiple monitors**:
`AXPosition` reports in the same coordinate family as `CGWindowBounds` -- a
single *global* space spanning every display, top-left origin, with
`(0, 0)` at the top-left corner of the display that owns the menu bar
(always `NSScreen.screens()[0]`). Confirmed by cross-checking a
`CGWindowListCopyWindowInfo` reading of the Dock's (full-screen-sized)
window while the Dock lived on the *second* monitor: its reported bounds
exactly matched that monitor's own `NSScreen.frame()` origin, not `(0, 0)`
-- there is no implicit per-screen coordinate reset. `NSScreen.frame()`
itself is bottom-left origin ("AppKit coordinates"). Converting from one to
the other requires anchoring on the *primary* screen's frame specifically
(`main.origin.y + main.size.height` is the AppKit-coordinate Y position of
the CG global origin), not the screen the Dock happens to be on.

Falls back to `"full_width"` (the strip's original, Dock-replacing
behavior) whenever any part of this can't be determined: Accessibility
permission not granted, Dock process not found, Dock oriented left/right
(out of scope for now), Dock currently auto-hidden, or not enough free
space beside the icon area.
"""

from __future__ import annotations

import ctypes
import logging
from dataclasses import dataclass
from typing import Any, Literal
lazy import subprocess

from webview.screen import Screen
lazy import AppKit
lazy import Quartz
lazy import webview

_logger = logging.getLogger(__name__)

StripMode = Literal["beside_dock", "full_width"]

# Minimum free width beside the Dock's icon area to bother with beside-dock
# mode at all -- below this, even the most compact chips wouldn't fit more
# than a couple of sessions. Roughly 4-5 compact chips' worth.
_MIN_BESIDE_DOCK_WIDTH = 400.0
# Gap between the Dock's icon area and the strip's near edge.
_SIDE_MARGIN = 8.0
# Gap between the strip's *outer* edges (the screen's own bottom edge, and
# whichever side isn't adjacent to the Dock) and the screen -- the real Dock
# floats with a visible margin on every exposed side rather than sitting
# flush against the screen edge, and the strip is meant to look the same way.
_SCREEN_EDGE_MARGIN = 4.0
# How close the Dock's icon-area bottom edge has to be to its screen's own
# bottom edge to count as "bottom-oriented". A belt-and-suspenders check
# alongside the authoritative `defaults read com.apple.dock orientation`
# query below -- a Dock with very few icons could otherwise produce a
# bounding box whose shape alone is ambiguous.
_BOTTOM_DOCK_Y_TOLERANCE = 100.0

_DEFAULTS_BIN = "/usr/bin/defaults"
_HI_SERVICES_PATH = (
    "/System/Library/Frameworks/ApplicationServices.framework/"
    "Frameworks/HIServices.framework/HIServices"
)
_CORE_FOUNDATION_PATH = (
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
)
_CF_STRING_ENCODING_UTF8 = 0x08000100
_AX_VALUE_CG_POINT_TYPE = 1
_AX_VALUE_CG_SIZE_TYPE = 2


class _CGPoint(ctypes.Structure):
    _fields_ = (("x", ctypes.c_double), ("y", ctypes.c_double))


class _CGSize(ctypes.Structure):
    _fields_ = (("width", ctypes.c_double), ("height", ctypes.c_double))


@dataclass(frozen=True)
class StripLayout:
    """Where and how big the strip window should be, and on which screen."""

    mode: StripMode
    screen: Screen
    x: float
    y: float
    width: float
    height: int


# Mutable container rather than a plain module global -- avoids a `global`
# statement for what's just a one-time memoization of the loaded libraries.
_ax_libs_cache: dict[str, tuple[Any, Any]] = {}


def _load_ax_libs() -> tuple[Any, Any] | None:
    """Load and configure the two ctypes libraries needed for AX queries.

    Cached after the first successful call -- loading a dylib is cheap, but
    there's no reason to repeat the `restype`/`argtypes` setup on every
    screen-change recomputation.
    """
    if "libs" in _ax_libs_cache:
        return _ax_libs_cache["libs"]
    try:
        hi = ctypes.cdll.LoadLibrary(_HI_SERVICES_PATH)
        cf = ctypes.cdll.LoadLibrary(_CORE_FOUNDATION_PATH)
    except OSError:
        _logger.debug("could not load HIServices/CoreFoundation", exc_info=True)
        return None
    hi.AXIsProcessTrusted.restype = ctypes.c_bool
    hi.AXIsProcessTrusted.argtypes = []
    hi.AXUIElementCreateApplication.restype = ctypes.c_void_p
    hi.AXUIElementCreateApplication.argtypes = [ctypes.c_int32]
    hi.AXUIElementCopyAttributeValue.restype = ctypes.c_int32
    hi.AXUIElementCopyAttributeValue.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    hi.AXValueGetValue.restype = ctypes.c_bool
    hi.AXValueGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p]
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_int32,
    ]
    cf.CFArrayGetCount.restype = ctypes.c_long
    cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
    cf.CFStringGetCString.restype = ctypes.c_bool
    cf.CFStringGetCString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_long,
        ctypes.c_int32,
    ]
    _ax_libs_cache["libs"] = (hi, cf)
    return _ax_libs_cache["libs"]


def _cfstr(cf: Any, value: str) -> Any:
    return cf.CFStringCreateWithCString(
        None, value.encode("utf-8"), _CF_STRING_ENCODING_UTF8
    )


def _cfstring_value(cf: Any, ref: Any) -> str:
    buf = ctypes.create_string_buffer(256)
    if not cf.CFStringGetCString(ref, buf, len(buf), _CF_STRING_ENCODING_UTF8):
        return ""
    return buf.value.decode("utf-8")


def _dock_pid() -> int | None:
    """Find the Dock process's PID via its on-screen window, not `NSRunningApplication`.

    `AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_
    ("com.apple.dock")` is the obvious API for this, and is what this used to
    call -- but confirmed live (direct side-by-side comparison logged from a
    real running strip) that it can unreliably return an *empty* list once a
    pywebview/WKWebView app's own windows are fully up, even though the Dock
    process is obviously running. `CGWindowListCopyWindowInfo` -- a Core
    Graphics/WindowServer level query, unrelated to `NSRunningApplication`'s
    own "list of GUI applications" bookkeeping -- found the correct PID in
    that exact same moment. `compute_strip_layout()` is now only ever called
    from `start_strip()`'s initial, pre-window measurement anyway (see the
    module docstring), where this was never observed to fail either way --
    kept as the more robust choice regardless.
    """
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID
    )
    for w in windows:
        if w.get("kCGWindowOwnerName") == "Dock":
            return int(w["kCGWindowOwnerPID"])
    return None


def _find_dock_list(hi: Any, cf: Any, app_elem: Any) -> Any | None:
    """Find the Dock process's `AXList` child -- the bar itself.

    Takes the first child with role `AXList` rather than assuming index 0,
    in case a future macOS version adds siblings (confirmed on this machine:
    exactly one child, and it is the `AXList`).
    """
    children_ptr = ctypes.c_void_p()
    err = hi.AXUIElementCopyAttributeValue(
        app_elem, _cfstr(cf, "AXChildren"), ctypes.byref(children_ptr)
    )
    if err != 0 or children_ptr.value is None:
        return None
    count = cf.CFArrayGetCount(children_ptr)
    for i in range(count):
        candidate = cf.CFArrayGetValueAtIndex(children_ptr, i)
        role_ptr = ctypes.c_void_p()
        role_err = hi.AXUIElementCopyAttributeValue(
            candidate, _cfstr(cf, "AXRole"), ctypes.byref(role_ptr)
        )
        if role_err == 0 and _cfstring_value(cf, role_ptr) == "AXList":
            return candidate
    return None


def _ax_position_and_size(
    hi: Any, cf: Any, element: Any
) -> tuple[_CGPoint, _CGSize] | None:
    pos_val = ctypes.c_void_p()
    size_val = ctypes.c_void_p()
    if (
        hi.AXUIElementCopyAttributeValue(
            element, _cfstr(cf, "AXPosition"), ctypes.byref(pos_val)
        )
        != 0
    ):
        return None
    if (
        hi.AXUIElementCopyAttributeValue(
            element, _cfstr(cf, "AXSize"), ctypes.byref(size_val)
        )
        != 0
    ):
        return None
    point = _CGPoint()
    size = _CGSize()
    if not hi.AXValueGetValue(pos_val, _AX_VALUE_CG_POINT_TYPE, ctypes.byref(point)):
        return None
    if not hi.AXValueGetValue(size_val, _AX_VALUE_CG_SIZE_TYPE, ctypes.byref(size)):
        return None
    return point, size


def _dock_icon_area_cg(pid: int) -> tuple[float, float, float, float] | None:
    """Return the Dock's icon-area bounding box `(x, y, width, height)`.

    In CG/AX global coordinates: top-left origin, spanning every display.
    `None` if Accessibility permission is missing, the Dock's AX tree
    doesn't look as expected, or any AX call fails.
    """
    libs = _load_ax_libs()
    if libs is None:
        return None
    hi, cf = libs
    if not hi.AXIsProcessTrusted():
        return None
    app_elem = hi.AXUIElementCreateApplication(pid)
    dock_list = _find_dock_list(hi, cf, app_elem)
    if dock_list is None:
        return None
    position_and_size = _ax_position_and_size(hi, cf, dock_list)
    if position_and_size is None:
        return None
    point, size = position_and_size
    return point.x, point.y, size.width, size.height


def _dock_orientation() -> str | None:
    """Read the Dock's screen-edge orientation ("bottom"/"left"/"right").

    `None` both when the lookup fails and when the user has never
    explicitly changed it -- `defaults read` finds no key in that case, but
    the actual factory default is "bottom", so callers should treat `None`
    the same as `"bottom"`, not as "unknown, give up".
    """
    result = subprocess.run(
        [_DEFAULTS_BIN, "read", "com.apple.dock", "orientation"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _full_width_layout(screen: Screen, height: int) -> StripLayout:
    margin = _SCREEN_EDGE_MARGIN
    return StripLayout(
        mode="full_width",
        screen=screen,
        x=screen.x + margin,
        y=screen.y + margin,
        width=screen.width - 2 * margin,
        height=height,
    )


def _dock_bounds_in_appkit_space(
    icon_area: tuple[float, float, float, float], main_ns_screen: Any
) -> tuple[float, float, float]:
    """Convert the icon area's CG (top-left) bounds to AppKit (bottom-left) coordinates.

    Returns `(dock_left, dock_right, dock_bottom_appkit_y)`. `dock_left`/
    `dock_right` don't need conversion (X doesn't flip); `dock_bottom_appkit_y`
    is anchored on the *primary* screen's frame, not whichever screen the
    Dock itself ends up on -- see the module docstring.
    """
    cg_x, cg_y, icon_width, icon_height = icon_area
    main_frame = main_ns_screen.frame()
    global_top_appkit_y = main_frame.origin.y + main_frame.size.height
    dock_left = cg_x
    dock_right = cg_x + icon_width
    dock_bottom_appkit_y = global_top_appkit_y - cg_y - icon_height
    return dock_left, dock_right, dock_bottom_appkit_y


def _locate_dock_screen(
    ns_screens: list[Any], dock_left: float, dock_bottom_appkit_y: float
) -> int | None:
    """Which `NSScreen` (by index) does the Dock bar actually sit on?"""
    for i, ns_screen in enumerate(ns_screens):
        frame = ns_screen.frame()
        if (
            frame.origin.x <= dock_left < frame.origin.x + frame.size.width
            and frame.origin.y
            <= dock_bottom_appkit_y
            < frame.origin.y + frame.size.height
        ):
            return i
    return None


def _dock_pid_and_icon_area() -> tuple[int, tuple[float, float, float, float]] | None:
    pid = _dock_pid()
    if pid is None:
        return None
    icon_area = _dock_icon_area_cg(pid)
    if icon_area is None:
        return None
    return pid, icon_area


@dataclass(frozen=True)
class _DockPlacement:
    screen: Screen
    screen_frame: Any
    dock_left: float
    dock_right: float
    dock_height: int


def _resolve_dock_placement() -> _DockPlacement | None:
    """Find the Dock's screen, icon-area edges, and reserved height -- or `None` if unavailable."""
    found = _dock_pid_and_icon_area()
    if found is None:
        return None
    _pid, icon_area = found
    orientation = _dock_orientation()
    if orientation not in {None, "bottom"}:
        return None
    ns_screens = AppKit.NSScreen.screens()
    if not ns_screens:
        return None
    dock_left, dock_right, dock_bottom_appkit_y = _dock_bounds_in_appkit_space(
        icon_area, ns_screens[0]
    )
    screen_index = _locate_dock_screen(ns_screens, dock_left, dock_bottom_appkit_y)
    if screen_index is None or screen_index >= len(webview.screens):
        return None
    screen_frame = ns_screens[screen_index].frame()
    if abs(dock_bottom_appkit_y - screen_frame.origin.y) > _BOTTOM_DOCK_Y_TOLERANCE:
        return None
    dock_height = round(
        ns_screens[screen_index].visibleFrame().origin.y - screen_frame.origin.y
    )
    return _DockPlacement(
        screen=webview.screens[screen_index],
        screen_frame=screen_frame,
        dock_left=dock_left,
        dock_right=dock_right,
        dock_height=dock_height,
    )


def _beside_dock_layout(placement: _DockPlacement) -> StripLayout | None:
    """Pick the left side of the Dock's icon area if there's room, else the right.

    Preferring left is a user preference (not a measurement-driven choice
    the way the old right-preferring tie-break was) -- `None` if neither
    side has `_MIN_BESIDE_DOCK_WIDTH` free.
    """
    frame = placement.screen_frame
    space_right = (
        (frame.origin.x + frame.size.width) - placement.dock_right - _SIDE_MARGIN
    )
    space_left = placement.dock_left - frame.origin.x - _SIDE_MARGIN
    # `_SCREEN_EDGE_MARGIN` insets only the strip's *outer horizontal* edge
    # (whichever side isn't already inset by `_SIDE_MARGIN` from the Dock) --
    # `y`/`height` deliberately get NO extra margin and reuse `dock_height`
    # (`visibleFrame`'s own reserved-space measurement) exactly as-is: that
    # measurement already reflects the real Dock's own exact footprint from
    # the screen's true bottom edge (whatever margin *it* floats with, if
    # any, is already baked into `visibleFrame`), so copying it verbatim is
    # what makes the strip match the Dock's height and bottom position
    # pixel-for-pixel. Adding our own extra vertical margin on top of that
    # (an earlier version did) made the strip sit measurably higher *and*
    # shorter than the real Dock instead of lining up with it.
    if space_left >= _MIN_BESIDE_DOCK_WIDTH:
        return StripLayout(
            mode="beside_dock",
            screen=placement.screen,
            x=frame.origin.x + _SCREEN_EDGE_MARGIN,
            y=frame.origin.y,
            width=space_left - _SCREEN_EDGE_MARGIN,
            height=placement.dock_height,
        )
    if space_right >= _MIN_BESIDE_DOCK_WIDTH:
        return StripLayout(
            mode="beside_dock",
            screen=placement.screen,
            x=placement.dock_right + _SIDE_MARGIN,
            y=frame.origin.y,
            width=space_right - _SCREEN_EDGE_MARGIN,
            height=placement.dock_height,
        )
    return None


def compute_strip_layout(*, mode: StripMode, full_width_height: int) -> StripLayout:
    """Compute the on-screen placement for the given, already-decided mode.

    Does not decide *between* modes -- see the module docstring for why.
    `"full_width"` is trivial and can never fail (just the primary screen's
    own width, no Dock measurement at all). `"beside_dock"` measures the real
    Dock's position/size once; if that's not possible right now
    (Accessibility permission missing, Dock process not found, not enough
    room beside it, ...) it falls back to full-width geometry for this one
    computation -- a one-time degradation of *this call's result*, not an
    automatic mode change: the caller decides whether/what to persist based
    on the `StripLayout.mode` actually returned.
    """
    if mode == "full_width":
        return _full_width_layout(webview.screens[0], full_width_height)
    placement = _resolve_dock_placement()
    if placement is None:
        return _full_width_layout(webview.screens[0], full_width_height)
    if placement.dock_height <= 0:
        return _full_width_layout(placement.screen, full_width_height)
    return _beside_dock_layout(placement) or _full_width_layout(
        placement.screen, full_width_height
    )
