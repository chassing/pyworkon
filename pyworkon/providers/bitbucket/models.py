from pydantic import BaseModel, HttpUrl


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


class Workspaces(PaginationBase):
    values: list[Workspace]


class Link(BaseModel):
    name: str = ""
    href: str


class RepositoryLinks(BaseModel):
    clone: list[Link]


class Repository(BaseModel):
    """Not complete!!"""

    links: RepositoryLinks
    uuid: str
    full_name: str  # chassing/myfarm
    slug: str  # myfarm
    is_private: bool
    name: str


class Repositories(PaginationBase):
    values: list[Repository]
