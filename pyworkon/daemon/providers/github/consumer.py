import base64
import logging

from clientele import api as clientele_api

from .models import (
    CheckRunsResponse,
    CombinedStatus,
    PullRequest,
    Repository,
    Review,
    SearchIssuesResponse,
)

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
            # Kept short: the circuit breaker (fail_max=3) needs 3 hung
            # requests to trip, so a long timeout multiplies how long PR
            # data stays blank for every open project on a network hiccup.
            timeout=10.0,
        )
    )


@client.get("/user/repos")
async def user_repos(  # ruff: ignore[unused-async]
    result: list[Repository],
    page: int,
    per_page: int = 100,
) -> list[Repository]:
    """Get all user repositories."""
    return result


@client.get("/repos/{owner}/{repo}/pulls")
async def repo_pulls(  # ruff: ignore[unused-async]
    result: list[PullRequest],
    owner: str,
    repo: str,
    head: str,
    state: str = "open",
) -> list[PullRequest]:
    """Get pull requests for a repository filtered by head branch."""
    return result


@client.get("/repos/{owner}/{repo}/commits/{ref}/status")
async def combined_status(  # ruff: ignore[unused-async]
    result: CombinedStatus,
    owner: str,
    repo: str,
    ref: str,
) -> CombinedStatus:
    """Get combined status for a commit ref."""
    return result


@client.get("/repos/{owner}/{repo}/commits/{ref}/check-runs")
async def check_runs(  # ruff: ignore[unused-async]
    result: CheckRunsResponse,
    owner: str,
    repo: str,
    ref: str,
) -> CheckRunsResponse:
    """Get check runs for a commit ref."""
    return result


@client.get("/repos/{owner}/{repo}/pulls/{pull_number}/reviews")
async def pull_reviews(  # ruff: ignore[unused-async]
    result: list[Review],
    owner: str,
    repo: str,
    pull_number: int,
) -> list[Review]:
    """Get reviews for a pull request."""
    return result


@client.get("/search/issues")
async def search_issues(  # ruff: ignore[unused-async]
    result: SearchIssuesResponse,
    q: str,
    per_page: int = 100,
) -> SearchIssuesResponse:
    """Search issues and pull requests."""
    return result
