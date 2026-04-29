"""Integration tests for the `cortex mcp-server` deprecation stub (R7, Task 14).

Verifies three behaviors required by spec R7 / plan Task 14:

  (a) ``cortex mcp-server`` exits non-zero and stderr names the migration
      target ``cortex-overnight-integration``.
  (b) After a successful ``cortex upgrade``, stderr emits a one-line notice
      pointing users at the new ``uv run ${CLAUDE_PLUGIN_ROOT}/server.py``
      invocation form.
  (c) When T12's verdict file (``plugin-refresh-semantics.md``) reports
      ``session_restart_required``, the deprecation message is augmented
      with a ``Restart Claude Code`` advisory.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cortex_command.cli import _dispatch_upgrade


T12_VERDICT_RELATIVE_PATH = (
    "lifecycle/decouple-mcp-server-from-cli-python-imports-own-auto-update-"
    "orchestration/plugin-refresh-semantics.md"
)


def _invoke_mcp_server(env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run ``cortex mcp-server`` in a subprocess with optional env overrides."""

    cortex = shutil.which("cortex")
    if cortex is not None:
        argv = [cortex, "mcp-server"]
    else:
        argv = [sys.executable, "-m", "cortex_command.cli", "mcp-server"]
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )


class TestMcpServerDeprecationStub(unittest.TestCase):
    """Tests for the `cortex mcp-server` deprecation stub."""

    def test_deprecation_stub_stderr_contains_migration_target(self):
        """`cortex mcp-server` exits non-zero and stderr names the plugin."""
        proc = _invoke_mcp_server()

        self.assertNotEqual(
            proc.returncode,
            0,
            msg=(
                f"expected non-zero exit, got {proc.returncode}; "
                f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
            ),
        )
        self.assertIn(
            "cortex-overnight-integration",
            proc.stderr,
            msg=f"stderr missing migration target: {proc.stderr!r}",
        )

    def test_deprecation_stub_appends_restart_advisory_when_t12_verdict_is_restart_required(self):
        """A `session_restart_required` verdict appends the restart advisory."""

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            verdict_file = tmp_path / T12_VERDICT_RELATIVE_PATH
            verdict_file.parent.mkdir(parents=True, exist_ok=True)
            verdict_file.write_text(
                "# Stub T12 verdict fixture\n"
                "\n"
                "## Verdict\n"
                "\n"
                "session_restart_required\n",
                encoding="utf-8",
            )

            proc = _invoke_mcp_server(
                env_overrides={"CORTEX_COMMAND_ROOT": str(tmp_path)},
            )

        self.assertNotEqual(
            proc.returncode,
            0,
            msg=f"expected non-zero exit; stderr={proc.stderr!r}",
        )
        self.assertIn(
            "Restart Claude Code",
            proc.stderr,
            msg=(
                "stderr missing 'Restart Claude Code' advisory: "
                f"{proc.stderr!r}"
            ),
        )


class TestPostUpgradeMigrationNotice(unittest.TestCase):
    """Tests for the post-`cortex upgrade` migration notice."""

    def test_post_upgrade_notice_emitted(self):
        """After a successful upgrade, stderr names the new uv run invocation."""

        # Mock subprocess.run for the three calls inside _dispatch_upgrade so
        # the test does not actually mutate the system. Pattern matches the
        # existing tests/test_cli_upgrade.py style.
        side_effects = [
            MagicMock(stdout="", returncode=0),  # git status --porcelain
            MagicMock(returncode=0),              # git pull --ff-only
            MagicMock(returncode=0),              # uv tool install
        ]
        mock_run = MagicMock(side_effect=side_effects)

        with patch("subprocess.run", mock_run):
            with patch("sys.stderr") as mock_stderr:
                rc = _dispatch_upgrade(MagicMock())

        self.assertEqual(rc, 0)
        written = "".join(
            c.args[0] for c in mock_stderr.write.call_args_list if c.args
        )
        self.assertIn(
            "update it to point at uv run",
            written,
            msg=f"stderr missing post-upgrade migration notice: {written!r}",
        )


if __name__ == "__main__":
    unittest.main()
