---
name: setup-merge
description: This skill should be used when the user says "/setup-merge", "merge settings", "setup merge", "merge claude settings into this project", or wants to merge global Claude Code settings into a project's local configuration.
disable-model-invocation: true
---

# Setup Merge

## Step 1: Safety Guards

Run these checks first, before any other action. Halt immediately if either guard fails.

### Symlink guard

Run: `test -L ~/.claude/settings.json`

If exit code is 0 (settings.json IS a symlink), convert it before proceeding.

Display: "Converting settings.json from symlink to regular file for merge compatibility."

Run: `python3 ${CLAUDE_SKILL_DIR}/scripts/merge_settings.py migrate --settings ~/.claude/settings.json`

Parse the JSON output. If `"ok": true`, continue to the next guard. If `"ok": false`, display the error and halt.

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

First, check if the target is a directory by running: `test -d {target}`

If it is a directory (exit code 0), display:

> **Warning**: `{target}` is a real directory (not a symlink). It must be removed before the symlink can be created. Replace `{target}` with symlink to `{source}`? [Y/n]

On Y: run `rm -r {target}` (not `rm -rf` — the deny rules block it, and we want errors to surface). If `rm -r` fails, display the error and skip this entry — do not proceed to `ln`. If `rm -r` succeeds, run `ln {ln_flag} {source} {target}`.

On N: skip. Count as skipped for the summary.

If it is NOT a directory, attempt to show a diff by running: `diff {target} {source}`

If `diff` is not available or fails, fall back to displaying the file size and inode info by running: `ls -li {target} {source}`

Then display:

> **Warning**: This file will be replaced by a symlink. This is destructive -- the original file will be lost. Replace `{target}` with symlink to `{source}`? [Y/n]

On Y: run `ln {ln_flag} {source} {target}`

On N: skip. Count as skipped for the summary.

## Step 5: Settings Interactive Flow

Process the settings categories from the detect JSON. For each category, either merge unconditionally (required hooks), prompt Y/n (optional hooks and per-category settings), or skip ("already installed").

### 5a. Required hooks

Read `settings.hooks_required` from the detect JSON.

If `settings.hooks_required.absent` is empty, display:

> Required hooks: already installed

Otherwise, display the list of absent required hooks:

> **Required hooks** — the following hooks will be merged (no prompt):

List each hook from the `absent` array showing its `event_type` and `command` field.

> Note: `cortex-sync-permissions.py` writes `_globalPermissionsHash` into `settings.local.json` at every SessionStart (workaround for upstream bug #17017).

These hooks are merged unconditionally -- do not prompt Y/n.

### 5b. Optional hooks

Read `settings.hooks_optional` from the detect JSON.

If `settings.hooks_optional.absent` is empty, display:

> Optional hooks: already installed

Otherwise, prompt for each absent optional hook individually. Use the descriptions below (from spec req 17) verbatim. Track which hook script filenames the user approves.

For each absent optional hook, extract the script filename from the `command` field and display the matching prompt:

**cortex-notify.sh** (may appear as `notify.sh` in the command field):

> `cortex-notify.sh` — Sends desktop notifications when Claude needs attention or completes. Requires cortex-notify infrastructure. Install? [Y/n]

On Y: add the script filename to the approved optional hooks list.
On N: skip. Count as skipped for the summary.

Build a JSON array of approved optional hook canonical filenames (e.g., `["cortex-notify.sh"]`). Store this as `APPROVED_OPTIONAL_HOOKS`.

### 5c. Per-category settings

For each of the 6 settings categories, check the detect JSON for a non-empty delta. If the delta is empty, display "already installed" and skip. Otherwise, show the delta and prompt Y/n.

Track approval as a boolean per category: `APPROVE_ALLOW`, `APPROVE_DENY`, `APPROVE_SANDBOX`, `APPROVE_STATUSLINE`, `APPROVE_PLUGINS`, `APPROVE_APIKEY`.

Initialize all to `false`.

#### Deny rules

Read `settings.deny.absent` from the detect JSON.

If the absent list is empty, display:

> Deny rules: already installed

Otherwise, display each entry from the absent list, then prompt:

> **Deny rules** — these safety rules will block dangerous commands (sudo, rm -rf, force push, reading secrets):
>
> (list each absent deny entry)
>
> Add these deny rules? [Y/n]

On Y: set `APPROVE_DENY=true`. On N: set `APPROVE_DENY=false`.

#### Allow rules

Read `settings.allow.absent` from the detect JSON.

If the absent list is empty, display:

> Allow rules: already installed

Otherwise, display each entry from the absent list, then prompt:

> **Allow rules** — these entries are additive and won't remove your existing rules:
>
> (list each absent allow entry)
>
> Add these allow rules? [Y/n]

On Y: set `APPROVE_ALLOW=true`. On N: set `APPROVE_ALLOW=false`.

#### Sandbox config

Read `settings.sandbox.absent` from the detect JSON.

If the absent dict is empty, display:

> Sandbox config: already installed

Otherwise, display the delta entries (allowedDomains, allowUnixSockets, excludedCommands, autoAllowBashIfSandboxed) and their values, then prompt:

> **Sandbox config** — network domains, unix sockets, excluded commands, and auto-allow settings:
>
> (list each absent sandbox entry with its current value)
>
> Add these sandbox settings? [Y/n]

On Y: set `APPROVE_SANDBOX=true`. On N: set `APPROVE_SANDBOX=false`.

#### StatusLine

Read `settings.statusLine.absent` from the detect JSON.

If the absent value is null/None, display:

> StatusLine: already installed

Otherwise, display the cortex-command statusLine config and prompt:

> **StatusLine** — cortex-command status bar config. Requires `~/.claude/statusline.sh` to be installed (handled by symlink section above):
>
> (show the statusLine object)
>
> Add statusLine config? [Y/n]

On Y: set `APPROVE_STATUSLINE=true`. On N: set `APPROVE_STATUSLINE=false`.

#### Plugins

Read `settings.plugins.absent` from the detect JSON.

If the absent dict is empty, display:

> Plugins: already installed

Otherwise, display each plugin key and value from the absent dict, then prompt:

> **Plugins** — context7 and claude-md-management plugin entries (merged individually; won't overwrite other plugins or enableAllProjectMcpServers):
>
> (list each absent plugin entry)
>
> Add these plugins? [Y/n]

On Y: set `APPROVE_PLUGINS=true`. On N: set `APPROVE_PLUGINS=false`.

#### apiKeyHelper

Read `settings.apiKeyHelper` from the detect JSON.

Check the `status` field:

- If `"present"` or `"not_in_repo"`: display:

  > apiKeyHelper: already installed

- If `"present_in_local"`: display:

  > apiKeyHelper: already configured in settings.local.json (already installed)

- If `"absent"`: first check if `~/.claude/get-api-key.sh` exists by running:

  ```
  test -f ~/.claude/get-api-key.sh
  ```

  If the file does NOT exist (exit code non-zero), display:

  > apiKeyHelper: skipped — `~/.claude/get-api-key.sh` stub not deployed. Run `just setup` to deploy the stub first.

  Do NOT prompt. Set `APPROVE_APIKEY=false`.

  If the file exists, display the stub path and prompt:

  > **apiKeyHelper** — delegates to `~/.claude/get-api-key.sh`. Returns empty for subscription users (no effect), or delegates to `~/.claude/get-api-key-local.sh` for API key users:
  >
  > (show the apiKeyHelper value from detect JSON)
  >
  > Add apiKeyHelper? [Y/n]

  On Y: set `APPROVE_APIKEY=true`. On N: set `APPROVE_APIKEY=false`.

### 5d. Check if anything to merge

If ALL of the following are true:
- `settings.hooks_required.absent` is empty (no required hooks to add)
- `APPROVED_OPTIONAL_HOOKS` is empty (no optional hooks approved)
- All 6 `APPROVE_*` flags are false

Then there is nothing to merge into settings.json. Display:

> No settings changes to apply.

Skip the merge invocation and proceed directly to Step 6 (Summary Report).

### 5e. Merge Invocation

Run the merge helper with all collected approvals:

```
python3 ${CLAUDE_SKILL_DIR}/scripts/merge_settings.py merge \
  --detect-file "$DETECT_FILE" \
  --optional-hooks '<APPROVED_OPTIONAL_HOOKS as JSON array string>' \
  --approve-allow <true|false> \
  --approve-deny <true|false> \
  --approve-sandbox <true|false> \
  --approve-statusline <true|false> \
  --approve-plugins <true|false> \
  --approve-apikey <true|false>
```

Where:
- `$DETECT_FILE` is the tempfile path captured in Step 2
- `APPROVED_OPTIONAL_HOOKS` is the JSON array of approved optional hook canonical filenames (e.g., `'["cortex-notify.sh"]'`)
- Each `--approve-*` flag is the literal string `true` or `false` based on the corresponding `APPROVE_*` variable

### Parse merge output

The merge helper prints a JSON object to stdout. Parse it:

**On `{"ok": true}`**: the merge succeeded. Read `contradictions` and `merged` arrays from the result. Store both for the summary report.

**On `{"error": "mtime_changed"}`**: display:

> settings.json was modified during this session -- re-run /setup-merge to merge against the current version.

Halt. Do not proceed to the summary.

**On `{"error": "json_invalid"}`**: display:

> Merge produced invalid JSON. This is a bug -- please report it.

Halt. Do not proceed to the summary.

**On any other error**: display the error message and halt.

## Step 6: Summary Report

After all steps complete, display a summary report covering both symlinks and settings.

### Symlinks

Count from Step 4:
- Symlinks installed (new + update + conflict-resolved)
- Symlinks skipped (user declined conflict resolution)

Display:

> **Symlinks**: N installed, N skipped

### Settings

Count from Step 5 and the merge result:
- Categories merged (from the merge result `merged` array length)
- Categories skipped by user (count of categories where user said N, excluding "already installed" categories)

Display:

> **Settings**: N categories merged, N categories skipped

### Contradictions

If the merge result `contradictions` array is non-empty, display all contradictions grouped by direction:

> **Contradictions** (resolve manually):

For each forward contradiction (allow blocked by existing deny):

> - Existing deny rule `{deny}` blocks cortex-command allow entry `{allow}`

For each reverse contradiction (deny blocked by existing allow):

> - Proposed deny rule `{deny}` blocks existing allow entry `{allow}`

### Skipped regular-file conflicts

If any symlink conflicts with status `conflict-file` were skipped (user said N), list them:

> **Skipped file conflicts** (original files preserved):
>
> - `{target}` (would symlink to `{source}`)
