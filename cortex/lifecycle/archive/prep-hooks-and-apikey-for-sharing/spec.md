# Specification: prep-hooks-and-apikey-for-sharing

## Problem Statement

Two issues block sharing cortex-command with new users. First, hook files deployed to `~/.claude/hooks/` have generic names (`validate-commit.sh`, `cleanup-session.sh`, etc.) that silently overwrite any matching files in a user's existing global hooks directory. Second, `claude/settings.json` references `apiKeyHelper: ~/.claude/get-api-key.sh` — a script that does not exist in the repo and is never created by setup — causing a file-not-found error at Claude Code startup for subscription users. Both issues are self-contained, atomic changes. This ticket resolves them by (a) renaming all hook files to a `cortex-` prefix so deployment is collision-free, and (b) shipping a stub `get-api-key.sh` in the repo that delegates to a local override or returns empty for subscription billing.

## Requirements

1. **All 12 hook files renamed with `cortex-` prefix**: The following files are renamed (source path → new name):
   - `hooks/cleanup-session.sh` → `cortex-cleanup-session.sh`
   - `hooks/notify-remote.sh` → `cortex-notify-remote.sh`
   - `hooks/notify.sh` → `cortex-notify.sh`
   - `hooks/scan-lifecycle.sh` → `cortex-scan-lifecycle.sh`
   - `hooks/validate-commit.sh` → `cortex-validate-commit.sh`
   - `claude/hooks/permission-audit-log.sh` → `cortex-permission-audit-log.sh`
   - `claude/hooks/setup-gpg-sandbox-home.sh` → `cortex-setup-gpg-sandbox-home.sh`
   - `claude/hooks/skill-edit-advisor.sh` → `cortex-skill-edit-advisor.sh`
   - `claude/hooks/sync-permissions.py` → `cortex-sync-permissions.py`
   - `claude/hooks/tool-failure-tracker.sh` → `cortex-tool-failure-tracker.sh`
   - `claude/hooks/worktree-create.sh` → `cortex-worktree-create.sh`
   - `claude/hooks/worktree-remove.sh` → `cortex-worktree-remove.sh`
   
   **AC**: `git ls-files hooks/ claude/hooks/` shows no files without the `cortex-` prefix (except `.gitignore` or other non-hook files if any).

2. **All 11 hook path references in `claude/settings.json` updated atomically**: 11 of 14 hook-related entries in the `hooks` block must be updated to `cortex-*` names. The two `~/.claude/notify.sh` entries (lines 264, 281) remain unchanged — `notify.sh` deploys to `~/.claude/notify.sh` and this destination path does not change. The `apiKeyHelper` line is handled in Requirement 5.
   
   Updated entries: `sync-permissions.py`, `scan-lifecycle.sh`, `setup-gpg-sandbox-home.sh`, `cleanup-session.sh`, `validate-commit.sh`, `notify-remote.sh` (×2), `permission-audit-log.sh`, `tool-failure-tracker.sh`, `skill-edit-advisor.sh`. For the WorktreeCreate/WorktreeRemove entries (lines 317, 325), the inline bash strings reference `$CWD/claude/hooks/worktree-create.sh` and `worktree-remove.sh` respectively; these must be updated to `cortex-worktree-create.sh` / `cortex-worktree-remove.sh`.
   
   **AC**: Running `grep -r 'hooks/validate-commit\|hooks/cleanup-session\|hooks/scan-lifecycle\|hooks/notify-remote\|hooks/permission-audit-log\|hooks/tool-failure-tracker\|hooks/skill-edit-advisor\|hooks/sync-permissions\|hooks/setup-gpg-sandbox-home\|hooks/worktree-create\|hooks/worktree-remove' claude/settings.json` returns no matches.

3. **Justfile updated in three places**:
   - `deploy-hooks` recipe: the special-case check `[ "$name" = "notify.sh" ]` updated to `[ "$name" = "cortex-notify.sh" ]` — this preserves the behavior of deploying `cortex-notify.sh` to `~/.claude/notify.sh` (the destination remains unchanged).
   - `validate-commit` recipe: `bash hooks/validate-commit.sh` → `bash hooks/cortex-validate-commit.sh`.
   - `check-symlinks` recipe: all 8 hook path entries updated to `cortex-*` names; the stale `~/.claude/hooks/setup-github-pat.sh` entry (file does not exist in the repo) is removed.
   
   **AC**: `just validate-commit msg="Test: valid message"` runs without "No such file" errors. `just check-symlinks` after deploying reports no symlink errors for hook entries.

4. **Docs, tests, and skills updated**: All references to old hook filenames in the following files are updated to the new `cortex-*` names:
   - `docs/agentic-layer.md` — 11 structured refs (lines 214–226) + ~5 prose refs (lines 270–275); also any bare hook-name references elsewhere in the file
   - `docs/setup.md` — 4 refs including manual `ln -sf` examples (lines 199–200, 292–293)
   - `docs/sdk.md` — 3 refs to worktree hooks (lines 96, 103, 111)
   - `tests/test_skill_behavior.sh` — line 17
   - `tests/test_hook_commit.sh` — line 16
   - `tests/test_hooks.sh` — lines 10, 97, 185, 204, 301, 330
   - `tests/test_tool_failure_tracker.sh` — line 19
   - `tests/lifecycle_phase.py` — line 5
   - `skills/lifecycle/SKILL.md` — line 373
   - `skills/lifecycle/references/implement.md` — line 56
   - `claude/dashboard/alerts.py` — line 112: `notify_remote_sh = root / "hooks" / "notify-remote.sh"` (live runtime path — must update to `cortex-notify-remote.sh`)
   - `claude/overnight/runner.sh` — line 794 comment
   - `claude/overnight/report.py` — line 204 docstring
   - `claude/statusline.sh` — line 377 comment
   
   **AC**: `grep -rn 'validate-commit\.sh\|cleanup-session\.sh\|scan-lifecycle\.sh\|notify-remote\.sh\|permission-audit-log\.sh\|tool-failure-tracker\.sh\|skill-edit-advisor\.sh\|sync-permissions\.py\|setup-gpg-sandbox-home\.sh\|worktree-create\.sh\|worktree-remove\.sh' docs/ tests/ skills/ claude/` returns no matches (excluding `claude/settings.json` which is covered by Req 2's AC, and `claude/hooks/` which is covered by Req 1's AC).

5. **`claude/get-api-key.sh` stub shipped in repo**: A new stub script is created at `claude/get-api-key.sh` with the following behavior: if `~/.claude/get-api-key-local.sh` exists, exec it with all arguments; otherwise, exit 0 with no output (empty return). The file must be executable (`chmod +x`). The existing `apiKeyHelper: ~/.claude/get-api-key.sh` line in `claude/settings.json` remains unchanged — it already points to the correct destination.
   
   **AC**: `ls -la claude/get-api-key.sh` exists and is executable. Running `output=$(bash claude/get-api-key.sh); echo "exit=$? output='$output'"` with no local override prints `exit=0 output=''`.

6. **deploy-config wires up the stub symlink**: The `deploy-config` recipe is updated to symlink `claude/get-api-key.sh` to `~/.claude/get-api-key.sh`, consistent with how `settings.json`, `CLAUDE.md`, and `statusline.sh` are already handled. The symlink step must include the regular-file check (same pattern as the other targets in the recipe).
   
   **AC**: After `just deploy-config`, `ls -la ~/.claude/get-api-key.sh` shows a symlink pointing to the repo's `claude/get-api-key.sh`. The symlink is functional.

7. **Atomic single commit**: All renames, reference updates, stub creation, and deploy-config change are delivered in a single commit. No intermediate state exists where a file has been renamed but `settings.json` still references the old name (or vice versa).
   
   **AC**: A single commit contains all changes. No partial-state commits.

8. **Hooks fire correctly after immediate re-deploy**: After the primary user runs `just deploy-hooks` immediately following `git pull`, all hooks execute without "No such file" errors. **Important**: `just deploy-hooks` must be run before starting any new Claude Code session after the pull (see Edge Cases — `~/.claude/notify.sh` transition window).
   
   **AC**: `just test` passes after `just deploy-hooks` completes.

9. **Interactive Claude Code startup verification (blocking pre-merge)**: With the stub in place and `apiKeyHelper: ~/.claude/get-api-key.sh` in settings.json, starting a new Claude Code session must not produce any startup error (file-not-found or otherwise) related to `apiKeyHelper`. Must be manually verified by the primary user before the PR is merged.
   
   **AC**: Primary user opens a new Claude Code session after `just deploy-config` and confirms no error, warning, or startup failure related to `get-api-key.sh` or `apiKeyHelper` appears.
   
   **Fallback if verification fails**: If Claude Code produces any startup error when `apiKeyHelper` returns empty, fall back to removing `apiKeyHelper` from `claude/settings.json` entirely (the stub and deploy-config symlink steps become unnecessary). Subscription users: no change needed. API-key users: must configure their own `apiKeyHelper` in `~/.claude/settings.local.json` for interactive use; overnight runs use `ANTHROPIC_API_KEY` env var (runner.sh does not read `settings.local.json`).

## Non-Requirements

- The deployment destination for `notify.sh` (`~/.claude/notify.sh`) does not change — only the source filename changes.
- This ticket does not create a `/setup-merge` skill, collision detection in `just setup`, or `Agents.md` split — those are adjacent tickets in the shareability epic.
- `research/` and `lifecycle/` historical artifacts are not updated — they are not runtime paths.
- The `docs/sdk.md:133` broken `claude/get-api-key.sh` reference is fixed implicitly when the stub is created (the reference becomes valid). No separate doc fix is required.
- This ticket does not add `setup-github-pat.sh` to the repo — only the stale `check-symlinks` reference to it is removed.

## Edge Cases

- **`notify.sh` deploy-hooks special case**: After renaming `hooks/notify.sh` → `hooks/cortex-notify.sh`, the `deploy-hooks` recipe's special case `[ "$name" = "notify.sh" ]` no longer matches. If the check is not updated to `cortex-notify.sh`, the file gets deployed to `~/.claude/hooks/cortex-notify.sh` instead of `~/.claude/notify.sh`, silently breaking all Notification and Stop hooks. Requirement 3 addresses this.

- **`~/.claude/notify.sh` transition window (active breakage risk)**: Unlike the `~/.claude/hooks/` dangling symlinks (which are harmless because their settings.json registrations are also removed), `~/.claude/notify.sh` remains registered in settings.json at all times. After `git pull` renames `hooks/notify.sh` to `hooks/cortex-notify.sh`, the existing symlink `~/.claude/notify.sh → hooks/notify.sh` becomes dangling while `settings.json` still registers this path for Notification and Stop events. Every Notification and Stop hook invocation in this window fires against a broken path. **Migration requirement**: the primary user must run `just deploy-hooks` before starting any new Claude Code session after pulling.

- **settings.json WorktreeCreate/WorktreeRemove inline bash**: Lines 317 and 325 use inline bash strings that reference `$CWD/claude/hooks/worktree-create.sh` and `worktree-remove.sh`. These are not simple path substitutions — they are embedded in a single-quoted bash command. The rename must update the filename inside the bash string, not the outer JSON.

- **stale `setup-github-pat.sh` in check-symlinks**: The file does not exist in the repo. Removing the entry from `check-symlinks` is safe — there are no other recipes that depend on it. Keeping it would cause `just check-symlinks` to report a false-negative failure after deploy.

- **`~/.claude/hooks/` dangling old symlinks**: After re-deploy, the old symlinks (`~/.claude/hooks/validate-commit.sh`, etc.) are left as dangling pointers — not deleted by `deploy-hooks`. These are safe: they don't match any hook event registration in settings.json after the settings.json update. The user may delete them manually or leave them.

- **`apiKeyHelper` stub when local override exists**: If `~/.claude/get-api-key-local.sh` exists, the stub execs it. If that script exits non-zero or outputs nothing, runner.sh falls back to subscription billing (existing behavior). The stub does not need to handle errors from the local override — it delegates fully.

- **deploy-config re-run when symlink already exists**: The new `ln -sf` for `get-api-key.sh` in deploy-config is idempotent (symlinks are replaced silently by `ln -sf`). The regular-file guard (same pattern as existing targets) prevents overwriting a user's custom non-symlink script without prompting.

## Technical Constraints

- Changes must be in a single commit — partial renames create a broken intermediate state where settings.json references non-existent hook paths.
- `deploy-hooks` uses glob patterns (`hooks/*.sh`, `claude/hooks/*`), so it picks up renamed files automatically. Only the `notify.sh` special-case check needs manual update.
- The `claude/settings.json` file is valid JSON — edits must preserve JSON validity. The inline bash strings in WorktreeCreate/WorktreeRemove entries are embedded in JSON string values; special characters must remain properly escaped.
- `claude/get-api-key.sh` must be executable at commit time (`chmod +x` before committing, or set via `git update-index --chmod=+x`).
- runner.sh reads `apiKeyHelper` from `~/.claude/settings.json` only. The `settings.json` `apiKeyHelper` line must remain pointing to `~/.claude/get-api-key.sh` (not `settings.local.json`).
- Tests reference hook paths via `$REPO_ROOT/hooks/<name>` patterns. Updating the path strings in test files is sufficient — no test logic changes are needed.
