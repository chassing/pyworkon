import logging
from typing import TYPE_CHECKING, Any, Self

from pyworkon.providers.models import Project
from pyworkon.sidebar.models import PRInfo, PRState, PRStatus

from . import consumer

if TYPE_CHECKING:
    from .models import Repository

log = logging.getLogger(__name__)

_STATUS_MAP: dict[str, PRStatus] = {
    "success": PRStatus.SUCCESS,
    "failure": PRStatus.FAILURE,
    "error": PRStatus.FAILURE,
    "pending": PRStatus.PENDING,
}


class GitHubApi:
    """GitHub REST interface."""

    API_URL = "https://api.github.com"

    def __init__(self, name: str, api_url: str, username: str, password: str) -> None:
        """Init."""
        self._name = name
        self._username = username
        consumer.configure(base_url=api_url, username=username, password=password)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object, **kwargs: Any) -> None: ...

    def projects(self) -> list[Project]:
        repos: list[Repository] = []
        per_page = 100
        for page in range(1, 1000):
            repos += consumer.user_repos(page=page, per_page=per_page)
            if len(repos) < page * per_page:
                break

        return [
            Project(
                project_id=f"{self._name}/{repo.full_name}",
                repository_url=repo.ssh_url,
            )
            for repo in repos
        ]

    def get_pr_info(
        self,
        owner_repo: str,
        branch: str,
        *,
        head_owner: str | None = None,
    ) -> PRInfo | None:
        """Get PR info for a branch (open, closed, or merged)."""
        owner, repo = owner_repo.split("/", 1)
        head_prefix = head_owner or owner
        try:
            pulls = consumer.repo_pulls(
                owner=owner,
                repo=repo,
                head=f"{head_prefix}:{branch}",
                state="all",
            )
            if pulls:
                pr = pulls[0]
                state = PRState.MERGED if pr.merged_at else PRState(pr.state)
                status = self._get_check_status(owner, repo, pr.head.sha)
                return PRInfo(
                    number=pr.number,
                    title=pr.title,
                    status=status,
                    state=state,
                    url=f"https://github.com/{owner}/{repo}/pull/{pr.number}",
                )
        except Exception:
            log.exception("Failed to fetch PR for %s branch=%s", owner_repo, branch)
        return None

    def _get_check_status(self, owner: str, repo: str, sha: str) -> PRStatus:
        try:
            combined = consumer.combined_status(owner=owner, repo=repo, ref=sha)
            return _STATUS_MAP.get(combined.state, PRStatus.PENDING)
        except Exception:
            log.exception(
                "Failed to fetch check status for %s/%s ref=%s", owner, repo, sha
            )
        return PRStatus.NONE
