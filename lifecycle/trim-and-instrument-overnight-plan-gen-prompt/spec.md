# Specification: Trim and instrument overnight plan-gen prompt

> **Scope note**: This spec reflects a reduced scope from the original backlog item. Deliverable #1 (conditional prompt trimming) is **deferred**. Research (see `research.md`) found that the trim saves pennies per session at real behavior-change risk, the epic discovery research did not endorse trimming, and the better path is to gather instrumentation data first. If the new event shows zero plan-gen dispatches over several sessions, a future ticket can retire Steps 3a-3e outright (cleaner than a conditional include). See `research.md` §Recommended Approach (Option C).
>
> **Epic reference**: `research/overnight-plan-building/research.md`

## Problem Statement

We currently *believe* plan-gen Steps 3a-3e in the overnight orchestrator prompt have never triggered in production. That belief is based on anecdotal reading of event logs for patterns, not instrumentation. Without direct evidence, we cannot confidently retire the plan-gen fallback or use frequency data to revisit the extraction decision (DR-1 "Contingency" in the epic research). Additionally, the one existing LLM-side `log_event` call in the orchestrator prompt (Step 4a's `FEATURE_FAILED` path) silently attributes round-1 events to `session_id: "manual"` because `LIFECYCLE_SESSION_ID` is exported in the wrong place in `runner.sh`. Any new LLM-side instrumentation inherits this bug.

This spec delivers a deterministic event when plan-gen sub-agents actually dispatch, fixes the prerequisite `LIFECYCLE_SESSION_ID` data-quality bug, and leaves the orchestrator prompt structurally unchanged.

## Requirements

1. **New `plan_gen_dispatched` event type added to `claude/overnight/events.py`**: The event name constant `PLAN_GEN_DISPATCHED = "plan_gen_dispatched"` is added to the constants block (lines 32-76), and the string `"plan_gen_dispatched"` is added to the `EVENT_TYPES` tuple (lines 78-124). **Acceptance**: `grep -c 'PLAN_GEN_DISPATCHED' claude/overnight/events.py` ≥ 2 (constant + tuple entry). `python3 -c "from claude.overnight.events import PLAN_GEN_DISPATCHED, EVENT_TYPES; assert PLAN_GEN_DISPATCHED in EVENT_TYPES"` exits 0.

2. **Orchestrator prompt emits the event inside Step 3b when plan-gen sub-agents are about to dispatch**: `claude/overnight/prompts/orchestrator-round.md` is modified to add an inline Python `log_event` call at the top of Step 3b, executed by the orchestrator LLM before the Task-tool fan-out. The call imports `PLAN_GEN_DISPATCHED` and `log_event` from `claude.overnight.events`, following the Step 4a precedent (lines 295-313). The event is emitted once per round in which plan-gen actually dispatches — not per feature. **Acceptance**: `grep -c 'PLAN_GEN_DISPATCHED' claude/overnight/prompts/orchestrator-round.md` = 1. `grep -c 'log_event' claude/overnight/prompts/orchestrator-round.md` ≥ 2 (existing Step 4a + new Step 3b).

3. **Event payload includes actionable fields**: When emitted, the event details dict contains `features` (list of feature slugs whose `plan_path` was missing), `reason` ("missing_plan_path"), `spec_paths` (dict of slug → spec_path), and `plan_paths` (dict of slug → expected plan_path). The top-level `round` field is populated from the orchestrator's `{round_number}` substitution, and `feature` is omitted (this is a round-level event, not a per-feature event). **Acceptance**: Inspecting the prompt text, the Step 3b `log_event` call has the following form (exact field names) — verified by `grep -A5 'PLAN_GEN_DISPATCHED' claude/overnight/prompts/orchestrator-round.md` showing `details={"features"`, `"reason"`, `"spec_paths"`, `"plan_paths"`.

4. **`LIFECYCLE_SESSION_ID` is exported before the orchestrator spawns**: The `export LIFECYCLE_SESSION_ID="$SESSION_ID"` statement in `claude/overnight/runner.sh` is moved from its current location (around line 708, inside the batch_runner branch) to a location BEFORE the orchestrator spawn at line 643. This ensures both the existing Step 4a `log_event` call AND the new Step 3b call attribute round-1 events to the correct session ID rather than falling back to `"manual"`. **Acceptance**: `grep -n 'export LIFECYCLE_SESSION_ID' claude/overnight/runner.sh` returns a line number LESS than the line number returned by `grep -n 'claude.*-p' claude/overnight/runner.sh | head -1`. Additionally, a manual comment in the commit message references this as a data-quality fix.

5. **Events.py contract test**: A new test (`tests/test_events_contract.py` or added to an existing test file) imports `claude/overnight/prompts/orchestrator-round.md` as text, scans for `log_event(` calls, extracts the first positional argument from each call (the event-type identifier), and asserts each extracted identifier maps to a constant that is in `EVENT_TYPES`. This catches the drift class of bug where a new event constant gets added to the prompt but forgotten in `events.py`. **Acceptance**: `just test` exits 0 with the new test included. Deliberately introducing a bad event name in the prompt causes the test to fail. Test is kept minimal — ~20-30 lines.

## Non-Requirements

- **Deliverable #1 (conditional prompt trimming) is NOT in scope.** No `{plan_gen_block}` token, no template split, no delimiter-based excision, no `fill_prompt()` changes. Steps 3a-3e remain physically present in `orchestrator-round.md` unchanged. This is a deliberate deferral — see scope note above.
- **No `plan_gen_completed` event.** Completion is inferrable from the absence of a subsequent `feature_failed` event with `details.stage == "plan_generation"` (or equivalent) for the same feature. Emitting a completion event adds a second LLM-side reliability point for redundant information.
- **No `plan_gen_skipped` event.** Absence of `plan_gen_dispatched` in a round IS the skipped signal. Emitting skipped on every round (which would be every round in the steady state) inverts signal-to-noise.
- **No harness-side hook (`PreToolUse` matcher: "Agent").** The research found this approach has granularity problems (cannot distinguish plan-gen from other Agent dispatches without parsing sub-agent prompts), scope problems (`claude/settings.json` is a repo-wide template), and compatibility unknowns under `--dangerously-skip-permissions`.
- **No changes to plan-gen fallback behavior.** The dispatch, deferral handling, and final validation logic in Steps 3a-3e are untouched. Only the instrumentation is added.
- **No changes to `pipeline-events.log`.** The new event targets `overnight-events.log` (the session/orchestrator log). These are different files with different writers — `pipeline-events.log` is written by `batch_runner.py` via `claude.pipeline.state.log_event()`.
- **No new helper modules.** The shared round-filter helper recommended as "A7" in research is not needed since deliverable #1 is deferred.

## Edge Cases

- **Round 1 attribution**: After the `LIFECYCLE_SESSION_ID` export move, round-1 `log_event` calls attribute to the correct session. Before the fix, they fell back to `"manual"`. Verification: manually inspect one round-1 event in a recent `overnight-events.log` for the existing Step 4a call — if any exist, they should have `session_id: "manual"` today and will have the correct session ID after the fix.
- **LLM skips the instrumentation call**: LLM self-audit reliability is imperfect (see `research.md` web agent findings). If the orchestrator dispatches plan-gen sub-agents but does not execute the inline Python for the `log_event` call — e.g., due to turn-budget pressure — the event is silently dropped. This is acceptable for a zero-frequency decision-support signal: a missed event over-represents "plan-gen never fires," which is the null hypothesis we already believe. If the event later shows unexpectedly high frequency, dropped events would *understate* the true rate, meaning the signal is directionally reliable (underestimates, never overestimates).
- **Events.py ValueError on unknown type**: If the prompt's inline `log_event` call references an event name not in `EVENT_TYPES`, `log_event()` raises ValueError inside the orchestrator's Python execution. The contract test in Requirement 5 is specifically designed to catch this drift class before it ships.
- **Future new Agent dispatches in the prompt**: If a future refactor adds other Agent-tool sub-dispatches to the orchestrator prompt (e.g., for a new escalation-resolution sub-agent), those new dispatches will NOT emit `plan_gen_dispatched` — they would need their own event type. The Step 3b call is scoped to plan-gen specifically by its placement, not by any runtime matcher.
- **Contract test false negative**: The regex scan in the contract test may miss calls inside unusual formatting (e.g., a `log_event(` call split across multiple lines in an unusual way). For the current prompt and the single added call, a straightforward `grep -oE` works. If future prompt formatting complicates this, the test can be upgraded to use a proper Python AST parse of embedded Python blocks.

## Changes to Existing Behavior

- **ADDED**: New event type `plan_gen_dispatched` in `overnight-events.log`. Downstream readers (dashboard `data.py:631`, morning report, metrics) tolerate unknown events — no crashes expected. Dashboard and metrics will not display it unless they're updated to recognize it (out of scope for this ticket).
- **MODIFIED**: Existing Step 4a `FEATURE_FAILED` events in round 1 will now attribute to the correct session ID instead of `"manual"`. This is a silent data-quality improvement to the existing event stream; no downstream consumer depends on the `"manual"` value.
- **ADDED**: New orchestrator-prompt instruction in Step 3b to emit the event before Task-tool fan-out. Adds ~10 lines to `orchestrator-round.md`.
- **MODIFIED**: `runner.sh` exports `LIFECYCLE_SESSION_ID` earlier in the session bootstrap, above the orchestrator spawn. The export is a pure variable-scope move, not a behavior change.

## Technical Constraints

- **`log_event()` strict validation**: `events.py:184` raises ValueError on unknown event types. The new constant MUST be added to both the constants block AND the `EVENT_TYPES` tuple atomically in the same change.
- **LLM-side `log_event` precedent**: The new Step 3b call must structurally match the existing Step 4a precedent (`orchestrator-round.md:295-313`) — same import path (`from claude.overnight.events import ..., log_event`), same `log_path=Path("{events_path}")` substitution, same `round={round_number}` substitution. The `orchestrator_io.py` module is the sanctioned import surface.
- **Substitution tokens**: The prompt's `{round_number}` and `{events_path}` tokens are substituted by `fill_prompt()` at runner.sh:379-394. No new tokens are introduced by this spec.
- **Fail-open by omission**: If the LLM skips the instrumentation call, no event is logged and the round proceeds normally. There is no runner-side fallback or cross-check. This is intentional — the event is decision-support, not load-bearing.
- **Commit discipline**: The `LIFECYCLE_SESSION_ID` export move is a bugfix independent of the instrumentation logic. It should land as a separate commit within the same PR so the bugfix stands alone in history.

## Open Decisions

(None. All decisions have been resolved with the user during the scope conversation that followed research.)
