"""Unit tests for ``cortex_command.overnight.seatbelt_probe.run_probe``.

Covers the five failure-mode branches specified in R4 acceptance:

  (i)   successful parse → ``result="ok"``
  (ii)  missing result file → ``result="failed"`` with cause containing "result file"
  (iii) claude exit-code != 0 → ``result="failed"``
  (iv)  skipped > 0 → ``result="failed"``
  (v)   ``FileNotFoundError`` on ``claude`` binary → ``result="failed"`` with
        cause "claude binary not found"

Each test mocks ``subprocess.Popen`` at the module boundary and controls
``$TMPDIR`` via ``monkeypatch.setenv`` so result/output files can be
pre-populated (or left absent) deterministically. The ``session_dir`` is
provided by pytest's ``tmp_path`` fixture.
"""

from __future__ import annotations

import subprocess
import unittest.mock
from pathlib import Path
from typing import Iterator

import pytest

import cortex_command.overnight.seatbelt_probe as probe_mod
from cortex_command.overnight.seatbelt_probe import run_probe


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def session_dir(tmp_path: Path) -> Path:
    """Return a fresh session directory under tmp_path."""
    d = tmp_path / "session"
    d.mkdir()
    return d


@pytest.fixture()
def tmpdir_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point $TMPDIR at a controlled subdirectory and return that path."""
    controlled = tmp_path / "tmpdir"
    controlled.mkdir()
    monkeypatch.setenv("TMPDIR", str(controlled))
    return controlled


# ---------------------------------------------------------------------------
# Helper: build a mock Popen that immediately returns with a given exit code.
# ---------------------------------------------------------------------------


def _make_popen_mock(returncode: int) -> unittest.mock.MagicMock:
    """Return a mock suitable for use as ``subprocess.Popen``."""
    proc = unittest.mock.MagicMock()
    proc.returncode = returncode
    proc.wait.return_value = returncode

    # Popen is used as a context manager in ``with open(...) as ...:`` blocks,
    # but the Popen itself is NOT used as a context manager — the ``with``
    # wraps the file handles, not the Popen. The Popen instance just needs
    # ``.wait()`` and ``.returncode``.
    popen_cls = unittest.mock.MagicMock(return_value=proc)
    return popen_cls


def _patch_popen(monkeypatch: pytest.MonkeyPatch, returncode: int) -> unittest.mock.MagicMock:
    """Patch ``subprocess.Popen`` in the probe module and return the class mock."""
    popen_cls = _make_popen_mock(returncode)
    monkeypatch.setattr(probe_mod.subprocess, "Popen", popen_cls)
    return popen_cls


# ---------------------------------------------------------------------------
# Branch (v): FileNotFoundError on claude binary
# ---------------------------------------------------------------------------


def test_run_probe_claude_binary_not_found(
    session_dir: Path,
    tmpdir_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Branch (v): Popen raises FileNotFoundError → result='failed', cause='claude binary not found'."""

    def _raise(*args, **kwargs):
        raise FileNotFoundError("claude: command not found")

    monkeypatch.setattr(probe_mod.subprocess, "Popen", _raise)

    result = run_probe(session_dir, home_repo=Path.cwd())

    assert result.result == "failed"
    assert result.cause == "claude binary not found"
    assert result.pytest_exit_code is None


# ---------------------------------------------------------------------------
# Branch (iii): claude exits with non-zero exit code
# ---------------------------------------------------------------------------


def test_run_probe_claude_exit_nonzero(
    session_dir: Path,
    tmpdir_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Branch (iii): claude process exits non-zero → result='failed' with cause describing exit code."""
    _patch_popen(monkeypatch, returncode=1)

    result = run_probe(session_dir, home_repo=Path.cwd())

    assert result.result == "failed"
    assert result.cause is not None
    assert "nonzero" in result.cause or "1" in result.cause
    assert result.pytest_exit_code is None


# ---------------------------------------------------------------------------
# Branch (ii): result file not written by the agent
# ---------------------------------------------------------------------------


def test_run_probe_missing_result_file(
    session_dir: Path,
    tmpdir_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Branch (ii): claude exits 0 but result file absent → result='failed', cause mentions 'result file'."""
    _patch_popen(monkeypatch, returncode=0)
    # Leave tmpdir_env empty — the result file is never written.

    result = run_probe(session_dir, home_repo=Path.cwd())

    assert result.result == "failed"
    assert result.cause is not None
    assert "result file" in result.cause


# ---------------------------------------------------------------------------
# Branch (iv): skipped > 0
# ---------------------------------------------------------------------------


def test_run_probe_skipped_nonzero(
    session_dir: Path,
    tmpdir_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Branch (iv): pytest summary contains 1 skipped → result='failed', cause mentions 'skipped'."""
    # Patch Popen to succeed (exit 0).
    popen_cls = _patch_popen(monkeypatch, returncode=0)

    # Intercept the Popen constructor so we can discover which result/output
    # paths the probe computed and pre-populate them before .wait() returns.
    result_path_holder: list[Path] = []
    output_path_holder: list[Path] = []

    real_popen_cls = popen_cls

    def _capturing_popen(args, **kwargs):
        # Extract result_path and output_path from the prompt argument.
        # The prompt is args[2] (index 2 of the claude CLI argv list).
        prompt_text: str = args[2]

        # Parse paths embedded in the prompt by _build_prompt().
        # Prompt format: "... tee <output_path>; printf 'exit=%d\n' $? > <result_path> ..."
        import re
        tee_m = re.search(r"tee\s+(\S+);", prompt_text)
        result_m = re.search(r"printf\s+'exit=%d\\n'\s+\$\?\s+>\s+(\S+)", prompt_text)

        if tee_m:
            output_path_holder.append(Path(tee_m.group(1)))
        if result_m:
            result_path_holder.append(Path(result_m.group(1)))

        # Pre-populate the files before returning the mock proc.
        # result file: exit=0 (pytest ran, but with a skipped test)
        if result_path_holder:
            result_path_holder[0].write_text("exit=0\n", encoding="utf-8")
        # output file: pytest summary with 1 skipped
        if output_path_holder:
            output_path_holder[0].write_bytes(
                b"====== 2 passed, 1 skipped in 0.42s ======\n"
            )

        return real_popen_cls.return_value

    monkeypatch.setattr(probe_mod.subprocess, "Popen", _capturing_popen)

    result = run_probe(session_dir, home_repo=Path.cwd())

    assert result.result == "failed"
    assert result.cause is not None
    assert "skipped" in result.cause


# ---------------------------------------------------------------------------
# Branch (i): successful parse → result="ok"
# ---------------------------------------------------------------------------


def test_run_probe_success(
    session_dir: Path,
    tmpdir_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Branch (i): claude exits 0, result file present with exit=0, output has >=2 passed, 0 skipped/failed/error → result='ok'."""
    popen_cls = _patch_popen(monkeypatch, returncode=0)

    result_path_holder: list[Path] = []
    output_path_holder: list[Path] = []

    real_proc = popen_cls.return_value

    def _capturing_popen(args, **kwargs):
        prompt_text: str = args[2]

        import re
        tee_m = re.search(r"tee\s+(\S+);", prompt_text)
        result_m = re.search(r"printf\s+'exit=%d\\n'\s+\$\?\s+>\s+(\S+)", prompt_text)

        if tee_m:
            output_path_holder.append(Path(tee_m.group(1)))
        if result_m:
            result_path_holder.append(Path(result_m.group(1)))

        if result_path_holder:
            result_path_holder[0].write_text("exit=0\n", encoding="utf-8")
        if output_path_holder:
            output_path_holder[0].write_bytes(
                b"tests/test_worktree_seatbelt.py::test_write_blocked PASSED\n"
                b"tests/test_worktree_seatbelt.py::test_read_allowed PASSED\n"
                b"====== 2 passed in 0.41s ======\n"
            )

        return real_proc

    monkeypatch.setattr(probe_mod.subprocess, "Popen", _capturing_popen)

    result = run_probe(session_dir, home_repo=Path.cwd())

    assert result.result == "ok"
    assert result.pytest_exit_code == 0
    assert result.cause is None
    assert "passed=2" in result.pytest_summary
    assert "skipped=0" in result.pytest_summary
    assert result.stdout_sha256 is not None
