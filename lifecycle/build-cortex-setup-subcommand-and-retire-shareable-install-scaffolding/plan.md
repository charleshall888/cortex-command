# Plan: build-cortex-setup-subcommand-and-retire-shareable-install-scaffolding

## Overview

Pure-retirement PR: delete the shareable-install scaffolding (setup-merge skill, `just setup`/`deploy-*` recipes, `claude/Agents.md`, `claude/rules/`, `claude/reference/`, `claude/settings.json`, `hooks/cortex-notify.sh`, and the `setup` argparse subparser) with no replacement subcommand. Doc updates land in the same PR and are committed **before** the deletions so intermediate commits never reference surfaces the same commit deleted.

## Tasks

### Task 1: Rewrite `README.md` distribution/setup sections

- **Files**: `README.md`
- **What**: Replace all text that instructs users to run `just setup`, `/setup-merge`, or reads as if deploys happen via symlinks. New flow: `curl | sh` bootstrap (ticket 118) → `uv tool install -e .` provides the `cortex` CLI → `/plugin install` in Claude Code (plugins ship skills/hooks/bin via ticket 120/121/122).
- **Depends on**: none
- **Complexity**: simple
- **Context**: lines to rewrite (from grep audit): `README.md:76-88` (back-up warning + quickstart block), `README.md:117-119` (optional hooks / `/setup-merge` remark), `README.md:170` (settings template paragraph), `README.md:186` (command reference). Keep structural headings stable; rewrite prose only. The bootstrap script itself doesn't exist yet (ticket 118), so phrase commands as the end-state flow with a note that bootstrap is pending if the README already acknowledges that.
- **Verification**: `grep -E "just setup|just deploy-|/setup-merge|cortex setup|~/.claude/rules|~/.claude/reference" README.md` — pass if zero matches.
- **Status**: [ ] pending

### Task 2a: Rewrite `docs/setup.md` intro, quickstart, and install walkthrough — plus targeted self-hoster settings reference

- **Files**: `docs/setup.md`
- **What**: Replace the top-of-file install narrative AND add a targeted "What to put in your own `~/.claude/settings.json`" section for self-hosters who don't have the maintainer's machine-config.

  **Part A — install walkthrough.** Scope: intro paragraph, quickstart block around `:13-48`, optional-hooks / `setup-merge` paragraphs around `:54-71`, and the "forking" paragraph at `:169`. Write a new walkthrough: (a) bootstrap prerequisites (`uv` installed, `claude` CLI installed), (b) `curl | sh` install (placeholder/TBD if 118 hasn't landed), (c) `/plugin marketplace add charleshall888/cortex-command` inside Claude, (d) `/plugin install cortex-interactive@cortex-command` (+ `cortex-overnight-integration` optional), (e) pointer to ticket 119's `cortex init` for per-repo setup.

  **Part B — self-hoster settings reference.** Add a new section titled "Recommended `~/.claude/settings.json` entries" covering only the load-bearing generic pieces. Do NOT ship a copy of the maintainer's full allow list or personal preferences (model, effortLevel, attribution, env vars, etc.) — those are personal. Cover exactly:
  - **`sandbox.excludedCommands`**: `["gh:*", "git:*", "WebFetch", "WebSearch"]` — critical because git/gh run unsandboxed for GPG signing and hook child processes; document that changing this breaks sandbox-excluded command behavior.
  - **`sandbox.autoAllowBashIfSandboxed: true`** — required for the overnight runner's sandbox-gated execution.
  - **`sandbox.allowedDomains`** — list the specific domains cortex-command requires for network access (api.github.com, raw.githubusercontent.com, registry.npmjs.org, *.anthropic.com — pull the current list from git history of `claude/settings.json` at time of writing).
  - **`sandbox.filesystem.allowWrite`** — reference `cortex init` (ticket 119) as the mechanism that adds per-repo overnight-session write paths automatically; no need to hand-edit.
  - **`statusLine.command`** — wire to the absolute install path `$HOME/.cortex/claude/statusline.sh` (or wherever the clone lives), with a note that it's optional and cortex-coupled.
  - **`permissions.deny`** — brief mention that a conservative deny list (sudo, `rm -rf`, force push, read secrets) is a safety baseline; link to git history of `claude/settings.json` for a starting template. Don't paste the full 80-item list inline.
  - Explicitly NOT covered: `permissions.allow` (users compose their own), `env`, `model`, `effortLevel`, `attribution`, `enableAllProjectMcpServers`, `alwaysThinkingEnabled`, `skipDangerousModePermissionPrompt`, `skipAutoPermissionPrompt` — all personal preference.

  Finish the section with: "For the exact historical template including the maintainer's personal allow list, see `git show HEAD:claude/settings.json` on the pre-117 commit."
- **Depends on**: none
- **Complexity**: complex
- **Context**: handles roughly the first two-thirds of the file (intro through "forking"), PLUS the new self-hoster settings reference section inserted before the "forking" paragraph. The "What `just setup` Does" reference table (`:79-106`) and the shadow-copy `cp -R` trap section (`:221-236`) belong to Task 2b.
- **Verification**: (a) `awk 'NR<=180' docs/setup.md | grep -E "just setup|just deploy-|/setup-merge|cortex setup|~/.claude/rules|~/.claude/reference|cortex-notify"` — pass if zero matches; (b) `grep -c "excludedCommands\|autoAllowBashIfSandboxed\|statusLine" docs/setup.md` — pass if count ≥ 3 (confirms the self-hoster reference section landed).
- **Status**: [ ] pending

### Task 2b: Delete `docs/setup.md` deploy-mechanism table and shadow-copy trap section

- **Files**: `docs/setup.md`
- **What**: Second-half cleanup. (a) Delete the "What `just setup` Does" mechanism table (`:79-106`) — under the new plugin model there is no `just setup` mechanism to document. (b) Delete the `cp -R` symlink trap section (`:221-236`) entirely. Of the four symlinks the section warned about (`settings.json`, `statusline.sh`, `notify.sh`, `CLAUDE.md`), three are deleted by this ticket and the fourth (`statusline.sh`) is no longer symlinked to `~/.claude/` by anything cortex ships — it becomes an absolute-path reference in the user's own `settings.json` (machine-config's responsibility). A full warning section about one file doesn't earn its place. If the maintainer later wants to document the statusline-specific caveat, it goes in `docs/` as a brief note, not a multi-paragraph section.
- **Depends on**: [2a]
- **Complexity**: simple
- **Context**: same file as 2a, sequenced after to avoid edit conflicts. After this task, a full-file grep for the retired terms must return zero.
- **Verification**: `grep -E "just setup|just deploy-|/setup-merge|cortex setup|~/.claude/rules|~/.claude/reference|cortex-notify" docs/setup.md` — pass if zero matches across the full file.
- **Status**: [ ] pending

### Task 3: Update `CLAUDE.md` symlink-architecture and deploy-bin sections

- **Files**: `CLAUDE.md`
- **What**: Replace the "Symlink Architecture" / "Key symlinks" table (lines 20-31) with a brief paragraph noting that cortex-command ships as a CLI (`uv tool install -e .`) + plugins (`/plugin install`) and no longer deploys symlinks into `~/.claude/`. Drop the `Full setup: just setup` bullet (line 37). Replace the "New global utilities follow the deploy-bin pattern" sentence at lines 58-59 with a pointer to `just --list` or a note that global utilities now ship via the `cortex-interactive` plugin's `bin/` directory (ticket 120 scope).
- **Depends on**: none
- **Complexity**: simple
- **Context**: this file is loaded into every session via `claudeMd`, so keep it tight — the rewrites are fact-fix, not re-architecture. Preserve the "Always commit using the `/commit` skill" and `just` dependency mentions. Spec R12 acceptance: `grep -E "Key symlinks|deploy-bin pattern|~/.claude/hooks|~/.claude/skills|just setup" CLAUDE.md` returns zero.
- **Verification**: `grep -E "Key symlinks|deploy-bin pattern|~/\.claude/hooks|~/\.claude/skills|just setup" CLAUDE.md` — pass if zero matches.
- **Status**: [ ] pending

### Task 4: Delete root-level `Agents.md`

- **Files**: `Agents.md` (repo root)
- **What**: Delete the root-level `Agents.md`. This is the project-local AGENTS.md-convention orientation file (for Codex/aider-style agents), separate from the deploy-source `claude/Agents.md` (which R3/Task 11 deletes) and separate from `CLAUDE.md` (which Task 3 updates). Maintainer only uses Claude Code, so the AGENTS.md convention file is unused; dropping it eliminates a stale orientation doc that would otherwise need parallel maintenance with `CLAUDE.md`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `git rm Agents.md`. Nothing symlinks this file anywhere (the deploy is from `claude/Agents.md`, not `Agents.md`). Content is near-duplicate of `CLAUDE.md` and also contains stale "All config is deployed via symlinks" prose that would otherwise need a rewrite. Simpler to delete. If the maintainer ever adopts a non-Claude-Code agent that reads AGENTS.md, they can recreate a thin file pointing at `CLAUDE.md` at that time.
- **Verification**: (a) `test -f Agents.md; echo $?` → `1`; (b) `grep -rn "Agents\.md" . --include="*.md" --include="*.py" --include="*.sh" --include="*.json" --include="justfile" --exclude-dir=.git --exclude-dir=lifecycle --exclude-dir=research --exclude-dir=retros --exclude-dir=.claude --exclude-dir=backlog/archive` returns only references that Tasks 5, 6, 7, and 11 will clean up (docs/agentic-layer.md:287, skills/requirements/SKILL.md:74, non-complete backlog items, claude/Agents.md internal self-reference — all handled elsewhere).
- **Status**: [ ] pending

### Task 5: Targeted edits to `docs/backlog.md`, `docs/agentic-layer.md`, `docs/overnight-operations.md`

- **Files**: `docs/backlog.md`, `docs/agentic-layer.md`, `docs/overnight-operations.md`
- **What**: Three targeted doc edits: (a) `docs/backlog.md:205-215` — the "Add a symlink entry to `just deploy-bin`" paragraph becomes "add the entry to the `cortex-interactive` plugin's `bin/` directory" (or note that bin/ deployment is plugin-owned post-120). (b) `docs/agentic-layer.md:204, 266, 287` — three references to `cortex-notify.sh` and `context-file-authoring.md` (references `Agents.md`); reword to reflect that notify moves to machine-config and reference docs ship via plugins. (c) `docs/overnight-operations.md:411, 467` — replace the literal `~/.claude/notify.sh` + `claude/settings.json hooks` prose with the plugin-native equivalent or mark the notify step as user/machine-config responsibility.
- **Depends on**: none
- **Complexity**: simple
- **Context**: these are narrow in-paragraph edits, not structural rewrites. No new content needed beyond renaming the deploy mechanism. For `docs/overnight-operations.md:467`, the sentence enumerates hook scripts and their settings.json wiring — if keeping the educational value, reframe as "plugin hook manifests" rather than `settings.json`.
- **Verification**: `grep -E "just setup|just deploy-|/setup-merge|cortex setup|cortex-notify\.sh|~/\.claude/rules|~/\.claude/reference" docs/backlog.md docs/agentic-layer.md docs/overnight-operations.md` — pass if zero matches.
- **Status**: [ ] pending

### Task 6: Update skill-embedded references to retired surfaces

- **Files**: `skills/overnight/SKILL.md`, `skills/morning-review/references/walkthrough.md`, `skills/lifecycle/SKILL.md`, `skills/lifecycle/references/specify.md`, `skills/lifecycle/references/plan.md`, `skills/requirements/SKILL.md`
- **What**: Surgical text edits so the R11 and R3 grep audits return zero matches inside `skills/`. Five classes of edit: (a) `skills/overnight/SKILL.md:307` — "run `just deploy-bin` first" becomes "install the `cortex-interactive` plugin". (b) `skills/morning-review/references/walkthrough.md:614` — same rewording for the "`git-sync-rebase.sh` not found" branch. (c) `skills/lifecycle/SKILL.md:279` and (d) `skills/lifecycle/references/{specify,plan}.md` (lines 157 and 249) — drop the `(see ~/.claude/reference/output-floors.md for expanded definitions)` parenthetical entirely; the underlying reference doc is deleted by Task 10 and won't exist for the interactive skill to load. Keep the surrounding "these approval surface fields" prose intact. (e) `skills/requirements/SKILL.md:74` — drop the "/Agents.md" fragment from the bullet "CLAUDE.md/Agents.md or equivalent project instructions" (becomes "CLAUDE.md or equivalent project instructions") so R3's `Agents\.md` grep clears.
- **Depends on**: none
- **Complexity**: simple
- **Context**: these skills currently live at `skills/*/` and are symlinked on old installs. In the new plugin world they move into `plugins/cortex-interactive/` (ticket 120) where the reference pointers will be re-added using `${CLAUDE_PLUGIN_ROOT}/references/`. This ticket removes the dead pointers; ticket 120 re-adds them in the plugin-native form.
- **Verification**: `grep -rn "just deploy-\|just setup\|/setup-merge\|setup-merge\|cortex setup\|~/\.claude/reference\|~/\.claude/rules\|Agents\.md" skills/` — pass if zero matches. (Grep superset matches Task 13's audit regex to prevent latent stale references surviving to the deletion phase.)
- **Status**: [ ] pending

### Task 7: Minimally reconcile active backlog items flagged by R11

- **Files**: `backlog/118-bootstrap-installer-curl-sh-pipeline.md`, `backlog/120-cortex-interactive-plugin.md`, `backlog/115-port-overnight-runner-into-cortex-cli.md`, `backlog/index.json`, `backlog/index.md`, plus any other non-complete items returned by the R11 grep — enumerate at task start via the R11 audit command and restrict edits to non-complete items only; regenerate the indexes after edits.
- **What**: Spec R11 Acceptance: `grep ... backlog/ | filter non-complete files` must return zero matches after this PR. Spec Technical Constraints says this is advisory, but R11's own Acceptance is binary — resolve by doing the minimum text edit per file that clears the match while preserving semantic intent. Example: in `118-bootstrap-installer-curl-sh-pipeline.md`, the line `cortex upgrade: git -C ~/.cortex pull && cortex setup --verify-symlinks` becomes `cortex upgrade: git -C ~/.cortex pull` with a trailing "`— 118's author finalizes upgrade semantics`" note. Do **not** redesign any sibling ticket's scope — every semantic change is the sibling's author to make; 117 just flushes stale command names.
- **Depends on**: none
- **Complexity**: simple
- **Context**: run `grep -rln "just setup\|just deploy-\|/setup-merge\|setup-merge\|cortex setup\|~/.claude/rules\|~/.claude/reference" backlog/ | while read f; do awk "/^status: (complete|abandoned)/{exit 0} END{exit 1}" "$f" || echo "$f"; done` at task start to get the exact target list; edit each. Treat backlog items with `status: complete` OR `status: abandoned` as immutable history. The plan's enumeration at author time identifies 118, 120, 115 as worked examples, but the grep typically also surfaces 119, 113, 125, and 128 — each of these carries load-bearing cross-ticket prose (119:34 migration statement, 113:30 epic-scope enumeration, 115:38 shared-contract claim, 120:25 causal justification). For files where the match lives inside argument/causal prose rather than a stale command name, do NOT attempt a text-only rewrite — surface the case to the user as an open decision and mark the file as deferred (consistent with Veto Surface #3: advisory mode for the hard cases).
- **Verification**: `bash -c 'grep -rln "just setup\|just deploy-\|/setup-merge\|setup-merge\|cortex setup\|~/\.claude/rules\|~/\.claude/reference" backlog/ 2>/dev/null | while read f; do awk "/^status: (complete|abandoned)/{exit 0} END{exit 1}" "$f" 2>/dev/null || echo "$f"; done'` — pass if output is empty (or matches a user-approved deferral list). Regenerate `backlog/index.{json,md}` via `python3 backlog/generate_index.py` after edits.
- **Status**: [ ] pending

### Task 8: Delete `.claude/skills/setup-merge/` directory

- **Files**: `.claude/skills/setup-merge/SKILL.md`, `.claude/skills/setup-merge/scripts/merge_settings.py`, `.claude/skills/setup-merge/` (rmdir after contents gone)
- **What**: Remove the project-local `/setup-merge` skill and its merge helper in full. The `classify()` helper in `merge_settings.py` is not ported — R1 is explicit on this.
- **Depends on**: [1, 2a, 2b, 3, 4, 5, 6, 7]
- **Complexity**: simple
- **Context**: `git rm -r .claude/skills/setup-merge/`. The only Python references to `merge_settings` in the repo are inside this directory (verified by research `§Codebase Analysis`); no callers outside.
- **Verification**: `test -e .claude/skills/setup-merge; echo $?` — pass if output is `1`. Then `grep -rn "setup-merge\|merge_settings" . --include="*.md" --include="*.json" --include="*.py" --include="justfile" --exclude-dir=.git --exclude-dir=lifecycle --exclude-dir=research --exclude-dir=retros --exclude-dir=backlog/archive` — pass if zero matches.
- **Status**: [ ] pending

### Task 9: Delete retired `justfile` recipes and update preserved-recipe prose references

- **Files**: `justfile`
- **What**: Remove the nine recipes listed in spec R2: `setup` (10-34), `setup-force` (37-118), `deploy-bin` (122-175), `deploy-reference` (178-221), `deploy-skills` (224-261), `deploy-hooks` (264-331), `deploy-config` (334-408), `check-symlinks` (727-773), `verify-setup` (776-831). Delete each recipe and its leading blank/heading lines cleanly. Leave every other recipe untouched **except** for one prose fix: `setup-tmux-socket` (around `justfile:518-553`) reads `$HOME/.claude/settings.json` and prints an error pointing the user at "`just setup`" — rewrite that error message to reference the new install flow ("install the cortex-interactive plugin" or similar) since `just setup` no longer exists. Do not change `setup-tmux-socket`'s behavior otherwise.
- **Depends on**: [1, 2a, 2b, 3, 4, 5, 6, 7]
- **Complexity**: complex
- **Context**: line numbers come from the research `§Codebase Analysis` + spec R2; they may drift slightly if the justfile has been edited since research was done — locate each recipe by header line (`setup:`, `deploy-bin:`, etc.) rather than by absolute line number. For the `setup-tmux-socket` prose fix, search within the recipe body for the literal string `just setup` and rewrite the error message it appears in. Multi-recipe edits; do them in one pass and verify `just --list` is clean afterward.
- **Verification**: (a) `just --list | grep -E "^(setup|setup-force|deploy-(bin|reference|skills|hooks|config)|check-symlinks|verify-setup)\b"` — pass if zero matches; (b) `grep -E "^(setup|setup-force|deploy-(bin|reference|skills|hooks|config)|check-symlinks|verify-setup):" justfile` — pass if zero matches; (c) `just --list` exits 0 (no parse error from the edits); (d) `grep -n "just setup" justfile` — pass if zero matches (confirms setup-tmux-socket's error message was updated).
- **Status**: [ ] pending

### Task 10: Delete `claude/rules/` and `claude/reference/` directories

- **Files**: `claude/rules/global-agent-rules.md`, `claude/rules/sandbox-behaviors.md`, `claude/rules/` (rmdir), `claude/reference/context-file-authoring.md`, `claude/reference/claude-skills.md`, `claude/reference/parallel-agents.md`, `claude/reference/output-floors.md`, `claude/reference/` (rmdir)
- **What**: Full directory deletions per spec R4 and R5. Rule content migrates into skills (by tickets 120/121) and reference material migrates to plugin `references/` (by tickets 120/121) — this ticket does **not** pre-migrate.
- **Depends on**: [1, 2a, 2b, 3, 4, 5, 6, 7]
- **Complexity**: simple
- **Context**: `git rm -r claude/rules claude/reference`. Spec Non-Requirements reiterates that no content is inlined anywhere by 117.
- **Verification**: `test -d claude/rules; echo $?` and `test -d claude/reference; echo $?` — both output `1`.
- **Status**: [ ] pending

### Task 11: Delete `claude/Agents.md`, `claude/settings.json`, `hooks/cortex-notify.sh` and update in-repo consumers

- **Files**: `claude/Agents.md`, `claude/settings.json`, `hooks/cortex-notify.sh`, `cortex_command/dashboard/alerts.py`, `cortex_command/dashboard/tests/test_alerts.py`
- **What**: Three file deletions per spec R3, R6, R7 PLUS update to the dashboard alert subsystem that depends on `hooks/cortex-notify.sh` at runtime. `cortex_command/dashboard/alerts.py:110` computes `notify_sh = root / "hooks" / "cortex-notify.sh"` and subprocesses it from `fire_notifications()`, which is wired through `poller.py` to `app.py` (live dashboard code, not just a hook). After this ticket, the notify helper is machine-config's responsibility and is not shipped from cortex-command. Remove the subprocess call path from `alerts.py` entirely (evaluate_alerts can still generate alert objects; the subprocess-out-to-shell path just goes away — or is replaced with a logging-only equivalent). Update `test_alerts.py:174` to drop the `cortex-notify.sh`-specific assertion or delete the test case if it was only about the notify subprocess. The user (maintainer) is handling the handoff of the now-deleted `~/.claude/settings.json` and `~/.claude/notify.sh` targets to machine-config separately — see Veto Surface for the pre-merge coordination question.
- **Depends on**: [1, 2a, 2b, 3, 4, 5, 6, 7]
- **Complexity**: complex
- **Context**: `git rm claude/Agents.md claude/settings.json hooks/cortex-notify.sh`; edit alerts.py + test_alerts.py to remove the notify-subprocess path. Spec R3 Acceptance includes a grep for `Agents\.md`; spec R7 includes a grep for `cortex-notify\|notify\.sh`. Without the alerts.py edit, R7's grep fails against the current tree (cortex_command/ is not in the exclude-dir list).
- **Verification**: (a) `test -f claude/Agents.md; echo $?` → `1`; (b) `test -f claude/settings.json; echo $?` → `1`; (c) `test -f hooks/cortex-notify.sh; echo $?` → `1`; (d) `grep -rn "Agents\.md" . --include="*.md" --include="*.py" --include="*.sh" --include="*.json" --include="justfile" --exclude-dir=.git --exclude-dir=lifecycle --exclude-dir=research --exclude-dir=retros --exclude-dir=.claude --exclude-dir=backlog/archive` returns zero; (e) `grep -rn "cortex-notify\|notify\.sh" . --include="*.md" --include="*.py" --include="*.sh" --include="*.json" --include="justfile" --exclude-dir=.git --exclude-dir=lifecycle --exclude-dir=research --exclude-dir=retros --exclude-dir=.claude --exclude-dir=backlog/archive` returns zero; (f) `pytest cortex_command/dashboard/tests/test_alerts.py` — pass if exit 0 (the test file still runs after the notify-path edit).
- **Status**: [ ] pending

### Task 12: Remove `setup` subparser from `cortex_command/cli.py`

- **Files**: `cortex_command/cli.py`
- **What**: Per spec R8, delete the `setup = subparsers.add_parser("setup", ...)` block and its `_make_stub("setup")` dispatch (currently `cortex_command/cli.py:63-68`). Also update the parser description at line 42 which says "orchestrates overnight runs, MCP server, and setup." — drop "and setup" or rewrite to reflect the remaining subcommands.
- **Depends on**: [1, 2a]
- **Complexity**: simple
- **Context**: the file currently defines five subparsers in order: `overnight`, `mcp-server`, `setup`, `init`, `upgrade`. Remove only the `setup` block (4 lines of parser wiring + 1 blank line). Other subparsers and `_make_stub` helper stay. No changes to `[project.scripts]` in `pyproject.toml` (spec Technical Constraints).
- **Verification**: (a) `python -c "from cortex_command.cli import _build_parser; p = _build_parser(); choices = p._subparsers._actions[-1].choices; import sys; sys.exit(0 if 'setup' not in choices else 1)"` → exit 0; (b) `cortex --help 2>&1 | grep -c '^\s*setup'` → output `0`; (c) `grep -n '"setup"' cortex_command/cli.py` → zero matches.
- **Status**: [ ] pending

### Task 14: Add project-scope `.claude/settings.json` preserving commit validation

- **Files**: `.claude/settings.json` (new file)
- **What**: Create a minimal project-scope `settings.json` with a single PreToolUse Bash hook wiring `cortex-validate-commit.sh` using Anthropic's documented `$CLAUDE_PROJECT_DIR` env-var pattern. Only this one hook. Other retired hooks either (a) migrate to plugins via 120/121, (b) move to machine-config, or (c) go dormant until rewired. The point of Task 14 is to ensure commit-message validation keeps firing when the maintainer edits cortex-command itself, regardless of what happens with `~/.claude/settings.json` during the 117↔120/121 gap.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The file should contain a single PreToolUse hook entry with matcher `Bash` invoking `"$CLAUDE_PROJECT_DIR"/hooks/cortex-validate-commit.sh`. Match the structure of the `hooks.PreToolUse[].hooks[]` array used in the retired `claude/settings.json` for `cortex-validate-commit.sh`, but swap the command string from `~/.claude/hooks/cortex-validate-commit.sh` to the env-var form. Do not include any other hook, permission, sandbox, or statusline key — this file's purpose is the single hook, not a new global template. Project-scope settings layer on top of user settings (per Claude Code's configuration-scopes semantics), so the file activates only when a Claude session is open inside cortex-command. `.claude/settings.local.json` already exists at the same level for per-machine permission allows — keep the two files separate.
- **Verification**: (a) `test -f .claude/settings.json; echo $?` → `0`; (b) `python3 -c "import json; json.load(open('.claude/settings.json'))"` — pass if exit 0 (valid JSON); (c) `python3 -c "import json; d=json.load(open('.claude/settings.json')); cmd=d['hooks']['PreToolUse'][0]['hooks'][0]['command']; assert 'CLAUDE_PROJECT_DIR' in cmd and 'cortex-validate-commit.sh' in cmd" ` — pass if exit 0.
- **Status**: [ ] pending

### Task 13: Run the full audit and test suite

- **Files**: (read-only task — no files modified)
- **What**: Final gate. Confirm spec R11 audit is clean across the whole repo (including `scripts/` and `cortex_command/`), run `just test`, and confirm `cortex` CLI parses after R8's change.
- **Depends on**: [1, 2a, 2b, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14]
- **Complexity**: simple
- **Context**: this is the Acceptance surface pulled from spec R11 (repo-wide grep with exclusions) and R13 (test suite passes). No file writes. If a grep surfaces a straggler in a backlog item or doc, loop back to the owning task (1–7, 14) via a new fix-up commit rather than rewriting this task; it's acceptable for the PR history to end with a "fix missed reference" commit after Task 13's audit fires. Extended the audit scope beyond spec R11's listed paths to include `scripts/` (catches `scripts/validate-callgraph.py` which references `claude/reference/claude-skills.md`). `Agents.md` is in the grep path but Task 4 deletes it — no match, no failure.
- **Verification**: (a) `bash -c 'grep -rln "just setup\|just deploy-\|/setup-merge\|setup-merge\|cortex setup\|~/\.claude/rules\|~/\.claude/reference" README.md docs/ CLAUDE.md skills/ backlog/ scripts/ 2>/dev/null | while read f; do awk "/^status: (complete|abandoned)/{exit 0} END{exit 1}" "$f" 2>/dev/null || echo "$f"; done'` — pass if output is empty; (b) `just test` — pass if exit 0; (c) `cortex --help` — pass if exit 0 and output lists exactly four subcommands (`overnight`, `mcp-server`, `init`, `upgrade`); (d) `grep -rn "cortex-notify\|notify\.sh" cortex_command/ hooks/ 2>/dev/null` — pass if zero matches (confirms Task 11's alerts.py edit stuck and hooks/cortex-notify.sh is gone); (e) `test -f .claude/settings.json` → `0` (confirms Task 14 landed).
- **Status**: [ ] pending

## Verification Strategy

End-to-end verification of the retirement:

1. **Structural deletion**: the eight repo surfaces listed in spec R1–R8 are gone (verified per-task above).
2. **Doc consistency**: `grep` audit across `README.md`, `CLAUDE.md`, `docs/`, `skills/`, `scripts/`, and non-complete `backlog/` items returns zero hits for the retired command names and paths (Task 13a). Root `Agents.md` is not in the grep scope because Task 4 deletes it.
3. **Test suite green**: `just test` (pipeline + overnight + pytest) exits 0 after the deletions (Task 13b). No test references `merge_settings.py` or the deleted recipes — if any do, those tests get removed as part of the deletion tasks that strand them.
4. **CLI surface**: `cortex --help` lists exactly `overnight`, `mcp-server`, `init`, `upgrade` (Task 13c); `cortex setup` produces argparse's standard "invalid choice" error.
5. **Preservation checks**: `claude/statusline.sh`, `claude/statusline.ps1` (see Veto Surface), `skills/`, `hooks/`, `claude/hooks/`, `bin/` remain unmodified (spot-check via `git diff` before commit).

**Commit ordering**: To satisfy spec Technical Constraints ("no mid-PR commit references something the same commit deleted"), sequence commits as: Tasks 1, 2a, 2b, 3, 4, 5, 6, 7, 14 (docs + backlog reconciliation + new project-scope settings file), then Tasks 8–12 (deletions — safe to group or split; the docs no longer mention the retired surfaces), then Task 13 (read-only audit; produces no commit). Task 12 (`cli.py`) must commit after Task 1 and Task 2a because those docs describe the `cortex setup` subcommand that Task 12 removes; the plan pins this via `Depends on: [1, 2a]`. Task 14 is independent and can commit at any time.

## Veto Surface

All decisions resolved during plan review (2026-04-23). Resolutions preserved here for audit:

1. **Root `Agents.md` — DELETED (Task 4).** Maintainer confirmed Claude Code is the only agent ecosystem in use; the AGENTS.md-convention file for other agents (Codex/aider/etc.) is unused and carries stale "deployed via symlinks" prose. Simpler to delete than maintain in parallel with `CLAUDE.md`. Task 4 now `git rm`s it.

2. **`claude/statusline.ps1` — preserve.** Windows PowerShell counterpart to `statusline.sh`; symmetric treatment under R9 (cortex-coupled; user wires via machine-config's settings.json using the absolute install path).

3. **Shadow-copy/`cp -R` section in `docs/setup.md` — drop entirely (Task 2b).** Post-117, three of the four files the section warned about are gone; one-file warning doesn't earn its place. If the maintainer later wants a statusline-specific caveat, it goes somewhere lighter than a multi-paragraph section.

4. **Transitional `just setup` shim — none.** Spec Non-Req explicitly rules it out. Users running `just setup` on old muscle-memory will hit `error: recipe 'setup' not found`. Acceptable; deprecation is loud, not silent.

5. **Pre-merge gate for Task 11 on machine-config adoption — accept the gap.** The wiring being retired (`~/.claude/notify.sh` hardcoded in `claude/settings.json:275,289`) does not conform to Anthropic's documented hook-path guidance (env-var-based, e.g., `$CLAUDE_PROJECT_DIR` / `${CLAUDE_PLUGIN_ROOT}`). Preserving it via pre-merge gates would protect a workaround, not a correct behavior. Clean cut; machine-config rewires with conformant paths. Task 14 keeps commit validation alive inside cortex-command itself during the gap.

6. **Task 7 binding vs advisory — binding.** Critical review's specific objection for ticket 118 (`cortex upgrade = git -C ~/.cortex pull && cortex setup --verify-symlinks` → `git -C ~/.cortex pull`) dissolves on closer inspection: once deploys stop, there is no symlink drift for `--verify-symlinks` to detect, so `git pull` alone is semantically correct rather than a behavior deletion. For the harder prose-argument cases (119:34, 113:30, 115:38, 125, 128), the plan's Task 7 context field instructs per-file deferral with user surfacing — that's sufficient without flipping the whole audit to advisory.

## Scope Boundaries

Mirroring spec Non-Requirements:

- **No `cortex setup` subcommand.** R8 removes the 114 stub.
- **No deployment to `~/.claude/` or `~/.local/bin/`.** Cortex-command writes nothing into those paths after this PR.
- **No pre-migration of rule or reference content** into skills or plugin directories (tickets 120/121 do that).
- **No `--merge-settings`, `--verify-symlinks`, `--with-extras`, `--dry-run`, `--prune-orphans` flags.** No `cortex setup` command exists to flag.
- **No cleanup of pre-existing dangling symlinks** in users' `~/.claude/` from prior `just setup` runs (ticket 124 owns this).
- **No management of `~/.claude/CLAUDE.md`** (always user-owned).
- **No per-repo sandbox `allowWrite` setup** in `settings.local.json` (moves to ticket 119's `cortex init`; backlog file updated in prior session).
- **No test coverage added** (R13 — this is pure retirement).
- **No handling of the 117↔120/121 gap window.** Old installs' skill symlinks into `claude/reference/` will silently fail reference-doc reads between 117 merging and 120/121 landing. Maintainer accepts.
- **No handling of the 117↔machine-config gap window for `~/.claude/settings.json` and `~/.claude/notify.sh`.** After 117 merges, these two symlinks dangle on the maintainer's machine. Functional impact: most hook wirings stop firing (commit validation survives via Task 14's project-scope settings), permission allow/deny list goes away (Claude Code falls back to prompt-on-everything defaults — UX regression, not security regression), statusline stops rendering, sandbox config falls back to defaults. Machine-config absorbs these as personal machine setup; the maintainer sequences the machine-config side around the merge. Ticket 124 is responsible for scripted dangling-symlink cleanup, not 117.
- **`~/.claude/CLAUDE.md` is NOT machine-config's responsibility — it's a design-violation cleanup.** Cortex-command historically shipped `claude/Agents.md` as a symlink target for `~/.claude/CLAUDE.md`, violating the design rule that cortex is rules-only (never installs global CLAUDE.md content; see memory `project_rules_only_not_claudemd.md`). Task 11's deletion of `claude/Agents.md` removes the misplaced content. Maintainer's post-merge manual cleanup: `rm ~/.claude/CLAUDE.md` to remove the dangling symlink. No replacement ships; the maintainer has stated they do not want a global CLAUDE.md. If the maintainer later wants one, they write their own personal file.
- **Post-merge manual cleanup (not a task, maintainer's own one-time action)**: `rm ~/.claude/CLAUDE.md ~/.claude/settings.json ~/.claude/notify.sh` (plus any `~/.claude/rules/cortex-*.md` and `~/.claude/reference/*.md` that are now dangling) — these are host-side symlinks that cortex-command no longer has targets for. Ticket 124 will eventually script this; until then it's a one-liner the maintainer runs after pulling 117.
- **No archive of the deleted `setup-merge/` skill.** Git history is the archive.
- **No trim of `claude/settings.json`** — whole file is deleted (so trimming doesn't apply), but this also means no separate chore ticket for template cleanup is spawned from 117.
- **No fix of the `claude/settings.json:361` vs `justfile:390-408` path inconsistency** — both files are deleted, so the drift disappears incidentally.
- **No pre-migration of hook scripts into plugin directories.** That is 120/121's work. **Note for ticket 120's author** (flagged during 117's plan phase, hook-home analysis): not every retired hook belongs in `cortex-interactive/hooks/hooks.json`. `cortex-validate-commit.sh` and `cortex-skill-edit-advisor.sh` enforce cortex-command-specific conventions and should not fire in unrelated repos. They belong in cortex-command's own `.claude/settings.json` (project scope — 117's Task 14 establishes this file), NOT in a plugin hooks manifest (which would fire them globally). Overnight-runner hooks (`cortex-scan-lifecycle.sh`, `cortex-cleanup-session.sh`, `cortex-tool-failure-tracker.sh`, `cortex-permission-audit-log.sh`) go to `cortex-overnight-integration`. `cortex-output-filter.sh` is universal-utility (plugin or machine-config). `cortex-notify.sh` is machine-personal (machine-config). Worktree hooks keep their CWD-from-stdin pattern.
