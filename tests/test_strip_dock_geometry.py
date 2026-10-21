"""Tests for beside-the-Dock layout detection (`dock_geometry.py`).

The AX/ctypes calls themselves aren't mocked at the ctypes level -- instead,
the module's own seams (`_dock_pid()`, `_dock_icon_area_cg()`,
`_dock_orientation()`) are monkeypatched directly, and `AppKit`/`webview`
are replaced with small fakes mirroring the shapes `native.py`'s and
`hover_monitor.py`'s tests already use.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from pyworkon.interfaces.strip import dock_geometry as dock_geometry_module
from pyworkon.interfaces.strip.dock_geometry import compute_strip_layout

# macOS-only -- absent on Linux CI, where `pywebview` installs without its
# Cocoa backend deps. `dock_geometry.py` imports `AppKit` lazily, so merely
# importing this test module doesn't fail -- but the `fake_appkit` fixture's
# `monkeypatch.setattr(dock_geometry_module, "AppKit", fake)` does a
# `getattr` first (to record the value to restore later), which *forces*
# that lazy import to resolve. Skip up front instead of failing at fixture
# setup for every test in this module.
pytest.importorskip("AppKit")

_FULL_WIDTH_HEIGHT = 56


@dataclass
class _FakeScreen:
    x: int
    y: int
    width: int
    height: int


@dataclass
class _FakePoint:
    x: float
    y: float


@dataclass
class _FakeSize:
    width: float
    height: float


@dataclass
class _FakeFrame:
    origin: _FakePoint
    size: _FakeSize


class _FakeNSScreen:
    def __init__(
        self, frame: _FakeFrame, visible_frame: _FakeFrame | None = None
    ) -> None:
        self._frame = frame
        self._visible_frame = visible_frame or frame

    def frame(self) -> _FakeFrame:
        return self._frame

    def visibleFrame(self) -> _FakeFrame:  # ruff: ignore[invalid-function-name] -- matches the real AppKit selector
        return self._visible_frame


@pytest.fixture
def fake_appkit(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock()
    monkeypatch.setattr(dock_geometry_module, "AppKit", fake)
    return fake


@pytest.fixture
def fake_webview(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock()
    monkeypatch.setattr(dock_geometry_module, "webview", fake)
    return fake


def _set_single_screen(
    fake_appkit: MagicMock,
    fake_webview: MagicMock,
    *,
    width: float = 3840,
    height: float = 2160,
    dock_reserved_height: int = 0,
) -> None:
    """One screen at the origin, optionally with a non-auto-hidden bottom Dock."""
    frame = _FakeFrame(origin=_FakePoint(0, 0), size=_FakeSize(width, height))
    visible_frame = _FakeFrame(
        origin=_FakePoint(0, dock_reserved_height),
        size=_FakeSize(width, height - dock_reserved_height),
    )
    fake_appkit.NSScreen.screens.return_value = [_FakeNSScreen(frame, visible_frame)]
    fake_webview.screens = [_FakeScreen(x=0, y=0, width=int(width), height=int(height))]


def _patch_dock(
    monkeypatch: pytest.MonkeyPatch,
    *,
    pid: int | None = 1234,
    icon_area: tuple[float, float, float, float] | None = (
        1154.0,
        2072.0,
        1532.0,
        78.0,
    ),
    orientation: str | None = "bottom",
) -> None:
    monkeypatch.setattr(dock_geometry_module, "_dock_pid", lambda: pid)
    monkeypatch.setattr(
        dock_geometry_module, "_dock_icon_area_cg", lambda _pid: icon_area
    )
    monkeypatch.setattr(dock_geometry_module, "_dock_orientation", lambda: orientation)


def test_falls_back_to_full_width_when_dock_process_not_found(
    fake_appkit: MagicMock, fake_webview: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_single_screen(fake_appkit, fake_webview, dock_reserved_height=84)
    _patch_dock(monkeypatch, pid=None)

    layout = compute_strip_layout(full_width_height=_FULL_WIDTH_HEIGHT)

    assert layout.mode == "full_width"
    assert layout.width == pytest.approx(3840 - 2 * 4.0)
    assert layout.height == _FULL_WIDTH_HEIGHT


def test_falls_back_to_full_width_when_icon_area_unavailable(
    fake_appkit: MagicMock, fake_webview: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E.g. Accessibility permission not granted."""
    _set_single_screen(fake_appkit, fake_webview, dock_reserved_height=84)
    _patch_dock(monkeypatch, icon_area=None)

    layout = compute_strip_layout(full_width_height=_FULL_WIDTH_HEIGHT)

    assert layout.mode == "full_width"


@pytest.mark.parametrize("orientation", ["left", "right"])
def test_falls_back_to_full_width_for_non_bottom_dock_orientation(
    fake_appkit: MagicMock,
    fake_webview: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    orientation: str,
) -> None:
    _set_single_screen(fake_appkit, fake_webview, dock_reserved_height=84)
    _patch_dock(monkeypatch, orientation=orientation)

    layout = compute_strip_layout(full_width_height=_FULL_WIDTH_HEIGHT)

    assert layout.mode == "full_width"


def test_missing_orientation_key_is_treated_as_bottom(
    fake_appkit: MagicMock, fake_webview: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A user who never touched Dock position has no `orientation` default -- the factory default is bottom."""
    _set_single_screen(fake_appkit, fake_webview, dock_reserved_height=84)
    _patch_dock(monkeypatch, orientation=None)

    layout = compute_strip_layout(full_width_height=_FULL_WIDTH_HEIGHT)

    assert layout.mode == "beside_dock"


def test_falls_back_to_full_width_when_dock_is_auto_hidden(
    fake_appkit: MagicMock, fake_webview: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`visibleFrame` reports zero Dock reservation while it's auto-hidden."""
    _set_single_screen(fake_appkit, fake_webview, dock_reserved_height=0)
    _patch_dock(monkeypatch)

    layout = compute_strip_layout(full_width_height=_FULL_WIDTH_HEIGHT)

    assert layout.mode == "full_width"
    assert layout.height == _FULL_WIDTH_HEIGHT


def test_beside_dock_placement_matches_real_measured_geometry(
    fake_appkit: MagicMock, fake_webview: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test using the exact numbers measured live on a real 3840x2160 display.

    Dock icon area: CG pos=(1154, 2072), size=(1532, 78). Dock reserved
    height (from `visibleFrame`): 84px. The Dock is horizontally centered,
    so both sides have ~1146px free -- left is preferred whenever it has
    enough room, per explicit user preference.
    """
    _set_single_screen(
        fake_appkit, fake_webview, width=3840, height=2160, dock_reserved_height=84
    )
    _patch_dock(monkeypatch, icon_area=(1154.0, 2072.0, 1532.0, 78.0))

    layout = compute_strip_layout(full_width_height=_FULL_WIDTH_HEIGHT)

    assert layout.mode == "beside_dock"
    assert layout.height == 84
    assert layout.x == pytest.approx(4.0)  # screen edge margin
    assert layout.width == pytest.approx(1154.0 - 8.0 - 4.0)
    # No vertical margin -- `y`/`height` must match the real Dock's own
    # exact footprint (via `dock_height`) pixel-for-pixel.
    assert layout.y == 0


def test_beside_dock_picks_right_side_when_left_is_too_narrow(
    fake_appkit: MagicMock, fake_webview: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Dock pushed far left: barely any room on the left, plenty on the right.
    _set_single_screen(
        fake_appkit, fake_webview, width=3840, height=2160, dock_reserved_height=84
    )
    _patch_dock(monkeypatch, icon_area=(100.0, 2072.0, 1700.0, 78.0))

    layout = compute_strip_layout(full_width_height=_FULL_WIDTH_HEIGHT)

    assert layout.mode == "beside_dock"
    assert layout.x == pytest.approx(1800.0 + 8.0)  # dock_right + margin
    assert layout.width == pytest.approx(3840 - 1800.0 - 8.0 - 4.0)


def test_falls_back_to_full_width_laptop_screen_too_small(
    fake_appkit: MagicMock, fake_webview: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test for the user's laptop-only case: not enough room on either side."""
    _set_single_screen(
        fake_appkit, fake_webview, width=1800, height=1169, dock_reserved_height=84
    )
    # Dock centered, ~1516px wide -- leaves ~130px per side on a 1800px screen.
    _patch_dock(monkeypatch, icon_area=(142.0, 1091.0, 1516.0, 78.0))

    layout = compute_strip_layout(full_width_height=_FULL_WIDTH_HEIGHT)

    assert layout.mode == "full_width"
    assert layout.width == pytest.approx(1800 - 2 * 4.0)


def test_falls_back_when_dock_bounds_do_not_match_any_screen(
    fake_appkit: MagicMock, fake_webview: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_single_screen(fake_appkit, fake_webview, dock_reserved_height=84)
    # Icon area far outside any known screen's bounds.
    _patch_dock(monkeypatch, icon_area=(99999.0, 99999.0, 100.0, 50.0))

    layout = compute_strip_layout(full_width_height=_FULL_WIDTH_HEIGHT)

    assert layout.mode == "full_width"


def test_picks_the_screen_the_dock_actually_lives_on(
    fake_appkit: MagicMock, fake_webview: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dock on the second monitor, at a non-zero global offset.

    Confirms the CG-to-AppKit conversion anchors on the *primary* screen,
    not the Dock's own.
    """
    main_frame = _FakeFrame(origin=_FakePoint(0, 0), size=_FakeSize(3840, 2160))
    main_visible = _FakeFrame(origin=_FakePoint(0, 0), size=_FakeSize(3840, 2130))
    second_frame = _FakeFrame(origin=_FakePoint(3840, 518), size=_FakeSize(3000, 1169))
    second_visible = _FakeFrame(
        origin=_FakePoint(3840, 602), size=_FakeSize(3000, 1047)
    )
    fake_appkit.NSScreen.screens.return_value = [
        _FakeNSScreen(main_frame, main_visible),
        _FakeNSScreen(second_frame, second_visible),
    ]
    fake_webview.screens = [
        _FakeScreen(x=0, y=0, width=3840, height=2160),
        _FakeScreen(x=3840, y=518, width=3000, height=1169),
    ]
    # Dock bar centered on the second monitor: CG pos=(4840, 1558), size=(1000, 78).
    # Converts to AppKit y = 2160 - 1558 - 78 = 524 -- anchored on the *primary*
    # screen's frame (not the second monitor's own), confirmed close to that
    # screen's own bottom edge (518), within tolerance.
    _patch_dock(monkeypatch, icon_area=(4840.0, 1558.0, 1000.0, 78.0))

    layout = compute_strip_layout(full_width_height=_FULL_WIDTH_HEIGHT)

    assert layout.screen.x == 3840
    assert layout.mode == "beside_dock"
