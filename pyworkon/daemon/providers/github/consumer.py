import base64
import logging

from clientele import api as clientele_api

from .models import CombinedStatus, PullRequest, Repository

log = logging.getLogger(__name__)

client = clientele_api.APIClient(base_url="https://api.github.com")


def configure(base_url: str, username: str, password: str) -> None:
    """Configure the GitHub API client."""
    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
    client.configure(
        config=clientele_api.BaseConfig(
            base_url=base_url,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "Authorization": f"Basic {credentials}",
            },
            timeout=60.0,
        )
    )


@client.get("/user/repos")
async def user_repos(  # noqa: RUF029
    result: list[Repository],
    page: int,
    per_page: int = 100,
) -> list[Repository]:
    """Get all user repositories."""
    return result


@client.get("/repos/{owner}/{repo}/pulls")
async def repo_pulls(  # noqa: RUF029
    result: list[PullRequest],
    owner: str,
    repo: str,
    head: str,
    state: str = "open",
) -> list[PullRequest]:
    """Get pull requests for a repository filtered by head branch."""
    return result


@client.get("/repos/{owner}/{repo}/commits/{ref}/status")
async def combined_status(  # noqa: RUF029
    result: CombinedStatus,
    owner: str,
    repo: str,
    ref: str,
) -> CombinedStatus:
    """Get combined status for a commit ref."""
    return result
