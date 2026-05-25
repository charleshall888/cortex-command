"""Phase 1 sibling-rewrite smoke test.

Exercises every ``bin/cortex-*`` script rewritten in Tasks 4a (bash) and
4b (Python/PEP 723) to verify that the new log-invocation guard does not
emit spurious ``cortex-log-invocation failed:`` warnings under normal
conditions, and that the script's own exit code is correctly propagated.

For Python/PEP 723 scripts, additionally asserts that no ``SyntaxError``
traceback appears on stderr — a defensive check against the critical-review-
flagged hazard of accidentally injecting bash syntax into a Python file.

Design constraints
------------------
* PATH isolation: the test subprocesses use a PATH from which
  ``cortex-log-invocation`` is filtered out.  When the binary is absent
  from PATH, the bash idiom ``command -v cortex-log-invocation`` returns
  nonzero (silent skip) and the Python idiom ``shutil.which("cortex-log-
  invocation")`` returns ``None`` (silent skip).  Neither emits the
  ``cortex-log-invocation failed:`` warning.  This is the desired behavior
  under normal conditions and is exactly what the smoke test verifies.

* State isolation: ``LIFECYCLE_SESSION_ID`` is unset in all subprocesses so
  ``cortex-log-invocation`` (if somehow reached) would not write a session
  log.  Setting ``HOME`` to a temp directory provides belt-and-suspenders
  protection against any log-side-effect.

* PEP 723 scripts (``#!/usr/bin/env -S uv run --script``) are invoked as
  executables so their inline dependency metadata is handled by uv.  These
  scripts are marked ``slow`` because uv may need to download packages in
  CI.  Run with ``pytest --run-slow`` to include them.

Covered scripts (Tasks 4a and 4b)
-----------------------------------
Task 4a (bash):
  - cortex-jcc

Console-script entry point (wheel-generated binstub; bash wrapper retired):
  - cortex-morning-review-complete-session

Task 4b (Python ``#!/usr/bin/env python3``):
  - cortex-archive-rewrite-paths
  - cortex-archive-sample-select
  - cortex-check-events-registry
  - cortex-check-path-hardcoding
  - cortex-requirements-parity-audit
  - cortex-rewrite-cli-pin

Task 4b (PEP 723 ``#!/usr/bin/env -S uv run --script``):
  - cortex-audit-doc
  - cortex-count-tokens
  - cortex-measure-l1-surface
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

import pytest


# ---------------------------------------------------------------------------
# Repo root and script paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = REPO_ROOT / "bin"

# The canonical stderr warning emitted by BOTH bash and Python idioms when
# cortex-log-invocation is present on PATH but exits nonzero.
_FAILED_WARNING = "cortex-log-invocation failed:"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_isolated_path() -> str:
    """Return a PATH string with the cortex-log-invocation binstub removed.

    If ``cortex-log-invocation`` is not on PATH (the expected state in a
    non-installed dev/CI environment), the current PATH is returned unchanged.
    Filtering ensures that even on an installed machine where the wheel binstub
    is in ``~/.local/bin/`` the smoke test exercises the silent-skip branch
    rather than the present-but-broken branch.
    """
    li_path = shutil.which("cortex-log-invocation")
    if li_path is None:
        return os.environ.get("PATH", "")
    # Remove the directory that contains the binstub from PATH.
    li_dir = str(Path(li_path).parent)
    filtered = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p != li_dir]
    return os.pathsep.join(filtered)


def _base_env(tmp_home: str) -> dict[str, str]:
    """Build a subprocess environment with PATH isolation and HOME redirected.

    Inherits the full current process environment (required so Python,
    uv, git, etc. remain resolvable), then:
    * Filters ``cortex-log-invocation`` out of PATH.
    * Sets HOME to a throwaway temp directory so no session-log files
      can be written to the real home tree.
    * Unsets LIFECYCLE_SESSION_ID so cortex-log-invocation (if somehow
      reached) has no session to log into.
    """
    env = dict(os.environ)
    env["PATH"] = _build_isolated_path()
    env["HOME"] = tmp_home
    env.pop("LIFECYCLE_SESSION_ID", None)
    return env


def _run(
    cmd: Sequence[str | Path],
    *,
    env: dict[str, str],
    cwd: Path = REPO_ROOT,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    """Run a subprocess, capturing stdout and stderr."""
    return subprocess.run(
        [str(c) for c in cmd],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=timeout,
    )


def _assert_no_log_invocation_warning(result: subprocess.CompletedProcess, script_name: str) -> None:
    """Assert that the script's stderr contains no spurious log-invocation warning."""
    assert _FAILED_WARNING not in result.stderr, (
        f"{script_name}: spurious '{_FAILED_WARNING}' found on stderr.\n"
        f"stderr = {result.stderr!r}"
    )


def _assert_no_syntax_error(result: subprocess.CompletedProcess, script_name: str) -> None:
    """Assert no SyntaxError traceback on stderr (Python/PEP 723 guard)."""
    assert "SyntaxError" not in result.stderr, (
        f"{script_name}: SyntaxError found on stderr — possible bash-block injection.\n"
        f"stderr = {result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Task 4a: bash scripts
# ---------------------------------------------------------------------------


def test_cortex_jcc_no_log_invocation_warning(tmp_path: Path) -> None:
    """cortex-jcc: silently skips log-invocation; exits with its own code."""
    script = BIN_DIR / "cortex-jcc"
    env = _base_env(str(tmp_path))
    # Provide a CORTEX_COMMAND_ROOT that exists but has no justfile so
    # cortex-jcc exits 1 with its own "justfile not found" message rather
    # than trying to exec just.
    fake_root = tmp_path / "fake-root"
    fake_root.mkdir()
    env["CORTEX_COMMAND_ROOT"] = str(fake_root)
    result = _run([script], env=env)
    _assert_no_log_invocation_warning(result, "cortex-jcc")
    # Script's own exit code: 1 (justfile not found)
    assert result.returncode == 1, (
        f"cortex-jcc: expected exit 1 (justfile not found), got {result.returncode}.\n"
        f"stderr = {result.stderr!r}"
    )


def test_cortex_morning_review_complete_session_no_log_invocation_warning(tmp_path: Path) -> None:
    """cortex-morning-review-complete-session: silently skips log-invocation; --help exits 0.

    After the bash wrapper deletion, the wheel-generated binstub IS the
    real entry path under ``uv tool install -e .``. ``shutil.which`` resolves
    it on PATH; absence triggers pytest.skip rather than a failure so this
    smoke test stays green in non-installed environments.
    """
    script = shutil.which("cortex-morning-review-complete-session")
    if script is None:
        pytest.skip("console-script not installed; run uv tool install -e . --force")
    env = _base_env(str(tmp_path))
    result = _run([script, "--help"], env=env)
    _assert_no_log_invocation_warning(result, "cortex-morning-review-complete-session")
    # --help is handled by argparse and exits 0.
    assert result.returncode == 0, (
        f"cortex-morning-review-complete-session: --help returned exit {result.returncode}.\n"
        f"stderr = {result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Task 4b: Python (#!/usr/bin/env python3) scripts
# ---------------------------------------------------------------------------


def test_cortex_archive_rewrite_paths_no_log_invocation_warning(tmp_path: Path) -> None:
    """cortex-archive-rewrite-paths: --help exits 0 with no log-invocation warning."""
    script = BIN_DIR / "cortex-archive-rewrite-paths"
    env = _base_env(str(tmp_path))
    result = _run([sys.executable, str(script), "--help"], env=env)
    _assert_no_log_invocation_warning(result, "cortex-archive-rewrite-paths")
    _assert_no_syntax_error(result, "cortex-archive-rewrite-paths")
    assert result.returncode == 0, (
        f"cortex-archive-rewrite-paths: --help returned exit {result.returncode}.\n"
        f"stderr = {result.stderr!r}"
    )


def test_cortex_archive_sample_select_no_log_invocation_warning(tmp_path: Path) -> None:
    """cortex-archive-sample-select: --help exits 0 with no log-invocation warning."""
    script = BIN_DIR / "cortex-archive-sample-select"
    env = _base_env(str(tmp_path))
    result = _run([sys.executable, str(script), "--help"], env=env)
    _assert_no_log_invocation_warning(result, "cortex-archive-sample-select")
    _assert_no_syntax_error(result, "cortex-archive-sample-select")
    assert result.returncode == 0, (
        f"cortex-archive-sample-select: --help returned exit {result.returncode}.\n"
        f"stderr = {result.stderr!r}"
    )


def test_cortex_check_events_registry_no_log_invocation_warning(tmp_path: Path) -> None:
    """cortex-check-events-registry: --help exits 0 with no log-invocation warning."""
    script = BIN_DIR / "cortex-check-events-registry"
    env = _base_env(str(tmp_path))
    result = _run([sys.executable, str(script), "--help"], env=env)
    _assert_no_log_invocation_warning(result, "cortex-check-events-registry")
    _assert_no_syntax_error(result, "cortex-check-events-registry")
    assert result.returncode == 0, (
        f"cortex-check-events-registry: --help returned exit {result.returncode}.\n"
        f"stderr = {result.stderr!r}"
    )


def test_cortex_check_path_hardcoding_no_log_invocation_warning(tmp_path: Path) -> None:
    """cortex-check-path-hardcoding: --help exits 0 with no log-invocation warning."""
    script = BIN_DIR / "cortex-check-path-hardcoding"
    env = _base_env(str(tmp_path))
    result = _run([sys.executable, str(script), "--help"], env=env)
    _assert_no_log_invocation_warning(result, "cortex-check-path-hardcoding")
    _assert_no_syntax_error(result, "cortex-check-path-hardcoding")
    assert result.returncode == 0, (
        f"cortex-check-path-hardcoding: --help returned exit {result.returncode}.\n"
        f"stderr = {result.stderr!r}"
    )


def test_cortex_requirements_parity_audit_no_log_invocation_warning(tmp_path: Path) -> None:
    """cortex-requirements-parity-audit: --help exits 0 with no log-invocation warning."""
    script = BIN_DIR / "cortex-requirements-parity-audit"
    env = _base_env(str(tmp_path))
    result = _run([sys.executable, str(script), "--help"], env=env)
    _assert_no_log_invocation_warning(result, "cortex-requirements-parity-audit")
    _assert_no_syntax_error(result, "cortex-requirements-parity-audit")
    assert result.returncode == 0, (
        f"cortex-requirements-parity-audit: --help returned exit {result.returncode}.\n"
        f"stderr = {result.stderr!r}"
    )


def test_cortex_rewrite_cli_pin_no_log_invocation_warning(tmp_path: Path) -> None:
    """cortex-rewrite-cli-pin: --help exits 0 with no log-invocation warning."""
    script = BIN_DIR / "cortex-rewrite-cli-pin"
    env = _base_env(str(tmp_path))
    result = _run([sys.executable, str(script), "--help"], env=env)
    _assert_no_log_invocation_warning(result, "cortex-rewrite-cli-pin")
    _assert_no_syntax_error(result, "cortex-rewrite-cli-pin")
    assert result.returncode == 0, (
        f"cortex-rewrite-cli-pin: --help returned exit {result.returncode}.\n"
        f"stderr = {result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Task 4b: PEP 723 (#!/usr/bin/env -S uv run --script) scripts
#
# These scripts require uv to resolve inline dependencies.  They are marked
# slow because uv may need to fetch packages.  Run with --run-slow to include
# them.
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_cortex_audit_doc_no_log_invocation_warning(tmp_path: Path) -> None:
    """cortex-audit-doc (PEP 723): no log-invocation warning; no SyntaxError on stderr.

    cortex-audit-doc calls resolve_api_key() before argparse, so it exits 1
    with an "No API key available" message when ANTHROPIC_API_KEY is unset.
    That nonzero exit is the script's own behavior — not a log-invocation
    regression.  The smoke test asserts the specific warning substrings are
    absent and accepts any exit code that does NOT come from the log-invocation
    guard.
    """
    script = BIN_DIR / "cortex-audit-doc"
    env = _base_env(str(tmp_path))
    # Ensure no API key is present so the script exits early with its own message.
    env.pop("ANTHROPIC_API_KEY", None)
    result = _run([str(script)], env=env, timeout=60)
    _assert_no_log_invocation_warning(result, "cortex-audit-doc")
    _assert_no_syntax_error(result, "cortex-audit-doc")
    # Exit code 1 is the script's own (no API key).  Any other nonzero code
    # would also be the script's own since log-invocation is absent from PATH.
    assert result.returncode in {0, 1}, (
        f"cortex-audit-doc: unexpected exit code {result.returncode}.\n"
        f"stderr = {result.stderr!r}"
    )


@pytest.mark.slow
def test_cortex_count_tokens_no_log_invocation_warning(tmp_path: Path) -> None:
    """cortex-count-tokens (PEP 723): no log-invocation warning; no SyntaxError.

    Like cortex-audit-doc, this script exits 1 when ANTHROPIC_API_KEY is
    absent.  The smoke test accepts exit 0 or 1 as the script's own code.
    """
    script = BIN_DIR / "cortex-count-tokens"
    env = _base_env(str(tmp_path))
    env.pop("ANTHROPIC_API_KEY", None)
    result = _run([str(script)], env=env, timeout=60)
    _assert_no_log_invocation_warning(result, "cortex-count-tokens")
    _assert_no_syntax_error(result, "cortex-count-tokens")
    assert result.returncode in {0, 1}, (
        f"cortex-count-tokens: unexpected exit code {result.returncode}.\n"
        f"stderr = {result.stderr!r}"
    )


@pytest.mark.slow
def test_cortex_measure_l1_surface_no_log_invocation_warning(tmp_path: Path) -> None:
    """cortex-measure-l1-surface (PEP 723): no log-invocation warning; exits 0.

    cortex-measure-l1-surface scans ``skills/*/SKILL.md`` under cwd and emits
    byte counts.  Running from REPO_ROOT gives it a real skills tree to scan
    and guarantees exit 0.
    """
    script = BIN_DIR / "cortex-measure-l1-surface"
    env = _base_env(str(tmp_path))
    result = _run([str(script)], env=env, cwd=REPO_ROOT, timeout=60)
    _assert_no_log_invocation_warning(result, "cortex-measure-l1-surface")
    _assert_no_syntax_error(result, "cortex-measure-l1-surface")
    assert result.returncode == 0, (
        f"cortex-measure-l1-surface: expected exit 0, got {result.returncode}.\n"
        f"stderr = {result.stderr!r}"
    )
