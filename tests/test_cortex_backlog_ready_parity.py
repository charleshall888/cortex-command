"""Parity test: cortex_command.backlog.ready vs captured fixtures.

Golden-replay fixture test that asserts the Python module produces
stdout/stderr/exit-code matching the captured fixtures under the named
tolerances declared in ``tests/fixtures/cortex-backlog-ready/README.md``.

Each fixture quintuple in tests/fixtures/cortex-backlog-ready/ contains:
  <case>.argv      one argv element per line (empty file = no extra args)
  <case>.stdin     literal bytes to pipe to stdin (empty for all current cases)
  <case>.stdout    captured stdout bytes
  <case>.stderr    captured stderr bytes
  <case>.exitcode  decimal exit status + trailing newline

The active-path fixtures (``ready_only``, ``include_blocked``) require a
synthetic backlog to be constructed in tmp_path before invocation. The
``missing_backlog_dir`` case is invoked in an empty tmp_path.

Named-tolerance categories:
  stdout: ["key-reorder", "unicode-escape", "number-format"]  (JSON output)
  stderr: empty for all current fixtures (byte-identical comparison)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Iterator

import pytest

from tests.test_parity_contract import (
    assert_byte_identical,
    assert_structurally_equivalent,
)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "cortex-backlog-ready"

_DETERMINISM_ENV_OVERRIDES: dict[str, str] = {
    "LC_ALL": "C",
    "TZ": "UTC",
}


# ---------------------------------------------------------------------------
# Synthetic backlog snapshot
# Used by active-path cases (ready_only, include_blocked).
# active records go into index.json; all records are written as .md files
# so the full-corpus scan (_load_full_corpus) can resolve terminal items.
# ---------------------------------------------------------------------------

_ACTIVE_RECORDS = [
    {
        "id": 1, "title": "critical refined item", "status": "refined",
        "priority": "critical", "type": "feature", "blocked_by": [], "parent": None,
        "tags": [], "uuid": "aaaaaaaa-0000-0000-0000-000000000001",
    },
    {
        "id": 2, "title": "high backlog item", "status": "backlog",
        "priority": "high", "type": "bug", "blocked_by": [], "parent": None,
        "tags": [], "uuid": "aaaaaaaa-0000-0000-0000-000000000002",
    },
    {
        "id": 3, "title": "medium backlog item", "status": "backlog",
        "priority": "medium", "type": "chore", "blocked_by": [], "parent": None,
        "tags": [], "uuid": "aaaaaaaa-0000-0000-0000-000000000003",
    },
    {
        "id": 5, "title": "external blocked item", "status": "backlog",
        "priority": "high", "type": "feature",
        "blocked_by": ["anthropics/claude-code#9999"], "parent": None,
        "tags": [], "uuid": "aaaaaaaa-0000-0000-0000-000000000005",
    },
]

_ALL_RECORDS = _ACTIVE_RECORDS + [
    {
        "id": 4, "title": "complete item", "status": "complete",
        "priority": "high", "type": "feature", "blocked_by": [], "parent": None,
        "tags": [], "uuid": "aaaaaaaa-0000-0000-0000-000000000004",
    },
]

# Cases that require the synthetic backlog (cwd must contain cortex/backlog/).
_NEEDS_BACKLOG: frozenset[str] = frozenset({"ready_only", "include_blocked"})


# ---------------------------------------------------------------------------
# Fixture discovery helpers
# ---------------------------------------------------------------------------


def _discover_cases() -> list[str]:
    """Return sorted list of case names present in the fixture directory."""
    return sorted(p.stem for p in FIXTURE_DIR.glob("*.argv"))


def _read_argv(case: str) -> list[str]:
    """Parse <case>.argv: one element per line (strip trailing newlines)."""
    text = (FIXTURE_DIR / f"{case}.argv").read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line]


def _read_stdin(case: str) -> bytes:
    return (FIXTURE_DIR / f"{case}.stdin").read_bytes()


def _read_expected_stdout(case: str) -> bytes:
    return (FIXTURE_DIR / f"{case}.stdout").read_bytes()


def _read_expected_stderr(case: str) -> bytes:
    return (FIXTURE_DIR / f"{case}.stderr").read_bytes()


def _read_expected_exitcode(case: str) -> int:
    return int((FIXTURE_DIR / f"{case}.exitcode").read_text(encoding="utf-8").strip())


# ---------------------------------------------------------------------------
# Synthetic backlog construction
# ---------------------------------------------------------------------------


def _write_md(backlog_dir: Path, record: dict) -> None:
    """Write a minimal NNN-slug.md frontmatter file for *record*."""
    slug = record["title"].replace(" ", "-")
    md_path = backlog_dir / f"{record['id']:03d}-{slug}.md"
    lines = [
        "---",
        'schema_version: "1"',
        f"uuid: {record['uuid']}",
        f"id: {record['id']}",
        f'title: "{record["title"]}"',
        f"status: {record['status']}",
        f"priority: {record['priority']}",
        f"type: {record['type']}",
        f"blocked_by: {json.dumps(record['blocked_by'])}",
        f"parent: {json.dumps(record['parent'])}",
        "---",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")


def _build_fixture_backlog(tmp_path: Path) -> Path:
    """Materialize the synthetic backlog under tmp_path/cortex/backlog/.

    All records (active + terminal) are written as .md files so the
    full-corpus scan in _load_full_corpus can resolve terminal blockers.
    index.json contains only active records, mirroring real collect_items()
    behavior.
    """
    backlog_dir = tmp_path / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True)
    for record in _ALL_RECORDS:
        _write_md(backlog_dir, record)
    (backlog_dir / "index.json").write_text(
        json.dumps(_ACTIVE_RECORDS, indent=2) + "\n",
        encoding="utf-8",
    )
    return backlog_dir


# ---------------------------------------------------------------------------
# Invocation helper
# ---------------------------------------------------------------------------

_result_cache: dict[tuple[str, str], subprocess.CompletedProcess] = {}


def _get_cwd(case: str, tmp_path: Path) -> Path:
    """Return the cwd to use when invoking the module for *case*."""
    if case in _NEEDS_BACKLOG:
        _build_fixture_backlog(tmp_path)
        return tmp_path
    # missing_backlog_dir and any future no-backlog cases use bare tmp_path.
    return tmp_path


def _invoke_case(case: str, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run python3 -m cortex_command.backlog.ready for the given fixture case."""
    cache_key = (str(tmp_path), case)
    if cache_key in _result_cache:
        return _result_cache[cache_key]

    argv = _read_argv(case)
    stdin_bytes = _read_stdin(case)
    cwd = _get_cwd(case, tmp_path)

    import os
    env = dict(os.environ)
    env.update(_DETERMINISM_ENV_OVERRIDES)
    # Prepend the repo root to PYTHONPATH so the working-tree module takes
    # precedence over any installed wheel that may still carry the stub.
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(REPO_ROOT) + (":" + existing_pythonpath if existing_pythonpath else "")
    )

    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.backlog.ready"] + argv,
        input=stdin_bytes,
        capture_output=True,
        cwd=str(cwd),
        env=env,
    )
    _result_cache[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# Parametrized parity tests
# ---------------------------------------------------------------------------


@pytest.mark.structural_equivalence(
    stream="stdout",
    tolerances=["key-reorder", "unicode-escape", "number-format"],
)
@pytest.mark.parametrize("case", _discover_cases())
def test_stdout_parity(case: str, tmp_path: Path) -> None:
    """stdout is structurally equivalent to the fixture (JSON document)."""
    expected_stdout = _read_expected_stdout(case)
    actual_stdout = _invoke_case(case, tmp_path).stdout

    # Both sides should be parseable JSON; use structural equivalence
    # with key-reorder + unicode-escape + number-format tolerances.
    assert_structurally_equivalent(
        actual_stdout,
        expected_stdout,
        stream="stdout",
        tolerances=["key-reorder", "unicode-escape", "number-format"],
    )


@pytest.mark.parametrize("case", _discover_cases())
def test_stderr_parity(case: str, tmp_path: Path) -> None:
    """stderr is byte-identical to the fixture (empty for all current cases)."""
    expected_stderr = _read_expected_stderr(case)
    actual_stderr = _invoke_case(case, tmp_path).stderr

    if not expected_stderr and not actual_stderr:
        assert_byte_identical(actual_stderr, expected_stderr)
    else:
        assert_byte_identical(actual_stderr, expected_stderr)


@pytest.mark.parametrize("case", _discover_cases())
def test_exitcode_parity(case: str, tmp_path: Path) -> None:
    """Exit code matches the fixture capture."""
    expected_exitcode = _read_expected_exitcode(case)
    result = _invoke_case(case, tmp_path)
    assert result.returncode == expected_exitcode, (
        f"exit code mismatch for {case!r}: "
        f"got {result.returncode}, expected {expected_exitcode}"
    )
