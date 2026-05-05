"""Unit tests for the `cortex dashboard` verb (Task 6 of #166).

Verifies:
  (1) ``cortex dashboard --help`` exits 0 and stdout contains ``--port``.
  (2) PID-file location resolves under ``$XDG_CACHE_HOME/cortex/`` (or
      ``~/.cache/cortex/`` fallback), never under the package directory.
  (3) The verb does NOT write to ``cortex_command/dashboard/.pid`` under
      any condition — installed-wheel layouts make the package directory
      read-only, and the in-package PID file would orphan stale state
      across cache-purge boundaries.

Pattern mirrors ``tests/test_cli_print_root.py``,
``tests/test_cli_upgrade.py``, ``tests/test_cli_handler_logs.py``.
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _invoke_dashboard_help() -> subprocess.CompletedProcess[str]:
    """Run ``cortex dashboard --help``, falling back to ``python -m`` on PATH miss."""

    cortex = shutil.which("cortex")
    if cortex is not None:
        argv = [cortex, "dashboard", "--help"]
    else:
        argv = [sys.executable, "-m", "cortex_command.cli", "dashboard", "--help"]
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=10,
    )


class TestCortexDashboardHelp(unittest.TestCase):
    """`cortex dashboard --help` exits 0 and surfaces the --port flag."""

    def test_help_exits_zero(self):
        proc = _invoke_dashboard_help()
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"non-zero exit: stdout={proc.stdout!r} stderr={proc.stderr!r}",
        )

    def test_help_contains_port_flag(self):
        proc = _invoke_dashboard_help()
        self.assertIn(
            "--port",
            proc.stdout,
            msg=f"--port flag missing from help output: {proc.stdout!r}",
        )


class TestDashboardPidPath(unittest.TestCase):
    """PID-file resolution honors XDG_CACHE_HOME and never writes in-package."""

    def _reload_app(self):
        """Reimport ``cortex_command.dashboard.app`` so module-level
        ``_pid_file`` is re-resolved against the current environment."""

        import cortex_command.dashboard.app as app_module

        return importlib.reload(app_module)

    def test_pid_path_honors_xdg_cache_home(self):
        """PID path resolves under ``$XDG_CACHE_HOME/cortex/`` when set."""

        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("XDG_CACHE_HOME")
            os.environ["XDG_CACHE_HOME"] = tmp
            try:
                app_module = self._reload_app()
                pid_path = app_module._resolve_pid_path()
                expected_parent = Path(tmp) / "cortex"
                self.assertEqual(pid_path.parent, expected_parent)
                self.assertEqual(pid_path.name, "dashboard.pid")
                self.assertTrue(
                    expected_parent.is_dir(),
                    msg=f"resolver did not create parent dir: {expected_parent}",
                )
            finally:
                if old is None:
                    os.environ.pop("XDG_CACHE_HOME", None)
                else:
                    os.environ["XDG_CACHE_HOME"] = old
                self._reload_app()

    def test_pid_path_falls_back_to_home_cache(self):
        """With ``XDG_CACHE_HOME`` unset the resolver falls back to ``~/.cache``."""

        old = os.environ.pop("XDG_CACHE_HOME", None)
        try:
            app_module = self._reload_app()
            pid_path = app_module._resolve_pid_path()
            expected_parent = Path(os.path.expanduser("~/.cache")) / "cortex"
            self.assertEqual(pid_path.parent, expected_parent)
            self.assertEqual(pid_path.name, "dashboard.pid")
        finally:
            if old is not None:
                os.environ["XDG_CACHE_HOME"] = old
            self._reload_app()

    def test_pid_path_never_in_package_directory(self):
        """Verb MUST NOT write PID to ``cortex_command/dashboard/.pid``.

        Installed-wheel layouts make the package directory read-only; an
        in-package PID write would crash on first launch in production
        installs. We verify both (a) the resolver never returns an
        in-package path, and (b) no such file appears after the resolver
        runs (i.e., the resolver's directory-creation side effect doesn't
        accidentally touch the package dir).
        """
        import cortex_command.dashboard.app as app_module

        package_dir = Path(app_module.__file__).resolve().parent
        in_package_pid = package_dir / ".pid"

        # Clean up any leftover state from prior failures so the assertion
        # below is meaningful.
        in_package_pid.unlink(missing_ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("XDG_CACHE_HOME")
            os.environ["XDG_CACHE_HOME"] = tmp
            try:
                app_module = self._reload_app()
                pid_path = app_module._resolve_pid_path()
                self.assertNotEqual(
                    pid_path.resolve(),
                    in_package_pid.resolve(),
                    msg=f"PID path resolves to in-package location: {pid_path}",
                )
                self.assertFalse(
                    str(pid_path).startswith(str(package_dir)),
                    msg=(
                        f"PID path is under package directory "
                        f"{package_dir}: {pid_path}"
                    ),
                )
                self.assertFalse(
                    in_package_pid.exists(),
                    msg=(
                        "PID file was written into the package directory "
                        f"({in_package_pid})"
                    ),
                )
            finally:
                if old is None:
                    os.environ.pop("XDG_CACHE_HOME", None)
                else:
                    os.environ["XDG_CACHE_HOME"] = old
                self._reload_app()


if __name__ == "__main__":
    unittest.main()
