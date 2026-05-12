# Review: Remove interpreter escape hatch commands

## Stage 1: Spec Compliance

### Requirement 1: Remove 6 interpreter entries from allow list
**Rating**: PASS

All 6 entries confirmed absent from `claude/settings.json`:
- `Bash(bash *)` -- 0 matches
- `Bash(sh *)` -- 0 matches
- `Bash(source *)` -- 0 matches
- `Bash(python *)` -- 0 matches (verified no false positive from `python3` patterns)
- `Bash(python3 *)` -- 0 matches (verified no false positive from `python3 -m` patterns)
- `Bash(node *)` -- 0 matches

### Requirement 2: Add 4 replacement patterns to allow list
**Rating**: PASS

All 4 entries present in `claude/settings.json` with exactly 1 match each:
- `Bash(python3 -m claude.*)` -- line 103
- `Bash(python3 -m json.tool *)` -- line 104
- `Bash(uv run *)` -- line 105
- `Bash(uv sync *)` -- line 106

Placement is correct: positioned immediately before the remaining language runtime cluster (`npm`, `npx`, `pip3`, `deno`, `go`) at lines 107-111.

### Requirement 3: Rewrite /commit GPG check to avoid bash -c
**Rating**: PASS

`grep -c 'bash -c' skills/commit/SKILL.md` = 0. The skill now uses `test -f "$TMPDIR/gnupghome/S.gpg-agent"` (line 50) with exit code semantics: exit 0 means use GNUPGHOME prefix, exit 1 means commit without prefix. Functionally equivalent to the old `bash -c` approach and matches the allowed `Bash(test *)` pattern.

### Requirement 4: Rewrite /morning-review state update to avoid python3 -c
**Rating**: PASS

`grep -c 'python3 -c' skills/morning-review/SKILL.md` = 0. The skill now uses `jq` for all state manipulation:
- Phase read: `jq -r '.phase' <path>`
- Phase update: `jq '.phase = "complete"' <path> > <path>.tmp` followed by `mv`
- Pointer file update uses the same jq pattern

All `jq` invocations match the allowed `Bash(jq *)` pattern.

### Requirement 5: Rewrite /setup-merge symlink check to avoid python3 -c
**Rating**: PASS

`grep -c 'python3 -c' .claude/skills/setup-merge/SKILL.md` = 0. The skill now uses `test -L ~/.claude/settings.json` (line 15) which matches the allowed `Bash(test *)` pattern. Functionally equivalent to the old `pathlib.Path.is_symlink()` approach.

### Requirement 6: Valid JSON maintained
**Rating**: PASS

`python3 -m json.tool claude/settings.json` exits 0. The settings file is valid JSON with correct comma handling after the removal of 6 entries and addition of 4 entries.

### Edge Cases Verified

- **WorktreeCreate/Remove hooks**: Still use `bash -c` in their `command` fields (lines 332, 342 of settings.json). These are harness-executed hook commands, not Bash tool invocations -- correctly left unchanged per spec.
- **Non-requirements**: `Bash(awk *)`, `Bash(make *)`, `Bash(docker *)`, `Bash(claude *)` remain in the allow list -- correctly out of scope per spec.

## Stage 2: Code Quality

### Naming conventions
Consistent with project patterns. The 4 new allow list entries follow the existing `Bash(<command> *)` format. The `python3 -m claude.*` pattern uses glob syntax consistent with other entries.

### Error handling
Appropriate for the context:
- The commit skill's `test -f` check uses exit codes, matching how Claude interprets command results.
- The morning-review's jq approach writes to a `.tmp` file then moves it into place, preserving the atomic-write pattern (minus fsync, which the spec explicitly notes is acceptable for interactive sessions).
- The setup-merge's `test -L` is a drop-in replacement with identical semantics.

### Test coverage
All verification steps from the plan are satisfied:
1. Valid JSON -- confirmed
2. All 6 interpreter entries removed -- confirmed (0 matches each)
3. All 4 replacement entries added -- confirmed (1 match each)
4. No `bash -c` in commit skill -- confirmed
5. No `python3 -c` in morning-review skill -- confirmed
6. No `python3 -c` in setup-merge skill -- confirmed

### Pattern consistency
The replacements follow existing project conventions:
- `test -f` and `test -L` are idiomatic shell checks already used elsewhere in the codebase
- `jq` for JSON manipulation is consistent with other skills that process JSON
- Allow list entries are logically grouped with the runtime cluster

## Requirements Drift
**State**: none
**Findings**:
- None

The implementation directly implements the defense-in-depth mandate from `requirements/project.md`: "minimal allow list" and "keep global allows read-only and let write operations fall through to prompt." Removing the 6 broad interpreter entries and replacing them with 4 targeted patterns tightens the allow list without introducing behavior not already described in project requirements.

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
