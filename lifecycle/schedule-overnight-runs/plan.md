# Plan: schedule-overnight-runs

## Overview

Add one-shot overnight scheduling via a new `bin/overnight-schedule` bash script with a self-dispatching architecture: when invoked normally, it validates the target time, writes `scheduled_start` to state, and launches a detached tmux session that re-invokes itself with an internal `__launch` subcommand. The `__launch` path handles caffeinate, sleep, state-clear, and exec to `overnight-start`. This avoids embedding complex logic in a tmux command string. The `/overnight` skill gains a scheduling prompt at Step 8.7, and `OvernightState` gains a `scheduled_start` metadata field.

## Tasks

### Task 1: Add `scheduled_start` field to OvernightState dataclass
- **Files**: `claude/overnight/state.py`
- **What**: Add `scheduled_start: Optional[str] = None` field to the `OvernightState` dataclass and add `scheduled_start=raw.get("scheduled_start")` to the `load_state()` function's return statement.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `OvernightState` is defined at `claude/overnight/state.py:154`. The field goes after `integration_worktrees` (line 210). In `load_state()` (line 275), add `scheduled_start=raw.get("scheduled_start")` to the return statement at line 321. Follow the existing pattern used by `paused_reason`, `worktree_path`, and other Optional fields — all use `raw.get()` for backward compatibility.
- **Verification**: `python3 -c "from claude.overnight.state import OvernightState; s = OvernightState(); print(s.scheduled_start)"` — pass if output is `None`
- **Status**: [x] complete

### Task 2: Create `bin/overnight-schedule` — full script with self-dispatch architecture
- **Files**: `bin/overnight-schedule`
- **What**: Create the complete `bin/overnight-schedule` bash script with two code paths: (A) the **setup path** (default, no `__launch` arg) that parses target time, validates format, computes delay, writes `scheduled_start` to state, launches tmux, and prints confirmation; and (B) the **launch path** (`__launch` as first arg) that runs caffeinate + sleep, clears `scheduled_start` from state, and execs `overnight-start`.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  The script dispatches on `$1`:
  - If `$1` is `__launch`: enter the launch path (internal, called by tmux)
  - Otherwise: enter the setup path (user-facing)

  **Setup path** (`$1` is a time string):
  - `TARGET_TIME="$1"; shift; OVERNIGHT_ARGS=("$@")`
  - Validate `TARGET_TIME` format: regex `^[0-2][0-9]:[0-5][0-9]$` for HH:MM (with hours <= 23 check), or `^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-2][0-9]:[0-5][0-9]$` for ISO
  - Compute delay: for HH:MM, use `date -j -f "%H:%M" "$TARGET_TIME" +%s`; for ISO, replace T with space and use `date -j -f "%Y-%m-%d %H:%M"`. If target passed today (HH:MM only), add 86400. Validate delay > 0 and <= 604800.
  - Compute `TARGET_ISO`: full ISO 8601 timestamp of target time (for state file write)
  - Compute `TARGET_UTC`: UTC equivalent via `date -u -r $TARGET_EPOCH "+%H:%M UTC"`
  - If state path exists (`${OVERNIGHT_ARGS[0]}`), write `scheduled_start` atomically using Python: `python3 -c "import json,sys,tempfile,os; p=sys.argv[1]; d=json.load(open(p)); d['scheduled_start']=sys.argv[2]; fd,t=tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(p))); os.write(fd,(json.dumps(d,indent=2)+'\n').encode()); os.close(fd); os.replace(t,os.path.abspath(p))" "$STATE_PATH" "$TARGET_ISO"`
  - tmux session collision avoidance (pattern from `bin/overnight-start` lines 44-49): `SESSION="overnight-scheduled"; N=2; while tmux has-session ...`
  - Launch tmux: `tmux new-session -d -s "$SESSION" "$SELF __launch $DELAY_SECONDS $STATE_PATH $TARGET_ISO ${OVERNIGHT_ARGS[*]}"` where `SELF="$(realpath "${BASH_SOURCE[0]}")"`. Since tmux passes the string to sh, all args are simple scalars (integers, paths, ISO strings — no spaces in lifecycle paths by convention).
  - Print confirmation: scheduled time (local + UTC), countdown (Xh Ym), attach command, cancel command.

  **Launch path** (`$1` is `__launch`):
  - `shift; DELAY=$1; STATE_PATH=$2; TARGET_ISO=$3; shift 3; OVERNIGHT_ARGS=("$@")`
  - `caffeinate -i sleep "$DELAY"` — keeps Mac awake during sleep
  - Clear `scheduled_start` from state: same Python one-liner as setup path but with `d['scheduled_start']=None`
  - `exec overnight-start "${OVERNIGHT_ARGS[@]}"` — replaces process, proper exec semantics per spec Req 10

  Follow `bin/overnight-start` conventions: `#!/usr/bin/env bash`, `set -euo pipefail`, guard against `--flag` style args on the user-facing path.
- **Verification**: `bash bin/overnight-schedule` (no args) — pass if exits 1 with usage text; `bash bin/overnight-schedule 25:99` — pass if exits 1 with format error; `bash bin/overnight-schedule 2099-01-01T00:00` — pass if exits 1 with ">7 days" error
- **Status**: [x] complete

### Task 3: Make `bin/overnight-schedule` executable
- **Files**: `bin/overnight-schedule`
- **What**: Set the executable bit on the new script.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: All scripts in `bin/` must be executable. Run `chmod +x bin/overnight-schedule`.
- **Verification**: `test -x bin/overnight-schedule` — pass if exit code is 0
- **Status**: [x] complete

### Task 4: Add `overnight-schedule` to justfile `deploy-bin` pairs
- **Files**: `justfile`
- **What**: Add `"$(pwd)/bin/overnight-schedule|$HOME/.local/bin/overnight-schedule"` to the `pairs` array in the `deploy-bin` recipe, after the `overnight-status` entry.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The `pairs` array is at justfile line 130. The last current entry is `git-sync-rebase.sh` at line 139. Add the new entry after line 138 (`overnight-status`). The comment at line 129 says "also update setup-force when adding new targets here."
- **Verification**: `grep -c 'overnight-schedule' justfile` — pass if count >= 1
- **Status**: [x] complete

### Task 5: Add `overnight-schedule` to justfile `setup-force` recipe
- **Files**: `justfile`
- **What**: Add `ln -sf "$(pwd)/bin/overnight-schedule" ~/.local/bin/overnight-schedule` to the `setup-force` recipe, after the `overnight-start` entry.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The `setup-force` recipe starts at line 37. The `overnight-start` symlink is at line 54. Add the new line after line 54.
- **Verification**: `grep 'ln.*overnight-schedule' justfile` — pass if output is non-empty
- **Status**: [x] complete

### Task 6: Add `overnight-schedule` to justfile `check-symlinks` recipe
- **Files**: `justfile`
- **What**: Add `check ~/.local/bin/overnight-schedule` to the `check-symlinks` recipe, after the `overnight-start` entry.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The `overnight-start` check is at justfile line 791. Add `check ~/.local/bin/overnight-schedule` on the line after it.
- **Verification**: `grep 'check.*overnight-schedule' justfile` — pass if output is non-empty
- **Status**: [x] complete

### Task 7: Add `overnight-schedule` justfile recipe
- **Files**: `justfile`
- **What**: Add a `just overnight-schedule` recipe that accepts a target time and optional overnight-start args, then invokes `overnight-schedule` (the deployed binary) with those args.
- **Depends on**: [4, 5, 6]
- **Complexity**: simple
- **Context**: Follow the pattern of the `overnight-start` recipe at justfile line 610. The new recipe should be placed adjacent to it. Recipe signature: `overnight-schedule target-time state="" time-limit="6" max-rounds="10" tier="max_100":`. The body invokes: `overnight-schedule "{{ target-time }}" "{{ state }}" "{{ time-limit }}" "{{ max-rounds }}" "{{ tier }}"`.
- **Verification**: `just --list | grep -c overnight-schedule` — pass if count is 1
- **Status**: [x] complete

### Task 8: Update `/overnight` SKILL.md with scheduling prompt
- **Files**: `skills/overnight/SKILL.md`
- **What**: Modify Step 8, sub-step 7 ("Print the runner command"). After the current `overnight-start` command presentation, add a scheduling prompt: use AskUserQuestion to ask "Run now or schedule for later?" with options "Run now" and "Schedule for specific time." If "Run now," present the existing `overnight-start` command unchanged. If "Schedule," prompt for target time (HH:MM or YYYY-MM-DDTHH:MM), then present `overnight-schedule <target-time> <state-path> <time-limit>` instead. Add a note about the dormant usage context requirement (Req 2 from spec). Also update Success Criteria item 6 (line 300) to mention both `overnight-start` and `overnight-schedule` as valid runner commands.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Step 8, sub-step 7 is at approximately line 217 of `skills/overnight/SKILL.md`. The current command is: `overnight-start $CORTEX_COMMAND_ROOT/lifecycle/sessions/{session_id}/overnight-state.json 6h`. The modified sub-step adds a branch: if scheduling, present `overnight-schedule <target-time> $CORTEX_COMMAND_ROOT/lifecycle/sessions/{session_id}/overnight-state.json 6h` instead.
- **Verification**: `grep -c 'overnight-schedule' skills/overnight/SKILL.md` — pass if count >= 2 (command reference + scheduling prompt text)
- **Status**: [x] complete

### Task 9: Deploy, verify symlinks, and run tests
- **Files**: `bin/overnight-schedule`, `justfile`
- **What**: Run `just deploy-bin` to create the symlink. Run `just check-symlinks` to verify. Run `just test` to ensure no regressions.
- **Depends on**: [1, 2, 3, 4, 5, 6, 7, 8]
- **Complexity**: simple
- **Context**: `just deploy-bin` creates symlinks from `bin/` to `~/.local/bin/`. `just check-symlinks` validates all expected symlinks exist. `just test` runs the full test suite.
- **Verification**: `just check-symlinks 2>&1 | grep -c FAIL` — pass if count is 0 (no failures); `just test` — pass if exit code is 0
- **Status**: [x] complete

## Verification Strategy

End-to-end verification after all tasks:

1. **Symlink exists**: `ls -la ~/.local/bin/overnight-schedule` shows symlink to `bin/overnight-schedule`
2. **Usage output**: `overnight-schedule` (no args) prints usage and exits 1
3. **Validation**: `overnight-schedule 25:99` exits 1 with format error
4. **ISO format**: `overnight-schedule 2099-01-01T00:00` exits 1 with ">7 days" error
5. **State schema**: `python3 -c "from claude.overnight.state import OvernightState; print(OvernightState().scheduled_start)"` prints `None`
6. **Justfile recipe**: `just --list | grep overnight-schedule` shows the recipe
7. **Check-symlinks**: `just check-symlinks` passes with no failures for `overnight-schedule`
8. **Test suite**: `just test` passes
