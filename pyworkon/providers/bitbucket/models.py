from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import (
    BaseModel,
    HttpUrl,
)


class PaginationBase(BaseModel):
    size: int
    page: int
    pagelen: int = 100
    next: Optional[HttpUrl] = None
    previous: Optional[HttpUrl] = None


class Workspace(BaseModel):
    uuid: str
    name: str
    slug: str
    is_private: bool
    created_on: datetime
    updated_on: Optional[datetime] = None


class Workspaces(PaginationBase):
    values: list[Workspace]


class Link(BaseModel):
    name: str = ""
    href: str


class RepositoryLinks(BaseModel):
    avatar: Link
    branches: Link
    clone: list[Link]
    commits: Link
    downloads: Link
    forks: Link
    hooks: Link
    html: Link
    pullrequests: Link
    self: Link
    source: Link
    tags: Link
    watchers: Link


class Owner(BaseModel):
    account_id: Optional[str] = None
    display_name: Optional[str] = None
    nickname: Optional[str] = None
    type: str = "user"
    uuid: str


class ForkPolicy(Enum):
    allow_forks = "allow_forks"
    no_public_forks = "no_public_forks"
    no_forks = "no_forks"


class Repository(BaseModel):
    """Not complete!!"""

    links: RepositoryLinks
    uuid: str
    full_name: str  # chassing/myfarm
    slug: str  # myfarm
    is_private: bool
    scm: str = "git"
    owner: Owner
    name: str
    description: str = ""
    created_on: datetime
    updated_on: Optional[datetime] = None
    size: int
    language: Optional[str] = None
    has_issues: bool = False
    has_wiki: bool = False
    fork_policy: ForkPolicy = ForkPolicy.allow_forks
    website: str = ""


class Repositories(PaginationBase):
    values: list[Repository]
