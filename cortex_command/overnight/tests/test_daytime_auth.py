"""Daytime hard-fail integration test for no-auth-vector scenarios.

Pins spec R6: when ``ensure_sdk_auth()`` resolves ``vector == "none"``
during ``run_daytime``'s Phase A auth bootstrap, the pipeline must
hard-fail before any worktree creation, and the outer finally must
write ``daytime-result.json`` with ``terminated_via == "startup_failure"``
and an error string containing ``"no auth vector available"``.
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


def test_no_auth_vector_hard_fails() -> None:
    """No auth vector available → ``daytime-result.json`` records a
    startup_failure with the R6 error substring.

    Setup:
      * ``ANTHROPIC_API_KEY`` and ``CLAUDE_CODE_OAUTH_TOKEN`` are both
        unset so ``ensure_sdk_auth`` cannot short-circuit on env.
      * ``pathlib.Path.home()`` is redirected to an empty fixture dir
        (no ``.claude/settings.json``, no ``personal-oauth-token``) so
        the helper and oauth-file branches both fail.
      * CWD is pinned to the fixture root so the finally's cwd-relative
        write of ``lifecycle/<feature>/daytime-result.json`` lands
        inside the fixture rather than polluting the real repo.
      * A minimal ``lifecycle/<feature>/plan.md`` is created so the
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
        feat_dir = td / "lifecycle" / feature
        feat_dir.mkdir(parents=True)
        (feat_dir / "plan.md").write_text(f"# {feature}\n", encoding="utf-8")

        # Save-and-restore the auth env vars so we can unset them for the
        # duration of the call without leaking state across tests.
        preserved = {}
        for var in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
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
            ):
                rc = _run_async(run_daytime(feature))
        finally:
            for var, val in preserved.items():
                os.environ[var] = val

        assert rc == 1

        result_path = td / "lifecycle" / feature / "daytime-result.json"
        assert result_path.exists(), "daytime-result.json was not written"

        with result_path.open(encoding="utf-8") as fh:
            result = json.load(fh)

    assert result["terminated_via"] == "startup_failure"
    assert result["outcome"] == "failed"
    assert result["error"] is not None
    assert "no auth vector available" in result["error"]


if __name__ == "__main__":
    unittest.main()
