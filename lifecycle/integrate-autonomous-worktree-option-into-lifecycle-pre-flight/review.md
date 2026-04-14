# Review: integrate-autonomous-worktree-option-into-lifecycle-pre-flight

## Stage 1: Spec Compliance

### Requirement 1: Four pre-flight options via AskUserQuestion
- **Expected**: §1 presents four options — worktree / autonomous worktree / main / feature branch — via AskUserQuestion.
- **Actual**: `implement.md` lines 11–16 enumerate the four options; AskUserQuestion is referenced on line 11. Dispatch routing on lines 20–24 covers all four selections.
- **Verdict**: PASS

### Requirement 2: Option guidance text
- **Expected**: Pre-flight prompt includes decision guidance distinguishing when to pick each option (live-steerable, many-task, no-live-steering-needed, trunk-based, PR-flow).
- **Actual**: Lines 13–16 include "live-steerable", "medium/many-task/no-live-steering-needed", "trunk-safe", and "PR-based flow" guidance for each option.
- **Verdict**: PASS

### Requirement 3: plan.md prerequisite check
- **Expected**: Before any guards/subprocess, verify `lifecycle/{feature}/plan.md` exists; on missing, surface error mentioning "plan.md" and do not proceed.
- **Actual**: §1b.i (line 114) specifies the plan.md check before any guards with the exact error message "plan.md not found — cannot launch autonomous worktree. Run /lifecycle plan first." and explicit instruction not to proceed.
- **Verdict**: PASS

### Requirement 4: Double-dispatch guard
- **Expected**: Check `daytime.pid`, verify liveness via `kill -0`, reject with documented message if alive.
- **Actual**: §1b.ii (lines 116–121) specifies the two separate Bash calls, liveness check, and the exact rejection message "Autonomous daytime run already in progress (PID {pid}) — wait for it to complete or check events.log".
- **Verdict**: PASS

### Requirement 5: Concurrent overnight guard
- **Expected**: Read active-session.json, match repo_path + phase==executing, derive session_dir from state_path.parent, check .runner.lock PID liveness.
- **Actual**: §1b.iii (lines 123–128) specifies the four separate Bash calls, using `Path(state_path).parent`, reading .runner.lock, and the exact rejection message. Stale-runner handling documented (emit warning and continue) matches the spec's edge-case guidance.
- **Verdict**: PASS

### Requirement 6: Worktree-branch guard
- **Expected**: If current branch matches `^worktree/agent-`, the daytime option must not be available (or selecting it must reject).
- **Actual**: `implement.md` line 18 specifies a "Worktree-agent context guard" that excludes the autonomous worktree option from the AskUserQuestion list when the branch matches `^worktree/agent-`, with a note explaining why.
- **Verdict**: PASS

### Requirement 7: Background subprocess launch
- **Expected**: Launch `python3 -m claude.overnight.daytime_pipeline --feature {slug}` in background with stdout/stderr redirected to `lifecycle/{feature}/daytime.log`, via Bash run_in_background=true.
- **Actual**: §1b.iv (lines 130–135) specifies the exact command with redirect `> lifecycle/{feature}/daytime.log 2>&1` and `run_in_background: true`.
- **Verdict**: PASS

### Requirement 8: implementation_dispatch event with mode: daytime
- **Expected**: After launch, append JSON event with `"mode": "daytime"` to events.log.
- **Actual**: §1b.v (lines 138–142) specifies the event with the correct shape and `"mode": "daytime"`.
- **Verdict**: PASS

### Requirement 9: Progress polling
- **Expected**: Initial ~10s wait, PID acquisition, liveness check, events.log tail, ~2-min cadence, 120-iteration bound.
- **Actual**: §1b.vi (lines 144–155) specifies `sleep 10` initial wait, PID cat, `kill -0` liveness, `tail -n 5` events tail (capped at 5 rather than 20 — spec says "~20" or "last ~20 events" but §1b.vi text explicitly argues 5 instead to limit context accumulation). Cadence is `sleep 120` between iterations; 120-iteration bound specified with timeout message matching spec. Additional 30-iteration checkpoint documented (extra feature).
- **Verdict**: PASS — the "~20" in the spec is a soft number ("brief human-readable summary"); reducing to 5 with a documented rationale is within spec intent. Termination bound and cadence match.

### Requirement 10: Result surfacing
- **Expected**: Read last non-empty "Feature " line; first-match-wins: merged successfully → success (show PR URL), deferred → deferred (show deferred file), paused → paused, otherwise → failed (last 20 lines of log).
- **Actual**: §1b.vii (lines 157–164) specifies exactly this ordered detection with a rationale paragraph explaining why substring accidents don't misclassify. PR URL regex pattern provided. Deferred file-display rule included (most recent by mtime, note count if multiple).
- **Verdict**: PASS

### Requirement 11: dispatch_complete event
- **Expected**: After result surfacing, append event with `mode: daytime`, outcome mapping (complete/deferred/paused/failed), pr_url or null.
- **Actual**: §1b.viii (lines 166–172) specifies the event with correct outcome mapping and pr_url (string or JSON literal null).
- **Verdict**: PASS

### Requirement 12: Skill-level behavior tests
- **Expected**: Tests for live PID guard, overnight guard live runner, stale PID no-fire, different-repo no-fire, no-session-file no-fire, polling fallback on missing PID, outcome-detection substring safety.
- **Actual**: `tests/test_daytime_preflight.py` contains seven matching tests plus a contract test. All tests pass (`python3 -m pytest tests/test_daytime_preflight.py` → 8 passed; `just test` → 3/3 suites passed).
- **Verdict**: PASS

### Requirement 13: Integration test for CLI invocation
- **Expected**: Test verifies skill invokes `python3 -m claude.overnight.daytime_pipeline --feature {slug}` with no extra flags beyond `--feature`.
- **Actual**: `test_skill_contracts` (lines 315–403) checks invocation string presence AND absence of `--tier`, `--criticality`, `--base-branch`, `--test-command` on that line; grep pattern from spec acceptance matches.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Helper functions in `test_daytime_preflight.py` use leading-underscore convention for module-private helpers; test names use the `test_<behavior>_<condition>` pattern consistent with the repo's existing test files. `daytime.pid`, `daytime.log`, `events.log`, `implementation_dispatch`, `dispatch_complete` match the spec vocabulary and §1a precedent.
- **Error handling**: The guard helpers defensively handle missing files, empty content, malformed JSON, non-integer PIDs, and `ProcessLookupError`/`PermissionError` in `os.kill`. Spec edge cases (stale PID, missing session file, malformed session file, repo mismatch, stale overnight lock) are all covered. The implement.md prose specifies exact rejection messages and fallback behaviors matching the spec.
- **Test coverage**: Seven unit tests cover Req 12 cases (double-dispatch live/stale, overnight live/different-repo/no-file, polling fallback, outcome substring). One contract test covers Req 13 and additionally guards doc invariants (invocation string, plan.md→daytime.pid ordering, two `"mode": "daytime"` occurrences, merged→deferred→paused ordering in §vii). Tests pass under `just test`.
- **Pattern consistency**: §1b mirrors §1a's structure (i–ix numbered steps, event-logging shape, "Exit /lifecycle entirely" closing), keeping the two alternate dispatch paths visually parallel. Bash-call-per-step guidance honors the `claude/rules/sandbox-behaviors.md` "no compound commands" rule — explicit in the prose. PR-URL regex and deferred-file handling follow existing conventions in the skill library.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
