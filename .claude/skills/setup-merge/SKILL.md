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

## Step 4: Symlink Resolution

Process all symlinks from the detect JSON before moving on to settings categories.

### Silent installs (new and update)

For every symlink entry where `status` is `new` or `update`, silently run:

```
ln {ln_flag} {source} {target}
```

using the `ln_flag`, `source`, and `target` values from the detect JSON entry. Do not prompt for these -- just execute them. Keep a count of how many were installed for the final summary.

### Conflict resolution (interactive)

Iterate the symlinks array from the detect JSON. For each entry where `status` is one of `conflict-broken`, `conflict-wrong-target`, or `conflict-file`, present the appropriate prompt. Process conflicts in the order they appear in the detect output.

#### conflict-broken

Display:

> Broken symlink at `{target}` (points to nothing). Replace with cortex-command symlink to `{source}`? [Y/n]

On Y: run `ln {ln_flag} {source} {target}`

On N: skip. Count as skipped for the summary.

#### conflict-wrong-target

First, read the current symlink target by running: `readlink {target}`

Then display:

> Symlink at `{target}` currently points to `{current_target}`. Repoint to `{source}`? [Y/n]

where `{current_target}` is the output of the `readlink` command.

On Y: run `ln {ln_flag} {source} {target}`

On N: skip. Count as skipped for the summary.

#### conflict-file

First, attempt to show a diff by running: `diff {target} {source}`

If `diff` is not available or fails, fall back to displaying the file size and inode info by running: `ls -li {target} {source}`

Then display:

> **Warning**: This file will be replaced by a symlink. This is destructive -- the original file will be lost. Replace `{target}` with symlink to `{source}`? [Y/n]

On Y: run `ln {ln_flag} {source} {target}`

On N: skip. Count as skipped for the summary.

<!-- Steps 5-6 (settings interactive flow, merge invocation) will be defined in Task 8 -->
