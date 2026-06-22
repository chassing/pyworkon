from pydantic import BaseModel


class Repository(BaseModel):
    """Not complete!!"""

    id: int
    name: str  # 'pyworkon'
    path_with_namespace: str  # 'assing/pyworkon'
    ssh_url_to_repo: str  # 'git@gitlab.com:assing/pyworkon.git'


class MergeRequestPipeline(BaseModel):
    id: int
    status: str  # success, failed, running, pending, canceled


class MergeRequest(BaseModel):
    iid: int
    title: str
    source_branch: str
    state: str  # opened, closed, merged
    draft: bool = False
    work_in_progress: bool = False
    pipeline: MergeRequestPipeline | None = None


class MRApprovalRule(BaseModel):
    approved: bool


class MRApprovalState(BaseModel):
    rules: list[MRApprovalRule] = []
