# Plan: Trim and instrument overnight plan-gen prompt

## Overview

Four changes across four files, in dependency order. Task 1 adds the new event constant atomically to both the constants block and the EVENT_TYPES tuple in `events.py`. Task 2 moves `LIFECYCLE_SESSION_ID` export in `runner.sh` to above the orchestrator spawn — this is a prerequisite data-quality fix that must ship as a separate commit. Task 3 adds the inline `log_event` call to Step 3b of the orchestrator prompt using the Step 4a pattern as a structural template. Task 4 adds a contract test that scans the orchestrator prompt for `log_event(` calls and asserts each event-type identifier maps to a constant in EVENT_TYPES.

Tasks 1 and 2 are independent and can be done in either order. Task 3 depends on Task 1 (the constant must exist before the prompt references it). Task 4 depends on Tasks 1 and 3 (the test must pass against the final state of both files).

## Tasks

---

### Task 1 — Add `PLAN_GEN_DISPATCHED` constant and tuple entry to `events.py`

**Files**: `/Users/charlie.hall/Workspaces/cortex-command/claude/overnight/events.py`

**What**: Add `PLAN_GEN_DISPATCHED = "plan_gen_dispatched"` to the constants block (after line 76, after `MORNING_REPORT_COMMIT_FAILED`) and add `PLAN_GEN_DISPATCHED,` to the `EVENT_TYPES` tuple (after line 123, after `MORNING_REPORT_COMMIT_FAILED`). Both additions must be in the same commit.

**Depends on**: Nothing.

**Context**: The constants block runs lines 32–76; the tuple runs lines 78–124. `log_event()` at line 184 raises `ValueError` if the event string is not in `EVENT_TYPES`. Adding the constant to both locations in one atomic change prevents the drift that would cause a runtime ValueError the first time the orchestrator executes the Step 3b call. The string value `"plan_gen_dispatched"` must match the constant name's snake_case convention used throughout the file.

**Verification**: Run `grep -c 'PLAN_GEN_DISPATCHED' /Users/charlie.hall/Workspaces/cortex-command/claude/overnight/events.py` — result must be 2 (one constant line, one tuple line). Run `python3 -c "from cortex_command.overnight.events import PLAN_GEN_DISPATCHED, EVENT_TYPES; assert PLAN_GEN_DISPATCHED in EVENT_TYPES; print('ok')"` from the repo root — must print `ok` and exit 0. The existing `test_all_log_event_calls_registered` test in `tests/test_events.py` must still pass (`just test` exits 0).

**Status**: pending

---

### Task 2 — Move `LIFECYCLE_SESSION_ID` export above orchestrator spawn in `runner.sh`

**Files**: `/Users/charlie.hall/Workspaces/cortex-command/claude/overnight/runner.sh`

**What**: Move the line `export LIFECYCLE_SESSION_ID="$SESSION_ID"` from line 708 (inside the `if [[ -f "$BATCH_PLAN_PATH" ]]` branch) to immediately before the orchestrator spawn at line 643 (`claude -p "$FILLED_PROMPT" ...`). The new location should be just before or just after the `echo "Spawning orchestrator agent for round $ROUND..."` line at line 636, within the round loop but outside the batch_runner conditional. No other lines change.

**Depends on**: Nothing (independent of Task 1).

**Context**: Line 708 is inside the `else` branch of `if [[ ! -f "$BATCH_PLAN_PATH" ]]`, so `LIFECYCLE_SESSION_ID` is exported only when a batch plan exists — that is, after the orchestrator has already run. On round 1, the orchestrator executes with `LIFECYCLE_SESSION_ID` unset, so the existing Step 4a `log_event` call and the new Step 3b call both fall back to `session_id: "manual"` (events.py line 191). Moving the export to before line 643 fixes this for all LLM-side log_event calls in all rounds. This is a pure variable-scope move — no other behavior changes. This task must ship as a separate commit from Task 3 per spec §Technical Constraints.

**Verification**: Run `grep -n 'export LIFECYCLE_SESSION_ID' /Users/charlie.hall/Workspaces/cortex-command/claude/overnight/runner.sh` and confirm the returned line number is less than the line number returned by `grep -n 'claude -p' /Users/charlie.hall/Workspaces/cortex-command/claude/overnight/runner.sh | head -1`. The existing `test_runner_signal.py` and `test_runner_resume.py` tests must still pass (`just test` exits 0).

**Status**: pending

---

### Task 3 — Add `log_event(PLAN_GEN_DISPATCHED, ...)` call at top of Step 3b in the orchestrator prompt

**Files**: `/Users/charlie.hall/Workspaces/cortex-command/claude/overnight/prompts/orchestrator-round.md`

**What**: Insert an inline Python `log_event` call at the top of Step 3b (after line 238, the `**Step 3b — Generate missing plans**:` header line). The call must appear before the instruction to dispatch Task sub-agents. The call follows the Step 4a precedent at lines 297–313 structurally: same import path (`from cortex_command.overnight.events import PLAN_GEN_DISPATCHED, log_event`), same `log_path=Path("{events_path}")` substitution, same `round={round_number}` substitution. The `feature` argument is omitted (this is a round-level event). The `details` dict must include fields: `features` (list of feature slugs whose plan_path was missing), `reason` (string `"missing_plan_path"`), `spec_paths` (dict of slug → spec_path), `plan_paths` (dict of slug → expected plan_path).

The inserted block (modeled on Step 4a) should read:

```python
from cortex_command.overnight.events import PLAN_GEN_DISPATCHED, log_event
from pathlib import Path

log_event(
    PLAN_GEN_DISPATCHED,
    round={round_number},
    details={
        "features": [<list of slugs whose plan_path is missing>],
        "reason": "missing_plan_path",
        "spec_paths": {<slug: spec_path for each feature>},
        "plan_paths": {<slug: expected plan_path for each feature>},
    },
    log_path=Path("{events_path}"),
)
```

The block is introduced with a brief instruction to the orchestrator to execute this before dispatching the Task sub-agents.

**Depends on**: Task 1 (the `PLAN_GEN_DISPATCHED` constant must exist in `events.py` before the prompt references it — otherwise, when the orchestrator executes the inline Python, it raises ImportError).

**Context**: Step 3b spans lines 238–265 in the current prompt. The Step 4a precedent is at lines 295–313 — the new call matches that structure exactly. The `{round_number}` and `{events_path}` tokens are substituted by `fill_prompt()` in `runner.sh:379–394` via `str.replace()`; no new tokens are introduced. The call is emitted once per round in which plan-gen actually dispatches, not once per feature — the `features` list captures all affected slugs in one event. If the LLM skips the call, no event is logged and the round proceeds normally (fail-open by omission per spec §Technical Constraints).

**Verification**: Run `grep -c 'PLAN_GEN_DISPATCHED' /Users/charlie.hall/Workspaces/cortex-command/claude/overnight/prompts/orchestrator-round.md` — result must be 1. Run `grep -c 'log_event' /Users/charlie.hall/Workspaces/cortex-command/claude/overnight/prompts/orchestrator-round.md` — result must be 2 (Step 3b new call + Step 4a existing call). Run `grep -A5 'PLAN_GEN_DISPATCHED' /Users/charlie.hall/Workspaces/cortex-command/claude/overnight/prompts/orchestrator-round.md` and confirm output includes `"features"`, `"reason"`, `"spec_paths"`, `"plan_paths"` field names.

**Status**: pending

---

### Task 4 — Add contract test scanning orchestrator prompt for `log_event(` calls

**Files**: `/Users/charlie.hall/Workspaces/cortex-command/tests/test_events_contract.py` (new file)

**What**: Create a new test file `tests/test_events_contract.py` (~25 lines). The test reads `claude/overnight/prompts/orchestrator-round.md` as text, finds all `log_event(` call sites using a regex, extracts the first positional argument from each call (the event-type identifier — either a constant name like `PLAN_GEN_DISPATCHED` or a string literal like `"feature_failed"`), and asserts that each extracted identifier resolves to a value in `EVENT_TYPES`. For constant-name identifiers, the test resolves them via `getattr(events, name)`. For string-literal identifiers, the test checks the string directly against `EVENT_TYPES`.

The existing `test_all_log_event_calls_registered` test in `tests/test_events.py` (lines 41–73) covers `.py` and `.sh` files in the overnight directory but does not scan prompt `.md` files — this new test fills that gap specifically for the orchestrator prompt.

**Depends on**: Task 1 (EVENT_TYPES must include `PLAN_GEN_DISPATCHED`), Task 3 (the prompt must contain the new `log_event(` call site for the test to be non-trivial).

**Context**: The existing test at `tests/test_events.py:41–73` is the model to follow for style. The new test does not duplicate it — it targets `.md` prompt files that the existing scan excludes. The test must fail if a `log_event(` call in the prompt references an event-type identifier not present in `EVENT_TYPES`. A sanity assertion (`assert len(found) >= 2`) ensures the regex finds at least the two expected call sites (Step 3b and Step 4a). Keep the file to ~25 lines.

**Verification**: Run `just test` — must exit 0 with the new test included and passing. To verify the test is not self-sealing, manually mutate a `log_event(` call in the prompt to reference a nonexistent event name (e.g., `BOGUS_EVENT`) and confirm `just test` exits non-zero with a descriptive assertion error. Restore the prompt after verification.

**Status**: pending

---

## Verification Strategy

The four tasks produce independently verifiable state at each step:

1. **After Task 1**: `grep -c PLAN_GEN_DISPATCHED events.py` = 2; the import assertion exits 0; `just test` exits 0.
2. **After Task 2**: `grep -n 'export LIFECYCLE_SESSION_ID' runner.sh` returns a line number below the `claude -p` spawn line; existing runner tests pass.
3. **After Task 3**: `grep -c log_event orchestrator-round.md` = 2; `grep -c PLAN_GEN_DISPATCHED orchestrator-round.md` = 1; field-name grep shows all four required details keys.
4. **After Task 4**: `just test` exits 0 across the full test suite. The contract test is validated as non-self-sealing by a mutation check (introduce a bad event name in the prompt, confirm the test catches it).

Commit discipline: Task 2 (the `LIFECYCLE_SESSION_ID` export move) ships as a separate commit from Tasks 1 and 3. Tasks 1, 3, and 4 may be combined or split as convenient, but the constant addition (Task 1) must precede the prompt edit (Task 3) if they are in separate commits, to avoid a window where the prompt references a constant that doesn't yet exist.
