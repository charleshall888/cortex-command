# Specification: Build /setup-merge local skill

> Epic context: `research/shareable-install/research.md` covers the full shareable-install initiative. This spec is scoped to the `/setup-merge` skill only — the conflict resolution path that runs after `just setup`'s additive mode prints a pending list.

## Problem Statement

After `just setup` runs in additive mode, any symlink target that already exists (as a regular file, a symlink to another repo, or a broken symlink) is skipped and added to a pending list. There is currently no automated path to resolve those conflicts: users must manually create symlinks, run `just setup-force` (destructive), or remain in a partially-installed state. `/setup-merge` is a local project skill — available only when Claude is opened in the cortex-command directory — that resolves all pending conflicts in a single interactive session. It handles two conflict classes: (1) symlink targets that are blocked by an existing file or symlink, and (2) the `~/.claude/settings.json` merge, where the user's existing settings must be enriched with cortex-command's hooks, permissions, sandbox config, statusLine, plugins, and apiKeyHelper without touching personal scalar settings.

## Requirements

### Skill Location and Structure

1. **Local project skill only** — skill lives at `.claude/skills/setup-merge/SKILL.md`. The `.claude/skills/` directory is project-local (Priority 3 in Claude Code skill precedence). Never deployed to `~/.claude/skills/` or `skills/`.
2. **Python helper script** — JSON manipulation, diff computation, and atomic writes delegated to `.claude/skills/setup-merge/scripts/merge_settings.py`. Uses Python stdlib only (json, os, tempfile, fnmatch, pathlib). Claude orchestrates the interactive UX; the script handles deterministic JSON operations.
3. **`disable-model-invocation: true`** in SKILL.md frontmatter — prevents auto-triggering; only runs on explicit `/setup-merge` invocation.

### Safety Guards (Run Before Anything Else)

4. **Symlink guard** — if `~/.claude/settings.json` is a symlink (`Path.is_symlink()` returns true), abort immediately with: "settings.json is managed as a symlink to the repo — use `just setup-force` to reinstall, or resolve conflicts manually." Do not attempt any write.
5. **Worktree guard** — if `git rev-parse --git-dir` differs from `git rev-parse --git-common-dir`, abort immediately with: "Run /setup-merge from the main cortex-command checkout, not from a worktree — symlinks created from a worktree path will break when the worktree is deleted."
6. **Sandbox warning** — if running in a sandboxed session (detect via `TMPDIR` starting with `/private/tmp/claude` or `/tmp/claude`), warn before attempting any write: "This session is sandboxed. The settings.json write may be blocked. If the write fails, run the merge helper directly from the terminal."

### Conflict Detection

7. **Re-detect from current state** — the skill detects conflicts by reading the live system state, not from any manifest or the output of a previous `just setup` run. This makes it self-contained and idempotent.
8. **Authoritative install list — runtime discovery** — the helper script determines what cortex-command would install by reading the repo's actual directories at invocation time, anchored to `git rev-parse --show-toplevel`. No hardcoded file lists; no fixed counts. For each category:
   - `~/.local/bin/*` — all files in `bin/` (listed at runtime)
   - `~/.claude/reference/*.md` — all `.md` files in `claude/reference/` (listed at runtime)
   - `~/.claude/skills/<name>` — all subdirectories in `skills/` (listed at runtime)
   - `~/.claude/hooks/<filename>` — all files in `hooks/` matching `cortex-*` prefix, any extension (`.sh`, `.py`, etc.) (listed at runtime)
   - `~/.claude/notify.sh` — `hooks/cortex-notify.sh` (hardcoded: this is the one special-case path mapping)
   - `~/.claude/statusline.sh` — `claude/statusline.sh` (hardcoded: single file)
   - `~/.claude/rules/<filename>` — all `.md` files in `claude/rules/` (listed at runtime)
9. **Conflict classification** (per symlink target):
   - `new` — target does not exist → install immediately without prompting
   - `update` — target is a symlink pointing to this repo → reinstall silently (idempotent)
   - `conflict-broken` — target is a broken symlink
   - `conflict-wrong-target` — target is a symlink pointing to a different path
   - `conflict-file` — target is a regular file

### Symlink Conflict Resolution (Interactive)

10. **New and update targets** — resolved silently; counted and reported in the summary but not prompted.
11. **Broken symlink conflicts** — show the broken path, ask Y/n to replace. On Y: `ln -sf` (files) or `ln -sfn` (directories). On N: skip and note in summary.
12. **Wrong-target symlink conflicts** — show current target path and cortex-command target path side-by-side, ask Y/n to repoint. On N: skip.
13. **Regular-file conflicts** — show a diff (via `diff` if available; graceful fallback to file listing if not), warn that the file will be replaced by a symlink, require explicit Y. On Y: `ln -sf`/`ln -sfn`. On N: skip.
14. **Symlink commands** — `ln -sfn <source-dir> <target>` for directory symlinks (skills); `ln -sf <source-file> <target>` for file symlinks (all others). Source paths must be absolute (resolved from repo root via `git rev-parse --show-toplevel`).

### settings.json Merge (Interactive Per-Category)

15. **Summary table first** — before any Y/n prompts, display a table listing all pending categories with the count of entries that would be added. Categories with no delta (everything already present) are marked "✓ already installed" and excluded from prompts.
16. **Required hooks — merged unconditionally** (no Y/n prompt): nine hooks across eight event types:
    - SessionStart: `cortex-sync-permissions.py`, `cortex-scan-lifecycle.sh`
    - SessionEnd: `cortex-cleanup-session.sh`
    - PreToolUse (Bash): `cortex-validate-commit.sh`
    - PostToolUse (Bash): `cortex-tool-failure-tracker.sh`
    - PostToolUse (Write|Edit): `cortex-skill-edit-advisor.sh`
    - Notification (permission_prompt): `cortex-permission-audit-log.sh`
    - WorktreeCreate: `cortex-worktree-create.sh`
    - WorktreeRemove: `cortex-worktree-remove.sh`

    **Hook presence detection**: a hook is considered present if the `(event-type, matcher, command-substring)` triple already exists anywhere in `settings.json`. `command-substring` means the script filename (e.g., `cortex-worktree-create.sh`) appears as a substring of the hook's `command` field. For hooks without a matcher (WorktreeCreate, WorktreeRemove): the matcher component of the triple is empty string.

    **Hook insertion algorithm** (when a hook is absent):
    1. In `settings.json["hooks"][event-type]`, find the first array entry whose `matcher` field equals the cortex hook's matcher (empty string for matcher-less event types).
    2. If found: append `{type: "command", command: <command>}` (with `timeout` if applicable) to that entry's `hooks` array. Do not create a new top-level entry.
    3. If not found: create a new entry `{matcher: <matcher>, hooks: [{type: "command", command: <command>}]}` (omit `matcher` key if matcher is empty string) and append it to the `settings.json["hooks"][event-type]` array. If `settings.json["hooks"][event-type]` does not exist, create it as an empty array first.

17. **Optional hooks — prompted per hook with description** (Y/n each):
    - `cortex-setup-gpg-sandbox-home.sh` (SessionStart) — "Sets up GPG agent for sandbox-compatible commit signing. macOS-specific. Required if you use signed commits in sandboxed sessions."
    - `cortex-notify.sh` (Notification + Stop) — "Sends desktop notifications when Claude needs attention or completes. Requires cortex-notify infrastructure."
    - `cortex-notify-remote.sh` (Notification + Stop) — "Sends remote notifications (Tailscale/Android). Requires notify-remote infrastructure."
    Use the same hook insertion algorithm as requirement 16.

18. **Per-category settings — prompted with delta** (Y/n each):
    - **Deny rules** — show list of entries not already present; recommend yes; note "These are safety rules (block sudo, rm -rf, force push, reading secrets)."
    - **Allow list** — show list of entries not already present (delta only); note entries are additive and won't remove existing user rules.
    - **Sandbox network config** — show allowedDomains, allowUnixSockets, excludedCommands, autoAllowBashIfSandboxed entries not already present.
    - **StatusLine** — show the cortex-command statusLine config; note "Requires `~/.claude/statusline.sh` to be installed (handled by symlink section above)."
    - **Plugins** — show context7 and claude-md-management plugin entries not already present; merge individual plugin keys only (do not overwrite other user plugins or `enableAllProjectMcpServers`). If a plugin key already exists with any value, report "already installed" and skip.
    - **apiKeyHelper** — show the stub path (`~/.claude/get-api-key.sh`); note "Returns empty for subscription users (no effect), or delegates to `~/.claude/get-api-key-local.sh` for API key users." Check both `~/.claude/settings.json` and `~/.claude/settings.local.json` for presence before offering.
19. **Personal scalars — never touched**: `model`, `effortLevel`, `alwaysThinkingEnabled`, `skipDangerousModePermissionPrompt`, `cleanupPeriodDays`, `attribution`, `env`, `$schema`, `sandbox.enabled`, `sandbox.filesystem.allowWrite`, `sandbox.filesystem.denyWithinAllow`, `enableAllProjectMcpServers`, any other top-level scalar not listed as a merge-in category.

### Contradiction Detection

20. **Deny-blocks-allow check** (forward direction) — before writing any approved allow entry, run: `fnmatch.fnmatch(allow_cmd, deny_pattern)` for each *existing* deny rule in the user's current `settings.json`. If a match is found, surface for manual resolution: "Your existing deny rule `{deny}` would block cortex-command allow entry `{allow}`. Resolve the conflict manually before this entry can be added."
21. **Allow-blocks-deny check** (reverse direction) — before writing any approved deny entry, run: `fnmatch.fnmatch(existing_allow_cmd, deny_pattern)` for each *existing* allow entry in the user's current `settings.json`. If a match is found, surface for manual resolution: "Proposed deny rule `{deny}` would block your existing allow entry `{existing_allow}`. Resolve the conflict manually before this deny entry can be added."
22. **Scope of checks** — forward check (req 20): only for proposed allow entries that are literal strings (no `*`). Reverse check (req 21): only for existing allow entries that are literal strings (no `*`). For wildcard allow entries in either direction, emit an advisory ("This entry contains a wildcard — verify it doesn't conflict with your rules") but proceed without blocking.
23. **Hard block behavior** — contradicted entries (in either direction) are skipped even if the user approved the category. Each contradiction is listed individually in the post-merge summary.

### Atomic Write

24. **Write path** — after all Y/n prompts are collected, merge_settings.py performs a single atomic write covering all approved categories. No partial writes.
25. **Atomic protocol** — immediately after reading `~/.claude/settings.json`, capture its mtime. Then: write merged content to a temp file in the same directory → validate JSON (`json.loads()`) → check that current mtime of `~/.claude/settings.json` matches the captured mtime → `os.replace()`. If any step fails, delete the temp file and abort with the error; original settings.json is untouched.
26. **Abort conditions** — abort (without writing) if: JSON validation fails, mtime check fails (file was modified during the interactive session), or `os.replace()` fails.

### Idempotency

27. **Second-run behavior** — on a second invocation, all already-installed entries report "already installed" and are excluded from Y/n prompts. No entries are re-added. If everything is installed, the skill exits: "All cortex-command components already installed."

### Post-Merge Summary

28. **Summary report** — after completion, display: count of symlinks installed, count of symlinks skipped, count of settings.json categories merged, count of settings.json categories skipped by user, list of all unresolved contradictions in both directions (allow-blocked-by-deny AND deny-blocked-by-existing-allow), list of skipped regular-file conflicts (if any).

## Non-Requirements

- Does NOT implement `just setup-force` destructive behavior (symlink replacement without conflict check)
- Does NOT verify that hook scripts exist or are executable at the hook paths
- Does NOT merge settings for other projects or repos
- Does NOT touch `~/.claude/settings.local.json` (read-only for presence detection)
- Does NOT support partial-category rollback after a successful write
- Does NOT create `claude/get-api-key.sh` if it doesn't exist (stub is a separate deliverable)
- Does NOT deploy globally — the skill is never added to `skills/` or `~/.claude/skills/`
- Does NOT use file locking for concurrent-write protection — mtime-based detection is sufficient for single-user personal tooling

## Edge Cases

- **`~/.claude/settings.json` is a symlink** → abort (requirement 4); do not write through it
- **Running from a worktree** → abort (requirement 5); symlinks would point to ephemeral paths
- **User declines all Y/n prompts** → no file is written; summary reports 0 merged
- **Mix of Y/n responses** → only approved categories merged in a single atomic write
- **Hook already present in wrong event type** → identity rule uses (event-type, matcher, command-substring) triple; mismatch = absent; the correct-event entry is added (per req 16 insertion algorithm) without removing the wrong one
- **User already has hooks under the same event type and matcher** → append cortex hook to the existing matcher group's `hooks` array (do not replace the group)
- **`enabledPlugins` key absent from user's settings.json** → create the key with only cortex-command entries; do not infer or touch other plugin state
- **apiKeyHelper in `settings.local.json` but not `settings.json`** → report "apiKeyHelper already configured in settings.local.json (already installed)"; do not add to settings.json
- **Forward contradiction found** → skip the blocked allow entry; log in summary; user must resolve manually; other non-contradicted entries from the same category are still written if approved
- **Reverse contradiction found** → skip the blocking deny entry; log in summary; user must resolve manually; other non-contradicted deny entries from the same category are still written if approved
- **`diff` not available on PATH** → fall back to displaying file size and inode info for regular-file conflicts; still require explicit Y
- **Sandboxed session** → warn at startup (requirement 6); attempt write; if `os.replace()` raises PermissionError, surface the error and halt with instructions to run the helper from the terminal
- **mtime check fails** → abort without writing; display: "settings.json was modified during this session — re-run /setup-merge to merge against the current version"
- **`bin/`, `hooks/`, `skills/`, `claude/rules/`, or `claude/reference/` contains files added since the skill was written** → automatically included in the install scope (runtime discovery handles repo evolution without code changes)

## Technical Constraints

- Python stdlib only — no third-party packages (json, os, tempfile, fnmatch, pathlib, subprocess)
- `python3` availability assumed (declared project dependency in requirements/project.md)
- `ln` availability assumed (standard macOS/Linux)
- `git rev-parse` availability assumed (standard; repo is always a git repo)
- `diff` availability optional — graceful fallback required
- Temp file must be in the same directory as `~/.claude/settings.json` for `os.replace()` to be atomic on the same filesystem
- The Python helper locates itself via `${CLAUDE_SKILL_DIR}` (set by Claude Code at skill invocation time) to avoid hardcoded paths
- The skill must run from the cortex-command repo root; it uses `git rev-parse --show-toplevel` to anchor source paths, not `$(pwd)`

## Open Decisions

- **Inform user about cortex-sync-permissions.py side effect** — this hook writes `_globalPermissionsHash` into `settings.local.json` at every SessionStart (a workaround for upstream bug #17017). The spec does not require a disclosure prompt, but implementation should consider whether to include a one-line note alongside the "required hooks" section explaining this non-obvious side effect. Left to implementer judgment.
