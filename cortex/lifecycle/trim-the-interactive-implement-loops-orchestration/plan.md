# Plan: trim-the-interactive-implement-loops-orchestration

## Overview

Land the spec's mode-agnostic subset in two waves: first the two additive verb-layer changes (a `preferred_remedy` field on advance.py's gate-mismatch refusal; a downgrade-only `--task-complexity` input on `cortex-resolve-model`), then the reference-prose edits folded into exactly one task per file — so each prose file has a single writer and the prose tasks can name the field/flag the verb tasks just defined. The spec's Proposed ADR-0030 is filed as part of the second wave. Key decision: requirement 12's `refused` routing row is written into each file by that file's own task (not a cross-cutting task), keeping Files disjoint per batch at the cost of a three-way wording repetition pinned by per-file grep acceptance.

## Outline

### Phase 1: Verb layer (tasks: 1, 2)
**Goal**: Additive verb changes — gate-mismatch refusals carry a typed re-sync remedy; builder model resolution accepts per-task complexity, downgrade-only.
**Checkpoint**: `uv run pytest tests/test_advance_gate_mismatch_remedy.py tests/test_resolve_model.py` green; no-flag `cortex-resolve-model` output byte-identical to the frozen golden anchor.

### Phase 2: Reference prose & records (tasks: 3, 4, 5, 6, 7)
**Goal**: One-writer-per-file prose edits covering requirements 1–10 and 12, the R13 caller wiring, and the ADR-0030 file.
**Checkpoint**: every spec acceptance grep passes; `uv run pytest tests/test_lifecycle_event_roundtrip.py tests/test_lifecycle_kept_pauses_parity.py tests/test_adr_citation_audit.py` green; net prose addition across implement.md/plan.md/review.md ≤ ~25 lines.

## Tasks

### Task 1: Add `preferred_remedy` to advance.py's gate-mismatch refusal (R11)
- **Files**: `cortex_command/lifecycle/advance.py`, `tests/test_advance_gate_mismatch_remedy.py` (new)
- **What**: The gate-mismatch refusal envelope gains an additive `preferred_remedy` field recommending re-sync — re-run `cortex-lifecycle-next` and thread its `advance_contract.expected_from_state` via `--from-state` — never echoing the detected phase. A new test asserts the payload shape.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The refusal dict is built at `advance.py:995–1008` (`"refusal": "gate-mismatch"`); keep every existing field including `sanctioned_override`. Precedent for the field's shape and tone: `_pause_refusal()`'s `typed_resume` at `advance.py:299–303` (a one-string recommendation naming the sanctioned surface). `--from-state` is honored at `advance.py:905–906` and substituted as `effective_from` at `:947`. Additive field only — never-crash `{state,...}` envelope, `PROTOCOL_VERSION` untouched, no new arm, no transition_table change. The remedy text must name `cortex-lifecycle-next` and `advance_contract.expected_from_state` and must not suggest passing the detected phase. Test fixture pattern: `tests/test_advance_spec_approve_writeback.py` (imports `cortex_command.lifecycle.advance as adv`, builds a temp lifecycle dir with an events.log whose resolved phase mismatches the arm's expected from_state, invokes the arm, asserts on the returned envelope). Assert: `refusal == "gate-mismatch"`, `preferred_remedy` present and naming `cortex-lifecycle-next`, `sanctioned_override` retained.
- **Verification**: `uv run pytest tests/test_advance_gate_mismatch_remedy.py` — passes; `grep -c 'preferred_remedy' cortex_command/lifecycle/advance.py` ≥ 1.
- **Status**: [x] done (9a5b9170 2026-07-20T08:16:07-05:00)

### Task 2: Downgrade-only `--task-complexity` on cortex-resolve-model (R13 verb side)
- **Files**: `cortex_command/lifecycle/resolve_model_cli.py`, `tests/test_resolve_model.py`
- **What**: Optional `--task-complexity` input, valid with `--role builder`: when the (role, criticality) cell resolves `opus` AND the value ∈ {trivial, simple}, return `sonnet`; every other case returns the cell unchanged. Golden tests cover the new lattice edge.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `_LIFECYCLE_MATRIX` at `resolve_model_cli.py:57–67` (builder row: low/medium sonnet, high/critical opus — the downgrade only fires at high/critical). Soft-input contract, a deliberate exception to the module's fail-loud docstring which must be updated to record it: the flag takes a free string — no argparse `choices=` (its violation would `sys.exit(2)` before main runs); validation happens in `main()`: absent → behavior identical to today; any value outside {trivial, simple, complex} → stderr warning + the unchanged cell + exit 0 (inherit, never downgrade, never halt). Floor is sonnet — interactive builders never resolve haiku. Also extend the matrix-separation docstring note (lines 4–10) to mention the task-complexity extension. `bin/cortex-resolve-model` passes `"$@"` through — no stub change. The frozen golden-anchor literal in `test_resolve_model.py` (`test_golden_anchor_matches_frozen_matrix`, line ~198) must stay byte-identical; add new parametrized cases instead.
- **Verification**: `uv run pytest tests/test_resolve_model.py` — green, including new cases: (builder, high, `--task-complexity simple`) → `sonnet`; (builder, high, `complex`) → `opus`; (builder, high, flag absent) → `opus`; (builder, high, bogus value) → `opus` + stderr warning + exit 0; (builder, medium, `simple`) → `sonnet` (unchanged); all pre-existing tests unmodified and passing.
- **Status**: [x] done (2ca4acb6 2026-07-20T08:20:43-05:00)

### Task 3: implement.md — report contract, checkpoint annotation, per-task model, refused row (R1–R4, R12, R13 wiring)
- **Files**: `skills/lifecycle/references/implement.md`
- **What**: Builder template step 5 becomes a final-message exit-report contract enumerating task name, status (completed/partial/failed), files modified, verification outcome, commit hash, deviations; step 3 gains the scoped-verification clause; §2 gains the no-round-trip line naming the §2d git checkpoint as completion authority; §2d's flip becomes `[x] done (<short-sha> <commit-ts>)`; the §2 model block resolves per task passing `--task-complexity`; §4's routing list gains a `refused` row.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: Template step 5 at `implement.md:100`, step 3 at `:98` — step 3 appends "— and only that; do not run broader suites unless the Verification field names them"; the template keeps its 6-step shape (R1 acceptance greps for `commit hash` inside the template). No-round-trip line lands in §2 (natural home: step **c. Wait**, `:62`): the orchestrator never sends follow-up "send your report" messages — the report is the builder's final message in whatever shape the runtime delivers it (tool result or completion notification), and completion is always derived from the §2d git checkpoint, never from return-delivery shape. §2d at `:64–68`: the flip line becomes `[x] done (<short-sha> <commit-ts>)` — the sha §2d just verified plus its committer timestamp via `git log -1 --format=%cI <sha>`; rework re-checkpoints (§3) update the annotation to the newest verifying sha. Model block at `:48–54`: resolve inside the per-task dispatch loop, passing each task's `Complexity` field via `--task-complexity` (absent/malformed field → the verb inherits the feature cell; keep halt-on-nonzero-exit). §4 list at `:123–127` gains a `refused` row: relay the envelope's `reason` and `preferred_remedy`, re-run `cortex-lifecycle-next`, re-invoke threading `advance_contract.expected_from_state` via `--from-state`; mismatch persists after re-sync → escalate to the operator with detected phase + expected from_state; never pass the detected phase. Hard constraints: kept-pause markers at `:23` and `:81` byte-untouched; no raw event-emission surface (zero-sweep); halt-arm comments at `:60`/`:129` untouched; imperative/SHOULD phrasing only, no MUST escalation; net addition ≤ ~10 lines.
- **Verification**: in `skills/lifecycle/references/implement.md`: `grep -c 'commit hash'` = 1, `grep -c 'follow-up'` ≥ 1, `grep -c 'done (<short-sha> <commit-ts>)'` = 1, `grep -c 'only that'` = 1, `grep -c 'task-complexity'` ≥ 1, `grep -c 'preferred_remedy'` ≥ 1; `uv run pytest tests/test_lifecycle_event_roundtrip.py tests/test_lifecycle_kept_pauses_parity.py` — green.
- **Status**: [x] done (5fb33ce9 2026-07-20T08:28:25-05:00)

### Task 4: plan.md reference — three authoring bullets + refused row (R5–R7 bullets, R12)
- **Files**: `skills/lifecycle/references/plan.md`
- **What**: Authoring rules gain straggler-isolation, hub-file-seam, and dress-rehearsal bullets; §4's routing list gains the `refused` row.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Authoring rules section at `plan.md:66–89`. Bullet 1 (must contain the word "straggler"): when the dependency graph allows, don't co-batch a `complex` task with `trivial`/`simple` siblings at the same topological level — split levels so heavy tasks occupy their own wave. Bullet 2 (hub-file seam): when ≥3 tasks would edit one coordinator file, an early task gives it a registration seam so later tasks add files instead of serializing edit chains. Bullet 3 (must contain "rehearsal"): a task that builds a capture/evidence rig must produce and validate a discarded sample of the exact committed-evidence shape end-to-end. §4's "Act on the returned `state`" list (after the `error` row, `:129–137`) gains a `refused` row with the same content shape as Task 3's (relay `reason` + `preferred_remedy`, re-run `cortex-lifecycle-next`, thread the served `advance_contract.expected_from_state`, escalate on persist; never the detected phase). Hard constraints: `plan-approval` kept-pause marker at `:109` byte-untouched; zero-sweep; net addition ≤ ~7 lines.
- **Verification**: in `skills/lifecycle/references/plan.md`: `grep -c 'straggler'` ≥ 1, `grep -c 'rehearsal'` ≥ 1, `grep -c 'preferred_remedy'` ≥ 1; `uv run pytest tests/test_lifecycle_event_roundtrip.py tests/test_lifecycle_kept_pauses_parity.py` — green.
- **Status**: [x] done (861f09b2 2026-07-20T08:32:20-05:00)

### Task 5: orchestrator-checklist-plan.md — P11, P12 rows + P7 carve-out (R6–R8)
- **Files**: `skills/lifecycle/references/orchestrator-checklist-plan.md`
- **What**: Two new mechanical checklist rows (P11 hub-file, P12 trivial-consistency) and a rehearsal carve-out amending P7's criteria.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The `| # | Item | Criteria |` table at `:5–16`; criteria must be binary-checkable (header rule, shared protocol in `orchestrator-review.md`). P11: flag any file appearing in ≥3 tasks' `Files` lists with no early seam task and no serializing `Depends on` chain. P12: flag any task tagged `trivial` whose What/Verification implies a commit — plan.md defines `trivial` as no-commit and the interactive loop fails zero-commit tasks at §2d; remedy is retag `simple`. P7 amendment (must mention the rehearsal carve-out): a rig task's validated-discarded-sample rehearsal is the primary-deliverable exercise, not a self-sealing flag. No new judgment row for rigs.
- **Verification**: in `skills/lifecycle/references/orchestrator-checklist-plan.md`: `grep -c 'P11'` = 1, `grep -c 'P12'` = 1, `grep -c 'rehearsal'` ≥ 1 (in the P7 row).
- **Status**: [x] done (601f424f 2026-07-20T08:22:50-05:00)

### Task 6: review.md — single-writer rule, shared test baseline, refused row (R9, R10, R12)
- **Files**: `skills/lifecycle/references/review.md`
- **What**: A role-scoped single-writer rule for review.md; a run-once orchestrator test baseline injected into the reviewer template; the `refused` routing row in §5.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Single-writer rule (grep target: "only the reviewer"): only the reviewer role writes `cortex/lifecycle/{feature}/review.md` — explicitly including §4's missing-drift re-dispatch (`:67`) and §4a's cap-2 re-dispatches (`:89`) as the same authorized role; any sub-agent a reviewer spawns is dispatched read-only and returns findings as a message envelope (the `skills/critical-review/` findings-envelope precedent), never file writes. Natural home: the §2 dispatch step or the header constraint block. §4/§4a retry semantics must stay textually unchanged. Test baseline (R10, grep target "Test Baseline" — needed ≥2 times): §1 gains an orchestrator step — run the configured `test-command` from `cortex/lifecycle.config.md` (`just test` here) once, capture a pass/fail summary plus a log path; the §2 Reviewer Prompt Template gains a `## Test Baseline` slot carrying summary + log path (never the full transcript); staleness rule: implementation commits after the baseline → the orchestrator re-runs once and replaces it; the reviewer and its sub-agents consume the baseline and never re-run the full suite. §5's "Act on the returned `state`" list (`:101–108`) gains the `refused` row (same content shape as Task 3's). Hard constraints: no kept-pause markers exist in this file — add none; zero-sweep; imperative/SHOULD phrasing, no MUST escalation; net addition ≤ ~8 lines.
- **Verification**: in `skills/lifecycle/references/review.md`: `grep -c 'Test Baseline'` ≥ 2, `grep -c 'only the reviewer'` ≥ 1, `grep -c 'preferred_remedy'` ≥ 1; `uv run pytest tests/test_lifecycle_event_roundtrip.py` — green.
- **Status**: [x] done (d41353e3 2026-07-20T08:36:35-05:00)

### Task 7: File ADR-0030 mode-agnostic-interactive-dispatch
- **Files**: `cortex/adr/0030-mode-agnostic-interactive-dispatch.md`
- **What**: File the spec's Proposed ADR as a numbered ADR with `status: proposed`, recording the mode-agnostic dispatch decision and its deferrals (pipelining, `task_complete`).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Content source: spec.md §Proposed ADR (`cortex/lifecycle/trim-the-interactive-implement-loops-orchestration/spec.md`, "Proposed ADR: 0030-mode-agnostic-interactive-dispatch") — carry its substance: report-in-final-message, completion from the git checkpoint never return-delivery shape, upstream version history (background-by-default ≥v2.1.198, report-bearing notifications ≥v2.1.211, only synchronous pinnable with session-wide collateral), consequences (pipelining and `task_complete` deferred until upstream stability + a measured case surviving token accounting; batch barrier stays), and the accepted trade-off. Format precedent: `cortex/adr/0029-per-pattern-side-ruling-for-sync-allowlist-conflicts.md` — YAML frontmatter `status: proposed`, H1 title, italic decision-date line citing the lifecycle (#401, 2026-07-20), `## Context`, `## Decision`. Numbering: 0030 is next after 0029 (no gap, no duplicate — the ADR citation audit checks both).
- **Verification**: `uv run pytest tests/test_adr_citation_audit.py` — green; `grep -c 'status: proposed' cortex/adr/0030-mode-agnostic-interactive-dispatch.md` = 1.
- **Status**: [x] done (1d8cd2aa 2026-07-20T08:24:32-05:00)

## Risks

- **Refused-row triplication**: the same routing row lands in three files by three tasks; wording may drift between copies. Accepted — each row is one line, the content shape is specified identically in each task, and per-file greps pin the load-bearing tokens. The alternative (a shared reference file) adds a read hop and a new file against the prose budget.
- **R13 is the spec's droppable should-have**: if dropped at approval, Task 2 is removed and Task 3 loses only its model-block edit (its `Depends on` becomes `[1]`); Phases 1–2 are otherwise unaffected.
- **Prose budget (≤ ~25 net lines across implement.md/plan.md/review.md)** is enforced by orchestrator review and per-task budgets, not by any test — reference growth is invisible to the suite.

## Acceptance

All 13 spec requirements' acceptance checks pass (greps + the new pytest cases); `just test` shows no new failures relative to the pre-implementation baseline; no-flag `cortex-resolve-model` output stays byte-identical to the frozen golden anchor; kept-pauses parity and zero-sweep tests pass untouched; `plugins/cortex-core/` mirrors regenerate cleanly via the pre-commit hook on each commit.
