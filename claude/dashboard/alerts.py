"""Alert detection and notification dispatch for the agent monitoring dashboard.

Evaluates running overnight session features for four alertable conditions:
stall (no activity for > 5 minutes), circuit breaker (CIRCUIT_BREAKER event
in overnight_events), deferred (feature status == "deferred"), and high rework
(rework_cycles >= 2). Fires notify.sh / cortex-notify-remote.sh subprocesses on first
trigger and deduplicates subsequent fires.

Functions:
    evaluate_alerts   -- detect/clear conditions, mutate state.alerts in place
    fire_notifications -- async fire notify.sh for new unnotified alerts
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from claude.dashboard.data import get_last_activity_ts

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
    """Fire notify.sh / cortex-notify-remote.sh for each new unnotified alert.

    Called every 5 seconds after ``evaluate_alerts``. For each alert entry
    with ``notified == False``, launches both notification scripts via
    ``asyncio.create_subprocess_shell`` (fire-and-forget). Subprocess failures
    are logged at WARNING and do not propagate.

    Args:
        state: Shared ``DashboardState`` instance (mutated in place).
        root: Project root path — notify scripts at ``root/hooks/cortex-notify.sh``
            and ``root/hooks/cortex-notify-remote.sh``.
    """
    notify_sh = root / "hooks" / "cortex-notify.sh"
    notify_remote_sh = root / "hooks" / "cortex-notify-remote.sh"

    async def _fire(script: Path, message: str) -> None:
        try:
            proc = await asyncio.create_subprocess_shell(
                f'{script} "{message}"',
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            asyncio.create_task(proc.wait())
        except Exception as exc:  # noqa: BLE001
            logger.warning("notify subprocess failed (%s): %s", script.name, exc)

    # Per-feature alerts
    for (slug, condition), entry in list(state.alerts.items()):
        if entry.get("notified"):
            continue

        if condition == "stall":
            message = f"\u26a0 {slug}: stalled (no activity for 5m)"
        elif condition == "deferred":
            message = f"\u23f8 {slug}: deferred"
        elif condition == "high_rework":
            count = entry.get("rework_cycles", 2)
            message = f"\U0001f504 {slug}: high rework ({count} cycles)"
        else:
            message = f"\u26a0 {slug}: {condition}"

        asyncio.create_task(_fire(notify_sh, message))
        asyncio.create_task(_fire(notify_remote_sh, message))
        entry["notified"] = True

    # Circuit breaker (once per session)
    if state.circuit_breaker_active and not state.circuit_breaker_notified:
        message = "\U0001f504 circuit breaker fired"
        asyncio.create_task(_fire(notify_sh, message))
        asyncio.create_task(_fire(notify_remote_sh, message))
        state.circuit_breaker_notified = True
