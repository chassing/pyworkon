import logging

from clientele import api as clientele_api

from .models import Repository

log = logging.getLogger(__name__)


client = clientele_api.APIClient(base_url="https://gitlab.com")


class GitLabConsumer:
    """https://docs.gitlab.com/"""

    def __init__(self, base_url: str, token: str) -> None:
        client.configure(
            config=clientele_api.BaseConfig(
                base_url=base_url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=60.0,
            )
        )

    @client.get("/api/v4/projects")
    def projects(
        self,
        result: list[Repository],
        *,
        membership: bool,
        page: int = 1,
        per_page: int = 100,
        order_by: str = "updated_at",
    ) -> list[Repository]:
        """Get all user projects."""
        return result
