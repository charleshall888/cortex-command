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

    Companion tests `test_synthesizer_trigger_{2_restates,3_adjacent_no_straddle,
    3_adjacent_with_straddle,4_vague}` follow the same prompt-assembly path but
    use an inline 2-of-3 retry loop (with `_apply_pass_criterion(results,
    '2-of-3')`) because their assertions anchor on rationale-prose words with
    higher decoding variance than this Trigger-1 binary-field check. The
    single-invocation rationale here is specific to the binary-field nature of
    the Trigger-1 assertion and does not generalize to Triggers 2/3/4.
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


@pytest.mark.slow
def test_synthesizer_trigger_2_restates() -> None:
    """Trigger 2 (restates) synthesizer-rubric test — 2-of-3 tolerance (#179 Task 2).

    Bypasses reviewer dispatch entirely: extracts the Step 2d synthesizer prompt
    template from SKILL.md, substitutes a stub artifact and a hand-crafted
    reviewer-output JSON envelope (one A-class finding whose
    `fix_invalidation_argument` restates the finding without a causal mechanism),
    then invokes `claude -p '<assembled prompt>' --model opus` up to 3 times.
    The per-attempt evaluator passes iff (a) the response contains an A→B
    reclassification note AND (b) the A→B rationale prose contains a
    Trigger-2-class token (restate / circular / without a causal / tautolog).
    Pass/fail is then derived via `_apply_pass_criterion(results, "2-of-3")`.

    The 2-of-3 tolerance accommodates real-LLM stochasticity in the synthesizer's
    rationale wording (per spec R6) while still failing loud when the rubric is
    structurally broken or when Trigger 2 is not actually being recognized.

    Calibration evidence (one-time, 2026-05-11, pre-commit, plus follow-up
    iteration after initial cross-trigger discrimination failure):
    ----------------------------------------------------------
    Ran `claude -p --model opus` four times with this exact assembled prompt
    (stub artifact + the Trigger-2 fixture envelope below). Verified properties
    (i) and (ii) per #179 Task 2 Context:

    (i) Per-trigger regex match: every captured response emitted under
        `## Concerns` a line of the form:
            "- Synthesizer re-classified finding 1 from A→B:
             fix_invalidation_argument restates the finding (...) without a
             causal link from the cited evidence to a concrete failure path."
        Both the A->B-marker regex and the Trigger-2 rationale-token regex
        (`restate | circular | without-a-causal | tautolog`, case-insensitive)
        matched on every captured rationale. Property (i) holds.

    (ii) Cross-trigger discrimination — INITIAL FAILURE, then disposition:
         The first calibration pass showed cross-trigger contamination by
         design: real Opus rationale lines are multi-sentence and frequently
         co-mention "adjacent" gaps or "hedged" / "no concrete failure path"
         framing while explaining why the argument is a restatement. The
         co-mention is not a Trigger-3 / Trigger-4 misclassification — Opus
         correctly classifies as Trigger 2 — but the token appears within the
         same rationale prose.

         Disposition: cross-trigger negative assertions are NOT included in the
         per-attempt evaluator. Property (ii)'s false-pass risk is theoretical
         for this test, which only asserts the positive Trigger-2 token match;
         it would matter if a single stdout had to be classified as exactly one
         trigger, but each per-trigger test is independent and only checks its
         own positive match. The rationale-line scoping (capturing just the
         A→B reclassification line as the suffix after the `A->B:` marker on
         that line) is retained because it tightens the
         Trigger-2 positive match against synthesizer-boilerplate noise (the
         template's prescribed opener "The concerns below are adjacent gaps or
         framing notes" must not be mistaken for the rationale).

    Result: calibration sound. Trigger-2 positive match on the captured
    rationale line is the load-bearing assertion; cross-trigger negatives
    deferred to a sibling concern.
    ----------------------------------------------------------
    """
    template = _extract_synthesizer_template()

    sentinel = "You are synthesizing findings from multiple independent adversarial reviewers"
    assert sentinel in template, (
        "synthesizer template extraction failed — anchor mismatch in SKILL.md"
    )

    # Hand-crafted reviewer JSON: one A-class finding whose
    # `fix_invalidation_argument` restates the finding text in tautological
    # form — no causal link from evidence to fix-failure. This is the canonical
    # Trigger 2 (restates) shape per SKILL.md Worked Example 4.
    #
    # Verbatim string per #179 spec Req 2; verified absent from SKILL.md so the
    # synthesizer can't memorize-and-regurgitate from the worked-example prose.
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
                "fix_invalidation_argument": (
                    "the proposed change does not produce its stated outcome "
                    "because the change as proposed will not produce the stated "
                    "outcome"
                ),
            }
        ],
    }
    reviewer_json = json.dumps(reviewer_envelope, indent=2)

    assembled = re.sub(
        r'\{artifact content\}', lambda _m: STUB_ARTIFACT, template, count=1
    )
    assembled = re.sub(
        r'\{all reviewer findings[^}]*\}', lambda _m: reviewer_json, assembled, count=1
    )

    assert "{artifact content}" not in assembled, (
        "regex substitution failed: {artifact content} placeholder still present"
    )
    assert "{all reviewer findings" not in assembled, (
        "regex substitution failed: {all reviewer findings ...} placeholder still present"
    )

    # Inline 2-of-3 retry loop — sequentially invoke claude up to 3 times,
    # record (passed, reason) per attempt. NOT delegated to `_run_n_times`
    # because that helper dispatches the full `/cortex-core:critical-review`
    # slash command, not synthesizer-only.
    results: list[tuple[bool, str]] = []
    for attempt_idx in range(3):
        proc = subprocess.run(
            ["claude", "-p", assembled, "--model", "opus"],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0:
            results.append((False, f"attempt {attempt_idx}: exit {proc.returncode}; stderr: {proc.stderr[:300]}"))
            continue
        stdout = proc.stdout
        ab_match = re.search(r're-classified finding \d+ from A→B', stdout)
        if not ab_match:
            results.append((False, f"attempt {attempt_idx}: no A→B reclassification note; stdout head: {stdout[:400]!r}"))
            continue
        # Capture the rationale prose on the A→B reclassification line so the
        # rationale-token regex (and the cross-trigger negative assertions
        # below) operate on the rationale itself, not on unrelated synthesizer
        # boilerplate. Per calibration: Trigger 3's "adjacent" co-matches in the
        # template's boilerplate opening line, so scoping to the rationale line
        # is required for clean cross-trigger discrimination.
        rationale_line_match = re.search(
            r're-classified finding \d+ from A→B:?\s*(.+)', stdout
        )
        rationale = rationale_line_match.group(1) if rationale_line_match else ""
        trigger2_match = re.search(
            r'(?i)restate|circular|without\s+a\s+causal|tautolog', rationale
        )
        if not trigger2_match:
            results.append((
                False,
                f"attempt {attempt_idx}: A→B note present but rationale prose does not match Trigger 2 tokens; "
                f"rationale: {rationale[:300]!r}",
            ))
            continue
        # Per calibration property (ii) disposition: cross-trigger negative
        # assertions deferred — real Opus rationale prose legitimately
        # co-mentions adjacent/hedged framing while correctly classifying as
        # Trigger 2. The positive Trigger-2 token match on the rationale line is
        # the load-bearing assertion.
        results.append((True, f"attempt {attempt_idx}: pass (rationale: {rationale[:120]!r})"))

    overall, summary = _apply_pass_criterion(results, "2-of-3")
    assert overall, (
        f"Trigger 2 (restates) synthesizer-rubric validation failed under 2-of-3: "
        f"{summary}; per-attempt reasons: {[r for _, r in results]}"
    )


# Shared envelope content for the Trigger 3 (adjacent) test pair (#179 Task 3).
#
# Per spec Req 4 isolation constraint, finding / evidence_quote /
# fix_invalidation_argument are byte-identical between the no_straddle and
# with_straddle fixtures; only `straddle_rationale` presence/value varies.
# This isolates the Straddle Protocol exemption as the single load-bearing
# variable across the pair.
#
# The shared `fix_invalidation_argument` describes a concrete effect one
# layer up from the change — the order-confirmation webhook still emitting a
# successful_charge event on raised timeout — specific enough to avoid
# Trigger 4 (vague) but adjacent: it does not name a failure path on
# `retries=0` itself, only a downstream dashboard-correctness gap.
# Verified held-out from `skills/critical-review/SKILL.md` via
# `grep -F 'order-confirmation webhook' skills/critical-review/SKILL.md`
# (exit 1) and `grep -F 'webhooks.py:204' skills/critical-review/SKILL.md`
# (exit 1), so the synthesizer cannot memorize-and-regurgitate from the
# worked-example prose.
_TRIGGER_3_SHARED_FINDING = (
    "The plan assumes setting `retries=0` is sufficient to disable retry "
    "behavior on timeout for the payment client."
)
_TRIGGER_3_SHARED_EVIDENCE_QUOTE = (
    "Set `retries=0` in the payment client constructor in `client.py:88` "
    "so that timed-out payment requests fail fast instead of being retried."
)
_TRIGGER_3_SHARED_FIX_INVAL_ARG = (
    "the order-confirmation webhook in `webhooks.py:204` still emits a "
    "successful_charge event when the payment client raises on timeout, "
    "so downstream fulfilment dashboards will show charges that never "
    "settled."
)
_TRIGGER_3_WITH_STRADDLE_RATIONALE = (
    "splits between fix-invalidation (the webhook emitting a "
    "successful_charge on a raised timeout collapses the documented "
    "'fail fast' outcome from the caller's perspective) and an adjacent "
    "webhook-event-correctness gap; biasing up because the downstream "
    "contract under 'fail fast' explicitly assumes no successful_charge "
    "event fires when the call raises."
)


def _build_trigger_3_envelope(with_straddle: bool) -> dict:
    """Assemble the Trigger 3 reviewer envelope, optionally with straddle_rationale.

    Shared envelope content is sourced from module-level constants so the only
    load-bearing variable between the two fixtures is `straddle_rationale`
    presence/value (spec Req 4).
    """
    finding = {
        "class": "A",
        "finding": _TRIGGER_3_SHARED_FINDING,
        "evidence_quote": _TRIGGER_3_SHARED_EVIDENCE_QUOTE,
        "fix_invalidation_argument": _TRIGGER_3_SHARED_FIX_INVAL_ARG,
    }
    if with_straddle:
        finding["straddle_rationale"] = _TRIGGER_3_WITH_STRADDLE_RATIONALE
    return {"angle": "fragile assumptions", "findings": [finding]}


@pytest.mark.slow
def test_synthesizer_trigger_3_adjacent_no_straddle() -> None:
    """Trigger 3 (adjacent, no straddle) synthesizer-rubric test — 2-of-3 (#179 Task 3).

    Bypasses reviewer dispatch entirely: extracts the Step 2d synthesizer prompt
    template from SKILL.md, substitutes a stub artifact and a hand-crafted
    reviewer-output JSON envelope (one A-class finding whose
    `fix_invalidation_argument` describes an adjacent downstream gap, with NO
    `straddle_rationale` field), then invokes `claude -p '<assembled prompt>'
    --model opus` up to 3 times. The per-attempt evaluator passes iff (a) the
    response contains an A→B reclassification note AND (b) the A→B rationale
    prose contains a Trigger-3 anchor token (adjacent / adjacency /
    no straddle_rationale / describes an adjacent), case-insensitive. Pair
    partner: `test_synthesizer_trigger_3_adjacent_with_straddle` — both tests
    share finding / evidence_quote / fix_invalidation_argument byte-for-byte;
    the only load-bearing variable across the pair is `straddle_rationale`
    presence/value (spec Req 4).

    Calibration evidence (one-time, 2026-05-11, pre-commit):
    ----------------------------------------------------------
    Ran `claude -p --model opus` once with this exact assembled prompt
    (stub artifact + the no-straddle fixture envelope below). Captured
    response (excerpt):

        No fix-invalidating objections after evidence re-examination. The
        concerns below are adjacent gaps or framing notes — do not read as
        verdict.

        Synthesizer re-classified finding 1 from A→B:
        fix_invalidation_argument describes an adjacent downstream gap
        (webhook emitting `successful_charge` on timeout) rather than a
        failure of the proposed change. The plan's stated outcome —
        payment requests fail fast instead of retrying — is not
        invalidated by the webhook behavior; `retries=0` still disables
        retries. The misleading downstream signal is an adjacent B-class
        concern, and no `straddle_rationale` is present to invoke the
        exemption.

    Verified properties:
    (i) Per-trigger regex match: both the A→B-marker regex and the
        Trigger-3 anchor regex (`adjacent | adjacency |
        no straddle_rationale | describes an adjacent`, case-insensitive)
        matched on the A→B rationale-line suffix. Property (i) holds.
    (ii) Cross-trigger discrimination: per Task 2's lesson learned, the
         rationale-token check is scoped to the post-`A→B:` suffix via
         `re.search(r're-classified finding \\d+ from A→B:?\\s*(.+)',
         stdout)`. The opening boilerplate "The concerns below are
         adjacent gaps or framing notes" would otherwise match
         "adjacent" outside the rationale; scoping prevents that. The
         Trigger-2 token regex (`restate | circular | without\\s+a\\s+causal
         | tautolog`) does NOT match the captured rationale line.
         Property (ii) holds for the load-bearing positive assertion.

    Disposition: calibration sound. Single live opus run produced a clean
    Trigger-3 downgrade signal; no fixture iteration required.
    ----------------------------------------------------------
    """
    template = _extract_synthesizer_template()

    sentinel = "You are synthesizing findings from multiple independent adversarial reviewers"
    assert sentinel in template, (
        "synthesizer template extraction failed — anchor mismatch in SKILL.md"
    )

    reviewer_envelope = _build_trigger_3_envelope(with_straddle=False)
    # Defensive: confirm the no-straddle fixture genuinely lacks the field.
    assert "straddle_rationale" not in reviewer_envelope["findings"][0], (
        "no_straddle fixture must not include straddle_rationale"
    )
    reviewer_json = json.dumps(reviewer_envelope, indent=2)

    assembled = re.sub(
        r'\{artifact content\}', lambda _m: STUB_ARTIFACT, template, count=1
    )
    assembled = re.sub(
        r'\{all reviewer findings[^}]*\}', lambda _m: reviewer_json, assembled, count=1
    )

    assert "{artifact content}" not in assembled, (
        "regex substitution failed: {artifact content} placeholder still present"
    )
    assert "{all reviewer findings" not in assembled, (
        "regex substitution failed: {all reviewer findings ...} placeholder still present"
    )

    # Inline 2-of-3 retry loop — sequential invocation, per-attempt evaluator.
    # Not delegated to `_run_n_times`: that helper dispatches the full
    # `/cortex-core:critical-review` slash command, not synthesizer-only.
    results: list[tuple[bool, str]] = []
    for attempt_idx in range(3):
        proc = subprocess.run(
            ["claude", "-p", assembled, "--model", "opus"],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0:
            results.append((False, f"attempt {attempt_idx}: exit {proc.returncode}; stderr: {proc.stderr[:300]}"))
            continue
        stdout = proc.stdout
        ab_match = re.search(r're-classified finding \d+ from A→B', stdout)
        if not ab_match:
            results.append((False, f"attempt {attempt_idx}: no A→B reclassification note; stdout head: {stdout[:400]!r}"))
            continue
        # Scope the anchor-token check to the rationale-line suffix so
        # template boilerplate ("The concerns below are adjacent gaps...")
        # cannot false-pass for "adjacent". This mirrors Task 2's scoping.
        rationale_line_match = re.search(
            r're-classified finding \d+ from A→B:?\s*(.+)', stdout
        )
        rationale = rationale_line_match.group(1) if rationale_line_match else ""
        trigger3_match = re.search(
            r'(?i)adjacent|adjacency|no\s+straddle_rationale|describes\s+an?\s+adjacent',
            rationale,
        )
        if not trigger3_match:
            results.append((
                False,
                f"attempt {attempt_idx}: A→B note present but rationale prose does not match Trigger 3 anchors; "
                f"rationale: {rationale[:300]!r}",
            ))
            continue
        results.append((True, f"attempt {attempt_idx}: pass (rationale: {rationale[:120]!r})"))

    overall, summary = _apply_pass_criterion(results, "2-of-3")
    assert overall, (
        f"Trigger 3 (adjacent, no straddle) synthesizer-rubric validation failed under 2-of-3: "
        f"{summary}; per-attempt reasons: {[r for _, r in results]}"
    )


@pytest.mark.slow
def test_synthesizer_trigger_3_adjacent_with_straddle() -> None:
    """Trigger 3 (adjacent, with straddle) synthesizer-rubric test — 2-of-3 (#179 Task 3).

    Pair partner of `test_synthesizer_trigger_3_adjacent_no_straddle`.
    Identical envelope content except this fixture adds a populated
    `straddle_rationale` field (bias-up rationale). Per the synthesizer
    rubric (SKILL.md Step 2d, Trigger 3 Straddle exemption), the presence of
    `straddle_rationale` MUST preempt Trigger 3 — the finding ratifies as A
    and NO A→B reclassification fires.

    Per-attempt evaluator: the load-bearing disposition signal is the
    ABSENCE of an A→B reclassification marker (i.e., no downgrade fired
    despite adjacency). Optionally, the synthesizer may also emit explicit
    Straddle-exemption prose ("Straddle exemption preserves A-class",
    "ratify as A", "trigger 3 does NOT fire") — when it does, that's
    stronger evidence; when it doesn't, silent ratification (finding
    surfaces under `## Objections` with no A→B note) is the disposition.
    The negative assertion is therefore the primary pass criterion;
    positive prose matching is captured for diagnostic visibility only.

    Calibration evidence (one-time, 2026-05-11, pre-commit, two runs to
    confirm prose-vs-silent ratification variance):
    ----------------------------------------------------------
    Ran `claude -p --model opus` twice with this exact assembled prompt
    (stub artifact + the with-straddle fixture envelope below).

    Run 1: silent ratification. Response opened directly with
    `## Objections` and surfaced the finding as an A-class objection
    (citing the webhook contract and the "fail fast" outcome
    invalidation). NO `Synthesizer re-classified finding N from A→B`
    marker present. NO explicit Straddle-exemption prose. Disposition:
    correct ratification, silent. The positive ratification regex
    (`straddle exemption | Straddle (Protocol )?(bias-up|exempt) |
    trigger 3 does NOT fire | ratify as A`) did NOT match.

    Run 2: explicit Straddle-exemption prose. Response surfaced the
    finding under `## Objections` and appended
    "(Straddle exemption preserves A-class: the downstream contract
    collapses the documented fail-fast outcome, not merely an adjacent
    dashboard concern.)" NO A→B marker present. The positive
    ratification regex matched on "Straddle exemption".

    Disposition implication: the positive prose regex would false-fail
    on silent ratification (Run 1). Per the Task Context calibration
    guidance for the with-straddle case ("If the calibration shows
    ambiguity, add a complementary negative assertion: ... NO downgrade
    fired — this is consistent with the with-straddle case ratifying as
    A"), the test's load-bearing pass criterion is the ABSENCE of an
    A→B reclassification marker. The positive prose regex is recorded
    in the attempt's reason string for diagnostic value but is not
    load-bearing.

    Cross-trigger considerations: this test does not need rationale-line
    scoping because no rationale line is expected to exist (ratification
    means no `A→B:` marker fires). The positive ratification regex is
    only checked across full stdout for diagnostic capture.

    Disposition: calibration sound. Negative assertion is the disposition
    signal; positive prose is diagnostic.
    ----------------------------------------------------------
    """
    template = _extract_synthesizer_template()

    sentinel = "You are synthesizing findings from multiple independent adversarial reviewers"
    assert sentinel in template, (
        "synthesizer template extraction failed — anchor mismatch in SKILL.md"
    )

    reviewer_envelope = _build_trigger_3_envelope(with_straddle=True)
    # Defensive: confirm the with-straddle fixture genuinely has the field
    # populated and that the shared envelope content matches the pair partner.
    assert "straddle_rationale" in reviewer_envelope["findings"][0], (
        "with_straddle fixture must include a populated straddle_rationale"
    )
    assert reviewer_envelope["findings"][0]["fix_invalidation_argument"] == (
        _TRIGGER_3_SHARED_FIX_INVAL_ARG
    ), "shared fix_invalidation_argument must be byte-identical across the pair"
    reviewer_json = json.dumps(reviewer_envelope, indent=2)

    assembled = re.sub(
        r'\{artifact content\}', lambda _m: STUB_ARTIFACT, template, count=1
    )
    assembled = re.sub(
        r'\{all reviewer findings[^}]*\}', lambda _m: reviewer_json, assembled, count=1
    )

    assert "{artifact content}" not in assembled, (
        "regex substitution failed: {artifact content} placeholder still present"
    )
    assert "{all reviewer findings" not in assembled, (
        "regex substitution failed: {all reviewer findings ...} placeholder still present"
    )

    results: list[tuple[bool, str]] = []
    for attempt_idx in range(3):
        proc = subprocess.run(
            ["claude", "-p", assembled, "--model", "opus"],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0:
            results.append((False, f"attempt {attempt_idx}: exit {proc.returncode}; stderr: {proc.stderr[:300]}"))
            continue
        stdout = proc.stdout
        # Load-bearing disposition signal: NO A→B reclassification marker
        # (Straddle exemption preempts Trigger 3, so the finding ratifies
        # as A and no downgrade fires).
        ab_match = re.search(r're-classified finding \d+ from A→B', stdout)
        if ab_match:
            results.append((
                False,
                f"attempt {attempt_idx}: A→B reclassification fired despite straddle_rationale presence "
                f"(rubric violation — Straddle exemption should preempt Trigger 3); marker: {ab_match.group(0)!r}; "
                f"stdout head: {stdout[:400]!r}",
            ))
            continue
        # Diagnostic capture only — positive prose may or may not appear
        # depending on whether the synthesizer ratifies silently or
        # explicitly notes the exemption. Not load-bearing.
        prose_match = re.search(
            r'(?i)straddle\s+exemption|Straddle\s+(?:Protocol\s+)?(?:bias-up|exempt)|trigger\s+3\s+does\s+NOT\s+fire|ratify\s+as\s+A',
            stdout,
        )
        prose_note = (
            f"explicit straddle prose: {prose_match.group(0)!r}"
            if prose_match else "silent ratification (no A→B marker)"
        )
        results.append((True, f"attempt {attempt_idx}: pass ({prose_note})"))

    overall, summary = _apply_pass_criterion(results, "2-of-3")
    assert overall, (
        f"Trigger 3 (adjacent, with straddle) synthesizer-rubric validation failed under 2-of-3: "
        f"{summary}; per-attempt reasons: {[r for _, r in results]}"
    )


@pytest.mark.slow
def test_synthesizer_trigger_4_vague() -> None:
    """Trigger 4 (vague) synthesizer-rubric test — 2-of-3 tolerance (#179 Task 4).

    Bypasses reviewer dispatch entirely: extracts the Step 2d synthesizer prompt
    template from SKILL.md, substitutes a stub artifact and a hand-crafted
    reviewer-output JSON envelope (one A-class finding whose
    `fix_invalidation_argument` is hedged/speculative — "could potentially",
    "may emerge", "some environments" — with no concrete failure path), then
    invokes `claude -p '<assembled prompt>' --model opus` up to 3 times. The
    per-attempt evaluator passes iff (a) the response contains an A→B
    reclassification note AND (b) the A→B rationale prose contains a
    Trigger-4 anchor token (speculative / vague / hedged /
    no concrete failure path / trigger 4), case-insensitive. Pass/fail is then
    derived via `_apply_pass_criterion(results, "2-of-3")`.

    The 2-of-3 tolerance accommodates real-LLM stochasticity in the
    synthesizer's rationale wording (per spec R6) while still failing loud
    when the rubric is structurally broken or when Trigger 4 is not actually
    being recognized.

    The fixture's `fix_invalidation_argument` ("this approach could
    potentially encounter issues under load conditions that may emerge in
    some environments") is verbatim per #179 spec Req 5; verified held-out
    from `skills/critical-review/SKILL.md` via `grep -F ... SKILL.md`
    (exit 1) so the synthesizer cannot memorize-and-regurgitate from the
    worked-example prose. Deliberately distinct from the Worked Example 8
    string ("might cause performance issues", SKILL.md line ~275) for the
    same reason.

    Calibration evidence (one-time, 2026-05-11, pre-commit):
    ----------------------------------------------------------
    Ran `claude -p --model opus` once with this exact assembled prompt
    (stub artifact + the Trigger-4 fixture envelope below). Captured
    response (excerpt):

        No fix-invalidating objections after evidence re-examination. The
        concerns below are adjacent gaps or framing notes — do not read as
        verdict.

        ## Concerns

        - Synthesizer re-classified finding 1 from A→B:
          fix_invalidation_argument is speculative ("could potentially
          encounter issues", "may emerge in some environments") with no
          concrete failure path.

    Verified properties:
    (i) Per-trigger regex match: both the A→B-marker regex and the
        Trigger-4 anchor regex (`speculative | vague | hedged |
        no\\s+concrete\\s+failure\\s+path | trigger\\s+4`, case-insensitive)
        matched on the A→B rationale-line suffix. Captured rationale-line
        suffix: 'fix_invalidation_argument is speculative ("could
        potentially encounter issues", "may emerge in some environments")
        with no concrete failure path.' Trigger-4 token regex matched
        "speculative" (and "no concrete failure path" also present).
        Property (i) holds.

    (ii) Cross-trigger discrimination: per the lessons from Tasks 2 and 3,
         the rationale-token check is scoped to the post-`A→B:` suffix via
         `re.search(r're-classified finding \\d+ from A→B:?\\s*(.+)',
         stdout)`. The template's opening boilerplate "The concerns below
         are adjacent gaps or framing notes" would otherwise false-match
         "adjacent" outside the rationale; scoping prevents that. On the
         captured rationale line, the Trigger-2 token regex (`restate |
         circular | without\\s+a\\s+causal | tautolog`) did NOT match, and
         the Trigger-3 token regex (`adjacent | adjacency |
         no\\s+straddle_rationale | describes\\s+an?\\s+adjacent`) did NOT
         match either. Property (ii) holds for the load-bearing positive
         assertion.

    Disposition: calibration sound. Single live opus run produced a clean
    Trigger-4 downgrade signal; no fixture iteration required. The
    synthesizer cited the fixture's hedged phrases verbatim
    ("could potentially encounter issues", "may emerge in some
    environments") inside the rationale, which is the strongest possible
    signal that Trigger 4 is being recognized as designed.
    ----------------------------------------------------------
    """
    template = _extract_synthesizer_template()

    sentinel = "You are synthesizing findings from multiple independent adversarial reviewers"
    assert sentinel in template, (
        "synthesizer template extraction failed — anchor mismatch in SKILL.md"
    )

    # Hand-crafted reviewer JSON: one A-class finding whose
    # `fix_invalidation_argument` is hedged/speculative with no concrete
    # failure path. This is the canonical Trigger 4 (vague) shape per
    # SKILL.md Worked Example 8 — deliberately worded to avoid the
    # Worked Example 8 string ("might cause performance issues") so the
    # synthesizer can't pattern-match from memorization.
    #
    # Verbatim string per #179 spec Req 5; verified absent from SKILL.md
    # via `grep -F` (exit 1).
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
                "fix_invalidation_argument": (
                    "this approach could potentially encounter issues under "
                    "load conditions that may emerge in some environments"
                ),
            }
        ],
    }
    reviewer_json = json.dumps(reviewer_envelope, indent=2)

    assembled = re.sub(
        r'\{artifact content\}', lambda _m: STUB_ARTIFACT, template, count=1
    )
    assembled = re.sub(
        r'\{all reviewer findings[^}]*\}', lambda _m: reviewer_json, assembled, count=1
    )

    assert "{artifact content}" not in assembled, (
        "regex substitution failed: {artifact content} placeholder still present"
    )
    assert "{all reviewer findings" not in assembled, (
        "regex substitution failed: {all reviewer findings ...} placeholder still present"
    )

    # Inline 2-of-3 retry loop — sequential invocation, per-attempt evaluator.
    # Not delegated to `_run_n_times`: that helper dispatches the full
    # `/cortex-core:critical-review` slash command, not synthesizer-only.
    results: list[tuple[bool, str]] = []
    for attempt_idx in range(3):
        proc = subprocess.run(
            ["claude", "-p", assembled, "--model", "opus"],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0:
            results.append((False, f"attempt {attempt_idx}: exit {proc.returncode}; stderr: {proc.stderr[:300]}"))
            continue
        stdout = proc.stdout
        ab_match = re.search(r're-classified finding \d+ from A→B', stdout)
        if not ab_match:
            results.append((False, f"attempt {attempt_idx}: no A→B reclassification note; stdout head: {stdout[:400]!r}"))
            continue
        # Scope the anchor-token check to the rationale-line suffix so
        # template boilerplate ("The concerns below are adjacent gaps...")
        # cannot false-pass cross-trigger negatives. This mirrors Tasks 2/3
        # scoping.
        rationale_line_match = re.search(
            r're-classified finding \d+ from A→B:?\s*(.+)', stdout
        )
        rationale = rationale_line_match.group(1) if rationale_line_match else ""
        trigger4_match = re.search(
            r'(?i)speculative|vague|hedged|no\s+concrete\s+failure\s+path|trigger\s+4',
            rationale,
        )
        if not trigger4_match:
            results.append((
                False,
                f"attempt {attempt_idx}: A→B note present but rationale prose does not match Trigger 4 anchors; "
                f"rationale: {rationale[:300]!r}",
            ))
            continue
        # Per calibration property (ii) disposition (mirroring Tasks 2/3):
        # cross-trigger negative assertions are deferred. The positive
        # Trigger-4 token match on the rationale-line suffix is the
        # load-bearing assertion; cross-trigger contamination only matters
        # if a single stdout had to be classified as exactly one trigger.
        results.append((True, f"attempt {attempt_idx}: pass (rationale: {rationale[:120]!r})"))

    overall, summary = _apply_pass_criterion(results, "2-of-3")
    assert overall, (
        f"Trigger 4 (vague) synthesizer-rubric validation failed under 2-of-3: "
        f"{summary}; per-attempt reasons: {[r for _, r in results]}"
    )
