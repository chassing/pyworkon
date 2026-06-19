import logging
from typing import TYPE_CHECKING, Any, Self

from pyworkon.providers.models import Project
from pyworkon.sidebar.models import PRInfo, PRState, PRStatus

from .consumer import GitLabConsumer

if TYPE_CHECKING:
    from .models import Repository

log = logging.getLogger(__name__)

_PIPELINE_STATUS_MAP: dict[str, PRStatus] = {
    "success": PRStatus.SUCCESS,
    "failed": PRStatus.FAILURE,
    "canceled": PRStatus.FAILURE,
    "running": PRStatus.PENDING,
    "pending": PRStatus.PENDING,
    "created": PRStatus.PENDING,
    "manual": PRStatus.PENDING,
}


class GitLabApi:
    """GitLab REST interface."""

    API_URL = "https://gitlab.com"

    def __init__(self, name: str, api_url: str, username: str, password: str) -> None:
        """Init."""
        self._name = name
        self._api = GitLabConsumer(base_url=api_url, token=password)
        self._base_url = api_url.rstrip("/")
        self._username = username

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object, **kwargs: Any) -> None: ...

    def projects(self) -> list[Project]:
        page = 1
        repos: list[Repository] = []
        while True:
            repos_page = self._api.projects(membership=True, page=page)
            if not repos_page:
                break
            repos += repos_page
            page += 1

        if not repos:
            log.error("No repositories found.")
        return [
            Project(
                project_id=f"{self._name}/{repo.path_with_namespace}",
                repository_url=repo.ssh_url_to_repo,
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
        """Get MR info for a branch (opened, closed, or merged)."""
        try:
            return self._find_mr(owner_repo, branch)
        except Exception:
            log.exception(
                "Failed to fetch MR for %s branch=%s",
                owner_repo,
                branch,
            )
        return None

    def _find_mr(self, project_path: str, branch: str) -> PRInfo | None:
        gitlab_to_state: dict[str, PRState] = {
            "opened": PRState.OPEN,
            "closed": PRState.CLOSED,
            "merged": PRState.MERGED,
        }
        for mr_state in ("opened", "merged", "closed"):
            mrs = self._api.merge_requests(
                project_id=project_path,
                source_branch=branch,
                state=mr_state,
            )
            if not mrs:
                continue

            mr = mrs[0]
            status = PRStatus.NONE
            if mr.pipeline:
                status = _PIPELINE_STATUS_MAP.get(mr.pipeline.status, PRStatus.PENDING)
            return PRInfo(
                number=mr.iid,
                title=mr.title,
                status=status,
                state=gitlab_to_state.get(mr.state, PRState.OPEN),
                url=f"{self._base_url}/{project_path}/-/merge_requests/{mr.iid}",
            )
        return None
