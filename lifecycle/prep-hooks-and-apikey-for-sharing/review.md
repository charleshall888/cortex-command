# Review: prep-hooks-and-apikey-for-sharing (cycle 2)

## Stage 1: Spec Compliance

### Requirement 1: All 12 hook files renamed with `cortex-` prefix
- **Expected**: All 12 listed hook files renamed; `git ls-files hooks/ claude/hooks/` shows no files without the `cortex-` prefix (except non-hook files).
- **Actual**: All 12 files correctly renamed. Remaining non-prefixed files (`claude/hooks/bell.ps1`, `claude/hooks/setup-github-pat.sh`) are not registered hooks and are correctly excluded from scope.
- **Verdict**: PASS

### Requirement 2: All 11 hook path references in `claude/settings.json` updated atomically
- **Expected**: 11 of 14 hook-related entries updated to `cortex-*` names. The two `~/.claude/notify.sh` entries remain unchanged. WorktreeCreate/WorktreeRemove inline bash strings updated. No old names remain (per AC grep pattern).
- **Actual**: All 11 entries updated. Lines 264 and 282 (`~/.claude/notify.sh`) correctly unchanged. WorktreeCreate (line 318) and WorktreeRemove (line 328) inline bash strings correctly reference `cortex-worktree-create.sh` and `cortex-worktree-remove.sh`. JSON validated via `python3 -m json.tool`. AC grep returns zero matches.
- **Verdict**: PASS

### Requirement 3: Justfile updated in three places
- **Expected**: (a) `deploy-hooks` special case updated to `cortex-notify.sh`, (b) `validate-commit` recipe uses `cortex-validate-commit.sh`, (c) `check-symlinks` entries updated to `cortex-*` and stale `setup-github-pat.sh` entry removed.
- **Actual**: (a) Line 70: `[ "$name" = "cortex-notify.sh" ]` -- correct. (b) Line 421: `bash hooks/cortex-validate-commit.sh` -- correct. (c) Lines 449-455: all 7 hook entries in `~/.claude/hooks/` use `cortex-*` prefix plus `~/.claude/notify.sh` (8 total); stale `setup-github-pat.sh` entry removed.
- **Verdict**: PASS

### Requirement 4: Docs, tests, and skills updated
- **Expected**: All references to old hook filenames in the listed files updated to `cortex-*` names. AC grep pattern returns no matches across docs/, tests/, skills/, and claude/ (excluding settings.json and claude/hooks/).
- **Actual**: All references updated. Verified by running the AC grep pattern against each directory scope -- zero matches for any of the 11 old hook names. The `notify.sh` source-path references that were missed in cycle 1 are now fixed:
  - `claude/dashboard/alerts.py` line 111: `root / "hooks" / "cortex-notify.sh"` -- fixed
  - `claude/dashboard/alerts.py` line 108: docstring says `root/hooks/cortex-notify.sh` -- fixed
  - `docs/setup.md` line 201: `ln -sf` example uses `cortex-notify.sh` -- fixed
  - `docs/setup.md` line 298: compatibility table uses `cortex-notify.sh` -- fixed
  - `CLAUDE.md` line 27 / `Agents.md` line 27: symlink table uses `hooks/cortex-notify.sh` -- fixed
- **Verdict**: PASS

### Requirement 5: `claude/get-api-key.sh` stub shipped in repo
- **Expected**: Executable stub at `claude/get-api-key.sh` that delegates to `~/.claude/get-api-key-local.sh` if it exists, otherwise exits 0 with no output.
- **Actual**: File exists, git mode is `100755` (executable). Script checks for `$HOME/.claude/get-api-key-local.sh`, execs it with `$@` if executable, otherwise exits 0. Logic is correct and clean.
- **Verdict**: PASS

### Requirement 6: deploy-config wires up the stub symlink
- **Expected**: `deploy-config` recipe symlinks `claude/get-api-key.sh` to `~/.claude/get-api-key.sh` with the regular-file guard.
- **Actual**: Line 90 includes `~/.claude/get-api-key.sh` in the target loop. Line 103 adds the `ln -sf` case. The regular-file guard (lines 91-98) applies to all targets including this one. Pattern is consistent with existing targets.
- **Verdict**: PASS

### Requirement 7: Atomic single commit
- **Expected**: All changes delivered in a single commit. No partial-state commits.
- **Actual**: Two commits exist: `4d19ccb` (30 files -- all renames, stub, settings, docs, tests) and `b78dc3e` (3 files -- fixes from cycle 1 review). The second commit addresses `alerts.py` runtime path, `docs/setup.md` examples, and `Agents.md` symlink table. The intermediate state between the two commits does not break settings.json hook registrations (the core concern), but does leave `alerts.py` pointing to a nonexistent `hooks/notify.sh` and documentation with stale references.
- **Verdict**: PARTIAL
- **Notes**: The two commits should be squashed before merge to satisfy the single-commit AC. This is a mechanical squash with no conflicts. The intermediate state is a consequence of the review cycle itself, not a design flaw.

### Requirement 8: Hooks fire correctly after immediate re-deploy
- **Expected**: After `just deploy-hooks`, all hooks execute without "No such file" errors.
- **Actual**: Cannot verify runtime behavior in a read-only review. The `deploy-hooks` recipe correctly globs `hooks/*.sh` and `claude/hooks/*`, so renamed files are picked up automatically. The `cortex-notify.sh` special case (line 70) is correctly handled. No structural issues that would prevent correct deployment.
- **Verdict**: PASS (structural verification only; runtime verification deferred to user)

### Requirement 9: Interactive Claude Code startup verification (blocking pre-merge)
- **Expected**: Manual verification by primary user that no startup error related to `apiKeyHelper` appears.
- **Actual**: Cannot verify in automated review. The stub exists, is executable, and returns empty. Structurally correct.
- **Verdict**: PASS (structural verification only; manual verification deferred to user per spec)

## Requirements Compliance (project.md)

- **File-based state**: No new databases or servers introduced. The `get-api-key.sh` stub is a plain file. Compliant.
- **Complexity must earn its place**: The `get-api-key.sh` stub is minimal (11 lines). The rename is mechanical. No unnecessary complexity added. Compliant.
- **Symlink architecture**: New symlink follows existing pattern in `deploy-config` (regular-file guard, `ln -sf`). Compliant.
- **Settings JSON must remain valid JSON**: Verified via `python3 -m json.tool`. Compliant.
- **Hook/notification scripts must be executable**: `get-api-key.sh` has mode `100755`. Compliant.
- **Commit conventions**: Imperative mood, descriptive messages. Compliant.

## Stage 2: Code Quality

### Naming conventions
All 12 hooks consistently use the `cortex-` prefix. No mixed naming. The prefix choice is clean and collision-resistant. The `get-api-key.sh` stub follows the existing naming pattern in `claude/`.

### Error handling
The `get-api-key.sh` stub uses `[[ -x "$local_script" ]]` (checks both existence and executability), which is correct -- a non-executable override file is silently skipped rather than producing an exec error. The `deploy-config` regular-file guard is consistent with existing targets.

### Test coverage
All test files that reference hook paths have been updated. The test file count matches the spec's list. No new tests were needed since no logic changed -- only paths. The `test_alerts.py` line 174 comment mentions `cortex-notify-remote.sh`, which is correct.

### Pattern consistency
The implementation follows the existing project patterns exactly:
- `deploy-hooks` glob pattern picks up renames automatically
- `deploy-config` target loop extended with the same pattern
- `check-symlinks` entries use the same `check` function
- Settings.json hook registrations use the same path format

One minor observation (not a blocker): `check-symlinks` does not include a check for `~/.claude/get-api-key.sh`, though it checks the other three `deploy-config` targets (`settings.json`, `CLAUDE.md`, `statusline.sh`). Not required by the spec, but noted for potential follow-up.

## Verdict

All 5 issues from cycle 1 have been correctly addressed. All requirements PASS except Requirement 7 (PARTIAL -- two commits instead of one). The fix is a mechanical squash before merge.

```json
{"verdict": "APPROVED", "cycle": 2, "notes": ["Req 7 PARTIAL: two commits (4d19ccb + b78dc3e) should be squashed before merge to satisfy single-commit AC", "check-symlinks does not verify ~/.claude/get-api-key.sh symlink (not required by spec, noted for follow-up)", "Reqs 8 and 9 require manual verification by primary user before merge"]}
```
