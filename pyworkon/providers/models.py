from pydantic import BaseModel


class Project(BaseModel):
    project_id: str
    repository_url: str
