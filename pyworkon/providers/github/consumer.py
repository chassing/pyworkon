import logging

import httpx
from clientele import api as clientele_api

from .models import Repository

log = logging.getLogger(__name__)

client = clientele_api.APIClient(base_url="https://api.github.com")


class GitHubConsumer:
    """https://docs.github.com/en/rest"""

    def __init__(self, base_url: str, auth: httpx.Auth | tuple[str, str]) -> None:
        client.configure(
            config=clientele_api.BaseConfig(
                base_url=base_url,
                auth=auth,
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=60.0,
            )
        )

    @client.get("/user/repos")
    def user_repos(
        self,
        result: list[Repository],
        page: int,
        per_page: int = 100,
    ) -> list[Repository]:
        """Get all user repositories."""
        return result
