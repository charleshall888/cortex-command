# Research: shareable-install

> Explore approaches for making cortex-command installable without overwriting a
> new user's existing Claude global settings, enabling the repo to be shared or
> forked without destructive first-run behavior.

## Research Questions

1. What does the current install actually overwrite, and what protection exists today?
   → **Answered: only `deploy-config` prompts; all other recipes are fully silent. See Codebase Analysis.**

2. Does Claude Code's `settings.json` format support layering or merging multiple config files?
   → **Yes — four-scope hierarchy with array concatenation. Project-scope arrays are additive on top of user settings.**

3. Can skills and hooks be namespaced/added alongside existing user content without conflict?
   → **Skills: plugin namespacing exists but requires MCP setup — not available for directory deploy. Hooks: no namespacing mechanism; `cortex-` prefix is the solution. `.claude/rules/` is the officially documented symlink-safe path for instructions — but user-scope `~/.claude/rules/` requires verification.**

4. What models exist for non-destructive config distribution (additive, merge, profile-based, opt-in)?
   → **Four patterns: backup-and-replace (oh-my-zsh), conflict-abort (GNU Stow), diff-then-apply (chezmoi), source-line injection (nvm/homebrew). Details in Domain & Prior Art.**

5. What do similar AI agent config-sharing projects do to avoid clobbering global configs?
   → **Community consensus: use project-scope files to avoid the problem entirely. No well-documented solution exists for merging into `~/.claude/settings.json`.**

6. What's the minimal viable change — can we add an opt-in mode to `just setup`?
   → **Yes — ~50–100 lines of bash per recipe to add existence checks. But this is insufficient alone; skills and hooks have a deeper namespacing problem, and `settings.json` merge is the hardest case.**

---

## Codebase Analysis

### What `just setup` actually overwrites

`just setup` chains five sub-recipes. Only one prompts before overwriting.

| Recipe | Targets | Prompting | Silent overwrite risk |
|--------|---------|-----------|----------------------|
| `deploy-bin` | 7 symlinks in `~/.local/bin/` | None | Low — names are cortex-specific |
| `deploy-reference` | 4 symlinks in `~/.claude/reference/` | None | Low — cortex-specific filenames |
| `deploy-skills` | 31 **directory** symlinks in `~/.claude/skills/` | None | **High** — common names (commit, research, pr, lifecycle, discovery) |
| `deploy-hooks` | 14+ file symlinks in `~/.claude/hooks/` | None | **High** — common names (validate-commit.sh, cleanup-session.sh) |
| `deploy-config` | 3 file symlinks + `settings.local.json` | **Yes, for regular files only** | Medium — existing symlinks replaced silently |

`deploy-config` uses `[ -f "$target" ] && [ ! -L "$target" ]` to detect regular files and prompt. An existing symlink at any of these paths is silently replaced with no prompt.

`settings.local.json` is not a symlink — it is written directly. If it exists and `jq` is available, the `sandbox.filesystem.allowWrite` key is overwritten (other keys preserved). If `jq` is absent, the file is fully overwritten. No prompt in either case.

### The skill directory symlink problem

`deploy-skills` uses `ln -sfn` to create directory symlinks:
```bash
ln -sfn "$(pwd)/skills/$name" "$HOME/.claude/skills/$name"
```

GitHub issue [anthropics/claude-code#14836](https://github.com/anthropics/claude-code/issues/14836) (open, 25+ upvotes, Feb 2026) documents that when skill directories inside `~/.claude/skills/` are symlinks rather than real directories, Claude Code's `/skills` discovery command shows "No skills found." The root cause is that skill discovery uses `find` without the `-L` flag.

This is deferred out of scope for this work but is a known issue affecting new users.

### Existing layering mechanism

`settings.local.json` is already used as a layering mechanism for the sandbox `allowWrite` path. `sync-permissions.py` (the SessionStart hook) merges project-level permissions into the session at startup. This is the existing precedent for additive, non-clobbering config.

### No selective install mode exists

Each sub-recipe (`just deploy-skills`, `just deploy-hooks`, etc.) can be invoked individually, but this is undocumented. There are no `--skip-*`, `--check`, or `--additive` flags.

---

## Web & Documentation Research

### Claude Code settings layering

Claude Code has a four-scope settings hierarchy (low to high precedence):

1. **User** — `~/.claude/settings.json`
2. **Project** — `.claude/settings.json` (committed, shared with team)
3. **Local** — `.claude/settings.local.json` (not committed, per-machine)
4. **Managed** — `/Library/Application Support/ClaudeCode/managed-settings.json` (macOS, cannot be overridden by users)

**Merge behavior:** Arrays (`permissions.allow`, `permissions.deny`) are concatenated and deduplicated across scopes. Scalars: higher-priority scope wins. Objects: deep-merged. This means project-scope `permissions.allow` entries are strictly additive on top of whatever the user already has.

**CLAUDE.md layering:** `~/.claude/CLAUDE.md` (user scope) + `./CLAUDE.md` or `./.claude/CLAUDE.md` (project scope) both load, in order. The `@path/to/import` syntax pulls in another file (max 5 hops). The `.claude/rules/` directory is an alternative: all `.md` files load automatically with same priority as `.claude/CLAUDE.md`.

**`.claude/rules/` is the officially documented symlink-safe path at project scope.** The docs explicitly state it supports symlinks for cross-project sharing. User-scope `~/.claude/rules/` is mentioned in community sources but not prominently documented by Anthropic — **this must be verified before the CLAUDE.md strategy can be adopted** (see DR-4).

### Known Claude Code symlink bugs

- **[anthropics/claude-code#764](https://github.com/anthropics/claude-code/issues/764)** (65+ upvotes): Symlinking `~/.claude/` *as a directory* breaks commands and CLAUDE.md reading. Cortex-command uses individual file/dir symlinks, not the directory itself — this specific bug does not apply.
- **[anthropics/claude-code#14836](https://github.com/anthropics/claude-code/issues/14836)** (25+ upvotes, open): Skill directory symlinks break `/skills` discovery. Directly affects current `deploy-skills`. Deferred.
- Individual file symlinks (for SKILL.md, settings.json, hooks) have no documented failures.
- **Pattern**: both verified issues represent Claude Code behaving contrary to user expectation. Unverified assumptions about symlink behavior should be treated with skepticism until confirmed.

---

## Domain & Prior Art

### Dotfile distribution patterns

| Pattern | Tool | Behavior on conflict | User experience |
|---------|------|---------------------|-----------------|
| Backup-and-replace | oh-my-zsh | Renames existing to `*.pre-oh-my-zsh`; prompts user | Safe; user prompted; original preserved |
| Conflict-abort | GNU Stow | Refuses to proceed; user must resolve manually | Safe; zero silent overwrites; requires user action |
| Diff-then-apply | chezmoi | Non-destructive by default; `merge-all` for conflicts | Most flexible; adds tool dependency |
| Source-line injection | nvm, homebrew | Appends loader line to existing file; idempotency check prevents duplicates | Least disruptive; can't handle arbitrary config |

### Prior art in AI agent config sharing

- **TheDecipherist/claude-code-mastery-project-starter-kit**: Explicitly advertises "non-destructive merge" that "preserves everything you already have." Most directly analogous prior art found.
- **chezmoi for multi-tool MCP config**: Keep one canonical config in chezmoi source state, generate each tool's format via templates.
- **Community consensus**: Use project-scope files to avoid touching user-scope config entirely. No well-tested solution exists for cleanly merging into `~/.claude/settings.json`.

---

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| A: Additive install (check-before-overwrite) | S | Doesn't solve namespace collisions for skills/hooks | None |
| B: Two-mode install (`just setup` additive + `just setup-force`) | S | Requires clear documentation of what each mode does | None |
| C: Prefix hooks `cortex-*` | M | Breaking change for existing users; cascades to settings.json hooks block, check-symlinks recipe, docs | Migration guide |
| D: `~/.claude/rules/cortex-command.md` for CLAUDE.md | M | **Blocking: user-scope `~/.claude/rules/` must be verified first** (see DR-4) | Verify + Agents.md refactor |
| E: `/setup-merge` skill for conflict resolution | M | UX burden: requires user to open Claude session in cortex-command repo directory | Collision-detection design spec |
| F: chezmoi-based distribution | L | New tool dependency; architecture change; high contributor friction | chezmoi install |

---

## Decision Records

### DR-1: Skill directory symlinks are already broken for skill discovery

- **Context**: `deploy-skills` creates directory symlinks. Claude Code issue #14836 documents that `/skills` discovery does not follow symlinks.
- **Options**: (a) Accept — skills work when invoked directly; (b) Symlink individual `SKILL.md` files instead of directories; (c) Copy directories.
- **Recommendation**: Investigate option (b). Option (c) breaks live-edit workflow.
- **Status**: Deferred — out of scope for this work.

### DR-2: `settings.json` must still be written globally; hooks cannot move to project scope

- **Context**: All hooks serve all projects, not just cortex-command. `validate-commit.sh` enforces style globally. `scan-lifecycle.sh` self-exits in projects without `lifecycle/` but is designed to fire anywhere lifecycle tracking is used. `sync-permissions.py`, `cleanup-session.sh`, `permission-audit-log.sh`, `notify.sh`, `tool-failure-tracker.sh` are all global infrastructure.
- **Decision**: `~/.claude/settings.json` must be written. The shareability fix for `settings.json` is additive merge, not scope migration.
- **What additive merge means for settings.json**: The `/setup-merge` skill must handle `settings.json` carefully:
  - `permissions.allow`: union of existing and cortex-command entries (never remove user's existing entries)
  - `permissions.deny`: union — but conservative; never silently remove a user's existing deny rule
  - `hooks`: add cortex-command hook registrations that are not already present; do not overwrite existing hook entries for the same event type
  - Scalar settings (`model`, `sandbox`, `effortLevel`, etc.): leave unchanged if already set; only write if absent
  - This is content-aware work that bash cannot do — agent skill is appropriate here

### DR-3: Hook files must be prefixed `cortex-` to eliminate collision risk

- **Context**: Generic hook names (`validate-commit.sh`, `cleanup-session.sh`) collide with any power user's existing hooks.
- **Decision**: Rename all hook files to `cortex-<name>.sh` (e.g., `cortex-validate-commit.sh`).
- **Cascade scope**: This is not a "single-file change." The following all require updating:
  - All hook path references in `claude/settings.json` (the hooks block, 8 event types, 15+ entries)
  - `check-symlinks` recipe in the justfile (hardcodes hook names)
  - Any documentation referencing hook paths by name
  - README backup warning
- **Migration for existing users**: One-time update. The cascade is mechanical (find-and-replace hook filenames) but must be done completely — a partial rename leaves dangling references.

### DR-4: `~/.claude/rules/` at user scope must be verified before adopting the CLAUDE.md strategy

- **Context**: The proposed CLAUDE.md strategy (deploy `~/.claude/rules/cortex-command.md` as a symlink to `claude/Agents.md`, never touch `~/.claude/CLAUDE.md`) depends entirely on Claude Code loading `.md` files from `~/.claude/rules/` automatically for all projects.
- **Why this is a blocking prerequisite**: The docs clearly document `.claude/rules/` at project scope. User-scope `~/.claude/rules/` is mentioned in community sources but not prominently documented. If user-scope rules/ does not load automatically, the entire strategy silently fails: no error, no warning, cortex-command instructions stop applying to all projects.
- **Verification required before implementation**: Start a Claude session, create `~/.claude/rules/test.md` with a distinctive instruction, confirm it is applied in a project that has no `.claude/CLAUDE.md`. Only then can DR-4 be considered resolved.
- **Fallback if unverified**: Use the `@import` injection approach — append `@/path/to/cortex-command/claude/Agents.md` to the user's existing `~/.claude/CLAUDE.md` (create it if absent). This has a different set of trade-offs: absolute path dependency, requires `Agents.md` refactor to remove install-specific assumptions, but does not depend on an unverified feature.
- **Either way**: `claude/Agents.md` must be refactored to remove the line "Global Claude Code settings live at `~/.claude/settings.json` (symlinked from `cortex-command/claude/settings.json`)" — this assumption is only true for users who adopted the full install, not new sharers.

### DR-5: Collision-detection classification rubric

For `just setup`'s pre-install check, each target is classified as:

| Class | Condition | Action |
|-------|-----------|--------|
| `new` | Target does not exist | Install immediately |
| `update` | Target exists as a symlink pointing to this repo already | Reinstall (safe re-run) |
| `conflict` | Target exists as a symlink pointing somewhere else | Skip; add to pending list |
| `conflict` | Target exists as a regular file | Skip; add to pending list |

The distinction between `update` and `conflict` is: same repo path = update (safe), different path or non-symlink = conflict (requires judgment). After install, `just setup` prints the pending list and instructs the user to run `/setup-merge` from within the cortex-command repo.

**UX burden acknowledged**: `/setup-merge` is a local project skill in `.claude/skills/` — it is only available when the user has a Claude session open inside the cortex-command repo directory. This is a real friction point for new users who may not yet be oriented. The setup output must make this explicit: "Open Claude in the cortex-command directory and run `/setup-merge` to resolve N conflicts."

---

## Additional Finding: `apiKeyHelper` blocks subscription users on first install

`claude/settings.json` contains:
```json
"apiKeyHelper": "~/.claude/get-api-key.sh"
```

This script is not in the repo and no setup step creates it. A new user gets a "No such file or directory" error at Claude Code startup, blocking all interactive use.

**Key facts:**
- `runner.sh:42-44`: `apiKeyHelper` only authenticates the parent `claude` process — it does NOT export `ANTHROPIC_API_KEY` into child subprocesses.
- `runner.sh` logs `Warning: apiKeyHelper returned empty` — not an error; overnight runs on subscription billing when the helper is absent.
- Subscription users (`/login`) need no API key helper.
- `runner.sh` reads `~/.claude/settings.json` only — it does NOT read `settings.local.json`.

**Fix:** Remove `apiKeyHelper` from `claude/settings.json`.

**Migration paths by user type:**

| User type | Interactive Claude Code | Overnight runner |
|-----------|------------------------|-----------------|
| Subscription | `/login` — no change needed | Works as-is (subscription fallback) |
| API key billing | Add `apiKeyHelper` to `~/.claude/settings.local.json` | Set `ANTHROPIC_API_KEY` in shell env — `runner.sh` does not read `settings.local.json` |

**Important**: for overnight/runner.sh users, `settings.local.json` is NOT a valid migration target — the runner never reads it. `ANTHROPIC_API_KEY` env var is the only correct path for overnight API-key billing.

**`smoke_test.py` inconsistency**: `smoke_test.py` checks for `apiKeyHelper` in `.claude/settings.local.json` (project-local), not `~/.claude/settings.local.json` (user-local). After the fix, this test passes for subscription users but the path it checks is different from where API-key interactive users are told to configure the helper. This is a pre-existing inconsistency that the fix does not create but does expose.

---

## Findings from User Input

- **Skills must be globally available** across all projects. Global deploy is a requirement, not opt-in.
- **Hook prefix:** `cortex-` (e.g., `cortex-validate-commit.sh`). See DR-3 for cascade scope.
- **CLAUDE.md strategy:** Deploy `~/.claude/rules/cortex-command.md` as a symlink (Option 3). Blocked on DR-4 verification. `Agents.md` must be refactored regardless of which CLAUDE.md strategy is used.
- **Install flow:** `just setup` runs collision detection per DR-5, installs `new` and `update` targets, skips `conflict` targets, prints pending list. `/setup-merge` (local project skill in `.claude/skills/`) resolves conflicts inline — no re-run of `just setup` needed.
- **`/setup-merge` handles both skill conflicts and `settings.json` merge** — the latter is the harder and more dangerous case (see DR-2).
- **Skill directory symlink bug** (issue #14836): deferred.

---

## Final Decisions

- **`Agents.md` split**: Split into two files. One file contains genuinely generic rules (git behavior, commit style, compound command avoidance) — safe to inject into any user's global context. The second file contains cortex-command-specific setup notes (settings architecture, conditional loading table, skill invocations) — relevant only to users who have adopted the full install, kept separate so it can be excluded from the shared rules injection or maintained independently.

- **`settings.json` strategy — Model B (merge-once, not symlink)**: New/shared users keep their own `~/.claude/settings.json`. `/setup-merge` adds cortex-command's entries into it. The primary user's machine keeps the existing symlink model. `just setup-force` restores the destructive symlink behavior for those who want it.

- **`settings.json` category split**:
  - *Merge in (framework):* hooks block, statusLine, sandbox network config + excludedCommands + autoAllowBashIfSandboxed, context7 + claude-md-management plugins, apiKeyHelper stub reference, deny list (safety rules)
  - *Never touch (personal):* model, effortLevel, alwaysThinkingEnabled, skipDangerousModePermissionPrompt, cleanupPeriodDays, attribution, env/experimental flags, sandbox.enabled, sandbox.filesystem.allowWrite (handled separately by deploy-config per machine)
  - *Ask (optional):* permissions.allow list, sandbox.enabled

- **`/setup-merge` UX — interactive per-category opt-in**: The skill reads the user's existing `~/.claude/settings.json` and diffs it against what cortex-command contributes — no separate manifest or marker needed. Components already present are shown as "already installed" and skipped. For each remaining component:
  - **Required hooks — merged unconditionally, not a question:** `sync-permissions.py`, `scan-lifecycle.sh`, `validate-commit.sh`, `skill-edit-advisor.sh`, `tool-failure-tracker.sh`, `cleanup-session.sh`, `permission-audit-log.sh`, `worktree-create.sh`, `worktree-remove.sh`
  - **Optional hooks — asked separately:** `setup-gpg-sandbox-home.sh` (GPG/sandbox, macOS-specific), `notify.sh` + `notify-remote.sh` (notifications, require local infrastructure)
  - **Deny rules** — shown as a list; user asked Y/n; recommended yes (safety rules)
  - **Allow list** — shown as a list of what would be added beyond what they have; Y/n
  - **Sandbox network config** — allowed domains + excludedCommands; Y/n
  - **StatusLine** — cortex-command statusline script; Y/n
  - **Plugins** — context7, claude-md-management; Y/n per plugin or as a group
  - **apiKeyHelper** — stub that delegates to `~/.claude/get-api-key-local.sh` or falls back to subscription; Y/n
  Each question shows current value (if any) and what would be added/changed. Only approved components are written.

- **`just setup` vs `just setup-force`**:
  - `just setup` — new default; additive; runs collision detection, installs `new`/`update` targets, skips conflicts, prints pending list for `/setup-merge`
  - `just setup-force` — current behavior; destructive symlink model; what the primary user (repo owner) runs on their own machine

- **`settings.json` deny/allow conflict handling**: If a user's existing deny rules contradict cortex-command's allow list (or vice versa), `/setup-merge` surfaces the conflict for manual resolution rather than applying any automatic merge. The user decides.

- **`apiKeyHelper` — stub approach**: Ship `claude/get-api-key.sh` in the repo. The stub calls `~/.claude/get-api-key-local.sh` if it exists, returns empty otherwise. `apiKeyHelper` in `settings.json` points to the symlinked stub. Subscription users: stub returns empty, Claude Code and runner.sh fall back to subscription cleanly. API key users: put switching logic in `~/.claude/get-api-key-local.sh` (managed by private machine-config). Runner.sh reads the stub from `~/.claude/settings.json` and handles empty return as subscription billing (existing behavior, lines 46–65). Verification required: confirm Claude Code interactive startup handles an `apiKeyHelper` that returns empty without error.
