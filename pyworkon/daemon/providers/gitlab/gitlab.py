import logging
from typing import TYPE_CHECKING, Any, Self

from pyworkon.daemon.providers.models import Project
from pyworkon.interfaces.tui.models import (
    CICheck,
    PRInfo,
    PRReviewStatus,
    PRState,
    PRStatus,
)

from . import consumer

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
        self._base_url = api_url.rstrip("/")
        self._username = username
        consumer.configure(base_url=api_url, token=password)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object, **kwargs: Any) -> None: ...

    async def projects(self) -> list[Project]:
        page = 1
        repos: list[Repository] = []
        while True:
            repos_page = await consumer.list_projects(membership=True, page=page)
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

    async def get_pr_info(
        self,
        owner_repo: str,
        branch: str,
        *,
        head_owner: str | None = None,
    ) -> PRInfo | None:
        """Get MR info for a branch (opened, closed, or merged)."""
        try:
            return await self._find_mr(owner_repo, branch)
        except (ConnectionError, TimeoutError, OSError):
            log.debug("Failed to fetch MR for %s branch=%s", owner_repo, branch)
        return None

    async def _find_mr(self, project_path: str, branch: str) -> PRInfo | None:
        gitlab_to_state: dict[str, PRState] = {
            "opened": PRState.OPEN,
            "closed": PRState.CLOSED,
            "merged": PRState.MERGED,
        }
        for mr_state in ("opened", "merged", "closed"):
            mrs = await consumer.merge_requests(
                project_id=project_path,
                source_branch=branch,
                state=mr_state,
            )
            if not mrs:
                continue

            mr = mrs[0]
            is_draft = mr.draft or mr.work_in_progress
            status = PRStatus.NONE
            ci_checks: list[CICheck] = []
            if mr.pipeline:
                status = _PIPELINE_STATUS_MAP.get(mr.pipeline.status, PRStatus.PENDING)
                pipeline_url = (
                    f"{self._base_url}/{project_path}/-/pipelines/{mr.pipeline.id}"
                )
                ci_checks = [CICheck(name="Pipeline", status=status, url=pipeline_url)]

            review_status = (
                PRReviewStatus.NONE
                if is_draft
                else await self._get_review_status(project_path, mr.iid)
            )
            return PRInfo(
                number=mr.iid,
                title=mr.title,
                status=status,
                state=gitlab_to_state.get(mr.state, PRState.OPEN),
                url=f"{self._base_url}/{project_path}/-/merge_requests/{mr.iid}",
                review_status=review_status,
                is_draft=is_draft,
                ci_checks=ci_checks,
            )
        return None

    async def _get_review_status(
        self, project_path: str, mr_iid: int
    ) -> PRReviewStatus:
        try:
            approval = await consumer.mr_approval_state(
                project_id=project_path, merge_request_iid=mr_iid
            )
        except (ConnectionError, TimeoutError, OSError):
            log.debug("Failed to fetch approvals for %s!%d", project_path, mr_iid)
            return PRReviewStatus.NONE

        if not approval.rules:
            return PRReviewStatus.NONE
        if all(r.approved for r in approval.rules):
            return PRReviewStatus.APPROVED
        return PRReviewStatus.PENDING
