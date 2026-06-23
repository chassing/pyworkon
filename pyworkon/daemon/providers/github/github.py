from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Self

from pyworkon.daemon.providers.models import Project
from pyworkon.interfaces.tui.models import (
    CICheck,
    PRInfo,
    PRReviewStatus,
    PRState,
    PRStatus,
    ReviewPR,
)

from . import consumer

if TYPE_CHECKING:
    from .models import PullRequest, Repository, SearchIssueItem

log = logging.getLogger(__name__)

_CONCLUSION_STATUS_MAP: dict[str, PRStatus] = {
    "success": PRStatus.SUCCESS,
    "failure": PRStatus.FAILURE,
    "cancelled": PRStatus.FAILURE,
    "timed_out": PRStatus.FAILURE,
    "action_required": PRStatus.FAILURE,
}

_REVIEW_STATE_MAP: dict[str, PRReviewStatus] = {
    "APPROVED": PRReviewStatus.APPROVED,
    "CHANGES_REQUESTED": PRReviewStatus.CHANGES_REQUESTED,
}


class GitHubApi:
    """GitHub REST interface."""

    API_URL = "https://api.github.com"

    def __init__(self, name: str, api_url: str, username: str, password: str) -> None:
        """Init."""
        self._name = name
        self._username = username
        consumer.configure(base_url=api_url, username=username, password=password)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object, **kwargs: Any) -> None: ...

    async def projects(self) -> list[Project]:
        repos: list[Repository] = []
        per_page = 100
        for page in range(1, 1000):
            repos += await consumer.user_repos(page=page, per_page=per_page)
            if len(repos) < page * per_page:
                break

        return [
            Project(
                project_id=f"{self._name}/{repo.full_name}",
                repository_url=repo.ssh_url,
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
        """Get PR info for a branch (open, closed, or merged)."""
        owner, repo = owner_repo.split("/", 1)
        head_prefix = head_owner or owner
        try:
            pulls = await consumer.repo_pulls(
                owner=owner,
                repo=repo,
                head=f"{head_prefix}:{branch}",
                state="all",
            )
        except (ConnectionError, TimeoutError, OSError):
            log.debug("Failed to fetch PR for %s branch=%s", owner_repo, branch)
            return None
        if not pulls:
            return None
        return await self._build_pr_info(owner, repo, pulls[0])

    async def _build_pr_info(self, owner: str, repo: str, pr: PullRequest) -> PRInfo:
        state = PRState.MERGED if pr.merged_at else PRState(pr.state)
        ci_status, ci_checks = await self._get_checks(owner, repo, pr.head.sha)
        review_status = (
            PRReviewStatus.NONE
            if pr.draft
            else await self._get_review_status(owner, repo, pr.number)
        )
        return PRInfo(
            number=pr.number,
            title=pr.title,
            status=ci_status,
            state=state,
            url=f"https://github.com/{owner}/{repo}/pull/{pr.number}",
            review_status=review_status,
            is_draft=pr.draft,
            ci_checks=ci_checks,
        )

    async def _get_checks(
        self, owner: str, repo: str, sha: str
    ) -> tuple[PRStatus, list[CICheck]]:
        """Fetch check runs and derive overall status + failed checks."""
        try:
            response = await consumer.check_runs(owner=owner, repo=repo, ref=sha)
        except (ConnectionError, TimeoutError, OSError):
            log.debug("Failed to fetch checks for %s/%s ref=%s", owner, repo, sha)
            return PRStatus.NONE, []

        if not response.check_runs:
            return PRStatus.NONE, []

        failed: list[CICheck] = []
        overall = PRStatus.SUCCESS
        for run in response.check_runs:
            if run.status != "completed":
                overall = PRStatus.PENDING
                continue
            status = _CONCLUSION_STATUS_MAP.get(run.conclusion or "", PRStatus.NONE)
            if status == PRStatus.FAILURE:
                overall = PRStatus.FAILURE
                failed.append(CICheck(name=run.name, status=status, url=run.html_url))
        return overall, failed

    async def _get_review_status(
        self, owner: str, repo: str, pull_number: int
    ) -> PRReviewStatus:
        """Aggregate reviews to a single status (latest per reviewer)."""
        try:
            reviews = await consumer.pull_reviews(
                owner=owner, repo=repo, pull_number=pull_number
            )
        except (ConnectionError, TimeoutError, OSError):
            log.debug("Failed to fetch reviews for %s/%s#%d", owner, repo, pull_number)
            return PRReviewStatus.NONE

        if not reviews:
            return PRReviewStatus.NONE

        latest_per_user: dict[str, str] = {}
        for review in reviews:
            if review.state in {"COMMENTED", "DISMISSED"}:
                continue
            latest_per_user[review.user.login] = review.state

        if not latest_per_user:
            return PRReviewStatus.NONE
        if any(s == "CHANGES_REQUESTED" for s in latest_per_user.values()):
            return PRReviewStatus.CHANGES_REQUESTED
        if any(s == "APPROVED" for s in latest_per_user.values()):
            return PRReviewStatus.APPROVED
        return PRReviewStatus.PENDING

    async def get_review_requested_prs(self) -> dict[str, list[ReviewPR]]:
        """Get all open PRs where the authenticated user is a requested reviewer.

        Returns a dict keyed by owner/repo with lists of ReviewPR objects.
        """
        try:
            response = await consumer.search_issues(
                q=f"is:open is:pr review-requested:{self._username}",
                per_page=100,
            )
        except (ConnectionError, TimeoutError, OSError):
            log.debug("Failed to fetch review-requested PRs")
            return {}

        result: dict[str, list[ReviewPR]] = {}
        api_prefix = "https://api.github.com/repos/"
        for item in response.items:
            owner_repo = item.repository_url.removeprefix(api_prefix)
            if not owner_repo or owner_repo == item.repository_url:
                continue
            review_pr = self._build_review_pr(item)
            result.setdefault(owner_repo, []).append(review_pr)
        return result

    @staticmethod
    def _build_review_pr(item: SearchIssueItem) -> ReviewPR:
        return ReviewPR(
            number=item.number,
            title=item.title,
            url=item.html_url,
            author=item.user.login,
            is_draft=item.draft,
        )
