import logging

import uplink
from requests import Response

from .models import Repository

log = logging.getLogger(__name__)


@uplink.response_handler
def raise_for_status(response: Response) -> Response:
    response.raise_for_status()
    return response


@raise_for_status
@uplink.timeout(60)
@uplink.returns.json
@uplink.json
@uplink.headers({"Accept": "application/vnd.github.v3+json"})
class GitHubConsumer(uplink.Consumer):
    """https://docs.github.com/en/rest"""

    @uplink.get("user/repos")
    def user_repos(  # type: ignore[empty-body]
        self, page: uplink.Query, per_page: uplink.Query = "100"
    ) -> list[Repository]:
        """Get all user repositories."""
