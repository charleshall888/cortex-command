# Plan: auto-progress-lifecycle-phases-when-no-blockers

## Overview
Land the spec in three sequenced phases: (Phase 1) fix the cycle-counter bug and add approval-event-aware phase detection in `cortex_command/common.py` so the auto-advance contract has a sound foundation; (Phase 2) rewrite skill prose to remove ceremonial framing, register the two new event types in the events-registry, and add the kept-pauses inventory; (Phase 3) ship two test files — phase-detector regression and kept-pauses parity — to prevent regression. Tasks sequence Phase 1 first because R3's detector must precede R5/R6's emit-side prose; otherwise a `spec_approved` event from approved specs would be emitted but no consumer would read it.

## Outline

### Phase 1: common.py primitives (tasks: 1, 2)
**Goal**: Fix the cycle-counter bug and add approval-event lookup with migration sentinel to the phase detector.
**Checkpoint**: `python3 -c "from cortex_command.common import detect_lifecycle_phase"` succeeds; fixture-based tests would pass (formal tests land in Phase 3).

### Phase 2: Skill prose rewrites + events-registry (tasks: 3, 4, 5, 6, 7, 8)
**Goal**: Disambiguate the Phase Transition contract, rewrite specify.md and plan.md §4 to remove ceremonial framing and emit approval events, enrich resume-staleness prompt, auto-skip refine when artifacts exist, unify per-phase auto-advance phrasing, add kept-pauses inventory.
**Checkpoint**: `grep -c "must approve before proceeding" skills/lifecycle/references/specify.md` returns 0; `grep "must approve before implementation begins" skills/lifecycle/references/plan.md` returns 0; per-phase auto-advance grep across {plan,implement,review,complete}.md passes; kept-pauses subsection exists in SKILL.md.

### Phase 3: Test surface (tasks: 9, 10)
**Goal**: Phase-detector regression test (R11) and kept-pauses parity test (R12) lock in the contract.
**Checkpoint**: `just test tests/test_lifecycle_auto_advance.py` and `just test tests/test_lifecycle_kept_pauses_parity.py` both exit 0.

## Tasks

### Task 1: Fix review-cycle counter to read from events.log
- **Files**: `cortex_command/common.py`, `tests/test_common_utils.py` (if existing cycle-counter test exists, update it)
- **What**: Replace the regex-on-review.md cycle counter at `common.py:185–196` with a JSONL scan of `events.log` for `event: "review_verdict"` entries. Cycle = number of `review_verdict` events; default 1 when none present. The `review_content` variable continues to be read for verdict extraction (Step 2 at lines 210–233) but is no longer consulted for cycle counting.
- **Depends on**: none
- **Complexity**: simple
- **Context**: existing function `detect_lifecycle_phase` in `cortex_command/common.py` (function name confirmed at line 279). The regex pattern `r'"verdict"\s*:\s*"([A-Z_]+)"'` stays for verdict-value extraction; only the cycle-length computation moves to events.log. JSONL parsing pattern is well-established in the module; reuse `events_log.read_text(errors="replace")` then iterate per line with `json.loads`. Existing test fixture pattern can be inferred from `tests/test_lifecycle_state.py` if needed.
- **Verification**: `python3 -c "from cortex_command.common import detect_lifecycle_phase; import tempfile, pathlib, json; d=pathlib.Path(tempfile.mkdtemp())/'f'; d.mkdir(); (d/'events.log').write_text('{\"event\":\"review_verdict\",\"verdict\":\"CHANGES_REQUESTED\"}\n'*2); (d/'review.md').write_text('verdict only'); print(detect_lifecycle_phase(str(d))['cycle'])"` prints `2`. Pass if output is `2`.
- **Status**: [ ] pending

### Task 2: Add approval-event lookup with migration sentinel to phase detector
- **Files**: `cortex_command/common.py`
- **What**: In `detect_lifecycle_phase`, at the branch where `spec.md` exists and would normally advance to `plan` (and similarly for `plan.md` → `implement`), insert an approval-event check before the advance. Approval logic: if `spec_approved` event in events.log → advance; else if `phase_transition` event with `"from":"specify"` (any `to`) exists in events.log → advance (migration sentinel for in-flight lifecycles authored before approval events existed); else stay in `specify`. Same pattern for `plan.md`/`plan_approved`/`"from":"plan"`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Existing phase detector code in `cortex_command/common.py` around lines 230–270 reads `events.log` already (line 199–208 for `feature_complete` check). Reuse that pattern. The migration sentinel pattern uses `any(json.loads(line).get("event") == "phase_transition" and json.loads(line).get("from") == "specify" for line in events_content.splitlines() if line.strip())`. Keep return shape unchanged: `{"phase": ..., "checked": ..., "total": ..., "cycle": ...}`.
- **Verification**: `python3 -c "from cortex_command.common import detect_lifecycle_phase; import tempfile, pathlib, json; d=pathlib.Path(tempfile.mkdtemp())/'f'; d.mkdir(); (d/'spec.md').write_text('x'); (d/'events.log').write_text(''); print(detect_lifecycle_phase(str(d))['phase'])"` prints `specify`. Pass if output is `specify` (not `plan`).
- **Status**: [ ] pending

### Task 3: Disambiguate SKILL.md Phase Transition + add Kept user pauses inventory
- **Files**: `skills/lifecycle/SKILL.md`
- **What**: At the existing Phase Transition section (lines 161–172), replace the ambiguous sentence "After completing a phase artifact, announce the transition and proceed to the next phase automatically" with a per-phase completion rule that explicitly names each phase's gate condition: Specify=spec_approved-event-or-migration-sentinel, Plan=plan_approved-event-or-migration-sentinel, Implement=plan.md-tasks-all-checked, Review=review_verdict-APPROVED-event-or-cycle-2-escalation, Complete=feature_complete-event. Then add a new "Kept user pauses" subsection immediately after, listing 19 entries from the spec's R10 (one bullet per entry, `- <file>:<rough-line> — <one-line rationale>` format).
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Phase Transition section at SKILL.md:161–172. The R10 inventory in the spec enumerates 19 sites — copy them verbatim with file:line and rationale. The new subsection header should be a level-3 markdown heading (`### Kept user pauses`) under the Phase Transition section, so it doesn't conflict with the existing top-level sections.
- **Verification**: `grep -A20 "Per-phase completion rule\|Kept user pauses" skills/lifecycle/SKILL.md | wc -l` returns ≥20 (subsection has substantive content); `grep -c "spec_approved" skills/lifecycle/SKILL.md` returns ≥1; `grep -c "Kept user pauses" skills/lifecycle/SKILL.md` returns 1. Pass if all three conditions hold.
- **Status**: [ ] pending

### Task 4: Rewrite specify.md §4 (spec approval) and register spec_approved event
- **Files**: `skills/lifecycle/references/specify.md`, `bin/.events-registry.md`
- **What**: In `specify.md:153–161`, delete the sentence "The user must approve before proceeding to Plan. If the user requests changes, revise the spec and re-present." Replace with explicit AskUserQuestion options enumeration (`Approve` / `Request changes` / `Cancel`) on the existing call, plus the auto-advance flow on Approve (emit `spec_approved` event AND `phase_transition` event AND continue to Plan). Add a `lifecycle_cancelled` event mention for the Cancel branch. In `bin/.events-registry.md`, register the `spec_approved` event type with name + schema (`ts, event, feature`) + one-line description + producer column listing `skills/lifecycle/references/specify.md`.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: `skills/lifecycle/references/specify.md` §4 (lines 153–161). The existing prose at line 155 already directs use of AskUserQuestion; the change is to enumerate options and define the Approve branch's event emissions. `bin/.events-registry.md` follows the established events-registry table format — read an existing entry as a pattern reference before adding the new row.
- **Verification**: `grep -c "must approve before proceeding" skills/lifecycle/references/specify.md` returns 0; `grep "spec_approved" skills/lifecycle/references/specify.md` returns ≥1 match; `grep -E '^\| .spec_approved' bin/.events-registry.md` returns 1 match. Pass if all three conditions hold.
- **Status**: [ ] pending

### Task 5: Rewrite plan.md §4 (plan approval) and register plan_approved event
- **Files**: `skills/lifecycle/references/plan.md`, `bin/.events-registry.md`
- **What**: In `plan.md:275–282`, delete "The user must approve before implementation begins. If the user requests changes, revise and re-present." Replace with explicit AskUserQuestion options (`Approve` / `Request changes` / `Cancel`) on the existing call, plus auto-advance flow on Approve (emit `plan_approved` + `phase_transition` events). Register `plan_approved` event in `bin/.events-registry.md` with producer column listing `skills/lifecycle/references/plan.md`.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: `skills/lifecycle/references/plan.md` §4 (lines 275–282). Same pattern as Task 4. The §4 of plan.md does not currently invoke AskUserQuestion in its prose (verified by reading); the explicit AskUserQuestion call should be added so the Approve/Request changes/Cancel options surface materially. Verify before editing: count existing AskUserQuestion call sites with `grep -c "AskUserQuestion" skills/lifecycle/references/plan.md`.
- **Verification**: `grep -c "must approve before implementation begins" skills/lifecycle/references/plan.md` returns 0; `grep "plan_approved" skills/lifecycle/references/plan.md` returns ≥1 match; `grep -E '^\| .plan_approved' bin/.events-registry.md` returns 1 match. Pass if all three conditions hold.
- **Status**: [ ] pending

### Task 6: Enrich SKILL.md resume-staleness prompt
- **Files**: `skills/lifecycle/SKILL.md`
- **What**: At `SKILL.md:106` ("If resuming from a previous session, report the detected phase and offer to continue or restart from an earlier phase"), expand to direct surfacing two specific staleness signals: artifact mtime (computed via `os.path.getmtime` or `stat -c %Y`) and `git log --since="$(stat -c %Y spec.md)" --oneline -- <files-mentioned-in-spec>` count. The "offer to continue or restart" framing remains; the addition is what the prompt should surface.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Single-paragraph addition to existing prose at SKILL.md:106. No new tools or modules introduced — the prose directs the model to invoke standard shell tools when resuming.
- **Verification**: `grep -A8 "If resuming from a previous session" skills/lifecycle/SKILL.md | grep -E "mtime|getmtime|stat" | wc -l` returns ≥1 AND `grep -A8 "If resuming from a previous session" skills/lifecycle/SKILL.md | grep -E "git log|commits-since" | wc -l` returns ≥1. Pass if both conditions hold.
- **Status**: [ ] pending

### Task 7: Auto-skip refine when both research.md and spec.md exist
- **Files**: `skills/refine/SKILL.md`
- **What**: In `skills/refine/SKILL.md:48–62` (Step 2 Check State), replace the "offer to re-run or exit (both artifacts present — spec is complete)" prose with directive to announce that refine is complete and skip to Step 6 (Completion). Re-run is triggered only by explicit user message. No `--rerun` flag introduced.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Single block replacement at `skills/refine/SKILL.md:48–62`. The existing prose at line 49 says "offer to re-run or exit"; replace with skip-to-Step-6 directive. Argument parser unchanged.
- **Verification**: `grep -c "offer to re-run or exit" skills/refine/SKILL.md` returns 0; `grep -A6 "both artifacts exist\|spec.md exists AND" skills/refine/SKILL.md | grep -i "complete\|skip" | wc -l` returns ≥1. Pass if both conditions hold.
- **Status**: [ ] pending

### Task 8: Unify per-phase auto-advance phrasing across plan/implement/review/complete
- **Files**: `skills/lifecycle/references/plan.md`, `skills/lifecycle/references/implement.md`, `skills/lifecycle/references/review.md`, `skills/lifecycle/references/complete.md`
- **What**: Ensure each transition section in the four files contains both literal phrases "Proceed automatically" AND "do not ask the user for confirmation" in the same paragraph. `implement.md:265` already has the canonical phrasing — propagate to the other three. The transition section in each file is at: plan.md §5 (line 284), implement.md §4 (line 244), review.md §5 (line 190), complete.md (end of file). Where the phrase is already present, no edit needed.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Read each transition section first to check current phrasing. The canonical sentence to insert (or preserve): "**Proceed automatically** — do not ask the user for confirmation. Announce the transition briefly and continue." Punctuation between the two literal phrases is unconstrained per R9 acceptance criteria.
- **Verification**: `python3 -c "import pathlib; files=['plan.md','implement.md','review.md','complete.md']; r={f: ('Proceed automatically' in (t:=pathlib.Path(f'skills/lifecycle/references/{f}').read_text()) and 'do not ask the user for confirmation' in t) for f in files}; print(r); assert all(r.values())"` exits 0.
- **Status**: [ ] pending

### Task 9: Phase-detector regression tests
- **Files**: `tests/test_lifecycle_auto_advance.py`
- **What**: New pytest module with seven test cases covering R1, R3, and R4 happy-path + edge cases. Each case constructs a synthetic `lifecycle/{fixture}/` directory in `tmp_path`, writes specific `events.log` + `spec.md`/`plan.md`/`review.md` content, and asserts `detect_lifecycle_phase(str(fixture_dir))` returns the expected phase or cycle. Cases: `happy_path_advances_to_complete`, `specify_blocks_without_approval`, `spec_approval_unlocks_plan`, `migration_sentinel_unlocks_in_flight_spec`, `plan_blocks_without_approval`, `plan_migration_sentinel_unlocks_in_flight`, `cycle_2_changes_requested_escalates`, `cycle_counter_ignores_review_md` (eight cases total — the "plan_approval_gates mirror" from the spec expands into three plan-side cases; renumbered to 8 in implementation).
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: Follow existing test patterns in `tests/test_lifecycle_state.py` or `tests/test_lifecycle_phase_parity.py` for fixture construction. Use pytest `tmp_path` fixture. Import: `from cortex_command.common import detect_lifecycle_phase`. Each test writes minimal artifacts then asserts a single field of the returned dict.
- **Verification**: `just test tests/test_lifecycle_auto_advance.py` exits 0 with 8 passing cases.
- **Status**: [ ] pending

### Task 10: Kept-pauses parity test
- **Files**: `tests/test_lifecycle_kept_pauses_parity.py`
- **What**: Parse the "Kept user pauses" subsection from `skills/lifecycle/SKILL.md` (matching bullet format `- <file>:<rough-line> — <rationale>`). For each entry, open the named file and assert that "AskUserQuestion" appears within ±20 lines of the rough-line anchor. Inversely, for every "AskUserQuestion" mention under `skills/lifecycle/` and `skills/refine/` markdown files, assert there's an inventory entry pointing to a line within ±20 lines. Any mismatch is a test failure. This gives R10 its anti-rot enforcement.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Use `pathlib.Path.glob("skills/lifecycle/**/*.md")` and `glob("skills/refine/**/*.md")` for the AskUserQuestion scan. Parse the inventory section with a regex against the SKILL.md content. Each inventory line: `^- ([^:]+):(\d+) — (.+)$`. Compare line numbers with a tolerance window of 20.
- **Verification**: `just test tests/test_lifecycle_kept_pauses_parity.py` exits 0 with both directions of the parity check passing (inventory→source AND source→inventory).
- **Status**: [ ] pending

## Risks

- **R3 migration sentinel could mask a legitimate stalled-in-specify state**: a feature that genuinely should be re-approved (e.g., spec changed mid-flight) would be auto-treated as approved if a stale `phase_transition: specify→plan` event exists in events.log. Mitigation: this state requires manual intervention via `/cortex-core:lifecycle <phase>` to reset; not in scope here. Document as a known limitation in Task 2's commit message.
- **Plan.md §4 currently does NOT invoke AskUserQuestion**: spec audit assumed it did. Task 5 must add the call, which is a behavior change beyond pure prose. Acceptance is unchanged but implementer should verify before editing.
- **Events-registry parity check may run during commit and require both event types simultaneously**: if Tasks 4 and 5 land separately and the registry validates producer references, intermediate commits may fail. Mitigation: combine Tasks 4 and 5 into a single commit, OR run them in a single PR and tolerate the pre-commit failure on the intermediate task with care.
- **The kept-pauses inventory in Task 3 lists 19 specific sites with file:line anchors that may drift if the source files are reformatted**: Task 10's parity test uses a ±20 line tolerance to absorb minor drift. If line numbers shift by >20 lines, the test fails and the inventory must be updated.
- **The simplified `--rerun` flag drop (R8) may leave refine without a documented re-run path**: per Task 7, re-run is triggered by user message only. This is a UX regression vs. introducing a flag, but consistent with refine's existing conversational style.

## Acceptance

The whole-feature acceptance criterion: after all 10 tasks land, running `/cortex-core:lifecycle <new-feature>` end-to-end exhibits these observable behaviors: (a) Specify and Plan phases each emit exactly one user-facing AskUserQuestion at §4 with options Approve/Request changes/Cancel — no separate "do you approve?" preamble; (b) Implement→Review and Review→Complete transitions emit `phase_transition` events without any user-facing pause when verdict is APPROVED; (c) `detect_lifecycle_phase` correctly routes the lifecycle through `specify → plan → implement → review → complete` consulting both artifact existence and approval events; (d) `just test tests/test_lifecycle_auto_advance.py tests/test_lifecycle_kept_pauses_parity.py` exits 0; (e) `bin/.events-registry.md` lists both `spec_approved` and `plan_approved` with producer references that the registry parity scanner accepts.
