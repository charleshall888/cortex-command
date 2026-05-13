"""Daytime integration tests for auth probe scenarios.

Covers:
  * R3 policy — when ``resolve_and_probe()`` returns ``ok=False`` (probe
    result="absent"), ``run_daytime`` must hard-fail before any worktree
    creation, and the outer finally must write ``daytime-result.json`` with
    ``terminated_via == "startup_failure"`` and an error string containing
    ``"no auth vector available"``.
  * R3 policy — when ``resolve_and_probe()`` returns ``ok=True`` with
    ``vector!="none"`` (explicit env credential), ``run_daytime`` proceeds
    past Phase A (startup_failure is NOT triggered in Phase A for auth).
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import unittest
from pathlib import Path
from unittest.mock import patch


class _CwdCtx:
    """Chdir context manager — mirrors test_daytime_pipeline.py."""

    def __init__(self, path: Path):
        self._path = path
        self._orig: str | None = None

    def __enter__(self) -> None:
        self._orig = os.getcwd()
        os.chdir(self._path)

    def __exit__(self, *exc) -> None:
        if self._orig is not None:
            os.chdir(self._orig)


def _run_async(coro):
    """Run ``coro`` to completion on a fresh event loop."""
    return asyncio.run(coro)


def test_no_auth_vector_absent_keychain_hard_fails() -> None:
    """vector=none AND probe=absent → ``daytime-result.json`` records startup_failure.

    Setup:
      * ``ANTHROPIC_API_KEY``, ``ANTHROPIC_AUTH_TOKEN``, and
        ``CLAUDE_CODE_OAUTH_TOKEN`` are all unset so ``ensure_sdk_auth``
        resolves ``vector="none"``.
      * ``pathlib.Path.home()`` is redirected to an empty fixture dir
        (no ``.claude/settings.json``, no ``personal-oauth-token``) so
        the helper and oauth-file branches both fail.
      * ``probe_keychain_presence`` is patched to return ``"absent"`` so
        the R3 policy triggers the startup_failure path deterministically,
        without relying on the real Keychain state of the test machine.
      * CWD is pinned to the fixture root so the finally's cwd-relative
        write of ``cortex/lifecycle/<feature>/daytime-result.json`` lands
        inside the fixture rather than polluting the real repo.
      * A minimal ``cortex/lifecycle/<feature>/plan.md`` is created so the
        ``_check_cwd`` guard passes; the hard-fail must still occur
        before ``execute_feature`` runs.
    """
    import tempfile

    from cortex_command.overnight.daytime_pipeline import run_daytime

    feature = "feat"

    with tempfile.TemporaryDirectory() as raw_td:
        td = Path(raw_td)

        # Build the minimal fixture feature inside td so _check_cwd
        # (which looks for ``lifecycle/`` in cwd) passes.
        feat_dir = td / "cortex" / "lifecycle" / feature
        feat_dir.mkdir(parents=True)
        (feat_dir / "plan.md").write_text(f"# {feature}\n", encoding="utf-8")

        # Save-and-restore the auth env vars so we can unset them for the
        # duration of the call without leaking state across tests.
        preserved = {}
        for var in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
            if var in os.environ:
                preserved[var] = os.environ.pop(var)
        try:
            with (
                _CwdCtx(td),
                # Redirect ~/.claude/* lookups into the empty td: no
                # settings.json, no personal-oauth-token → vector "none".
                patch.object(
                    pathlib.Path, "home", staticmethod(lambda: td)
                ),
                # Patch probe to return "absent" so the R3 startup_failure
                # path fires deterministically regardless of real Keychain state.
                patch(
                    "cortex_command.overnight.auth.probe_keychain_presence",
                    return_value="absent",
                ),
            ):
                rc = _run_async(run_daytime(feature))
        finally:
            for var, val in preserved.items():
                os.environ[var] = val

        assert rc == 1

        result_path = td / "cortex" / "lifecycle" / feature / "daytime-result.json"
        assert result_path.exists(), "daytime-result.json was not written"

        with result_path.open(encoding="utf-8") as fh:
            result = json.load(fh)

    assert result["terminated_via"] == "startup_failure"
    assert result["outcome"] == "failed"
    assert result["error"] is not None
    assert "no auth vector available" in result["error"]


def test_no_auth_vector_unavailable_keychain_continues() -> None:
    """vector=none AND probe=unavailable → Phase A does NOT trigger startup_failure.

    The R3 policy treats "unavailable" as continue-with-soft-warning.
    This test verifies the pipeline does NOT write startup_failure for
    the unavailable probe outcome. It is expected to fail further in the
    pipeline (e.g. plan.md not found or worktree creation fails), but the
    auth probe itself does not block execution.
    """
    import tempfile

    from cortex_command.overnight.daytime_pipeline import run_daytime

    feature = "feat-unavailable"

    with tempfile.TemporaryDirectory() as raw_td:
        td = Path(raw_td)

        feat_dir = td / "cortex" / "lifecycle" / feature
        feat_dir.mkdir(parents=True)
        (feat_dir / "plan.md").write_text(f"# {feature}\n", encoding="utf-8")

        preserved = {}
        for var in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
            if var in os.environ:
                preserved[var] = os.environ.pop(var)
        try:
            with (
                _CwdCtx(td),
                patch.object(
                    pathlib.Path, "home", staticmethod(lambda: td)
                ),
                # Probe returns "unavailable" — R3 says continue.
                patch(
                    "cortex_command.overnight.auth.probe_keychain_presence",
                    return_value="unavailable",
                ),
            ):
                rc = _run_async(run_daytime(feature))
        finally:
            for var, val in preserved.items():
                os.environ[var] = val

        result_path = td / "cortex" / "lifecycle" / feature / "daytime-result.json"
        assert result_path.exists(), "daytime-result.json was not written"

        with result_path.open(encoding="utf-8") as fh:
            result = json.load(fh)

    # The pipeline must NOT fail with startup_failure due to auth probe.
    # It may fail for other reasons (worktree, batch runner, etc.).
    assert result["terminated_via"] != "startup_failure" or (
        result["error"] is not None
        and "no auth vector available" not in result["error"]
    ), (
        f"Pipeline unexpectedly triggered auth startup_failure with probe=unavailable; "
        f"result={result}"
    )


# ---------------------------------------------------------------------------
# Retain the original test name as an alias for backward compatibility with
# any devs grepping for ``test_no_auth_vector_hard_fails`` in the test suite.
# ---------------------------------------------------------------------------

test_no_auth_vector_hard_fails = test_no_auth_vector_absent_keychain_hard_fails


if __name__ == "__main__":
    unittest.main()
