"""Golden-file replay tests for the cortex-scan-lifecycle SessionStart hook.

Task 1 deliverable: this module is the *skeleton* established alongside the
captured golden fixtures under ``tests/fixtures/hooks/scan_lifecycle/``.
Each ``test_golden_<case>_additionalContext`` stub asserts the byte-for-byte
``hookSpecificOutput.additionalContext`` substring against the corresponding
``<case>.expected.additionalContext.txt`` fixture.

The stubs are wired but skipped here — Task 14 lights them up by replaying
the same fixtures through the new ``cortex hooks scan-lifecycle`` Python
subcommand (not yet implemented at Task-1 commit time).

Fixture cases per spec req #2:
  (a) no lifecycle dir
  (b) single incomplete feature
  (c) multiple incomplete features
  (d) post-/clear session migration
  (e) Morning Review active
  (f) pipeline-state with executing/paused/failed features

The literal token ``__NO_OUTPUT__`` (on its own line) in an
``.expected.additionalContext.txt`` represents "hook emitted no JSON
envelope" — i.e. an empty stdout from the wrapper / subcommand. Any other
content is asserted as a byte-equivalent additionalContext match.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests._hook_fixture_helpers import (
    fixture_expected_path,
    fixture_input_path,
)


CASES = (
    "a_no_lifecycle_dir",
    "b_single_incomplete_feature",
    "c_multiple_incomplete_features",
    "d_post_clear_session_migration",
    "e_morning_review_active",
    "f_pipeline_state_with_statuses",
)


NO_OUTPUT_SENTINEL = "__NO_OUTPUT__\n"


def _load_fixture_pair(case: str) -> tuple[dict, str]:
    """Return ``(input_payload, expected_additional_context_or_sentinel)``.

    The input payload's ``cwd`` field still holds the ``__TMPDIR__``
    placeholder — replay code must substitute it for a real staged repo
    path before feeding stdin to the hook / subcommand.
    """
    in_path = fixture_input_path(case)
    expected_path = fixture_expected_path(case)
    payload = json.loads(in_path.read_text(encoding="utf-8"))
    expected = expected_path.read_text(encoding="utf-8")
    return payload, expected


# ----------------------------------------------------------------------------
# Golden-file replay stubs (Task 14 implements the body)
# ----------------------------------------------------------------------------


@pytest.mark.skip(
    reason="Task 14 implements replay against cortex hooks scan-lifecycle"
)
def test_golden_a_no_lifecycle_dir_additionalContext() -> None:
    payload, expected = _load_fixture_pair("a_no_lifecycle_dir")
    # Expected to assert no stdout (NO_OUTPUT sentinel).
    assert payload is not None
    assert expected == NO_OUTPUT_SENTINEL


@pytest.mark.skip(
    reason="Task 14 implements replay against cortex hooks scan-lifecycle"
)
def test_golden_b_single_incomplete_feature_additionalContext() -> None:
    payload, expected = _load_fixture_pair("b_single_incomplete_feature")
    assert payload is not None
    assert expected and expected != NO_OUTPUT_SENTINEL


@pytest.mark.skip(
    reason="Task 14 implements replay against cortex hooks scan-lifecycle"
)
def test_golden_c_multiple_incomplete_features_additionalContext() -> None:
    payload, expected = _load_fixture_pair("c_multiple_incomplete_features")
    assert payload is not None
    assert expected and expected != NO_OUTPUT_SENTINEL


@pytest.mark.skip(
    reason="Task 14 implements replay against cortex hooks scan-lifecycle"
)
def test_golden_d_post_clear_session_migration_additionalContext() -> None:
    payload, expected = _load_fixture_pair("d_post_clear_session_migration")
    assert payload is not None
    assert expected and expected != NO_OUTPUT_SENTINEL


@pytest.mark.skip(
    reason="Task 14 implements replay against cortex hooks scan-lifecycle"
)
def test_golden_e_morning_review_active_additionalContext() -> None:
    payload, expected = _load_fixture_pair("e_morning_review_active")
    assert payload is not None
    assert expected and expected != NO_OUTPUT_SENTINEL


@pytest.mark.skip(
    reason="Task 14 implements replay against cortex hooks scan-lifecycle"
)
def test_golden_f_pipeline_state_with_statuses_additionalContext() -> None:
    payload, expected = _load_fixture_pair("f_pipeline_state_with_statuses")
    assert payload is not None
    assert expected and expected != NO_OUTPUT_SENTINEL


# ----------------------------------------------------------------------------
# Meta-test: every CASE has both a fixture pair on disk
# ----------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES)
def test_fixture_pair_present(case: str) -> None:
    in_path = fixture_input_path(case)
    expected_path = fixture_expected_path(case)
    assert in_path.is_file(), f"missing input fixture: {in_path}"
    assert expected_path.is_file(), f"missing expected fixture: {expected_path}"
    # Non-empty invariant (per Task 1 verification).
    assert expected_path.stat().st_size > 0, (
        f"expected fixture is empty: {expected_path}"
    )


def test_all_six_cases_enumerated() -> None:
    """Guard: the CASES tuple covers all six spec-req-#2 cases (a-f)."""
    assert len(CASES) == 6
    prefixes = sorted({c.split("_", 1)[0] for c in CASES})
    assert prefixes == ["a", "b", "c", "d", "e", "f"]
