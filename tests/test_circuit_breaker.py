"""Tests for the provider circuit breaker registry."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from pyworkon.daemon.providers import circuit_breaker


@pytest.fixture(autouse=True)
def _reset_breakers() -> Iterator[None]:
    """Isolate tests from the module-level breaker registry."""
    circuit_breaker._breakers.clear()
    yield
    circuit_breaker._breakers.clear()


def test_get_open_providers_empty_when_no_breakers_registered() -> None:
    assert circuit_breaker.get_open_providers() == []


def test_get_open_providers_excludes_closed_breakers() -> None:
    circuit_breaker.get_breaker("github")

    assert circuit_breaker.get_open_providers() == []


def test_get_open_providers_includes_open_breakers() -> None:
    circuit_breaker.get_breaker("github").open()
    circuit_breaker.get_breaker("gitlab-cee")

    assert circuit_breaker.get_open_providers() == ["github"]
