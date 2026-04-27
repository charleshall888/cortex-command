"""Subprocess+JSON contract tests for the plugin-bundled MCP server.

Task 5 seeds this file with the confused-deputy startup-check test
(R17). Subsequent tasks (Tasks 6+) extend the file with tool-delegation
contract tests (R2), the schema-version round-trip tests (R15), and the
``overnight start`` concurrent-runner JSON-shape test (R4).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = (
    REPO_ROOT
    / "plugins"
    / "cortex-overnight-integration"
    / "server.py"
)


def test_plugin_path_mismatch_exits_nonzero(tmp_path: Path) -> None:
    """R17 — confused-deputy mitigation.

    Invoke the plugin server with ``CLAUDE_PLUGIN_ROOT`` pointed at an
    attacker-controlled directory that does NOT contain
    ``server.py``; the server must refuse to start, exit non-zero, and
    emit a stderr message containing ``"plugin path mismatch"``.
    """

    if shutil.which("uv") is None:
        pytest.skip("uv not installed; cannot resolve PEP 723 deps")

    assert SERVER_PATH.exists(), f"plugin server.py missing at {SERVER_PATH}"

    attacker_root = tmp_path / "attacker-controlled"
    attacker_root.mkdir()

    completed = subprocess.run(
        ["uv", "run", "--script", str(SERVER_PATH)],
        capture_output=True,
        text=True,
        timeout=60,
        env={
            # Minimal env: keep PATH so ``uv`` resolves; override
            # CLAUDE_PLUGIN_ROOT to the attacker-controlled directory.
            "PATH": __import__("os").environ.get("PATH", ""),
            "HOME": __import__("os").environ.get("HOME", ""),
            "CLAUDE_PLUGIN_ROOT": str(attacker_root),
        },
    )

    assert completed.returncode != 0, (
        "expected non-zero exit when CLAUDE_PLUGIN_ROOT points outside "
        f"the plugin directory; got returncode={completed.returncode}, "
        f"stdout={completed.stdout!r}, stderr={completed.stderr!r}"
    )
    assert "plugin path mismatch" in completed.stderr, (
        "expected stderr to contain 'plugin path mismatch'; got "
        f"stderr={completed.stderr!r}"
    )
