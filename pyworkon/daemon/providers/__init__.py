from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from pyworkon.config import Provider, ProviderType
from pyworkon.daemon.providers.circuit_breaker import get_breaker
from pyworkon.exceptions import UnknownProviderTypeError
lazy from pyworkon.daemon.providers.models import ProviderApi

from .github import GitHubApi
from .gitlab import GitLabApi

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

PROVIDER_MAPPING: dict[ProviderType, type[GitHubApi | GitLabApi]] = {
    ProviderType.github: GitHubApi,
    ProviderType.gitlab: GitLabApi,
}


@asynccontextmanager
async def get_provider(provider: Provider) -> AsyncGenerator[ProviderApi]:
    """Get a provider API client wrapped in a circuit breaker.

    Raises pybreaker.CircuitBreakerError when the provider is unreachable.
    """
    try:
        cls = PROVIDER_MAPPING[provider.type]
    except KeyError:
        msg = f"{provider.name}: {provider.type=} not supported"
        raise UnknownProviderTypeError(msg) from None

    breaker = get_breaker(provider.name)
    with breaker.calling():
        api = cls(
            name=provider.name,
            api_url=str(provider.api_url),
            username=provider.username,
            password=provider.password,
        )
        async with api as instance:
            yield instance
