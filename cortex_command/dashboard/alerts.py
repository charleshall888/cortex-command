"""Alert detection and notification dispatch for the agent monitoring dashboard.

Evaluates running overnight session features for four alertable conditions:
stall (no activity for > 5 minutes), circuit breaker (CIRCUIT_BREAKER event
in overnight_events), deferred (feature status == "deferred"), and high rework
(rework_cycles >= 2). Logs first-trigger notifications and deduplicates
subsequent fires via a notified flag.

Functions:
    evaluate_alerts    -- detect/clear conditions, mutate state.alerts in place
    fire_notifications -- log new unnotified alerts and mark them notified
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from cortex_command.dashboard.data import get_last_activity_ts

logger = logging.getLogger(__name__)

_STALL_THRESHOLD_SECS = 300  # 5 minutes


def evaluate_alerts(state: "DashboardState", root: Path, lifecycle_dir: Path) -> None:  # type: ignore[name-defined]
    """Evaluate alert conditions and mutate state.alerts / circuit_breaker_active.

    Called every 5 seconds from the alert polling task. Adds new alert entries
    when conditions become true; removes them when conditions clear.

    Conditions:
    - stall: ``status == "running"`` and last activity > 5 minutes ago
    - circuit_breaker: any event in ``overnight_events`` has
      ``event == "CIRCUIT_BREAKER"``
    - deferred: ``status == "deferred"``
    - high_rework: ``rework_cycles >= 2``

    Args:
        state: Shared ``DashboardState`` instance (mutated in place).
        root: Project root path (unused; reserved for future use).
        lifecycle_dir: Path to the ``lifecycle/`` directory.
    """
    if not state.overnight:
        return

    now = datetime.now(timezone.utc)
    features = state.overnight.get("features", {})

    # --- Circuit breaker (session-level) ---
    if not state.circuit_breaker_active:
        for event in state.overnight_events:
            if event.get("event") == "CIRCUIT_BREAKER":
                state.circuit_breaker_active = True
                break

    # --- Per-feature conditions ---
    for slug, feat in features.items():
        status = feat.get("status", "")
        fs = (state.feature_states.get(slug) or {})
        rework = fs.get("rework_cycles", 0)

        # Stall: running with no activity for > threshold
        if status == "running":
            last_ts = get_last_activity_ts(slug, lifecycle_dir)
            if last_ts is not None:
                stale = (now - last_ts).total_seconds() > _STALL_THRESHOLD_SECS
                if stale:
                    key = (slug, "stall")
                    if key not in state.alerts:
                        state.alerts[key] = {"first_seen": now, "notified": False}
                else:
                    state.alerts.pop((slug, "stall"), None)
            else:
                state.alerts.pop((slug, "stall"), None)
        else:
            state.alerts.pop((slug, "stall"), None)

        # Deferred
        if status == "deferred":
            key = (slug, "deferred")
            if key not in state.alerts:
                state.alerts[key] = {"first_seen": now, "notified": False}
        else:
            state.alerts.pop((slug, "deferred"), None)

        # High rework
        if rework >= 2:
            key = (slug, "high_rework")
            if key not in state.alerts:
                state.alerts[key] = {"first_seen": now, "notified": False, "rework_cycles": rework}
        else:
            state.alerts.pop((slug, "high_rework"), None)


async def fire_notifications(state: "DashboardState", root: Path) -> None:  # type: ignore[name-defined]
    """Log newly-detected alerts and mark them notified.

    Called every 5 seconds after ``evaluate_alerts``. For each alert entry
    with ``notified == False``, emits a log line and flips ``notified`` to
    ``True`` so subsequent ticks do not re-fire. The shell-subprocess
    notification channel was retired with the shareable-install scaffolding;
    machine-config is now responsible for wiring alert messages to any
    desktop-notifier surface.

    Args:
        state: Shared ``DashboardState`` instance (mutated in place).
        root: Project root path (unused; reserved for future use).
    """
    # Per-feature alerts
    for (slug, condition), entry in list(state.alerts.items()):
        if entry.get("notified"):
            continue

        if condition == "stall":
            message = f"⚠ {slug}: stalled (no activity for 5m)"
        elif condition == "deferred":
            message = f"⏸ {slug}: deferred"
        elif condition == "high_rework":
            count = entry.get("rework_cycles", 2)
            message = f"\U0001f504 {slug}: high rework ({count} cycles)"
        else:
            message = f"⚠ {slug}: {condition}"

        logger.info("alert: %s", message)
        entry["notified"] = True

    # Circuit breaker (once per session)
    if state.circuit_breaker_active and not state.circuit_breaker_notified:
        logger.info("alert: \U0001f504 circuit breaker fired")
        state.circuit_breaker_notified = True
