"""Unit tests for the advisory `cortex upgrade` handler in cortex_command.cli.

The original handler ran `git pull` + `uv tool install -e` against a local
clone. Under the wheel-install migration (Tasks 1–14) the CLI ships from a
tag-pinned wheel and cannot self-upgrade — instead `cortex upgrade` is an
advisory printer that points users at:

  1. ``/plugin update cortex-overnight@cortex-command`` for the
     MCP-driven path (the auto-install hook in the MCP server reinstalls the
     CLI on first tool call after the plugin updates).
  2. ``uv tool install --reinstall git+...@<tag>`` for the bare-shell path.

These tests verify:
  (a) the handler exits 0;
  (b) stdout contains the ``/plugin update`` substring (MCP path advisory);
  (c) stdout contains the ``--reinstall`` substring (bare-shell path advisory);
  (d) the handler does NOT shell out to ``git`` or ``uv`` (no
      ``subprocess.run([...])`` calls under the new advisory contract).
"""

from __future__ import annotations

import io
import sys
import unittest
from unittest.mock import MagicMock, patch

from cortex_command.cli import _dispatch_upgrade


class TestCortexUpgrade(unittest.TestCase):
    """Tests for the advisory ``_dispatch_upgrade`` (post wheel-install migration)."""

    def _capture_dispatch(self):
        """Run ``_dispatch_upgrade`` with stdout/stderr captured.

        Returns ``(rc, stdout, stderr, mock_run)`` so each test can make its
        own assertions without duplicating the wiring.
        """
        stdout = io.StringIO()
        stderr = io.StringIO()
        mock_run = MagicMock()
        with patch("subprocess.run", mock_run), \
                patch.object(sys, "stdout", stdout), \
                patch.object(sys, "stderr", stderr):
            rc = _dispatch_upgrade(MagicMock())
        return rc, stdout.getvalue(), stderr.getvalue(), mock_run

    def test_exit_zero(self):
        """Advisory printer always exits 0."""
        rc, _stdout, _stderr, _run = self._capture_dispatch()
        self.assertEqual(rc, 0)

    def test_stdout_contains_plugin_update_advisory(self):
        """Stdout advises the MCP-driven `/plugin update` path."""
        _rc, stdout, _stderr, _run = self._capture_dispatch()
        self.assertIn("/plugin update", stdout)

    def test_stdout_contains_reinstall_advisory(self):
        """Stdout advises the bare-shell `--reinstall` path."""
        _rc, stdout, _stderr, _run = self._capture_dispatch()
        self.assertIn("--reinstall", stdout)

    def test_no_git_or_uv_subprocess_invocations(self):
        """Advisory contract: no `git` or `uv` shell-outs from this handler.

        The pre-migration handler ran three subprocesses
        (`git status`, `git pull`, `uv tool install`). Under the wheel-install
        migration the CLI cannot self-upgrade, so any subprocess call here
        would be a regression toward the old behavior.
        """
        _rc, _stdout, _stderr, mock_run = self._capture_dispatch()
        for invocation in mock_run.call_args_list:
            argv = invocation.args[0] if invocation.args else []
            self.assertNotIn("git", argv,
                             f"unexpected git invocation: {invocation}")
            self.assertNotIn("uv", argv,
                             f"unexpected uv invocation: {invocation}")


if __name__ == "__main__":
    unittest.main()
