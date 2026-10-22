"""Global macOS hotkey registration via Carbon's HIToolbox Event Manager.

`RegisterEventHotKey`/`InstallEventHandler` are the only supported way to bind
a system-wide hotkey on macOS without requesting Accessibility or Input
Monitoring permission -- confirmed against Apple's own docs and multiple
independent reports: an `NSEvent` global monitor needs Accessibility to
receive key events at all, and a `CGEventTap` needs Input Monitoring. These
functions are part of the deprecated Carbon framework and are no longer
wrapped by PyObjC's own bindings, but they remain present in the OS and
reachable via `objc.createFrameworkDirAndGetattr()`, pointed directly at the
HIToolbox framework bundle inside Carbon.framework.

The bridging technique and the function-signature/struct-type metadata in
`_load_hitoolbox()` below are ported from QuickMacHotKey
(https://github.com/glyph/QuickMacHotKey, MIT licensed, Copyright (c) 2023
Glyph Lefkowitz) rather than hand-derived -- getting even one byte of a C
function's type-encoding string wrong here risks a crash, not a catchable
Python exception, so this reuses a verified-working reference instead of
guessing at the Carbon Event Manager's C ABI.

Like every other AppKit-touching call in this package (see `native.py`'s
module docstring), `RegisterEventHotKey`/`InstallEventHandler` must run on
the main thread -- they're dispatched through the same run loop AppKit's own
event system uses -- so `register_hotkey()` marshals its setup through
`AppHelper.callAfter`, exactly like `native.py` does for every window
mutation. The fired hotkey callback itself also arrives on the main thread;
it hands off to a new background thread before calling the registered
callback, mirroring `native.py`'s `prepare_picker_window()`/
`_handle_resign_key` pattern -- the callback here is `StripBridge
.toggle_project_picker`, which can reach `Window.evaluate_js()`
(`AppHelper.callAfter(eval); semaphore.acquire()`), and calling that
synchronously from the main thread would deadlock exactly the way that
module's docstring already documents.
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING, Any
lazy import contextlib
lazy import threading

lazy import objc
lazy from PyObjCTools import AppHelper

if TYPE_CHECKING:
    from collections.abc import Callable

# Carbon's classic "OSType" four-character-code convention -- distinguishes
# pyworkon's own hotkey registration from any other app's, though in practice
# each process only ever receives events for hotkeys it registered itself:
# both `RegisterEventHotKey` and `InstallEventHandler` below target
# `GetEventDispatcherTarget()`, which is scoped to this process.
_HOTKEY_SIGNATURE: int = struct.unpack("@I", b"PYWK")[0]
_HOTKEY_ID: int = 1  # Only one global hotkey is ever registered: the picker toggle.

_MODIFIER_KEYS: dict[str, int] = {
    "cmd": 0x0100,
    "command": 0x0100,
    "shift": 0x0200,
    "option": 0x0800,
    "alt": 0x0800,
    "ctrl": 0x1000,
    "control": 0x1000,
}

# Virtual keycodes (`kVK_*`), stable across macOS versions -- ported from the
# same verified QuickMacHotKey source as the HIToolbox bridging below.
_VIRTUAL_KEYS: dict[str, int] = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04, "g": 0x05,
    "z": 0x06, "x": 0x07, "c": 0x08, "v": 0x09, "b": 0x0B, "q": 0x0C,
    "w": 0x0D, "e": 0x0E, "r": 0x0F, "y": 0x10, "t": 0x11,
    "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17,
    "equal": 0x18, "9": 0x19, "7": 0x1A, "minus": 0x1B, "8": 0x1C,
    "0": 0x1D, "rightbracket": 0x1E, "o": 0x1F, "u": 0x20,
    "leftbracket": 0x21, "i": 0x22, "p": 0x23, "l": 0x25, "j": 0x26,
    "quote": 0x27, "k": 0x28, "semicolon": 0x29, "backslash": 0x2A,
    "comma": 0x2B, "slash": 0x2C, "n": 0x2D, "m": 0x2E, "period": 0x2F,
    "tab": 0x30, "space": 0x31, "grave": 0x32, "delete": 0x33,
    "escape": 0x35, "return": 0x24, "enter": 0x24,
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76, "f5": 0x60,
    "f6": 0x61, "f7": 0x62, "f8": 0x64, "f9": 0x65, "f10": 0x6D,
    "f11": 0x67, "f12": 0x6F,
    "left": 0x7B, "right": 0x7C, "down": 0x7D, "up": 0x7E,
}  # fmt: skip


def parse_hotkey(spec: str) -> tuple[int, int]:
    """Parse e.g. `"ctrl+option+space"` into `(modifier_mask, virtual_keycode)`.

    Requires at least one modifier -- a bare, unmodified key (e.g. just
    `"space"`) would otherwise globally intercept every press of that key
    across the whole system, which is never what a hotkey config is for.
    """
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        msg = f"Empty hotkey spec: {spec!r}"
        raise ValueError(msg)
    *modifier_names, key_name = parts
    if key_name not in _VIRTUAL_KEYS:
        msg = f"Unknown key {key_name!r} in hotkey spec {spec!r}"
        raise ValueError(msg)
    if not modifier_names:
        msg = f"Hotkey spec {spec!r} has no modifier key"
        raise ValueError(msg)
    modifiers = 0
    for name in modifier_names:
        if name not in _MODIFIER_KEYS:
            msg = f"Unknown modifier {name!r} in hotkey spec {spec!r}"
            raise ValueError(msg)
        modifiers |= _MODIFIER_KEYS[name]
    return modifiers, _VIRTUAL_KEYS[key_name]


def _load_hitoolbox() -> dict[str, Any]:
    """Bridge the subset of Carbon's HIToolbox Event Manager this module needs.

    See this module's docstring for why this is ported verbatim from
    QuickMacHotKey's `_MinimalHIToolbox` rather than hand-derived: these byte
    strings are raw C type encodings (argument/return types, struct layouts,
    in/out parameter markers) that PyObjC needs to correctly marshal calls
    into a framework it has no built-in bindings for. `EventHotKeyID`'s
    struct type is registered here (for `RegisterEventHotKey`'s embedded
    `{EventHotKeyID=II}` argument type) even though it's never extracted into
    the returned namespace -- callers pass a plain 2-tuple instead, which
    PyObjC accepts anywhere a registered 2-field struct is expected, mirroring
    QuickMacHotKey's own usage.
    """
    misc = {
        "EventTypeSpec": objc.createStructType(
            "EventTypeSpec", b"{EventTypeSpec=LL}", ["eventClass", "eventKind"]
        ),
        "EventHotKeyID": objc.createStructType(
            "EventHotKeyID", b"{EventHotKeyID=II}", ["signature", "id"]
        ),
        "EventHotKeyRef": objc.createOpaquePointerType(
            "EventHotKeyRef", b"^{OpaqueEventHotKeyRef=}"
        ),
        "EventTargetRef": objc.createOpaquePointerType(
            "EventTargetRef", b"^{OpaqueEventTargetRef=}"
        ),
        "EventHandlerRef": objc.createOpaquePointerType(
            "EventHandlerRef", b"^{OpaqueEventHandlerRef=}"
        ),
        "EventHandlerCallRef": objc.createOpaquePointerType(
            "EventHandlerCallRef", b"^{OpaqueEventHandlerCallRef=}"
        ),
        "EventRef": objc.createOpaquePointerType("EventRef", b"^{OpaqueEventRef=}"),
    }
    functions = {
        "RegisterEventHotKey": (
            b"iII{EventHotKeyID=II}^{OpaqueEventTargetRef=}I^^{OpaqueEventHotKeyRef}",
            "",
            {"arguments": {5: {"type_modifier": "o", "null_accepted": False}}},
        ),
        "UnregisterEventHotKey": (b"i^{OpaqueEventHotKeyRef}",),
        "GetEventDispatcherTarget": (b"^{OpaqueEventTargetRef=}",),
        "InstallEventHandler": (
            b"i^{OpaqueEventTargetRef=}^?L^{EventTypeSpec=II}^v^^{OpaqueEventHandlerRef}",
            "",
            {
                "arguments": {
                    1: {
                        "callable_retained": True,
                        "callable": {
                            "retval": {"type": b"i"},
                            "arguments": {
                                0: {"type": "^{OpaqueEventHandlerCallRef=}"},
                                1: {"type": "^{OpaqueEventRef=}"},
                                2: {"type": "^v"},
                            },
                        },
                    },
                    3: {"type_modifier": b"n", "c_array_length_in_arg": 2},
                    5: {"type_modifier": b"o", "null_accepted": False},
                }
            },
        ),
        "GetEventParameter": (
            b"i^{OpaqueEventRef=}II^IQ^Q^v",
            "",
            {
                "arguments": {
                    3: {"type_modifier": "o"},
                    5: {"type_modifier": "o"},
                    6: {"type_modifier": "o", "c_array_length_in_arg": 4},
                }
            },
        ),
    }
    enums = (
        "$typeEventHotKeyID@1751869796"
        "$kEventClassKeyboard@1801812322"
        "$kEventHotKeyPressed@5"
        "$kEventParamDirectObject@757935405"
        "$"
    )
    metadict = {"misc": misc, "functions": functions, "enums": enums}
    namespace: dict[str, Any] = {}
    _dir_func, getattr_func = objc.createFrameworkDirAndGetattr(
        name="HIToolbox",
        frameworkIdentifier="com.apple.HIToolbox",
        frameworkPath=objc.pathForFramework(
            "/System/Library/Frameworks/"
            "Carbon.framework/Versions/Current/Frameworks/"
            "HIToolbox.framework"
        ),
        globals_dict=namespace,
        inline_list=None,
        parents=(),
        metadict=metadict,
    )
    # `createFrameworkDirAndGetattr()` merges `metadict["misc"]` straight into
    # `namespace` eagerly (confirmed by reading `objc/_lazyimport.py`), so
    # "EventTypeSpec" is already present here -- only `functions`/`enums`
    # entries are resolved lazily through `getattr_func()`.
    for name in (
        "RegisterEventHotKey",
        "UnregisterEventHotKey",
        "GetEventDispatcherTarget",
        "InstallEventHandler",
        "GetEventParameter",
        "typeEventHotKeyID",
        "kEventClassKeyboard",
        "kEventHotKeyPressed",
        "kEventParamDirectObject",
    ):
        namespace[name] = getattr_func(name)
    return namespace


class _HotkeyRegistry:
    """Owns the HIToolbox bridge and the single registered hotkey's mutable state.

    A class instead of module-level globals mutated via `global` -- same
    reasoning as `StripBridge`/`HoverMonitor` elsewhere in this package:
    encapsulated instance state instead of module-level mutable globals.
    """

    def __init__(self) -> None:
        self._hitoolbox: dict[str, Any] | None = None
        self._event_handler_installed = False
        self._active_callback: Callable[[], None] | None = None
        self._active_hotkey_ref: Any = None

    def _hit(self, name: str) -> Any:
        if self._hitoolbox is None:
            msg = "HIToolbox bridge not loaded yet"
            raise RuntimeError(msg)
        return self._hitoolbox[name]

    def _install_event_handler(self) -> None:
        """One-time setup: install the single shared Carbon hotkey event handler.

        Only one hotkey is ever registered (see `_HOTKEY_ID`), but the
        dispatch still checks the fired event's own `EventHotKeyID` against
        it rather than unconditionally firing, mirroring the verified
        reference implementation's design and leaving no assumption that this
        process's Carbon event target could somehow receive another hotkey's
        event.
        """
        if self._event_handler_installed:
            return

        hot_key_spec = self._hit("EventTypeSpec")(
            eventClass=self._hit("kEventClassKeyboard"),
            eventKind=self._hit("kEventHotKeyPressed"),
        )

        @objc.callbackFor(self._hit("InstallEventHandler"))
        def _on_hotkey_event(_call_ref: Any, event: Any, _user_data: Any) -> int:
            with contextlib.suppress(Exception):
                _result, _actual_type, _actual_size, raw = self._hit(
                    "GetEventParameter"
                )(
                    event,
                    self._hit("kEventParamDirectObject"),
                    self._hit("typeEventHotKeyID"),
                    None,
                    8,
                    None,
                    None,
                )
                signature, hotkey_id = struct.unpack("@II", raw)
                if (
                    signature == _HOTKEY_SIGNATURE
                    and hotkey_id == _HOTKEY_ID
                    and self._active_callback is not None
                ):
                    threading.Thread(target=self._active_callback, daemon=True).start()
            return 0

        result, _handler_ref = self._hit("InstallEventHandler")(
            self._hit("GetEventDispatcherTarget")(),
            _on_hotkey_event,
            1,
            [hot_key_spec],
            None,
            None,
        )
        if result != 0:
            msg = f"InstallEventHandler failed with OSStatus {result}"
            raise RuntimeError(msg)
        self._event_handler_installed = True

    def register(
        self, keycode: int, modifiers: int, callback: Callable[[], None]
    ) -> None:
        """Runs on the main thread (see `register_hotkey()`'s `AppHelper.callAfter`)."""
        if self._hitoolbox is None:
            self._hitoolbox = _load_hitoolbox()
        self._install_event_handler()
        self._active_callback = callback
        hotkey_id = (_HOTKEY_SIGNATURE, _HOTKEY_ID)
        result, hotkey_ref = self._hit("RegisterEventHotKey")(
            keycode,
            modifiers,
            hotkey_id,
            self._hit("GetEventDispatcherTarget")(),
            0,
            None,
        )
        if result == 0:
            self._active_hotkey_ref = hotkey_ref

    def unregister(self) -> None:
        """Runs on the main thread (see `register_hotkey()`'s `AppHelper.callAfter`)."""
        if self._active_hotkey_ref is not None:
            self._hit("UnregisterEventHotKey")(self._active_hotkey_ref)
            self._active_hotkey_ref = None
        self._active_callback = None


_registry = _HotkeyRegistry()


def register_hotkey(
    hotkey_str: str, callback: Callable[[], None]
) -> Callable[[], None]:
    """Register a global hotkey; `callback` runs (off the main thread) when it's pressed.

    `hotkey_str` is parsed eagerly (`parse_hotkey()` raises `ValueError`
    synchronously on a bad spec, before anything is scheduled), but the actual
    Carbon registration is deferred via `AppHelper.callAfter` since it must
    run on the main thread (see this module's docstring). Returns an
    `unregister` callable.
    """
    modifiers, keycode = parse_hotkey(hotkey_str)
    AppHelper.callAfter(_registry.register, keycode, modifiers, callback)

    def _unregister() -> None:
        AppHelper.callAfter(_registry.unregister)

    return _unregister
