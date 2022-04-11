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
class GitLabConsumer(ContextConsumer):
    """https://docs.gitlab.com/"""

    @uplink.get("api/v4/projects")
    def projects(self, membership: uplink.Query(type=bool), per_page: uplink.Query = "100") -> list[Repository]:  # type: ignore
        """Get all user projects.

        Pagination is done via http headers in reply and I'm to lazy to implement that.
        """
