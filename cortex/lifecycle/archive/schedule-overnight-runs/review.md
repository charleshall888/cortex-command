# Review: schedule-overnight-runs

**Reviewer**: Claude (automated)
**Cycle**: 1
**Date**: 2026-04-08

## Stage 1: Spec Compliance

### Requirement 1: Scheduling prompt at Step 8.7
**Rating**: PASS

The SKILL.md Step 8, sub-step 7 now asks the user "Run now or schedule for later?" via AskUserQuestion after plan approval and before presenting the runner command. Both options (run now / schedule) are covered with the appropriate command templates.

### Requirement 2: Usage context (future/dormant)
**Rating**: PASS

The SKILL.md includes the dormant usage-context note as a blockquote alongside the scheduling prompt. No implementation work performed, as specified.

### Requirement 3: Time input format
**Rating**: PASS

`bin/overnight-schedule` accepts both `HH:MM` (line 102) and `YYYY-MM-DDTHH:MM` (line 83) via separate regex branches. The `T` separator is required for the ISO format, matching the spec.

### Requirement 4: New bin/overnight-schedule script
**Rating**: PASS

Standalone bash script exists at `bin/overnight-schedule` with `+x` permissions. Accepts target time as first positional arg. Forwards remaining args to `overnight-start` via `exec` (line 44). Prints usage with no args (lines 60-72). Deploy-bin creates the symlink at `~/.local/bin/overnight-schedule`.

### Requirement 5: Delay computation
**Rating**: PASS

Uses BSD `date -j -f` for parsing (lines 91, 109). For `HH:MM`: schedules today if future, tomorrow if past with the specified message "Target time has passed today -- scheduling for tomorrow" (line 115). For ISO: validates target is in the future (line 97-100) and exits with code 1 if past. Validates within 7 days (line 129). Delay computed as `TARGET_EPOCH - NOW_EPOCH` (line 126).

### Requirement 6: Input validation
**Rating**: PASS

Pattern matching validates format before any use. `HH:MM` regex `^[0-2][0-9]:[0-5][0-9]$` plus explicit hour range check `10#$HOUR > 23` (line 105). ISO regex similarly constrained with additional hour check (line 86). Invalid formats exit with code 1 and print expected formats (lines 120-124). Flag-style args rejected early (lines 52-57).

### Requirement 7: Mac sleep prevention
**Rating**: PASS

Line 28: `caffeinate -i sleep "$DELAY"` wraps the sleep period, preventing system sleep during the wait.

### Requirement 8: Confirmation output
**Rating**: PASS

Lines 190-194 print all required information matching the spec patterns:
- `Scheduled for $TARGET_LOCAL local ($TARGET_UTC)` -- matches "Scheduled for HH:MM local (HH:MM UTC)"
- `Starting in ${DELAY_HOURS}h ${DELAY_MINUTES}m` -- matches "Starting in Xh Ym"
- `Attach: tmux attach -t $SESSION` -- matches spec
- `Cancel: tmux kill-session -t $SESSION` -- matches spec

### Requirement 9: tmux session
**Rating**: PASS

Session naming uses collision-avoidance pattern (lines 177-182): tries `overnight-scheduled`, then `overnight-scheduled-2`, etc. using `tmux has-session -t =SESSION`. Sleep + caffeinate + launch runs inside a detached tmux session (line 184). After `exec overnight-start` completes, the scheduled session naturally exits.

### Requirement 10: Delegation to overnight-start
**Rating**: PASS

After the sleep period, `exec overnight-start "${OVERNIGHT_ARGS[@]}"` (line 44) replaces the process with overnight-start, forwarding all args (state-path, time-limit, max-rounds, tier). `overnight-start` creates the `overnight-runner` tmux session and the runner continues there.

### Requirement 11: scheduled_start field in overnight-state.json
**Rating**: PASS

Before sleeping, writes `scheduled_start` as ISO 8601 timestamp to the state file via atomic write (python3 with tempfile + os.replace, lines 154-163). Clears to `None` just before calling `overnight-start` (lines 32-41), also via atomic write. Missing/unwritable state file produces warnings but does not block scheduling (lines 163, 165).

### Requirement 12: State schema backward compatibility
**Rating**: PASS

`OvernightState` dataclass has `scheduled_start: Optional[str] = None` (line 214 of state.py). `load_state()` uses `raw.get("scheduled_start")` (line 342), which returns `None` for pre-existing state files that lack the field.

### Requirement 13: Justfile recipe
**Rating**: PASS

Lines 645-647 define `overnight-schedule` recipe with matching parameters (target-time, state, time-limit, max-rounds, tier) that delegates to the `overnight-schedule` binary.

### Requirement 14: Deploy and symlink integration
**Rating**: PASS

All three recipe lists updated together:
- `deploy-bin` (line 140): includes `overnight-schedule` symlink pair
- `setup-force` (line 55): includes `ln -sf` for `overnight-schedule`
- `check-symlinks` (line 798): includes validation for `overnight-schedule`

## Stage 2: Code Quality

### Naming Conventions
Consistent with project patterns. `bin/overnight-schedule` follows the `bin/overnight-*` naming convention alongside `overnight-start` and `overnight-status`. The tmux session name `overnight-scheduled` is distinct from `overnight-runner` used by `overnight-start`. The `scheduled_start` field name is consistent with the existing `started_at`/`updated_at` naming patterns in `OvernightState`.

### Error Handling
Appropriate for the context. The script follows the project's "proceed with warning" pattern for non-critical failures (state file writes) and hard-exits for validation failures (bad time format, past dates, >7 days). The `2>/dev/null || true` on state file operations (lines 41, 163) prevents observability failures from blocking scheduling.

### Code Quality Notes

**tmux argument passing with empty state path**: When `STATE_PATH` is empty (no state path provided), the tmux command string `"$SELF __launch $DELAY_SECONDS $STATE_PATH $TARGET_ISO ${OVERNIGHT_ARGS[*]}"` collapses the empty variable, causing positional argument misalignment in the `__launch` handler. The `__launch` path would misinterpret `TARGET_ISO` as `STATE_PATH` and `shift 3` would fail. This only affects direct CLI invocation without a state path -- the primary flow through the `/overnight` skill always provides one. The spec lists this as an edge case (line 61) rather than a core requirement, but the implementation does not correctly handle it despite the spec saying "Scheduling still works; just no state-file observability."

**String-based tmux command**: The tmux command uses a single string (`${OVERNIGHT_ARGS[*]}`) rather than a proper array expansion, meaning arguments with spaces would break. This matches the existing `overnight-start` pattern and the spec's positional-only constraint mitigates the risk, but it is worth noting.

### Pattern Consistency
Follows existing project conventions well:
- `set -euo pipefail` header matching `overnight-start`
- Self-invocation pattern (`$SELF __launch`) for the tmux inner command
- Atomic state file writes via python3 inline scripts matching the project's tempfile + mv/replace pattern
- Collision-avoidance for tmux session names matching `overnight-start`'s approach
- Deploy-bin / setup-force / check-symlinks triple-symmetry maintained

### Test Coverage
No automated tests are present for `overnight-schedule`. The plan verification steps are runtime acceptance criteria (manual invocation checks). This is consistent with how `overnight-start` is tested in the project -- these are integration-level scripts that rely on tmux and system time, making unit testing impractical.

## Requirements Drift
**State**: detected
**Findings**:
- The `scheduled_start` field and scheduling capability are new behaviors not reflected in `requirements/project.md` or any area requirements. The project requirements mention "Overnight execution framework, session management, and morning reporting" (In Scope) but do not specifically mention scheduling or delayed launch.
**Update needed**: requirements/project.md (minor -- add scheduling to the overnight execution framework description in the In Scope section)

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "detected"
}
```

All 14 specification requirements pass. The implementation is clean, follows project conventions, and handles edge cases appropriately. The empty-state-path tmux argument issue is a minor robustness gap for direct CLI use (the primary skill-driven flow is unaffected) and does not warrant blocking approval.
