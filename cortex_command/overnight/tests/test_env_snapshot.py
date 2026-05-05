"""Unit tests for the env-snapshot rule in
:meth:`MacOSLaunchAgentBackend._snapshot_env` (R15).

Covers:
  - All five snapshotable env vars present.
  - None of the optional vars present.
  - Partial presence (subset).
  - Negative invariant: HOME / USER / LOGNAME / TMPDIR are NOT in the
    snapshot, even when set in the process environment.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from cortex_command.overnight.scheduler.macos import MacOSLaunchAgentBackend


class TestEnvSnapshot(unittest.TestCase):
    """R15 env-snapshot contract."""

    def _snapshot_with_env(self, env: dict[str, str]) -> dict[str, str]:
        """Run :meth:`_snapshot_env` against a fully-replaced os.environ.

        The caller_env passed in is intentionally empty so we observe
        the snapshot's behavior against ``os.environ`` only.
        """
        with patch.dict("os.environ", env, clear=True):
            return MacOSLaunchAgentBackend._snapshot_env({})

    def test_all_five_keys_present(self) -> None:
        env = {
            "PATH": "/usr/bin:/bin",
            "ANTHROPIC_API_KEY": "ak-test",
            "CLAUDE_CODE_OAUTH_TOKEN": "tok-test",
            "CORTEX_REPO_ROOT": "/repos/cortex",
            "CORTEX_WORKTREE_ROOT": "/repos/worktrees",
        }
        snapshot = self._snapshot_with_env(env)
        self.assertEqual(snapshot, env)

    def test_path_only(self) -> None:
        env = {"PATH": "/usr/bin"}
        snapshot = self._snapshot_with_env(env)
        self.assertEqual(snapshot, {"PATH": "/usr/bin"})

    def test_partial_optional_keys(self) -> None:
        env = {
            "PATH": "/usr/bin",
            "ANTHROPIC_API_KEY": "ak-test",
            # CLAUDE_CODE_OAUTH_TOKEN absent
            "CORTEX_REPO_ROOT": "/repos/cortex",
            # CORTEX_WORKTREE_ROOT absent
        }
        snapshot = self._snapshot_with_env(env)
        self.assertEqual(
            snapshot,
            {
                "PATH": "/usr/bin",
                "ANTHROPIC_API_KEY": "ak-test",
                "CORTEX_REPO_ROOT": "/repos/cortex",
            },
        )

    def test_no_optional_keys_present(self) -> None:
        env = {"PATH": "/usr/bin"}
        snapshot = self._snapshot_with_env(env)
        self.assertEqual(set(snapshot.keys()), {"PATH"})

    def test_path_falls_back_to_caller_env_when_process_lacks_it(self) -> None:
        """If PATH is missing from os.environ but present in caller_env,
        the snapshot should still pick it up so launchd has something
        usable. (Defensive: production callers always have PATH set.)
        """
        with patch.dict("os.environ", {}, clear=True):
            snapshot = MacOSLaunchAgentBackend._snapshot_env(
                {"PATH": "/caller/bin"}
            )
        self.assertEqual(snapshot, {"PATH": "/caller/bin"})

    def test_home_user_logname_tmpdir_excluded(self) -> None:
        """Negative invariant — HOME / USER / LOGNAME / TMPDIR must NOT
        appear in the snapshot even when set, because launchd inherits
        them from the logged-in session per RQ3.
        """
        env = {
            "PATH": "/usr/bin",
            "HOME": "/Users/test",
            "USER": "test",
            "LOGNAME": "test",
            "TMPDIR": "/var/folders/xx/T/",
            "ANTHROPIC_API_KEY": "ak-test",
        }
        snapshot = self._snapshot_with_env(env)
        for forbidden in ("HOME", "USER", "LOGNAME", "TMPDIR"):
            self.assertNotIn(
                forbidden,
                snapshot,
                f"{forbidden!r} must NOT be in env snapshot",
            )
        # Sanity: the allowed keys are still there.
        self.assertIn("PATH", snapshot)
        self.assertIn("ANTHROPIC_API_KEY", snapshot)


if __name__ == "__main__":
    unittest.main()
