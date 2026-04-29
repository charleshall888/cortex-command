"""Integration tests for `cortex --print-root` (R3, R16, R2d).

Verifies the forever-public-API JSON shape emitted by the top-level
``--print-root`` flag (envelope ``version`` ``"1.1"``):

  - ``version`` equals ``"1.1"`` (currently shipped envelope version)
  - ``root`` is an absolute path that exists (the user's cortex project)
  - ``package_root`` is an absolute path that exists (the install location)
  - ``head_sha`` is exactly 40 hex chars when ``root`` is a git repo
  - ``remote_url`` is non-empty when ``root`` is a git repo

The non-editable-wheel-install migration (Tasks 1–14) split ``root`` (user
project) from ``package_root`` (install location). ``head_sha`` and
``remote_url`` only populate when ``root`` is a git repo, so the test pins
``CORTEX_REPO_ROOT`` to this repository (which is a git clone) to exercise
the populated path.

The test invokes ``cortex --print-root`` via ``subprocess.run`` against the
console script installed by ``uv tool install -e .``. A fallback to
``python -m cortex_command.cli`` is used when the console script is not on
PATH (e.g. CI sandboxes where ``uv tool update-shell`` has not been run).
"""

from __future__ import annotations

import json
import os
import shutil
import string
import subprocess
import sys
import unittest
from pathlib import Path


HEX_CHARS = set(string.hexdigits)
REPO_ROOT = Path(__file__).resolve().parents[1]


def _invoke_print_root(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run ``cortex --print-root``, falling back to ``python -m`` on PATH miss."""

    cortex = shutil.which("cortex")
    if cortex is not None:
        argv = [cortex, "--print-root"]
    else:
        argv = [sys.executable, "-m", "cortex_command.cli", "--print-root"]
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )


class TestCortexPrintRoot(unittest.TestCase):
    """Tests for the `cortex --print-root` versioned JSON contract (R3, R16, R2d)."""

    def _env_with_repo_root(self) -> dict[str, str]:
        """Environment with CORTEX_REPO_ROOT pinned at this repo (a git clone).

        Pinning here lets us assert ``head_sha`` / ``remote_url`` are
        populated from the git probes — those fields stay empty when ``root``
        is not a git repo. The repo itself is guaranteed to have ``.git/``
        because the test file lives inside it.
        """
        env = os.environ.copy()
        env["CORTEX_REPO_ROOT"] = str(REPO_ROOT)
        return env

    def test_print_root_envelope_v1_1_shape(self):
        """Exit 0; stdout parses as JSON with version 1.1 envelope fields."""
        proc = _invoke_print_root(self._env_with_repo_root())

        self.assertEqual(
            proc.returncode,
            0,
            msg=f"non-zero exit: stdout={proc.stdout!r} stderr={proc.stderr!r}",
        )

        payload = json.loads(proc.stdout)

        # version is exactly "1.1" under the current envelope contract.
        self.assertEqual(
            payload.get("version"),
            "1.1",
            msg=f"unexpected envelope version: {payload.get('version')!r}",
        )

        # root must be an absolute path that exists on disk.
        root = payload.get("root")
        self.assertIsInstance(root, str)
        self.assertTrue(
            Path(root).is_absolute(),
            msg=f"root is not absolute: {root!r}",
        )
        self.assertTrue(
            Path(root).exists(),
            msg=f"root does not exist: {root!r}",
        )

        # package_root (added by Task 7) must be present, absolute, and
        # exist on disk. Distinct from root under wheel install (root is
        # the user's project; package_root is the install location).
        package_root = payload.get("package_root")
        self.assertIsInstance(package_root, str)
        self.assertTrue(
            Path(package_root).is_absolute(),
            msg=f"package_root is not absolute: {package_root!r}",
        )
        self.assertTrue(
            Path(package_root).exists(),
            msg=f"package_root does not exist: {package_root!r}",
        )

        # head_sha is exactly 40 hex chars when root is a git repo (it is
        # — we pinned CORTEX_REPO_ROOT to this repository).
        head_sha = payload.get("head_sha")
        self.assertIsInstance(head_sha, str)
        self.assertEqual(
            len(head_sha),
            40,
            msg=f"head_sha not 40 chars: {head_sha!r}",
        )
        self.assertTrue(
            all(c in HEX_CHARS for c in head_sha),
            msg=f"head_sha not all hex: {head_sha!r}",
        )

        # remote_url is non-empty when root is a git repo.
        remote_url = payload.get("remote_url")
        self.assertIsInstance(remote_url, str)
        self.assertGreater(
            len(remote_url),
            0,
            msg="remote_url is empty",
        )

    def test_print_root_unset_env_falls_back_to_cwd(self):
        """With CORTEX_REPO_ROOT unset, cwd is used (when cwd looks like a project).

        We invoke from this repository's root, which contains ``lifecycle/``
        and ``backlog/`` — so the CWD-based resolution path resolves cleanly
        and emits the same envelope shape.
        """
        env = os.environ.copy()
        env.pop("CORTEX_REPO_ROOT", None)

        cortex = shutil.which("cortex")
        if cortex is not None:
            argv = [cortex, "--print-root"]
        else:
            argv = [sys.executable, "-m", "cortex_command.cli", "--print-root"]
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
            cwd=str(REPO_ROOT),
        )

        self.assertEqual(
            proc.returncode,
            0,
            msg=f"non-zero exit: stdout={proc.stdout!r} stderr={proc.stderr!r}",
        )
        payload = json.loads(proc.stdout)
        self.assertEqual(payload.get("version"), "1.1")
        self.assertIn("root", payload)
        self.assertIn("package_root", payload)


if __name__ == "__main__":
    unittest.main()
