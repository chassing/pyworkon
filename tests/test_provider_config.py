"""Tests for provider HTTP client timeout configuration.

Reproduces the bug where a 60s per-request timeout let network hiccups hang
for minutes before the circuit breaker even noticed, blanking PR/CI data for
every open project on that provider for a full 5-minute reset window.
"""

from __future__ import annotations

from pyworkon.config import Provider
from pyworkon.daemon.providers.github import consumer as github_consumer
from pyworkon.daemon.providers.gitlab import consumer as gitlab_consumer

_MAX_ACCEPTABLE_TIMEOUT = 15.0


def test_provider_defaults_to_no_ignored_review_requests() -> None:
    provider = Provider(
        name="github",
        api_url="https://api.github.com",
        username="test-user",
        password="test-value",
    )
    assert provider.ignored_review_requests == []


def test_provider_parses_ignored_review_requests() -> None:
    provider = Provider.model_validate({
        "name": "github",
        "api_url": "https://api.github.com",
        "username": "test-user",
        "password": "test-value",
        "ignored_review_requests": [
            {"repository": "owner/repo", "authors": ["renovate[bot]", "alice"]}
        ],
    })
    assert provider.ignored_review_requests[0].repository == "owner/repo"
    assert provider.ignored_review_requests[0].authors == ["renovate[bot]", "alice"]
    assert provider.model_dump()["ignored_review_requests"] == [
        {"repository": "owner/repo", "authors": ["renovate[bot]", "alice"]}
    ]


def test_github_consumer_configure_uses_short_timeout() -> None:
    github_consumer.configure(
        base_url="https://api.github.com", username="test-user", password="test-value"
    )
    assert github_consumer.client.config.timeout <= _MAX_ACCEPTABLE_TIMEOUT


def test_gitlab_consumer_configure_uses_short_timeout() -> None:
    gitlab_consumer.configure(base_url="https://gitlab.com", token="test-value")
    assert gitlab_consumer.client.config.timeout <= _MAX_ACCEPTABLE_TIMEOUT
