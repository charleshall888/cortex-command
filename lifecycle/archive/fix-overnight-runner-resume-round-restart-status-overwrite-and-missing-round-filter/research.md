# Research: Fix overnight runner resume path

## Codebase Analysis

### Files That Will Change

1. **`claude/overnight/runner.sh`**
   - Line 519: `ROUND=1` hardcoded — must read from `state.current_round` on resume
   - Line 756: `MERGED_THIS_ROUND=$(( MERGED_AFTER - MERGED_BEFORE ))` — can go negative on resume; `MERGED_BEFORE` must be captured inside the round loop
   - Line 763: stall check `MERGED_THIS_ROUND -eq 0` — should be `-le 0` to catch negatives
   - Lines 525–530: pre-loop `MERGED_BEFORE` capture — must be eliminated/moved inside loop

2. **`claude/overnight/prompts/orchestrator-round.md`**
   - §1 (currently lines 154, 201, 207 area): mentions `round_assigned == current_round` but never implements the filter
   - Fix: Add an explicit Python code-block filter (same style as the existing §2a dependency gate) to exclude features not yet assigned to the current round
   - **Critical constraint from adversarial review**: filter must be `round_assigned <= current_round` (not `==`), and must exempt `paused` features regardless of `round_assigned` — otherwise conflict-recovery re-queues are incorrectly excluded

3. **`claude/overnight/map_results.py`**
   - `_map_results_to_state()` lines 90–122: unconditionally overwrites terminal statuses in `features_paused` and `features_failed` loops
   - `_handle_missing_results()` lines 162–166: already has the correct guard — `if fs.status in _TERMINAL_STATUSES: continue`
   - Fix: mirror the existing guard into the `features_paused` and `features_failed` blocks in `_map_results_to_state()`
   - `_TERMINAL_STATUSES = frozenset({"merged", "failed", "deferred"})` already defined at line 32

### Existing Patterns and State Structure

- **`OvernightState.current_round: int`** (state.py:198) — already persisted; updated at end of each round (runner.sh:797)
- **`OvernightFeatureStatus.round_assigned: Optional[int]`** (state.py:87) — per-feature; set during session creation; persisted across resume; preserved by interrupt handler (not reset to `pending`)
- **Round increment** happens at line 797, *after* map_results completes — see edge case below
- **`determine_resume_point()` in state.py** (lines 572–625) treats `paused`, `failed`, and `deferred` as "needs work" — but `count_pending()` in runner.sh only counts `pending` and `running`
- **Interrupt handler** (`interrupt.py`) resets interrupted features to `pending` but preserves `round_assigned`
- **Stall circuit breaker** at runner.sh:763 uses `MERGED_THIS_ROUND -eq 0` — this silently passes for negative values

### Integration Points

- `map_results.py` is called from runner.sh after each `batch_runner.py` invocation; writes `batch-N-results.json` → updates `overnight-state.json`
- `round_history` in state tracks per-round summaries but is written by `map_results.py`, not available before the round completes
- `batch_id = ROUND` throughout (consistent; no changes needed to this mapping)
- Orchestrator prompt receives `{round_number}` substitution from runner.sh (line 605 area)

## Web Research

Prior art is strongly consistent with the proposed fixes. Patterns from Spring Batch, Symphony (OpenAI), and AWS Batch all confirm:

- **Read resume point from state, never hardcode**: Standard checkpoint pattern — `round = state['last_completed'] + 1`, not a literal. Google ADK reads `agent_state` at startup before any dispatch; Spring Batch reads last step status from `JobRepository`.
- **Terminal state is default-skip**: Spring Batch skips `COMPLETED` steps by default; AWS Batch never re-dispatches `SUCCEEDED`/`FAILED` jobs. The opt-in is explicit (`allowStartIfComplete=true`); the default is idempotent skip.
- **Filter before dispatch, not after**: Symphony checks terminal status before adding to the dispatch queue, not in the dispatch handler. The pre-dispatch filter is the canonical form.
- **Per-item eligibility, not delta arithmetic**: Deriving "remaining work" by filtering live state (`[f for f in features if f['status'] not in DONE_STATES]`) avoids non-monotonic arithmetic entirely. AWS Lambda Powertools uses `INPROGRESS`/`COMPLETE`/`EXPIRED` state per item — never a batch delta.
- **Analog for negative-count bug**: Pydantic AI issue #3983 — `new_messages()` returned negative results when history processors removed messages, producing a negative index. Fix: `max(0, computed_index)` + don't assume prior-run count is always smaller.

No conflicting signals found between agents.

## Requirements & Constraints

**From `requirements/pipeline.md`:**

- Session Orchestration AC: "Paused sessions resume to the phase they paused from" — violated by Bug 1 (round hardcode)
- Feature Status Lifecycle: `pending → running → merged` is the success path; statuses are forward-only and terminal states are immutable — violated by Bug 3 (status overwrite)
- Edge Cases: "Features already at `merged` are skipped via idempotency tokens; `paused` features re-enter the execution queue" — violated by Bugs 2 and 3
- Atomicity constraint: "All state writes are atomic (tempfile + `os.replace()`) — partial-write corruption is not possible" — Bug 3 violates the spirit of this by corrupting state through a legal write

**From `requirements/multi-agent.md`:**

- "Sessions that resume after interruption skip features already merged (plan hash + task ID used as idempotency tokens)" — directly violated by current resume path
- "Features with `intra_session_blocked_by` dependencies are excluded from dispatch at round-planning time (orchestrator prompt), not at dispatch time" — the round filter belongs in the orchestrator prompt (same layer as the dependency gate), consistent with the proposed fix

## Tradeoffs & Alternatives

### Bug 1 — Round selection on resume

**Approach A (recommended)**: One-liner replacing `ROUND=1` with `ROUND=$(python3 -c "import json; print(json.load(open('$STATE_PATH'))['current_round'])")` — consistent with every other session-metadata read in runner.sh.

**Approach B**: Accept `--start-round N` CLI flag. Requires callers to know the current round out-of-band; adds coordination burden the state file already solves.

**Critical edge case (adversarial)**: `state.current_round` is updated *after* map_results runs. If the session crashes during map_results (after batch completes, before the increment), the state has `current_round = N` and `batch-N-results.json` already exists. On resume, fix A would re-run round N. Mitigation: check whether `batch-{N}-results.json` exists before treating `current_round` as the next round to run. If results file exists, skip to N+1.

### Bug 2 — Round filter in dispatch

**Approach A (recommended)**: Add a Python code-block filter to orchestrator-round.md §1, styled like the existing §2a dependency gate. The orchestrator already executes Python code blocks for §2a; a §1 addition is architecturally consistent.

**Approach B**: Pre-compute eligible features in runner.sh and inject as a constrained list into the prompt. More robust but adds template injection complexity and diverges from "agent reads state directly" architecture.

**Approach C**: Add a new Python eligibility module callable from the orchestrator. New module for a simple filter — over-engineered.

**Critical filter semantics (adversarial — must get this right)**:
- **Wrong**: `round_assigned == current_round` — excludes `paused` features from prior rounds and interrupted features (which retain their original `round_assigned`)
- **Right**: `round_assigned <= current_round OR status == 'paused'` — or equivalently, exclude only features with `round_assigned > current_round AND status == 'pending'`
- The intent is: "don't dispatch future-round features, but always allow paused/recovery features through"

### Bug 3 — Terminal status overwrite

**Approach A (recommended)**: Add `if fs.status in _TERMINAL_STATUSES: continue` to the `features_paused` and `features_failed` loops in `_map_results_to_state()`, mirroring the existing guard in `_handle_missing_results()`.

**Approach B**: Filter results lists upstream before entering the update loops. Splits filter and update responsibilities across two locations; Approach A is more cohesive.

**Approach C**: Only protect `merged` status. Creates asymmetry since `_TERMINAL_STATUSES` already defines the full set.

**Adversarial note**: The `merged` loop should not itself be guarded (overwriting `failed`→`merged` on a successful retry is correct behavior). The critical protection is on `features_paused` and `features_failed` only.

### Bug 4 — Negative merged-count arithmetic

**Approach A (recommended)**: Move `MERGED_BEFORE` capture inside the round loop (before the orchestrator spawns each round), eliminating the pre-loop initialization. The existing end-of-round `MERGED_BEFORE=$MERGED_AFTER` continues to serve for rounds 2+.

**Approach B**: Read round-level merged count from `state.round_history`. More principled but adds an extra Python read after each batch; `round_history` is populated by `map_results.py` so ordering is correct, but adds indirection.

**Approach C**: `max(0, MERGED_AFTER - MERGED_BEFORE)` band-aid. Silences the display bug but doesn't fix the stall detector interaction.

**Additional mitigation (adversarial)**: Change stall test at runner.sh:763 from `-eq 0` to `-le 0`. The root fix (Approach A) prevents the negative value, but the guard catches any future regression.

## Adversarial Review

### Failure modes and edge cases

1. **Bug 1 edge case — crash during map_results before round increment**: `state.current_round` is updated at the *end* of each round, after `map_results.py` completes. If the runner crashes during `map_results.py`, `current_round` still has the round N value but `batch-N-results.json` may already be written. On resume, the fix reads `current_round=N` and re-spawns the orchestrator for round N — re-dispatching partially-mapped features. Fix: check for existence of `batch-{N}-results.json` and if present, skip to N+1 (or commit to write-ahead incrementing `current_round` before map_results runs).

2. **Bug 2 edge case — paused feature exemption is critical**: `paused` features retain their original `round_assigned` from prior rounds. A filter of `round_assigned == current_round` would exclude them. `determine_resume_point()` classifies `paused` as "needs work" but a strict round filter would silently drop them from the dispatch queue. The filter must exempt `paused` features: `(round_assigned <= current_round) OR (status == 'paused')`.

3. **Bug 2 edge case — interrupted features**: `interrupt.py` resets interrupted features to `pending` but preserves `round_assigned`. A feature interrupted mid-run retains its original `round_assigned` (e.g., 1) but if `current_round` was already advanced to 2, the `== current_round` filter would incorrectly exclude it. The `<= current_round` semantics fix this.

4. **Bug 4 — stall detector with negative counts**: The stall circuit breaker at runner.sh:763 checks `-eq 0`. A negative `MERGED_THIS_ROUND` would not trigger the stall counter, producing silent incorrect progress tracking. Change to `-le 0`.

5. **Existing bug — `count_pending()` doesn't count `paused`**: runner.sh's `count_pending()` only counts `pending` and `running` features. If only `paused` features remain, it returns 0 and the runner exits thinking the session is complete. This is pre-existing and independent of the four fixes, but the round filter interacts with it: if the filter incorrectly drops paused features, `count_pending()` may return 0 and terminate the session prematurely. Out of scope for #040 but must not be made worse.

### Assumptions that may not hold

- Bug 3 fix assumes `paused` is the only result that can overwrite `merged` — verified correct; the `merged` loop processes first and the `paused`/`failed` guards prevent the overwrite.
- Bug 2 prompt fix assumes the LLM consistently executes code blocks as written — empirically supported by the existing §2a gate which uses the same pattern, but softer than code enforcement.

### Recommended mitigations

1. Bug 1 fix must include a `batch-{N}-results.json` existence check alongside the `current_round` read.
2. Bug 2 filter must be `round_assigned <= current_round OR status == 'paused'`, not `== current_round`.
3. Bug 4 stall test must change to `-le 0`.
4. Pre-existing `count_pending()` / `paused` interaction is out of scope but spec should explicitly call it out as a known limitation.

## Open Questions

- **Q1**: Should `current_round` be incremented write-ahead (before map_results) rather than write-after (current), to eliminate the crash-during-map_results edge case? Write-ahead is safer for resumability but means a crashed round N session would skip to N+1 on resume, potentially leaving round N's results unmapped.
- **Q2**: For the Bug 2 orchestrator prompt fix — should the filter be expressed as prose instruction ("only process features where round_assigned <= current_round or status is paused") or as a Python code block (like §2a)? Code block is more machine-legible but tightly couples the prompt to the state schema. If the schema changes, the prompt code block silently breaks.
- **Q3**: The `count_pending()` / `paused` interaction is a pre-existing bug. Should #040 fix it (by adding `paused` to the pending count) or leave it out of scope to keep the PR focused?
