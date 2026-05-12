# Research: apply-confirmed-safe-permission-tightening

## Epic Reference

Background context from [research/permissions-audit/research.md](../../research/permissions-audit/research.md) — the parent epic (#054) that identified these changes as confirmed-safe (DR-1, DR-3 through DR-7). This ticket applies only the subset with no dependency on the escape hatch spike (#055).

## Codebase Analysis

### Target File: `claude/settings.json`

The canonical source for global Claude Code settings, deployed to `~/.claude/settings.json`. Not a symlink — copied on first install, updated via `/setup-merge` or `just setup-force`.

Key structure for this feature:

- **`permissions.allow`** (lines 12–148, 136 entries): Contains all entries to be removed:
  - `Read(~/**)` — broad home-directory read access
  - `Bash(* --version)`, `Bash(* --help *)` — leading wildcard matches any executable
  - `Bash(open -na *)` — macOS convenience
  - `Bash(pbcopy *)`, `Bash(pbcopy)` — macOS convenience
  - `Bash(env *)`, `Bash(env)` — debugging only
  - `Bash(printenv *)`, `Bash(printenv)` — debugging only
  - `mcp__perplexity__*`, `mcp__jetbrains__*`, `mcp__atlassian__*` (lines 145–147) — owner-specific MCP

- **`permissions.deny`** (lines 149–205, 56 entries): Target for new deny entries.

- **`permissions.ask`** (line 207): Currently empty array `[]`. Target for `git restore` move.

- **`skipDangerousModePermissionPrompt`** (line 371): Top-level key (not inside `permissions`). To be removed.

### Deployment Pipeline

Two deployment mechanisms exist:

1. **`just setup` → `deploy-config`**: Copies `claude/settings.json` to `~/.claude/settings.json` only on first install. Subsequent runs print `[ok]` and suggest `/setup-merge`. Does NOT overwrite existing settings.

2. **`just setup-force`**: Direct `cp` overwrite of `~/.claude/settings.json`. Destructive — replaces the user's customizations.

3. **`/setup-merge` skill** (`skills/setup-merge/`): Additive-only merge — detects entries in `claude/settings.json` absent from `~/.claude/settings.json` and adds them. **Cannot remove entries or propagate tightening.** This means:
   - New deny entries (DR-6) will be propagated by `/setup-merge` on next run
   - Removed allow entries (DR-1, DR-3) will NOT be removed from existing user installations
   - The `ask` list addition (DR-4) will be propagated
   - This is acceptable — the feature's scope is editing the canonical source; propagation to existing installs is a separate concern

### Hook Interaction: `cortex-sync-permissions.py`

SessionStart hook that merges global permissions into project-level `settings.local.json`:

- **Merge direction**: `~/.claude/settings.json` (global) → `<project>/.claude/settings.local.json` (local)
- **Merge strategy**: Union/dedup — adds entries from global into local, never removes
- **Hash-skip**: Stores `_globalPermissionsHash` in local `settings.local.json`. Re-merges only when global changes
- **Key finding**: The hook will NOT re-add entries removed from `settings.json`, but entries already synced into `~/.claude/settings.local.json` from previous sessions persist there. This is a cosmetic issue — the entries in `settings.local.json` are still active but harmless (they're allow rules that are merely more permissive than needed).

**Project-level impact**: The repo's `.claude/settings.local.json` has no `permissions` key (only `sandbox` config), so the hook skips it for this project. No interaction risk.

**Global-level impact**: `~/.claude/settings.local.json` (204 lines) already has MCP entries and `git restore *` synced in from previous sessions. After this change, they'll persist in `settings.local.json` but won't be re-injected from global. For the owner, this means the MCP entries will naturally remain available (they persist in settings.local.json from previous syncs).

### Backlog 047

File: `backlog/047-investigate-gaps-in-settingsjson-deny-list.md`
Status: `backlog` (never started)
Content: Investigation-only ticket listing 6 items — all of which are now addressed by this ticket's DR-6 deny additions. The ticket body explicitly states "Subsumes backlog 047."

Archival approach: Set `status: complete` with a note that it was subsumed by #056.

### MCP Migration to `settings.local.json`

The MCP entries (`mcp__perplexity__*`, `mcp__jetbrains__*`, `mcp__atlassian__*`) need to move from `claude/settings.json` to the owner's `~/.claude/settings.local.json`. Since `~/.claude/settings.local.json` already has these entries (synced by the hook), the migration is:

1. Remove from `claude/settings.json` (the canonical template)
2. No action needed on `~/.claude/settings.local.json` — entries already present

For new adopters, MCP entries won't be in the template (correct behavior — they're owner-specific). The owner's local file retains them from previous syncs.

### Files Affected

| File | Change Type |
|------|-------------|
| `claude/settings.json` | Remove allow entries, add deny entries, add ask entry, remove setting |
| `backlog/047-*.md` | Archive (status: complete, subsumed note) |

No changes needed to:
- `cortex-sync-permissions.py` — merge behavior is correct as-is
- `/setup-merge` — additive-only is acceptable for this scope
- `.claude/settings.local.json` (project) — no permissions key, no interaction
- `~/.claude/settings.local.json` — entries persist naturally, no cleanup needed

## Open Questions

- Should `Bash(git restore *)` be removed from the allow list entirely (since it's moving to ask), or should it remain in allow as well? (Answer: remove from allow and add to ask — the ask list takes precedence per deny→ask→allow evaluation order, but having it in both would be confusing. Remove from allow, add to ask.)
