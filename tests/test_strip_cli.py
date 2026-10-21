"""Tests for the `pyworkon strip` CLI command."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from click.testing import CliRunner

from pyworkon.interfaces.shell import PyworkonContext, cli

if TYPE_CHECKING:
    import pytest

strip_cli = importlib.import_module("pyworkon.interfaces.shell.commands.strip")


def test_strip_command_starts_strip_without_auto_hide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(
        strip_cli, "start_strip", lambda *, auto_hide: calls.append(auto_hide)
    )

    result = CliRunner().invoke(cli, ["strip"], obj=PyworkonContext())

    assert result.exit_code == 0, result.output
    assert calls == [False]


def test_strip_command_passes_auto_hide_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(
        strip_cli, "start_strip", lambda *, auto_hide: calls.append(auto_hide)
    )

    result = CliRunner().invoke(cli, ["strip", "--auto-hide"], obj=PyworkonContext())

    assert result.exit_code == 0, result.output
    assert calls == [True]
