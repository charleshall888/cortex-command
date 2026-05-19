# Writer-Site Inventory: implement-variant-a-end-to-end

Call-graph audit from `skills/lifecycle/references/implement.md` §1a–§4 and
`skills/lifecycle/references/complete.md`. Excludes sites in
`cortex_command/overnight/daytime_pipeline.py` (slated for #246 removal).

Classification follows `research.md` §"The eight named writer sites — verified state":
- **cwd-pinned**: path resolved relative to process CWD at write time; mid-session `cd` changes where the write lands.
- **env-pinned**: path resolved via `_resolve_user_project_root()` (env-first) or `git rev-parse --show-toplevel` from the process's actual worktree root; CWD changes do not alter the destination.

---

## Sites reachable from implement.md §1a–§4

### Site 1 — `implement.md` §2b inline `batch_dispatch` write

**File**: `skills/lifecycle/references/implement.md:137-140` (orchestrator inline Bash)
**Write**: orchestrator appends `{"event": "batch_dispatch", ...}` to
`cortex/lifecycle/{feature}/events.log` using a bare relative path in the inline
Python/Bash snippet the model executes directly.
**Reachability**: Every Variant A session that reaches §2 Task Dispatch fires this write
for each batch.
**Classification**: `cwd-pinned` — the inline snippet uses a bare `cortex/lifecycle/...`
path; the destination resolves to the CWD at the time of the Bash tool call.

---

### Site 2 — `implement.md` §3 rework `phase_transition` write

**File**: `skills/lifecycle/references/implement.md:202-205` (orchestrator inline Bash)
**Write**: orchestrator appends `{"event": "phase_transition", "to": "implement-rework", ...}`
to `cortex/lifecycle/{feature}/events.log`.
**Reachability**: Reached only when re-entering from Review with CHANGES_REQUESTED; fires
once per rework cycle.
**Classification**: `cwd-pinned` — bare `cortex/lifecycle/...` path in inline snippet.

---

### Site 3 — `implement.md` §4 transition `phase_transition` write

**File**: `skills/lifecycle/references/implement.md:231-234` (orchestrator inline Bash)
**Write**: orchestrator appends `{"event": "phase_transition", "to": "review|complete", ...}`
to `cortex/lifecycle/{feature}/events.log` after all tasks complete.
**Reachability**: Every Variant A session that completes all tasks triggers this write.
**Classification**: `cwd-pinned` — bare `cortex/lifecycle/...` path in inline snippet.

---

### Site 4 — `implement.md` §2d `plan.md` checkpoint update

**File**: `skills/lifecycle/references/implement.md:149` (orchestrator inline Bash/edit)
**Write**: orchestrator updates `cortex/lifecycle/{feature}/plan.md`, changing `[ ]` to `[x]`
for tasks that complete successfully in each batch.
**Reachability**: After each batch checkpoint in §2d; fires once per completed batch.
**Classification**: `cwd-pinned` — plan.md is referenced by slug-relative path; resolves
relative to CWD at the time of the Write/Edit tool call.

---

### Site 5 — `bin/cortex-lifecycle-state:69` (read-only, CWD-relative)

**File**: `bin/cortex-lifecycle-state:69`
**Access**: `events="cortex/lifecycle/$feature/events.log"` — bare relative path; this
script is read-only (does not write to events.log), but the read resolves relative to CWD.
**Reachability**: Called in `implement.md` §4 to determine criticality before transition.
**Classification**: `cwd-pinned` (read) — listed for completeness since a post-cd read
that resolves to the wrong tree would silently return stale state and mis-route the
transition. Not a writer site strictly, but a CWD-relative reader that informs a
subsequent write.

---

### Site 6 — `bin/cortex-lifecycle-counters:63-64` (read-only, CWD-relative)

**File**: `bin/cortex-lifecycle-counters:63-64`
**Access**: `plan="cortex/lifecycle/$feature/plan.md"` and `review="cortex/lifecycle/$feature/review.md"` — bare relative paths; this script is read-only.
**Reachability**: Called in `complete.md` Step 11 to populate `tasks_total` and
`rework_cycles` in the `feature_complete` event.
**Classification**: `cwd-pinned` (read) — same rationale as Site 5; a wrong-tree read
produces a stale event payload. Not a writer site strictly; listed for completeness.

---

## Sites reachable from complete.md

### Site 7 — `complete.md` Step 4 `pr.json` write

**File**: `skills/lifecycle/references/complete.md:50-62` (orchestrator inline Python)
**Write**: orchestrator writes `cortex/lifecycle/{slug}/pr.json` via
`pathlib.Path(f"cortex/lifecycle/{slug}/pr.json")` in the inline atomic-write snippet.
**Reachability**: Reached on first-run path through Step 4; also on re-invocation via
Branch 3 orphan-PR reconstruction.
**Classification**: `cwd-pinned` — the bare `pathlib.Path(f"cortex/lifecycle/...")` pattern
resolves relative to CWD.

---

### Site 8 — `complete.md` Step 5 `pr_opened` event write

**File**: `skills/lifecycle/references/complete.md:85-89` (orchestrator inline Bash)
**Write**: orchestrator appends `{"event": "pr_opened", ...}` to
`cortex/lifecycle/{slug}/events.log`.
**Reachability**: Reached immediately after Step 4 on the first-run path.
**Classification**: `cwd-pinned` — bare `cortex/lifecycle/...` path in inline snippet.

---

### Site 9 — `complete.md` Step 11 `feature_complete` event write

**File**: `skills/lifecycle/references/complete.md:222-225` (orchestrator inline Bash)
**Write**: orchestrator appends `{"event": "feature_complete", ...}` to
`cortex/lifecycle/{slug}/events.log` during re-invocation finalization.
**Reachability**: Reached on re-invocation after PR merge, during the Steps 8–12 path.
**Classification**: `cwd-pinned` — bare `cortex/lifecycle/...` path in inline snippet.

---

## Eight ticket-named sites from research.md — reachability verdict

The following are the eight sites named in `research.md` §"The eight named writer sites —
verified state". Each is assessed for reachability from implement.md §1a–§4 or complete.md.

| Site | Location | Reachable from implement/complete? | Classification | Notes |
|------|-----------|------------------------------------|----------------|-------|
| 1 | `cortex_command/refine.py:117` | No | `cwd-pinned` | Called only from `cortex-refine emit-lifecycle-start` in the refine skill, not from implement.md or complete.md. |
| 2 | `cortex_command/critical_review.py:340-349,375-416,318-322` | No | `env-pinned` | Called from Plan/Specify phases and critical-review skill only; uses `_git_toplevel()` (git rev-parse from CWD, worktree-correct). |
| 3 | `bin/cortex-complexity-escalator:265,296` | No | `cwd-pinned` | Called only at Research→Specify and Specify→Plan gates (complexity-escalation.md), not from implement.md or complete.md. |
| 4 | `cortex_command/discovery.py:189-197` | No | `env-pinned` | `resolve_events_log_path()` takes an explicit `repo_root` argument derived from `_default_repo_root()` (git rev-parse); not called from implement.md or complete.md. |
| 5 | `cortex_command/backlog/update_item.py:445` | Yes (complete.md Step 9) | `env-pinned` | CLI entry point routes via `_resolve_user_project_root()` (env-first). Already worktree-aware. |
| 6 | `cortex_command/backlog/update_item.py:169` | Yes (complete.md Step 9, via `_append_event`) | `env-pinned` | `events_path = item_path.parent / ...`; `item_path` is derived from the resolved `BACKLOG_DIR`; correct by inheritance. |
| 7 | `claude/statusline.sh:244-247` | No (not invoked from lifecycle skills) | `env-pinned` | Reads `workspace.current_dir` from statusline payload, not process CWD. Read-only observer; no writes. Runs as a hook outside skill control flow. |
| 8 | `cortex_command/overnight/report.py:52,125` | No | `env-pinned` | Called from overnight runner only; uses `_resolve_user_project_root()`. |

---

## Summary

Sites reachable from implement.md §1a–§4 or complete.md and classified as **cwd-pinned writers** (i.e., destination changes with a mid-session `cd`) are Sites 1–4 (implement.md inline writes) and Sites 7–9 (complete.md inline writes). These are the targets for Phase 3's per-callsite refactor.

Of the eight ticket-named sites, only two are reachable from implement.md/complete.md
(`update_item.py:445` and `update_item.py:169`), and both are already env-pinned
(no Phase 3 refactor needed for those two).

The three ticket-named CWD-pinned sites NOT reachable from implement.md/complete.md
(`refine.py:117`, `cortex-complexity-escalator:265,296`) are noted for completeness;
Phase 3 does not modify them per the spec's constraint that only orchestrator-session-reachable
sites are in scope.

`critical_review.py` uses `_git_toplevel()` (env-pinned via git rev-parse from the active
worktree), so it is worktree-correct today and is not a CWD regression risk.

site_count: 9
