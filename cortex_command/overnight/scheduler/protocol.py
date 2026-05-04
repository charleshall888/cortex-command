"""Scheduler protocol and result dataclasses.

Defines the platform-agnostic ``Scheduler`` ``Protocol`` (PEP 544) that
backends implement, plus the frozen dataclasses returned by
``schedule()`` and ``cancel()``. The macOS-only ``MacOSLaunchAgentBackend``
is the only shipped implementation; the protocol exists as a plug-in
extensibility point for future backends.

This module is intentionally backend-free: it imports nothing from
``macos`` so it remains importable on every platform. Backend selection
is handled by :mod:`cortex_command.overnight.scheduler.dispatch`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ScheduledHandle:
    """Handle returned by :meth:`Scheduler.schedule` describing the scheduled job.

    Fields:
        label: launchd label for the loaded agent (e.g.
            ``com.cortex.overnight.<session_id>``). Stable identifier
            used for ``cancel()`` and ``list_active()``.
        session_id: Overnight session identifier the schedule fires for.
        plist_path: Absolute path to the rendered launchd plist file.
        launcher_path: Absolute path to the per-schedule launcher script
            invoked by launchd.
        scheduled_for_iso: ISO 8601 timestamp of the resolved fire time.
        created_at_iso: ISO 8601 timestamp when the schedule was created.
    """

    label: str
    session_id: str
    plist_path: Path
    launcher_path: Path
    scheduled_for_iso: str
    created_at_iso: str


@dataclass(frozen=True)
class CancelResult:
    """Result returned by :meth:`Scheduler.cancel` describing teardown outcome.

    Fields:
        label: The launchd label that was targeted for cancellation.
        bootout_exit_code: Exit code from ``launchctl bootout``. ``0`` is
            success; non-zero indicates the agent was already gone or
            another error occurred (callers decide whether to treat as
            fatal).
        sidecar_removed: True if the sidecar tracking entry was removed.
        plist_removed: True if the plist file was removed from disk.
        launcher_removed: True if the launcher script was removed from
            disk.
    """

    label: str
    bootout_exit_code: int
    sidecar_removed: bool
    plist_removed: bool
    launcher_removed: bool


@runtime_checkable
class Scheduler(Protocol):
    """Platform-agnostic scheduler interface.

    Implementations schedule a one-shot overnight runner invocation at a
    target wall-clock time, manage its lifecycle (cancel, list), and
    declare whether the current platform is supported.
    """

    def schedule(
        self,
        target: datetime,
        session_id: str,
        env: dict[str, str],
        repo_root: Path,
    ) -> ScheduledHandle:
        """Schedule a one-shot overnight runner for ``session_id`` at ``target``.

        Args:
            target: Wall-clock fire time (timezone-aware).
            session_id: Overnight session identifier to attach to the
                scheduled job.
            env: Environment variables to inject into the launched
                runner process.
            repo_root: Absolute path to the repository the runner should
                operate in.

        Returns:
            ScheduledHandle describing the scheduled job.
        """
        ...

    def cancel(self, label: str) -> CancelResult:
        """Cancel a previously-scheduled job by ``label``."""
        ...

    def list_active(self) -> list[ScheduledHandle]:
        """Return handles for all currently-scheduled jobs."""
        ...

    @staticmethod
    def is_supported() -> bool:
        """Return True iff the current platform is supported by this backend."""
        ...
