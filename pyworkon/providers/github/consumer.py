import logging

import uplink
from uplink_httpx import ContextConsumer

from .models import Repository

log = logging.getLogger(__name__)


@uplink.response_handler
def raise_for_status(response):
    response.raise_for_status()
    return response


@raise_for_status
@uplink.timeout(10)
@uplink.returns.json
@uplink.json
@uplink.headers({"Accept": "application/vnd.github.v3+json"})
class GitHubConsumer(ContextConsumer):
    """https://docs.github.com/en/rest"""

    @uplink.get("user/repos")
    def user_repos(self, page: uplink.Query, per_page: uplink.Query = "100") -> list[Repository]:  # type: ignore
        """Get all user repositories."""
