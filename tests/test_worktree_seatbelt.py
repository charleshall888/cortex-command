"""Seatbelt-active integration tests for both worktree dispatch paths.

R10 of restore-worktree-root-env-prefix: prove the new branch-(c) default
(``$TMPDIR/cortex-worktrees/<feature>``) passes the Seatbelt writability
probe AND that the bash hook's path matches end-to-end.

These tests are skipped outside an active Claude Code Bash session (where
``CLAUDE_CODE_SANDBOX=1`` is set). The skip is structural — running them
without an active sandbox would not exercise the property they are designed
to verify (whether the Seatbelt OS-level sandbox actually permits the path).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cortex_command.pipeline.worktree import (
    cleanup_worktree,
    probe_worktree_writable,
    resolve_worktree_root,
)


SEATBELT_REASON = "requires active Claude Code Seatbelt sandbox (CLAUDE_CODE_SANDBOX=1)"


def _repo_root() -> Path:
    """Resolve this repo's root via git rev-parse for hook stdin payload."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


@pytest.mark.skipif(
    os.environ.get("CLAUDE_CODE_SANDBOX") != "1",
    reason=SEATBELT_REASON,
)
def test_python_resolver_default_passes_probe_under_seatbelt():
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


@pytest.mark.skipif(
    os.environ.get("CLAUDE_CODE_SANDBOX") != "1",
    reason=SEATBELT_REASON,
)
def test_hook_emitted_path_passes_probe_under_seatbelt():
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
