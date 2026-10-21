"""Wire schema for the strip's local webview -- sanitized sidebar state for JS rendering.

The strip never leaves the machine, but its rendering logic lives in
JavaScript inside a WKWebView, so it gets the same credential-stripping as the
relay path (`daemon/relay_publisher.to_relay_payload`): `Project.provider`
carries a `password` field the JS context has no business touching.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

from pyworkon.daemon.models import AgentInfo, PRInfo, ReviewPR

if TYPE_CHECKING:
    from pyworkon.daemon.protocol import SidebarStatePayload

ProviderKind = Literal["github", "gitlab"]

# `Project.repository_url` is always a `git@host:owner/repo.git` SSH clone
# URL -- set from GitHub's `ssh_url` / GitLab's `ssh_url_to_repo` API fields,
# never a browsable web URL. Neither provider's response carries a separate
# `html_url`/`web_url` for this, and no provider config field carries a
# usable web host independent of the SSH one -- the host segment here is
# already correct for self-hosted GitLab, since it comes straight from the
# real git remote.
_SSH_URL_PATTERN = re.compile(r"^git@(?P<host>[^:/]+):(?P<path>.+?)(?:\.git)?$")


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class StripSessionState(_FrozenModel):
    session_name: str
    project_id: str
    project_name: str
    provider_type: ProviderKind | None = None
    repository_url: str | None = None
    branch: str | None = None
    is_dirty: bool = False
    pr: PRInfo | None = None
    agents: list[AgentInfo] = []
    review_prs: list[ReviewPR] = []


class StripStatePayload(_FrozenModel):
    sessions: list[StripSessionState]
    plain_sessions: list[str]


def _repository_web_url(ssh_url: str | None) -> str | None:
    """Convert a `git@host:owner/repo.git` SSH clone URL into a browsable `https://` one.

    `None` for anything that doesn't match the expected SSH form -- a
    non-clickable link is harmless, a broken one opened in the browser isn't.
    """
    if ssh_url is None:
        return None
    if ssh_url.startswith(("http://", "https://")):
        return ssh_url
    match = _SSH_URL_PATTERN.match(ssh_url)
    if match is None:
        return None
    return f"https://{match['host']}/{match['path']}"


def to_strip_payload(state: SidebarStatePayload) -> StripStatePayload:
    """Sanitize daemon state for the strip's JS rendering context."""
    return StripStatePayload(
        sessions=[
            StripSessionState(
                session_name=s.session_name,
                project_id=s.project.id,
                project_name=s.project.name,
                provider_type=s.project.provider.type if s.project.provider else None,
                repository_url=_repository_web_url(s.project.repository_url),
                branch=s.branch,
                is_dirty=s.is_dirty,
                pr=s.pr,
                agents=list(s.agents),
                review_prs=state.review_prs.get(s.project.id, []),
            )
            for s in state.sessions
        ],
        plain_sessions=list(state.plain_sessions),
    )
