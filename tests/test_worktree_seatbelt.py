"""Seatbelt-active integration tests for both worktree dispatch paths.

R10 of restore-worktree-root-env-prefix: prove the new branch-(c) default
(``$TMPDIR/cortex-worktrees/<feature>``) passes the Seatbelt writability
probe AND that the bash hook's path matches end-to-end.

These tests skip outside an active sandbox via a kernel-level capability
probe: the ``seatbelt_active`` fixture attempts to open ``<repo>/.git/HEAD``
for write (``O_WRONLY``, no truncation, no creation). ``.git/HEAD`` is one
of the suffixes denied by ``build_orchestrator_deny_paths`` in
``cortex_command/overnight/sandbox_settings.py``, so a successful open
means no sandbox is enforcing and the tests would not actually exercise
the Seatbelt property they are designed to verify.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from cortex_command.pipeline.worktree import (
    cleanup_worktree,
    probe_worktree_writable,
    resolve_worktree_root,
)


def _repo_root() -> Path:
    """Resolve this repo's root via git rev-parse for hook stdin payload."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


@pytest.fixture(scope="module")
def seatbelt_active() -> bool:
    """Kernel-level capability probe: is Seatbelt denying writes to .git/HEAD?

    Replaces the legacy ``CLAUDE_CODE_SANDBOX`` env-var gate (which was
    undocumented on macOS Seatbelt and silently skipped). The probe attempts
    ``O_WRONLY`` on ``<repo>/.git/HEAD`` without ``O_TRUNC`` or ``O_CREAT`` —
    the file exists and the open does not truncate or write any bytes.

    Returns ``True`` when ``PermissionError`` is raised (sandbox enforcing).
    Calls ``pytest.skip`` when the open succeeds (no sandbox active). Calls
    ``pytest.fail`` when the sentinel is missing (test must run from a git
    checkout — silent skip would be the failure mode this lifecycle closes).
    """
    sentinel = _repo_root() / ".git" / "HEAD"
    try:
        fd = os.open(sentinel, os.O_WRONLY)
    except PermissionError:
        return True
    except FileNotFoundError:
        pytest.fail(
            "kernel probe sentinel .git/HEAD missing; run from a git checkout"
        )
    else:
        os.close(fd)
        pytest.skip(
            "sandbox not active (open-for-write to .git/HEAD succeeded)"
        )


def test_python_resolver_default_passes_probe_under_seatbelt(seatbelt_active):
    """R10(a): the Python resolver's branch-(c) default is writable under Seatbelt."""
    feature = "verify-r10-py"
    try:
        worktree_root = resolve_worktree_root(feature, session_id=None)
        result = probe_worktree_writable(worktree_root)
        assert result.ok is True, (
            f"probe failed: cause={result.cause!r}, "
            f"remediation_hint={result.remediation_hint!r}"
        )
        assert result.cause is None
    finally:
        cleanup_worktree(feature)


def test_hook_emitted_path_passes_probe_under_seatbelt(seatbelt_active):
    """R10(b): the bash hook's emitted path is writable under Seatbelt."""
    feature = "verify-r10-hook"
    repo = _repo_root()
    hook_path = repo / "claude" / "hooks" / "cortex-worktree-create.sh"
    payload = json.dumps({"cwd": str(repo), "name": feature})

    try:
        completed = subprocess.run(
            [str(hook_path)],
            input=payload,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, (
            f"hook failed with exit {completed.returncode}; "
            f"stderr={completed.stderr!r}"
        )
        emitted_path = completed.stdout.strip()
        assert emitted_path, f"hook emitted empty stdout; stderr={completed.stderr!r}"

        result = probe_worktree_writable(Path(emitted_path))
        assert result.ok is True, (
            f"probe of hook-emitted path failed: "
            f"path={emitted_path!r}, cause={result.cause!r}, "
            f"remediation_hint={result.remediation_hint!r}"
        )
    finally:
        cleanup_worktree(feature)
