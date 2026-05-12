"""Byte-equivalence test for cortex-* invocation telemetry (Spec R12).

The packaged ``cortex_command.backlog._telemetry.log_invocation`` must
produce a JSONL record that is byte-for-byte identical to what
``bin/cortex-log-invocation`` emits for the same inputs (modulo
timestamp drift, which is normalized away in the comparison).

This is the only acceptance gate for R12 — the spec's
``bin/cortex-invocation-report --json | jq '.invocations[]'`` command
is broken (the aggregator's JSON shape has no ``.invocations[]`` key);
this byte-equivalence test is the working substitute.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from cortex_command.backlog import _telemetry


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BASH_SHIM = REPO_ROOT / "bin" / "cortex-log-invocation"


def _normalize_ts(line: str) -> str:
    """Replace any ISO-8601-Z timestamp with a fixed sentinel for comparison."""
    return re.sub(
        r'"ts":"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"',
        '"ts":"<TS>"',
        line,
    )


@pytest.mark.skipif(
    not BASH_SHIM.is_file(),
    reason="bin/cortex-log-invocation not present (CLI tier not installed)",
)
@pytest.mark.parametrize("use_env_var", [False, True], ids=["slow-path", "fast-path"])
def test_python_helper_byte_equivalent_to_bash_shim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    use_env_var: bool,
) -> None:
    """Each side writes one JSONL record; the records (sans ts) must match byte-for-byte.

    Parametrized over the two repo-root resolution paths the shim and
    Python emitter both implement (#198 Task 2):

    - ``slow-path``: ``CORTEX_REPO_ROOT`` is unset; both sides fall through
      to ``git rev-parse --show-toplevel``. Original coverage.
    - ``fast-path``: ``CORTEX_REPO_ROOT`` is set to the fake repo; both
      sides take the env-var fast path with ``.git``-marker validation.
      Closes the gap where the new env-var branch was previously unreached
      by this test.
    """
    session_id = "session-test-byte-equivalence-20260429"

    # Stage a fake repo: HOME so breadcrumbs land in tmp; CWD inside a git
    # repo so `git rev-parse --show-toplevel` from the bash shim resolves
    # to a tmp-rooted toplevel. The Python helper uses the same git
    # rev-parse call, so both implementations target the same repo root.
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", str(fake_repo)],
        check=True,
        capture_output=True,
    )

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("LIFECYCLE_SESSION_ID", session_id)
    if use_env_var:
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(fake_repo))
    else:
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    monkeypatch.chdir(fake_repo)

    session_dir = fake_repo / "lifecycle" / "sessions" / session_id
    session_dir.mkdir(parents=True)
    log_file = session_dir / "bin-invocations.jsonl"

    # ---- Bash shim invocation ----
    # Bash shim takes argv: <script_path> [args...]; argv_count = $# - 1.
    # Use script_path "cortex-test-script" and two synthetic args to make
    # argv_count = 2 deterministic.
    bash_env = {
        **os.environ,
        "HOME": str(fake_home),
        "LIFECYCLE_SESSION_ID": session_id,
    }
    if use_env_var:
        bash_env["CORTEX_REPO_ROOT"] = str(fake_repo)
    else:
        bash_env.pop("CORTEX_REPO_ROOT", None)
    bash_result = subprocess.run(
        [str(BASH_SHIM), "cortex-test-script", "arg-one", "arg-two"],
        env=bash_env,
        cwd=str(fake_repo),
        capture_output=True,
        text=True,
    )
    assert bash_result.returncode == 0, f"bash shim failed: {bash_result.stderr}"
    bash_lines = log_file.read_bytes().splitlines()
    assert len(bash_lines) == 1, f"expected exactly 1 bash record, got {len(bash_lines)}"
    bash_line = bash_lines[0].decode("utf-8")

    # ---- Truncate the log so the Python record stands alone ----
    log_file.write_text("")

    # ---- Python helper invocation ----
    # Python's argv_count is len(sys.argv) - 1, so set argv to mirror
    # the bash invocation: argv[0] is the user-visible command name,
    # argv[1..] are the args. argv_count = 2 to match.
    monkeypatch.setattr(sys, "argv", ["cortex-test-script", "arg-one", "arg-two"])
    _telemetry.log_invocation("cortex-test-script")
    py_lines = log_file.read_bytes().splitlines()
    assert len(py_lines) == 1, f"expected exactly 1 python record, got {len(py_lines)}"
    py_line = py_lines[0].decode("utf-8")

    # ---- Byte-equivalence (modulo ts) ----
    bash_norm = _normalize_ts(bash_line)
    py_norm = _normalize_ts(py_line)
    assert bash_norm == py_norm, (
        "byte-equivalence mismatch:\n"
        f"  bash:   {bash_norm!r}\n"
        f"  python: {py_norm!r}"
    )

    # Also verify the actual record schema matches expectations.
    record = json.loads(py_line)
    assert set(record.keys()) == {"ts", "script", "argv_count", "session_id"}
    assert record["script"] == "cortex-test-script"
    assert record["argv_count"] == 2
    assert record["session_id"] == session_id
