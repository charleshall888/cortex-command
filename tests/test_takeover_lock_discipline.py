"""Static gate enforcing that ``.runner.pid.takeover.lock`` is referenced only
from ``cortex_command/overnight/ipc.py``.

The takeover lockfile is the kernel coordination artifact that serializes
``_check_concurrent_start`` + ``write_runner_pid`` + ``handle_cancel`` (per the
spec at ``lifecycle/fix-runnerpid-takeover-race-in-ipcpywrite-runner-pid/spec.md``).
Its discipline rules — never written, never unlinked, never ``durable_fsync``'d,
must not be matched by ``*.lock`` globs — are load-bearing for correctness.
Concentrating every reference to the path in ``ipc.py`` lets reviewers audit
the lockfile contract from a single file; any other module mentioning the path
is a regression risk (silent write/unlink/glob misuse) and must be flagged at
``just test`` time rather than at runtime.

This static gate walks ``cortex_command/`` for ``.py`` files, line-scans for the
literal substring ``runner.pid.takeover.lock``, and fails if any match lives
outside ``cortex_command/overnight/ipc.py``.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = REPO_ROOT / "cortex_command"
ALLOWED_FILE = PACKAGE_ROOT / "overnight" / "ipc.py"
SUBSTRING = "runner.pid.takeover.lock"


def test_takeover_lock_discipline() -> None:
    """Only ``cortex_command/overnight/ipc.py`` may reference the lockfile path."""
    violations: list[str] = []
    for py_path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if py_path.resolve() == ALLOWED_FILE.resolve():
            continue
        try:
            text = py_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if SUBSTRING in line:
                violations.append(f"{py_path}:{lineno}: {line.strip()}")

    assert not violations, (
        "Found references to '"
        + SUBSTRING
        + "' outside cortex_command/overnight/ipc.py. The takeover lockfile "
        "path must be referenced only from ipc.py to keep the lockfile "
        "discipline (never written, never unlinked, never durable_fsync'd) "
        "auditable from a single file. Violations:\n  "
        + "\n  ".join(violations)
    )
