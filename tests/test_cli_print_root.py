"""Integration tests for `cortex --print-root` (R3, R16).

Verifies the forever-public-API JSON shape emitted by the top-level
``--print-root`` flag:

  - ``version`` starts with ``"1."``
  - ``root`` is an absolute path that exists
  - ``head_sha`` is exactly 40 hex chars
  - ``remote_url`` is non-empty

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


def _invoke_print_root() -> subprocess.CompletedProcess[str]:
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
        env=os.environ.copy(),
    )


class TestCortexPrintRoot(unittest.TestCase):
    """Tests for the `cortex --print-root` versioned JSON contract (R3, R16)."""

    def test_print_root_emits_versioned_json(self):
        """Exit 0; stdout parses as JSON with all four required fields."""
        proc = _invoke_print_root()

        self.assertEqual(
            proc.returncode,
            0,
            msg=f"non-zero exit: stdout={proc.stdout!r} stderr={proc.stderr!r}",
        )

        payload = json.loads(proc.stdout)

        # version must start with "1." (major-version-1 contract).
        self.assertIsInstance(payload.get("version"), str)
        self.assertTrue(
            payload["version"].startswith("1."),
            msg=f"version does not start with '1.': {payload['version']!r}",
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

        # head_sha is exactly 40 hex chars.
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

        # remote_url is non-empty.
        remote_url = payload.get("remote_url")
        self.assertIsInstance(remote_url, str)
        self.assertGreater(
            len(remote_url),
            0,
            msg="remote_url is empty",
        )


if __name__ == "__main__":
    unittest.main()
