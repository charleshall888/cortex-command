"""Subscription-tier-bound concurrency caps for overnight orchestration.

Provides ``ConcurrencyManager.acquire``/``release`` to enforce a fixed
concurrency limit derived from the operator's subscription tier, plus
``load_throttle_config`` to resolve the tier and any overrides into a
``ThrottleConfig``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum

# Historical note: an adaptive rate-limit-backoff wrapper (throttled_dispatch)
# was deleted in 2026-05-04 after evidence showed it was never wired into the
# live dispatch path. If rate-limit-induced session pauses become a problem in
# production, see git log for the deletion commit and
# cortex/lifecycle/remove-dead-throttled-dispatch-wrapper-keep-concurrencymanager-acquire-release/
# for context.


# ---------------------------------------------------------------------------
# Subscription tiers
# ---------------------------------------------------------------------------

class SubscriptionTier(Enum):
    """Anthropic API subscription tiers with concurrency limits."""

    MAX_5 = "max_5"
    MAX_100 = "max_100"
    MAX_200 = "max_200"


_TIER_DEFAULTS: dict[SubscriptionTier, dict[str, int]] = {
    SubscriptionTier.MAX_5: {"max_runners": 1, "max_workers": 1},
    SubscriptionTier.MAX_100: {"max_runners": 2, "max_workers": 2},
    SubscriptionTier.MAX_200: {"max_runners": 3, "max_workers": 3},
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ThrottleConfig:
    """Configuration for subscription-tier-bound concurrency caps.

    Fields:
        tier: Subscription tier enum.
        max_concurrent_runners: Max batch runners running in parallel.
        max_concurrent_workers: Max workers per batch runner.
    """

    tier: SubscriptionTier = SubscriptionTier.MAX_100
    max_concurrent_runners: int = 2
    max_concurrent_workers: int = 2


def load_throttle_config(
    tier_name: str | None = None,
    overrides: dict | None = None,
) -> ThrottleConfig:
    """Load throttle configuration from a tier name with optional overrides.

    Args:
        tier_name: Tier string (e.g., "max_100", "max_200"). Defaults to
            MAX_100 if None or unrecognized.
        overrides: Dict of field overrides to apply on top of tier defaults.

    Returns:
        ThrottleConfig with tier defaults and any overrides applied.
    """
    # Resolve tier
    tier = SubscriptionTier.MAX_100
    if tier_name:
        for t in SubscriptionTier:
            if t.value == tier_name.lower():
                tier = t
                break

    defaults = _TIER_DEFAULTS[tier]
    config = ThrottleConfig(
        tier=tier,
        max_concurrent_runners=defaults["max_runners"],
        max_concurrent_workers=defaults["max_workers"],
    )

    # Apply overrides
    if overrides:
        for key, value in overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)

    return config


# ---------------------------------------------------------------------------
# Concurrency manager
# ---------------------------------------------------------------------------

class ConcurrencyManager:
    """Wraps an asyncio.Semaphore to enforce a tier-bound concurrency cap.

    The cap is fixed at construction time from ``ThrottleConfig.max_concurrent_workers``;
    callers use ``acquire``/``release`` to gate concurrent work against it.
    """

    def __init__(self, config: ThrottleConfig) -> None:
        self._config = config
        self._max = config.max_concurrent_workers
        self._effective = self._max
        self._semaphore = asyncio.Semaphore(self._max)
        self._overflow_lock = asyncio.Lock()

    @property
    def current_concurrency(self) -> int:
        """Current effective concurrency limit."""
        return self._effective

    async def acquire(self) -> None:
        """Acquire a concurrency slot, blocking if at effective limit."""
        await self._semaphore.acquire()

    def release(self) -> None:
        """Release a concurrency slot."""
        self._semaphore.release()
