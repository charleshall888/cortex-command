"""macOS launchd backend stub.

Task 1 ships only the importable class skeleton; Task 2 fleshes out the
launchd plist rendering, ``launchctl bootstrap`` invocation, sidecar
tracking, and teardown logic. Method bodies raise ``NotImplementedError``
so accidental early use surfaces loudly.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from cortex_command.overnight.scheduler.protocol import (
    CancelResult,
    ScheduledHandle,
)


class MacOSLaunchAgentBackend:
    """launchd-backed scheduler. Filled in by Task 2."""

    def schedule(
        self,
        target: datetime,
        session_id: str,
        env: dict[str, str],
        repo_root: Path,
    ) -> ScheduledHandle:
        raise NotImplementedError(
            "MacOSLaunchAgentBackend.schedule() is implemented in Task 2"
        )

    def cancel(self, label: str) -> CancelResult:
        raise NotImplementedError(
            "MacOSLaunchAgentBackend.cancel() is implemented in Task 2"
        )

    def list_active(self) -> list[ScheduledHandle]:
        raise NotImplementedError(
            "MacOSLaunchAgentBackend.list_active() is implemented in Task 2"
        )

    @staticmethod
    def is_supported() -> bool:
        return sys.platform == "darwin"
