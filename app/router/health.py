from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class _ProviderState:
    consecutive_failures: int = 0
    unhealthy_until: float | None = None


class ProviderHealth:
    """In-memory circuit breaker state per upstream provider (single-process MVP)."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        recovery_seconds: float = 60.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._states: dict[str, _ProviderState] = {}

    def is_healthy(self, provider: str) -> bool:
        state = self._state(provider)
        if state.unhealthy_until is None:
            return True

        now = time.monotonic()
        if now >= state.unhealthy_until:
            state.unhealthy_until = None
            state.consecutive_failures = 0
            return True

        return False

    def record_failure(self, provider: str) -> None:
        state = self._state(provider)
        state.consecutive_failures += 1
        if state.consecutive_failures >= self._failure_threshold:
            state.unhealthy_until = time.monotonic() + self._recovery_seconds

    def record_success(self, provider: str) -> None:
        state = self._state(provider)
        state.consecutive_failures = 0
        state.unhealthy_until = None

    def snapshot(self) -> dict[str, dict[str, int | float | None]]:
        return {
            provider: {
                "consecutive_failures": state.consecutive_failures,
                "unhealthy_until": state.unhealthy_until,
            }
            for provider, state in self._states.items()
        }

    def _state(self, provider: str) -> _ProviderState:
        if provider not in self._states:
            self._states[provider] = _ProviderState()
        return self._states[provider]
