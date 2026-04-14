# Plan: integrate-autonomous-worktree-option-into-lifecycle-pre-flight

## Overview

Add a "Implement in autonomous worktree" fourth pre-flight option to `implement.md §1 Branch Selection`, backed by a new `§1b Daytime Dispatch` alternate path that guards against double-dispatch and concurrent overnight runs, launches `python3 -m claude.overnight.daytime_pipeline` in the background, polls for completion, and surfaces results. Accompany the change with behavior tests covering all guard scenarios and a contract test for the CLI invocation shape.

## Tasks

### Task 1: Expand pre-flight branch selection to four options

- **Files**: `skills/lifecycle/references/implement.md`
- **What**: Update §1 Branch Selection from three to four options — insert "Implement in autonomous worktree" as the new option 2, add decision guidance text that distinguishes when to pick each option, add a worktree-branch guard, and wire the new option to §1b.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Current §1 text at `skills/lifecycle/references/implement.md` lines 11-21: "prompt the user via AskUserQuestion with three options" — must become "four options"
  - New option slot: insert between "Implement in worktree" and "Implement on main". Option 1 = worktree (existing), Option 2 = autonomous worktree (new), Option 3 = main (existing), Option 4 = feature branch (existing)
  - Decision guidance (Req 2): each option's description must include when-to-pick guidance. The guidance for autonomous worktree must use at least one of: "live-steer", "many-task", or "no-live" so that `grep -i "live.steer\|many.task\|no.live"` returns ≥ 1 match. Suggested framing per spec: "small/live-steerable → single-agent worktree; medium/many-task/no-live-steering-needed → autonomous worktree"
  - Worktree-branch guard (Req 6): immediately before the `AskUserQuestion` call, check whether `git branch --show-current` matches `^worktree/agent-`. If it does, exclude the "Implement in autonomous worktree" option from the list presented to the user and note "autonomous worktree unavailable from within a worktree agent context". This satisfies the acceptance criterion `grep -A5 "worktree.*agent\|agent.*worktree" implement.md` showing guard text.
  - Dispatch routing addition at `implement.md` lines 18-20 (current routing block): add one line — "If the user selects **Implement in autonomous worktree**, proceed to §1b (Daytime Dispatch alternate path below)"
- **Verification**:
  - `grep -c "autonomous worktree" skills/lifecycle/references/implement.md` — pass if count ≥ 1
  - `grep -i "live.steer\|many.task\|no.live" skills/lifecycle/references/implement.md` — pass if count ≥ 1
  - `grep -A5 "worktree.*agent\|agent.*worktree" skills/lifecycle/references/implement.md` — pass if output shows branch-prefix guard text
- **Status**: [x] complete

---

### Task 2: Add §1b Daytime Dispatch alternate path

- **Files**: `skills/lifecycle/references/implement.md`
- **What**: Insert `### 1b. Daytime Dispatch (Alternate Path)` immediately after the `### 1a. Worktree Dispatch (Alternate Path)` section and before `### 2. Task Dispatch`. The section describes: plan.md prerequisite check, double-dispatch guard, overnight concurrent guard, background subprocess launch, `implementation_dispatch` event, polling loop, result surfacing (4 ordered outcomes), and `dispatch_complete` event.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - **Section placement**: insert after `§1a` (ending at current line 103 `hooks/cortex-cleanup-session.sh`) and before `### 2. Task Dispatch` (current line 104)
  - **Plan.md prerequisite (Req 3)**: First action in §1b, before any guards. Check: `lifecycle/{feature}/plan.md` must exist. On failure: surface "plan.md not found — cannot launch autonomous worktree. Run /lifecycle plan first." and exit §1b. Do NOT proceed to guards or subprocess.
  - **Double-dispatch guard (Req 4)**: Two separate Bash calls:
    1. Read PID: `cat lifecycle/{feature}/daytime.pid 2>/dev/null`
    2. Liveness: `kill -0 $pid 2>/dev/null`. Exit 0 = alive → reject with "Autonomous daytime run already in progress (PID {pid}) — wait for it to complete or check events.log". Non-0 or empty file → proceed.
  - **Overnight concurrent guard (Req 5)**: Four separate Bash calls (sandbox rule: no compound commands):
    1. Read active session: `cat ~/.local/share/overnight-sessions/active-session.json 2>/dev/null` — if absent, proceed normally
    2. Parse `repo_path`, `phase`, `state_path` fields from JSON. If `repo_path != CWD` or `phase != "executing"`: proceed normally
    3. Derive session dir: parent directory of `state_path`. Read: `cat {session_dir}/.runner.lock 2>/dev/null` — extract runner PID
    4. Check liveness: `kill -0 $runner_pid 2>/dev/null`. Alive → reject with "Overnight runner is active (PID {pid}) — wait for it to complete before launching a daytime run." Dead → emit warning "overnight state shows executing but no live runner found — may be stale; proceeding" and continue.
    - `state_path` is the full path to the session's state JSON file (e.g. `lifecycle/sessions/{id}/overnight-state.json`); the session dir is the containing directory (`Path(state_path).parent`). This matches the `bin/overnight-status` detection pattern.
  - **Background subprocess launch (Req 7)**: Single Bash call with `run_in_background=true`. Command: `python3 -m claude.overnight.daytime_pipeline --feature {slug} > lifecycle/{feature}/daytime.log 2>&1`. Subprocess writes `lifecycle/{feature}/daytime.pid` at its own startup. The skill does not write the PID — it only reads it.
  - **`implementation_dispatch` event (Req 8)**: Immediately after background launch, separate Bash call appends to `lifecycle/{feature}/events.log`:
    ```json
    {"ts": "<ISO 8601>", "event": "implementation_dispatch", "feature": "<name>", "mode": "daytime"}
    ```
  - **Polling loop (Req 9)**: Sequential Bash calls, no compound commands:
    - Initial wait: `sleep 10` Bash call with `timeout: 15000` (15 seconds — ample margin over the sleep duration; follows a background launch so it is not a blocking subprocess wait)
    - After initial wait: read PID file with `cat lifecycle/{feature}/daytime.pid 2>/dev/null`. If file absent: startup failure — go to result surfacing immediately using `daytime.log` content
    - Per-iteration: (a) `kill -0 $pid 2>/dev/null` — non-0 exit = process exited, go to result surfacing; (b) `tail -n 5 lifecycle/{feature}/events.log` — surface brief summary of most recent 5 events (capped to limit context accumulation; not 20); (c) `sleep 120` Bash call with `timeout: 130000` (130 seconds — ample margin over the sleep duration)
    - Termination bound: 120 iterations (~4 hours). Context window exhaustion — not iteration count — is the practical binding constraint for long runs. At 30 iterations (~1 hour), pause and offer the user the option to suspend polling: "Subprocess still running after 30 iterations (~1 hour). Continue polling or stop? (The process continues in background — monitor `lifecycle/{feature}/daytime.log` and `events.log` directly.)" If the user stops, exit the polling loop. On reaching 120 iterations without exit: "Polling timeout — subprocess may still be running (PID {pid}). Check `lifecycle/{feature}/daytime.log` directly for status." Exit polling loop.
  - **Result surfacing (Req 10)**: Read last non-empty line of `lifecycle/{feature}/daytime.log` beginning with `"Feature "`. Apply first-match-wins in this exact order:
    1. Contains `"merged successfully"` → success: display the line; scan full daytime.log for a GitHub PR URL (pattern `https://github.com/[^/]+/[^/]+/pull/[0-9]+`) and display it if found
    2. Contains `"deferred"` → deferred: display the line; read most recent file in `lifecycle/{feature}/deferred/` by modification time and display its content; if multiple files exist, note the count
    3. Contains `"paused"` → paused: display the line; instruct user to check `events.log` for details and re-run when ready
    4. No `"Feature "` line found, or line matches none of the above → failed: display last 20 lines of `daytime.log`; instruct user to check `lifecycle/{feature}/daytime.log` for full details
    - Note: this ordered detection is intentional — a failure message containing "paused" as a substring (e.g. `"Feature X failed: subprocess paused unexpectedly"`) still classifies as failed because "merged successfully" and "deferred" are checked first, and "paused" would only match at step 3, which is reached only if steps 1 and 2 did not match. The ordering ensures substring accidents do not misclassify.
  - **`dispatch_complete` event (Req 11)**: After result surfacing, separate Bash call appends to `lifecycle/{feature}/events.log`:
    ```json
    {"ts": "<ISO 8601>", "event": "dispatch_complete", "feature": "<name>", "mode": "daytime", "outcome": "complete|deferred|paused|failed", "pr_url": "<url>|null"}
    ```
    `outcome` maps: "merged successfully" → `"complete"`, "deferred" → `"deferred"`, "paused" → `"paused"`, other/no-match → `"failed"`. `pr_url` = the PR URL string if found, JSON literal `null` otherwise.
  - **No `.dispatching` mechanism**: per spec Non-Requirements, the existing noclobber `$$` is unsuitable for daytime (PID `$$` dies milliseconds after the Bash call). Do not use `.dispatching` in §1b. The `daytime.pid` guard is sufficient.
- **Verification**:
  - `grep -c "1b\|Daytime Dispatch" skills/lifecycle/references/implement.md` — pass if count ≥ 2
  - `grep '"mode": "daytime"' skills/lifecycle/references/implement.md` — pass if count ≥ 2 (implementation_dispatch and dispatch_complete)
  - `grep 'implementation_dispatch' skills/lifecycle/references/implement.md` — pass if count ≥ 1
  - `grep 'dispatch_complete' skills/lifecycle/references/implement.md` — pass if count ≥ 1 (the daytime mode one; §1a already has the worktree mode one)
- **Status**: [x] complete

---

### Task 3: Write behavior and integration tests

- **Files**: `tests/test_daytime_preflight.py` (new)
- **What**: Add eight tests covering all guard scenarios from Req 12 and the CLI invocation contract from Req 13. Use the same pytest style as existing `tests/test_lifecycle_state.py` and `tests/test_runner_signal.py`.
- **Depends on**: [1, 2]
- **Complexity**: complex
- **Context**:
  - Test style: standard pytest, `Path` + `tmp_path` fixtures, no subprocess mocking frameworks — create real temp files and (where possible) real processes. Reference `tests/test_runner_signal.py` for subprocess + signal patterns; `tests/test_skill_contracts.py` for document content assertion patterns. Run `just test` before and after to verify no regressions.
  - The file must satisfy: `grep -r "daytime_preflight\|autonomous_worktree\|daytime.*guard\|daytime.*pid" tests/` → finds `tests/test_daytime_preflight.py`. Use at least one of those terms in a function or variable name in the file.
  - The file must also satisfy: `grep -r "daytime_pipeline.*feature\|feature.*daytime_pipeline" tests/` → finds this file. Include the invocation string `python3 -m claude.overnight.daytime_pipeline --feature` in the contract test.
  - Required tests (implement as pure Python guard-logic tests or document contract tests):

  **Guard tests** — implement the guard logic described in spec §1b as Python helper functions and test their behavior:

  1. `test_double_dispatch_guard_live_pid` (daytime.pid guard): create `daytime.pid` containing `os.getpid()` (current process — guaranteed alive); run guard logic; assert rejection message contains "already in progress"
  2. `test_overnight_guard_live_runner` (overnight guard): create `active-session.json` with `repo_path=CWD`, `phase="executing"`, `state_path` set to `str(tmp_session_dir / "overnight-state.json")` (use `overnight-state.json` as the filename — the actual runtime value); create `.runner.lock` in `tmp_session_dir` containing `os.getpid()` (alive). Before calling the guard helper, assert independently that `Path(state_path).parent == tmp_session_dir` (validates the `.parent` derivation step). Then run guard logic; assert rejection contains "Overnight runner is active"
  3. `test_double_dispatch_guard_stale_pid` (stale PID): find a PID guaranteed to be dead — start a subprocess, capture its PID, wait for it to exit, use that PID; create `daytime.pid` with the dead PID; run guard logic; assert guard does NOT fire (no rejection, guard returns "proceed")
  4. `test_overnight_guard_different_repo` (repo path mismatch): create `active-session.json` with `repo_path="/some/other/repo"`, `phase="executing"`, live `.runner.lock`; run guard logic; assert guard does NOT fire
  5. `test_overnight_guard_no_session_file` (absent session file): ensure `active-session.json` does not exist in temp home; run guard logic; assert guard does NOT fire
  6. `test_polling_fallback_startup_failure` (no daytime.pid appears): simulate the polling initial-wait logic with `daytime.pid` absent after wait; assert the fallback path reads `daytime.log` for result detection rather than blocking on PID
  7. `test_outcome_detection_paused_substring_in_failure`: feed a `daytime.log` whose last `"Feature "` line is `"Feature X failed: subprocess paused unexpectedly"`; run result-surfacing logic; assert outcome is `"failed"`, not `"paused"`

  **Contract test** — read `implement.md` and assert document content:

  8. `test_skill_contracts`: read `skills/lifecycle/references/implement.md` and locate the §1b section (text between `### 1b.` and the next `### ` heading). Assert all of: (a) invocation string `python3 -m claude.overnight.daytime_pipeline --feature` is present; (b) no extra flags on the same invocation line (`--tier`, `--criticality`, `--base-branch`, `--test-command` absent from that line); (c) "plan.md" text appears before the first `daytime.pid` reference in §1b (guard ordering: plan.md check → daytime.pid → overnight); (d) `"mode": "daytime"` appears at least twice in §1b (implementation_dispatch and dispatch_complete events); (e) `"merged successfully"` appears before `"deferred"` and `"deferred"` appears before `"paused"` in §1b (first-match-wins outcome detection ordering is preserved)

  - `REPO_ROOT = Path(__file__).resolve().parent.parent` — use this pattern for all file paths
  - For overnight guard tests: mock the `active-session.json` path. The real path is `~/.local/share/overnight-sessions/active-session.json` (global). Factor the guard logic into a testable helper `_check_overnight_guard(session_file: Path, cwd: Path) -> tuple[bool, str]` that accepts the session file path as a parameter (so tests can pass a tmp_path version). Document that the §1b implementation reads the real global path when `session_file` is not overridden.
- **Verification**:
  - `just test` — pass if exits 0
  - `grep -r "daytime_preflight\|autonomous_worktree\|daytime.*guard\|daytime.*pid" tests/` — pass if shows `tests/test_daytime_preflight.py`
  - `grep -r "daytime_pipeline.*feature\|feature.*daytime_pipeline" tests/` — pass if shows `tests/test_daytime_preflight.py`
- **Status**: [x] complete

---

## Verification Strategy

After all tasks complete, run these checks in order:

1. `grep -c "autonomous worktree" skills/lifecycle/references/implement.md` — pass if ≥ 1 (Req 1)
2. `grep -c "AskUserQuestion" skills/lifecycle/references/implement.md` — pass if ≥ 1 (Req 1, existing check)
3. `grep -i "live.steer\|many.task\|no.live" skills/lifecycle/references/implement.md` — pass if ≥ 1 (Req 2)
4. `grep -A5 "worktree.*agent\|agent.*worktree" skills/lifecycle/references/implement.md` — pass if output shows worktree-branch guard text (Req 6)
5. `grep '"mode": "daytime"' skills/lifecycle/references/implement.md` — pass if count ≥ 2 (Req 8 + Req 11)
6. `just test` — pass if exits 0 (Req 12 + Req 13)
7. `grep -r "daytime_preflight\|autonomous_worktree\|daytime.*guard\|daytime.*pid" tests/` — pass if finds test file (Req 12)
8. `grep -r "daytime_pipeline.*feature\|feature.*daytime_pipeline" tests/` — pass if finds test file (Req 13)

Interactive-only verifications (require a real daytime session):
- Selecting "autonomous worktree" when `daytime.pid` is live produces the rejection message (Req 4)
- Outcome detection shows distinct output per path (Req 10)
- `implementation_dispatch` and `dispatch_complete` events appear in events.log (Req 8, 11)

## Veto Surface

- **Worktree-branch guard placement**: Excluding the autonomous option from the list (simpler) vs. showing it with immediate rejection after selection (more visible). Plan chooses exclusion from list — simpler implementation, same safety guarantee.
- **Test approach for guards**: Pure Python helper functions implementing the guard logic (allows isolated unit testing) vs. shell scripts that simulate the skill's actual Bash sequence. Plan chooses Python helpers — consistent with existing test style and avoids subprocess overhead for simple PID-file checks.
- **Session file path for overnight guard tests**: Real global `~/.local/share/overnight-sessions/active-session.json` cannot be used in tests. Plan injects the path as a parameter to a testable helper, with the §1b prose reading the real global path in production. If the project prefers full integration tests, Task 3 can be replaced with subprocess-based tests using HOME overrides (as in `test_runner_signal.py`).

## Scope Boundaries

- No changes to `claude/overnight/daytime_pipeline.py`, `orchestrator.py`, `feature_executor.py`, or `outcome_router.py`
- No changes to `skills/lifecycle/SKILL.md` — daytime.pid guard stays in §1b only, not Step 2
- No `worktree/daytime-*` branch prefix — daytime uses `pipeline/{feature}` naming (fixed by #078)
- No fix for `cleanup_worktree()` `-2` suffix bug — deferred per Non-Requirements
- No interactive merge approval, resume/re-entry for paused runs, or atomic OS-level locking
- No changes to morning report or overnight session orchestration
