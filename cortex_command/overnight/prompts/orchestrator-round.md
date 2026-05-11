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

**Cycle-breaking check**: Before attempting resolution, check for prior resolutions via the precomputed per-feature dict:

```python
prior_resolutions = ctx["escalations"]["prior_resolutions_by_feature"].get(entry["feature"], [])
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

**Step 3b.1 — Criticality branch (synthesizer dual-plan path)**: Before falling through to the single-agent dispatch template below, partition `missing` into a critical-tier subset that takes the parallel-variant + synthesizer path and a non-critical subset that takes the existing single-agent path unchanged. The branch is gated by `synthesizer_overnight_enabled` in `lifecycle.config.md`; when the gate is `false` (default, fail-closed), all features fall through to the single-agent path.

```python
from cortex_command.overnight.cli_handler import read_synthesizer_gate
from cortex_command.overnight.events import (
    PLAN_SYNTHESIS_DISPATCHED,
    PLAN_SYNTHESIS_DEFERRED,
    SYNTHESIZER_ERROR,
)
import json

# Repo-root lifecycle.config.md (fail-closed: missing file -> gate False).
gate_enabled = read_synthesizer_gate(Path("lifecycle.config.md"))

def _read_criticality(feature_slug: str) -> str:
    """Most-recent ``lifecycle_start`` or ``criticality_override`` event wins.

    Default to ``"medium"`` when no criticality field is found, mirroring
    ``skills/lifecycle/references/plan.md`` §1a precedent.
    """
    events_path = Path(f"lifecycle/{feature_slug}/events.log")
    if not events_path.exists():
        return "medium"
    last = "medium"
    for line in events_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("event") in ("lifecycle_start", "criticality_override"):
            crit = entry.get("criticality")
            if isinstance(crit, str):
                last = crit
    return last

critical_subset = []
single_agent_subset = []
for f in missing:
    if gate_enabled and _read_criticality(f["slug"]) == "critical":
        critical_subset.append(f)
    else:
        single_agent_subset.append(f)
```

For each feature in `critical_subset`, run the synthesizer dual-plan flow described in (1)–(8) below. After the critical_subset processing finishes, the surviving features (those that the synthesizer auto-selected a variant for) have their `plan.md` written; deferred features are marked `deferred` in the orchestrator agent's exit-report envelope (worker-style wrapper) so `runner.py` can route them through the existing `cortex_command/overnight/deferral.py:write_deferral` channel. Features in `single_agent_subset` continue to the existing single-agent dispatch template below — no change to non-critical-tier behavior.

(1) **Variant dispatch (criticality == critical branch)**: For each feature whose criticality is `critical`,
dispatch 2-3 parallel Sonnet plan-gen Task sub-agents writing to `plan-variant-A.md`,
`plan-variant-B.md`, optionally `plan-variant-C.md` under `lifecycle/{{feature_slug}}/`.
The orchestrator agent decides 2 vs 3 based on how many distinct approaches are identifiable from spec+research; minimum 2, maximum 3. Each sub-agent uses the **same** plan-agent prompt template as the single-agent path below (lines reading "You are generating an implementation plan ..."), substituting `{{feature_plan_path}}` per variant. Emit `PLAN_SYNTHESIS_DISPATCHED` before dispatch:

```python
log_event(
    PLAN_SYNTHESIS_DISPATCHED,
    round={round_number},
    feature=f["slug"],
    details={
        "variant_count": variant_count,  # 2 or 3
        "variant_paths": [
            f"lifecycle/{f['slug']}/plan-variant-A.md",
            f"lifecycle/{f['slug']}/plan-variant-B.md",
            # plan-variant-C.md if variant_count == 3
        ],
    },
    log_path=Path("{events_path}"),
)
```

(2) **Variant-edge cases**: After all variant sub-agents return:
- If **only 1 variant** wrote successfully (the others crashed or returned `{"status": "deferred"}`): accept it directly. Copy that variant's content to `lifecycle/{{feature_slug}}/plan.md`, append a v2 `plan_comparison` event with `disposition: "auto_select"`, `selector_confidence: "high"`, `selection_rationale: "single surviving variant"`, `operator_choice: null`, `schema_version: 2`, and `position_swap_check_result: "agreed"`. Skip the synthesizer dispatch for this feature.
- If **all variants failed**: fall back to the single-agent path — append the feature back to `single_agent_subset` so it goes through the existing dispatch template below.
- If **≥2 variants succeeded**: proceed to the synthesizer Task sub-agent dispatch in (3) below.

(3) **Synthesizer dispatch**: Dispatch one fresh Opus synthesizer Task sub-agent per critical feature with ≥2 surviving variants. The sub-agent's **system prompt** is the shared fragment loaded from `cortex_command/overnight/prompts/plan-synthesizer.md` via `importlib.resources.files("cortex_command.overnight.prompts").joinpath("plan-synthesizer.md").read_text()` — do not paraphrase or inline. The **user prompt** inlines the surviving variant paths (`lifecycle/{{feature_slug}}/plan-variant-A.md`, etc.) and the swap-and-require-agreement instruction directing the synthesizer to compare the variants twice with order swapped before assigning `confidence: "high"` or `"medium"`, and to emit a JSON envelope per the schema in the system prompt fragment. The synthesizer is read-only; no worktree isolation is required.

(4) **Envelope extraction (LAST-occurrence anchor)**: Parse the synthesizer Task sub-agent's output using the same LAST-occurrence anchor pattern as the canonical `skills/lifecycle/references/plan.md` §1b:

```python
import re
matches = list(re.finditer(r'^<!--findings-json-->\s*$', synth_output, re.MULTILINE))
if not matches:
    envelope = None  # malformed: route as confidence=low
else:
    tail = synth_output[matches[-1].end():]
    try:
        envelope = json.loads(tail)
        # Validate: schema_version=2, per_criterion (object), verdict in {A,B,C},
        # confidence in {high,medium,low}, rationale (string).
        if not (
            envelope.get("schema_version") == 2
            and isinstance(envelope.get("per_criterion"), dict)
            and envelope.get("verdict") in ("A", "B", "C")
            and envelope.get("confidence") in ("high", "medium", "low")
            and isinstance(envelope.get("rationale"), str)
        ):
            envelope = None
    except (json.JSONDecodeError, ValueError):
        envelope = None
```

The `last occurrence` semantics tolerate prose that quotes the `<!--findings-json-->` delimiter earlier in the response.

(5) **Route on verdict + confidence**:

- **`verdict ∈ {"A","B","C"}` AND `confidence ∈ {"high","medium"}`**: copy the selected variant's content to `lifecycle/{{feature_slug}}/plan.md` (verdict `"A"` → `plan-variant-A.md`, `"B"` → `plan-variant-B.md`, `"C"` → tie at high/medium confidence is a logically impossible state per the synthesizer fragment, so treat as malformed and follow the deferred branch). Then append a v2 `plan_comparison` event to `lifecycle/{{feature_slug}}/events.log`:

  ```python
  with open(f"lifecycle/{f['slug']}/events.log", "a", encoding="utf-8") as fh:
      fh.write(json.dumps({
          "ts": "<ISO 8601 UTC>",
          "event": "plan_comparison",
          "schema_version": 2,
          "feature": f["slug"],
          "variants": [
              {"label": "Plan A", "approach": "<summary>", "task_count": <N>, "risk": "<risk summary>"},
              # plus Plan B (and Plan C if 3 variants survived)
          ],
          "selected": "Plan A",  # or "Plan B" / "Plan C"
          "selection_rationale": envelope["rationale"],
          "selector_confidence": envelope["confidence"],
          "position_swap_check_result": "agreed",  # high/medium implies swap probe agreed
          "disposition": "auto_select",  # overnight surface: no operator
          "operator_choice": None,
      }) + "\n")
  ```

  The `disposition: "auto_select"` value is reserved for the overnight surface; `operator_choice` is always `null` here. The round continues to Step 3c for this feature.

- **`confidence: "low"` OR malformed envelope**: emit `PLAN_SYNTHESIS_DEFERRED` and mark the feature `deferred` in the orchestrator agent's exit-report envelope (worker-style exit-report wrapper):

  ```python
  log_event(
      PLAN_SYNTHESIS_DEFERRED,
      round={round_number},
      feature=f["slug"],
      details={
          "reason": "low_confidence" if envelope else "malformed_envelope",
          "selector_confidence": (envelope or {}).get("confidence", "low"),
      },
      log_path=Path("{events_path}"),
  )
  # In the orchestrator agent's final exit-report envelope, mark this feature:
  #   {"slug": f["slug"], "status": "deferred", "reason": "synthesizer deferred (low confidence)"}
  # runner.py routes the deferred feature through the existing
  # cortex_command/overnight/deferral.py:write_deferral channel
  # (worker-exit-report deferral path). This avoids introducing a new
  # orchestrator-side deferral source.
  ```

  Also append a v2 `plan_comparison` event with `disposition: "deferred"`, `selector_confidence: "low"`, `selection_rationale: "synthesizer deferred"`, `position_swap_check_result: "disagreed"`, `selected: "none"`, `operator_choice: null`, `schema_version: 2` so the audit trail records the deferral.

(6) **Synthesizer SDK error**: If the Opus synthesizer Task sub-agent crashes, times out, or the SDK call raises, treat the result as `confidence: "low"` for routing purposes. Emit `SYNTHESIZER_ERROR` **before** the `PLAN_SYNTHESIS_DEFERRED` event so post-session triage has both signals:

```python
log_event(
    SYNTHESIZER_ERROR,
    round={round_number},
    feature=f["slug"],
    details={"error": str(exc), "stage": "synthesizer_dispatch"},
    log_path=Path("{events_path}"),
)
# then proceed with the deferred branch in (5) above
```

(7) **Anti-sway role separation**: The synthesizer Task sub-agent is dispatched fresh — it shares no context with the variant plan-gen sub-agents from (1) and no context with the orchestrator agent itself. Enforced by issuing a NEW Task sub-agent each time, never reusing a prior agent's session.

(8) **Fall-through to single-agent path**: After processing all critical-tier features in `critical_subset`, the orchestrator agent dispatches the **remaining** non-critical features in `single_agent_subset` through the existing single-agent path immediately below. Critical-tier features whose synthesizer auto-selected a variant have already had their `plan.md` written and skip the dispatch template entirely; deferred critical-tier features are marked `deferred` in the exit-report envelope and excluded from this round.

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
    feature_plan_paths={"feature-a": "lifecycle/<feature-a-slug>/plan.md", "feature-b": "lifecycle/<feature-b-slug>/plan.md"},
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
