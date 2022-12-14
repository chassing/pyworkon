from typing import Type

from pydantic import HttpUrl

from ..config import (
    Provider,
    ProviderType,
)
from ..exceptions import UnknownProviderType
from .bitbucket import BitbucketApi
from .github import GitHubApi
from .gitlab import GitLabApi

PROVIDER_MAPPING: dict[ProviderType, Type[GitHubApi] | Type[GitLabApi] | Type[BitbucketApi]] = {
    ProviderType.github: GitHubApi,
    ProviderType.gitlab: GitLabApi,
    ProviderType.bitbucket: BitbucketApi,
}


def get_provider(provider: Provider) -> GitHubApi | GitLabApi | BitbucketApi:
    try:
        return PROVIDER_MAPPING[provider.type](
            name=provider.name,
            api_url=provider.api_url,
            username=provider.username,
            password=provider.password,
        )
    except KeyError:
        raise UnknownProviderType(f"{provider.name}: {provider.type=} not supported")


def get_default_url(provider_type: ProviderType) -> HttpUrl:
    try:
        return HttpUrl(PROVIDER_MAPPING[provider_type].API_URL)
    except KeyError:
        raise UnknownProviderType(f"{provider_type=} not supported")
