# generated by datamodel-codegen:
#   filename:  https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.yaml
#   timestamp: 2022-04-04T12:48:11+00:00

from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    Field,
)


class SimpleUser(BaseModel):
    name: str | None = None
    email: str | None = None
    login: str | None = Field(None, example="octocat")
    id: int | None = Field(None, example=1)
    node_id: str | None = Field(None, example="MDQ6VXNlcjE=")
    avatar_url: str | None = Field(
        None, example="https://github.com/images/error/octocat_happy.gif"
    )
    gravatar_id: str | None = Field(None, example="41d064eb2195891e12d0413f63227ea7")
    url: str | None = Field(None, example="https://api.github.com/users/octocat")
    html_url: str | None = Field(None, example="https://github.com/octocat")
    followers_url: str | None = Field(
        None, example="https://api.github.com/users/octocat/followers"
    )
    following_url: str | None = Field(
        None, example="https://api.github.com/users/octocat/following{/other_user}"
    )
    gists_url: str | None = Field(
        None, example="https://api.github.com/users/octocat/gists{/gist_id}"
    )
    starred_url: str | None = Field(
        None, example="https://api.github.com/users/octocat/starred{/owner}{/repo}"
    )
    subscriptions_url: str | None = Field(
        None, example="https://api.github.com/users/octocat/subscriptions"
    )
    organizations_url: str | None = Field(
        None, example="https://api.github.com/users/octocat/orgs"
    )
    repos_url: str | None = Field(
        None, example="https://api.github.com/users/octocat/repos"
    )
    events_url: str | None = Field(
        None, example="https://api.github.com/users/octocat/events{/privacy}"
    )
    received_events_url: str | None = Field(
        None, example="https://api.github.com/users/octocat/received_events"
    )
    type: str | None = Field(None, example="User")
    site_admin: bool | None = None
    starred_at: str | None = Field(None, example='"2020-07-09T00:17:55Z"')


class LicenseSimple(BaseModel):
    key: str | None = Field(None, example="mit")
    name: str | None = Field(None, example="MIT License")
    url: str | None = Field(None, example="https://api.github.com/licenses/mit")
    spdx_id: str | None = Field(None, example="MIT")
    node_id: str | None = Field(None, example="MDc6TGljZW5zZW1pdA==")
    html_url: str | None = None


class RepositoryPermissions(BaseModel):
    admin: bool | None = None
    pull: bool | None = None
    triage: bool | None = None
    push: bool | None = None
    maintain: bool | None = None


class TemplatePermission(BaseModel):
    admin: bool | None = None
    maintain: bool | None = None
    push: bool | None = None
    triage: bool | None = None
    pull: bool | None = None


class Owner(BaseModel):
    login: str | None = None
    id: int | None = None
    node_id: str | None = None
    avatar_url: str | None = None
    gravatar_id: str | None = None
    url: str | None = None
    html_url: str | None = None
    followers_url: str | None = None
    following_url: str | None = None
    gists_url: str | None = None
    starred_url: str | None = None
    subscriptions_url: str | None = None
    organizations_url: str | None = None
    repos_url: str | None = None
    events_url: str | None = None
    received_events_url: str | None = None
    type: str | None = None
    site_admin: bool | None = None


class TemplateRepository(BaseModel):
    id: int | None = None
    node_id: str | None = None
    name: str | None = None
    full_name: str | None = None
    owner: Owner | None = None
    private: bool | None = None
    html_url: str | None = None
    description: str | None = None
    fork: bool | None = None
    url: str | None = None
    archive_url: str | None = None
    assignees_url: str | None = None
    blobs_url: str | None = None
    branches_url: str | None = None
    collaborators_url: str | None = None
    comments_url: str | None = None
    commits_url: str | None = None
    compare_url: str | None = None
    contents_url: str | None = None
    contributors_url: str | None = None
    deployments_url: str | None = None
    downloads_url: str | None = None
    events_url: str | None = None
    forks_url: str | None = None
    git_commits_url: str | None = None
    git_refs_url: str | None = None
    git_tags_url: str | None = None
    git_url: str | None = None
    issue_comment_url: str | None = None
    issue_events_url: str | None = None
    issues_url: str | None = None
    keys_url: str | None = None
    labels_url: str | None = None
    languages_url: str | None = None
    merges_url: str | None = None
    milestones_url: str | None = None
    notifications_url: str | None = None
    pulls_url: str | None = None
    releases_url: str | None = None
    ssh_url: str | None = None
    stargazers_url: str | None = None
    statuses_url: str | None = None
    subscribers_url: str | None = None
    subscription_url: str | None = None
    tags_url: str | None = None
    teams_url: str | None = None
    trees_url: str | None = None
    clone_url: str | None = None
    mirror_url: str | None = None
    hooks_url: str | None = None
    svn_url: str | None = None
    homepage: str | None = None
    language: str | None = None
    forks_count: int | None = None
    stargazers_count: int | None = None
    watchers_count: int | None = None
    size: int | None = None
    default_branch: str | None = None
    open_issues_count: int | None = None
    is_template: bool | None = None
    topics: list[str] | None = None
    has_issues: bool | None = None
    has_projects: bool | None = None
    has_wiki: bool | None = None
    has_pages: bool | None = None
    has_downloads: bool | None = None
    archived: bool | None = None
    disabled: bool | None = None
    visibility: str | None = None
    pushed_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    permissions: TemplatePermission | None = None
    allow_rebase_merge: bool | None = None
    temp_clone_token: str | None = None
    allow_squash_merge: bool | None = None
    allow_auto_merge: bool | None = None
    delete_branch_on_merge: bool | None = None
    allow_update_branch: bool | None = None
    allow_merge_commit: bool | None = None
    subscribers_count: int | None = None
    network_count: int | None = None


class Repository(BaseModel):
    id: int | None = Field(
        None, description="Unique identifier of the repository", example=42
    )
    node_id: str | None = Field(None, example="MDEwOlJlcG9zaXRvcnkxMjk2MjY5")
    name: str | None = Field(
        None, description="The name of the repository.", example="Team Environment"
    )
    full_name: str | None = Field(None, example="octocat/Hello-World")
    license: LicenseSimple | None = None
    organization: SimpleUser | None = None
    forks: int | None = None
    permissions: RepositoryPermissions | None = None
    owner: SimpleUser | None = None
    private: bool | None = Field(
        False, description="Whether the repository is private or public."
    )
    html_url: str | None = Field(None, example="https://github.com/octocat/Hello-World")
    description: str | None = Field(None, example="This your first repo!")
    fork: bool | None = None
    url: str | None = Field(
        None, example="https://api.github.com/repos/octocat/Hello-World"
    )
    archive_url: str | None = Field(
        None,
        example="http://api.github.com/repos/octocat/Hello-World/{archive_format}{/ref}",
    )
    assignees_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/assignees{/user}"
    )
    blobs_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/git/blobs{/sha}"
    )
    branches_url: str | None = Field(
        None,
        example="http://api.github.com/repos/octocat/Hello-World/branches{/branch}",
    )
    collaborators_url: str | None = Field(
        None,
        example="http://api.github.com/repos/octocat/Hello-World/collaborators{/collaborator}",
    )
    comments_url: str | None = Field(
        None,
        example="http://api.github.com/repos/octocat/Hello-World/comments{/number}",
    )
    commits_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/commits{/sha}"
    )
    compare_url: str | None = Field(
        None,
        example="http://api.github.com/repos/octocat/Hello-World/compare/{base}...{head}",
    )
    contents_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/contents/{+path}"
    )
    contributors_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/contributors"
    )
    deployments_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/deployments"
    )
    downloads_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/downloads"
    )
    events_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/events"
    )
    forks_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/forks"
    )
    git_commits_url: str | None = Field(
        None,
        example="http://api.github.com/repos/octocat/Hello-World/git/commits{/sha}",
    )
    git_refs_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/git/refs{/sha}"
    )
    git_tags_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/git/tags{/sha}"
    )
    git_url: str | None = Field(None, example="git:github.com/octocat/Hello-World.git")
    issue_comment_url: str | None = Field(
        None,
        example="http://api.github.com/repos/octocat/Hello-World/issues/comments{/number}",
    )
    issue_events_url: str | None = Field(
        None,
        example="http://api.github.com/repos/octocat/Hello-World/issues/events{/number}",
    )
    issues_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/issues{/number}"
    )
    keys_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/keys{/key_id}"
    )
    labels_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/labels{/name}"
    )
    languages_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/languages"
    )
    merges_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/merges"
    )
    milestones_url: str | None = Field(
        None,
        example="http://api.github.com/repos/octocat/Hello-World/milestones{/number}",
    )
    notifications_url: str | None = Field(
        None,
        example="http://api.github.com/repos/octocat/Hello-World/notifications{?since,all,participating}",
    )
    pulls_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/pulls{/number}"
    )
    releases_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/releases{/id}"
    )
    ssh_url: str = Field(None, example="git@github.com:octocat/Hello-World.git")
    stargazers_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/stargazers"
    )
    statuses_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/statuses/{sha}"
    )
    subscribers_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/subscribers"
    )
    subscription_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/subscription"
    )
    tags_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/tags"
    )
    teams_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/teams"
    )
    trees_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/git/trees{/sha}"
    )
    clone_url: str | None = Field(
        None, example="https://github.com/octocat/Hello-World.git"
    )
    mirror_url: str | None = Field(
        None, example="git:git.example.com/octocat/Hello-World"
    )
    hooks_url: str | None = Field(
        None, example="http://api.github.com/repos/octocat/Hello-World/hooks"
    )
    svn_url: str | None = Field(
        None, example="https://svn.github.com/octocat/Hello-World"
    )
    homepage: str | None = Field(None, example="https://github.com")
    language: str | None = None
    forks_count: int | None = Field(None, example=9)
    stargazers_count: int | None = Field(None, example=80)
    watchers_count: int | None = Field(None, example=80)
    size: int | None = Field(None, example=108)
    default_branch: str | None = Field(
        None, description="The default branch of the repository.", example="master"
    )
    open_issues_count: int | None = Field(None, example=0)
    is_template: bool | None = Field(
        False,
        description="Whether this repository acts as a template that can be used to generate new repositories.",
        example=True,
    )
    topics: list[str] | None = None
    has_issues: bool | None = Field(
        True, description="Whether issues are enabled.", example=True
    )
    has_projects: bool | None = Field(
        True, description="Whether projects are enabled.", example=True
    )
    has_wiki: bool | None = Field(
        True, description="Whether the wiki is enabled.", example=True
    )
    has_pages: bool | None = None
    has_downloads: bool | None = Field(
        True, description="Whether downloads are enabled.", example=True
    )
    archived: bool | None = Field(
        False, description="Whether the repository is archived."
    )
    disabled: bool | None = Field(
        None, description="Returns whether or not this repository disabled."
    )
    visibility: str | None = Field(
        "public", description="The repository visibility: public, private, or internal."
    )
    pushed_at: datetime | None = Field(None, example="2011-01-26T19:06:43Z")
    created_at: datetime | None = Field(None, example="2011-01-26T19:01:12Z")
    updated_at: datetime | None = Field(None, example="2011-01-26T19:14:43Z")
    allow_rebase_merge: bool | None = Field(
        True,
        description="Whether to allow rebase merges for pull requests.",
        example=True,
    )
    template_repository: TemplateRepository | None = None
    temp_clone_token: str | None = None
    allow_squash_merge: bool | None = Field(
        True,
        description="Whether to allow squash merges for pull requests.",
        example=True,
    )
    allow_auto_merge: bool | None = Field(
        False,
        description="Whether to allow Auto-merge to be used on pull requests.",
        example=False,
    )
    delete_branch_on_merge: bool | None = Field(
        False,
        description="Whether to delete head branches when pull requests are merged",
        example=False,
    )
    allow_merge_commit: bool | None = Field(
        True,
        description="Whether to allow merge commits for pull requests.",
        example=True,
    )
    allow_forking: bool | None = Field(
        None, description="Whether to allow forking this repo"
    )
    subscribers_count: int | None = None
    network_count: int | None = None
    open_issues: int | None = None
    watchers: int | None = None
    master_branch: str | None = None
    starred_at: str | None = Field(None, example='"2020-07-09T00:17:42Z"')
