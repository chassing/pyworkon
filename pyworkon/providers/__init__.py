from typing import Union

from ..config import Provider, ProviderType
from ..exceptions import UnknownProviderType
from .bitbucket import BitbucketApi
from .github import GitHubApi
from .gitlab import GitLabApi


def get_provider(provider: Provider) -> Union[GitHubApi, GitLabApi]:
    if provider.type == ProviderType.github:
        return GitHubApi(url=provider.api_url, username=provider.username, password=provider.password)
    if provider.type == ProviderType.bitbucket:
        return BitbucketApi(url=provider.api_url, username=provider.username, password=provider.password)
    raise UnknownProviderType(f"{provider.name}: {provider.type=} not supported")
