# Research: prep-hooks-and-apikey-for-sharing

## Epic Reference

Epic research at `research/shareable-install/research.md`. This ticket is one of the prerequisite steps for the shareability epic — specifically the hook renaming (DR-3) and apiKeyHelper stub (Final Decision §6) components. The `/setup-merge` skill, `just setup` collision detection, and `Agents.md` split are adjacent tickets in the same epic.

## Codebase Analysis

### Hook files: two directories, 12 files

There are two hook directories, with different deploy targets:

**`hooks/` → deploys to `~/.claude/hooks/` (except notify.sh)**
- `cleanup-session.sh`
- `notify-remote.sh`
- `notify.sh` ← special: deploys to `~/.claude/notify.sh`, not `~/.claude/hooks/`
- `scan-lifecycle.sh`
- `validate-commit.sh`

**`claude/hooks/` → deploys to `~/.claude/hooks/`**
- `permission-audit-log.sh`
- `setup-gpg-sandbox-home.sh`
- `skill-edit-advisor.sh`
- `sync-permissions.py`
- `tool-failure-tracker.sh`
- `worktree-create.sh`
- `worktree-remove.sh`

All 12 files need renaming to `cortex-<name>` (e.g., `cortex-validate-commit.sh`).

### settings.json hook references (14 path entries)

All `~/.claude/hooks/` references will need updating. `notify.sh` is a special case — it deploys to `~/.claude/notify.sh` and settings.json references that exact path; the renamed source file (`cortex-notify.sh`) changes the source but deploy-hooks hardcodes the destination as `~/.claude/notify.sh`, so settings.json references to `~/.claude/notify.sh` stay unchanged.

| Line | Event | Current command (extract) | Update required? |
|------|-------|--------------------------|-----------------|
| 219 | SessionStart | `~/.claude/hooks/sync-permissions.py` | → `cortex-sync-permissions.py` |
| 224 | SessionStart | `~/.claude/hooks/scan-lifecycle.sh` | → `cortex-scan-lifecycle.sh` |
| 229 | SessionStart | `~/.claude/hooks/setup-gpg-sandbox-home.sh` | → `cortex-setup-gpg-sandbox-home.sh` |
| 240 | SessionEnd | `~/.claude/hooks/cleanup-session.sh` | → `cortex-cleanup-session.sh` |
| 251 | PreToolUse(Bash) | `~/.claude/hooks/validate-commit.sh` | → `cortex-validate-commit.sh` |
| 264 | Notification | `~/.claude/notify.sh permission` | **unchanged** (deploy destination stays `~/.claude/notify.sh`) |
| 268 | Notification | `~/.claude/hooks/notify-remote.sh permission` | → `cortex-notify-remote.sh` |
| 272 | Notification | `~/.claude/hooks/permission-audit-log.sh` | → `cortex-permission-audit-log.sh` |
| 281 | Stop | `~/.claude/notify.sh complete` | **unchanged** |
| 285 | Stop | `~/.claude/hooks/notify-remote.sh complete` | → `cortex-notify-remote.sh` |
| 293 | PostToolUse(Bash) | `~/.claude/hooks/tool-failure-tracker.sh` | → `cortex-tool-failure-tracker.sh` |
| 302 | PostToolUse(Write\|Edit) | `~/.claude/hooks/skill-edit-advisor.sh` | → `cortex-skill-edit-advisor.sh` |
| 317 | WorktreeCreate | inline bash: `$CWD/claude/hooks/worktree-create.sh` | → `cortex-worktree-create.sh` |
| 325 | WorktreeRemove | inline bash: `$CWD/claude/hooks/worktree-remove.sh` | → `cortex-worktree-remove.sh` |

11 of 14 entries need updating. The two `~/.claude/notify.sh` references and the `apiKeyHelper` line (line 3) are unchanged.

### Justfile: 3 update points

**`deploy-hooks` recipe (lines 62–82)**: Uses glob (`hooks/*.sh`, `claude/hooks/*`) — no hardcoded filenames. However, it has a special case: `[ "$name" = "notify.sh" ]` to deploy `notify.sh` to `~/.claude/notify.sh` instead of `~/.claude/hooks/`. After renaming to `cortex-notify.sh`, this check must be updated to `[ "$name" = "cortex-notify.sh" ]`.

**`validate-commit` recipe (line 420)**: `echo "{{ msg }}" | bash hooks/validate-commit.sh` → must update to `hooks/cortex-validate-commit.sh`.

**`check-symlinks` recipe (lines 448–455)**: 8 hardcoded hook paths. All need updating to `cortex-*` names. Notable: includes `~/.claude/hooks/setup-github-pat.sh` — this file does not exist in `hooks/` or `claude/hooks/` (stale reference, should be removed).

### Docs: references in 3 files

**`docs/agentic-layer.md`**: 11 hook names in a structured list (lines 214–226) + ~5 prose references (lines 270–275). All need updating.

**`docs/setup.md`**: 4 references including two manual `ln -sf` examples with hardcoded old names (lines 199–200, 292–293).

**`docs/sdk.md`**: 3 references to worktree hooks (lines 96, 103, 111) + line 133 has a broken `claude/get-api-key.sh` reference (the stub doesn't exist yet — will be created by this ticket).

### Tests: 4 files with references

| File | Lines | Hook referenced |
|------|-------|----------------|
| `tests/test_skill_behavior.sh` | 17 | `hooks/validate-commit.sh` |
| `tests/test_hook_commit.sh` | 16 | `hooks/validate-commit.sh` |
| `tests/test_hooks.sh` | 10, 97, 185, 204, 301, 330 | cleanup-session, scan-lifecycle, setup-gpg-sandbox-home, worktree-create, worktree-remove, sync-permissions |
| `tests/test_tool_failure_tracker.sh` | 19 | `claude/hooks/tool-failure-tracker.sh` |

All test references must be updated; tests derive hook paths from `$REPO_ROOT/hooks/<name>` or `$REPO_ROOT/claude/hooks/<name>` patterns.

### runner.sh apiKeyHelper handling (lines 44–65)

`runner.sh` reads `apiKeyHelper` from `~/.claude/settings.json` only (not `settings.local.json`). If the helper path doesn't exist or returns non-zero, the Python block exits silently and `_API_KEY` is empty. If empty, runner.sh emits `"Warning: apiKeyHelper returned empty — overnight subagents will use subscription billing"` to stderr and continues. This confirms a stub that exits 0 with no output will not break overnight runs — subscription billing fallback applies.

### deploy-config recipe: no apiKeyHelper symlink exists

The current `deploy-config` recipe (lines 85–116) symlinks `settings.json`, `CLAUDE.md`, and `statusline.sh`. There is no symlink step for `get-api-key.sh`. Adding `ln -sf "$(pwd)/claude/get-api-key.sh" "$HOME/.claude/get-api-key.sh"` here is the natural location — consistent with how other config files are deployed.

### apiKeyHelper stub design

From research/shareable-install/research.md Final Decisions (line 251):
- Ship `claude/get-api-key.sh` in the repo
- Stub calls `~/.claude/get-api-key-local.sh` if present, returns empty otherwise
- `apiKeyHelper` in `settings.json` already points to `~/.claude/get-api-key.sh` (line 3) — no change needed there

### Scope note: research artifacts, skills, lifecycle files

References in `research/`, `lifecycle/`, and `skills/` directories are historical or documentation artifacts (not live runtime paths). The skill files (`skills/lifecycle/SKILL.md:373`, `skills/lifecycle/references/implement.md:56`) reference `worktree-create.sh` in prose — these are documentation, not runtime hook invocations. These do NOT need updating for the hook rename to work correctly; updating them is optional documentation cleanup.

Research files (`research/shareable-install/research.md`, `research/session-window-naming/research.md`, `research/claude-code-sdk-usage/research.md`) contain old hook names as historical references. Not in scope.

## Open Questions

- **`setup-github-pat.sh` stale reference**: `check-symlinks` recipe references `~/.claude/hooks/setup-github-pat.sh` but this file does not exist in `hooks/` or `claude/hooks/`. This is a pre-existing stale reference. Resolution: remove it from `check-symlinks` as part of this ticket (mechanical cleanup). Deferred: verify no other recipe depends on it before removing.
- **Claude Code interactive startup behavior with empty apiKeyHelper**: The stub returns empty (exit 0, no output). runner.sh handles this correctly (subscription billing fallback). The research doc flags: "Verification required: confirm Claude Code interactive startup handles an `apiKeyHelper` that returns empty without error." This is an interactive-Claude-Code-specific verification that cannot be automated — it requires starting a new Claude session with the stub in place and confirming no error appears. The acceptance criterion "(verified)" means this must be manually confirmed as part of implementation sign-off before the commit is considered complete.
