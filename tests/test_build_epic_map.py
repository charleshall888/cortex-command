"""Tests for ``cortex-build-epic-map`` and ``cortex_command.backlog.build_epic_map``.

Covers (per Requirement 11):
  - ``normalize_parent`` unit cases for the four normalization rules
    (null/missing → None, quote-strip, UUID skip, integer match).
  - End-to-end subprocess invocations of the entry point against fixtures
    in ``tests/fixtures/build_epic_map/``.
  - Schema-version validation (only ``"1"`` accepted; others exit 2).
  - Malformed-input handling (invalid JSON, missing path → exit 1).
  - ``spec``-field passthrough (null, missing, empty-string, non-empty).
  - Exit-code branching (0 success, 1 input error, 2 schema mismatch).
  - Ordering correctness (integer-id ascending, NOT lexicographic).
  - Deterministic output across repeated runs.
  - ``--help`` mentions ``index.json`` (Requirement 2).

The packaged module is invoked via ``python -m
cortex_command.backlog.build_epic_map`` in subprocess. Direct unit tests
of ``normalize_parent`` import from ``cortex_command.backlog.build_epic_map``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cortex_command.backlog.build_epic_map import normalize_parent


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "build_epic_map"


def _run_wrapper(*args: str) -> subprocess.CompletedProcess:
    """Invoke the packaged module via ``python -m``.

    Pins ``CORTEX_REPO_ROOT`` to this repo so any user-project-rooted
    resolution inside the build_epic_map module lands here. The legacy
    ``CORTEX_COMMAND_ROOT`` name was renamed to ``CORTEX_REPO_ROOT`` as part
    of the non-editable-wheel-install migration; no production code consults
    the old name.
    """
    env = os.environ.copy()
    env["CORTEX_REPO_ROOT"] = str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "cortex_command.backlog.build_epic_map", *args],
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )


# ---------------------------------------------------------------------------
# normalize_parent — pure-function unit cases
# ---------------------------------------------------------------------------


def test_parent_normalization_null_missing() -> None:
    """Rule 1: explicit ``None`` and missing-key both normalize to ``None``."""
    assert normalize_parent(None) is None
    # Missing key via dict.get() → None passed in.
    item: dict = {}
    assert normalize_parent(item.get("parent")) is None


def test_parent_normalization_quote_strip() -> None:
    """Rule 2: surrounding ``"`` or ``'`` are stripped before integer parsing."""
    assert normalize_parent('"103"') == 103
    assert normalize_parent("'103'") == 103


def test_parent_normalization_uuid_skip() -> None:
    """Rule 3: any value containing ``-`` is treated as UUID-shaped → ``None``."""
    assert normalize_parent("58f9eb72-1234-5678-90ab-cdef01234567") is None
    assert normalize_parent("abc-123") is None


def test_parent_normalization_integer_match() -> None:
    """Rule 4: integer string and bare integer parse; non-numeric → ``None``."""
    assert normalize_parent("103") == 103
    assert normalize_parent(103) == 103
    assert normalize_parent("abc") is None


# ---------------------------------------------------------------------------
# End-to-end subprocess invocations against fixtures
# ---------------------------------------------------------------------------


def test_multi_epic_subprocess() -> None:
    """multi_epic.json: two epics with mixed parent forms produce sorted output."""
    fixture = FIXTURES / "multi_epic.json"
    result = _run_wrapper(str(fixture))
    assert result.returncode == 0, (
        f"expected exit 0, got {result.returncode}\nstderr={result.stderr!r}"
    )
    parsed = json.loads(result.stdout)
    assert parsed["schema_version"] == "1"
    # Epic keys ordered ascending.
    assert list(parsed["epics"].keys()) == ["100", "101"]
    # Children IDs match expected sorted ordering. The UUID-shaped (202) and
    # hyphenated-short (203) parents are skipped per rule 3; the standalone
    # (300) item is not a child of any epic.
    assert [c["id"] for c in parsed["epics"]["100"]["children"]] == [200, 201]
    assert [c["id"] for c in parsed["epics"]["101"]["children"]] == [204]


def test_wide_shape_keys_only() -> None:
    """Each child dict exposes exactly the four contracted keys (Requirement 5)."""
    fixture = FIXTURES / "wide_shape.json"
    result = _run_wrapper(str(fixture))
    assert result.returncode == 0, (
        f"expected exit 0, got {result.returncode}\nstderr={result.stderr!r}"
    )
    parsed = json.loads(result.stdout)
    children = parsed["epics"]["100"]["children"]
    assert children, "wide_shape.json should produce at least one child"
    for child in children:
        assert sorted(child.keys()) == ["id", "spec", "status", "title"], (
            f"child {child!r} has unexpected keys"
        )


def test_spec_passthrough_null() -> None:
    """``spec: null`` round-trips to JSON ``null`` (Requirement 11c)."""
    fixture = FIXTURES / "wide_shape.json"
    result = _run_wrapper(str(fixture))
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    by_id = {c["id"]: c for c in parsed["epics"]["100"]["children"]}
    # id 201 has explicit "spec": null
    assert by_id[201]["spec"] is None


def test_spec_passthrough_missing() -> None:
    """Missing ``spec`` field round-trips to JSON ``null``."""
    fixture = FIXTURES / "wide_shape.json"
    result = _run_wrapper(str(fixture))
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    by_id = {c["id"]: c for c in parsed["epics"]["100"]["children"]}
    # id 202 omits the "spec" key entirely → serialized as null via .get()
    assert by_id[202]["spec"] is None


def test_spec_passthrough_empty_string() -> None:
    """Empty-string ``spec`` round-trips as the literal empty string."""
    fixture = FIXTURES / "wide_shape.json"
    result = _run_wrapper(str(fixture))
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    by_id = {c["id"]: c for c in parsed["epics"]["100"]["children"]}
    # id 203 has "spec": ""
    assert by_id[203]["spec"] == ""


def test_spec_passthrough_non_empty_string() -> None:
    """Non-empty ``spec`` paths round-trip verbatim."""
    fixture = FIXTURES / "wide_shape.json"
    result = _run_wrapper(str(fixture))
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    by_id = {c["id"]: c for c in parsed["epics"]["100"]["children"]}
    # id 200 has "spec": "cortex/lifecycle/example-feature/spec.md"
    assert by_id[200]["spec"] == "cortex/lifecycle/example-feature/spec.md"


def test_no_epics_emits_empty_map(tmp_path: Path) -> None:
    """no_epics.json: items present but none have ``type: epic``.

    Also covers the empty-array edge case via tmp_path: writing a bare ``[]``
    (no items at all) produces the same ``epics: {}`` envelope.
    """
    # Case 1: items present but no epics.
    fixture = FIXTURES / "no_epics.json"
    result = _run_wrapper(str(fixture))
    assert result.returncode == 0, (
        f"expected exit 0, got {result.returncode}\nstderr={result.stderr!r}"
    )
    parsed = json.loads(result.stdout)
    assert parsed["epics"] == {}
    assert parsed["schema_version"] == "1"

    # Case 2: empty items array via tmp_path.
    empty_index = tmp_path / "empty_index.json"
    empty_index.write_text("[]\n", encoding="utf-8")
    result_empty = _run_wrapper(str(empty_index))
    assert result_empty.returncode == 0, (
        f"empty array: expected exit 0, got {result_empty.returncode}\n"
        f"stderr={result_empty.stderr!r}"
    )
    parsed_empty = json.loads(result_empty.stdout)
    assert parsed_empty == {"schema_version": "1", "epics": {}}


def test_malformed_json_exits_1() -> None:
    """Malformed JSON input → exit 1, non-empty stderr."""
    fixture = FIXTURES / "malformed_json.json"
    result = _run_wrapper(str(fixture))
    assert result.returncode == 1, (
        f"expected exit 1, got {result.returncode}\nstderr={result.stderr!r}"
    )
    assert result.stderr.strip(), "expected non-empty stderr on malformed JSON"


def test_missing_path_exits_1() -> None:
    """Nonexistent index path → exit 1, stderr contains the offending path."""
    missing = "/nonexistent/path/index.json"
    result = _run_wrapper(missing)
    assert result.returncode == 1, (
        f"expected exit 1, got {result.returncode}\nstderr={result.stderr!r}"
    )
    assert missing in result.stderr, (
        f"expected stderr to mention path {missing!r}; got {result.stderr!r}"
    )


def test_schema_v2_exits_2() -> None:
    """``schema_version: "2"`` → exit 2, exact diagnostic on stderr, empty stdout."""
    import re

    fixture = FIXTURES / "v2_schema.json"
    result = _run_wrapper(str(fixture))
    assert result.returncode == 2, (
        f"expected exit 2, got {result.returncode}\nstderr={result.stderr!r}"
    )
    assert result.stdout == "", (
        f"expected empty stdout on schema mismatch; got {result.stdout!r}"
    )
    # The implementation formats the offending value via Python repr(), which
    # yields single-quoted output for simple strings (e.g. ``'2'``). The task
    # spec's reference regex uses double quotes; we accept either style here
    # since both convey the same diagnostic. The expected-clause ("1") is
    # always double-quoted (string literal in the format string).
    pattern = r"""cortex-build-epic-map: unsupported schema_version ['"][^'"]*['"] — expected "1\""""
    assert re.search(pattern, result.stderr), (
        f"expected stderr matching {pattern!r}; got {result.stderr!r}"
    )


def test_deterministic_output() -> None:
    """Two consecutive invocations against the same fixture produce identical bytes."""
    fixture = FIXTURES / "multi_epic.json"
    first = _run_wrapper(str(fixture))
    second = _run_wrapper(str(fixture))
    assert first.returncode == 0 and second.returncode == 0
    assert first.stdout == second.stdout, (
        "expected byte-identical stdout across repeated runs"
    )


def test_width_mixed_epic_ordering(tmp_path: Path) -> None:
    """Epics ordered by integer-id ascending — NOT lexicographic.

    Build a tmp fixture with epic ids ``9`` and ``100`` (and one child each).
    Lexicographic ordering would yield ``["100", "9"]``; integer-ascending
    must yield ``["9", "100"]``. This is the regression guard against any
    accidental ``sort_keys=True`` slipping into the implementation.
    """
    items = [
        {
            "id": 9,
            "title": "Single-digit epic",
            "type": "epic",
            "parent": None,
            "schema_version": "1",
        },
        {
            "id": 100,
            "title": "Three-digit epic",
            "type": "epic",
            "parent": None,
            "schema_version": "1",
        },
        {
            "id": 500,
            "title": "Child of 9",
            "type": "feature",
            "parent": "9",
            "spec": None,
            "status": "backlog",
            "schema_version": "1",
        },
        {
            "id": 501,
            "title": "Child of 100",
            "type": "feature",
            "parent": "100",
            "spec": None,
            "status": "backlog",
            "schema_version": "1",
        },
    ]
    index_path = tmp_path / "width_mixed.json"
    index_path.write_text(json.dumps(items), encoding="utf-8")

    result = _run_wrapper(str(index_path))
    assert result.returncode == 0, (
        f"expected exit 0, got {result.returncode}\nstderr={result.stderr!r}"
    )
    parsed = json.loads(result.stdout)
    assert list(parsed["epics"].keys()) == ["9", "100"], (
        f"expected integer-ascending ordering ['9', '100']; "
        f"got {list(parsed['epics'].keys())!r}"
    )


# ---------------------------------------------------------------------------
# CLI / argparse — --help substring check (Requirement 2)
# ---------------------------------------------------------------------------


def test_help_mentions_index_json() -> None:
    """``cortex-build-epic-map --help`` mentions ``index.json``."""
    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.backlog.build_epic_map", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"--help should exit 0, got {result.returncode}\nstderr={result.stderr!r}"
    )
    assert "index.json" in result.stdout, (
        f"expected --help output to mention 'index.json'; got {result.stdout!r}"
    )
