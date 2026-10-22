from pydantic import BaseModel


class Repository(BaseModel):
    """Not complete!!"""

    id: int
    name: str  # 'pyworkon'
    path_with_namespace: str  # 'assing/pyworkon'
    ssh_url_to_repo: str  # 'git@gitlab.com:assing/pyworkon.git'


class MergeRequest(BaseModel):
    iid: int
    title: str
    source_branch: str
    state: str  # opened, closed, merged
    draft: bool = False
    work_in_progress: bool = False


class MRApprovalRule(BaseModel):
    approved: bool


class MRApprovalState(BaseModel):
    rules: list[MRApprovalRule] = []


class MergeRequestPipeline(BaseModel):
    id: int
    project_id: int  # pipelines run in the MR's source project, which may be a fork
    status: str  # success, failed, running, pending, canceled
    web_url: str


class PipelineJob(BaseModel):
    name: str
    status: str  # success, failed, running, pending, canceled, created, manual, skipped
    web_url: str
