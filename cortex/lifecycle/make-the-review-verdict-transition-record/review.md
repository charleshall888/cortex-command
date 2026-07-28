# Review: make-the-review-verdict-transition-record

**Cycle**: 1 · **Tier**: complex · **Criticality**: high

## Reviewer independence — read the verdict with this caveat

This review was performed **in-session by the agent that wrote all five implementation
commits**, at the operator's direction (the session carries a standing directive against
dispatching sub-agents). The phase normally dispatches a fresh read-only reviewer with no
implementation context. A self-review cannot catch a wrong mental model — it can only catch
things inconsistent with the model that produced the code.

To partly offset that, the findings below lean on **executed probes rather than reasoning**:
every claim about test discrimination was verified by checking out the pre-fix source and
re-running (results inline), and every constant-equality claim was grepped rather than
recalled.

## Inputs

- Spec: `cortex/lifecycle/make-the-review-verdict-transition-record/spec.md` (12 requirements)
- Requirements: `cortex/requirements/project.md`, `glossary.md`, `pipeline.md`
  (`cortex-load-requirements` matched area docs; no no-match warning)
- Commits under review: `b6efad53`, `842b8aea`, `d707acb2`, `44bc06bd`, `14a951d7`
- Test baseline: `just test` → **8/8 suites passed, exit 0**
  (`scratchpad/review-baseline-421.log`). Not re-run by this review.

## Stage 1 — Spec compliance

| Req | Rating | Evidence |
|---|---|---|
| R1 neither pipeline arm supplies `from_state` | PASS | Both `_advance_to_review` and `_advance_review_complete` call `advance` with no `from_state`. Rebuilt fixture asserts the pre-call phase is `review`, then that both rows landed. |
| R2 `_current_phase` deleted | PASS | `git grep '_current_phase\|detect_lifecycle_phase' -- review_dispatch.py` → no matches, import removed. |
| R3 morning-review site drops artifact `from_state` | PASS | Line and `detect_lifecycle_phase` import both gone; `git grep 'from_state=' -- advance_lifecycle.py` → no matches. |
| R4 no-review branch fires implement-exit arm, asserts route | PASS | `test_simple_medium_advances_via_implement_exit_arm` pins one `phase_transition{implement→complete}`, no `review_verdict`, `advanced-complete`. `test_a_non_complete_route_is_never_reported_as_complete` pins the route assertion. |
| R5 `review_required` is corrupted-aware | PASS | Predicate now ORs `reduction.corrupted`. Constants verified identical to the arm's: both `{"high","critical"}`, defaults `medium`/`simple`. |
| R6 refusal audible, returns `advance-refused` | PASS | Returned literal, `KNOWN_STATES`, and the docstring `States:` list all updated; test asserts state, `caplog` warning naming the feature, and membership. |
| R7 walkthrough documents the state + a fallback rule | **PARTIAL** | All three acceptance greps pass on both copies. See finding 1 — the event-count prose was *replaced* rather than *restated*. |
| R8 fixtures rebuilt to carry machine rows | **PARTIAL** | All three fixtures rebuilt with `"from"`/`"to"` chains and pre-call phase assertions. But the literal acceptance grep still returns matches — see finding 2. |
| R9 `test_review_verdict_recording` pins one outcome | PASS | `if appended` gone; assertions unconditional. Verified it fails on pre-fix source. |
| R10 per-verb `from_state` invariant pinned | PASS | Grouping test plus a companion that feeds the same helper a synthetic divergent row, so the invariant cannot decay into a vacuous assertion. |
| R11 refusal text names omission | PASS | Both clauses present and asserted in the existing gate-mismatch test; the re-sync clause and its warning retained verbatim. |
| R12 downstream readers see completion | PASS (weak pin) | E2E test asserts `already-complete` on re-run. See finding 5 — this one does **not** discriminate. |

**No FAIL — Stage 2 ran.**

### Discrimination probe (executed, not reasoned)

Restoring the pre-fix sources and re-running the new tests:

- pre-fix `advance_lifecycle.py` (`44bc06bd`) → **5 failed, 15 passed**, including all four
  #421-specific tests and `test_every_state_is_known`.
- pre-fix `review_dispatch.py` (`1a4667c9`) → **1 failed**, with the exact reported failure:
  `detected phase 'review' does not match expected from_state 'complete'` — the caller's
  artifact-derived `complete` against the gate's events-first `review`, i.e. the spec's
  Problem Statement reproduced verbatim.

Both files restored; `git diff` clean.

## Stage 2 — Code quality

1. **R7's prose was replaced, not corrected.** The requirement says the stale event-count
   prose "is corrected to match what the arms now emit". The first draft did enumerate the
   new emissions; it pushed the directory 604 bytes over its reference-size pin, so it was
   rewritten to point at the verb's returned `state` instead ("read them off the verb's
   `state` rather than predicting them"). That is *more* correct under verb-first
   (`project.md` Architectural Constraints) and every stated acceptance criterion passes,
   but it is a substitution, and the forcing function was the ratchet rather than a design
   call. Rated PARTIAL so the substitution is on the record.
2. **R8's acceptance grep is unsatisfiable as written.** `grep -rn "from_phase\|to_phase"
   --include="*.py" .` still returns 6 matches in `tests/failure_matrix.py:46-65`. They are
   **local variable names** reading `entry.get("from")`/`entry.get("to")` — correct code,
   pre-existing, and not the misspelled-key defect (research's claim was "the sole repo-wide
   occurrence of those *keys*", which holds). The requirement's intent is met; its literal
   grep was over-broad from the start. Not fixed, because renaming variables in an unrelated
   file was outside the task's `Files`.
3. **The two review predicates agree by duplication, not by construction.** `review_required`
   and `implement_transition._resolve_route` now produce identical answers, but via two
   copies of `{"high","critical"}` and two copies of the `medium`/`simple` defaults. The
   spec's own Technical Constraint — "Any future edit to either rule must change both" — is
   carried only by a code comment. This is the same unenforced-invariant shape that R10
   exists to fix for `from_state`, left unfixed one module over. **Recommend a follow-up
   ticket** to hoist the predicate into one shared callable; not blocking, since the spec
   scoped R5 to alignment rather than unification.
4. **Two near-identical refusal helpers now exist.** `advance_lifecycle._refusal_state` and
   `review_dispatch._advance_or_warn` do the same job in sibling modules with different
   shapes (one returns a state, one returns None). Deliberate — the spec's Technical
   Constraints keep both modules routing through `advance` independently, and sharing would
   couple overnight to pipeline — but it is duplication worth naming.
5. **R12's e2e test does not discriminate.** It passes against the pre-fix source too (that
   path's crash-recovery branch happened to gate correctly on this fixture). It is a valid
   acceptance check for "downstream sees completion", not a regression pin. The pins that
   actually catch this bug are the four #421 tests and the rebuilt
   `test_review_verdict_recording`.
6. **Scope additions beyond the plan's `Files`, both forced by red verification, both
   disclosed**: `tests/test_advance_status_projection_sweep.py` (a **fourth** file with the
   same no-`phase_transition` fixture defect the spec found in three — its two
   `advance_lifecycle` seeds went red the moment the arm gated honestly) and
   `skills/morning-review/references/size-pin.txt` (annotated `# raised:` line, the
   affordance `project.md` Architectural Constraints explicitly sanctions).
7. **Plan verification steps were executed**, not assumed: every task's `Verification` field
   was run and its output recorded at implementation time.
8. **Error handling preserves the best-effort contract.** `_refusal_state` and
   `_envelope_route` both tolerate a non-dict envelope; an `error` envelope degrades to
   `missing-review` rather than a false completion; nothing raises.

### Environment issue surfaced during implementation

`core.hooksPath` pointed at a nonexistent `myhooks/`, so **every git hook was disabled** —
including commit-message validation and the dual-source mirror reconciliation that
`project.md` lists as a named-evidence enforcement gate. Fixed via `just setup-githooks`;
Task 4 was re-committed so its mirror folded in. Commits `b6efad53`, `842b8aea`, `d707acb2`
were never message-validated (inspected by hand: all conform). Not a code defect, but it
means the repo silently lost gate coverage for an unknown prior window.

## Requirements Drift

**State**: detected

**Findings**:
- `cortex/requirements/pipeline.md:85` states that morning review writes synthetic
  `review_verdict: APPROVED, cycle: 0` events for features that legitimately skip review.
  R4 removed exactly that behavior — the no-review branch now fires the implement-exit arm
  and writes no verdict row at all. The requirement now describes behavior that no longer
  exists.

**Update needed**: `cortex/requirements/pipeline.md`

## Suggested Requirements Update

**File**: `cortex/requirements/pipeline.md`
**Section**: `### Post-Merge Review`
**Content**:

```
  - Morning review no longer writes a synthetic `review_verdict: APPROVED, cycle: 0` row: a feature that legitimately skips review exits via the implement-transition arm, recording only `phase_transition{from: implement, to: complete}`. A corrupted reduction is review-required and routes to `missing-review` rather than being auto-completed (#421).
```

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["R7: event-count prose replaced with a pointer to the verb's state rather than restated, forced by the reference-size ratchet", "R8: acceptance grep still matches tests/failure_matrix.py local variable names (not the misspelled-key defect; pre-existing, out of task scope)", "Stage 2: the two review predicates agree by duplicated constants with no shared source - recommend a follow-up ticket", "R12's e2e test passes against pre-fix source and is an acceptance check, not a regression pin", "Reviewed in-session by the implementing agent, not an independent reviewer"], "requirements_drift": "detected"}
```
