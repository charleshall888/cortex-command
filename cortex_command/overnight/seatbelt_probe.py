"""Seatbelt probe module for overnight session-start validation.

Spawns ``claude -p`` under orchestrator-style sandbox settings, has the spawned
agent invoke ``pytest tests/test_worktree_seatbelt.py -v`` via Bash, reads pytest
exit code and summary from ``$TMPDIR/``-resident files the agent's command writes
(bypassing model paraphrase), and constructs a ``ProbeResult``.

The module emits no events itself — the runner (Task 7) is the dual emitter.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from cortex_command.overnight.sandbox_settings import (
    build_orchestrator_deny_paths,
    build_sandbox_settings_dict,
    read_soft_fail_env,
    register_atexit_cleanup,
    write_settings_tempfile,
)


@dataclass
class ProbeResult:
    """Result of a single seatbelt probe invocation."""

    result: Literal["ok", "failed"]
    pytest_exit_code: Optional[int]
    pytest_summary: str
    stdout_path: Optional[Path]
    stdout_sha256: Optional[str]
    cause: Optional[str]


def _build_prompt(output_path: Path, result_path: Path) -> str:
    """Build the verbatim prompt from spec R4 with paths substituted."""
    return (
        f"Execute exactly this Bash command in a single tool call and exit immediately:\n"
        f"\n"
        f"uv run pytest tests/test_worktree_seatbelt.py -v 2>&1 | tee {output_path}; "
        f"printf 'exit=%d\\n' $? > {result_path}\n"
        f"\n"
        f"Do not modify the command. Do not add any other tool calls. "
        f"After the Bash returns, respond with a one-word summary (\"done\" is fine) and exit."
    )


def run_probe(session_dir: Path, home_repo: Path) -> ProbeResult:
    """Run the seatbelt probe under orchestrator-style sandbox settings.

    Spawns ``claude -p`` with the verbatim prompt from spec R4, reads the pytest
    exit code and summary from ``$TMPDIR/``-resident files the agent's Bash command
    writes, and returns a ``ProbeResult``.

    On any failure mode (claude binary missing, non-zero exit, result-file missing,
    exit != 0, count assertion fails), returns ``result="failed"`` with a one-line
    ``cause``.

    Args:
        session_dir: The overnight session directory (used for sandbox settings
            tempfile and claude stdout capture).
        home_repo: Absolute path to the home cortex repo.

    Returns:
        A ``ProbeResult`` describing the outcome.
    """
    # Resolve $TMPDIR once; use it for both UUID-named result files and the
    # allow-list entry.
    tmpdir = os.environ.get("TMPDIR", "/tmp")
    tmpdir_resolved = Path(tmpdir).resolve()

    # UUID-randomized basenames so concurrent probe invocations don't collide.
    output_path = Path(tmpdir) / f"cortex-seatbelt-output-{uuid.uuid4()}.txt"
    result_path = Path(tmpdir) / f"cortex-seatbelt-result-{uuid.uuid4()}.txt"

    # Build sandbox settings: orchestrator deny-set + minimal $TMPDIR allow.
    deny_paths = build_orchestrator_deny_paths(home_repo, integration_worktrees={})
    soft_fail = read_soft_fail_env()
    settings = build_sandbox_settings_dict(
        deny_paths,
        allow_paths=[str(tmpdir_resolved)],
        soft_fail=soft_fail,
    )

    # Write the per-spawn tempfile and register atexit cleanup.
    tempfile_path = write_settings_tempfile(session_dir, settings)
    register_atexit_cleanup(tempfile_path)

    # Build the verbatim prompt from spec R4.
    prompt = _build_prompt(output_path, result_path)

    # Capture claude's stdout to a file under session_dir (avoid Popen
    # pipe-buffer deadlock per runner.py:1029 pattern).
    claude_stdout_path = session_dir / "seatbelt-probe-claude-stdout.json"
    claude_stderr_path = session_dir / "seatbelt-probe-claude-stderr.txt"

    # --- Spawn claude -p ---
    try:
        with open(claude_stdout_path, "wb") as stdout_handle, \
             open(claude_stderr_path, "wb") as stderr_handle:
            proc = subprocess.Popen(
                [
                    "claude",
                    "-p",
                    prompt,
                    "--settings",
                    str(tempfile_path),
                    "--dangerously-skip-permissions",
                    "--max-turns",
                    "4",
                    "--output-format=json",
                ],
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
                env={**os.environ, "CORTEX_RUNNER_CHILD": "1"},
            )
            proc.wait()
        claude_exit = proc.returncode
    except FileNotFoundError:
        return ProbeResult(
            result="failed",
            pytest_exit_code=None,
            pytest_summary="",
            stdout_path=None,
            stdout_sha256=None,
            cause="claude binary not found",
        )

    # Check claude's own exit code.
    if claude_exit != 0:
        # Read stderr tail for the cause string.
        try:
            stderr_bytes = claude_stderr_path.read_bytes()
            stderr_tail = stderr_bytes.decode("utf-8", errors="replace")[-200:]
        except OSError:
            stderr_tail = ""
        return ProbeResult(
            result="failed",
            pytest_exit_code=None,
            pytest_summary="",
            stdout_path=None,
            stdout_sha256=None,
            cause=f"claude exit nonzero: {claude_exit}, stderr tail: {stderr_tail}",
        )

    # --- Read result file ---
    if not result_path.exists():
        return ProbeResult(
            result="failed",
            pytest_exit_code=None,
            pytest_summary="",
            stdout_path=None,
            stdout_sha256=None,
            cause="result file not written; agent likely paraphrased instead of executing the bash command",
        )

    result_text = result_path.read_text(encoding="utf-8", errors="replace").strip()
    if not result_text:
        return ProbeResult(
            result="failed",
            pytest_exit_code=None,
            pytest_summary="",
            stdout_path=None,
            stdout_sha256=None,
            cause="result file empty",
        )

    exit_match = re.search(r"exit=(-?\d+)", result_text)
    if not exit_match:
        return ProbeResult(
            result="failed",
            pytest_exit_code=None,
            pytest_summary="",
            stdout_path=None,
            stdout_sha256=None,
            cause="unparseable pytest summary",
        )
    pytest_exit = int(exit_match.group(1))

    if pytest_exit != 0:
        return ProbeResult(
            result="failed",
            pytest_exit_code=pytest_exit,
            pytest_summary="",
            stdout_path=None,
            stdout_sha256=None,
            cause=f"pytest exit nonzero: {pytest_exit}",
        )

    # --- Read output file and compute sha256 ---
    if not output_path.exists():
        return ProbeResult(
            result="failed",
            pytest_exit_code=pytest_exit,
            pytest_summary="",
            stdout_path=None,
            stdout_sha256=None,
            cause="result file not written; agent likely paraphrased instead of executing the bash command",
        )

    output_bytes = output_path.read_bytes()
    stdout_sha256 = hashlib.sha256(output_bytes).hexdigest()
    output_text = output_bytes.decode("utf-8", errors="replace")

    # Parse individual pytest result counts from the output file.
    def _count(pattern: str) -> int:
        m = re.search(pattern, output_text)
        return int(m.group(1)) if m else 0

    passed = _count(r"(\d+) passed")
    failed = _count(r"(\d+) failed")
    skipped = _count(r"(\d+) skipped")
    error = _count(r"(\d+) error")

    summary = f"passed={passed} failed={failed} skipped={skipped} error={error}"

    # Check skipped > 0 first per spec edge case "sandbox not enforcing".
    if skipped > 0:
        return ProbeResult(
            result="failed",
            pytest_exit_code=pytest_exit,
            pytest_summary=summary,
            stdout_path=output_path,
            stdout_sha256=stdout_sha256,
            cause="skipped count > 0; sandbox not enforcing",
        )

    # Validate count assertions: passed >= 2, failed == 0, skipped == 0, error == 0.
    if not (passed >= 2 and failed == 0 and error == 0):
        # If we can't parse any counts at all, surface as unparseable.
        if passed == 0 and failed == 0 and skipped == 0 and error == 0:
            return ProbeResult(
                result="failed",
                pytest_exit_code=pytest_exit,
                pytest_summary=summary,
                stdout_path=output_path,
                stdout_sha256=stdout_sha256,
                cause="unparseable pytest summary",
            )
        return ProbeResult(
            result="failed",
            pytest_exit_code=pytest_exit,
            pytest_summary=summary,
            stdout_path=output_path,
            stdout_sha256=stdout_sha256,
            cause=f"pytest count assertion failed: {summary}",
        )

    return ProbeResult(
        result="ok",
        pytest_exit_code=pytest_exit,
        pytest_summary=summary,
        stdout_path=output_path,
        stdout_sha256=stdout_sha256,
        cause=None,
    )
