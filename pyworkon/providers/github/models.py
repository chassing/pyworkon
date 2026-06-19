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


class CombinedStatus(BaseModel):
    state: str  # success, failure, pending
    total_count: int
