# Specification: apply-confirmed-safe-permission-tightening

## Problem Statement

`claude/settings.json` — the canonical template deployed as global Claude Code settings — contains overly broad allow-list entries (leading wildcards, unused macOS commands, fragile read-everything patterns), is missing deny entries for known sensitive paths and dangerous commands, and includes owner-specific MCP permissions that don't belong in a publicly shared template. These issues were identified and confirmed safe to fix by the permissions audit epic (#054, DR-1/DR-3 through DR-7). This ticket applies all confirmed-safe changes in a single pass. It also subsumes backlog #047 (deny list gap investigation), whose findings are a subset of the changes here.

## Requirements

### R1: Remove fragile/unused allow-list entries

Remove the following 10 entries from `permissions.allow` in `claude/settings.json`:

- `Read(~/**)` — fragile allowlist-everything pattern (DR-1)
- `Bash(* --version)` — leading wildcard matches any executable (DR-3)
- `Bash(* --help *)` — leading wildcard matches any executable (DR-3)
- `Bash(open -na *)` — macOS convenience, unused by any workflow
- `Bash(pbcopy *)` — macOS convenience, unused by any workflow
- `Bash(pbcopy)` — macOS convenience, unused by any workflow
- `Bash(env *)` — debugging only, unused at runtime
- `Bash(env)` — debugging only, unused at runtime
- `Bash(printenv *)` — debugging only, unused at runtime
- `Bash(printenv)` — debugging only, unused at runtime

**Acceptance**: `python3 -c "import json; d=json.load(open('claude/settings.json')); assert 'Read(~/**)' not in d['permissions']['allow']"` exits 0; `grep -c '* --version' claude/settings.json` = 0; `grep -c 'pbcopy' claude/settings.json` = 0; `grep -c 'printenv' claude/settings.json` = 0; `grep -c '"Bash(env' claude/settings.json` = 0; `grep -c 'open -na' claude/settings.json` = 0.

### R2: Move `git restore` to ask

Remove `Bash(git restore *)` from `permissions.allow` and add it to `permissions.ask`.

**Acceptance**: `python3 -c "import json; d=json.load(open('claude/settings.json')); assert 'Bash(git restore *)' in d['permissions']['ask']; assert 'Bash(git restore *)' not in d['permissions']['allow']"` exits 0.

### R3: Remove `skipDangerousModePermissionPrompt`

Remove the top-level `"skipDangerousModePermissionPrompt": true` key-value pair from `claude/settings.json`.

**Acceptance**: `grep -c 'skipDangerousModePermissionPrompt' claude/settings.json` = 0.

### R4: Add deny-list entries

Add the following 9 entries to `permissions.deny` in `claude/settings.json`:

- `Read(~/.config/gh/hosts.yml)` — GitHub CLI auth token (DR-6)
- `Read(**/*.p12)` — certificate/key bundles (DR-6)
- `WebFetch(domain:0.0.0.0)` — loopback alias (DR-6, subsumes #047)
- `Bash(crontab *)` — persistence mechanism (DR-6, subsumes #047)
- `Bash(eval *)` — arbitrary command execution (DR-6)
- `Bash(xargs *rm*)` — deletion via xargs (DR-6)
- `Bash(find * -delete*)` — bulk deletion via find (DR-6)
- `Bash(find * -exec rm*)` — bulk deletion via find (DR-6)
- `Bash(find * -exec shred*)` — bulk deletion via find (DR-6)

**Acceptance**: `python3 -c "import json; d=json.load(open('claude/settings.json')); deny=d['permissions']['deny']; assert 'Read(~/.config/gh/hosts.yml)' in deny; assert 'Read(**/*.p12)' in deny; assert 'WebFetch(domain:0.0.0.0)' in deny; assert 'Bash(crontab *)' in deny; assert 'Bash(eval *)' in deny; assert 'Bash(xargs *rm*)' in deny; assert 'Bash(find * -delete*)' in deny; assert 'Bash(find * -exec rm*)' in deny; assert 'Bash(find * -exec shred*)' in deny"` exits 0.

### R5: Remove owner-specific MCP entries from template

Remove the following 3 entries from `permissions.allow` in `claude/settings.json`:

- `mcp__perplexity__*`
- `mcp__jetbrains__*`
- `mcp__atlassian__*`

These are owner-specific MCP integrations that don't belong in a publicly shared template. They already persist in the owner's `~/.claude/settings.local.json` from prior hook syncs.

**Acceptance**: `grep -c 'mcp__perplexity' claude/settings.json` = 0; `grep -c 'mcp__jetbrains' claude/settings.json` = 0; `grep -c 'mcp__atlassian' claude/settings.json` = 0.

### R6: JSON validity

`claude/settings.json` must remain valid JSON after all changes.

**Acceptance**: `python3 -c "import json; json.load(open('claude/settings.json'))"` exits 0.

### R7: Archive backlog #047

Mark `backlog/047-investigate-gaps-in-settingsjson-deny-list.md` as complete, noting it was subsumed by #056.

**Acceptance**: `python3 -c "import yaml; f=open('backlog/047-investigate-gaps-in-settingsjson-deny-list.md').read(); fm=f.split('---')[1]; d=yaml.safe_load(fm); assert d['status']=='complete'"` exits 0.

## Non-Requirements

- **No hook modifications**: `cortex-sync-permissions.py` is not modified. Its union/dedup merge behavior is correct as-is — it will stop injecting removed entries on the next sync cycle.
- **No propagation to existing installs**: `/setup-merge` is additive-only and cannot remove entries. Propagation of removals to existing `~/.claude/settings.json` installs is out of scope. Users can run `just setup-force` to overwrite.
- **No cleanup of `~/.claude/settings.local.json`**: Entries synced to `settings.local.json` from previous sessions persist there. They are harmless (allow rules that are merely more permissive than needed) and will not be cleaned up.
- **No escape hatch changes**: `Bash(bash *)`, `Bash(sh *)`, `Bash(source *)`, `Bash(python *)`, `Bash(python3 *)`, `Bash(node *)` are NOT addressed by this ticket — they depend on the escape hatch spike (#055, DR-2).
- **No `settings.local.json` template**: MCP entries are removed from the template. They are not written to a `settings.local.json` template — the owner already has them from prior syncs, and new adopters won't have these MCP servers configured.

## Edge Cases

- **Comma-separated JSON trailing comma**: When removing the last entries from the allow list (MCP entries at lines 145–147), ensure the preceding entry's comma is correct. JSON does not permit trailing commas.
- **Duplicate entries**: Before adding deny entries, verify none already exist in the deny list to avoid duplicates.
- **Evaluation order for git restore**: `permissions.ask` is evaluated after `deny` but before `allow`. Moving `git restore` from allow to ask means it will prompt on every use. This is the intended behavior (DR-4) since `git restore` permanently discards uncommitted changes.
- **Deny pattern false positives**: Several R4 deny patterns use glob wildcards that may match legitimate operations. `Bash(xargs *rm*)` matches any xargs command where "rm" appears as a substring (e.g., `xargs grep "form"` matches because "form" contains "rm"). `Bash(find * -exec rm*)` and `Bash(find * -delete*)` block routine single-file cleanup operations (e.g., `find . -name "*.pyc" -exec rm {} \;`), not just bulk deletion. Unlike `ask` rules, `deny` rules provide no override mechanism — blocked commands require editing `settings.json` to unblock. These are accepted trade-offs: the patterns cast a wider net than strictly necessary to prevent evasion via flag reordering, at the cost of occasional false positives on safe operations.

## Changes to Existing Behavior

> **Note:** These changes describe the template defaults in `claude/settings.json`. For existing installs where entries persist in `~/.claude/settings.local.json` from prior hook syncs, behavioral changes may not take immediate effect. See Non-Requirements for scoping details.

- MODIFIED: `Read(~/**)` previously auto-allowed all home-directory reads → now prompts for out-of-repo reads (mitigated by `autoAllowBashIfSandboxed` for sandbox-managed environments; only affects the Read tool, not Bash)
- MODIFIED: `Bash(git restore *)` previously auto-allowed → now prompts via `ask` list
- MODIFIED: `Bash(* --version)` and `Bash(* --help *)` previously matched any executable → removed, specific version checks like `Bash(git --version)` remain allowed
- REMOVED: `skipDangerousModePermissionPrompt` → users see the standard prompt when entering dangerous mode
- REMOVED: `Bash(open -na *)`, `Bash(pbcopy *)`, `Bash(pbcopy)` → macOS convenience commands now prompt
- REMOVED: `Bash(env *)`, `Bash(env)`, `Bash(printenv *)`, `Bash(printenv)` → environment inspection commands now prompt
- REMOVED: `mcp__perplexity__*`, `mcp__jetbrains__*`, `mcp__atlassian__*` from template → owner retains in `settings.local.json`
- ADDED: 9 deny entries for sensitive paths and dangerous commands → these are blocked for direct invocations (deny takes precedence over allow in evaluation order)
- ADDED: `Bash(git restore *)` to ask list → prompts on destructive restore operations

## Technical Constraints

- **JSON validity**: `claude/settings.json` must be valid JSON at all times. Use `python3 -c "import json; json.load(open('claude/settings.json'))"` to verify.
- **Evaluation order**: Permission evaluation is deny → ask → allow (first match wins). Deny always takes precedence. An entry in `ask` will prompt even if a matching entry exists in `allow`, but only if it is not in `deny`.
- **`/setup-merge` is additive-only**: The merge skill detects entries absent from the user's settings and adds them. It cannot remove entries. New deny entries (R4) and ask entries (R2) will be propagated by `/setup-merge`. Removed allow entries (R1, R5) will not be auto-removed from existing installs.
- **Hook re-sync**: After `claude/settings.json` changes, the `cortex-sync-permissions.py` hook's hash will change, triggering a re-merge on next session start. The re-merge unions the new (smaller) global allow set into project-level `settings.local.json`. Previously synced entries persist in `settings.local.json` but are not re-injected from global.

## Open Decisions

(None — all decisions are resolved by the epic research DRs and confirmed in this spec.)
