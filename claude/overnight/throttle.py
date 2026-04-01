"""Subscription-aware concurrency management with adaptive rate limit backoff.

Manages how many concurrent agents the system spawns based on subscription
tier, detects rate limit responses, and reduces concurrency dynamically.
Wraps the pipeline's dispatch_task with rate limit detection and backoff.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from claude.pipeline.dispatch import DispatchResult, dispatch_task
from claude.pipeline.state import log_event


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
    """Configuration for subscription-aware concurrency management.

    Fields:
        tier: Subscription tier enum.
        max_concurrent_runners: Max batch runners running in parallel.
        max_concurrent_workers: Max workers per batch runner.
        backoff_base_seconds: Base delay for exponential backoff.
        backoff_max_seconds: Maximum delay cap.
        rate_limit_threshold: Rate limits within window before reducing.
    """

    tier: SubscriptionTier = SubscriptionTier.MAX_100
    max_concurrent_runners: int = 2
    max_concurrent_workers: int = 2
    backoff_base_seconds: float = 30.0
    backoff_max_seconds: float = 300.0
    rate_limit_threshold: int = 3


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
# Adaptive concurrency manager
# ---------------------------------------------------------------------------

class ConcurrencyManager:
    """Wraps an asyncio.Semaphore with adaptive concurrency.

    Reduces effective concurrency when rate limits are detected within
    a sliding window, and restores it after consecutive successes.
    """

    def __init__(self, config: ThrottleConfig) -> None:
        self._config = config
        self._max = config.max_concurrent_workers
        self._effective = self._max
        self._semaphore = asyncio.Semaphore(self._max)
        self._overflow_lock = asyncio.Lock()

        # Rate limit tracking (sliding window)
        self._rate_limit_timestamps: list[float] = []
        self._window_seconds = 300.0  # 5 minutes

        # Restoration tracking
        self._consecutive_successes = 0
        self._successes_to_restore = 10

        # Stats
        self._total_rate_limits = 0
        self._reductions = 0
        self._restorations = 0

    @property
    def current_concurrency(self) -> int:
        """Current effective concurrency limit."""
        return self._effective

    @property
    def stats(self) -> dict:
        """Return throttle statistics for reporting."""
        return {
            "total_rate_limits": self._total_rate_limits,
            "reductions": self._reductions,
            "restorations": self._restorations,
            "current_limit": self._effective,
            "max_limit": self._max,
        }

    async def acquire(self) -> None:
        """Acquire a concurrency slot, blocking if at effective limit."""
        await self._semaphore.acquire()

    def release(self) -> None:
        """Release a concurrency slot."""
        self._semaphore.release()

    def report_rate_limit(self) -> None:
        """Record a rate limit event.

        After threshold events within the sliding window, reduces
        effective concurrency by 1 (minimum 1).
        """
        now = time.monotonic()
        self._total_rate_limits += 1
        self._consecutive_successes = 0

        # Add to sliding window
        self._rate_limit_timestamps.append(now)

        # Prune old entries
        cutoff = now - self._window_seconds
        self._rate_limit_timestamps = [
            ts for ts in self._rate_limit_timestamps if ts > cutoff
        ]

        # Check threshold
        if len(self._rate_limit_timestamps) >= self._config.rate_limit_threshold:
            if self._effective > 1:
                self._effective -= 1
                self._reductions += 1
            # Clear window after reduction
            self._rate_limit_timestamps.clear()

    def report_success(self) -> None:
        """Record a successful dispatch.

        After consecutive successes post-reduction, restores
        concurrency by 1 (up to original max).
        """
        self._consecutive_successes += 1

        if (
            self._effective < self._max
            and self._consecutive_successes >= self._successes_to_restore
        ):
            self._effective += 1
            self._restorations += 1
            self._consecutive_successes = 0


# ---------------------------------------------------------------------------
# Throttled dispatch wrapper
# ---------------------------------------------------------------------------

async def throttled_dispatch(
    feature: str,
    task: str,
    worktree_path: Path,
    complexity: str,
    system_prompt: str,
    manager: ConcurrencyManager,
    log_path: Optional[Path] = None,
    criticality: str = "medium",
) -> DispatchResult:
    """Dispatch a task with rate limit detection and adaptive backoff.

    Wraps ``dispatch_task()`` with concurrency management. On rate limit
    (infrastructure_failure), applies exponential backoff and reports
    to the ConcurrencyManager.

    Args:
        feature: Feature name for logging.
        task: Task prompt.
        worktree_path: Working directory.
        complexity: Complexity tier.
        system_prompt: System prompt for the agent.
        manager: ConcurrencyManager instance.
        log_path: Optional event log path.
        criticality: Criticality level.

    Returns:
        DispatchResult from the underlying dispatch.
    """
    await manager.acquire()
    try:
        result = await dispatch_task(
            feature=feature,
            task=task,
            worktree_path=worktree_path,
            complexity=complexity,
            system_prompt=system_prompt,
            log_path=log_path,
            criticality=criticality,
        )

        if result.success:
            manager.report_success()
        elif result.error_type == "infrastructure_failure":
            manager.report_rate_limit()

            # Exponential backoff
            attempt = manager._total_rate_limits
            delay = min(
                manager._config.backoff_base_seconds * (2 ** (attempt - 1)),
                manager._config.backoff_max_seconds,
            )

            if log_path:
                log_event(log_path, {
                    "event": "throttle_backoff",
                    "feature": feature,
                    "delay_seconds": delay,
                    "current_concurrency": manager.current_concurrency,
                })

            await asyncio.sleep(delay)

        return result
    finally:
        manager.release()
