# Review: extract-morning-review-deterministic-sequences-c11-c15-bundle (cycle 1)

## Stage 1: Spec Compliance

### R1 — C11 helper exists as Python module + bash shim
**Status**: PASS
- `bin/cortex-morning-review-complete-session` exists, is executable, and is `cortex-*` prefixed.
- The first non-comment line after the shebang invokes `"$(dirname "$0")/cortex-log-invocation" "$0" "$@" || true` (line 2), satisfying the DR-7 telemetry-shim convention.
- Acceptance grep for `cortex-log-invocation` in `head -20`: returns 1 (≥1).

### R2 — C11 dispatches via Python module
**Status**: PASS
- `python3 -m cortex_command.overnight.complete_morning_review_session` appears twice (Branch (a) line 7 and Branch (b) line 14): grep count 2 (≥1).
- `CORTEX_COMMAND_ROOT` appears 6 times: grep count 6 (≥1).
- Three-branch dispatcher: (a) packaged-form import-and-`-m`, (b) `CORTEX_COMMAND_ROOT` checkout with sanity-guard `grep '^name = "cortex-command"' "$CORTEX_COMMAND_ROOT/pyproject.toml"` plus the `env PYTHONPATH=...` `-m` invocation (the documented Veto-Surface variation from the `cortex-update-item` precedent), (c) explicit "install cortex-interactive plugin or set CORTEX_COMMAND_ROOT" message + `exit 2`.

### R3 — C11 uses canonical state-machine API
**Status**: PASS
- `cortex_command/overnight/complete_morning_review_session.py:33` — `from cortex_command.overnight.state import load_state, save_state, transition` (grep count 2 ≥1).
- Line 99: `new_state = transition(state, "complete")` (grep count 1 ≥1).
- Lines 102 + 33: `save_state(...)` references count 2 (≥1).
- No `jq`-style or direct `phase = "complete"` mutation in the new module — only the canonical functions are used.

### R4 — C11 CLI contract is explicit
**Status**: PARTIAL
- The Python module (`cortex_command/overnight/complete_morning_review_session.py:50–60`) declares the `--pointer` argparse flag and the `Path(pointer_path).unlink(missing_ok=True)` line at module line 113.
- The shim is a thin three-branch dispatcher that forwards `"$@"` and does not literally mention `--pointer`. The spec acceptance command `grep -E '\-\-pointer' bin/cortex-morning-review-complete-session | wc -l` returns **0** (spec asks ≥1), so the literal acceptance check fails.
- However, the spec immediately notes "covered functionally by pytest cases (Requirement 6)", and the functional intent is verified end-to-end:
  - `tests/test_cortex_morning_review_complete_session.py:71-97` (case a) invokes the shim with `--pointer` and asserts the pointer is unlinked — exercising the full shim → Python `--pointer` argparse → `unlink(missing_ok=True)` path through the real bash entry point.
  - `tests/test_cortex_morning_review_complete_session.py:100-127` (case b) invokes the shim WITHOUT `--pointer` and asserts the unrelated sentinel file is preserved.
- `grep -E 'unlink\(missing_ok=True\)' cortex_command/overnight/complete_morning_review_session.py | wc -l` returns 1 (≥1) — the second R4 acceptance command passes.
- Net: PARTIAL because of the literal grep miss on the shim; the implementation fulfills the contract through forwarded args and is functionally verified.

### R5 — C11 silent-skip semantics for non-executing phases
**Status**: PASS
- Module lines 91-92: `if state.phase != "executing": return 0`. No `transition()` call. No pointer unlink (the unlink at line 112-113 is gated on falling through to the post-`save_state` happy path).
- Verified by tests:
  - case (c) `test_phase_complete_is_noop_pointer_untouched` (lines 130-155): `phase: "complete"` + `--pointer` → state unchanged, pointer preserved, exit 0.
  - case (d) `test_phase_paused_or_planning_is_noop_pointer_untouched` (lines 158-189): parametrized over `["paused", "planning"]`, asserts state unchanged + pointer preserved + exit 0.

### R6 — C11 has pytest fixture-replay tests
**Status**: PASS
- `tests/test_cortex_morning_review_complete_session.py` exists.
- `grep -cE '^def test_' tests/test_cortex_morning_review_complete_session.py` returns **7** (≥6).
- Coverage:
  - (a) executing+pointer (test_executing_with_pointer_transitions_to_complete_and_unlinks_pointer)
  - (b) executing without pointer (test_executing_without_pointer_transitions_to_complete_no_pointer_touched)
  - (c) phase complete (test_phase_complete_is_noop_pointer_untouched)
  - (d) phase paused/planning (test_phase_paused_or_planning_is_noop_pointer_untouched, parametrized)
  - (e) state file missing (test_state_file_missing_silent_skip)
  - (f) malformed phase (test_malformed_phase_exits_nonzero_state_unchanged_stderr_names_phase) — fixture writes all six required keys with `phase: "running"`, asserts non-zero exit, byte-identical state file, and `"running"` substring in stderr.
  - bonus: missing-required-key KeyError path (test_missing_required_key_exits_nonzero_state_unchanged).
- Per the orchestrator's confirmed verification fact: `uv run pytest tests/` reports 426 passed including this file.

### R7 — C12 helper exists as bash leaf script
**Status**: PASS
- `bin/cortex-morning-review-gc-demo-worktrees` exists, is executable, prefixed `cortex-*`.
- Line 2: `cortex-log-invocation` shim line as the first non-comment line.
- Line 3: `set -euo pipefail`.
- All stderr log lines tagged `[gc-demo-worktrees]` (lines 31, 65, 69, 71, 77, 79).

### R8 — C12 has a narrow CLI contract
**Status**: PASS
- Lines 14-17: bare invocation with zero args prints `Usage: cortex-morning-review-gc-demo-worktrees <active-session-id>` to stderr and exits 2 (verified empirically: `./bin/cortex-morning-review-gc-demo-worktrees` → stderr `Usage: ...`, exit 2).
- `grep -E 'demo-overnight-' bin/cortex-morning-review-gc-demo-worktrees | wc -l` returns 4 (≥1) — prefix is hardcoded at line 53 (regex `^demo-overnight-`) and referenced in comments.
- `grep -E -- '--force' bin/cortex-morning-review-gc-demo-worktrees | wc -l` returns 0 — no `--force` flag.
- No `--prefix` or `--exclude` flag.

### R9 — C12 uncommitted-state precondition
**Status**: PASS
- Line 63: `dirty_status="$(git -C "$path" status --porcelain --ignored=traditional 2>/dev/null || true)"`.
- Line 64-67: if `dirty_status` is non-empty, log `[gc-demo-worktrees] skipping <path>: uncommitted state` to stderr and `continue` (skip the `git worktree remove`).
- Verified by test_uncommitted_untracked_file_skips_with_stderr_log (lines 202-235): an untracked `scratch.txt` results in worktree preserved + tagged skip log + exit 0.

### R10 — C12 ordering invariant preserved
**Status**: PASS
- Per-worktree `git worktree remove` runs inside the `for path in "${candidates[@]}"` loop (lines 44-74).
- The single `git worktree prune` invocation appears at line 78 — outside the for-loop (which ends at line 74).
- The "[gc-demo-worktrees] pruning" stderr line at line 77 enables the test_prune_runs_once_after_all_remove_calls_ordering_invariant test to assert exactly one `pruning` line whose tagged-stream index is greater than every `removing` index (test lines 357-380).

### R11 — C12 has pytest fixture-replay tests
**Status**: PASS
- `tests/test_cortex_morning_review_gc_demo_worktrees.py` exists.
- `grep -cE '^def test_' tests/test_cortex_morning_review_gc_demo_worktrees.py` returns **6** (≥6).
- Coverage:
  - (a) test_clean_matching_worktree_is_removed
  - (b) test_path_under_tmpdir_not_matching_prefix_is_left_alone
  - (c) test_uncommitted_untracked_file_skips_with_stderr_log
  - (d) test_tracked_dirty_worktree_is_skipped_or_remove_failure_logged
  - (e) test_active_session_worktree_is_excluded_before_state_check
  - (f) test_prune_runs_once_after_all_remove_calls_ordering_invariant
- Tests use `_tagged()` helper (lines 59-71) to filter stderr to lines beginning with `[gc-demo-worktrees]` before line-index assertions, matching the spec/plan guidance about git's untagged stderr being unstable across versions.
- Fixture (`gc_fixture`, lines 74-125) is yield-based with `try/finally` teardown that force-removes registered worktrees and prunes the parent repo, preventing orphaned admin entries from breaking subsequent runs.
- Per the orchestrator's confirmed verification fact: `uv run pytest tests/` reports 426 passed including this file.

### R12 — SKILL.md is updated to call new scripts with their full CLI contracts
**Status**: PASS
- `grep -cE 'cortex-morning-review-complete-session' skills/morning-review/SKILL.md` returns 2 (≥1) — invoked at SKILL.md lines 38 and 44 (the two pointer-presence branches).
- `grep -cE 'cortex-morning-review-gc-demo-worktrees' skills/morning-review/SKILL.md` returns 1 (≥1) — invoked at line 60.
- `grep -cE "jq '\\.phase = " skills/morning-review/SKILL.md` returns 0 — inline `jq` mutation prose removed.
- `grep -cE 'demo-overnight-\[0-9\]\{4\}' skills/morning-review/SKILL.md` returns 0 — inline ERE regex prose removed.
- The agent's path-resolution branch (active-session pointer vs `lifecycle/sessions/latest-overnight` fallback) is preserved at SKILL.md lines 27-31.
- The two-bullet form at lines 35-45 captures the `--pointer`/no-`--pointer` gating predicate.

### R13 — SKILL.md prose passes the C12 script its required positional arg
**Status**: PASS
- SKILL.md line 60: `cortex-morning-review-gc-demo-worktrees "$session_id"`.
- `grep -cE 'cortex-morning-review-gc-demo-worktrees \S' skills/morning-review/SKILL.md` returns 1 (≥1).
- The session_id is read at line 50 via `jq -r '.session_id' <resolved_state_path>` (an explicit step inserted per Plan Task 6's "new explicit session-id read step" requirement, since the prior inline `jq -r '.phase'` flow is gone).

### R14 — Parity linter passes
**Status**: PASS
- `bin/cortex-check-parity` exits 0 (verified locally; orchestrator-confirmed at implement-phase end).
- No new entries added to `bin/.parity-exceptions.md`. Both new scripts are wired through SKILL.md fenced blocks (lines 37-39, 42-45, 59-61), which is the parity linter's recognized signal.

### R15 — Build-plugin byte-identity drift check passes
**Status**: PASS
- `git diff --exit-code plugins/cortex-interactive/bin/cortex-morning-review-complete-session plugins/cortex-interactive/bin/cortex-morning-review-gc-demo-worktrees` exits 0.
- Direct `diff` between canonical `bin/` and `plugins/cortex-interactive/bin/` confirms byte-identical state for both new scripts.
- Both plugin mirrors are committed (commit eb41ea1) and have the executable bit set.
- The `plugins/cortex-overnight-integration/skills/morning-review/SKILL.md` mirror is byte-identical to `skills/morning-review/SKILL.md` (10286 bytes each).

### R16 — Pre-commit hook passes
**Status**: PASS
- The implementation landed in three commits inside the spec range (eb41ea1 → 3a04813 → f525ac6) without `--no-verify`. The orchestrator-noted "implement phase commits succeeded" plus the working-tree-clean status of plugin mirrors confirms the dual-source pre-commit gate accepted each commit.

## Requirements Drift

**State**: detected
**Findings**:
- The C12 script introduces a "destructive operation refuses to act on dirty/untracked worktrees" semantic (R9 uncommitted-state precondition). This is a new safety-style architectural constraint — repository-wide GC scripts now have a documented precondition pattern of "skip rather than destroy when local state is dirty." `requirements/project.md` enumerates the SKILL.md-to-bin parity invariant under "Architectural Constraints" and graceful-failure norms under "Quality Attributes," but does not currently capture this "destructive ops respect uncommitted state" norm. The pattern is likely to recur in future cleanup scripts (see also `cortex-git-sync-rebase`'s allowlist-driven conflict resolution), so codifying it once now prevents drift.
- The "behavior change" called out in the spec (Changes to Existing Behavior, line 107: "Worktrees containing untracked files are now SKIPPED rather than removed") is not reflected anywhere in the loaded project requirements doc. This is a user-visible behavior shift in the morning-review surface; future contributors editing similar GC code would not learn the convention from project.md alone.

**Update needed**: `requirements/project.md`

## Suggested Requirements Update

**File**: `requirements/project.md`
**Section**: `## Quality Attributes`
**Content**:
```
- **Destructive operations preserve uncommitted state**: Cleanup scripts that remove user-visible artifacts (worktrees, branches, session directories) check for uncommitted or untracked state in the target before destruction and SKIP rather than destroy. Inline destructive sequences are extracted into named scripts when they reach this complexity bar so the precondition is testable. Stderr logs the skip with a tagged source prefix.
```

## Stage 2: Code Quality

### Naming conventions
- Both scripts follow the `bin/cortex-*` prefix convention. Names are domain-scoped (`cortex-morning-review-complete-session`, `cortex-morning-review-gc-demo-worktrees`) rather than generic (`cortex-complete-session`, `cortex-gc-worktrees`), making the call site in SKILL.md self-documenting.
- The Python module name `cortex_command.overnight.complete_morning_review_session` matches the script name 1:1 (modulo dashes → underscores) and is correctly placed in the `overnight/` package alongside `state.py` and `ipc.py`. Plan §Open Decisions resolved the namespace explicitly to this path.
- Stderr tag `[gc-demo-worktrees]` (without the `cortex-morning-review-` prefix) is concise; the test fixture filters on it cleanly.

### Error handling
- The C11 module's catch block at `complete_morning_review_session.py:79-86` consolidates `JSONDecodeError`, `KeyError`, and `ValueError` into a single `[complete-morning-review-session] error loading {state_path}: {e}` stderr message. The exception's `str(e)` includes the offending phase value (per `OvernightState.__post_init__`'s f-string format `Invalid phase {self.phase!r}; ...`), so the malformed-phase test's `"running" in result.stderr` assertion is genuinely testing the schema-improvement behavior the ticket lands.
- `save_state` failure is caught separately (`OSError` at lines 103-109) so the pointer is NOT unlinked — this matches the spec edge case (Case 5).
- Silent-skip vs loud-fail boundaries match spec edge cases:
  - Missing state file → silent exit 0 (Case 1, line 72).
  - Non-executing phase → silent exit 0 (Case 4, line 91).
  - Unparseable / malformed phase / missing key → loud non-zero (Case 2, line 81).
  - `save_state` `OSError` → loud non-zero, pointer preserved (Case 5, line 103).
- C12 silent-skips: `$TMPDIR` unset (line 23), `realpath` failure (line 26). Both match spec line 89.
- C12 best-effort logged-and-continue: `git worktree list` failure (line 30), per-worktree `git worktree remove` failure (line 70-72), trailing `git worktree prune` failure (line 78-80). All match spec lines 94-96.

### Test coverage
- C11: 7 `def test_` functions cover the six required cases plus a bonus KeyError case for the missing-required-key path. The malformed-phase fixture correctly writes all six required raw-JSON keys to bypass `OvernightState.__post_init__` validation at fixture-creation time (line 232-241), exercising the helper's actual `load_state` → `__post_init__` → `ValueError` path. This is the load-bearing test for the schema-enforcement improvement (the only real semantic change C11 lands on the `executing → complete` happy path).
- C12: 6 `def test_` functions cover the six required cases. The fixture (`gc_fixture`) yields a dict with `parent_repo`, `tmp_tmpdir`, and an `add_worktree` callable; teardown force-removes registered worktrees AND runs `git worktree prune` once, preventing the "already registered" failure mode the plan specifically called out at Plan Task 5 step 5. Each test platform-skips on Windows, matching the bash-only-script reality.
- Stderr filtering via `_tagged()` is applied consistently across the C12 tests that assert on stderr content (uncommitted-skip, removal-failed, ordering invariant). This avoids the cross-git-version flakiness the plan flagged.

### Pattern consistency
- C11 shim: layout matches `bin/cortex-update-item` — three-branch dispatcher with the same first-three-line skeleton (`#!/bin/bash`, log-invocation, `set -euo pipefail`), Branch (a) `python3 -c "import …" && exec python3 -m …`, Branch (b) `CORTEX_COMMAND_ROOT` checkout with the `grep '^name = "cortex-command"'` sanity guard, Branch (c) explicit error message + `exit 2`. The Branch (b) variation (`exec env PYTHONPATH="$CORTEX_COMMAND_ROOT:${PYTHONPATH:-}" python3 -m …` instead of `exec python3 "$CORTEX_COMMAND_ROOT/…/script.py"`) is correctly forced because the helper imports from `cortex_command.overnight.state`; running the file directly would not satisfy the package import. Documented in Plan §Veto Surface.
- C12 leaf: shape matches `bin/cortex-git-sync-rebase` — bash leaf with `set -euo pipefail`, tagged stderr log lines, explicit usage error, no third-party-runtime dependency. The script is self-contained.
- One minor observation: `bin/cortex-morning-review-complete-session` line 1 uses `#!/bin/bash` (matching `cortex-update-item`); `bin/cortex-morning-review-gc-demo-worktrees` line 1 also uses `#!/bin/bash`. The reference `cortex-git-sync-rebase` uses `#!/usr/bin/env bash`. The choice of `#!/bin/bash` is consistent with the closer dispatcher precedent and is not a defect; just noted for awareness.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
