from pyworkon.config import Provider, ProviderType
from pyworkon.exceptions import UnknownProviderTypeError

from .github import GitHubApi
from .gitlab import GitLabApi

PROVIDER_MAPPING: dict[ProviderType, type[GitHubApi] | type[GitLabApi]] = {
    ProviderType.github: GitHubApi,
    ProviderType.gitlab: GitLabApi,
}


def get_provider(provider: Provider) -> GitHubApi | GitLabApi:
    try:
        return PROVIDER_MAPPING[provider.type](
            name=provider.name,
            api_url=str(provider.api_url),
            username=provider.username,
            password=provider.password,
        )
    except KeyError:
        msg = f"{provider.name}: {provider.type=} not supported"
        raise UnknownProviderTypeError(msg) from None
