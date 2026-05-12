# Research: Build /setup-merge local skill

## Epic Reference

Epic research at `research/shareable-install/research.md` covers the full shareable-install initiative (additive `just setup`, hook prefixing, CLAUDE.md strategy). This ticket is scoped to the `/setup-merge` skill implementation only — the conflict resolution path that runs after `just setup` prints a pending list.

---

## Codebase Analysis

### Files That Will Be Created

**New local project skill (primary deliverable):**
- `.claude/skills/setup-merge/SKILL.md` — local project skill, placed in `.claude/skills/` (project-local), NOT `skills/` (global). Never globally deployed.
- `.claude/skills/setup-merge/scripts/merge_settings.py` — Python helper that handles all JSON reads, diffs, and atomic writes. Claude orchestrates the UX; the script handles deterministic JSON manipulation.

The `.claude/skills/` directory does not yet exist in the repo and must be created.

### settings.json Structure (Exact Fields the Skill Must Handle)

From `claude/settings.json` (the canonical source of what the skill merges into a user's file):

**Hooks block** — event-keyed dict, each value is an array of `{matcher?, hooks: [{type, command, timeout?}]}` objects:
- `SessionStart` — 3 commands: sync-permissions, scan-lifecycle, setup-gpg-sandbox (optional)
- `SessionEnd` — 1 command: cleanup-session
- `PreToolUse` (matcher: "Bash") — 1 command: validate-commit
- `PostToolUse` (matcher: "Bash") — 1 command: tool-failure-tracker
- `PostToolUse` (matcher: "Write|Edit") — 1 command: skill-edit-advisor
- `Notification` (matcher: "permission_prompt") — 3 commands: permission-audit-log, notify.sh, notify-remote.sh
- `Stop` — 2 commands: notify.sh complete, notify-remote.sh complete
- `WorktreeCreate` — 1 command: worktree-create (long inline bash)
- `WorktreeRemove` — 1 command: worktree-remove (long inline bash)

**Required hooks (merged unconditionally — 9 hooks):**
`cortex-sync-permissions.py`, `cortex-scan-lifecycle.sh`, `cortex-validate-commit.sh`, `cortex-skill-edit-advisor.sh`, `cortex-tool-failure-tracker.sh`, `cortex-cleanup-session.sh`, `cortex-permission-audit-log.sh`, `cortex-worktree-create.sh`, `cortex-worktree-remove.sh`

**Optional hooks (asked separately — 3 hooks):**
- `cortex-setup-gpg-sandbox-home.sh` (SessionStart) — GPG/sandbox, macOS-specific
- `cortex-notify.sh` + `cortex-notify-remote.sh` (Notification + Stop) — require local notification infrastructure

**Special case**: `cortex-notify.sh` is symlinked to `~/.claude/notify.sh` (not `~/.claude/hooks/cortex-notify.sh`). The skill must handle this path separately.

**Per-category settings (each shown as delta + Y/n):**
- `permissions.deny` — safety rules (safety-oriented; recommend yes)
- `permissions.allow` — 100+ entries (git, bash utils, gh, brew, docker, etc.)
- `sandbox.network` — allowedDomains, allowUnixSockets, excludedCommands, autoAllowBashIfSandboxed
- `statusLine` — `{type: "command", command: "~/.claude/statusline.sh", padding: 0}`
- `enabledPlugins` — context7, claude-md-management (merge individual keys, not the whole object)
- `apiKeyHelper` — stub pointing to `~/.claude/get-api-key.sh` (not yet shipped; presence check must also check `settings.local.json`)

**Fields to NEVER touch:** `model`, `effortLevel`, `alwaysThinkingEnabled`, `skipDangerousModePermissionPrompt`, `cleanupPeriodDays`, `attribution`, `env`, `$schema`, `sandbox.enabled`, `sandbox.filesystem.allowWrite`, `enableAllProjectMcpServers`, any scalar the user set explicitly.

**`apiKeyHelper` current state:** Not present in `claude/settings.json` (was removed). Lives in `~/.claude/settings.local.json` on the primary user's machine. When checking for presence, inspect BOTH `~/.claude/settings.json` and `~/.claude/settings.local.json`.

### Existing Patterns to Follow

**Python JSON manipulation** (`claude/hooks/cortex-sync-permissions.py`):
- Uses stdlib only: `json`, `pathlib.Path`, `os`
- Read: `json.loads(path.read_text())`
- Write: `path.write_text(json.dumps(settings, indent=2) + "\n")`
- The existing hook does NOT use atomic write — the skill's helper must add it

**Atomic write pattern (must implement):**
```python
import json, os, tempfile

def atomic_write_json(data, target_path):
    json_str = json.dumps(data, indent=2) + "\n"
    json.loads(json_str)  # validate before touching disk
    target_dir = os.path.dirname(os.path.abspath(target_path))
    fd, tmp = tempfile.mkstemp(dir=target_dir, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(json_str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target_path)  # POSIX atomic
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
```

`os.replace()` is POSIX atomic when source and destination are on the same filesystem (same directory guarantees this). Validate JSON before writing, not after.

**Symlink commands:**
- `ln -sfn <source-dir> <target>` — for directory symlinks (skills)
- `ln -sf <source-file> <target>` — for file symlinks (hooks, notify.sh)

### Integration Points and Dependencies

1. **`just setup`** — calls deploy-bin, deploy-reference, deploy-skills, deploy-hooks, deploy-config and writes conflict paths to `$CONFLICTS_FILE`. The skill is the resolution path for that list.
2. **`~/.claude/settings.json`** — the merge target. May be: (a) a regular file (new user), (b) a symlink to the repo (primary user). **Must detect the symlink case and abort before writing.**
3. **Conflict types from deploy-* recipes** — three types: broken symlink, symlink-to-wrong-target, regular file.
4. **`~/.local/bin/`, `~/.claude/reference/`, `~/.claude/skills/`, `~/.claude/hooks/`** — symlink target directories for the various deploy-* recipes.

---

## Web Research

### Glob Overlap Detection

No stdlib function checks "does deny pattern D subsume allow pattern A?" The practical implementation:

```python
import fnmatch

def would_be_blocked(allow_entry: str, deny_rules: list[str]) -> list[str]:
    """Returns deny rules that would block this allow entry."""
    def extract_cmd(rule: str) -> str:
        if rule.startswith("Bash(") and rule.endswith(")"):
            return rule[5:-1]
        return rule

    allow_cmd = extract_cmd(allow_entry)
    blocking = []
    for deny_rule in deny_rules:
        deny_pat = extract_cmd(deny_rule)
        if fnmatch.fnmatch(allow_cmd, deny_pat):
            blocking.append(deny_rule)
    return blocking
```

**Critical caveat**: The allow list contains wildcard entries like `Bash(* --version)` and `Bash(python3 *)`. Running fnmatch across all 100+ allow entries × 30+ deny entries with wildcard-heavy patterns will generate false positives. The overlap detection should be scoped narrowly:
- Only check when the allow entry is a **literal** (no `*`). For allow entries containing `*`, emit an advisory at most.
- Consider simplifying v1 to exact-string check only: does the allow string appear verbatim in the deny list?

### Atomic JSON Write

Canonical pattern (cross-platform, POSIX-safe):
- Temp file must be in the **same directory** as the target — `os.replace()` is only atomic on same filesystem
- `os.replace()` not `os.rename()` — `replace` is guaranteed atomic on POSIX
- Validate JSON before writing the temp file — not after

### Claude Code Settings Behavior

- `permissions.allow` and `permissions.deny` arrays are **concatenated and deduplicated** across scopes. Adding to user scope doesn't override project-scope entries.
- `hooks` block merging behavior across scopes is **not documented as deep-merge** — assumed to be scope-priority override. The skill writes to user-scope settings.json directly, so project-scope hooks from `.claude/settings.json` are orthogonal.
- Evaluation order: deny → ask → allow, first match wins.
- `~/.claude.json` stores: autoConnectIde, autoInstallIdeExtension, editorMode, showTurnDuration, teammateMode — NOT in `settings.json`. Adding these to `settings.json` triggers schema errors.

---

## Requirements & Constraints

From `requirements/project.md`:
- **File-based state only** — no manifest file. Detect state by reading live files.
- **Complexity must earn its place** — scope exactly to what's needed for conflict resolution.
- **Graceful partial failure** — surface errors clearly; don't silently swallow them.

From `backlog/007-build-setup-merge-skill.md` (acceptance criteria):
- Skill is local: `.claude/skills/setup-merge/` — not deployed globally
- Required hooks merged without prompting
- Optional hooks prompted with description of what they do
- Per-category questions show current value + proposed change before Y/n
- Already-present components shown as "already installed" and skipped
- deny/allow contradictions surfaced for manual resolution, not auto-merged
- Personal scalars untouched
- Atomic write: tmp → validate → mv; interrupted write leaves original intact
- Idempotent: second run shows everything as "already installed"

---

## Tradeoffs & Alternatives

### Implementation Language

**Recommended: Python script + Claude orchestration hybrid.**
- Python (`scripts/merge_settings.py`): handles JSON reads, diffs, atomic writes, fnmatch overlap checks. Uses stdlib only (json, os, tempfile, fnmatch, pathlib).
- Claude (SKILL.md): orchestrates the interactive loop — formats diffs readably, handles Y/n flow, invokes the script with approved categories as a JSON argument.
- Rationale: Claude is good at presenting diffs and managing conversation flow; a deterministic script is good at correct JSON manipulation and atomic writes. Neither can reliably do both.

**Rejected: bash + jq.** Glob overlap detection is painful in bash; hooks are complex nested objects that jq handles awkwardly; `jq` availability can't be assumed.

**Rejected: Claude-only (no script).** Model hallucination risk on JSON field preservation; atomic write contract is hard to enforce; no reproducible behavior.

### Interactivity Model

**Recommended: Summary table first, then prompt per category.**
- Show all N categories with pending changes in a table before any prompts.
- Walk through each category's Y/n in sequence, showing current value + proposed delta for each.
- Categories with no diff silently skipped.

### Symlink Conflict Resolution (Tiered by Type)

- **Broken symlink** → overwrite on Y (nothing to lose)
- **Symlink to wrong target** → show current target + cortex target, Y to repoint
- **Regular file** → show diff if available, warn it will be replaced, explicit Y required

### Conflict Detection

**Recommended: Diff-based with documented identity rules per category type.**
- allow/deny arrays: exact string match
- hooks: (event-type, matcher, command) triple
- WorktreeCreate/WorktreeRemove: match on the script path substring (not full inline command) — exact-string matching fails on whitespace normalization
- statusLine: compare `command` field
- plugins: compare key name
- sandbox: exact string match per array element

---

## Adversarial Review

### Failure Modes and Edge Cases

**Local skill discovery is unverified.** The `.claude/skills/` project-local path is a real directory (not a symlink), so it should not be affected by issue #14836. But this is an assumption — it must be verified that Claude Code loads skills from `.claude/skills/` at project scope before shipping.

**Symlink detection before write is critical.** `~/.claude/settings.json` is a symlink to the repo on the primary user's machine. `os.replace()` on a path that resolves through a symlink may either write through the symlink or replace the symlink inode with a real file (macOS behavior). The Python helper must check `Path("~/.claude/settings.json").is_symlink()` and abort with a clear message: "Use `just setup-force` instead — this file is a symlink to the repo."

**Worktree guard required.** `ln -sf $(pwd)/...` from a worktree creates symlinks pointing to ephemeral paths. Mirror the deploy-bin guard: `git rev-parse --git-dir` == `git rev-parse --git-common-dir`. Abort if running from a worktree.

**Hook command matching is fragile for WorktreeCreate/WorktreeRemove.** These use long inline bash one-liners. Match on a stable substring (the script path like `cortex-worktree-create.sh`) rather than exact command string.

**Sandbox blocks the atomic write.** If invoked from a sandboxed Claude Code session, `os.replace()` on `~/.claude/settings.json` will fail with "Operation not permitted." Add an explicit check: if `$TMPDIR` starts with `/private/tmp/claude` or `/tmp/claude`, warn the user before attempting the write.

**apiKeyHelper: check both settings files.** If already in `settings.local.json`, don't offer to add it to `settings.json`.

**`cortex-notify.sh` special path.** Symlink target is `~/.claude/notify.sh`, not `~/.claude/hooks/cortex-notify.sh`. The conflict resolution logic must handle this path explicitly.

**Unconditional hooks and informed consent.** `cortex-sync-permissions.py` runs at every SessionStart in every project and writes a `_globalPermissionsHash` into `settings.local.json`. This is a workaround for upstream bug #17017. Users should be informed, not just told "required hooks merged."

**fnmatch false positives on wildcard allow entries.** Apply overlap detection only to literal allow entries (no `*`). For allow entries containing `*`, emit advisory only or skip the check.

**enableAllProjectMcpServers guard.** When merging `enabledPlugins`, add individual keys only — do not serialize the whole cortex-command plugins object. `enableAllProjectMcpServers` is a sibling key that the user may have set to `true`; writing it as `false` is a silent regression.

---

## Open Questions

- **Does Claude Code load skills from `.claude/skills/` at project scope?** Resolved — the skills reference explicitly documents `.claude/skills/<name>/SKILL.md` as Priority 3 (project-scope) skill location. No empirical test needed.
- **Does Claude Code handle `apiKeyHelper` returning empty without error for interactive users?** Resolved — confirmed by primary user: empty return = subscription billing, set value = API key billing. Both paths work without error.
- **How does Claude Code merge the `hooks` block across scopes (user + project settings.json)?** Resolved — the skill writes only to user-scope `~/.claude/settings.json`. Cross-scope hook merging (user + project) is independent of the skill's write operation and does not affect its correctness.
