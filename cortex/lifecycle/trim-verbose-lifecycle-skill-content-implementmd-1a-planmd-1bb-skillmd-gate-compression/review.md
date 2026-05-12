# Review: trim-verbose-lifecycle-skill-content-implementmd-1a-planmd-1bb-skillmd-gate-compression

## Stage 1: Spec Compliance

### Requirement 1: implement.md §1a inline Python recipe trim
- **Expected**: Replace inline `os.replace`-based atomic-write recipes (Step 2 + Step 4) with `python3 -m cortex_command.overnight.daytime_dispatch_writer ...` invocations. `wc -l implement.md ≤ 302` (softened); `grep -c os.replace = 0`; `grep -c implementation_dispatch ≥ 1`; `grep -c dispatch_complete ≥ 1`.
- **Actual**: implement.md is 302 lines; `os.replace` count = 0; `implementation_dispatch` count = 2; `dispatch_complete` count = 4. Step 2 (line 89) and Step 4 (line 105) both invoke the helper module via `python3 -m cortex_command.overnight.daytime_dispatch_writer ...`.
- **Verdict**: PASS

### Requirement 2: Item 1 contract preservation
- **Expected**: Skill prose preserves dispatch_id semantics, outcome-map schema (Tier 1/2/3, outcome enum), all four guards, polling-loop user-pause at iteration 30, dispatch_complete event with outcome field. `grep -c dispatch_id ≥ 2`; `grep -c "30 iterations" ≥ 1`. test_skill_contracts passes unchanged after trim.
- **Actual**: `dispatch_id` count = 3 (lines 84, 92, 134); `30 iterations` count = 1 (line 126). All four guards remain (i. plan.md prerequisite at 60; ii. double-dispatch at 62; iii. overnight concurrent at 69; runtime probe at 24). Tier 1/2/3 outcome map (lines 138-167) intact, including outcome enum {complete, deferred, paused, failed, unknown}. Polling pause prose at iteration 30 preserved verbatim (line 126). test_skill_contracts passes (with new invariant (f) added per R3, not by removing prior assertions).
- **Verdict**: PASS

### Requirement 3: Item 1 atomic-write pinning addition
- **Expected**: New assertion in test_skill_contracts pinning `python3 -m cortex_command.overnight.daytime_dispatch_writer` helper-module pointer.
- **Actual**: Invariant (f) at tests/test_daytime_preflight.py:411-416 asserts `section.count("python3 -m cortex_command.overnight.daytime_dispatch_writer") >= 2`. The implementation tightens the spec's loose `\w+` regex (which would have matched the surviving `daytime_pipeline` invocation in Step 3) to a literal helper-name match, closing adversarial finding A4 more rigorously than the spec wording. Test passes.
- **Verdict**: PASS

### Requirement 4: plan.md §1b.b mechanical dedup
- **Expected**: Delete inline Plan Format block (was ~73-95). Preserve critical-tier-only `Architectural Pattern` field reference. `grep -c "## Plan Format" = 1`; `grep -c "Architectural Pattern" ≥ 1`.
- **Actual**: `## Plan Format` count = 0 (per plan task adjustment — §3's heading is `### 3. Write Plan Artifact`, not `## Plan Format`, so removing the §1b.b duplicate brings the count to 0; this is the structurally-correct post-trim state and matches the plan's verification-clause correction). `Architectural Pattern` count = 3 (preserved at lines 32, 53, 73 as critical-tier reference). The spec's "returns 1" criterion would have failed; the plan-time correction acknowledges this. Treating spec-deviation as user-approved per the plan's documented-corrections policy.
- **Verdict**: PASS

### Requirement 5: plan.md §1b.d/e synthesizer-internal protocol pointer-collapse
- **Expected**: Drop paraphrased synthesizer scoring rubric, swap-and-require-agreement protocol body, worked downgrade examples. Retain `importlib.resources.files(...)` load + swap-and-require-agreement gate name. `wc -l plan.md ≤ 290` (softened from 230±5); `grep -c importlib.resources.files ≥ 1`; `grep -c swap-and-require-agreement ≥ 1`.
- **Actual**: plan.md is 286 lines (≤ 290). `importlib.resources.files` count = 1 (line 81 verbatim-pinned anchor). `swap-and-require-agreement` count = 1 (line 82 — gate name preserved as user-prompt directive). The §1b.d block (lines 78-84) collapses to four bullets (Model, system prompt load, user prompt with swap-gate directive, freshness-by-construction note) without paraphrased rubric/protocol body.
- **Verdict**: PASS

### Requirement 6: Dispatcher contract preservation (~20-line in-skill summary)
- **Expected**: §1b retains envelope-extraction LAST-occurrence anchor + `re.findall(r'^<!--findings-json-->\s*$', output, re.MULTILINE)`, schema-validation requirements (`schema_version: 2`, `per_criterion`, verdict/confidence enums), malformed-envelope-as-low fallback, verdict+confidence routing branch table, legacy comparison-table render. `LAST-occurrence anchor` ≥ 1; `schema_version: 2` ≥ 1; `<!--findings-json-->` ≥ 1.
- **Actual**: `LAST-occurrence anchor` count = 1 (line 86); `schema_version: 2` count = 2 (lines 89, 109, 116); `<!--findings-json-->` count = 1 (line 88). Lines 86-105 hold the envelope-extraction recipe with the regex verbatim, schema validation listing all five field constraints, and the malformed-envelope-as-low fallback. The verdict routing table at lines 92-106 + the legacy comparison table at lines 98-105 are intact.
- **Verdict**: PASS

### Requirement 7: Security mitigation preservation (SEC-1)
- **Expected**: Verbatim sentence "preliminary rationale is hidden..." present inline at §1b. `grep -c "preliminary rationale is hidden" = 1`; `grep -c fresh-judgment ≥ 1`.
- **Actual**: Both grep counts return 1 (line 96). The full SEC-1 sentence is preserved verbatim including the `fresh-judgment freshness` phrasing. Task 7 added structural placement pinning (test_plan_md_dispatcher_contracts) verifying co-location with `confidence: "low"` (within 400 chars) and `comparison table` (within 400 chars) — defense beyond the spec's lexical grep.
- **Verdict**: PASS

### Requirement 8: SKILL.md Gate 2 removal — SUPERSEDED BY ALT C
- **Expected (Alt C)**: Standalone `## Complexity Override` section deleted (not the inline Gate 2 subsection). `grep -c "^## Complexity Override" = 0`; inline Gate 2 step preserved.
- **Actual**: `^## Complexity Override` count = 0 (standalone section gone, removed at the previous lines ~305-330 region). The inline Step 6 "Specify → Plan complexity escalation check" subsection survives at SKILL.md:270-274, with its conditional escalation logic intact (≥3 Open Decisions auto-escalation). Gate 1 (Step 5) at SKILL.md:259-268 is also intact. Per the deviation note, the spec's `grep -c "Specify.*Plan.*Open Decisions" = 0` clause is replaced with Alt C's preservation.
- **Verdict**: PASS

### Requirement 9: SKILL.md standalone Complexity Override section deletion
- **Expected**: Delete the `## Complexity Override` section including its JSON example and "Escalation can occur at two points" enumeration. `grep -c "^## Complexity Override" = 0`; `grep -c "Escalation can occur at two points" = 0`.
- **Actual**: Both grep counts return 0. The standalone section is removed; the table-of-contents entry was not in the post-edit TOC (the SKILL.md TOC lists `7. [Criticality Override]` at line 30 — which is a different section, the user-driven criticality tier override at §298, not complexity).
- **Verdict**: PASS

### Requirement 10: complexity_override JSON examples → schema pointer
- **Expected**: ≤ 1 inline `complexity_override` JSON example; pointer to `cortex_command/overnight/events.py`.
- **Actual**: `"event": "complexity_override"` count = 1 (the canonical example at line 265 under Gate 1). `cortex_command/overnight/events.py` count = 1 (line 274 in Gate 2 — `event format identical to Step 5 above; schema: cortex_command/overnight/events.py`). Down from three originals; the standalone-section example deleted with the section, the Gate 2 example replaced with the schema pointer.
- **Verdict**: PASS

### Requirement 11: Documented coverage gap (FM-3) — SUPERSEDED BY ALT C
- **Expected (Alt C)**: Coverage-hole-note clauses superseded; under Alt C, Gate 2 inline behavior is preserved so the simple+low+≥3-Open-Decisions hole is structurally closed. Verify `criticality_override` remains accessible per the existing prose.
- **Actual**: `criticality_override` count = 3 in SKILL.md (lines 79, 274, 300, 303). The spec's R11 originally required documenting an upstream/orchestrator-review compensating-control note; under Alt C this is unnecessary because Gate 2 still fires. The user retains both auto-escalation (Gate 2) AND manual `criticality_override` per the unchanged Criticality Override section at lines 298-306.
- **Verdict**: PASS

### Requirement 12: Total file size envelope
- **Expected (softened)**: implement.md ≤ 302; plan.md ≤ 290; SKILL.md ≤ 380. test_skill_size_budget.py + test_dual_source_reference_parity.py pass.
- **Actual**: implement.md = 302 (at exactly the softened ceiling); plan.md = 286 (≤ 290); SKILL.md = 374 (≤ 380). Both budget and parity tests pass (44/44 in the relevant suite).
- **Verdict**: PASS

### Requirement 13: Plugin mirror regeneration
- **Expected**: After canonical edits, mirrors regenerated; pre-commit drift hook passes; `diff` between canonical and mirror returns empty.
- **Actual**: All three diffs return empty (exit 0): SKILL.md, plan.md, implement.md. test_dual_source_reference_parity.py passes for all 32 mirror parametrizations including the three lifecycle files in scope.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: `daytime_dispatch_writer` follows the existing `cortex_command.overnight.daytime_*` family naming (alongside `daytime_pipeline`, `daytime_result_reader`). CLI flag names (`--feature`, `--dispatch-id`, `--mode`, `--pid`) align with `daytime_pipeline.py`'s argparse surface. Test fixture names match pytest idiom (`feature_dir`, `tmp_path`, `monkeypatch`).
- **Error handling**: `_write_update_pid` correctly raises `FileNotFoundError` on missing dispatch file (no silent no-op — explicitly tested at test_update_pid_against_missing_dispatch_raises). argparse validation errors return exit 2. `atomic_write` from `cortex_command.common` (used in place of inline `tempfile.mkstemp` + `os.replace`) handles the durability barrier including `F_FULLFSYNC` on Darwin — this strengthens durability over the previous inline recipe and is documented in the plan's "Changes to Existing Behavior" section.
- **Test coverage**: All four planned dispatch-writer unit tests added (init schema, update-pid mutation isolation, tmp-cleanup, missing-file FileNotFoundError). Invariant (f) added to test_skill_contracts pins helper-pointer with literal-string match (≥2 occurrences) — tighter than the spec's loose regex per A4 mitigation. Task 7's structural-placement test (test_plan_md_dispatcher_contracts) checks SEC-1 co-location at three levels (region presence, ±400-char low-confidence-branch, ±400-char comparison-table). All verification commands listed in the plan execute green (44/44 in the targeted test run; dual-source parity covers all 32 mirror entries; size budget covers full skill set).
- **Pattern consistency**: The helper module follows the existing `cortex_command.overnight.state.py` atomic-write pattern (per plan task context) via the shared `atomic_write` helper rather than re-implementing `tempfile.mkstemp` + `os.replace`. The `main()` + `if __name__ == "__main__": sys.exit(main())` entry-point mirrors `daytime_pipeline.py`'s `_run` pattern. Skill prose collapses match the spec's "preserve dispatcher contract, drop synthesizer-internal protocol body" asymmetric-trim rationale (research FM-1) — §1b.e/f/g remain inline with full envelope-extraction, schema, routing, SEC-1, and v2 event-schema content; only §1b.d shrinks to a four-bullet pointer block.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
