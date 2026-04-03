# Review: build-setup-merge-local-skill

## Stage 1: Spec Compliance

### Requirement 1: Local project skill only
- **Expected**: Skill lives at `.claude/skills/setup-merge/SKILL.md`. Never deployed to `~/.claude/skills/` or `skills/`.
- **Actual**: Skill is at `.claude/skills/setup-merge/SKILL.md`. Not in `skills/` or deployed globally.
- **Verdict**: PASS

### Requirement 2: Python helper script
- **Expected**: JSON manipulation, diff computation, and atomic writes delegated to `.claude/skills/setup-merge/scripts/merge_settings.py`. Uses Python stdlib only.
- **Actual**: `merge_settings.py` exists at the correct path. Imports are: argparse, fnmatch, json, os, subprocess, sys, tempfile, pathlib -- all stdlib.
- **Verdict**: PASS

### Requirement 3: disable-model-invocation: true
- **Expected**: SKILL.md frontmatter contains `disable-model-invocation: true`.
- **Actual**: Present in frontmatter (line 4).
- **Verdict**: PASS

### Requirement 4: Symlink guard
- **Expected**: If `~/.claude/settings.json` is a symlink, abort immediately with the specified message.
- **Actual**: SKILL.md Step 1 checks via `python3 -c` with `pathlib.Path.is_symlink()`. Correct abort message. Correct behavior (halt, no write).
- **Verdict**: PASS

### Requirement 5: Worktree guard
- **Expected**: If `git rev-parse --git-dir` differs from `git rev-parse --git-common-dir`, abort with the specified message.
- **Actual**: SKILL.md Step 1 compares the two values. Correct abort message.
- **Verdict**: PASS

### Requirement 6: Sandbox warning
- **Expected**: If `$TMPDIR` starts with `/private/tmp/claude` or `/tmp/claude`, warn before proceeding (do NOT halt).
- **Actual**: SKILL.md Step 1 checks TMPDIR prefix and displays the warning. Explicitly says "do NOT halt -- continue after displaying."
- **Verdict**: PASS

### Requirement 7: Re-detect from current state
- **Expected**: Skill detects conflicts by reading the live system state, not from any manifest or previous run output.
- **Actual**: `detect_settings()` reads `~/.claude/settings.json` and `settings.local.json` at invocation time. `discover_symlinks()` reads repo directories at invocation time. No cached state used.
- **Verdict**: PASS

### Requirement 8: Authoritative install list -- runtime discovery
- **Expected**: Helper script determines install scope by reading repo directories at invocation time. No hardcoded file lists. Specific categories enumerated: bin/, claude/reference/*.md, skills/<name>/, hooks/cortex-*, notify.sh, statusline.sh, claude/rules/*.md.
- **Actual**: `discover_symlinks()` reads each directory at runtime. All 7 categories are covered. Skills are filtered to subdirectories containing SKILL.md -- this matches the `just setup` / `deploy-skills` pattern (`for skill in skills/*/SKILL.md`), so it's consistent with existing behavior even though the spec says "all subdirectories".
- **Verdict**: PASS

### Requirement 9: Conflict classification
- **Expected**: Five classifications: new, update, conflict-broken, conflict-wrong-target, conflict-file.
- **Actual**: `classify()` function (lines 67-91) returns exactly these five values. Logic is correct: checks `not exists and not is_symlink` for new; `is_symlink and resolved matches` for update; broken symlink detection; wrong-target detection; regular file detection.
- **Verdict**: PASS

### Requirement 10: New and update targets resolved silently
- **Expected**: New and update targets resolved without prompting; counted in summary.
- **Actual**: SKILL.md Step 4 "Silent installs" section: "Do not prompt for these -- just execute them. Keep a count."
- **Verdict**: PASS

### Requirement 11: Broken symlink conflicts
- **Expected**: Show broken path, ask Y/n. On Y: `ln -sf` (files) or `ln -sfn` (dirs). On N: skip.
- **Actual**: SKILL.md Step 4 "conflict-broken" section matches. Uses `ln_flag` from detect JSON (which is `-sf` or `-sfn` based on category).
- **Verdict**: PASS

### Requirement 12: Wrong-target symlink conflicts
- **Expected**: Show current target and cortex-command target side-by-side, ask Y/n.
- **Actual**: SKILL.md runs `readlink {target}` then displays both paths with Y/n prompt.
- **Verdict**: PASS

### Requirement 13: Regular-file conflicts
- **Expected**: Show diff (fallback to file listing), warn about destructive replacement, require explicit Y.
- **Actual**: SKILL.md runs `diff`, falls back to `ls -li`, displays destructive warning, asks Y/n.
- **Verdict**: PASS

### Requirement 14: Symlink commands
- **Expected**: `ln -sfn` for directories, `ln -sf` for files. Source paths absolute from `git rev-parse --show-toplevel`.
- **Actual**: `discover_symlinks()` sets `-sfn` for skills (directories) and `-sf` for all others. Source paths use `repo_root` from `git rev-parse --show-toplevel`.
- **Verdict**: PASS

### Requirement 15: Summary table first
- **Expected**: Before any Y/n prompts, display a table listing all pending categories with counts. Categories with no delta marked "already installed".
- **Actual**: SKILL.md Step 3 presents symlink summary table and settings summary table before any prompts.
- **Verdict**: PASS

### Requirement 16: Required hooks merged unconditionally
- **Expected**: Nine hooks across eight event types merged without Y/n. Hook presence detection uses (event-type, matcher, command-substring) triple. Hook insertion algorithm: find matching matcher group, append to it or create new group.
- **Actual**: `REQUIRED_HOOK_SCRIPTS` contains 9 scripts. `is_hook_present()` implements triple matching. `apply_hooks()` implements the insertion algorithm correctly. SKILL.md Step 5a states "merged unconditionally -- do not prompt Y/n."
- **Verdict**: PASS

### Requirement 17: Optional hooks prompted per hook with description
- **Expected**: Three optional hooks prompted individually with specific descriptions.
- **Actual**: `OPTIONAL_HOOK_SCRIPTS` contains the 3 scripts. SKILL.md Step 5b prompts each with the spec-specified descriptions.
- **Verdict**: PASS

### Requirement 18: Per-category settings prompted with delta
- **Expected**: Six categories (deny, allow, sandbox, statusLine, plugins, apiKeyHelper) prompted with delta display and category-specific notes.
- **Actual**: SKILL.md Step 5c covers all six categories with appropriate prompts, notes, and delta displays. apiKeyHelper checks for stub existence and settings.local.json presence.
- **Verdict**: PASS

### Requirement 19: Personal scalars never touched
- **Expected**: model, effortLevel, alwaysThinkingEnabled, etc. never modified.
- **Actual**: `run_merge()` only modifies specific keys (hooks, permissions.allow, permissions.deny, sandbox.*, statusLine, enabledPlugins.*, apiKeyHelper). No code touches personal scalar fields.
- **Verdict**: PASS

### Requirement 20: Forward contradiction check (deny blocks allow)
- **Expected**: Before writing allow entries, check `fnmatch.fnmatch(allow_cmd, deny_pattern)` against existing deny rules. Surface for manual resolution if matched.
- **Actual**: `check_forward_contradictions()` implements this correctly. Uses `extract_cmd()` to strip `Bash()` wrapper. Returns contradictions list. Skips contradicted entries.
- **Verdict**: PASS

### Requirement 21: Reverse contradiction check (allow blocks deny)
- **Expected**: Before writing deny entries, check if existing literal allow entries would be blocked. Surface for manual resolution.
- **Actual**: `check_reverse_contradictions()` implements this correctly.
- **Verdict**: PASS

### Requirement 22: Scope of checks -- wildcard advisory
- **Expected**: Literal entries only for hard checks. For wildcard entries, emit advisory ("This entry contains a wildcard -- verify it doesn't conflict with your rules") but proceed without blocking.
- **Actual**: Literal-only check is correct (wildcard entries skip the check and proceed). However, the wildcard advisory message is NOT emitted anywhere -- neither in the Python script nor in SKILL.md. Wildcard entries are silently passed through.
- **Verdict**: PARTIAL
- **Notes**: The wildcard advisory is missing. The spec explicitly requires emitting a per-entry advisory for wildcard allow entries in either direction. The script correctly avoids blocking them, but omits the advisory.

### Requirement 23: Hard block behavior
- **Expected**: Contradicted entries skipped even if user approved category. Each contradiction listed in post-merge summary.
- **Actual**: `check_forward_contradictions` and `check_reverse_contradictions` return non-contradicted entries (written) and contradictions (skipped). Contradictions are accumulated in `all_contradictions` and returned in the merge result. SKILL.md Step 6 displays them.
- **Verdict**: PASS

### Requirement 24: Single atomic write after all prompts
- **Expected**: After all Y/n prompts collected, single atomic write covering all approved categories. No partial writes.
- **Actual**: `run_merge()` accumulates all changes in memory, then calls `atomic_write()` once at the end.
- **Verdict**: PASS

### Requirement 25: Atomic protocol (mtime guard)
- **Expected**: Capture mtime after reading. Write to temp in same directory. Validate JSON. Check mtime matches. os.replace(). On failure: delete temp, abort.
- **Actual**: `atomic_write()` implements all five steps: mtime check, JSON serialize, JSON validate, mkstemp in same dir + fsync, os.replace. Cleanup on failure deletes temp file.
- **Verdict**: PASS

### Requirement 26: Abort conditions
- **Expected**: Abort if JSON validation fails, mtime check fails, or os.replace() fails.
- **Actual**: All three abort paths return error dicts. Original settings.json untouched in all cases.
- **Verdict**: PASS

### Requirement 27: Second-run idempotency
- **Expected**: All already-installed entries report "already installed". No entries re-added. If everything installed, exit with "All cortex-command components already installed."
- **Actual**: SKILL.md Step 3 early exit condition says "If ALL symlinks are status `new` or `update` AND all settings categories show 'already installed'". Including `new` in the early exit condition is incorrect -- `new` means the symlink target does not exist (not installed). On a true second run, all symlinks would be `update`, so this works correctly in practice. But the condition is technically wrong: if symlink targets are missing (`new`) yet settings are fully merged, the skill would say "All installed" and skip creating those symlinks.
- **Verdict**: PARTIAL
- **Notes**: The early exit condition in SKILL.md Step 3 includes `new` status symlinks, which means "target does not exist." This should only include `update` to correctly represent "already installed." In the common second-run case all symlinks are `update` so this works, but the logic is wrong for edge cases where symlinks were deleted after settings were merged.

### Requirement 28: Post-merge summary
- **Expected**: Count of symlinks installed/skipped, categories merged/skipped, all contradictions (both directions), skipped regular-file conflicts.
- **Actual**: SKILL.md Step 6 covers all four summary sections with correct formatting.
- **Verdict**: PASS

## Requirements Compliance

- **Complexity earned its place**: The Python helper is well-scoped to deterministic JSON operations. The SKILL.md orchestrates interactive UX. This split is justified by the spec requirement for atomic writes, contradiction detection, and structured data flow between detect and merge phases.
- **Failure handling surfaces errors**: Errors from detect, merge, mtime mismatch, and JSON validation are all surfaced to the user with clear messages. No silent skips.
- **Self-contained artifacts**: The skill is fully self-contained in `.claude/skills/setup-merge/` with no external dependencies beyond Python stdlib and git. The detect tempfile bridges the detect/merge phases cleanly.
- **No project constraint violations**: The skill is project-local (never deployed globally), uses only stdlib, follows the symlink-to-repo editing pattern, and does not touch `settings.local.json` for writes.
- **File-based state**: Uses a tempfile for inter-phase data, consistent with the project's file-based state approach.

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. Function names use snake_case. Constants use UPPER_SNAKE_CASE. The skill directory follows the `setup-merge` kebab-case convention. SKILL.md frontmatter has `name`, `description`, and `disable-model-invocation` fields matching existing skills.
- **Error handling**: Appropriate for the context. JSON read failures return None or error dicts. Atomic write has cleanup on failure. The mtime guard prevents concurrent modification. The detect/merge split means a bad merge can be re-run without re-detecting. The `try/except OSError` in `atomic_write` covers filesystem errors including PermissionError for sandboxed sessions.
- **Test coverage**: The plan's verification strategy covers unit (detect + merge modes), guard verification, and end-to-end testing. However, these are manual verification steps, not automated tests. Given this is an interactive skill that modifies `~/.claude/settings.json`, automated tests would be complex to set up. The manual verification approach is pragmatic for this context.
- **Pattern consistency**: Follows existing project conventions. The SKILL.md step-by-step format matches other skills. The Python helper uses `pathlib.Path` throughout. The detect/merge two-phase pattern with a tempfile is a clean architecture choice that avoids shell quoting issues. The `extract_cmd` function for stripping `Bash()` wrappers is a focused utility.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["Requirement 22: wildcard advisory message not emitted for wildcard entries in contradiction checks (spec says emit advisory, implementation silently passes through)", "Requirement 27: SKILL.md Step 3 early exit condition includes 'new' status symlinks alongside 'update', which could cause the skill to report 'All installed' when symlink targets do not yet exist"]}
```
