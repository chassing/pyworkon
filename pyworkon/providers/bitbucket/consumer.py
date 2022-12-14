import logging

import uplink
from uplink_httpx import ContextConsumer

from .models import (
    Repositories,
    Workspaces,
)

log = logging.getLogger(__name__)


@uplink.response_handler
def raise_for_status(response):
    response.raise_for_status()
    return response


@raise_for_status
@uplink.timeout(10)
@uplink.returns.json
@uplink.json
@uplink.headers({"Accept": "application/json"})
class BitbucketConsumer(ContextConsumer):
    """https://developer.atlassian.com/cloud/bitbucket/rest/"""

    @uplink.get("2.0/workspaces")
    def workspaces(self, page: uplink.Query, pagelen: uplink.Query = "100") -> Workspaces:  # type: ignore
        """Get all user workspaces."""

    @uplink.get("2.0/repositories/{workspace}")
    def repositories(self, workspace: uplink.Path, page: uplink.Query, pagelen: uplink.Query = "100") -> Repositories:  # type: ignore
        """Get all workspace repositories."""
