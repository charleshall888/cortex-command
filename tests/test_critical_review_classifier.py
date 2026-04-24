"""Classifier-validation pytest for /cortex:critical-review V2 prompts.

Marked @pytest.mark.slow — invokes live models. Opt in via --run-slow.

Pass criterion is read from tests/fixtures/critical-review/baseline-stability.json
(written by tests/baseline_critical_review.py). Default: 3-of-3.
"""

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "critical-review" / "baseline-stability.json"


def _load_pass_criterion():
    """Read pass_criterion_recommendation from baseline-stability.json. Default 3-of-3."""
    if not BASELINE_PATH.exists():
        return "3-of-3"
    data = json.loads(BASELINE_PATH.read_text())
    return data.get("pass_criterion_recommendation", "3-of-3")


def _run_critical_review(fixture_path):
    """Invoke `claude -p '/critical-review {fixture_path}'` and return its synthesis output."""
    proc = subprocess.run(
        ["claude", "-p", f"/cortex:critical-review {fixture_path}"],
        capture_output=True, text=True, timeout=600,
    )
    return proc.stdout, proc.returncode


def _evaluate_pure_b(synthesis):
    """Pure-B pass: zero A-class findings AND no 'blocks'/'invalidates' verbs in synthesis."""
    if '"class": "A"' in synthesis:
        return False, "found A-class findings (expected zero)"
    if "blocks" in synthesis or "invalidates" in synthesis:
        return False, "synthesis contains blocks/invalidates verbs (verdict-framing leak)"
    return True, "pass"


def _evaluate_straddle(synthesis, meta):
    """Straddle pass: exactly 1 A-class + exactly 1 B-class finding matching named concerns."""
    a_count = synthesis.count('"class": "A"')
    b_count = synthesis.count('"class": "B"')
    if a_count != 1:
        return False, f"expected 1 A-class finding, got {a_count}"
    if b_count != 1:
        return False, f"expected 1 B-class finding, got {b_count}"
    a_concern = next((c for c in meta["concerns"] if c["expected_class"] == "A"), None)
    b_concern = next((c for c in meta["concerns"] if c["expected_class"] == "B"), None)
    a_anchor = a_concern["description"].split(".")[0][:40] if a_concern else ""
    b_anchor = b_concern["description"].split(".")[0][:40] if b_concern else ""
    if a_anchor and a_anchor not in synthesis:
        return False, f"A-concern anchor '{a_anchor}' not found in synthesis"
    if b_anchor and b_anchor not in synthesis:
        return False, f"B-concern anchor '{b_anchor}' not found in synthesis"
    return True, "pass"


def _check_reviewer_survival(synthesis):
    """Pass requires reviewers.completed == reviewers.dispatched. Reads from residue
    file if a lifecycle context is active, else from operator output prefix.
    Returns (survived: bool, reason: str)."""
    # In subprocess context the spawned `claude` may not have a lifecycle, so check
    # operator-output prefix for the partial-coverage notice. Absence of "N of M
    # reviewer angles completed." is taken as full survival.
    if "reviewer angles completed" in synthesis and "of" in synthesis.split("reviewer angles completed")[0]:
        return False, "partial reviewer coverage detected"
    return True, "no partial-coverage notice"


def _run_n_times(fixture_path, evaluator, meta=None, max_attempts=4):
    """Run N times with one retry on transient partial-coverage failure.
    Returns list of (passed: bool, reason: str)."""
    n = 3  # default 3-of-3
    results = []
    retried = False
    for i in range(n):
        synthesis, rc = _run_critical_review(fixture_path)
        if rc != 0:
            results.append((False, f"exit {rc}"))
            continue
        survived, survival_reason = _check_reviewer_survival(synthesis)
        if not survived and not retried:
            # Single retry on transient reviewer failure
            retried = True
            synthesis, rc = _run_critical_review(fixture_path)
            if rc != 0:
                results.append((False, f"retry exit {rc}"))
                continue
            survived, survival_reason = _check_reviewer_survival(synthesis)
        if not survived:
            # Distinguish "prompt broken" from "transient reviewer failure"
            results.append((False, f"reviewer survival failure: {survival_reason}"))
            continue
        passed, reason = evaluator(synthesis, meta) if meta else evaluator(synthesis)
        results.append((passed, reason))
    return results


def _apply_pass_criterion(results, criterion):
    """Apply pass criterion to per-run results. Returns (overall_pass, summary)."""
    passed = sum(1 for r, _ in results if r)
    total = len(results)
    if criterion == "3-of-3":
        return passed == total, f"{passed}/{total} (need {total}/{total})"
    if criterion == "2-of-3":
        return passed >= (total + 1) // 2 + (total % 2 == 0), f"{passed}/{total} (need majority)"
    if criterion == "escalate":
        pytest.skip("baseline-stability escalated — full prompt revision needed before classifier validation")
    return False, f"unknown criterion {criterion}"


@pytest.mark.slow
def test_pure_b_aggregation_named_concern_to_class():
    """3-of-3: pure-B fixture must produce zero A-class findings AND no verdict-framing verbs."""
    fixture = REPO_ROOT / "tests" / "fixtures" / "critical-review" / "pure_b_aggregation.md"
    assert fixture.exists(), f"missing fixture {fixture}"
    results = _run_n_times(str(fixture), _evaluate_pure_b)
    criterion = _load_pass_criterion()
    overall, summary = _apply_pass_criterion(results, criterion)
    assert overall, f"pure_b classifier validation failed under {criterion}: {summary}; details: {results}"


@pytest.mark.slow
def test_straddle_case_named_concern_to_class():
    """3-of-3: straddle fixture must produce exactly 1 A-class + 1 B-class matching named concerns."""
    fixture = REPO_ROOT / "tests" / "fixtures" / "critical-review" / "straddle_case.md"
    meta_path = REPO_ROOT / "tests" / "fixtures" / "critical-review" / "straddle_case.meta.json"
    assert fixture.exists(), f"missing fixture {fixture}"
    assert meta_path.exists(), f"missing meta {meta_path}"
    meta = json.loads(meta_path.read_text())
    results = _run_n_times(str(fixture), _evaluate_straddle, meta=meta)
    criterion = _load_pass_criterion()
    overall, summary = _apply_pass_criterion(results, criterion)
    assert overall, f"straddle classifier validation failed under {criterion}: {summary}; details: {results}"
