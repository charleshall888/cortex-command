# Research: Multi-step Complete phase + manage interactive feature worktree lifecycle

Original #239 scope: provide both ends of the long-lived interactive feature worktree lifecycle (creation when the user selects preflight option 2, cleanup gated on PR-merged-and-clean state).

Scope expanded mid-Spec to also restructure the lifecycle's Complete phase so it fires AFTER PR merge — but on a second iteration the user explicitly rejected a new "Submit" phase (R1) in favor of a **multi-step Complete with a mid-phase merge-wait pause**. Complete becomes a single phase with sequential steps; the user re-invokes `/cortex-core:lifecycle complete <slug>` once the PR is merged on GitHub; the phase does not finalize (no `feature_complete` event emitted) until cleanup is done.

This research had two prior shapes — the original "cleanup-trigger-mechanism inside today's lifecycle" (T1-T6 taxonomy) and the R1 "new Submit phase" framing. Both were materially invalidated by interview decisions. This document reflects the final committed direction.

## Codebase Analysis

### Today's Complete phase responsibilities (`skills/lifecycle/references/complete.md`)

1. Run tests (§1) — `cortex/lifecycle.config.md` `test-command`.
2. Log `feature_complete` event (§2) — fires before git workflow.
3. Backlog write-back: `status=complete` (§2) — `cortex-update-item {slug} status=complete session_id=null`.
4. Backlog index sync (§2).
5. Close backlog item (§3) — fallback for unmatched item.
6. Git workflow (§4) — commit lifecycle artifacts; push branch + create PR; or no-op on main.
7. Summarize (§5).
8. Preserve lifecycle directory (§6).

### Multi-step Complete responsibilities (after restructure)

Complete becomes a single phase with the following sequential steps:

1. **Run tests** — same as today.
2. **Commit lifecycle artifacts** — `/cortex-core:commit`.
3. **Push branch + create PR** — `/cortex-core:pr`.
4. **Write `cortex/lifecycle/{slug}/pr.json`** — `{number, url, head_branch, opened_at}` (atomic via tempfile + `os.replace`).
5. **Emit `pr_opened` event** to events.log so statusline + detector can render "Complete (awaiting merge)".
6. **Pause** — exit with handoff message: *"PR open at <url>; merge on GitHub, then re-run `/cortex-core:lifecycle complete <slug>` to finalize."*
7. *(re-invocation)* Detect state via `gh pr view <number> --json state,mergedAt` (idempotent + state-aware fallback per Adversarial §5/§6). Routes:
   - PR not yet merged → exit with "merge first" message (same pause as step 6).
   - PR merged + dirty worktree → exit with "uncommitted changes at <path>; resolve first" message.
   - PR merged + clean worktree → continue to step 8.
   - `feature_wontfix` event in events.log → exit with "lifecycle was wontfix'd at <ts>; nothing to complete" message.
   - Already-`feature_complete` in events.log → short-circuit to summary (no duplicate event, no re-cleanup).
8. **Worktree cleanup** (interactive prefix only): `cleanup_worktree(slug, branch="interactive/{slug}")` with primitive fixes M1/M2/M5 applied. No-op for option 1 / option 3 (no worktree to clean).
9. **Backlog write-back**: `cortex-update-item {slug} status=complete session_id=null`.
10. **Backlog index sync**: `cortex-generate-backlog-index` (or fallback chain).
11. **Log `feature_complete`** event (with new `merge_anchor: "merge"` field).
12. **Summarize + preserve lifecycle directory**.

### Files affected (multi-step Complete shape — much smaller than R1)

**Skill prose (canonical; plugin mirrors auto-regenerate)**:
- `skills/lifecycle/references/complete.md` — substantial rewrite to add the multi-step structure described above.
- `skills/lifecycle/references/implement.md` — option 2 of the preflight menu invokes worktree creation; option 2's body grows by ~10 lines to call `create_worktree()` and return the worktree path for downstream (#240's) dispatch.
- `skills/lifecycle/SKILL.md:189-200` — Kept user pauses inventory adds one entry for the merge-wait pause inside Complete (categorically new: "phase-exit pause", not an `AskUserQuestion` site).

**NOT affected** (vs. R1 — these are the ~25 saved files):
- No `skills/lifecycle/references/submit.md` (no new phase).
- No new phase enum entry in `skills/lifecycle/SKILL.md:8` line 8 or table line 95.
- No `cortex_command/common.py` detector changes for a new phase — `phase=complete` is still triggered by `feature_complete` event presence; the detector adds optional rendering of "complete (awaiting merge)" via `pr_opened` marker but does not restructure phase routing.
- No `cortex_command/pipeline/review_dispatch.py` changes for overnight reconciliation — the mode-aware-vs-uniform-enum question evaporates because there's no new phase to reconcile.
- No `tests/test_lifecycle_phase_parity.py` GLUE_FIXTURES rewrite.
- No docs phase-diagram updates across `docs/agentic-layer.md`, `docs/interactive-phases.md`, `docs/skills-reference.md`, `docs/setup.md`, `docs/dashboard.md`, `docs/backlog.md`, `docs/index.html:5785`.
- No `claude/statusline.sh:244-247` phase-detection ladder for a new phase (statusline still gets a renderer tweak for the awaiting-merge sub-state, smaller change).

**Worktree creation (original #239 scope, narrow)**:
- `skills/lifecycle/references/implement.md` option 2 — calls `cortex-worktree-resolve interactive/{slug}` and `create_worktree(feature="interactive-" + slug, base_branch="main")` to materialize the worktree. Returns path. The cd-mid-flight or fresh-session dispatch is **#240's territory**, not #239's. Epic #237 already locked Variant A (cd-mid-flight).
- `cortex_command/pipeline/worktree.py:191-307` `create_worktree()` — primitive works for any feature string; no functional changes needed for creation. M5 fix generalizes `_resolve_branch_name()` to accept the `interactive/{slug}` prefix (currently hardcodes `pipeline/{feature}` collision suffix logic).

**Cleanup primitive fixes (absorbed per user decision)**:
- `cortex_command/pipeline/worktree.py:309-371` `cleanup_worktree()`:
  - **M1**: replace `_repo_root()` with main-worktree lookup via `git worktree list --porcelain` first entry, so subprocesses don't run with cwd inside the removed worktree.
  - **M2**: remove silent `--force` fallback at lines 346-352; thread `force: bool = False` parameter, default False; only overnight cross-repo path may opt in.
  - **M5**: accept `branch` as a parameter at line 363 instead of hardcoding `pipeline/{feature}` — supports `interactive/{slug}` and any future prefix.

**Concurrency / pid file**:
- `cortex/lifecycle/sessions/{slug}.interactive.pid` — per-machine, exempt from cross-machine sync. #241 owns the lock semantics; #239 reads location for liveness check during cleanup gate.

**Statusline + hooks**:
- `claude/statusline.sh` and `hooks/cortex-scan-lifecycle.sh` `phase_label()` — render "Complete (awaiting merge)" when events.log shows `pr_opened` but no `feature_complete`. Renderer tweak only.
- `hooks/cortex-scan-lifecycle.sh` MUST NOT add `gh pr view` polling. User's manual re-invocation is the gate.

**SessionStart PATH bootstrap migration (absorbed per user decision)**:
- `claude/hooks/cortex-worktree-create.sh:18,42-50` — the PATH bootstrap currently lives in the WorktreeCreate hook (only fires for `claude --worktree` flow). Move equivalent PATH bootstrap to a SessionStart hook so any Dock/Finder-launched Claude session inherits the right PATH regardless of whether the worktree was created via `--worktree` or via manual `git worktree add` (the lifecycle's path).

**Morning-review walkthrough Section 5 ordering fix (absorbed per user decision)**:
- `skills/morning-review/references/walkthrough.md:430-456` — pre-existing bug: closes backlog `status=complete` BEFORE Section 6's merge step. Move to Section 6b (after merge confirmation). Add a guarding test.

**`feature_complete` event schema + metrics segmentation (absorbed per user decision)**:
- `bin/.events-registry.md` — extend `feature_complete` event schema with `merge_anchor: "review" | "merge"` field.
- `cortex_command/pipeline/metrics.py:161-276` — segment phase-duration aggregates by `merge_anchor` so historical comparisons across the restructure boundary are honest. Pre-restructure events get `merge_anchor: "review"` (legacy default); post-restructure events get `merge_anchor: "merge"`.
- Register `pr_opened` event in `bin/.events-registry.md` with producer (complete.md step 5) and consumers (statusline.sh renderer, detector for awaiting-merge sub-state).

**Tests**:
- `tests/test_lifecycle_kept_pauses_parity.py` — **categorical extension**: add "phase-exit pause" as a recognized kind alongside `AskUserQuestion`-site pauses. The merge-wait pause is a phase-exit pause.
- New test guarding morning-review ordering: a morning-review run with an unmerged PR must NOT close the backlog item.
- New test for multi-step Complete state routing: invoke Complete on a wontfix lifecycle → exit message; invoke twice rapidly → idempotent; invoke after web-UI merge → skip pause and proceed to cleanup.

**ADR**:
- `cortex/adr/NNNN-multi-step-complete-and-interactive-worktree-lifecycle.md` — captures: (1) Complete as multi-step phase with mid-phase merge-wait pause; (2) WorktreeCreate-hook bypass for lifecycle-managed `interactive/{slug}` worktrees is by design; (3) PATH bootstrap migrated to SessionStart; (4) rejected alternatives R1 (new Submit phase), R2 (bimodal Complete), R3 (PR creation in Review's tail), R4 (status transitions only). Three-criteria gate met per `cortex/adr/README.md`.

**Backlog**:
- `cortex/backlog/239-*.md` — this ticket; scope expanded to absorb all four sibling concerns per user decision.
- `cortex/backlog/240-*.md` — Variant A end-to-end inherits the new `pr.json` handoff; #240's PR-creation hook either invokes Complete's step 3-4 path or wires alongside it.

### Sibling ticket impact

| Ticket | Today's Assumption | Change |
|---|---|---|
| #238 (preflight menu) | Menu option 2 dispatches to daytime | Indirect — option 2 now invokes worktree creation; no daytime |
| #239 (this) | Worktree cleanup at Complete | Cleanup at post-merge step of multi-step Complete; absorbs primitive fixes + morning-review reorder + merge_anchor + PATH bootstrap migration |
| #240 (Variant A end-to-end) | PR creation in Complete §4 | PR creation moves to multi-step Complete step 3 (or #240's hook lives alongside); reads `pr.json` for cross-ticket handoff |
| #241 (concurrency guards) | `interactive.pid` lock | Owns the lock; #239 agrees on per-machine `cortex/lifecycle/sessions/{slug}.interactive.pid` location |
| #246 (daytime removal sweep) | Deletes implement.md §1a | No change; runs after this work ships |

### Effect on features without a worktree (options 1 & 3)

Multi-step Complete still fires for non-worktree features:
- Steps 1-7 (tests, commit, PR, pr.json, pause, recheck, route) run normally.
- Step 8 (worktree cleanup) becomes a no-op when no worktree exists (the `interactive/` prefix check filters it out).
- Steps 9-12 (backlog close, index sync, feature_complete, summary) run normally.

Complete remains a meaningful phase regardless of worktree presence — it represents the lifecycle's terminal work-state, not a worktree-specific operation.

## Web Research

(Carried forward from prior research cycle — still applicable.)

### Industry convention: "Done" = merged

GitHub, Linear, Jira, GitLab all converge: terminal status fires on PR merge, not PR open. GitHub explicitly shipped (April 2025) a toggle to decouple PR-merge from issue-close with the rationale *"merging a PR doesn't mean the work is done."* The dominant tracker-tool pattern matches the user's intuition; multi-step Complete with merge-wait pause aligns with this.

### AI-coding tools: agent task done = PR opened (with exceptions)

Cursor, Aider, GitHub Copilot Workspace, OpenAI Codex App all stop at PR creation. Devin's auto-merge is the major exception. `obra/superpowers/finishing-a-development-branch` is the closest agent-skill prior art and explicitly does NOT clean worktrees at PR-creation time — the same insight driving this work.

### Two-phase commit precedent

**GitHub Releases (draft → publish)** is the closest analogous pattern: prepare-for-completion vs. finalize-after-external-event. The multi-step Complete is the same shape with one phase + sequential steps instead of two phases.

### Post-merge automation patterns

GitHub Actions canonical: `on: pull_request: types: [closed]` + `if: github.event.pull_request.merged == true`. None of the surveyed patterns solve the local-worktree case cleanly. `cli/cli#380`, `#13380`, `#2625` confirm the gap. Multi-step Complete fills it via user-invoked re-entry.

### Worktree cleanup canonical rules

- Always `git worktree remove`, never `rm -rf` (stale `.git/worktrees/` metadata otherwise).
- Three-tier removal escalation pattern: `remove` → `remove --force` → `rm -rf && git worktree prune`. We adopt only the first tier; `--force` is removed from `cleanup_worktree()` per M2.
- Cleanup MUST NOT run from inside the worktree being removed (`anthropics/claude-code#29653` — CWD-deleted shell wedge). M1 fixes this in the primitive.

### Mid-session CWD deletion hazard

Adversarial concern carried forward: if Complete runs cleanup from inside the target worktree, every subsequent Bash call fails. M1 mitigation: pin cwd to main worktree via `git worktree list --porcelain` first entry. Additionally, the recipe should refuse to run when `realpath PWD == target worktree path` (defensive).

## Requirements & Constraints

### Verbatim load-bearing invariants

- **Destructive operations preserve uncommitted state** (`project.md:42`): *"Cleanup scripts removing user-visible artifacts (worktrees, branches, sessions) SKIP on uncommitted state. Inline destructive sequences extract into named scripts."* — Drives step 7's dirty-state gate and M2 (no silent `--force`).
- **Handoff readiness** (`project.md:13`): post-merge Complete must be agent-verifiable. Step 7's `gh pr view` + `git status --porcelain` + `git merge-base --is-ancestor` gates satisfy this — no human interpretation required.
- **Day/night split** (`project.md:11`): multi-step Complete fits the day/night idiom — Implement is daytime collaboration; merge happens on the user's schedule; the post-merge step 8-12 re-invocation can happen any time.

### `feature_complete` semantic shift

Pre-restructure: `feature_complete` fires at review-approved + git-workflow time (pre-merge for interactive; post-review-approved for overnight via `pipeline/review_dispatch.py`).
Post-restructure: `feature_complete` fires only at multi-step Complete's step 11, after merge + cleanup.

`merge_anchor: "review" | "merge"` field on the event distinguishes the two regimes. `cortex_command/pipeline/metrics.py:161-276` segments historical aggregates by this field.

### Backlog status field

Two code paths set `status=complete` today: `complete.md:29-35` and `skills/morning-review/references/walkthrough.md:100-104`. The morning-review path runs at Section 5 BEFORE Section 6's merge step — a pre-existing inversion. #239 absorbs the reorder (Section 5 → 6b).

### Kept user pauses inventory

`skills/lifecycle/SKILL.md:189-200` lists 8 entries; `tests/test_lifecycle_kept_pauses_parity.py` enforces each points to an `AskUserQuestion` reference. **The merge-wait pause is categorically new** — it's a phase-exit pause (the agent exits; the user re-invokes later). The parity test must extend its kind taxonomy.

### Terminal backlog statuses

`cortex_command/common.py:117-125` `TERMINAL_STATUSES = {complete, abandoned, done, resolved, wontfix, won't-do, wont-do}`. No new value needed.

### CLI / plugin version

`ADR-0002`: internal lifecycle semantics; no version bump required.

## Tradeoffs & Alternatives

### Restructure shape (decided)

| Option | Verdict |
|---|---|
| **Multi-step Complete** with mid-phase merge-wait pause (final committed direction) | **Adopted.** Minimal blast radius; uses existing mid-phase-pause pattern; no new phase enum. |
| R1 — new Submit phase | Rejected after evaluation. Earns ~25 files of churn for a named phase boundary; the affordance is already honored by a mid-phase pause inside Complete. |
| R2 — bimodal Complete (first run vs. second run) | Rejected on hackiness review. The multi-step framing achieves the same outcome with cleaner mental model (sequential progression, not two modes). |
| R3 — PR creation into Review's tail | Rejected. Breaks Review's explicit read-only contract (`review.md:91`). |
| R4 — status transitions only | Rejected. Splits state across two state machines (phase events.log + backlog status). |
| T1-T6 (cleanup-trigger taxonomy from prior research cycle) | Superseded. The trigger question evaporates under multi-step Complete: Complete IS the trigger. |

### Ticket scope (decided)

S1 — single ticket #239 absorbs all of: multi-step Complete rewrite, primitive fixes (M1/M2/M5), morning-review Section 5 reorder, `feature_complete` merge_anchor + metrics segmentation, PATH bootstrap migration to SessionStart, worktree creation in implement.md option 2, worktree cleanup at step 8, statusline rendering tweak, ADR, kept-pauses parity test extension.

Delivered as **two staged commits within one PR**:
1. Commit 1: primitive fixes + ADR + morning-review reorder + merge_anchor schema. Parity tests pass.
2. Commit 2: multi-step Complete rewrite + implement.md option 2 + statusline rendering + kept-pauses inventory entry + tests. Parity tests pass.

Bisectable at both commits.

### Files touched (final list)

**Skill prose (canonical)**:
- `skills/lifecycle/references/complete.md` (substantial rewrite)
- `skills/lifecycle/references/implement.md` (option 2 body, ~10 lines)
- `skills/lifecycle/SKILL.md` (kept-pauses inventory entry)
- `skills/morning-review/references/walkthrough.md` (Section 5 → 6b reorder)

**Python**:
- `cortex_command/pipeline/worktree.py` (M1, M2, M5 fixes; `_resolve_branch_name` generalization)
- `cortex_command/pipeline/metrics.py` (segment by `merge_anchor`)

**Hooks**:
- `claude/hooks/cortex-worktree-create.sh` (move PATH bootstrap out — possibly to new SessionStart hook)
- New SessionStart hook for PATH bootstrap (`claude/hooks/cortex-session-start-path-bootstrap.sh` or similar)
- `hooks/cortex-scan-lifecycle.sh` (`phase_label()` renders "Complete (awaiting merge)" sub-state)
- `claude/statusline.sh` (renders sub-state)

**Events / registry**:
- `bin/.events-registry.md` — register `pr_opened` event, extend `feature_complete` schema with `merge_anchor`

**Tests**:
- `tests/test_lifecycle_kept_pauses_parity.py` — extend kind taxonomy
- New test: morning-review ordering invariant
- New test: multi-step Complete state routing (wontfix, idempotent, web-UI-merge fallback)
- `cortex_command/pipeline/tests/test_metrics.py` — segmentation by merge_anchor

**Plugin mirrors**: auto-regenerate.

**ADR**:
- `cortex/adr/NNNN-multi-step-complete-and-interactive-worktree-lifecycle.md` (new)

**Backlog**:
- `cortex/backlog/239-*.md` updated scope
- `cortex/backlog/240-*.md` updated touch points (pr.json handoff)

Total: ~15-20 files (~half of R1's ~35-40).

## Adversarial Review

Findings carried forward from the second research cycle, re-evaluated under multi-step Complete. Most concerns still apply or have been resolved.

**§1. Overnight pipeline phase-graph dishonesty** — **RESOLVED.** No new phase, no synthetic transitions. Overnight's `review_dispatch.py:281-287` keeps emitting `phase_transition review→complete` + `feature_complete` atomically as today. The `merge_anchor: "review"` field on overnight's `feature_complete` events distinguishes them from interactive merge-anchored events.

**§2. In-flight lifecycle migration gap** — **MOSTLY RESOLVED.** No phase enum change means existing lifecycles with `feature_complete` events still detect as `phase=complete` via `common.py:267`. Lifecycles parked at `review` with APPROVED verdict but no `feature_complete` yet: they still detect as `review` until they reach the new Complete (per the unchanged detector logic). On first invocation, the new Complete runs steps 1-6 (creates PR for the first time). Edge case is benign.

**§3. Implement→Submit transition for review-skip path** — **N/A.** No Submit phase. Today's `implement.md:266-275` transitions to Complete for the review-skip path; that remains true.

**§4. Wontfix bypasses Complete** — **Confirmed in spec.** Step 7 checks for `feature_wontfix` event and exits with "lifecycle was wontfix'd at <ts>; nothing to complete." Locked.

**§5. Prose-only enforcement of merge-wait** — **ACCEPTED as design tradeoff.** Nothing structural reminds the user to come back. The kept-pauses inventory captures this as a "phase-exit pause" category; statusline shows "Complete (awaiting merge)" to surface the pending state. Acceptable given the smaller blast radius vs R1.

**§6. User-merged-via-web-UI-before-running-/complete** — **HANDLED by idempotent + state-aware step 7.** Complete's first invocation, on a state where PR exists and is merged, skips the pause and proceeds to cleanup. The `gh pr view <number>` query in step 7 detects this. If PR doesn't exist yet, step 3 creates it.

**§7. `feature_complete` semantic re-anchoring breaks calibration history** — **HANDLED by `merge_anchor` field + metrics segmentation.** Pre-restructure events carry `merge_anchor: "review"`; post-restructure interactive events carry `merge_anchor: "merge"`. Aggregates segment cleanly.

**§8. S1 vs S2 framing** — **HONORED user's S1 commitment with two-staged-commits discipline.** Single ticket, two commits, bisectable at each commit boundary.

**§9. Morning-review Section 5 ordering bug** — **ABSORBED.** Section 5 (`cortex-update-item status=complete`) moves to Section 6b after the merge step. New test guards the ordering.

**§10. Auto-advance via hook polling** — **REJECTED.** `hooks/cortex-scan-lifecycle.sh` does NOT add `gh pr view` polling. User's manual re-invocation is the gate. Documented in the new ADR and in `complete.md`.

**§11. Statusline rendering** — **ABSORBED.** "Complete (awaiting merge)" renderer tweak via `pr_opened` event detection.

**§12. Pipeline-events vs lifecycle-events split** — **HANDLED.** Step 7's already-`feature_complete`-in-log short-circuit prevents duplicate emission. Existing pipeline events at `cortex/lifecycle/pipeline-events.log` are not affected by multi-step Complete (those events come from overnight pipeline, which is unchanged).

### Adversarial findings specific to the multi-step Complete shape (new):

**§13. The `pr_opened` event registration carries no consumer at first** — Register with producer (complete.md step 5) and consumers (statusline renderer + detector sub-state). Without those consumers, the events-registry parity test will reject it. Verify both consumers ship in the same commit as the event registration.

**§14. `cleanup_worktree()`'s primitive defects could regress** — M2's removal of silent `--force` may surface existing latent failures in the overnight cross-repo cleanup path. Audit before commit 1: enumerate every callsite of `cleanup_worktree()`; verify each either (a) doesn't need force, or (b) explicitly passes `force=True` with documented rationale.

**§15. Two-staged-commit risk** — Commit 1's primitive fixes may transiently break a test that depends on the old `cleanup_worktree()` behavior. Run the full test suite between commits to confirm bisectability; if a test fails at commit 1 boundary, fold the test update into commit 1.

## Open Questions

All locked in the interview; no items deferred to spec.

1. Tests step location in multi-step Complete — **locked**: step 1 (before commit/PR). ✓
2. Mode-aware vs uniform enum — **N/A** under multi-step Complete (no new phase).
3. Implement→Submit transition — **N/A**.
4. Wontfix bypass — **locked**: step 7 detects `feature_wontfix` and exits with clear message. ✓
5. In-flight migration — **locked**: no migration needed; existing events keep detecting correctly. ✓
6. Idempotent Complete fallback — **locked**: state-aware step 7 with full edge-case routing (already-merged, dirty, twice-invoked, wontfix). ✓
7. Kept-pauses parity test extension — **locked**: add "phase-exit pause" kind. ✓
8. `feature_complete` `merge_anchor` field — **locked**: schema extension + metrics segmentation. ✓
9. Morning-review Section 5 reorder — **locked**: absorbed; Section 5 → 6b. ✓
10. `pr.json` handoff schema — **locked**: `{number, url, head_branch, opened_at}`. ✓
11. `cleanup_worktree()` primitive fixes — **locked**: absorbed (M1, M2, M5). ✓
12. `interactive.pid` location — **locked**: per-machine `cortex/lifecycle/sessions/{slug}.interactive.pid`. ✓
13. Statusline rendering — **locked**: "Complete (awaiting merge)" sub-state. ✓
14. ADR placement — **locked**: one ADR documenting multi-step Complete + hook bypass + rejected alternatives + PATH bootstrap migration. ✓

## Considerations Addressed

- **Cleanup-trigger seam with sibling ticket #240** (under restructure): Resolved. #240's PR-creation hook either uses or is wired alongside Complete's step 3-4 path. #239 writes `cortex/lifecycle/{slug}/pr.json` at step 4; #239's step 7 reads it. #240 may extend or consume the same file. Single-direction handoff inside one ticket scope; #240 inherits the contract.

- **Backwards-impact survey** (under multi-step Complete): ~15-20 files total — ~half of R1's footprint. Skill prose (4 files), Python (2 files), hooks (3 files), tests (3-4 files), events-registry, ADR, backlog. Plugin mirrors auto-regenerate. Critical hidden surface: morning-review Section 5 ordering bug exposed by but not caused by this work — absorbed per user decision.

- **Effect on features that have no worktree (options 1 & 3)**: Resolved. Multi-step Complete still fires for non-worktree features; step 8 (worktree cleanup) is a no-op when no `interactive/`-prefix worktree exists. Steps 1-7 and 9-12 run unchanged. Complete remains a meaningful phase regardless of worktree presence (represents terminal work-state, not worktree-specific operation).
