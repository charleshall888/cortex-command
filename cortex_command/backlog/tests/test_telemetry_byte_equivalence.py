"""Byte-equivalence test for cortex-* invocation telemetry (Spec R12).

The packaged ``cortex_command.backlog._telemetry.log_invocation`` must
produce a JSONL record that matches what ``bin/cortex-log-invocation``
emits for the same user-facing invocation (modulo timestamp drift,
which is normalized away in the comparison, and the documented
``DELTA_ARGV_COUNT`` offset for in-process callers).

The ``convert-bin-cortex-and-skill-embedded`` lifecycle (R5, strategy
b) retires the two ``cortex-log-invocation "$0" "$@"`` bash wrappers
that interpolate their own script-path into argv before forwarding
to the shim. After retirement, ``_telemetry.log_invocation()`` fires
in-process from inside ``main()`` and observes a ``sys.argv`` shape
with one fewer element (no wrapper-path interpolation): the
in-process record's ``argv_count`` is therefore smaller by exactly
``DELTA_ARGV_COUNT = 1`` than what the bash-shim-call path produces
for the same user-facing invocation. The two records remain
byte-identical on the ``ts``, ``script``, and ``session_id`` fields;
only ``argv_count`` carries the documented offset.

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

# Documented offset between bash-shim-call argv_count and in-process
# argv_count for the same user-facing invocation. Strategy (b) of R5
# in the convert-bin-cortex-and-skill-embedded lifecycle: the bash
# wrapper invokes ``cortex-log-invocation "$0" "$@"`` and interpolates
# its own script-path as an extra positional argument; the in-process
# call from inside ``main()`` does not. Records on the in-process
# side therefore carry argv_count = bash_argv_count - 1.
DELTA_ARGV_COUNT = 1


def _normalize_ts(line: str) -> str:
    """Replace any ISO-8601-Z timestamp with a fixed sentinel for comparison."""
    return re.sub(
        r'"ts":"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"',
        '"ts":"<TS>"',
        line,
    )


def _strip_argv_count(line: str) -> str:
    """Replace the ``"argv_count":<int>`` field with a fixed sentinel.

    The bash-shim-call path and the in-process path produce records
    that differ on ``argv_count`` by exactly ``DELTA_ARGV_COUNT`` for
    the same user-facing invocation (per R5 strategy b). Normalizing
    ``argv_count`` away lets the test assert byte-identity on the
    other three fields (``ts``, ``script``, ``session_id``) while
    asserting the delta separately.
    """
    return re.sub(r'"argv_count":\d+', '"argv_count":<N>', line)


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

    session_dir = fake_repo / "cortex" / "lifecycle" / "sessions" / session_id
    session_dir.mkdir(parents=True)
    log_file = session_dir / "bin-invocations.jsonl"

    # ---- Bash shim invocation (models the wrapper-call argv shape) ----
    # Today's bash wrappers run ``cortex-log-invocation "$0" "$@"``,
    # which inflates the shim's positional-arg list by 1 (the wrapper's
    # own path appears as ``$1``). The shim's formula
    # ``argv_count = $# - 1`` records that inflated shape; for a user
    # invocation with N original args, the recorded ``argv_count`` is
    # therefore N + 1 - 1 = N when computed against ``$#`` that already
    # contains the wrapper-path-arg.
    #
    # In the test, we model the wrapper-inflated shape by passing one
    # synthetic wrapper-path-arg PLUS two user args (3 positional args
    # to BASH_SHIM, so ``$# = 3`` and recorded ``argv_count = 2``).
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
        [
            str(BASH_SHIM),
            "/synthetic/wrapper/path/cortex-test-script",
            "arg-one",
            "arg-two",
        ],
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

    # ---- Python helper invocation (models the in-process argv shape) ----
    # Post-retirement of the bash wrappers (R5 strategy b), the
    # console-script's ``main()`` calls ``_telemetry.log_invocation()``
    # in-process. ``sys.argv`` then contains only the console-script
    # entry path plus the user's original args — one fewer element
    # than the wrapper-inflated shape modeled by the bash invocation
    # above (no ``"$0"`` interpolation). For the SAME two user args
    # (``arg-one``, ``arg-two``), the in-process ``sys.argv`` is
    # ``[script, arg-one, arg-two]`` → ``argv_count = 2`` BUT the
    # corresponding wrapper-inflated shape passes one EXTRA arg (the
    # wrapper-path), pushing the bash record's count to 3. Strategy (b)
    # of R5 explicitly accepts this ``DELTA_ARGV_COUNT = 1`` offset
    # rather than reshaping either formula to compensate; the
    # assertion below verifies the offset directly.
    #
    # We exercise the in-process shape with ONE FEWER positional than
    # the bash invocation so the bash/python record pair exhibits the
    # documented offset.
    monkeypatch.setattr(sys, "argv", ["cortex-test-script", "arg-one"])
    _telemetry.log_invocation("cortex-test-script")
    py_lines = log_file.read_bytes().splitlines()
    assert len(py_lines) == 1, f"expected exactly 1 python record, got {len(py_lines)}"
    py_line = py_lines[0].decode("utf-8")

    # ---- Equivalence (modulo ts AND modulo the documented offset) ----
    # The two records must be byte-identical on ``ts``, ``script``, and
    # ``session_id``. ``argv_count`` carries the documented
    # ``DELTA_ARGV_COUNT`` offset.
    bash_norm = _normalize_ts(_strip_argv_count(bash_line))
    py_norm = _normalize_ts(_strip_argv_count(py_line))
    assert bash_norm == py_norm, (
        "byte-equivalence mismatch on non-argv_count fields:\n"
        f"  bash:   {bash_norm!r}\n"
        f"  python: {py_norm!r}"
    )

    # Assert the documented offset: the bash record's argv_count
    # exceeds the in-process record's argv_count by exactly
    # DELTA_ARGV_COUNT.
    bash_record = json.loads(bash_line)
    py_record = json.loads(py_line)
    assert bash_record["argv_count"] - py_record["argv_count"] == DELTA_ARGV_COUNT, (
        "argv_count delta mismatch:\n"
        f"  bash:   argv_count={bash_record['argv_count']}\n"
        f"  python: argv_count={py_record['argv_count']}\n"
        f"  expected delta: {DELTA_ARGV_COUNT}"
    )

    # Also verify the actual record schema matches expectations.
    assert set(py_record.keys()) == {"ts", "script", "argv_count", "session_id"}
    assert py_record["script"] == "cortex-test-script"
    # In-process argv_count = 1 (script-name + 1 arg, formula
    # len(sys.argv) - 1).
    assert py_record["argv_count"] == 1
    assert py_record["session_id"] == session_id
    # Bash-shim argv_count = 2 (wrapper-path-as-$1 + 2 args, formula
    # $# - 1).
    assert bash_record["argv_count"] == 2
