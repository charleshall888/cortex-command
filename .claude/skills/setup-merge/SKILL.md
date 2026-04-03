---
name: setup-merge
description: This skill should be used when the user says "/setup-merge", "merge settings", "setup merge", "merge claude settings into this project", or wants to merge global Claude Code settings into a project's local configuration.
disable-model-invocation: true
---

# Setup Merge

## Step 1: Safety Guards

Run these checks first, before any other action. Halt immediately if either guard fails.

### Symlink guard

Run: `python3 -c "import pathlib; exit(0 if pathlib.Path('~/.claude/settings.json').expanduser().is_symlink() else 1)"`

If exit code is 0 (settings.json IS a symlink), halt immediately. Print:

> settings.json is managed as a symlink to the repo — use `just setup-force` to reinstall, or resolve conflicts manually.

Do not proceed. Do not attempt any write.

### Worktree guard

Run `git rev-parse --git-dir` and `git rev-parse --git-common-dir`. Compare the two outputs.

If they are different (this is a worktree, not the main checkout), halt immediately. Print:

> Run /setup-merge from the main cortex-command checkout, not from a worktree — symlinks created from a worktree path will break when the worktree is deleted.

Do not proceed.

### Sandbox warning

Check whether `$TMPDIR` starts with `/private/tmp/claude` or `/tmp/claude`.

If true, display this warning before proceeding (do NOT halt — continue after displaying):

> This session is sandboxed. The settings.json write may be blocked. If the write fails, run the merge helper directly from the terminal.

## Step 2: Detect

Run the detect helper to discover symlink inventory and settings.json diffs:

```
DETECT_FILE=$(python3 ${CLAUDE_SKILL_DIR}/scripts/merge_settings.py detect --repo-root $(git rev-parse --show-toplevel) --settings ~/.claude/settings.json)
```

`DETECT_FILE` now holds the path to the tempfile containing the full detect output as JSON. Store this path — it is needed by later steps.

Read the contents of `DETECT_FILE` (the JSON tempfile).

If the JSON contains `"error"` in the `settings` object, display the error and halt.

## Step 3: Summary Table

Present a summary table from the detect output before any Y/n prompts.

### Symlink summary

Count symlinks by status from the `symlinks` array. Display one row per status type that has a non-zero count:

| Category | Count |
|----------|-------|
| New (will install) | N |
| Already installed | N |
| Conflict: broken symlink | N |
| Conflict: wrong target | N |
| Conflict: existing file | N |

### Settings summary

Display one row per settings category. For each category, show the count of entries that would be added. If the category has no delta (empty absent list), mark it "already installed":

| Settings Category | Status |
|-------------------|--------|
| Required hooks | N to add / already installed |
| Optional hooks | N to review / already installed |
| Allow rules | N to add / already installed |
| Deny rules | N to add / already installed |
| Sandbox config | N to add / already installed |
| StatusLine | to add / already installed |
| Plugins | N to add / already installed |
| apiKeyHelper | to add / already installed / present in settings.local.json |

If ALL symlinks are status `new` or `update` AND all settings categories show "already installed", print "All cortex-command components already installed." and stop.

<!-- Steps 4-6 (symlink resolution, settings interactive flow, merge invocation) will be defined in Tasks 7-8 -->
