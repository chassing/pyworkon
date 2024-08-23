from pydantic import BaseModel


class Repository(BaseModel):
    """Not complete!!"""

    id: int
    name: str  # 'pyworkon'
    path_with_namespace: str  # 'assing/pyworkon'
    ssh_url_to_repo: str  # 'git@gitlab.com:assing/pyworkon.git'
