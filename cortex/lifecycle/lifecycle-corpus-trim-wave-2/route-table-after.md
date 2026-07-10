# Route-Table Recompute — lifecycle-corpus-trim-wave-2 (Task 13 / spec R13)

Closeout measurement of per-route **loaded bytes** after the token-reduction wave.
Method: `wc -c` over the **unique** set of files each route instructs reading today,
tracing `skills/lifecycle/SKILL.md` and the reference topology (research.md
"Codebase Analysis" method). A file read once is counted once — the shared
protocol / always-on set is not double-charged when a gate fires twice.

The **before** column is reconstructed at the pre-campaign commit `36113812`
(skills untouched until `966867dc`) and reproduces research.md's baselines
exactly (A=99,449, C=28,372, D=25,295, F=19,492, always-on=11,927) — confirming
the file lists and byte method are sound.

Targets are **decimal KB** (KB = 1000 B), as fixed by plan.md's byte-carryover
arithmetic (line 96: "SKILL.md+backlog-writeback … vs the 9,000B target") and
the spec R13 `−X%`-of-baseline framing. Every target below is also missed under
the KiB reading (×1024).

## Route table (before / after / target / met?)

| Route | Files | Before | After | Δ | Δ% | Target | Met? |
|---|---|---|---|---|---|---|---|
| **A** — new feature, trunk, complex, first-run | 18 | 99,449 | 91,721 | −7,728 | −7.8% | ≤84,000 (−15%) | **NO** (+7,721) |
| **C** — resume at plan | 6 | 28,372 | 25,167 | −3,205 | −11.3% | ≤21,000 (−26%) | **NO** (+4,167) |
| **D** — resume at implement | 4 | 25,295 | 18,744 | −6,551 | −25.9% | ≤16,000 (−37%) | **NO** (+2,744) |
| **F** — complete finalize re-invocation | 3 | 19,492 | 14,859 | −4,633 | −23.8% | ≤12,000 (−38%) | **NO** (+2,859) |
| **Always-on** — every route | 2 | 11,927 | 9,693 | −2,234 | −18.7% | ≤9,000 (−25%) | **NO** (+693) |

All five funded targets are **MISSED**. Per the Task 13 instruction, no cuts are
forced to hit the numbers — the honest measurement is recorded for operator
review at the phase gate. Shortfall analysis below.

## File lists per route (after)

**A — new feature, trunk, complex, first-run** (91,721 B):
`SKILL.md` 7,736 · `backlog-writeback.md` 1,957 · `refine-delegation.md` 5,285 ·
refine `SKILL.md` 8,319 · refine `clarify.md` 5,970 · `load-requirements.md` 967 ·
refine `clarify-critic.md` 8,578 · refine `research-phase.md` 2,918 ·
refine `specify.md` 12,423 · `orchestrator-review.md` 2,577 ·
`orchestrator-checklist-specify.md` 1,225 · `orchestrator-checklist-plan.md` 1,699 ·
`criticality-matrix.md` 1,897 · `plan.md` 9,301 · `implement.md` 7,154 ·
`review.md` 5,998 · `complete-first-run.md` 2,586 · `complete.md` 5,166.
(worktree-entry.md **not** loaded on trunk.)

**C — resume at plan** (25,167 B):
`SKILL.md` 7,736 · `backlog-writeback.md` 1,957 · `plan.md` 9,301 ·
`criticality-matrix.md` 1,897 · `orchestrator-review.md` 2,577 ·
`orchestrator-checklist-plan.md` 1,699.

**D — resume at implement** (18,744 B):
`SKILL.md` 7,736 · `backlog-writeback.md` 1,957 · `implement.md` 7,154 ·
`criticality-matrix.md` 1,897.

**F — complete finalize re-invocation** (14,859 B):
`SKILL.md` 7,736 · `backlog-writeback.md` 1,957 · `complete.md` 5,166.
(complete-first-run.md **not** loaded on re-invocation.)

**Always-on** (9,693 B): `SKILL.md` 7,736 · `backlog-writeback.md` 1,957.

## Shortfall analysis

The structural levers landed; the word-level levers under-delivered against the
funding arithmetic.

**What delivered (structural offload / merges):**
- `implement.md` 11,471 → 7,154 (−4,317): worktree machinery moved to
  `worktree-entry.md`, which trunk (A) and resume-at-implement (D) never load.
- `complete.md` on the finalize route 7,565 → 5,166 (−2,399): first-run PR flow
  split to `complete-first-run.md`, which route F never loads.
- `backlog-writeback.md` 3,452 → 1,957 (−1,495): prose recipes collapsed to the
  `cortex-lifecycle-enter` / `-finalize` / `-register-artifact` verb one-liners.
- delegation merge 6,062 (4 files) → 5,285 (1 file, −777).
- `SKILL.md` 8,475 → 7,736 (−739).

**Why every target still misses:**

1. **Word-level yields came in ~5–6 KB below the funding assumption.** The
   refine corpus (held at floor, safe cuts only) moved barely: refine `SKILL.md`
   −212, `clarify-critic.md` −384, `specify.md` −186, `clarify.md`/`research-phase.md`
   ≈ 0. `criticality-matrix.md` 0, `review.md` −24. The clause-parity review
   (Task R13 compression-diff) correctly bounded these — but the R13 route
   targets were funded assuming deeper word-level compression than clause parity
   permits. The plan's own risk register (line 142) flagged this exact mode
   ("if word-level yields land low … the '−15%' narrative thins") but sized the
   slack at 2–3 KB; the real word-level shortfall on route A is ~7.7 KB.

2. **The always-on residual propagates into every route.** plan.md line 96
   budgeted Tasks 8+10 to bring `SKILL.md`+`backlog-writeback.md` from 10,162 B
   to the 9,000 B target (−1,162 B). They delivered −469 B (to 9,693 B); the
   remaining 693 B needs SKILL.md word-level compression the clause-parity review
   did not fund. Because every route includes the always-on set, no route can
   reach its target without first closing this 693 B gap.

3. **Route A is penalized by both splits it can't benefit from.** As the
   full-run route it loads *both* halves of each split, paying the split-header
   overhead (orchestrator: 5,363 → 2,577+1,225+1,699 = 5,501, **+138**;
   complete first-run: 7,565 → 5,166+2,586 = 7,752, **+187**) without the
   route-exclusivity benefit that the splits buy the partial routes (C, F). The
   splits are a net win *only* where a route loads one half — exactly the −35–45%
   band routes (D, F) the spec named as the real deliverable, which came closest
   (D −25.9%, F −23.8%) but still fell short of their aggressive −37%/−38% ceilings.

**Reconciliation gap.** The R13 route ceilings were set top-down (−X% of
baseline); the per-task cut floors were set bottom-up (what clause parity deems
safe). They do not reconcile: e.g. `implement.md` met its own task-level floor
(Task 5 wanted ≤7,400; delivered 7,154) yet route D still misses 16,000 because
the target implied further compression of surviving `SKILL.md`/`criticality-matrix.md`
prose that no task was scoped to make safely. Closing the gap would require a
new, deeper compression pass on the refine corpus and always-on set beyond this
wave's clause-parity envelope — an operator decision at the gate, not a forced
cut here.

## End-to-end drives

**Drive 1 — worktree route, both entry seams (static conformance): PASS.**
- `implement.md` §1 routes **both** worktree seams to an imperative
  `worktree-entry.md` read: the `resolved` → `worktree-interactive` arm (L20,
  "record the returned `entry_mode` … then read … worktree-entry.md and follow
  it") and the picker `prompt` → worktree selection (L21, "record entry mode
  `selected`, then read … worktree-entry.md and follow it").
- `worktree-entry.md` carries the full Step v sequence in the pinned order:
  op 1 `_origin_pwd=$(pwd)` → op 2 suppressed-picker structural branch (emitting
  the stable literal `EnterWorktree skipped: suppressed-picker (branch-mode
  worktree-interactive)`) → op 3 `cortex-worktree-precondition` → op 4
  `EnterWorktree(path=…)` → op 5 `cortex-lifecycle-event interactive-worktree-entered`.
  The `selected` / `suppressed` branch is internal to the extracted file; §1 hands
  off only the entry-mode marker. Order and labels (i–vii, the intentional i→v gap)
  intact.

**Drive 2 — complete re-invocation → finalize verb (real verb, disposable fixture): PASS.**
- `complete.md` Step 7 (`cortex-lifecycle-complete-route`) routes `on_main` /
  `merged_clean_ancestor` to Step 9, which calls
  `cortex-lifecycle-finalize --feature {slug} --backend {resolved-backend}
  --backlog-file {backlog-filename}`.
- Ran the actual verb against a minimal tmp fixture
  (`cortex/lifecycle/<slug>/{plan.md,events.log}`):
  `python -m cortex_command.lifecycle.finalize --feature <slug> --backend none
  --backlog-file ""` → exit 0, envelope
  `{"state":"finalized",…,"emitted":true}`, and the emitted events.log row is:
  `{"ts": …, "event": "feature_complete", "feature": …, "tasks_total": 0,
  "rework_cycles": 0, "merge_anchor": "merge"}` — **`merge_anchor: "merge"`
  present**. A second invocation emitted no duplicate (`feature_complete` row
  count stayed 1), confirming the idempotent guard.

## Full suite

`just build-plugin` clean; `git status --porcelain plugins/` empty after rebuild.
`just test`: 6/7 clusters PASS. The single failure is the **documented sandbox
baseline** — `tests/test_mcp_subprocess_contract.py::test_plugin_path_mismatch_exits_nonzero`,
a pypi.org DNS lookup blocked by the sandbox (passes with network:
`uv run pytest tests/` → 2280 passed, 0 failed). The order-dependent
`test_templates`/`feature_cards` pollution pair did not fire this run
(tests-dashboard PASS). No regressions.

Two **campaign-caused** test failures were surfaced and fixed in this task (they
pre-dated Task 13 but were left by earlier structural commits):
- `tests/test_complete_index_sync_gate.py` — pinned `### Step 10 — Backlog
  Index Sync`, a section the wave **deliberately removed** (spec R6/R8: index
  regen moved into the backend-gated finalize verb). The guarded contract is now
  fully covered Python-side by `test_finalize.py`
  (`test_backend_none_skips_writeback_but_emits`, `test_external_backend_state`,
  `test_cortex_backlog_updates_the_item`). Deleted the superseded structural
  test — consistent with the wave's "replace prose-structural tests with verb
  tests" pattern.
- `tests/test_skill_handoff.py::test_canonical_skill_handoff_fields_present` —
  the handoff schema requires `discovery_source` in skill `refine`; Task 11's
  `research-phase.md` path-guard rewrite dropped the literal when redirecting the
  pointer to `refine-delegation.md`. Restored the `discovery_source`/`research`
  literal in the path guard while keeping the refine-delegation.md cross-reference.
