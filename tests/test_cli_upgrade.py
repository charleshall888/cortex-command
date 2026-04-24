"""Unit tests for the `cortex upgrade` handler in cortex_command.cli.

Covers four scenarios from spec R13–R15 of the curl|sh bootstrap installer
ticket:
  (a) happy path — three subprocess.run calls succeed in the documented order;
  (b) dirty-tree abort — non-empty stdout from `git status --porcelain` aborts
      after a single subprocess call;
  (c) subprocess failure on `git pull` — a CalledProcessError on call 2
      prevents the third (`uv tool install`) call from running;
  (d) `CORTEX_COMMAND_ROOT` override — env var overrides the `~/.cortex`
      default and is propagated as the `cwd=` argument.

NOTE: subprocess is lazy-imported inside `_dispatch_upgrade`, so the spec's
suggested patch target `cortex_command.cli.subprocess.run` does not exist at
module scope. We patch `subprocess.run` directly instead — same patched
function object is used by the handler's local `import subprocess`.
"""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from cortex_command.cli import _dispatch_upgrade


class TestCortexUpgrade(unittest.TestCase):
    """Tests for `_dispatch_upgrade` covering R13–R15."""

    # ------------------------------------------------------------------
    # (a) Happy path — R13 contract: three calls in order.
    # ------------------------------------------------------------------

    def test_happy_path_runs_three_calls_in_order(self):
        """Three subprocess.run calls execute in the documented order; exit 0."""
        cortex_root = str(Path.home() / ".cortex")
        side_effects = [
            MagicMock(stdout="", returncode=0),  # git status --porcelain (clean)
            MagicMock(returncode=0),              # git pull --ff-only
            MagicMock(returncode=0),              # uv tool install
        ]
        mock_run = MagicMock(side_effect=side_effects)

        env_patch = patch.dict(os.environ, {}, clear=False)
        # Ensure CORTEX_COMMAND_ROOT is unset so the default `~/.cortex` is used.
        if "CORTEX_COMMAND_ROOT" in os.environ:
            env_patch = patch.dict(
                os.environ,
                {k: v for k, v in os.environ.items() if k != "CORTEX_COMMAND_ROOT"},
                clear=True,
            )

        with env_patch, patch("subprocess.run", mock_run):
            rc = _dispatch_upgrade(MagicMock())

        self.assertEqual(rc, 0)
        self.assertEqual(mock_run.call_count, 3)
        self.assertEqual(
            mock_run.call_args_list[0],
            call(
                ["git", "status", "--porcelain"],
                cwd=cortex_root,
                check=True,
                capture_output=True,
                text=True,
            ),
        )
        self.assertEqual(
            mock_run.call_args_list[1],
            call(
                ["git", "-C", cortex_root, "pull", "--ff-only"],
                check=True,
            ),
        )
        self.assertEqual(
            mock_run.call_args_list[2],
            call(
                ["uv", "tool", "install", "-e", cortex_root, "--force"],
                check=True,
            ),
        )

    # ------------------------------------------------------------------
    # (b) Dirty-tree abort — R14: stdout non-empty -> abort after 1 call.
    # ------------------------------------------------------------------

    def test_dirty_tree_aborts_after_single_call(self):
        """Non-empty `git status --porcelain` output aborts before pull/install."""
        side_effects = [
            MagicMock(stdout="M file.py\n", returncode=0),
        ]
        mock_run = MagicMock(side_effect=side_effects)

        with patch("subprocess.run", mock_run):
            with patch("sys.stderr") as mock_stderr:
                rc = _dispatch_upgrade(MagicMock())

        self.assertEqual(rc, 1)
        self.assertEqual(mock_run.call_count, 1)
        # Reconstruct the stderr write payload to assert "uncommitted changes" appeared.
        written = "".join(
            c.args[0] for c in mock_stderr.write.call_args_list if c.args
        )
        self.assertIn("uncommitted changes", written)

    # ------------------------------------------------------------------
    # (c) Subprocess failure on call 2 — R15: pull fails, install does not run.
    # ------------------------------------------------------------------

    def test_pull_failure_skips_uv_tool_install(self):
        """A CalledProcessError on `git pull` aborts before `uv tool install`."""
        cortex_root = str(Path.home() / ".cortex")
        pull_cmd = ["git", "-C", cortex_root, "pull", "--ff-only"]
        side_effects = [
            MagicMock(stdout="", returncode=0),  # git status --porcelain (clean)
            subprocess.CalledProcessError(returncode=128, cmd=pull_cmd),
        ]
        mock_run = MagicMock(side_effect=side_effects)

        with patch("subprocess.run", mock_run):
            rc = _dispatch_upgrade(MagicMock())

        self.assertEqual(rc, 1)
        self.assertEqual(mock_run.call_count, 2)
        # The third call (uv tool install) must not have been invoked.
        for call_args in mock_run.call_args_list:
            self.assertNotIn("uv", call_args.args[0])

    # ------------------------------------------------------------------
    # (d) CORTEX_COMMAND_ROOT override — env var propagates to cwd= and -C.
    # ------------------------------------------------------------------

    def test_cortex_command_root_env_override(self):
        """CORTEX_COMMAND_ROOT replaces the `~/.cortex` default in cwd= and -C."""
        override_root = "/opt/custom/cortex"
        side_effects = [
            MagicMock(stdout="", returncode=0),
            MagicMock(returncode=0),
            MagicMock(returncode=0),
        ]
        mock_run = MagicMock(side_effect=side_effects)

        with patch.dict(os.environ, {"CORTEX_COMMAND_ROOT": override_root}):
            with patch("subprocess.run", mock_run):
                rc = _dispatch_upgrade(MagicMock())

        self.assertEqual(rc, 0)
        # Call 1: cwd=override_root (not $HOME/.cortex).
        self.assertEqual(mock_run.call_args_list[0].kwargs.get("cwd"), override_root)
        # Call 2: `git -C <override_root> pull --ff-only`.
        self.assertEqual(
            mock_run.call_args_list[1].args[0],
            ["git", "-C", override_root, "pull", "--ff-only"],
        )
        # Call 3: `uv tool install -e <override_root> --force`.
        self.assertEqual(
            mock_run.call_args_list[2].args[0],
            ["uv", "tool", "install", "-e", override_root, "--force"],
        )


if __name__ == "__main__":
    unittest.main()
