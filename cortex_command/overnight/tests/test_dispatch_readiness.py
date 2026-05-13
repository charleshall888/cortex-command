"""Unit and integration tests for verify_dispatch_readiness() (R18).

Covers:
  * both-pass — auth resolves and worktree probe succeeds → ReadinessResult.ok=True.
  * auth-absent — probe_keychain_presence returns "absent" with vector=none →
    ReadinessResult with failed_check="auth".
  * worktree-blocked — auth passes but probe_worktree_writable returns ok=False →
    ReadinessResult with failed_check="worktree".
  * integration — run_daytime writes daytime-result.json with a structured error
    naming the failed check on readiness failure.

The worktree probe is patched in all cases to avoid real filesystem/git side
effects during CI.  Auth is patched to control vector and keychain outcomes
deterministically.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from cortex_command.overnight.readiness import ReadinessResult, verify_dispatch_readiness


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_auth_probe_result(ok: bool, vector: str = "env_preexisting", keychain: str = "skipped") -> object:
    """Build a minimal AuthProbeResult-compatible object for patching."""
    from cortex_command.overnight.auth import AuthProbeResult

    if ok:
        return AuthProbeResult(
            ok=True,
            vector=vector,
            keychain=keychain,
            result="ok",
            auth_event={"ts": "2026-01-01T00:00:00+00:00", "event": "auth_bootstrap", "vector": vector, "message": "ok"},
            probe_event=None,
        )
    else:
        return AuthProbeResult(
            ok=False,
            vector="none",
            keychain="absent",
            result="absent",
            auth_event={"ts": "2026-01-01T00:00:00+00:00", "event": "auth_bootstrap", "vector": "none", "message": "none"},
            probe_event={"ts": "2026-01-01T00:00:00+00:00", "event": "auth_probe", "vector": "none", "keychain": "absent", "result": "absent", "source": "ensure_sdk_auth"},
        )


def _make_probe_result(ok: bool, cause: str | None = None, hint: str | None = None) -> object:
    """Build a ProbeResult for patching probe_worktree_writable."""
    from cortex_command.pipeline.worktree import ProbeResult

    return ProbeResult(ok=ok, cause=cause, remediation_hint=hint)


# ---------------------------------------------------------------------------
# Test: both checks pass → ok=True
# ---------------------------------------------------------------------------


def test_both_pass_returns_ok(tmp_path: Path) -> None:
    """When auth resolves and worktree probe succeeds, ReadinessResult.ok is True."""
    auth_ok = _make_auth_probe_result(ok=True)
    wt_ok = _make_probe_result(ok=True)

    with (
        patch(
            "cortex_command.overnight.readiness.resolve_and_probe",
            return_value=auth_ok,
        ),
        patch(
            "cortex_command.overnight.readiness.resolve_worktree_root",
            return_value=tmp_path / "wt",
        ),
        patch(
            "cortex_command.overnight.readiness.probe_worktree_writable",
            return_value=wt_ok,
        ),
    ):
        result = verify_dispatch_readiness(feature="test-feat", session_id=None)

    assert result.ok is True
    assert result.failed_check is None
    assert result.cause is None
    assert result.remediation_hint is None
    assert result.auth_probe_result is auth_ok


# ---------------------------------------------------------------------------
# Test: auth probe absent → failed_check="auth"
# ---------------------------------------------------------------------------


def test_auth_absent_returns_failed_auth(tmp_path: Path) -> None:
    """When auth probe returns absent, ReadinessResult has failed_check='auth'."""
    auth_fail = _make_auth_probe_result(ok=False)

    with (
        patch(
            "cortex_command.overnight.readiness.resolve_and_probe",
            return_value=auth_fail,
        ),
        patch(
            "cortex_command.overnight.readiness.resolve_worktree_root",
            return_value=tmp_path / "wt",
        ),
        patch(
            "cortex_command.overnight.readiness.probe_worktree_writable",
        ) as mock_wt,
    ):
        result = verify_dispatch_readiness(feature="test-feat", session_id=None)

    assert result.ok is False
    assert result.failed_check == "auth"
    assert result.cause is not None
    assert "auth probe failed" in result.cause
    assert result.remediation_hint is not None
    # Worktree probe should not run when auth fails first.
    mock_wt.assert_not_called()


# ---------------------------------------------------------------------------
# Test: worktree probe blocked → failed_check="worktree"
# ---------------------------------------------------------------------------


def test_worktree_blocked_returns_failed_worktree(tmp_path: Path) -> None:
    """When auth passes but worktree probe fails, ReadinessResult has failed_check='worktree'."""
    auth_ok = _make_auth_probe_result(ok=True)
    wt_fail = _make_probe_result(
        ok=False,
        cause="sandbox_blocked",
        hint="Add the path to sandbox.filesystem.allowWrite.",
    )

    with (
        patch(
            "cortex_command.overnight.readiness.resolve_and_probe",
            return_value=auth_ok,
        ),
        patch(
            "cortex_command.overnight.readiness.resolve_worktree_root",
            return_value=tmp_path / "wt",
        ),
        patch(
            "cortex_command.overnight.readiness.probe_worktree_writable",
            return_value=wt_fail,
        ),
    ):
        result = verify_dispatch_readiness(feature="test-feat", session_id=None)

    assert result.ok is False
    assert result.failed_check == "worktree"
    assert result.cause == "sandbox_blocked"
    assert result.remediation_hint is not None
    assert "allowWrite" in result.remediation_hint


# ---------------------------------------------------------------------------
# Test: auth failure is checked before worktree (order guarantee)
# ---------------------------------------------------------------------------


def test_auth_checked_before_worktree(tmp_path: Path) -> None:
    """Auth failure returns immediately without running the worktree probe."""
    auth_fail = _make_auth_probe_result(ok=False)

    with (
        patch(
            "cortex_command.overnight.readiness.resolve_and_probe",
            return_value=auth_fail,
        ),
        patch(
            "cortex_command.overnight.readiness.resolve_worktree_root",
        ) as mock_root,
        patch(
            "cortex_command.overnight.readiness.probe_worktree_writable",
        ) as mock_probe,
    ):
        result = verify_dispatch_readiness(feature="test-feat", session_id=None)

    assert result.ok is False
    assert result.failed_check == "auth"
    # resolve_worktree_root and probe_worktree_writable must not run.
    mock_root.assert_not_called()
    mock_probe.assert_not_called()


# ---------------------------------------------------------------------------
# Integration: run_daytime writes structured error on auth readiness failure
# ---------------------------------------------------------------------------


def test_run_daytime_writes_structured_error_on_auth_failure() -> None:
    """daytime-result.json includes a structured error naming 'auth' on auth failure."""
    from cortex_command.overnight.daytime_pipeline import run_daytime

    feature = "dispatch-readiness-test-auth"

    with tempfile.TemporaryDirectory() as raw_td:
        td = Path(raw_td)
        feat_dir = td / "cortex" / "lifecycle" / feature
        feat_dir.mkdir(parents=True)
        (feat_dir / "plan.md").write_text(f"# {feature}\n", encoding="utf-8")

        orig_dir = os.getcwd()
        try:
            os.chdir(td)
            auth_fail = _make_auth_probe_result(ok=False)
            readiness_fail = ReadinessResult(
                ok=False,
                failed_check="auth",
                cause=(
                    "auth probe failed: vector=none, keychain=absent — "
                    "Keychain entry absent; no auth vector available"
                ),
                remediation_hint="Set ANTHROPIC_API_KEY or authenticate via 'claude auth login'.",
                auth_probe_result=auth_fail,
            )
            stderr_buf = io.StringIO()
            with (
                patch.object(sys, "stderr", stderr_buf),
                patch(
                    "cortex_command.overnight.daytime_pipeline.verify_dispatch_readiness",
                    return_value=readiness_fail,
                ),
            ):
                rc = asyncio.run(run_daytime(feature))

            assert rc == 1

            result_path = td / "cortex" / "lifecycle" / feature / "daytime-result.json"
            assert result_path.exists(), "daytime-result.json was not written"
            with result_path.open(encoding="utf-8") as fh:
                result_data = json.load(fh)

        finally:
            os.chdir(orig_dir)

    assert result_data["terminated_via"] == "startup_failure"
    assert result_data["outcome"] == "failed"
    assert result_data["error"] is not None
    # Error must name the failed check.
    assert "failed_check=auth" in result_data["error"]


# ---------------------------------------------------------------------------
# Integration: run_daytime writes structured error on worktree readiness failure
# ---------------------------------------------------------------------------


def test_run_daytime_writes_structured_error_on_worktree_failure() -> None:
    """daytime-result.json includes a structured error naming 'worktree' on worktree failure."""
    from cortex_command.overnight.daytime_pipeline import run_daytime

    feature = "dispatch-readiness-test-wt"

    with tempfile.TemporaryDirectory() as raw_td:
        td = Path(raw_td)
        feat_dir = td / "cortex" / "lifecycle" / feature
        feat_dir.mkdir(parents=True)
        (feat_dir / "plan.md").write_text(f"# {feature}\n", encoding="utf-8")

        orig_dir = os.getcwd()
        try:
            os.chdir(td)
            auth_ok = _make_auth_probe_result(ok=True)
            readiness_fail = ReadinessResult(
                ok=False,
                failed_check="worktree",
                cause="sandbox_blocked",
                remediation_hint="Add the path to sandbox.filesystem.allowWrite.",
                auth_probe_result=auth_ok,
            )
            stderr_buf = io.StringIO()
            with (
                patch.object(sys, "stderr", stderr_buf),
                patch(
                    "cortex_command.overnight.daytime_pipeline.verify_dispatch_readiness",
                    return_value=readiness_fail,
                ),
            ):
                rc = asyncio.run(run_daytime(feature))

            assert rc == 1

            result_path = td / "cortex" / "lifecycle" / feature / "daytime-result.json"
            assert result_path.exists(), "daytime-result.json was not written"
            with result_path.open(encoding="utf-8") as fh:
                result_data = json.load(fh)

        finally:
            os.chdir(orig_dir)

    assert result_data["terminated_via"] == "startup_failure"
    assert result_data["outcome"] == "failed"
    assert result_data["error"] is not None
    # Error must name the failed check.
    assert "failed_check=worktree" in result_data["error"]
