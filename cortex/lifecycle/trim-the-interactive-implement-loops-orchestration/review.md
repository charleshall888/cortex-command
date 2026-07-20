# Review: trim-the-interactive-implement-loops-orchestration

Reviewer role. Implementation: `9a5b9170..d41353e3` (7 commits, all tagged #401). Test baseline consumed from the orchestrator's single `just test` run (see `## Test Baseline` below) — not re-run in full here; only narrow, targeted commands were used to check acceptance criteria.

## Test Baseline

7 of 8 arms PASS (test-pipeline, test-init, test-install, tests, tests-lifecycle-backlog-cortex, tests-dashboard, tests-takeover-stress). FAIL: `test-overnight`, exactly one failing test — `cortex_command/overnight/tests/test_scheduler_bootout_on_fire.py::test_launcher_boots_out_own_label_after_started_fire` (1 failed, 644 passed in that arm). Pre-existing: predates this feature's commits, reproduces in isolation, and its surface (overnight launchd scheduler) is untouched by the diff. Log: `/private/tmp/claude-501/-Users-charliehall-Workspaces-cortex-command/85ebb919-d7d7-4fe9-ae27-3e0b735a60df/scratchpad/test-baseline-401.log`.

Targeted re-verification run during this review (all green): `tests/test_advance_gate_mismatch_remedy.py`, `tests/test_resolve_model.py`, `tests/test_lifecycle_event_roundtrip.py`, `tests/test_lifecycle_kept_pauses_parity.py`, `tests/test_adr_citation_audit.py` — 92 passed, 0 failed.

## Stage 1 — Spec Compliance

| # | Requirement | Verdict |
|---|---|---|
| R1 | Builder exit-report contract in the final message | PASS |
| R2 | No-round-trip rule | PASS |
| R3 | Commit-sha completion annotation | PASS |
| R4 | Scoped verification line | PASS |
| R5 | Straggler-isolation authoring rule | PASS |
| R6 | Hub-file seam rule + checklist row (P11) | PASS |
| R7 | Dress-rehearsal rule with P7 carve-out | PASS |
| R8 | Trivial-consistency checklist row (P12) | PASS |
| R9 | Review single-writer rule (role-scoped) | PASS |
| R10 | Shared test baseline (run-once) | PASS |
| R11 | Gate-mismatch re-sync remedy | PASS |
| R12 | `refused` routing rows (implement.md/plan.md/review.md) | PASS |
| R13 | Per-task builder tiering (downgrade-only) | PASS |

**R1** — `implement.md` Builder Prompt Template step 5 reads "Report as your final message: task name, status (completed/partial/failed), files modified, verification outcome, commit hash, deviations." `grep -c 'commit hash'` = 1; the template block still has its original 6 numbered steps.

**R2** — §2c: "Send no follow-up 'send your report' messages: the report is the builder's final message in whatever shape the runtime delivers it (tool result or completion notification), and completion is always derived from the §2d git checkpoint, never from return-delivery shape." `grep -c 'follow-up'` = 1, names the §2d checkpoint as completion authority.

**R3** — §2d: "flip `[ ]` → `[x] done (<short-sha> <commit-ts>)` for every task that succeeded — the sha just verified plus its committer timestamp from `git log -1 --format=%cI <sha>`." `grep -c 'done (<short-sha> <commit-ts>)'` = 1. Confirmed dogfooded correctly: `plan.md`'s own per-task `Status` lines use exactly this shape, and every recorded `<sha> <timestamp>` pair matches `git log -1 --format=%cI <sha>` for the corresponding commit.

**R4** — Template step 3: "Verify your implementation per the Verification field — and only that; do not run broader suites unless the Verification field names them." `grep -c 'only that'` = 1, inside the template.

**R5** — plan.md Authoring rules gains "**Straggler isolation** — when the dependency graph allows, don't co-batch a `complex` task with `trivial`/`simple` siblings at the same topological level; split levels so a heavy straggler occupies its own wave rather than idling a batch barrier." `grep -c 'straggler'` = 1.

**R6** — plan.md gains "**Hub-file seam** — when ≥3 tasks would edit one coordinator file, give it a registration seam in an early task so later tasks add files instead of serializing edit chains." `orchestrator-checklist-plan.md` gains row P11 with the mechanical criteria verbatim from the spec. `grep -c 'P11'` = 1.

**R7** — plan.md gains "**Dress rehearsal** — a task that builds a capture/evidence rig must produce and validate a discarded sample of the exact committed-evidence shape end-to-end." (`grep -c 'rehearsal'` = 1). P7's row gains the carve-out sentence verbatim ("a rig task's validated-discarded-sample rehearsal is the primary-deliverable exercise, not a self-sealing flag") — no new judgment row added, as directed.

**R8** — `orchestrator-checklist-plan.md` gains row P12, mechanical criteria matching the spec exactly, citing the pre-existing `trivial` = no-commit definition in plan.md's Complexity table. `grep -c 'P12'` = 1.

**R9** — review.md §2 gains "**Single-writer rule** — only the reviewer role writes `cortex/lifecycle/{feature}/review.md`: this reviewer sub-task plus §4's missing-drift re-dispatch and §4a's cap-2 re-dispatches are the same authorized role; any sub-agent the reviewer spawns is dispatched read-only and returns findings as a message envelope (the `skills/critical-review/` findings-envelope precedent), never file writes." §4 and §4a bodies are byte-identical before/after (diffed directly against pre-implementation `review.md` — no textual change).

**R10** — review.md §1 gains a "**Test Baseline**" step (run-once `test-command`, summary + log path, staleness re-run rule); the Reviewer Prompt Template gains a `## Test Baseline` slot. `grep -c 'Test Baseline'` = 2.

**R11** — `advance.py`'s gate-mismatch refusal dict gains an additive `preferred_remedy` field: "re-sync: re-run cortex-lifecycle-next and thread its advance_contract.expected_from_state through --from-state (the sanctioned re-sync — never pass the detected phase)." Shape matches the `_pause_refusal()` `typed_resume` precedent. `sanctioned_override` retained. New test `tests/test_advance_gate_mismatch_remedy.py` asserts exactly this — passes (1/1).

**R12** — Identical `refused` row added to all three files' "Act on the returned `state`" lists (implement.md §4, plan.md §4, review.md §5), byte-for-byte identical across all three: relays `reason`/`preferred_remedy`, re-runs `cortex-lifecycle-next`, threads `advance_contract.expected_from_state` via `--from-state`, escalates on persistent mismatch, never advertises the detected phase. `grep -c 'preferred_remedy'` = 1 in each file, inside the state-routing list.

**R13** — `resolve_model_cli.py` gains `--task-complexity` (no `choices=`, validated in `main()`): absent → unchanged; `{trivial, simple}` on an `opus` cell → `sonnet`; everything else → unchanged; out-of-set value → stderr warning naming the bad value + unchanged cell + exit 0. Golden anchor test (`test_golden_anchor_matches_frozen_matrix`) untouched and passing; new parametrized cases cover every spec-named case including the low/medium no-op and the bogus-value warn-and-inherit path. `implement.md`'s §2 model block passes `--task-complexity "<task Complexity>"` (`grep -c 'task-complexity'` = 2). `bin/cortex-resolve-model` unchanged (still a bare `"$@"` passthrough).

**Non-Requirements** — confirmed absent from the diff: no `task_complete` event, no `bin/.events-registry.md` change, no `implement_transition.py` change, no `PROTOCOL_VERSION` touch in `advance.py` (single additive field only), no report-file/SendMessage/SubagentStop-hook prose, no `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`/Agent Teams mention, no `kept-pauses-data.toml` change (markers at implement.md:23/81 and plan.md:115 byte-untouched; `tests/test_lifecycle_kept_pauses_parity.py` green), no prose model literals (`haiku|sonnet|opus`) added to any reference file, no reuse of the pipeline `_MODEL_MATRIX`, no verification-execution tooling, and no `--from-state <detected>` advertisement (the added rows explicitly say "never pass the detected phase").

**Stage 1 result: no FAIL.** Proceeding to Stage 2.

## Stage 2 — Code Quality

**Soft-input contract vs. fail-loud docstring** — `resolve_model_cli.py`'s module docstring records the deliberate exception in full (lines 34–42: "Soft-input exception — `--task-complexity` ... is the one input that does NOT fail loud..."), so a future reader hits the rationale before the fail-loud list below it could otherwise mislead them. The `--task-complexity` argparse help string repeats the contract concisely. Consistent.

**Refused-row wording** — the three copies in implement.md/plan.md/review.md are byte-identical (`diff` confirms no drift), stronger than the plan's accepted "wording may drift between copies" risk.

**Kept-pause markers** — `implement-branch-pick` (implement.md:23), `implement-batch-failure` (implement.md:81), and `plan-approval` (plan.md:115) markers are untouched; `tests/test_lifecycle_kept_pauses_parity.py` passes.

**Prose budget** — net line deltas (git diff numstat, insertions − deletions): implement.md +1, plan.md +7, review.md +8 → 16 net lines total across the three files, versus a target of ≤ ~25. Comfortably under budget, and each file is at or under its own per-task sub-budget (implement.md ≤10, plan.md ≤7, review.md ≤8).

**Naming/pattern consistency** — P11/P12 follow the existing `P<n> | Item | Criteria` table convention; the new plan.md Authoring-rules bullets follow the file's existing `**Bold label** — description.` idiom and are placed at logically coherent points (Straggler isolation/Hub-file seam after Dependencies; Dress rehearsal after Code budget/self-sealing verification). ADR-0030 follows the ADR-0029 frontmatter/heading precedent exactly and is the next unused number (no gap, no duplicate) — `tests/test_adr_citation_audit.py` passes (11/11).

**Test coverage vs. plan verification steps** — every task's verification command was executed and passes: Task 1 (`test_advance_gate_mismatch_remedy.py`), Task 2 (`test_resolve_model.py`, including the byte-identical golden anchor), Tasks 3/4/6 (per-file greps plus `test_lifecycle_event_roundtrip.py`/`test_lifecycle_kept_pauses_parity.py`), Task 5 (checklist greps), Task 7 (`test_adr_citation_audit.py`). The dual-source mirrors under `plugins/cortex-core/skills/lifecycle/references/` are byte-identical to their canonical sources for all four touched files.

**Error handling** — `resolve_model_cli.py`'s new branch preserves every existing fail-loud exit-2 path (role/criticality validation runs before the task-complexity branch is reached) and adds no new halting path; the never-halt soft-input contract is upheld for every tested value including absent and out-of-set.

**Stage 2 result: no issues found.**

## Requirements Drift

**State**: none

**Findings**: None. The change stays inside architectural boundaries the requirements docs and prior ADRs already establish: the `preferred_remedy`/`refused` addition is a refinement of the already-documented served-lifecycle-verb-class contract (`project.md` "Served lifecycle verb class" → ADR-0024/ADR-0025); the `--task-complexity` downgrade-only tiering extends the interactive lifecycle's `_LIFECYCLE_MATRIX`, whose separation from the overnight pipeline matrix in `multi-agent.md`'s Model Selection Matrix (including its "no downgrade path" escalation-ladder language, which is scoped to the overnight session's error-recovery ladder, a different mechanism) was already established by ADR-0023 and was re-confirmed non-binding during this feature's research phase (`research.md` §Requirements & Constraints: "does not bind the interactive loop"). ADR-0030 itself is filed per the repo's ADR discipline (canonical home for the decision; requirements docs are not required to restate it — many prior ADRs, including the closely analogous ADR-0023, also carry no `project.md` back-pointer, so its absence here is consistent with precedent, not a gap).

**Update needed**: None

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
