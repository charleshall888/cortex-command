"""Backend dispatch for the scheduler package.

``get_backend()`` selects ``MacOSLaunchAgentBackend`` on darwin and
``_UnsupportedScheduler`` everywhere else. The unsupported backend's
methods raise ``NotImplementedError`` and ``is_supported()`` returns
``False``, so CLI surfaces can detect the platform and exit cleanly
with a "macOS-only" message rather than crashing on import.

Tests monkeypatch ``sys.platform`` (or ``cortex_command.overnight.
scheduler.dispatch.sys.platform``) to drive both branches.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from cortex_command.overnight.scheduler.macos import MacOSLaunchAgentBackend
from cortex_command.overnight.scheduler.protocol import (
    CancelResult,
    ScheduledHandle,
    Scheduler,
)


class _UnsupportedScheduler:
    """Scheduler stub used on non-darwin platforms.

    All scheduling operations raise ``NotImplementedError``. Callers
    should check ``is_supported()`` before invoking other methods and
    surface a platform-appropriate error to the user.
    """

    _UNSUPPORTED_MSG = "cortex overnight scheduling requires macOS"

    def schedule(
        self,
        target: datetime,
        session_id: str,
        env: dict[str, str],
        repo_root: Path,
    ) -> ScheduledHandle:
        raise NotImplementedError(self._UNSUPPORTED_MSG)

    def cancel(self, label: str) -> CancelResult:
        raise NotImplementedError(self._UNSUPPORTED_MSG)

    def list_active(self) -> list[ScheduledHandle]:
        raise NotImplementedError(self._UNSUPPORTED_MSG)

    @staticmethod
    def is_supported() -> bool:
        return False


def get_backend() -> Scheduler:
    """Return the scheduler backend for the current platform.

    Returns ``MacOSLaunchAgentBackend()`` on darwin, otherwise an
    ``_UnsupportedScheduler`` whose ``is_supported()`` is ``False``.
    """
    if sys.platform == "darwin":
        return MacOSLaunchAgentBackend()
    return _UnsupportedScheduler()
