from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import (
    BaseModel,
    HttpUrl,
)


class Repository(BaseModel):
    """Not complete!!"""

    id: int
    description: str | None = ""
    name: str  # 'pyworkon'
    name_with_namespace: str  # 'assing / pyworkon'
    path: str  # 'pyworkon'
    path_with_namespace: str  # 'assing/pyworkon'
    created_at: datetime
    default_branch: Optional[str] = "main"
    # tag_list: []
    # topics: []
    ssh_url_to_repo: str  # 'git@gitlab.com:assing/pyworkon.git'
    http_url_to_repo: HttpUrl  # 'https://gitlab.com/assing/pyworkon.git'
    web_url: HttpUrl  # 'https://gitlab.com/assing/pyworkon'
    readme_url: HttpUrl | None = (
        None  # 'https://gitlab.com/assing/pyworkon/-/blob/main/README.md'
    )
    avatar_url: Optional[HttpUrl] = None
    forks_count: int  # 0
    star_count: int  # 1
    last_activity_at: datetime  # '2021-11-26T08:28:28.518Z'
