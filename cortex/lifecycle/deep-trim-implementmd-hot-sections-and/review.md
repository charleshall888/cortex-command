# Review: deep-trim-implementmd-hot-sections-and

## Stage 1: Spec Compliance

### Requirement R1: Replace §1a-i with a real lock probe ordered after the overnight guard (s10)
- **Expected**: In implement.md §1a, remove the `cat …sessions/{slug}.interactive.pid` + `kill -0` prose. `selected` mode does not re-acquire; `suppressed` mode acquires `cortex-interactive-lock acquire {slug}` positioned **after** the §1a overnight guard, branching on exit code (0 → worktree creation; non-zero → surface stderr verbatim, exit §1a). Acceptance greps: `kill -0` = 0, phantom `sessions/*.interactive.pid` = 0, awk ordering exit 0, contract test green.
- **Actual**: `grep -c 'kill -0'` = 0; `grep -cE 'sessions/[^ ]*\.interactive\.pid'` = 0. The awk ordering check exits 0 (suppressed acquire at line 105 > §1a overnight-check sidecar at line 97). §1a-ii (line 102) states the lock runs "only **after** the overnight guard (i) has passed, so a rejecting overnight guard can never orphan a held lock." Line 104 (`selected`): "do **not** acquire again … Proceed to iii." Line 105 (`suppressed`): "Exit 0 → proceed to iii. Non-zero → … surface that stderr verbatim and exit §1a without creating a worktree." `.venv/bin/pytest tests/test_implement_worktree_interactive_contract.py -q` → 5 passed.
- **Verdict**: PASS
- **Notes**: Ordering is correct both mechanically (105 > 97) and semantically (prose gates acquire on overnight-guard pass), closing the orphan-lock-on-overnight-reject hazard the critical-review flagged.

### Requirement R2: Rewire fire-condition (iv) to the real lock (lifecycle_implement.py)
- **Expected**: `_has_live_interactive_session` returns `slug in scan_live_locks(pathlib.Path(repo_root))` (imported from `cortex_command.interactive_lock`); `_SESSIONS_RELDIR` and phantom-path construction deleted. Acceptance: `_SESSIONS_RELDIR` = 0, `scan_live_locks\s*\(` ≥ 1, branch-mode test green.
- **Actual**: `grep -c '_SESSIONS_RELDIR'` = 0; `grep -cE 'scan_live_locks\s*\('` = 1 (line 76: `return slug in _scan_live_locks(_pathlib.Path(repo_root))`). Import at line 28. `.venv/bin/pytest tests/test_lifecycle_implement_branch_mode.py -q` → 9 passed.
- **Verdict**: PASS
- **Notes**: Delegation is clean — the predicate calls the single source of truth; no liveness algorithm re-implemented in the consumer.

### Requirement R3: Update the branch-mode picker fixture to the real lock path
- **Expected**: The a3 case writes a JSON lock at `cortex/lifecycle/{slug}/interactive.pid` with `"magic": "cortex-interactive-lock"`, live self-PID (`os.getpid()`), `session_id: null`, `start_time: null` (Row-4 conservative-LIVE); the `(True, "live_interactive_worktree_session")` assertion and the `.git/info/exclude` gitignore are retained. Acceptance: `TestShouldFirePicker` green.
- **Actual**: `test_a3_trunk_live_interactive_pid_fires` (lines 92–150) writes the real lock at `cortex/lifecycle/{slug}/interactive.pid` with magic + `os.getpid()` + null session/start_time, gitignores `cortex/` via `.git/info/exclude`, sanity-checks a clean tree, and asserts `(True, "live_interactive_worktree_session")`. `.venv/bin/pytest tests/test_lifecycle_implement_branch_mode.py::TestShouldFirePicker -q` → 5 passed.
- **Verdict**: PASS
- **Notes**: The fixture drives a real on-disk lock through `should_fire_picker → _has_live_interactive_session → scan_live_locks` (no mocks) — an integration-level exercise of the dead→live flip, matching the spec's Row-4-sufficient scoping.

### Requirement R4: Fix BOTH stale phantom docstrings (lifecycle_implement.py)
- **Expected**: Realign the `_has_live_interactive_session` docstring (was `implement.md:78–82`) and the `should_fire_picker` condition-(iv) line (was phantom `sessions/{slug}.interactive.pid`) to reference `scan_live_locks` + `§1a-i`, dropping line-number/phantom-path cites. Acceptance: `implement.md:78` = 0, phantom path = 0, `scan_live_locks` ≥ 2.
- **Actual**: `grep -c 'implement.md:78'` = 0; `grep -cE 'sessions/[^ ]*\.interactive\.pid'` = 0; `grep -c 'scan_live_locks'` = 4. Docstring line 72–74: "Delegates to `…scan_live_locks` … See `implement.md` §1a-i." Condition-(iv) line 97–99: "holds a live interactive lock per `cortex_command.interactive_lock.scan_live_locks` (§1a-i)."
- **Verdict**: PASS

### Requirement R5: Apply the eight verified compressions (s3, s5, s6, s12, s14, s21, s23, s11)
- **Expected**: Compress each section per its keep-list, preserving pinned tokens. Acceptance: full suite green plus per-pin greps.
- **Actual**: `just test` → 7/7 passed. Per-pin (against implement.md): `create_worktree` = 1; `cortex-worktree-create --feature interactive-` = 1; `**iii.` = 1; `Implement on feature branch with worktree` = 3; `bash -s --` = 2; `_interactive_overnight_check.sh` = 2; `ADR-0004` = 1; `self-sealing` = 1. Pinned dependency tests `test_lifecycle_enterworktree_callsites` + `test_gate_and_gated_path_use_same_binary` both green (3 passed + 1 passed). Commits are decomposed one-per-verdict (s3/s5/s6/s11/s12/s13+s14/s21/s23).
- **Verdict**: PASS

### Requirement R6: Compress s13 (step-v) at 10–15%, coordinated with s14
- **Expected**: ~10–15% cut preserving the four ordered tokens (`_origin_pwd` → `cortex-worktree-precondition` → `EnterWorktree(` → `interactive_worktree_entered`), the literal `EnterWorktree skipped: suppressed-picker`, absence of `verify-worktree-auth`, the "silent non-invocation" clause, and the cache-clear enumeration; ≥1 `**`-prefixed line surviving after the step-v body. Acceptance: `test_lifecycle_step_v_ordering.py` green.
- **Actual**: `_origin_pwd` = 1, `cortex-worktree-precondition` = 3, `EnterWorktree(` = 1, `interactive_worktree_entered` = 1, `EnterWorktree skipped: suppressed-picker` = 1, `verify-worktree-auth` = 0, `silent non-invocation` = 1. `.venv/bin/pytest tests/test_lifecycle_step_v_ordering.py -q` → 5 passed (the green test structurally asserts the trailing `**`-prefixed terminator).
- **Verdict**: PASS

### Requirement R7: Extract the merge-back procedure to a sibling reference (s18)
- **Expected**: Move the §2e five-case procedure into a new `skills/lifecycle/references/merge-back.md`; keep the inline §2e skip line; add an SP001/SP002-safe read directive (body-resolved absolute path) on the worktree-dispatch arm; add a `merge-back` entry to SKILL.md's Reference-path propagation block; git-track the new file in the same commit. Acceptance: file exists + git-tracked; references-resolve test green; `cortex-check-skill-path --audit` exit 0.
- **Actual**: `merge-back.md` exists and `git ls-files --error-unmatch` succeeds. implement.md §2e (line 186) reads it via `${CLAUDE_SKILL_DIR}/references/merge-back.md` (SP-safe prefixed form); the inline skip line "§2(e) merge-back applies unchanged" survives at line 143. SKILL.md line 161 adds the `merge-back` propagation entry. New file retains the `claude/hooks/cortex-worktree-create.sh` citation (grep = 1). `.venv/bin/pytest tests/test_lifecycle_references_resolve.py -q` → 4 passed; `cortex-check-skill-path --audit` → exit 0.
- **Verdict**: PASS

### Requirement R8: Regenerate the cortex-core mirror in the same commit; leave the `$model` block byte-unchanged
- **Expected**: After the canonical edits, `just build-plugin` and stage `plugins/cortex-core/skills/lifecycle/**` in the same commit; the §2b `$model` "halt and escalate" block byte-unchanged. Acceptance: `git diff --quiet plugins/cortex-core/skills/lifecycle/` clean; `halt and escalate` diff empty; pre-commit drift gate passes (commits landed).
- **Actual**: `git diff --quiet plugins/cortex-core/skills/lifecycle/` → exit 0 (mirror in sync). `git diff -- skills/lifecycle/references/implement.md | grep -E '^[-+].*halt and escalate'` → empty (the `$model` clause unmodified). The range diff shows canonical + mirror (`plugins/cortex-core/skills/lifecycle/{SKILL.md,references/implement.md,references/merge-back.md}`) moved together; all 11 commits landed on `main`, so the `.githooks/pre-commit` drift gate passed.
- **Verdict**: PASS

## Stage 2: Code Quality
- **Naming conventions**: Consistent. The aliased import `scan_live_locks as _scan_live_locks` follows the module's closed-public-API convention (only `REASONS` / `should_fire_picker` / `read_dispatch_choice` are public; all helpers underscore-prefixed). Removing `_SESSIONS_RELDIR` shrinks the module's private surface rather than leaving a dead constant.
- **Error handling**: Appropriate and improved. The consumer delegates entirely to `scan_live_locks`, which already handles missing lifecycle dir, JSON parse failures, and STALE owners gracefully (returns `set()` / skips), so `_has_live_interactive_session` inherits fail-safe behavior with no duplicated try/except. The R1 acquire-after-overnight-guard ordering removes the orphan-lock failure mode on the suppressed path.
- **Test coverage**: The plan's verification steps executed — full suite 7/7 plus every per-pin grep and awk check. The dead→live picker flip is covered through the real code path (a3 writes an on-disk lock and drives the top-level `should_fire_picker` predicate, not a mocked helper). One observation (not a defect, matches spec scope): coverage stops at the predicate; there is no separate E2E through the `cortex-lifecycle-picker-decision` console-script layer or an `acquire`→`scan` round-trip, and the fixture deliberately uses a Row-4 null-session lock rather than the Row-1 self-session lock a live `acquire` writes — the spec explicitly scoped the fixture that way (Technical Constraints, a3 fixture note).
- **Pattern consistency**: Gate authoring is structural, not re-narrated. implement.md §1a-ii branches on the `cortex-interactive-lock acquire` exit code and defers the rejection wording to the script's stderr rather than re-describing the R4 liveness branch table; the Python consumer delegates to `scan_live_locks` rather than re-deriving liveness. The merge-back read directive uses the SP001/SP002-safe `${CLAUDE_SKILL_DIR}/references/merge-back.md` prefixed form (skill-path audit exit 0). The `$model` block is left un-deduplicated as the deliberate #353-owned island, consistent with the spec's stated asymmetry.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
