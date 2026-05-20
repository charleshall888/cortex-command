"""Parity test: cortex_command.backlog.load_parent_epic vs original bin script.

Golden-replay fixture test that asserts the Python port produces
byte-equivalent stdout/stderr/exit-code as the captured original, within
the named tolerances declared in the fixture README.

Each fixture quintuple in tests/fixtures/cortex-load-parent-epic/ contains:
  <case>.argv      one argv element per line (line 1 is argv[1] of the script)
  <case>.stdin     literal bytes to pipe to stdin (empty for all current cases)
  <case>.stdout    captured stdout bytes
  <case>.stderr    captured stderr bytes
  <case>.exitcode  decimal exit status + trailing newline

The `broken_parent` case requires a synthetic backlog created at runtime in
`tmp_path`; the parity test sets `CORTEX_BACKLOG_DIR` to that synthetic dir.
The `valid_parent` and `no_parent` cases point `CORTEX_BACKLOG_DIR` at the
repo's live `cortex/backlog/`.

Named-tolerance categories opted in for this fixture set (per README):
  stdout:  ["unicode-escape", "trailing-newline", "key-reorder"]
  stderr:  []  (byte-identical; always empty for captured cases)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_parity_contract import (
    assert_byte_identical,
    assert_structurally_equivalent,
)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "cortex-load-parent-epic"
BACKLOG_DIR = REPO_ROOT / "cortex" / "backlog"

# Determinism env-var overrides mirroring the capture harness (see README).
_DETERMINISM_ENV_OVERRIDES: dict[str, str] = {
    "LC_ALL": "C",
    "TZ": "UTC",
}


# ---------------------------------------------------------------------------
# Fixture discovery helpers
# ---------------------------------------------------------------------------


def _discover_cases() -> list[str]:
    """Return sorted list of case names present in the fixture directory."""
    cases: list[str] = []
    for path in FIXTURE_DIR.glob("*.argv"):
        cases.append(path.stem)
    return sorted(cases)


def _read_argv(case: str) -> list[str]:
    """Parse <case>.argv: one element per line (strip trailing newlines)."""
    text = (FIXTURE_DIR / f"{case}.argv").read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line]


def _read_stdin(case: str) -> bytes:
    """Read <case>.stdin as raw bytes (may be empty)."""
    return (FIXTURE_DIR / f"{case}.stdin").read_bytes()


def _read_expected_stdout(case: str) -> bytes:
    return (FIXTURE_DIR / f"{case}.stdout").read_bytes()


def _read_expected_stderr(case: str) -> bytes:
    return (FIXTURE_DIR / f"{case}.stderr").read_bytes()


def _read_expected_exitcode(case: str) -> int:
    text = (FIXTURE_DIR / f"{case}.exitcode").read_text(encoding="utf-8").strip()
    return int(text)


# ---------------------------------------------------------------------------
# Synthetic backlog setup for broken_parent case
# ---------------------------------------------------------------------------

_CHILD_ITEM_CONTENT = """\
---
id: 100
title: "Child item"
type: chore
status: active
parent: 999
---

# Child item
"""

# Deliberately malformed YAML — mapping collision causes yaml.safe_load to raise.
_BROKEN_PARENT_CONTENT = """\
---
id: 999
title: broken
type: epic
bad: :
  - broken: yaml
    :
---
"""


def _setup_broken_backlog(tmp_path: Path) -> Path:
    """Create a synthetic backlog dir with child + broken-parent for the broken_parent case."""
    backlog = tmp_path / "backlog"
    backlog.mkdir(parents=True, exist_ok=True)
    (backlog / "100-child-item.md").write_text(_CHILD_ITEM_CONTENT, encoding="utf-8")
    (backlog / "999-broken-epic.md").write_text(_BROKEN_PARENT_CONTENT, encoding="utf-8")
    return backlog


# ---------------------------------------------------------------------------
# Environment construction
# ---------------------------------------------------------------------------


def _build_env(*, backlog_dir: str) -> dict[str, str]:
    """Build a minimal environment for one fixture invocation.

    Inherits the current process environment, then applies determinism
    overrides and CORTEX_BACKLOG_DIR.
    """
    env = dict(os.environ)
    env.update(_DETERMINISM_ENV_OVERRIDES)
    env["CORTEX_BACKLOG_DIR"] = backlog_dir
    # Remove LIFECYCLE_SESSION_ID so telemetry does not write side-effects.
    env.pop("LIFECYCLE_SESSION_ID", None)
    return env


# ---------------------------------------------------------------------------
# Per-case backlog dir
# ---------------------------------------------------------------------------


def _get_backlog_dir(case: str, tmp_path: Path) -> str:
    """Return the backlog directory path string for a given case."""
    if case == "broken_parent":
        return str(_setup_broken_backlog(tmp_path))
    # valid_parent and no_parent use the live repo backlog.
    return str(BACKLOG_DIR)


# ---------------------------------------------------------------------------
# Invocation helper (memoized per case+tmp_path)
# ---------------------------------------------------------------------------

_result_cache: dict[tuple, subprocess.CompletedProcess] = {}


def _invoke_case(case: str, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run python3 -m cortex_command.backlog.load_parent_epic for the given fixture case."""
    cache_key = (id(tmp_path), case)
    if cache_key in _result_cache:
        return _result_cache[cache_key]

    argv = _read_argv(case)
    stdin_bytes = _read_stdin(case)
    backlog_dir = _get_backlog_dir(case, tmp_path)
    env = _build_env(backlog_dir=backlog_dir)

    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.backlog.load_parent_epic"] + argv,
        input=stdin_bytes,
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=env,
    )

    _result_cache[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# Parametrized parity tests
# ---------------------------------------------------------------------------


@pytest.mark.structural_equivalence(
    stream="stdout",
    tolerances=["unicode-escape", "trailing-newline", "key-reorder"],
)
@pytest.mark.parametrize("case", _discover_cases())
def test_stdout_parity(case: str, tmp_path: Path) -> None:
    """stdout matches the fixture capture within named tolerances."""
    expected_stdout = _read_expected_stdout(case)
    actual_stdout = _invoke_case(case, tmp_path).stdout

    if not expected_stdout and not actual_stdout:
        assert_byte_identical(actual_stdout, expected_stdout)
    else:
        assert_structurally_equivalent(
            actual_stdout,
            expected_stdout,
            stream="stdout",
            tolerances=["unicode-escape", "trailing-newline", "key-reorder"],
        )


@pytest.mark.parametrize("case", _discover_cases())
def test_stderr_parity(case: str, tmp_path: Path) -> None:
    """stderr is byte-identical to the fixture capture (always empty)."""
    expected_stderr = _read_expected_stderr(case)
    actual_stderr = _invoke_case(case, tmp_path).stderr
    assert_byte_identical(actual_stderr, expected_stderr)


@pytest.mark.parametrize("case", _discover_cases())
def test_exitcode_parity(case: str, tmp_path: Path) -> None:
    """Exit code matches the fixture capture."""
    expected_exitcode = _read_expected_exitcode(case)
    result = _invoke_case(case, tmp_path)
    assert result.returncode == expected_exitcode, (
        f"exit code mismatch for {case!r}: "
        f"got {result.returncode}, expected {expected_exitcode}\n"
        f"stdout: {result.stdout!r}\n"
        f"stderr: {result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Edge-case parametric tests (synthetic backlog, not fixture files)
# ---------------------------------------------------------------------------


def test_missing_parent_branch(tmp_path: Path) -> None:
    """Child with a parent id that has no matching NNN-*.md emits missing JSON, exit 0."""
    backlog = tmp_path / "backlog"
    backlog.mkdir()
    # Child references parent 42, but no 042-*.md exists.
    (backlog / "010-child.md").write_text(
        "---\nid: 10\ntitle: child\nparent: 42\ntype: chore\n---\n", encoding="utf-8"
    )
    env = _build_env(backlog_dir=str(backlog))
    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.backlog.load_parent_epic", "010-child"],
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=env,
    )
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}: {result.stderr!r}"
    data = json.loads(result.stdout.decode("utf-8"))
    assert data == {"status": "missing", "parent_id": 42}


def test_non_epic_parent_branch(tmp_path: Path) -> None:
    """Parent file whose type is not 'epic' emits non_epic JSON, exit 0."""
    backlog = tmp_path / "backlog"
    backlog.mkdir()
    (backlog / "010-child.md").write_text(
        "---\nid: 10\ntitle: child\nparent: 20\ntype: chore\n---\n", encoding="utf-8"
    )
    (backlog / "020-parent.md").write_text(
        "---\nid: 20\ntitle: not an epic\ntype: chore\n---\n", encoding="utf-8"
    )
    env = _build_env(backlog_dir=str(backlog))
    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.backlog.load_parent_epic", "010-child"],
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=env,
    )
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}: {result.stderr!r}"
    data = json.loads(result.stdout.decode("utf-8"))
    assert data["status"] == "non_epic"
    assert data["parent_id"] == 20
    assert data["type"] == "chore"


def test_drift_normalize_parent() -> None:
    """normalize_parent in load_parent_epic.py must be byte-equivalent to build_epic_map.py.

    Asserts the local re-implementation and canonical import agree on a
    representative corpus of values — the same drift contract the original
    bin/ script comments described.
    """
    from cortex_command.backlog.build_epic_map import normalize_parent as canonical
    from cortex_command.backlog.load_parent_epic import normalize_parent as local

    cases = [
        None,
        0,
        1,
        42,
        "42",
        "'42'",
        '"42"',
        "42-foo",
        "abc",
        "uuid-shaped-value",
        3.0,
        True,
        [],
        {},
    ]
    for value in cases:
        expected = canonical(value)
        actual = local(value)
        assert actual == expected, (
            f"normalize_parent drift for {value!r}: "
            f"local={actual!r} canonical={expected!r}"
        )
