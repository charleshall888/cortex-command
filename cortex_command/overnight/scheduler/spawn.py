"""PID handshake helper with liveness probe (Task 6).

Public surface:
    - :func:`wait_for_pid_file` — poll for a ``runner.pid`` file appearance
      and return the contained PID once liveness is verified, or ``None``
      on timeout.

The handshake is the load-bearing primitive for the async-spawn contract
(spec R18): the parent CLI (or the launcher) writes a
``runner.spawn-pending`` sentinel, forks the runner under
``start_new_session=True``, then calls :func:`wait_for_pid_file` to wait
for the runner's own ``runner.pid`` write. On appearance the helper
performs an ``os.kill(pid, 0)`` liveness probe; if the runner has
already died (e.g., crashed within the first second), the probe raises
``ProcessLookupError`` and the helper returns ``None`` so the caller
can surface ``started: false, error_class: spawn_died`` instead of a
spurious ``started: true``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional


def _read_pid(path: Path) -> Optional[int]:
    """Best-effort read of the ``pid`` field from a ``runner.pid`` JSON file.

    Returns ``None`` if the file does not exist, is unreadable, is not
    valid JSON, or does not contain an integer ``pid`` field. The caller
    is expected to retry on transient failures inside the polling loop.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    pid = data.get("pid") if isinstance(data, dict) else None
    if isinstance(pid, int):
        return pid
    return None


def wait_for_pid_file(
    path: Path,
    timeout: float = 5.0,
    poll_interval: float = 0.05,
) -> Optional[int]:
    """Poll for ``path`` to appear and return the contained PID once live.

    Args:
        path: Filesystem path to the ``runner.pid`` JSON file.
        timeout: Wall-clock seconds to wait before giving up. The
            default 5.0 matches the spec R18 budget.
        poll_interval: Sleep between ``path.exists()`` checks. The
            default 50ms gives ~100 polls in the 5-second window with
            negligible CPU cost.

    Returns:
        The PID read from ``path`` once the file exists AND
        ``os.kill(pid, 0)`` succeeds (liveness verified). Returns
        ``None`` on:
          - timeout (file never appeared within ``timeout``);
          - liveness probe raises ``ProcessLookupError`` (runner died
            after writing ``runner.pid`` but before the probe ran);
          - ``runner.pid`` exists but is not parseable into an int PID.

        Callers distinguish the two ``None`` cases by checking the
        sentinel / file presence themselves; this helper only reports
        "verified-live PID available" vs "not yet, or no longer".
    """
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        if path.exists():
            pid = _read_pid(path)
            if pid is not None:
                # Liveness probe — distinguishes a runner that wrote
                # runner.pid then crashed before the parent's poll tick
                # from one still alive. ``os.kill(pid, 0)`` does not
                # send a signal; it only checks for process existence
                # under the current effective UID.
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    return None
                except PermissionError:
                    # Process exists but we cannot signal it. Treat as
                    # alive — the verify-by-magic step downstream can
                    # still reject a foreign claim.
                    return pid
                return pid
        if time.monotonic() >= deadline:
            return None
        time.sleep(poll_interval)
