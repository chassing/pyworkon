"""Tests for the strip webview's sidebar-state sanitization."""

from __future__ import annotations

import pytest

from pyworkon.config import Provider, ProviderType
from pyworkon.daemon.models import ReviewPR
from pyworkon.daemon.project_mgr import Project
from pyworkon.daemon.protocol import SessionState, SidebarStatePayload
from pyworkon.interfaces.strip.schema import _repository_web_url, to_strip_payload

from .conftest import make_pr_info


def _provider(*, password: str) -> Provider:
    return Provider(
        name="github",
        type=ProviderType.github,
        api_url="https://api.github.com",
        username="chassing",
        password=password,
    )


def _state_with_provider(provider: Provider | None) -> SidebarStatePayload:
    return SidebarStatePayload(
        sessions=[
            SessionState(
                session_name="my-session",
                project=Project(id="github/owner/repo", provider=provider),
                branch="main",
                is_dirty=True,
                pr=make_pr_info(),
            )
        ],
        plain_sessions=["plain"],
        projects=[Project(id="github/owner/repo2", provider=provider)],
        review_prs={
            "github/owner/repo": [
                ReviewPR(number=1, title="Review me", url="https://x/1", author="bob")
            ]
        },
        open_providers=["gitlab"],
    )


def test_to_strip_payload_excludes_provider_credentials() -> None:
    state = _state_with_provider(_provider(password="supersecret123"))

    strip_payload = to_strip_payload(state)

    assert "supersecret123" not in strip_payload.model_dump_json()


def test_to_strip_payload_maps_provider_type_only() -> None:
    state = _state_with_provider(_provider(password="unused"))

    strip_payload = to_strip_payload(state)

    assert strip_payload.sessions[0].provider_type == "github"


def test_to_strip_payload_handles_no_provider() -> None:
    state = _state_with_provider(None)

    strip_payload = to_strip_payload(state)

    assert strip_payload.sessions[0].provider_type is None


def test_to_strip_payload_preserves_pr_and_plain_sessions() -> None:
    state = _state_with_provider(None)

    strip_payload = to_strip_payload(state)

    assert strip_payload.sessions[0].pr == state.sessions[0].pr
    assert strip_payload.sessions[0].branch == "main"
    assert strip_payload.sessions[0].is_dirty is True
    assert strip_payload.plain_sessions == ["plain"]


def test_to_strip_payload_attaches_review_prs_by_project_id() -> None:
    state = _state_with_provider(None)

    strip_payload = to_strip_payload(state)

    assert strip_payload.sessions[0].review_prs == state.review_prs["github/owner/repo"]


def test_to_strip_payload_empty_review_prs_when_no_match() -> None:
    state = SidebarStatePayload(
        sessions=[
            SessionState(
                session_name="s", project=Project(id="github/owner/other"), pr=None
            )
        ],
        plain_sessions=[],
        projects=[],
        review_prs={"github/owner/repo": []},
    )

    strip_payload = to_strip_payload(state)

    assert strip_payload.sessions[0].review_prs == []


@pytest.mark.parametrize(
    ("ssh_url", "expected"),
    [
        (
            "git@github.com:octocat/Hello-World.git",
            "https://github.com/octocat/Hello-World",
        ),
        ("git@gitlab.com:assing/pyworkon.git", "https://gitlab.com/assing/pyworkon"),
        # Self-hosted GitLab: the host segment comes straight from the real
        # git remote, so this needs no provider-config lookup to get right.
        (
            "git@gitlab.example.com:group/sub/repo.git",
            "https://gitlab.example.com/group/sub/repo",
        ),
        (None, None),
        ("not-a-git-url", None),
        (
            "https://github.com/octocat/Hello-World",
            "https://github.com/octocat/Hello-World",
        ),
    ],
)
def test_repository_web_url_converts_ssh_clone_urls(
    ssh_url: str | None, expected: str | None
) -> None:
    assert _repository_web_url(ssh_url) == expected


def test_to_strip_payload_converts_repository_url_to_a_browsable_link() -> None:
    state = SidebarStatePayload(
        sessions=[
            SessionState(
                session_name="s",
                project=Project(
                    id="github/owner/repo",
                    repository_url="git@github.com:owner/repo.git",
                ),
                pr=None,
            )
        ],
        plain_sessions=[],
        projects=[],
        review_prs={},
    )

    strip_payload = to_strip_payload(state)

    assert strip_payload.sessions[0].repository_url == "https://github.com/owner/repo"
