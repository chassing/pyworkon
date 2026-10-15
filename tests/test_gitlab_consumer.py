"""Tests for the GitLab provider's list_projects request shape.

Reproduces the bug where gitlab-cee (a self-hosted instance with many
membership projects) never finished a sync: list_projects requested GitLab's
full (non-simple) project payload, which is expensive to compute server-side
for a large project list, causing every page request to exceed the client
timeout.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyworkon.daemon.providers.gitlab import consumer as gitlab_consumer

if TYPE_CHECKING:
    from pytest_httpx2 import HTTPXMock


async def test_list_projects_requests_simple_payload(httpx2_mock: HTTPXMock) -> None:
    gitlab_consumer.configure(base_url="https://gitlab.example.com", token="test-value")
    httpx2_mock.add_response(json=[])

    await gitlab_consumer.list_projects(membership=True, page=1)

    request = httpx2_mock.get_request()
    assert request is not None
    assert request.url.params["simple"] == "true"
