from pydantic import BaseModel


class Repository(BaseModel):
    name: str
    full_name: str  # octocat/Hello-World")
    ssh_url: str  # git@github.com:octocat/Hello-World.git")
