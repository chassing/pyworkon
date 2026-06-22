"""Circuit breaker for provider API calls.

Prevents log spam when a provider is unreachable (e.g., VPN down).
After FAIL_MAX consecutive failures, the circuit opens and skips
calls for RESET_TIMEOUT seconds. One WARNING is logged when opening,
one INFO when the provider recovers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

import pybreaker

log = logging.getLogger(__name__)

FAIL_MAX = 3
RESET_TIMEOUT = 300

_breakers: dict[str, pybreaker.CircuitBreaker] = {}
_notification_callback: Callable[[str, str], None] | None = None


def set_notification_callback(callback: Callable[[str, str], None]) -> None:
    """Register a callback for circuit breaker state changes (level, message)."""
    global _notification_callback  # noqa: PLW0603
    _notification_callback = callback


class _LogListener(pybreaker.CircuitBreakerListener):
    def state_change(
        self, cb: pybreaker.CircuitBreaker, old_state: Any, new_state: Any
    ) -> None:
        if new_state.name == "open":
            msg = f"Provider {cb.name} unreachable after {FAIL_MAX} failures, pausing for {cb.reset_timeout}s"
            log.warning(msg)
            if _notification_callback:
                _notification_callback("warning", msg)
        elif old_state.name == "open":
            msg = f"Provider {cb.name} is back"
            log.info(msg)
            if _notification_callback:
                _notification_callback("information", msg)


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
