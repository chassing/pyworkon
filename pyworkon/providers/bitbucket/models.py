from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import (
    BaseModel,
    HttpUrl,
)


class PaginationBase(BaseModel):
    size: int
    page: int
    pagelen: int = 100
    next: HttpUrl | None = None
    previous: HttpUrl | None = None


class Workspace(BaseModel):
    uuid: str
    name: str
    slug: str
    is_private: bool
    created_on: datetime
    updated_on: datetime | None = None


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
    account_id: str | None = None
    display_name: str | None = None
    nickname: str | None = None
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
    updated_on: datetime | None = None
    size: int
    language: str | None = None
    has_issues: bool = False
    has_wiki: bool = False
    fork_policy: ForkPolicy = ForkPolicy.allow_forks
    website: str = ""


class Repositories(PaginationBase):
    values: list[Repository]
