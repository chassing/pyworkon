from pydantic import BaseModel


class Repository(BaseModel):
    name: str
    full_name: str  # octocat/Hello-World
    ssh_url: str  # git@github.com:octocat/Hello-World.git


class PullRequestHead(BaseModel):
    ref: str
    sha: str


class PullRequest(BaseModel):
    number: int
    title: str
    head: PullRequestHead
    state: str  # open, closed
    merged_at: str | None = None
    draft: bool = False


class CombinedStatus(BaseModel):
    state: str  # success, failure, pending
    total_count: int


class CheckRun(BaseModel):
    name: str
    status: str  # queued, in_progress, completed
    conclusion: str | None = None  # success, failure, neutral, cancelled, ...
    html_url: str


class CheckRunsResponse(BaseModel):
    check_runs: list[CheckRun]


class ReviewUser(BaseModel):
    login: str


class Review(BaseModel):
    state: str  # APPROVED, CHANGES_REQUESTED, COMMENTED, DISMISSED
    user: ReviewUser
