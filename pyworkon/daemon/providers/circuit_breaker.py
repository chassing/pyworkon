"""Circuit breaker for provider API calls.

Prevents log spam when a provider is unreachable (e.g., VPN down).
After FAIL_MAX consecutive failures, the circuit opens and skips
calls for RESET_TIMEOUT seconds. One WARNING is logged when opening,
one INFO when the provider recovers.
"""

from __future__ import annotations

import logging
from typing import Any

import pybreaker

log = logging.getLogger(__name__)

FAIL_MAX = 3
RESET_TIMEOUT = 300

_breakers: dict[str, pybreaker.CircuitBreaker] = {}


class _LogListener(pybreaker.CircuitBreakerListener):
    def state_change(
        self, cb: pybreaker.CircuitBreaker, old_state: Any, new_state: Any
    ) -> None:
        if new_state.name == "open":
            log.warning(
                "Provider %s unreachable after %d failures, pausing for %ds",
                cb.name,
                FAIL_MAX,
                cb.reset_timeout,
            )
        elif old_state.name == "open":
            log.info("Provider %s is back", cb.name)


_listener = _LogListener()


def get_breaker(provider_name: str) -> pybreaker.CircuitBreaker:
    """Get or create a circuit breaker for a provider."""
    if provider_name not in _breakers:
        _breakers[provider_name] = pybreaker.CircuitBreaker(
            fail_max=FAIL_MAX,
            reset_timeout=RESET_TIMEOUT,
            name=provider_name,
            listeners=[_listener],
        )
    return _breakers[provider_name]
