# Research: overnight-merge-conflict-prevention

## Research Questions

1. How does the overnight runner currently assign features to rounds, and is there any file-level overlap detection? → **Tag-based greedy grouping only — no file-level detection exists**
2. Does any pre-flight analysis check for file/area overlap before scheduling features into the same round? → **No. Risk detection in `plan.py` flags shared epics/tags post-hoc as warnings only**
3. What does the current merge handling do, and where does it fail? → **No-ff merge → trivial fast-path conflict resolution → repair agent → defer. Gaps exist in scheduling, not in the merge mechanics themselves**
4. When a merge conflict occurs, what ends up in the morning report? → **`conflicted_files` and `conflict_summary` are written to the event log but are not surfaced inline in the morning report — user sees paused features with generic error strings**
5. Are feature branches left intact after conflict, and is there a clear recovery path? → **Branches are intact; base branch is cleanly aborted. But no recovery guidance is surfaced to the user**
6. Are there industry patterns from parallel CI/CD that apply here? → **Yes: merge train sequential pre-integration is directly applicable; file-impact prediction from plan DAGs is feasible**

---

## Codebase Analysis

### Round Assignment (the root cause)

**`claude/overnight/backlog.py` — `group_into_batches()` (line 869)**

Three-phase algorithm:
1. Extract up to 2 "quick win" bugs/chores regardless of tags → Batch 1
2. Greedy tag assignment: for each remaining item, find the batch with most tag overlap; start a new batch if no overlap exists
3. Split oversized batches (>5 items) while preserving tag locality

The function signature is `group_into_batches(scored_items: list[tuple[BacklogItem, float]], ...)`. It receives only `BacklogItem` instances. `BacklogItem` is populated from backlog YAML frontmatter — it contains tags, type, priority, parent ID, lifecycle_slug, and plan path, but no lifecycle spec content. No lifecycle files are read at selection or grouping time.

`select_overnight_batch()` (the entry point, line 973) loads items from the backlog index or directory, filters, scores, and calls `group_into_batches()`. It reads only the backlog directory. Lifecycle spec or plan files are never opened during overnight planning.

**The core problem**: grouping is purely semantic (tags). Two features that share tags (e.g., `[auth, users]`) will be placed in the same round regardless of whether they edit the same files. For a fresh project where all 10 tickets come from one discovery, they typically share tags AND modify the same new files — worst-case scenario.

Intra-session dependency (`intra_session_deps`) exists via BFS round assignment for explicit blockers, but this requires human-declared dependencies. There is no automatic inference.

### Risk Detection (incomplete)

**`claude/overnight/plan.py` — `_detect_risks()` (line 47)**

Post-grouping risk scan detects:
- Features sharing a parent epic ID
- Tags that appear in more than one batch

Both checks work from `BacklogItem` metadata already in the `Batch` objects — no external files are read here either. These are surfaced as warnings in the session plan, not enforced. The system proceeds regardless. File-level overlap is never checked.

### Merge Mechanics (sound)

**`claude/pipeline/merge.py` — `merge_feature()` (line 158)**

Flow: CI gate → `git merge --no-ff` → conflict detection → trivial fast-path (≤3 files, non-hot) → repair agent (Sonnet→Opus escalation) → defer.

On conflict: `classify_conflict()` (`conflict.py` line 687) aborts the merge cleanly — base branch is always left clean. Feature branch is preserved intact.

The merge mechanics themselves are solid. The gap is upstream (scheduling), not in the merge layer.

### Failure Visibility Gap

**`claude/overnight/batch_runner.py` — `_apply_feature_result()` (line 1350)**  
**`claude/overnight/report.py` — `collect_report_data()` (line 88)**

On conflict, the event log receives:
- `merge_conflict_classified` event with `details.conflicted_files` (list) and `details.conflict_summary` (human-readable string)
- `feature_paused` event with `error` and `conflict: True`

`collect_report_data()` already loads all events into `data.events`. The `_render_failed_features()` function already iterates `data.events` to count retry attempts per feature. The data needed to render conflict details is already present in memory during report generation — it just isn't extracted.

**The gap**: the render function reads only `fs.error` from `OvernightFeatureStatus`. `OvernightFeatureStatus` has no `conflict_summary` or `conflicted_files` fields — only `error`, `recovery_attempts`, and `recovery_depth`. The `merge_conflict_classified` event details sit in `data.events` but are never joined to the failing feature's report section.

### Recovery State

After a failed merge:
- Feature branch `pipeline/{feature}` is intact, all commits preserved
- Base branch (`main` or integration branch) is cleanly aborted — no partial merge state
- `OvernightFeatureStatus.recovery_attempts` and `recovery_depth` are tracked in state

No recovery guidance is written anywhere the user would see it in the morning. The user must independently reconstruct what happened and figure out the git state.

### Circuit Breaker

`CIRCUIT_BREAKER_THRESHOLD = 3` consecutive pauses in a batch stops the batch (not the session). For a 10-ticket session where many features conflict, the circuit breaker may kick in and halt subsequent work — reducing successful output further.

**Interaction with area separation**: The circuit breaker counter is per-batch, not per-session. If area separation forces conflicting items into separate single-item batches, the counter resets between batches and never accumulates. The circuit breaker then provides no global protection — the session runs every item and every item conflicts. Area separation does not reduce the total number of conflicts on a net-new project where the overlap is genuine file-level collision: it only prevents conflicts from being intra-batch. Features that genuinely modify the same file will still conflict when their branches are merged sequentially.

---

## Domain & Prior Art

### Merge Train Pattern (GitLab)

The key insight: test each MR against all predecessors already merged (simulated forward integration). MR #1 tests against (A + main), MR #2 tests against (A + B + main), etc. — all in parallel. When position N fails, downstream positions are requeued.

**Applied here**: rather than merging features independently in parallel, serialize them through an integration branch in dependency/overlap order. Features whose predicted file overlap is high are placed in serial rounds rather than parallel rounds. This is the "why" behind separating conflicting work into different rounds — not just tag grouping.

### Affected-Package Detection (Nx/Turborepo)

Algorithm: build a DAG of dependencies by analyzing imports → diff branch against baseline → BFS/DFS reachability to find affected packages.

**Applied here**: if backlog items or lifecycle plan files for each feature enumerate the files they intend to modify (even coarsely — "this feature touches `auth/`, `users/`"), the scheduler can build a conflict graph and place overlapping features in serial rounds. The key limitation: plan-time file prediction is imprecise for net-new projects where the file structure doesn't yet exist.

### Conflict-Aware Scheduling

No established standard exists at the work-item scheduling level. Research shows 0.92 precision is achievable using developer roles + file touch patterns — but this requires historical data. 

The practical finding: file-level conflict prediction before implementation is unreliable. The more viable approach is **area/module declaration** (human or AI-assisted) rather than automated file scanning.

### Git rerere

`git rerere` memorizes conflict resolutions and replays them on identical future conflicts. Not applicable here (conflicts in a fresh project won't repeat), but worth noting for regression prevention.

---

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **A. Area-declaration on backlog items** — add `areas:` field to backlog item YAML frontmatter; scheduler uses it to group conflicting features in serial rounds | S | Spec authors (human or AI) must fill field; net-new projects have uncertain areas; requires new `BacklogItem` field and a scheduler change in `group_into_batches()` | None — additive to existing schema. Field must go on the backlog item, not the lifecycle spec: `group_into_batches()` receives only `BacklogItem` data and never reads lifecycle files |
| **B. Plan-time file-impact extraction** — parse lifecycle plan files (markdown) at session planning time to extract file paths mentioned; build conflict graph for scheduling | M | Plan files may not exist yet; file paths mentioned are heuristic, not authoritative; requires `select_overnight_batch()` to open and parse external files | Lifecycle plans must be written before overnight (already required); non-trivial plumbing to pass plan content into the grouping algorithm |
| **C. Conflict details inline in morning report** — extract `conflict_summary` + `conflicted_files` from event log and surface them in the Not Completed section | S | Low risk | None — `data.events` is already loaded by `collect_report_data()`; `_render_failed_features()` already iterates events; no state schema change needed |
| **D. Recovery instructions in morning report** — when a feature is paused due to conflict, add a structured "how to recover" block: branch name, conflicted files, suggested next steps | S | Low risk | None |
| **E. Integration branch per round** — instead of merging features direct to main, use a per-round integration branch; test the integration branch before promoting to main | L | Significant orchestration change; doesn't prevent conflicts, just isolates them | Changes to merge.py, plan.py, state schema |
| **F. Merge-train-style serialization** — within a round, execute potentially-conflicting features serially instead of in parallel; test each against prior merges | M | Reduces parallelism benefit; requires conflict graph construction | Approach A or B to build conflict graph |

---

## Decision Records

### DR-1: Root cause is scheduling, not merge mechanics

- **Context**: The merge mechanics (conflict detection, trivial fast-path, repair agent) work correctly. The root cause is that features are grouped by semantic tags without regard for file-level overlap.
- **Options**: Fix merge mechanics vs. fix scheduling
- **Recommendation**: Fix scheduling (Approaches A or B) — the merge layer is already correct
- **Trade-offs**: Scheduling fixes require earlier information (area declarations or plan parsing); they can't catch all conflicts, but dramatically reduce them for the most common case (grouped features from one discovery)

### DR-2: Plan-time prediction vs. spec-time declaration

- **Context**: Two ways to predict which files a feature will touch: parse plan files automatically (B), or declare areas explicitly on the backlog item (A).
- **Options**: Automatic extraction (B) vs. human/AI declaration (A)
- **Recommendation**: Start with declaration (A) — add an `areas:` field to the backlog item YAML frontmatter. `/refine` and `/lifecycle` would be responsible for populating it when writing the spec or plan. This is more reliable and adds no new parsing complexity. Approach B can be layered on later.
- **Key constraint**: The `areas:` field cannot live only in the lifecycle spec. `group_into_batches()` and `select_overnight_batch()` read only `BacklogItem` data from the backlog index — lifecycle spec files are never opened during overnight planning. The field must be on the backlog item itself (in YAML frontmatter), mirrored there from the spec if needed.
- **Algorithm inversion required**: The current greedy phase in `group_into_batches()` treats tag overlap as a *grouping attractor* — items with high tag overlap land in the same batch. Area overlap must be treated as a *separation constraint*: the algorithm must check a candidate batch for area collision *before* computing tag overlap and actively prefer starting a new batch even when a tag-overlap match exists. When an item has both high tag overlap (current grouping pull) and area overlap (new separation push), area-overlap takes priority. This is not an additive field — it is a new constraint layer in the grouping logic. The tag-grouping objective and the area-separation objective can directly conflict; the implementation must define this resolution rule explicitly.
- **Silent absence**: If the `areas:` field is absent (not populated on the backlog item), the separation constraint is silently skipped — no warning emitted, no fallback behavior, no degraded mode. The system proceeds exactly as today. The user has no way to know the constraint was ignored.
- **Worst-case parallelism collapse**: On the net-new project scenario (all items share both tags and areas), area separation forces every item into its own single-item batch. Parallel execution is eliminated entirely. This should be treated as an explicit expected behavior when areas fully overlap — the system serializes rather than risk conflicts — but it should be stated, not implied, as the intended outcome.
- **Phase 3 (split) cannot compensate**: The split algorithm (`_split_oversized_batch()`, line ~848) preserves tag locality and splits by size only. If area separation failed to prevent a collision (due to absent or coarse declarations), the split phase cannot fix it.
- **`_detect_risks()` must be replaced, not supplemented**: The existing risk detector in `plan.py` checks for tag overlap *across* batches. But `group_into_batches()` ensures tag overlap *within* batches. These work in opposite directions — the risk detector fires on secondary tag overlap across clusters, not on the primary conflict population. With an areas-aware scheduling implementation, `_detect_risks()` should be replaced with an areas-overlap *within-batch* validation that confirms the separation constraint was honored, not supplemented with an areas check on top of a broken tag check.
- **Net-new project limitation**: Area declarations are hardest to write precisely when they are most needed. On a fresh project with no established module boundaries, all 10 tickets from one discovery share tags and likely share the same new files — exactly the scenario where area declarations are most uncertain. On an established project with clear module boundaries, declarations are easy to write but conflicts are already less likely. **Area separation reduces intra-batch conflict clustering; it does not prevent genuine file-level conflicts.** Features that actually modify the same file will still conflict when their branches are merged sequentially into main. For net-new projects, C+D (visibility and recovery improvements) are the primary near-term mitigation. The `areas:` approach pays off incrementally as the codebase develops structure and declaration confidence improves.
- **Trade-offs**: Declaration requires the AI writing the spec to predict file overlap. Even coarse area tags reduce conflicts on established projects. Enforcement relies on humans/AI populating the field consistently — there is no fallback if it's absent or wrong.

### DR-3: Morning report failure visibility

- **Context**: `conflict_summary` and `conflicted_files` are already captured in the event log but never shown to the user in the morning report.
- **Recommendation**: This is a low-effort fix (Approach C) and should be prioritized independently of the scheduling work. It directly addresses the "couldn't tell what went wrong" complaint. Implementation: in `_render_failed_features()`, build a per-feature index of `merge_conflict_classified` events from `data.events` (which is already loaded) and render `details.conflict_summary` and `details.conflicted_files` in the paused feature block. No change to `OvernightFeatureStatus` or `overnight-state.json` is needed.
- **Implementation risk (blocking)**: The join between event log data and the state's feature dict is by feature name string. The event's `feature` field is written during execution (from the master plan, which is written by an LLM agent); the state dict key is set during planning (`item.lifecycle_slug or slugify(item.title)` from the backlog item). These are two independent write sites with no enforcement that they produce matching strings. If the agent writes a slightly different display name in the master plan than the backlog slug, the join silently produces nothing — the paused feature renders without conflict details, no error is raised, and the user sees the same degraded output as before. There is no existing test that verifies this invariant. **This is the most likely failure mode of the one proposal marked as "low risk, no prerequisites."** Treat as a blocking requirement: the implementation must include an automated test (not just manual inspection) that verifies the feature name in `merge_conflict_classified` events matches the key in `data.state.features` for a representative conflict scenario.
- **Trade-offs**: None beyond the blocking verification above. Backlog 002 is adjacent; this may be folded into the same ticket or tracked separately.

### DR-4: Recovery guidance

- **Context**: Feature branches are intact after conflict. The user has a recoverable state but no guidance on what to do.
- **Recommendation**: Approach D — add a structured recovery block to the morning report for each conflicted feature. Minimal format: branch name, conflicted files, suggested action ("re-run in next session", "resolve manually and re-enqueue", or "mark as merged if already done").
- **Trade-offs**: This is a report formatting concern, not a workflow concern. Keep it simple.

---

## Open Questions

- For the `areas:` field approach (DR-2): should `/refine` populate this field from the spec content, or should `/lifecycle` plan phase populate it from the plan? Lifecycle plan phase has more concrete information (actual file paths) but runs later. Either way the field must end up on the backlog item YAML, not only in the spec.
- If area declarations are added to backlog items, how does the existing `_detect_risks()` in `plan.py` interact? Should the tag-overlap check be replaced or supplemented by an areas-overlap check?
- Does the circuit breaker threshold (3 consecutive pauses) need adjustment for high-conflict sessions? Three might be too low when conflicts are structural rather than feature-specific failures.
