"""Classifier-validation pytest for /cortex-core:critical-review V2 prompts.

Marked @pytest.mark.slow — invokes live models. Opt in via --run-slow.

Pass criterion is read from tests/fixtures/critical-review/baseline-stability.json
(written by tests/baseline_critical_review.py). Default: 3-of-3.
"""

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "critical-review" / "baseline-stability.json"
SKILL_MD_PATH = REPO_ROOT / "skills" / "critical-review" / "SKILL.md"

# Stub artifact used to ground the synthesizer prompt's "{artifact content}" reference.
# Minimal but coherent — a small spec fragment with one concrete claim a reviewer
# could plausibly tag at A-class.
STUB_ARTIFACT = """\
# Plan: Disable retry on payment endpoint timeouts

## Change
Set `retries=0` in the payment client constructor in `client.py:88` so that
timed-out payment requests fail fast instead of being retried.

## Rationale
Retries on timeout cause duplicate charges when the upstream gateway
eventually completes the original request after the client has already
retried. Failing fast surfaces the timeout to the caller, who can
decide whether to retry idempotently.

## Acceptance
- Payment client no longer retries on timeout.
- Existing retry behavior for non-payment clients is preserved.
"""


def _load_pass_criterion():
    """Read pass_criterion_recommendation from baseline-stability.json. Default 3-of-3."""
    if not BASELINE_PATH.exists():
        return "3-of-3"
    data = json.loads(BASELINE_PATH.read_text())
    return data.get("pass_criterion_recommendation", "3-of-3")


def _run_critical_review(fixture_path):
    """Invoke `claude -p '/critical-review {fixture_path}'` and return its synthesis output."""
    proc = subprocess.run(
        ["claude", "-p", f"/cortex-core:critical-review {fixture_path}"],
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


def _evaluate_weak_argument_downgrade(synthesis, meta=None):
    """Weak-argument-downgrade pass: synthesis emits an A→B reclassification note.

    The fixture is calibrated so reviewers plausibly raise an A-class finding
    whose strongest honest fix_invalidation_argument hits a downgrade trigger
    (adjacent issue without straddle_rationale). The synthesizer rubric should
    fire and emit the standard reclassification phrase.
    """
    if re.search(r're-classified finding \d+ from A→B', synthesis):
        return True, "pass"
    if "A→B" in synthesis:
        return True, "pass (substring)"
    return False, "no A→B reclassification note found in synthesis"


@pytest.mark.slow
def test_weak_argument_downgrade():
    """2-of-3: weak-argument fixture must produce an A→B reclassification note (R6).

    Uses 2-of-3 tolerance directly per spec R6 — not the global baseline
    criterion — because reviewer-side field-inclusion variance is expected.
    """
    fixture = REPO_ROOT / "tests" / "fixtures" / "critical-review" / "weak_argument_downgrade.md"
    assert fixture.exists(), f"missing fixture {fixture}"
    results = _run_n_times(str(fixture), _evaluate_weak_argument_downgrade)
    overall, summary = _apply_pass_criterion(results, "2-of-3")
    assert overall, f"weak_argument_downgrade classifier validation failed under 2-of-3: {summary}; details: {results}"


def _extract_synthesizer_template():
    """Extract the Step 2d Opus Synthesis prompt template from SKILL.md.

    Uses header-anchored search (NOT line numbers — line numbers shift after edits).
    Finds the `### Step 2d: Opus Synthesis` heading, then the first `---` line
    after it (start of template), then the next `---` line (end of template).
    """
    skill_md = SKILL_MD_PATH.read_text()
    header_match = re.search(r'^### Step 2d: Opus Synthesis\s*$', skill_md, re.MULTILINE)
    assert header_match, "Step 2d: Opus Synthesis header not found in SKILL.md"
    after_header = skill_md[header_match.end():]
    delims = list(re.finditer(r'^---\s*$', after_header, re.MULTILINE))
    assert len(delims) >= 2, (
        "expected at least 2 '---' delimiters after Step 2d header; "
        f"found {len(delims)}"
    )
    template = after_header[delims[0].end():delims[1].start()].strip("\n")
    return template


@pytest.mark.slow
def test_synthesizer_rubric_deterministic():
    """Deterministic synthesizer-rubric test (R7).

    Bypasses reviewer dispatch entirely — extracts the Step 2d synthesizer prompt
    template from SKILL.md, substitutes a stub artifact and a hand-crafted
    reviewer-output JSON envelope (one A-class finding with a deliberately weak
    `fix_invalidation_argument`), invokes `claude -p '<assembled prompt>' --model
    opus`, and asserts the response contains the A→B reclassification note.

    This decouples rubric verification from reviewer-side stochasticity.
    Single live model invocation; no 2-of-3 tolerance.
    """
    template = _extract_synthesizer_template()

    # Sentinel substring assertion — converts silent skew to loud failure if
    # SKILL.md is restructured. The task spec named
    # "After all parallel reviewer agents from Step 2c complete" but that
    # phrase lives in the prose intro BEFORE the `---` delimiter (line 186 of
    # SKILL.md), not in the extracted template body. The intent is to detect
    # extraction skew, so we use the unique opener of the template body
    # ("You are synthesizing findings from multiple independent adversarial
    # reviewers") which is present only in Step 2d's template.
    sentinel = "You are synthesizing findings from multiple independent adversarial reviewers"
    assert sentinel in template, (
        "synthesizer template extraction failed — anchor mismatch in SKILL.md"
    )

    # Hand-crafted reviewer JSON: one A-class finding with empty
    # `fix_invalidation_argument` (trigger 1 — absent/empty) — unambiguously
    # fires the rubric.
    reviewer_envelope = {
        "angle": "fragile assumptions",
        "findings": [
            {
                "class": "A",
                "finding": (
                    "The plan assumes setting `retries=0` is sufficient to disable "
                    "retry behavior on timeout for the payment client."
                ),
                "evidence_quote": (
                    "Set `retries=0` in the payment client constructor in "
                    "`client.py:88` so that timed-out payment requests fail fast "
                    "instead of being retried."
                ),
                "fix_invalidation_argument": "",
            }
        ],
    }
    reviewer_json = json.dumps(reviewer_envelope, indent=2)

    # Regex substitution — naive .replace() against bare placeholder names
    # would silently no-op because the actual placeholders include descriptive
    # clauses (em-dash for the long form). str.format() cannot be used because
    # the Output Format section contains literal JSON braces.
    assembled = re.sub(
        r'\{artifact content\}', lambda _m: STUB_ARTIFACT, template, count=1
    )
    assembled = re.sub(
        r'\{all reviewer findings[^}]*\}', lambda _m: reviewer_json, assembled, count=1
    )

    # Post-substitution assertion — catches placeholder-name drift loudly.
    assert "{artifact content}" not in assembled, (
        "regex substitution failed: {artifact content} placeholder still present"
    )
    assert "{all reviewer findings" not in assembled, (
        "regex substitution failed: {all reviewer findings ...} placeholder still present"
    )

    # Invoke claude -p directly with the assembled prompt — bypasses reviewer
    # dispatch entirely. Modeled after _run_critical_review above.
    proc = subprocess.run(
        ["claude", "-p", assembled, "--model", "opus"],
        capture_output=True, text=True, timeout=600,
    )
    stdout = proc.stdout
    assert proc.returncode == 0, (
        f"claude -p exited {proc.returncode}; stderr: {proc.stderr[:500]}"
    )

    # Pass assertion: synthesizer emits the A→B reclassification note.
    match = re.search(r're-classified finding \d+ from A→B', stdout)
    assert match, (
        "synthesizer did not emit A→B reclassification note for weak-argument "
        f"finding; stdout (first 2000 chars):\n{stdout[:2000]}"
    )
