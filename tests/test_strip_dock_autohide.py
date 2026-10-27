"""Tests for the strip's automatic macOS Dock auto-hide management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pyworkon.interfaces.strip import bridge as bridge_module
from pyworkon.interfaces.strip.bridge import (
    _dock_autohide_enabled,
    _set_dock_autohide,
    recover_dock_autohide_from_unclean_shutdown,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


@dataclass
class _FakeCompletedProcess:
    stdout: str


def test_dock_autohide_enabled_parses_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bridge_module.subprocess,
        "run",
        lambda *_a, **_kw: _FakeCompletedProcess("true\n"),
    )

    assert _dock_autohide_enabled() is True


def test_dock_autohide_enabled_parses_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bridge_module.subprocess,
        "run",
        lambda *_a, **_kw: _FakeCompletedProcess("false\n"),
    )

    assert _dock_autohide_enabled() is False


def test_set_dock_autohide_invokes_osascript_with_absolute_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        bridge_module.subprocess,
        "run",
        lambda cmd, **_kw: calls.append(cmd) or _FakeCompletedProcess(""),
    )

    _set_dock_autohide(enabled=True)

    assert len(calls) == 1
    assert calls[0][0] == "/usr/bin/osascript"
    assert "set autohide of dock preferences to true" in calls[0][2]


def test_set_dock_autohide_false(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        bridge_module.subprocess,
        "run",
        lambda cmd, **_kw: calls.append(cmd) or _FakeCompletedProcess(""),
    )

    _set_dock_autohide(enabled=False)

    assert "set autohide of dock preferences to false" in calls[0][2]


def test_recover_from_unclean_shutdown_is_a_noop_without_a_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        bridge_module, "_DOCK_AUTOHIDE_ORIGINAL_MARKER", tmp_path / "marker"
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(
        bridge_module.subprocess,
        "run",
        lambda cmd, **_kw: calls.append(cmd) or _FakeCompletedProcess(""),
    )

    recover_dock_autohide_from_unclean_shutdown()

    assert calls == []


def test_recover_from_unclean_shutdown_restores_the_persisted_original_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression test for the "stuck full-width forever, never flashes" bug.

    Confirmed live: a `SIGKILL`/crash while the real Dock is forced hidden
    leaves this marker behind. The next launch must restore the *persisted*
    original value, not re-read the Dock's current (still-forced) setting --
    that would permanently poison every future override with the wrong
    baseline, with zero visible Dock flashing to ever reveal it (every
    "restore" would just reassert the same already-true value).
    """
    marker = tmp_path / "marker"
    marker.write_text("false")
    monkeypatch.setattr(bridge_module, "_DOCK_AUTOHIDE_ORIGINAL_MARKER", marker)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        bridge_module.subprocess,
        "run",
        lambda cmd, **_kw: calls.append(cmd) or _FakeCompletedProcess(""),
    )

    recover_dock_autohide_from_unclean_shutdown()

    assert "set autohide of dock preferences to false" in calls[0][2]
    assert not marker.exists()
