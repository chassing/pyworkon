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
@uplink.timeout(10)
@uplink.returns.json
@uplink.json
class GitLabConsumer(uplink.Consumer):
    """https://docs.gitlab.com/"""

    @uplink.get("api/v4/projects")
    def projects(  # type: ignore[empty-body]
        self,
        membership: uplink.Query(type=bool),  # type: ignore[valid-type]
        page: uplink.Query = "1",
        per_page: uplink.Query = "100",
        order_by: uplink.Query = "updated_at",
    ) -> list[Repository]:
        """Get all user projects.

        Pagination is done via http headers in reply and I'm to lazy to implement that.
        """
