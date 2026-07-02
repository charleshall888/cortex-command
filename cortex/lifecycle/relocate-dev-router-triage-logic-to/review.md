# Review: relocate-dev-router-triage-logic-to

Independent read-only review (reviewer did not implement). All acceptance grep/test
commands named by R1–R12 were RUN against the working tree. The feature's `skills/dev/`
edits, both new references, their mirrors, and the wiring-guard test are already committed
(commits `b40bf225`, `5d151707`, `b5d8aac2`); the working tree carries only unrelated
concurrent-session artifacts and this feature's own `events.log`.

## Stage 1: Spec Compliance

### Requirement 1: Triage-rendering reference created AND removed from the body
- **Expected**: `skills/dev/references/triage-rendering.md` holds Block 1 + Block 2 verbatim; the moved tokens are absent from the body.
- **Actual**: `test -f` exits 0. In the ref: `Flat Ready List`=1, `Per-epic workflow recommendation`=1. In the body: both tokens=0. Full-span absence also confirmed (`Suppress children`/`Suppress epics`/`No active child tickets found`=0).
- **Verdict**: PASS

### Requirement 2: Criticality-heuristics reference created AND removed from the body
- **Expected**: `skills/dev/references/criticality-heuristics.md` holds `### Heuristic Signals` + `### Forming the Suggestion` verbatim; `### Resumed Lifecycle` NOT moved; token absent from body.
- **Actual**: `test -f` exits 0. Ref `Payments, billing, financial data`=1. Body `Payments, billing, financial data`=0; body `### Heuristic Signals`=0, `### Forming the Suggestion`=0, `No elevated signals`=0. `### Resumed Lifecycle` guard remains resident (body line 89).
- **Verdict**: PASS

### Requirement 3: Branch-1 imperative Read pointer at `### 3c`
- **Expected**: single `${CLAUDE_SKILL_DIR}/references/triage-rendering.md` pointer at/after `### 3c` and after Step-3b exit-code handling.
- **Actual**: pointer count=1 at line 149; `### 3c` heading at line 147; Step-3b exit-1/exit-2 handling at lines 144–145. Ordering `149 > 147 ≥ 145` holds. Uses own-dir `${CLAUDE_SKILL_DIR}` form (not bare-relative). Pointer is a distinct imperative Read line.
- **Verdict**: PASS

### Requirement 4: Two-caller imperative Read pointer for criticality-heuristics
- **Expected**: single `${CLAUDE_SKILL_DIR}/references/criticality-heuristics.md` pointer reachable from Branch 5 and the Step-4 decline path.
- **Actual**: pointer count=1 at line 98. Branch 5 routes into Step 2 ("Perform the criticality pre-assessment (Step 2)", line 71); Step-4 decline routes into Step 2 (line 173). Both flow top-down through the Step-2 guard to the single pointer at line 98.
- **Verdict**: PASS

### Requirement 5: Step 2 order — resume route-out precedes the Read pointer
- **Expected**: confirm-resume route-out line number < criticality pointer line number; guard referent rewritten to name the reference.
- **Actual**: route-out "Skip the criticality suggestion" at line 95 < pointer at line 98. Guard opening rewritten (line 91: "Before performing this criticality assessment (its heuristic-signals table now lives in the reference Read below)…"); the dangling pre-move phrase `Before performing this assessment`=0. Only occurrence of the `criticality-heuristics.md` token in Step 2 is the pointer line.
- **Verdict**: PASS

### Requirement 6: Deterministic Step 3b mechanics stay in the body
- **Expected**: backend gate, 3a regen, `cortex-build-epic-map` invocation, ready-set intersection, exit-1/exit-2 routing remain resident.
- **Actual**: `cortex-build-epic-map`=3 (≥1), `schema_version`=2 (≥1), `deterministic epic`=1 (the plan's discriminating token unique to the 3b invocation). Backend gate, index regen, intersection, and exit-code handling all remain in the body.
- **Verdict**: PASS

### Requirement 7: Pinned headings preserved as stubs
- **Expected**: `## Step 2: Criticality Pre-Assessment`=1 and `### 3c. Present Ready Items`=1.
- **Actual**: both =1; content moved, headings kept as anchors.
- **Verdict**: PASS

### Requirement 8: Invocation lines preserved verbatim
- **Expected**: contract-lint gate exits 0; `cortex-*`/slash invocation strings byte-preserved wherever they land.
- **Actual**: `cortex-check-contract --audit` exit 0. Slash invocations (`/cortex-core:discovery`, `/cortex-overnight:overnight`, `/cortex-core:refine`, `/cortex-core:lifecycle`) preserved byte-for-byte in `triage-rendering.md`. No `cortex-*` binstub token moved (`cortex-build-epic-map` stays in Step 3b).
- **Verdict**: PASS

### Requirement 9: Mirror regenerated, byte-parity clean, AND tracked
- **Expected**: `git diff --quiet -- plugins/cortex-core/skills/dev/` exits 0; `test_dual_source_reference_parity.py` passes; both mirror refs tracked.
- **Actual**: `git diff --quiet` exits 0. `git ls-files --error-unmatch` on both mirror refs exits 0 (tracked). `diff -q` confirms canonical↔mirror byte-identical for both refs and SKILL.md. `test_dual_source_reference_parity.py`: 61 passed.
- **Verdict**: PASS

### Requirement 10: Standing wiring-guard test added (with body-absence negative control)
- **Expected**: test asserts both refs exist in canonical+mirror; single `${CLAUDE_SKILL_DIR}` pointer each; directives distinct from stub headings; full-span moved-token absence; docstring disclaims runtime coverage.
- **Actual**: `tests/test_dev_triage_refs_wired.py` exists and is tracked; 5 assertions pass (existence, single-occurrence own-dir pointer, distinct imperative directive, stub-heading survival, full-span negative control with 9 tokens spanning both blocks). Module docstring explicitly states runtime missed-read / read-but-not-applied is OUT OF SCOPE.
- **Verdict**: PASS

### Requirement 11: Full gate suite green against a captured baseline
- **Expected**: `just test` exit 0, or every non-zero result present in the provenance-stamped baseline.
- **Actual**: orchestrator recorded `just test` exit 0 (baseline HEAD `8f803a31`, 0 failing tests — clean baseline). Targeted re-runs all green: wiring guard (5), dual-source parity (61), L1 ratchet (20), parity-related pytest suite (73). `cortex-check-contract`, `cortex-check-skill-path --audit`, `cortex-check-bare-python-import --audit` all exit 0. NOTE: a whole-repo `cortex-check-parity --audit` flags pre-existing bare-python callsites in `tests/test_morning_review_status_close_ordering.py` (an unrelated morning-review file, last touched by `74f38d92`, NOT in this changeset) — that audit recipe is not part of `just test`, and every parity pytest test that `just test` does run passes, so R11's gate is unaffected.
- **Verdict**: PASS

### Requirement 12: L1-neutral
- **Expected**: dev's L1 frontmatter surface (285 B) unchanged; no ratchet budget row raised.
- **Actual**: `test_l1_surface_ratchet.py`: 20 passed. `git diff` on `skills/dev/SKILL.md` shows no frontmatter field-line changes; no diff to the ratchet budget test / dev's row. Only the body moved.
- **Verdict**: PASS

## Stage 2: Code Quality
- **Naming conventions**: Consistent. Reference files are consumer-keyed (`criticality-heuristics.md`, `triage-rendering.md`) under the new `skills/dev/references/` dir; the guard test `test_dev_triage_refs_wired.py` mirrors the `test_competing_plans_wired.py` naming. Reference headers name their consuming Step/Branch.
- **Error handling**: Appropriate for the context (prose references + static test). The test uses per-assertion functions with explanatory failure messages; the body Read pointers are imperative gates ("Read … and apply/render … before …") rather than bare bracketed links, matching the edge-case mitigation the spec calls for. Both references are 61 and 36 lines — well under the ~100-line ToC cap, so no ToC is required (spec-consistent).
- **Test coverage**: The plan's verification steps were executed and reproduce green. The wiring guard's load-bearing negative control keys on a full-span 9-token set (both block sub-headings plus distinctive body lines), so a partial re-inline or copy-not-move fails it — not just a three-sentinel check. The docstring honestly scopes out the untestable runtime missed-read / read-but-not-applied risk rather than overclaiming.
- **Pattern consistency**: Follows the #341 sibling lazy-ref extraction pattern (stub heading + single imperative pointer + wiring guard modeled on `test_competing_plans_wired.py`) and ADR-0009 skill-path resolution (own-dir `${CLAUDE_SKILL_DIR}/references/<file>.md` form, no bare-relative, no sibling `../`). The propagation-manifest half of #341 is deliberately and correctly NOT adopted — dev has no downstream shell lines or composed subagent prompts, and a manifest would create a disqualifying second occurrence of each path token. No new MUST/CRITICAL/REQUIRED escalation introduced (pointers are soft imperatives), consistent with the MUST-escalation policy.

## Requirements Drift
**State**: none
**Findings**:
- None. The change is L1-neutral (dev stays at 285 B, a routing-pressure-cluster skill; no budget row raised), applies existing ADR-0009 and the established #341 extraction pattern, introduces no new MUST/CRITICAL escalation, and adds no behavior beyond the spec's stated relocation. It matches the project.md "SKILL.md L1 surface ratchet" constraint and the "prescribe What and Why, not How" / skill-path-resolution design principles.
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
