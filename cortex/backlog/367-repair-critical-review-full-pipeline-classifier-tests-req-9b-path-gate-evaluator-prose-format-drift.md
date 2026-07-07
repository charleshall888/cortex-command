---
schema_version: "1"
uuid: 9bc329d8-1a89-4b00-90c1-0cf1dad6cf18
title: 'Repair critical-review full-pipeline classifier tests: Req 9b path gate + evaluator prose-format drift'
status: wontfix
priority: low
type: chore
created: 2026-07-03
updated: 2026-07-06
areas: ['skills', 'tests']
tags: ['critical-review', 'test-debt']
---
## Why

The three full-pipeline critical-review classifier tests in `tests/test_critical_review_classifier.py` — `test_pure_b_aggregation_named_concern_to_class`, `test_straddle_case_named_concern_to_class`, `test_weak_argument_downgrade` — fail under `uv run pytest --run-slow` (verified **3 failed / 5 passed** on 2026-07-03; the 5 passing are the synthesizer-only tests repaired in #364).

The cause is **not** stochasticity. The pipeline's Step 2a.5 `prepare-dispatch` **path-validation gate (Req 9b)** — added to `critical_review.py` *after* these tests were written (`23a386b2`; opened to `cortex/research/` in `180d903a`) — rejects any artifact not strictly under `cortex/lifecycle/` or `cortex/research/`. The tests invoke `/cortex-core:critical-review` against fixtures under `tests/fixtures/critical-review/`, so the gate exits 2 (`"… is not strictly under any of …"`) **before dispatching any reviewer**. No synthesis is ever produced; the evaluators then score the *rejection prose*, yielding misleading failures:

- straddle → `"expected 1 A-class finding, got 0"` (0 `"class": "A"` strings in an error message)
- pure_b → `"blocks/invalidates verdict-framing leak"` (the error text itself says *"Why this **blocks** critical-review"*)
- weak_argument → `"no A→B reclassification note found"`

These are the only automated **end-to-end** validation of the reviewer→synthesizer classifier path, so while red, full-pipeline A/B/C classification and the A→B downgrade are unverified. (The rubric itself is still covered by the deterministic synthesizer-only trigger tests fixed in #364.)

## Role

Three stacked repairs:

1. **Path gate** — stage each fixture under an allowed root before invocation. `_run_critical_review` (and any direct call site) should copy the fixture into a temp dir under `cortex/research/` (or `cortex/lifecycle/`), invoke against the copy, and remove it afterward — via `try/finally` so it is cleaned up even on failure. The pipeline's own rejection message suggests exactly this staging.

2. **Evaluator prose-format drift** — once the pipeline runs, its synthesis output is **prose** (`## Objections` for A-class, `## Concerns` for B-class, per `references/synthesizer-prompt.md`), **not** the reviewer-side `"class": "A"` JSON that `_evaluate_pure_b`/`_evaluate_straddle` currently count. Rewrite those evaluators to key on the prose sections + the concern anchors from the meta files (which already describe this contract — e.g. `weak_argument_downgrade.meta.json`'s `expected_synthesizer_behavior.objections_section_emitted`). NOTE: this drift is **inferred from static evidence** (class-JSON lives only in `reviewer-prompt.md`/`residue-write.md`; the synthesizer output format is prose) and was **never observed end-to-end** because the Req 9b gate blocked every run in investigation — confirm against a real synthesis before finalizing.

3. **Re-baseline** — `tests/fixtures/critical-review/baseline-stability.json` is invalid: its `straddle: per_run_probability 0.0` was measured *through* the same broken path (and `tests/baseline_critical_review.py` invokes the same fixture paths, so it needs the part-1 staging fix too). Regenerate after 1+2, then set the pass criterion. `weak_argument_downgrade` depends on two-stage reviewer stochasticity (reviewers must first raise the A-class finding for the synthesizer to downgrade it) — re-confirm its `2-of-3` tolerance or accept that it overlaps the now-passing deterministic trigger tests.

## Integration

Verification requires full-pipeline `claude -p "/cortex-core:critical-review <artifact>"` runs — **stochastic, ~10 min each, multiple per test** for the N-of-3 criterion. These **cannot be reliably run from inside a nested Claude Code session**: the inner `claude` cannot create `~/.claude/session-env` under the outer sandbox (EPERM) and needs `--dangerously-disable-sandbox`, and even then each run is one stochastic sample. **Do the calibration in a normal terminal.** `tests/baseline_critical_review.py` needs the same path-staging fix or it will keep emitting invalid baselines.

## Edges

- Do **not** loosen Req 9b to accept `tests/fixtures/` — the path gate is a real production safety constraint; the tests must conform to it, not the reverse.
- Do **not** reintroduce a class-JSON expectation in the synthesizer output to satisfy the evaluators — the prose output format is deliberate (the A/B signal is `## Objections`/`## Concerns` + the residue file).
- The staged copy must never pollute the tracked `cortex/research/` tree — isolate in a temp subdir and clean up on every path (including failure/timeout).
- `pure_b`'s A-class check is currently **vacuous** (passes for the wrong reason — the JSON substring is simply absent from prose); the rewrite must actually assert *absence of an `## Objections` section*, not absence of a JSON substring.

## Touch points

- `tests/test_critical_review_classifier.py` — `_run_critical_review` (path staging), `_evaluate_pure_b`, `_evaluate_straddle`, possibly `_evaluate_weak_argument_downgrade`
- `tests/baseline_critical_review.py` — same path-staging fix
- `tests/fixtures/critical-review/baseline-stability.json` — regenerate after the fix
- `skills/critical-review/references/synthesizer-prompt.md` — read-only; the prose output contract the evaluators must match
- `critical_review.py` (`prepare-dispatch` Req 9b) — read-only; the constraint the tests must conform to

## Done when

All three full-pipeline tests pass under `uv run pytest --run-slow` (at their re-confirmed N-of-3 criteria) **run in a real terminal**, `baseline-stability.json` is regenerated through the fixed path, and no staged fixture copy remains in `cortex/research/` after a run.

Filed from the #364 investigation: repairing the extraction source (the 5 synthesizer-only tests) exposed this next layer once those tests could reach their model calls. See #364.
## Wontfix rationale (2026-07-06)

Closed without repair; the three full-pipeline tests, their evaluators, `tests/baseline_critical_review.py`, `baseline-stability.json`, and the pipeline fixtures (`pure_b_aggregation`, `straddle_case`, `weak_argument_downgrade`) were deleted rather than left permanently red. Cost/value: the repair and every future prompt change require stochastic N-of-3 calibration via real-terminal `claude -p` runs (~10 min each, live-billed), while the classification rubric is already covered by the deterministic synthesizer-only tests repaired in #364, which remain in `tests/test_critical_review_classifier.py`. The end-to-end reviewer→synthesizer path is exercised on every real critical-review run with a human reading the output, and its failure mode (missing synthesis) is loud. Do not re-file without new evidence that silent e2e classifier drift is occurring in practice.
