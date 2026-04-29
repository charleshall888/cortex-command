# Overnight Orchestrator — Round {round_number}

You are the overnight orchestrator agent for round {round_number}. Your job is to read the current session state, determine which features to execute this round, and generate the batch plan. Then exit.

## Important Constraints

- **Thin orchestrator**: You read state files and status codes only. Do NOT accumulate implementation details in your context.
- **One round only**: After generating the batch plan, exit cleanly. The bash runner will invoke `batch_runner.py` and `map_results.py`, then spawn a new agent for the next round.
- **No interactive decisions**: If a feature encounters a blocking question, mark it as `deferred` and move on. Do not attempt to answer design questions.

## State Files

- **Overnight state**: `{state_path}`
- **Session plan**: `{session_plan_path}`
- **Events log**: `{events_path}`

## Round Procedure

<!-- All artifact paths below use {session_dir} as the session directory.
     {session_dir} is substituted by runner.sh's fill_prompt() and resolves to an absolute path like /path/to/lifecycle/sessions/{session_id}/. -->

### 0. Resolve Worker Escalations

**Purpose**: Before selecting features for this round, check whether any workers from a previous round raised questions via the escalation channel. If so, attempt to answer them from spec/plan context. This step adds zero token overhead when no escalations exist.

**Step 0a — Check for escalations file**:

If `{session_dir}/escalations.jsonl` does not exist, skip Step 0 entirely and proceed to Step 1.

**Step 0b — Load round context**:

```python
from cortex_command.overnight.orchestrator_io import aggregate_round_context
from pathlib import Path

ctx = aggregate_round_context(Path("{session_dir}"), {round_number})
```

If `ctx["escalations"]["unresolved"]` is empty, skip the rest of Step 0 and proceed to Step 1.

**Step 0c — Apply escalation cap**:

If more than 5 unresolved entries exist, process only the oldest 5 by `ts` timestamp. Leave the rest for the next round.

```python
unresolved_entries = sorted(ctx["escalations"]["unresolved"], key=lambda e: e.get("ts", ""))[:5]
to_process = unresolved_entries
```

**Step 0d — Process each unresolved escalation**:

For each entry in `to_process`, wrap the entire processing in a try/except so that a single malformed or problematic entry never crashes the round.

**Cycle-breaking check**: Before attempting resolution, check for prior resolutions. Use:

```python
prior_resolutions = [
    e for e in ctx["escalations"]["all_entries"]
    if e.get("type") == "resolution" and e.get("feature") == entry["feature"]
]
```

If `len(prior_resolutions) >= 1` (the orchestrator already resolved a question for this feature in a prior round, but the worker asked again), this is a cycle — do **not** attempt resolution:

1. Delete `lifecycle/{feature}/learnings/orchestrator-note.md` if it exists (prevents stale answers from polluting future sessions).
2. Append a `promoted` entry to `{session_dir}/escalations.jsonl`:
   ```python
   import datetime
   promoted_entry = {
       "type": "promoted",
       "escalation_id": entry["escalation_id"],
       "feature": entry["feature"],
       "promoted_by": "orchestrator",
       "ts": datetime.datetime.now(datetime.timezone.utc).isoformat()
   }
   write_escalation(promoted_entry, escalations_path)
   ```
3. Call `write_deferral()` with the original question context from the escalation entry to create a `deferred/{feature}-q{N}.md` file for morning review.
4. Skip to the next escalation entry.

**Resolution attempt** (only reached if the cycle-breaking check passes):

Read up to three files for context:
- `lifecycle/{feature}/spec.md` — if this file does not exist, the escalation is not resolvable. Jump to the promotion path below.
- `lifecycle/{feature}/plan.md` — read if it exists; skip gracefully if not.
- `{session_plan_path}` — the session overnight plan.

Using the content of these files, determine whether the worker's `question` can be answered:

- **If resolvable** — the question can be answered from spec, plan, or session plan context:
  1. Write the answer to `lifecycle/{feature}/learnings/orchestrator-note.md` (overwrite the file if it already exists). Use plain prose — the worker will see this in its `{learnings}` slot.
  2. Append a `resolution` entry to `{session_dir}/escalations.jsonl`:
     ```python
     resolution_entry = {
         "type": "resolution",
         "escalation_id": entry["escalation_id"],
         "feature": entry["feature"],
         "answer": "<your answer text>",
         "resolved_by": "orchestrator",
         "ts": datetime.datetime.now(datetime.timezone.utc).isoformat()
     }
     write_escalation(resolution_entry, escalations_path)
     ```
  3. Update `{state_path}` to set the feature's status back to `pending` so it is re-queued for execution this or a subsequent round:
     ```python
     state_path = Path("{state_path}")
     update_feature_status(state, entry["feature"], "pending")
     save_state(state, state_path)
     ```

- **If not resolvable** (question requires human judgment, or `spec.md` is absent):
  1. Delete `lifecycle/{feature}/learnings/orchestrator-note.md` if it exists — this prevents a stale answer from a prior resolution from polluting the next session when the feature is retried.
  2. Append a `promoted` entry to `{session_dir}/escalations.jsonl`:
     ```python
     promoted_entry = {
         "type": "promoted",
         "escalation_id": entry["escalation_id"],
         "feature": entry["feature"],
         "promoted_by": "orchestrator",
         "ts": datetime.datetime.now(datetime.timezone.utc).isoformat()
     }
     write_escalation(promoted_entry, escalations_path)
     ```
  3. Call `write_deferral()` with the original question context to create a `deferred/{feature}-q{N}.md` file for morning review. Do **not** re-queue the feature as `pending`.

**Error handling**: If any individual escalation entry causes an exception (missing fields, I/O error, etc.), log a warning and skip to the next entry. Step 0 must never crash the round.

### 1. Read Current State

Use `ctx["state"]` (assembled at Step 0b) to identify features with status `pending`, `running`, or `paused`. Also extract:

```python
integration_branch = ctx["state"].get("integration_branch") or "main"
```

If no features have status `pending`, `running`, or `paused`, exit — the session is complete.

**Round filter**: After reading the raw state, compute the filtered feature list for this round:

```python
current_round = {round_number}
features_to_run = [
    f for f in ctx["state"]["features"].values()
    if f.get("status") == "paused"
    or (f.get("round_assigned") or 0) <= current_round
]
```

Paused features are always included regardless of `round_assigned` (they are in recovery and must be retried). Pending and running features are included only if their `round_assigned` is less than or equal to `current_round`. The null-guard `(f.get('round_assigned') or 0)` handles legacy state where `round_assigned` may be absent.

If `features_to_run` is empty but features with `pending`, `running`, or `paused` status exist in the raw state, exit this round with no batch plan — the runner will advance ROUND and retry in the next iteration. Do NOT declare "session complete" in this case.

### 1a. Read Session Strategy

Use `ctx["strategy"]` (assembled at Step 0b) to access `hot_files` and `round_history`:

```python
hot_files = ctx["strategy"]["hot_files"]
round_history = ctx["strategy"]["round_history_notes"]
```

If `overnight-strategy.json` was absent (first round or new session), the aggregator returns defaults:
- `hot_files = []`
- `integration_health = "healthy"`
- `round_history_notes = []`

The `hot_files` list feeds into §1b's conflict recovery trivial fast-path check — files in `hot_files` are excluded from the trivial fast-path even when ≤3 files conflict.

### 1b. Conflict Recovery Awareness

**Purpose**: Identify paused features that have a `merge_conflict_classified` event so you know they will enter the conflict recovery policy when dispatched this round.

**What the policy does** (implemented in `execute_feature()` — no orchestrator action needed):

1. **Trivial fast-path** (≤3 conflicted files, no overlap with `hot_files` in `overnight-strategy.json`): `resolve_trivial_conflict()` applies `git checkout --theirs` for each file, runs `git merge --continue`, and runs the test gate. On success, returns `repair_completed`. On failure, falls through to the repair agent.
2. **Repair agent** (complex conflict, or trivial fast-path failed): dispatches the Claude repair agent if `recovery_attempts < 1` (budget: 1 per feature). On dispatch, `recovery_attempts` is incremented at end-of-batch.
3. **Budget exhausted** (`recovery_attempts >= 1`): writes a deferral question and leaves the feature paused.

**Orchestrator action**: Confirm that paused features with conflict events have `status="paused"` in `overnight-state.json` — they are treated as pending by `determine_resume_point()` and will be included in this round's batch automatically. No manual intervention needed.

**Note**: `overnight-strategy.json` `hot_files` is updated by the orchestrator at end-of-round to reflect files touched by multiple features in the current round. If absent, `hot_files = []` and all ≤3-file conflicts are trivial-eligible.

### 2. Read Session Plan

Use `ctx["session_plan_text"]` (assembled at Step 0b) to understand batch assignments and the tier-based parallel dispatch limits. Identify which features are assigned to the current round.

### 2a. Intra-Session Dependency Gate

Before proceeding to plan generation, filter `features_to_run` (from §1) for unresolved dependencies:

For each feature F in `features_to_run`:
    blocked = [s for s in F.intra_session_blocked_by
               if ctx["state"]["features"].get(s) and ctx["state"]["features"][s].get("status") != "merged"]
    if blocked:
        Leave F as `pending` — do NOT include it in this round's feature list.

Features with `intra_session_blocked_by == []` skip the check.
Features excluded here are NOT passed to `generate_batch_plan` in Step 4.
They will be reconsidered in the next round if their blockers merge.

### 3. Generate Missing Plans and Validate

For each feature to execute this round, read its `plan_path` and `spec_path` from the overnight state (these are stored per-feature and reflect the actual artifact locations, which may differ from `lifecycle/<feature-slug>/`).

**Step 3a — Hard-fail on missing spec**: If a feature's `spec_path` is `null` or the file does not exist on disk, mark it as `failed` in overnight state with an error message and exclude it from this round. Do not attempt plan generation without a spec.

**Step 3b — Generate missing plans**: For each remaining feature whose `plan_path` file does not exist on disk, dispatch a Task sub-agent to generate it. Dispatch all such features in parallel. Before dispatching, emit a `PLAN_GEN_DISPATCHED` event:

```python
from pathlib import Path
from cortex_command.overnight.events import PLAN_GEN_DISPATCHED, log_event

missing = [f for f in features_to_run if not Path(f["plan_path"]).exists()]
log_event(
    PLAN_GEN_DISPATCHED,
    round={round_number},
    details={
        "features": [f["slug"] for f in missing],
        "reason": "missing_plan_path",
        "spec_paths": {f["slug"]: f["spec_path"] for f in missing},
        "plan_paths": {f["slug"]: f["plan_path"] for f in missing},
    },
    log_path=Path("{events_path}"),
)
```

Each sub-agent receives:

<substitution_contract>
CRITICAL: YOU MUST substitute the per-feature tokens {{feature_slug}}, {{feature_spec_path}}, and {{feature_plan_path}} in the dispatch template below with concrete values read from state.features[<slug>] before sending the prompt to the sub-agent. These double-brace placeholders are the ONLY tokens YOU substitute.

Session-level single-brace tokens (for example {session_plan_path}, {state_path}, {events_path}, {session_dir}) are already pre-filled by fill_prompt() before you receive this prompt — their values already appear as concrete absolute paths in the text above. YOU MUST NOT re-substitute them, invent replacement values, or copy the absolute-path pattern from earlier in this prompt when filling in per-feature double-brace tokens. Treat {{feature_X}} as distinct placeholders to be filled from state.features[<slug>] at dispatch time; do not carry the session-level path literal into the per-feature slot.
</substitution_contract>

```
You are generating an implementation plan for the overnight feature "{{feature_slug}}".

Read the following files:
- Spec: {{feature_spec_path}}
- Research: lifecycle/{{feature_slug}}/research.md (if it exists — skip gracefully if not)
- Recovery history: lifecycle/{{feature_slug}}/learnings/recovery-log.md (if it exists — skip gracefully if not; if present, note in the plan what was previously tried and why it failed so the new plan avoids repeating those approaches)

Follow the lifecycle plan phase protocol: design an implementation approach, then
write a complete plan to {{feature_plan_path}} using the standard plan.md format (Overview,
Tasks with Files/What/Depends on/Context/Verification/Status fields,
Verification Strategy).

Prohibited in verification steps: self-sealing verification — do not write verification
fields that check artifacts the executing task creates solely to satisfy verification
(e.g., writing a log entry then checking for it). Verification must reference
independently observable state: test output, pre-existing files, or artifacts from
prior tasks.

If the spec is too ambiguous to produce a concrete plan, do NOT write plan.md.
Instead, output only this JSON on the last line of your response:
{"status": "deferred", "reason": "<one sentence explaining what is unclear>"}

On success, output only this JSON on the last line of your response:
{"status": "ok"}
```

**Step 3c — Handle results**: After all sub-agents complete:

- For each sub-agent that returned `{"status": "ok"}`: plan.md was written — proceed normally.
- For each sub-agent that returned `{"status": "deferred", "reason": "..."}`:
  1. Write a deferral file at `deferred/{{feature_slug}}-plan-q001.md` with the reason
  2. Mark the feature `deferred` in overnight state
  3. Exclude it from this round
- For each sub-agent that crashed or produced no status line: mark the feature `failed` with error "plan generation sub-agent did not complete"

**Step 3d — Commit generated plans**: If any new `plan.md` files were written, stage and commit them using `/commit` before proceeding.

**Step 3e — Final validation**: Confirm all remaining features have their `plan_path` on disk. Any still missing at this point are marked `failed`.

### 4. Generate Batch Master Plan

Use the overnight batch plan generator to create a temporary master plan for this round's features. Pass a `feature_plan_paths` dict mapping each feature name to its `plan_path` from state. The function returns a tuple of `(plan_path, excluded)` — unpack both:

```python
from cortex_command.overnight.batch_plan import generate_batch_plan
plan_path, excluded = generate_batch_plan(
    features=["feature-a", "feature-b"],
    feature_plan_paths={"feature-a": "lifecycle/actual-dir-a/plan.md", "feature-b": "lifecycle/actual-dir-b/plan.md"},
    test_command=None,
    base_branch=integration_branch,
    output_path=Path("{session_dir}") / "batch-plan-round-{round_number}.md",
)
```

**Step 4a — Handle excluded features**: `excluded` is a list of dicts with `"name"` and `"error"` keys for features whose plans could not be parsed. For each excluded feature, mark it as `failed` in the overnight state (same mechanism as Step 3e for missing plans) and log a `FEATURE_FAILED` event to the overnight events log before proceeding to batch execution:

```python
from cortex_command.overnight.events import FEATURE_FAILED, log_event
from cortex_command.overnight.orchestrator_io import save_state, update_feature_status

state_path = Path("{state_path}")
for ex in excluded:
    # Update the feature's status to "failed" with the error in overnight state
    update_feature_status(state, ex["name"], "failed", error=ex["error"])
    save_state(state, state_path)
    # Log the failure event
    log_event(
        FEATURE_FAILED,
        round={round_number},
        feature=ex["name"],
        details={"error": ex["error"], "stage": "batch_plan_generation"},
        log_path=Path("{events_path}"),
    )
```

Features marked failed here are excluded from all subsequent steps in this round.

### 8. Exit

Exit cleanly. runner.sh will invoke `batch_runner.py` (step 5) and `map_results.py` (steps 6–7a) after this agent exits.
