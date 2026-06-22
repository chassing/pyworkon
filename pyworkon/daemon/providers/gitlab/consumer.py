import logging

from clientele import api as clientele_api

from .models import MergeRequest, MRApprovalState, Repository

log = logging.getLogger(__name__)


client = clientele_api.APIClient(base_url="https://gitlab.com")


def configure(base_url: str, token: str) -> None:
    """Configure the GitLab API client."""
    client.configure(
        config=clientele_api.BaseConfig(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60.0,
        )
    )


@client.get("/api/v4/projects")
async def list_projects(  # noqa: RUF029
    result: list[Repository],
    *,
    membership: bool,
    page: int = 1,
    per_page: int = 100,
    order_by: str = "updated_at",
) -> list[Repository]:
    """Get all user projects."""
    return result


@client.get("/api/v4/projects/{project_id}/merge_requests")
async def merge_requests(  # noqa: RUF029
    result: list[MergeRequest],
    project_id: str,
    source_branch: str,
    state: str = "opened",
) -> list[MergeRequest]:
    """Get merge requests for a project filtered by source branch."""
    return result


@client.get(
    "/api/v4/projects/{project_id}/merge_requests/{merge_request_iid}/approval_state"
)
async def mr_approval_state(  # noqa: RUF029
    result: MRApprovalState,
    project_id: str,
    merge_request_iid: int,
) -> MRApprovalState:
    """Get approval state for a merge request."""
    return result
