"""Tests for the strip's automatic macOS Dock auto-hide management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pyworkon.interfaces.strip import bridge as bridge_module
from pyworkon.interfaces.strip.bridge import _dock_autohide_enabled, _set_dock_autohide

if TYPE_CHECKING:
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
