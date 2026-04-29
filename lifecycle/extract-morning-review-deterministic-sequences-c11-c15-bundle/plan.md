# Plan: extract-morning-review-deterministic-sequences-c11-c15-bundle

## Overview

Extract the C11 session-completion sequence into a Python module + bash shim that routes through `cortex_command.overnight.state.transition()` (closing the schema-bypass gap), and extract the C12 demo-worktree GC sweep into a narrow bash leaf script with an uncommitted-state precondition. Both scripts are wired into `skills/morning-review/SKILL.md` Step 0 in place of the inline `jq`/regex prose, with pytest fixture-replay coverage and dual-source plugin mirroring.

## Tasks

### Task 1: Create C11 Python module
- **Files**: `cortex_command/overnight/complete_morning_review_session.py`
- **What**: Implement the C11 helper as a runnable module (`python3 -m cortex_command.overnight.complete_morning_review_session`) that reads `<state_path>` (positional) and `--pointer <pointer_path>` (optional flag), validates via the canonical state-machine API, transitions `executing → complete`, persists, and optionally unlinks the pointer file.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Package home: `cortex_command/overnight/` (sibling of `state.py`, `ipc.py`). `cortex_command/overnight/__init__.py` already exists; no package wiring needed.
  - State-machine API surface (verified at spec time per `cortex_command/overnight/state.py`):
    - `from cortex_command.overnight.state import load_state, save_state, transition` — all three are module-level functions.
    - `load_state(state_path: Path) -> OvernightState` (state.py:334). Read path: opens the file via `state_path.read_text(...)`, parses via `json.loads`, then dict-indexes six required raw-JSON keys (`session_id`, `plan_ref`, `current_round`, `phase`, `started_at`, `updated_at`) at state.py:380–399 before constructing `OvernightState`. Raises (a) `FileNotFoundError` if the file does not exist; (b) `json.JSONDecodeError` (a `ValueError` subclass) on unparseable JSON; (c) `KeyError` on a missing required key; (d) `ValueError` from `OvernightState.__post_init__` (state.py:272) when all six keys are present but `phase` is not in `PHASES`.
    - `save_state(state, path: Path) -> None` (state.py:404). Already uses `os.replace()` per pipeline.md:134. May raise `OSError`/`PermissionError` on read-only filesystem, disk full, or permission-denied target.
    - `transition(state: OvernightState, new_phase: str) -> OvernightState` (state.py:543). Raises `ValueError` on invalid `new_phase` (line 561) or invalid forward edge (line 595). Forward grammar `_FORWARD_TRANSITIONS = {"planning": {"executing"}, "executing": {"complete"}}` — only `executing → complete` is a valid edge to `complete`.
  - CLI shape (entry point: `def main(argv: list[str] | None = None) -> int`, then `if __name__ == "__main__": sys.exit(main())`):
    - Positional: `state_path` (Path).
    - Optional: `--pointer <pointer_path>` (Path).
  - Behavior matrix (must match spec §Edge Cases for C11):
    1. **Missing state file** — guard upfront via `if not state_path.exists(): return 0`. Exit 0 silently. No `load_state` call. No pointer touched (the `--pointer` flag's stale-pointer-cleanup-on-missing-state is intentionally out of scope; subsequent runs silent-skip).
    2. **State file exists but unparseable / structurally invalid / malformed phase** — single catch block: `try: state = load_state(state_path) except (json.JSONDecodeError, KeyError, ValueError) as e:` → write `[complete-morning-review-session] error loading {state_path}: {e}` to stderr, exit non-zero. The catch covers all four loud-failure subclasses: `JSONDecodeError` (corrupt JSON), `KeyError` (missing required raw key), `ValueError` (the unified subclass for both phase-not-in-PHASES from `__post_init__` AND `transition` grammar errors). Exception's `str(e)` includes the offending value (the `__post_init__` message format is `f"Invalid phase {self.phase!r}; must be one of {PHASES}"`), satisfying spec R6 case (f) "stderr names the invalid phase".
    3. **State loaded, `state.phase == "executing"`** — call `transition(state, "complete")`, then `save_state(state, state_path)`, then if `--pointer` was supplied call `Path(pointer_path).unlink(missing_ok=True)`. Exit 0.
    4. **State loaded, `state.phase` ∈ {`"complete"`, `"paused"`, `"planning"`}** — exit 0 silently. Do NOT call `transition()` (would `ValueError` per the forward grammar above). Do NOT touch the pointer.
    5. **`save_state` raises `OSError`/`PermissionError`** — catch in case 3 specifically (`except OSError as e:`), write `[complete-morning-review-session] error writing {state_path}: {e}` to stderr, exit non-zero. Do NOT unlink the pointer (the pointer-unlink rule is gated on `save_state` returning normally).
  - The pointer unlink is only attempted when `--pointer` is supplied AND `save_state` returned normally (i.e., only on the case-3 success path).
  - Required imports: `argparse`, `sys`, `json` (for `json.JSONDecodeError`), `pathlib.Path`, plus `from cortex_command.overnight.state import load_state, save_state, transition`. `FileNotFoundError`, `KeyError`, `ValueError`, `OSError` are builtins. No re-implementing of state I/O.
- **Verification**: `cd /Users/charlie.hall/Workspaces/cortex-command && python3 -c "from cortex_command.overnight.complete_morning_review_session import main; raise SystemExit(0 if callable(main) else 1)"` — pass if exit 0.
- **Status**: [ ] pending

### Task 2: Create C11 bash shim
- **Files**: `bin/cortex-morning-review-complete-session`
- **What**: Bash shim that dispatches to the Task 1 Python module via the three-branch fallback pattern from `bin/cortex-update-item`. Forwards all arguments unchanged; exits 2 with a guidance message if neither dispatch path works.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Pattern reference: `bin/cortex-update-item` (lines 1–17). Mirror its layout exactly.
  - Required structural lines (in order):
    1. `#!/bin/bash`
    2. `"$(dirname "$0")/cortex-log-invocation" "$0" "$@" || true` (DR-7 telemetry shim — first non-comment line; this is the canonical convention validated by the parity linter and cited in the spec acceptance for R1).
    3. `set -euo pipefail`
  - Three-branch dispatcher:
    - **Branch (a) — packaged form**: `python3 -c "import cortex_command.overnight.complete_morning_review_session" 2>/dev/null` → on success `exec python3 -m cortex_command.overnight.complete_morning_review_session "$@"`.
    - **Branch (b) — `CORTEX_COMMAND_ROOT` checkout**: if `[ -n "${CORTEX_COMMAND_ROOT:-}" ]` AND `grep -q '^name = "cortex-command"' "$CORTEX_COMMAND_ROOT/pyproject.toml" 2>/dev/null` (sanity guard parity with `cortex-update-item` line 11 — refuses a misconfigured `CORTEX_COMMAND_ROOT` pointing at an unrelated checkout) AND the file exists at `$CORTEX_COMMAND_ROOT/cortex_command/overnight/complete_morning_review_session.py`, `exec env PYTHONPATH="$CORTEX_COMMAND_ROOT:${PYTHONPATH:-}" python3 -m cortex_command.overnight.complete_morning_review_session "$@"`. (Differs from `cortex-update-item` branch (b) by using `-m` plus `PYTHONPATH` because the helper imports the `cortex_command.overnight.state` package — running the file directly would not satisfy package imports.)
    - **Branch (c) — not found**: stderr message naming the helper plus the install fix `install cortex-interactive plugin or set CORTEX_COMMAND_ROOT`, then `exit 2`.
  - File mode: `chmod +x` (the dual-source pre-commit hook checks executability for canonical `bin/cortex-*`).
- **Verification**: `cd /Users/charlie.hall/Workspaces/cortex-command && test -x bin/cortex-morning-review-complete-session && [ "$(head -3 bin/cortex-morning-review-complete-session | grep -c 'cortex-log-invocation')" -ge 1 ] && [ "$(grep -c 'python3 -m cortex_command\.overnight\.complete_morning_review_session' bin/cortex-morning-review-complete-session)" -ge 1 ] && [ "$(grep -c 'CORTEX_COMMAND_ROOT' bin/cortex-morning-review-complete-session)" -ge 1 ]` — pass if exit 0.
- **Status**: [ ] pending

### Task 3: Write C11 pytest tests
- **Files**: `tests/test_cortex_morning_review_complete_session.py`
- **What**: Pytest fixture-replay tests covering the six C11 behavior cases from spec R6. Tests invoke the real bash shim via `subprocess.run` and assert on filesystem state + exit code + stderr.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**:
  - Pattern reference: `tests/test_git_sync_rebase.py` — pytest tmpdir + `subprocess.run([str(SCRIPT_PATH), ...], cwd=...)` against the real script.
  - Module-level constant: `SCRIPT_PATH = Path(__file__).resolve().parent.parent / "bin" / "cortex-morning-review-complete-session"`.
  - Test functions (one per case in spec R6, ≥6 named functions starting with `test_`):
    - `test_executing_with_pointer_transitions_to_complete_and_unlinks_pointer` — fixture state has `phase: "executing"`; pointer file exists. After invocation: `load_state(state_path).phase == "complete"`; pointer file no longer exists; exit 0.
    - `test_executing_without_pointer_transitions_to_complete_no_pointer_touched` — fixture state has `phase: "executing"`; no `--pointer` arg passed; sentinel pointer file at an unrelated path is untouched. After invocation: state phase is `"complete"`; exit 0.
    - `test_phase_complete_is_noop_pointer_untouched` — fixture state `phase: "complete"`; pointer file exists; `--pointer` passed. After invocation: state phase still `"complete"`; pointer file still exists; exit 0.
    - `test_phase_paused_or_planning_is_noop_pointer_untouched` — parametrized over `["paused", "planning"]` (or two separate cases); same assertions as above (no state change, pointer preserved, exit 0).
    - `test_state_file_missing_silent_skip` — invoke pointing at a non-existent state_path; assert exit 0 and stderr is empty (or empty enough — no error message about missing state).
    - `test_malformed_phase_exits_nonzero_state_unchanged_stderr_names_phase` — manually write JSON containing **all six required raw-JSON keys** (`session_id`, `plan_ref`, `current_round`, `phase`, `started_at`, `updated_at`) with `phase: "running"` (or any value not in `PHASES = ("planning", "executing", "complete", "paused")`) and stub other-field values that satisfy basic structural validity (e.g., `session_id: "test-session"`, `plan_ref: "test-plan"`, `current_round: 1`, `started_at: "2026-04-28T00:00:00Z"`, `updated_at: "2026-04-28T00:00:00Z"`); assert exit code != 0 AND state file content is byte-identical to the pre-invocation fixture AND stderr contains the malformed phase value (e.g., `"running"`). (Failure mode the test is locking in: the helper reaches `OvernightState.__post_init__`, which raises `ValueError("Invalid phase 'running'; must be one of (...)")`. A fixture omitting any of the six required keys would raise `KeyError` at the dict-index step in `load_state` — the helper still exits non-zero with stderr, but the `"running"` substring assertion would fail.)
  - **Optional bonus case** (highly recommended, not a `def test_` requirement): a separate test for `KeyError`-on-missing-key behavior — fixture writes JSON with only `phase: "running"` (omits the other five keys); helper exits non-zero; stderr names the missing key. This locks in the catch-block coverage for `KeyError` separately from the `ValueError` path. If included, increment the `^def test_` count for clarity.
  - Fixture state writes use `cortex_command.overnight.state.save_state(...)` for cases (a)–(d) so the JSON layout is canonical; the malformed case (f) writes raw JSON via `json.dump` directly with the six required keys (above) to bypass `__post_init__` validation at fixture-creation time while still passing `load_state`'s required-key checks.
  - All `subprocess.run` calls pass `text=True, capture_output=True`. Each test uses `tmp_path` fixture for isolation.
  - The shim is invoked directly (not `python3 bin/...`) so the dispatcher path coverage is real.
- **Verification**: `cd /Users/charlie.hall/Workspaces/cortex-command && uv run pytest tests/test_cortex_morning_review_complete_session.py -v` — pass if exit 0 (all collected tests pass) AND `[ "$(grep -c '^def test_' tests/test_cortex_morning_review_complete_session.py)" -ge 6 ]`.
- **Status**: [ ] pending

### Task 4: Create C12 narrow bash leaf script
- **Files**: `bin/cortex-morning-review-gc-demo-worktrees`
- **What**: Bash leaf script that sweeps stale `demo-overnight-*` worktrees under `$TMPDIR`, with hardcoded prefix and one positional arg (active session ID to exclude). No flags, no `--force`. Includes the spec R9 uncommitted-state precondition and the spec R10 ordering invariant (per-worktree `git worktree remove` then a single `git worktree prune` after all removals).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Pattern reference: `bin/cortex-git-sync-rebase` for bash leaf-script structure.
  - Required structural lines (in order):
    1. `#!/bin/bash`
    2. `"$(dirname "$0")/cortex-log-invocation" "$0" "$@" || true`
    3. `set -euo pipefail`
  - CLI contract (per spec R8):
    - Exactly one positional arg: `<active-session-id>`.
    - No flags. No `--force`. No `--prefix`. No `--exclude`.
    - Invocation with zero args → stderr `Usage: cortex-morning-review-gc-demo-worktrees <active-session-id>`, exit non-zero.
  - Stderr-log convention: every action and skip line tagged `[gc-demo-worktrees]`.
  - Algorithm (preserves existing SKILL.md semantics from lines 50–75):
    1. Validate exactly 1 positional arg or exit non-zero with usage.
    2. If `${TMPDIR:-}` is empty OR `realpath "$TMPDIR"` fails → exit 0 silently (preserves SKILL.md line 66 silent-skip).
    3. Run `git worktree list --porcelain`. On non-zero exit → log stderr line and exit 0 (best-effort cleanup).
    4. For each `worktree <path>` line in the porcelain output:
       a. Compute `basename` of `<path>`.
       b. If `<path>` does not start with `<resolved_tmpdir>/` → skip.
       c. If `basename` does not match Bash ERE `^demo-overnight-` → skip.
       d. If `basename` starts with `demo-${active_session_id}-` (active-session exclusion) → skip silently.
       e. Run `git -C "<path>" status --porcelain --ignored=traditional`. If output is non-empty → stderr `[gc-demo-worktrees] skipping <path>: uncommitted state`, continue to next path. (Spec R9.)
       f. Otherwise log `[gc-demo-worktrees] removing <path>` to stderr, run `git worktree remove "<path>"` (no `--force`). On non-zero exit → log stderr line and continue with next path. (Preserves SKILL.md line 73 "do not abort the sweep".)
    5. After all per-path attempts complete: log `[gc-demo-worktrees] pruning` to stderr, run `git worktree prune`. On non-zero → log stderr and exit 0. (Preserves SKILL.md line 74 "non-fatal".)
  - The `[gc-demo-worktrees] removing` and `[gc-demo-worktrees] pruning` log lines are the observable signal that lets the Task 5 ordering test verify R10 by line-order assertion on the captured stderr.
  - Bash regex: use `[[ "$basename" =~ ^demo-overnight- ]]` (ERE via `=~`).
  - File mode: `chmod +x`.
- **Verification**: `cd /Users/charlie.hall/Workspaces/cortex-command && test -x bin/cortex-morning-review-gc-demo-worktrees && [ "$(head -3 bin/cortex-morning-review-gc-demo-worktrees | grep -c 'cortex-log-invocation')" -ge 1 ] && [ "$(grep -c 'set -euo pipefail' bin/cortex-morning-review-gc-demo-worktrees)" -ge 1 ] && [ "$(grep -c 'demo-overnight-' bin/cortex-morning-review-gc-demo-worktrees)" -ge 1 ] && [ "$(grep -c 'status --porcelain --ignored=traditional' bin/cortex-morning-review-gc-demo-worktrees)" -ge 1 ] && ! grep -q -- '--force' bin/cortex-morning-review-gc-demo-worktrees && bin/cortex-morning-review-gc-demo-worktrees 2>&1 >/dev/null | grep -q '^Usage:' && ! bin/cortex-morning-review-gc-demo-worktrees >/dev/null 2>&1` — pass if exit 0 (the final `!` inverts the expected non-zero exit when called with no args).
- **Status**: [ ] pending

### Task 5: Write C12 pytest tests
- **Files**: `tests/test_cortex_morning_review_gc_demo_worktrees.py`
- **What**: Pytest fixture-replay tests covering the six C12 behavior cases from spec R11. Tests build real git repos + real worktrees in pytest tmpdirs (since the script invokes real `git worktree`), invoke the script via `subprocess.run`, and assert on worktree presence/absence + stderr line ordering.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**:
  - Pattern reference: `tests/test_git_sync_rebase.py` — fixture repo + `subprocess.run([str(SCRIPT_PATH), ...], cwd=..., env=...)` invoking the real script.
  - Module-level constant: `SCRIPT_PATH = Path(__file__).resolve().parent.parent / "bin" / "cortex-morning-review-gc-demo-worktrees"`.
  - Per-test fixture setup helper (define once at module top):
    1. Create a parent repo: `git init <repo>; git -C <repo> commit --allow-empty -m initial`.
    2. Receive a `tmp_tmpdir: Path` per test (a pytest tmp subdir used as `$TMPDIR`).
    3. For each demo worktree to create: `git -C <repo> worktree add <tmp_tmpdir>/demo-overnight-2026-04-28-0900-20260428T130000Z`.
    4. Invoke script with `env={"TMPDIR": str(tmp_tmpdir), "PATH": os.environ["PATH"]}`, `cwd=<repo>`, capture stdout+stderr.
  - Required test functions (≥6, one per case in spec R11):
    - `test_clean_matching_worktree_is_removed` — single matching worktree, no untracked files. Assert: worktree dir no longer exists after run; exit 0; stderr contains `[gc-demo-worktrees] removing`.
    - `test_path_under_tmpdir_not_matching_prefix_is_left_alone` — worktree at `<tmp_tmpdir>/feature-something-...`. Assert: dir still exists after run; not in stderr `removing` lines; exit 0.
    - `test_uncommitted_untracked_file_skips_with_stderr_log` — matching worktree with `<path>/scratch.txt` untracked. Assert: dir still exists; stderr contains `[gc-demo-worktrees] skipping <path>: uncommitted state`; exit 0.
    - `test_tracked_dirty_worktree_is_skipped_or_remove_failure_logged` — matching worktree with a modified tracked file (or staged change). Assert: dir still exists after run AND (skip log line OR `git worktree remove` failure log line) appears in stderr. Either branch is acceptable per spec edge-case bullet at line 93.
    - `test_active_session_worktree_is_excluded_before_state_check` — fixture worktree named `demo-<active_id>-...`. Pass `<active_id>` as the script's positional arg. Assert: dir still exists; no stderr `removing` or `skipping` line for that path (the active-session exclusion fires before the state check, so no skip log either).
    - `test_prune_runs_once_after_all_remove_calls_ordering_invariant` — three matching clean worktrees. **Filter stderr to lines starting with `[gc-demo-worktrees]` BEFORE computing line indices** — `git worktree remove` and `git worktree prune` themselves emit untagged stderr (warnings, "Removing worktrees/...", etc.) that interleave with the script's tagged log lines. Without filtering, the line-index comparison is sensitive to git's own output and flaky across git versions. Concretely: `tagged = [line for line in stderr.splitlines() if line.startswith("[gc-demo-worktrees]")]`; assert exactly one element matches `[gc-demo-worktrees] pruning`, and its index in `tagged` is greater than the index of every `[gc-demo-worktrees] removing` element. Apply the same `[gc-demo-worktrees]`-prefix filtering when other tests in this file assert on stderr substring presence (e.g., the uncommitted-state skip log) — only the filtered stream is reliably ordered and reliably matched.
  - Each test uses `tmp_path` fixture and a sub-path for the synthetic `$TMPDIR` (do not pollute the host `$TMPDIR`).
  - **Fixture teardown**: each test must use a `yield`-based pytest fixture (or equivalent `addfinalizer` registration) that, in teardown, runs `git -C <parent_repo> worktree remove --force <wt>` for each worktree path created during setup, then `git -C <parent_repo> worktree prune` once. This prevents orphaned admin entries under `<parent_repo>/.git/worktrees/` from breaking subsequent test runs with "already registered" errors when a test crashes or is interrupted mid-fixture. The parent repo itself MUST live under `tmp_path` (not a shared per-module fixture) so its `.git/worktrees/` directory is cleaned up by pytest's tmpdir GC.
  - Skip tests on Windows (the script is bash-only); follow `tests/test_git_sync_rebase.py`'s skip pattern if present.
- **Verification**: `cd /Users/charlie.hall/Workspaces/cortex-command && uv run pytest tests/test_cortex_morning_review_gc_demo_worktrees.py -v` — pass if exit 0 AND `[ "$(grep -c '^def test_' tests/test_cortex_morning_review_gc_demo_worktrees.py)" -ge 6 ]`.
- **Status**: [ ] pending

### Task 6: Update SKILL.md to invoke new scripts
- **Files**: `skills/morning-review/SKILL.md`
- **What**: Replace the inline `jq` mutation prose at lines 35–48 with a single invocation of `cortex-morning-review-complete-session`. Replace the inline regex/loop sweep at lines 50–75 with a single invocation of `cortex-morning-review-gc-demo-worktrees`. Preserve the agent's path-resolution branch at lines 23–34 (active-session pointer vs `lifecycle/sessions/latest-overnight` fallback). Add an explicit `session_id` read step before the C12 invocation. Rewrite line 76 to drop the now-unobservable phase-terminal clause. Pass the resolved active session ID as the C12 script's positional arg (spec R13).
- **Depends on**: [2, 4]
- **Complexity**: simple
- **Context**:
  - **Lines 23–34 (preserved as-is)**: the prose that resolves `<resolved_state_path>` from either the active-session pointer (line 29: gates on `phase == "executing"`) or the `lifecycle/sessions/latest-overnight` fallback (line 30). The agent still owns this resolution; the new scripts only own the post-resolution mutation. Line 31 silent-skip "If neither path resolves to a readable file" is also preserved.
  - **Lines 35–48 (replaced)**: the inline `jq -r '.phase'` precondition + `jq '.phase = "complete"' > tmp` + `mv` + `rm -f <pointer_path>` block. Replaced by a single fenced Bash block invoking the shim. The helper now owns the precondition (per spec R5). The new prose specifies the pointer-flag gating predicate explicitly:
    - **Pass `--pointer <pointer_path>` iff the agent's path-resolution branch CHOSE the active-session pointer** (i.e., line 29's `phase == "executing"` check passed). When the path-resolution branch fell back to `latest-overnight` (line 30), invoke the shim WITHOUT `--pointer`.
    - This gating preserves current `rm -f <pointer_path>` semantics (current line 48 only fires when the active-session pointer was used and was found in `executing` phase). With the new helper, the unlink fires inside the helper on case 3 (executing → complete) when `--pointer` is supplied — same conditions, same outcome.
    - Two-bullet prose form ("If you used the active-session pointer..." / "If you used the fallback...") is acceptable.
  - **New explicit session-id read step** (inserted before the C12 invocation block): the agent must read `session_id` from `<resolved_state_path>` via `jq -r '.session_id' <resolved_state_path>` and store the result. Current line 70 step 1's "Read the current session ID (already resolved by Step 0 from `overnight-state.json`)" depended on the inline `jq` flow above; that flow is gone after Task 6. The session_id must be re-read explicitly.
    - **Read order vs C11**: the read can happen either BEFORE the C11 helper invocation (while phase is still `"executing"`) OR AFTER (state file's `session_id` field is invariant under C11 — only `phase` mutates). For prose simplicity, the new SKILL.md prose performs the read AFTER C11 completes, since `<resolved_state_path>` is unchanged and still readable.
  - **Lines 50–75 (replaced)**: the entire ERE-vs-BRE prose, regex literal, per-worktree loop, and explicit ordering-between-step-4-and-5 prose. Replaced by a single Bash invocation `cortex-morning-review-gc-demo-worktrees "$session_id"` (where `$session_id` is the value resolved by the new read step above). Brief preamble (1–2 sentences) explaining the sweep's purpose stays.
  - **Sweep ordering**: explicitly pin "the C12 sweep runs AFTER the C11 helper invocation" in the new prose (matches current line 53 "After marking the session complete, sweep stale demo worktrees..."). Both orderings are functionally safe (the C12 script does not depend on overnight-state.json's mutated phase), but the explicit pin removes ambiguity.
  - **Line 76 (rewritten — NOT preserved verbatim)**: original text — "Skip Step 0 entirely if no session is found or the session phase is already terminal (anything other than `'executing'`)." — references a phase observation the agent no longer performs after Task 6 removes the inline `jq -r '.phase'` check. Rewrite to: "Skip Step 0 entirely if neither path-resolution branch resolved to a readable state file (line 31). Otherwise invoke the C11 helper unconditionally — the helper itself silent-skips when phase is anything other than `'executing'` (per spec R5), and is safe to call repeatedly." This faithfully translates the original's two-clause skip into one clause owned by the agent (path-resolution failure) and one clause owned by the helper (non-executing phase silent-skip).
  - `walkthrough.md` references at lines 162, 195, 209, 543 are about Section 2a (creating demo worktrees) and Section 6 (post-review user cleanup), NOT the inline regex/loop. They are not callers of the inline patterns being removed and require no changes.
  - Caller enumeration confirmed: `grep -nrE "jq '\.phase = " skills/ requirements/ docs/ claude/ hooks/ tests/` and `grep -nrE 'demo-overnight-\[0-9\]\{4\}' skills/ requirements/ docs/` are expected to return zero matches outside `skills/morning-review/SKILL.md` itself.
- **Verification**: `cd /Users/charlie.hall/Workspaces/cortex-command && [ "$(grep -c 'cortex-morning-review-complete-session' skills/morning-review/SKILL.md)" -ge 1 ] && [ "$(grep -c 'cortex-morning-review-gc-demo-worktrees' skills/morning-review/SKILL.md)" -ge 1 ] && [ "$(grep -c "jq '\.phase = " skills/morning-review/SKILL.md)" -eq 0 ] && [ "$(grep -cE 'demo-overnight-\[0-9\]\{4\}' skills/morning-review/SKILL.md)" -eq 0 ] && [ "$(grep -cE 'cortex-morning-review-gc-demo-worktrees \S' skills/morning-review/SKILL.md)" -ge 1 ] && [ "$(grep -cE "jq -r '\.session_id'" skills/morning-review/SKILL.md)" -ge 1 ] && [ "$(grep -c 'session phase is already terminal' skills/morning-review/SKILL.md)" -eq 0 ]` — pass if exit 0. The added `jq -r '.session_id'` grep verifies the new explicit session-id read step is present (per the rewrite above); the negative grep on "session phase is already terminal" verifies the dangling line-76 phrase has been replaced.
- **Status**: [ ] pending

### Task 7: Mirror new scripts into the cortex-interactive plugin
- **Files**: `plugins/cortex-interactive/bin/cortex-morning-review-complete-session`, `plugins/cortex-interactive/bin/cortex-morning-review-gc-demo-worktrees`
- **What**: Run `just build-plugin` to rsync the new canonical `bin/cortex-*` scripts into the cortex-interactive plugin's `bin/`. Confirm byte-identical state via `git diff --exit-code`.
- **Depends on**: [2, 4]
- **Complexity**: simple
- **Context**:
  - `just build-plugin` runs `rsync -a --delete --include='cortex-*' --exclude='*' bin/ plugins/cortex-interactive/bin/`. New `cortex-morning-review-*` files are auto-included.
  - The dual-source pre-commit hook (enabled by `just setup-githooks`) runs the same rsync at commit time and refuses to commit if the working tree differs from the rsync output. Running `just build-plugin` here keeps the working tree clean before the Task 9 commit.
- **Verification**: `cd /Users/charlie.hall/Workspaces/cortex-command && just build-plugin && git diff --exit-code plugins/cortex-interactive/bin/` — pass if exit 0 (no unstaged drift after the rsync).
- **Status**: [ ] pending

### Task 8: Run parity check and full test suite
- **Files**: (verification-only — no files modified)
- **What**: Run `bin/cortex-check-parity` and `just test` to confirm the new scripts are wired through SKILL.md, the existing test suite still passes, and the new test files from Tasks 3 and 5 pass.
- **Depends on**: [3, 5, 6, 7]
- **Complexity**: simple
- **Context**:
  - `bin/cortex-check-parity` scans `skills/**/*.md`, `CLAUDE.md`, `requirements/`, `tests/`, `justfile`, `claude/hooks/`, `hooks/` for inline-code, fenced-block, and path-qualified references to `bin/cortex-*` scripts. New `cortex-morning-review-*` scripts are wired via the Task 6 SKILL.md edit.
  - `just test` (per repo justfile) runs the full pytest suite. Adds the two new test files from Tasks 3 and 5 alongside existing coverage.
  - No new entries in `bin/.parity-exceptions.md` should be needed.
- **Verification**: `cd /Users/charlie.hall/Workspaces/cortex-command && bin/cortex-check-parity && just test` — pass if exit 0 from both commands run sequentially.
- **Status**: [ ] pending

### Task 9: Commit via /cortex-interactive:commit
- **Files**: (commit-only — invokes the commit skill, no direct edits)
- **What**: Stage all created/modified files and create a commit using `/cortex-interactive:commit`. The dual-source drift hook, parity hook, and any other pre-commit checks must pass without `--no-verify` (spec R16).
- **Depends on**: [8]
- **Complexity**: simple
- **Context**:
  - Files to stage: `bin/cortex-morning-review-complete-session`, `bin/cortex-morning-review-gc-demo-worktrees`, `cortex_command/overnight/complete_morning_review_session.py`, `tests/test_cortex_morning_review_complete_session.py`, `tests/test_cortex_morning_review_gc_demo_worktrees.py`, `skills/morning-review/SKILL.md`, `plugins/cortex-interactive/bin/cortex-morning-review-complete-session`, `plugins/cortex-interactive/bin/cortex-morning-review-gc-demo-worktrees`. Lifecycle artifacts (`research.md`, `spec.md`, `plan.md`, `events.log`, `index.md`) are committed separately by the lifecycle skill at phase boundaries.
  - Per CLAUDE.md, never invoke `git commit` directly; use the `/cortex-interactive:commit` skill.
- **Verification**: Interactive/session-dependent: the `/cortex-interactive:commit` skill is interactive (it composes the message, runs pre-commit hooks, and reports the resulting `git log -1`); success is observable in the post-commit `git log` output but the commit step itself runs through the skill.
- **Status**: [ ] pending

## Verification Strategy

End-to-end verification proceeds in three layers:

1. **Unit (pytest fixture-replay)**: Tasks 3 and 5 prove the two scripts behave correctly across all spec edge cases (executing/non-executing/missing/malformed for C11; clean/untracked/dirty/active-session/ordering for C12). These are the load-bearing regression checks because no automated end-to-end `/morning-review` test exists in this repo (research §verified-facts #5).
2. **Integration (parity + full suite)**: Task 8's `bin/cortex-check-parity` confirms the new scripts are referenced through the in-scope SKILL.md, and `just test` confirms no existing test was broken by the SKILL.md edit or the new Python module.
3. **Distribution (build-plugin + commit gate)**: Task 7's byte-identity drift check and Task 9's pre-commit hook gate confirm the canonical `bin/` and the cortex-interactive plugin's `bin/` ship in lockstep.

Manual verification of the runtime path (running `/morning-review` against a fixture session directory) is out of scope per spec §Non-Requirements ("No new automated end-to-end test for `/morning-review` skill is added"). The unit tests in Tasks 3 and 5 are the substitute regression signal.

## Veto Surface

- **C11 dispatch shape**. The shim uses Branch (b) `env PYTHONPATH="$CORTEX_COMMAND_ROOT" python3 -m cortex_command.overnight.complete_morning_review_session`, which differs from `cortex-update-item`'s Branch (b) (which runs the file directly because `backlog/update_item.py` is a top-level module). The difference is forced: `complete_morning_review_session.py` imports from the `cortex_command.overnight.state` package and cannot run as a bare script. **Precedent caveat**: `cortex-update-item`'s Branch (a) is dead code in this repo (`cortex_command/backlog/` does not exist; `python3 -c "import cortex_command.backlog.update_item"` raises `ModuleNotFoundError`), so the precedent dispatcher is effectively single-branch in production. The new C11 shim's Branch (a) WILL fire under `uv tool install -e .` (the `cortex_command/overnight/` package exists), making C11 the first real two-branch dispatcher in the repo. The Task 2 verification only checks string presence; production validation that Branch (a) actually exec's the helper end-to-end is left to Task 3's pytest fixture (which invokes the shim directly, confirming Branch-(a) success on a real install). If the user prefers strict shape parity with `cortex-update-item`, the alternative is to relocate `complete_morning_review_session.py` to a top-level module path that doesn't require the `cortex_command` package on `sys.path` — but that would fragment the overnight package layout for one helper.
- **C12 ordering test mechanism**. Task 5 verifies the R10 ordering invariant by asserting line-order on the script's `[gc-demo-worktrees] removing` and `[gc-demo-worktrees] pruning` stderr lines. This couples the test to a logging contract added in Task 4. An alternative would be to mock `git` via a wrapper script on `PATH`, recording call order — that's heavier and brittle to git internals. Stderr line-order is the simpler observable.
- **C12 untracked-state precondition is a behavior change.** Pre-existing demo-overnight-* worktrees on disk that contain only untracked user files are now SKIPPED rather than removed. This is a real protection against silent destruction of in-flight user work in demo worktrees, but it does mean such worktrees stay on disk until the user resolves them. The spec accepts this trade-off (spec line 107) and the research's adversarial agent flagged it (research §security/data-loss). Veto opportunity if the user disagrees with the behavior change.
- **No new end-to-end `/morning-review` test**. Researched gap, deferred to a separate ticket per spec §Non-Requirements. If the user wants e2e coverage as a precondition for this ticket, scope expands by ~1 task (a pytest harness that drives the SKILL.md prose against a fixture session).

## Scope Boundaries

Per spec §Non-Requirements:

- **C13 backlog-closure parallel dispatch is NOT extracted** — already adopted in `walkthrough.md` §5; no remaining gaps.
- **C14 git preflight sync is NOT extracted** — inline 2-line `git fetch && git rev-list --count` is simpler than any wrapper.
- **C15 backlog-index regeneration fallback chain is NOT simplified** — the assumed PATH invariant is false in the general user case; the fallback is load-bearing.
- **`walkthrough.md` `git-sync-rebase.sh` drift fix is NOT done** — already fixed; ticket body claim is stale (verified zero matches in `walkthrough.md`).
- **`cortex_command/overnight/state.py:transition()` is NOT modified** — leveraged as-is.
- **No `flock` or `O_EXCL` cross-process serialization is added** — concurrent morning-review races are out of scope (broader IPC review carve-out).
- **No `.cortex-demo-marker` provenance file is introduced** — earlier draft included it; critical review identified this would silently regress GC behavior on every pre-existing demo worktree on user disks. Replaced by the uncommitted-state precondition (R9).
- **No new automated end-to-end `/morning-review` test is added** — flagged as a separate-ticket candidate.
- **The cosmetic `# git-sync-rebase.sh` comment-line drift in `bin/cortex-git-sync-rebase` is NOT fixed** — drive-by; opportunistic cleanup, not in scope.
- **`docs/setup.md` plugin-bin/ PATH-extension documentation gap is NOT fixed** — flagged as a precondition for any future C15 simplification, but independent of this ticket.
