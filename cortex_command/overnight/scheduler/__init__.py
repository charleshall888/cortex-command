"""Scheduler package: protocol, dataclasses, and backend dispatch.

Public surface:
    - ``Scheduler`` — platform-agnostic protocol implemented by backends.
    - ``ScheduledHandle`` — frozen dataclass returned by ``schedule()``.
    - ``CancelResult`` — frozen dataclass returned by ``cancel()``.
    - ``get_backend()`` — returns the backend for the current platform.

Only ``MacOSLaunchAgentBackend`` ships today; non-darwin platforms get an
internal ``_UnsupportedScheduler`` whose ``is_supported()`` returns
False so CLI surfaces can exit cleanly with a "macOS-only" message.
"""

from __future__ import annotations

from cortex_command.overnight.scheduler.dispatch import get_backend
from cortex_command.overnight.scheduler.protocol import (
    CancelResult,
    ScheduledHandle,
    Scheduler,
)

__all__ = [
    "CancelResult",
    "ScheduledHandle",
    "Scheduler",
    "get_backend",
]
