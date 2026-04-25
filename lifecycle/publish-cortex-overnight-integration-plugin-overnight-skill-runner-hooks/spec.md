# Specification: Publish cortex-overnight-integration plugin (overnight skill + runner hooks)

> Epic context: this is the second of two core plugins in the overnight-layer-distribution
> epic ([research/overnight-layer-distribution/research.md](../../research/overnight-layer-distribution/research.md),
> DR-2). The first plugin (`cortex-interactive`) shipped in ticket 120. This ticket ships
> the runner-side complement so users can launch overnight runs from inside Claude Code
> via the MCP control plane (DR-1).

## Problem Statement

Users today initiate overnight runs from a terminal via `cortex overnight start`, which
forces a context switch out of Claude Code. The MCP control-plane server (`cortex mcp-server`,
shipped in ticket 116) exposes five tools that let Claude itself drive overnight runs, but
those tools only become available when a Claude Code plugin registers the server via
`.mcp.json`. This ticket publishes the `cortex-overnight-integration` plugin that bundles
that `.mcp.json` along with the two overnight-side skills (`overnight`, `morning-review`)
and four runner-only hooks. With this plugin enabled, Claude can start, monitor, and review
overnight runs without leaving the chat — the north-star UX of the epic.

## Requirements

1. **Plugin manifest**: `plugins/cortex-overnight-integration/.claude-plugin/plugin.json`
   exists with three fields: `name = "cortex-overnight-integration"`,
   `author = "Charlie Hall <charliemhall@gmail.com>"`, and a `description` that names
   both prerequisites (the `cortex` CLI on PATH and the `cortex-interactive` plugin).
   Acceptance:
   - `jq -er '.name' plugins/cortex-overnight-integration/.claude-plugin/plugin.json` exits 0 and prints `cortex-overnight-integration`.
   - `jq -e '.description | contains("cortex CLI") and contains("cortex-interactive")' plugins/cortex-overnight-integration/.claude-plugin/plugin.json` exits 0.

2. **Skills synced from canonical sources**: `plugins/cortex-overnight-integration/skills/`
   contains `overnight/` and `morning-review/` subdirectories whose contents match the
   top-level `skills/overnight/` and `skills/morning-review/` sources byte-for-byte
   (including `morning-review/references/`).
   Acceptance:
   - `diff -rq skills/overnight/ plugins/cortex-overnight-integration/skills/overnight/` exits 0 with no output.
   - `diff -rq skills/morning-review/ plugins/cortex-overnight-integration/skills/morning-review/` exits 0 with no output.

3. **Runner-only hooks present in plugin tree**: `plugins/cortex-overnight-integration/hooks/`
   contains four scripts, each byte-identical to its source location:
   - `cortex-cleanup-session.sh` ← `hooks/cortex-cleanup-session.sh`
   - `cortex-scan-lifecycle.sh` ← `hooks/cortex-scan-lifecycle.sh`
   - `cortex-tool-failure-tracker.sh` ← `claude/hooks/cortex-tool-failure-tracker.sh`
   - `cortex-permission-audit-log.sh` ← `claude/hooks/cortex-permission-audit-log.sh`
   
   Each is executable (`chmod +x`).
   Acceptance:
   - For each of the four pairs: `cmp -s <source> plugins/cortex-overnight-integration/hooks/<name>` exits 0.
   - `find plugins/cortex-overnight-integration/hooks/ -name 'cortex-*.sh' -not -perm -u+x | wc -l` returns `0`.

4. **Hook manifest with correct schema per event**: `plugins/cortex-overnight-integration/hooks/hooks.json`
   registers each of the four hooks against its actual event type. The manifest pins explicit
   matcher choices per event (no `if needed` ambiguity):
   - `SessionStart` → `cortex-scan-lifecycle.sh`. Matcher omitted (fire on every session start; no source filter needed).
   - `SessionEnd` → `cortex-cleanup-session.sh`. Matcher omitted (per upstream schema, SessionEnd does not take a matcher).
   - `PostToolUse` → `cortex-tool-failure-tracker.sh`. Matcher omitted (the script self-filters on `tool_name == "Bash"` internally; matcher omission means the dispatcher fires for every tool, which is acceptable overhead since the script exits early on non-Bash invocations).
   - `Notification` → `cortex-permission-audit-log.sh`. Matcher omitted (the script self-filters on `notification_type == "permission_prompt"` internally; matcher omission means the dispatcher fires for every notification, which is acceptable since the script exits early on non-matching types).
   
   Acceptance:
   - `jq -r '.hooks | keys[] | ascii_downcase' plugins/cortex-overnight-integration/hooks/hooks.json | sort | tr '\n' ' '` returns `notification posttooluse sessionend sessionstart `.
   - For each event `E in {SessionStart, SessionEnd, PostToolUse, Notification}`: `jq -e --arg E "$E" '.hooks[$E][0].hooks[0] | .type == "command" and (.command | startswith("${CLAUDE_PLUGIN_ROOT}/hooks/cortex-"))' hooks.json` exits 0.
   - `jq -e '.hooks.SessionStart[0].hooks[0].command | endswith("cortex-scan-lifecycle.sh")' hooks.json` exits 0; analogous for SessionEnd→cleanup-session, PostToolUse→tool-failure-tracker, Notification→permission-audit-log.
   - `jq -e '.hooks | to_entries | all(.value[0] | has("matcher") | not)' hooks.json` exits 0 (verifies all four entries omit the matcher field, matching the deliberate decision above).

5. **MCP server registration**: `plugins/cortex-overnight-integration/.mcp.json` contains a
   single `mcpServers.cortex-overnight` entry with `command: "cortex"` and `args: ["mcp-server"]`.
   This file already exists from prior work and the implementation must verify its contents
   match this contract; if it doesn't, the file is rewritten to match.
   Acceptance:
   - `jq -er '.mcpServers["cortex-overnight"].command' plugins/cortex-overnight-integration/.mcp.json` returns `cortex`.
   - `jq -er '.mcpServers["cortex-overnight"].args | join(" ")' plugins/cortex-overnight-integration/.mcp.json` returns `mcp-server`.
   - `jq -e '.mcpServers | length == 1' plugins/cortex-overnight-integration/.mcp.json` exits 0 (no extra servers registered).

6. **Build recipe with per-plugin manifests (bash-3.2-compatible)**: the `build-plugin`
   recipe in `justfile` dispatches per-plugin SKILLS and HOOKS lists. The implementation
   uses bash-3.2-compatible idiom (no `declare -A` associative arrays, no `mapfile`) — see
   Technical Constraints. The recommended shape is a `case "$p" in cortex-interactive)
   SKILLS=(...); HOOKS=(...);; cortex-overnight-integration) SKILLS=(...); HOOKS=(...);;
   esac` block inside the existing `for p in {{BUILD_OUTPUT_PLUGINS}}` loop. Hook source paths
   may live under either `hooks/` or `claude/hooks/` — the per-plugin `HOOKS` array carries
   full source paths so the recipe handles both directories without further branching logic.
   Acceptance:
   - The recipe runs cleanly under `/usr/bin/env bash` on macOS system bash 3.2: `bash --version` may report 3.2.x and `just build-plugin` exits 0.
   - After running `just build-plugin && rm -rf plugins/cortex-overnight-integration/skills && just build-plugin`, the second run produces the same final tree (`diff -rq` against a checkout of the post-first-run state is empty) — verifying the recipe is idempotent and rebuilds from scratch.
   - After `just build-plugin`, `ls plugins/cortex-overnight-integration/skills/` returns exactly two entries: `morning-review` and `overnight`.
   - After `just build-plugin`, `ls plugins/cortex-interactive/skills/ | wc -l` returns `14`.
   - After `just build-plugin`, every entry in `cortex-overnight-integration`'s HOOKS source list (4 paths from R3) corresponds to a byte-identical file in `plugins/cortex-overnight-integration/hooks/` — covered by R3 acceptance, but the build recipe is the producer.
   - Removing one cortex-overnight-integration HOOKS entry from the recipe and rerunning `just build-plugin` removes the corresponding file from the plugin tree on the next run (verifies per-plugin isolation; can be tested manually before final commit).

7. **Pre-commit drift check passes for both plugins**: with the new layout committed,
   `bash .githooks/pre-commit` exits 0 (Phase 1 plugin classification + Phase 4 drift detection).
   Acceptance:
   - After `just build-plugin && git add -A`, running `bash .githooks/pre-commit` exits 0.
   - `git diff --quiet plugins/cortex-overnight-integration/` and `git diff --quiet plugins/cortex-interactive/` both exit 0.

8. **`cortex init` widens sandbox allowWrite scope, with symlink-safety repointed**: the
   `cortex init` subcommand (in `cortex_command/init/handler.py`) registers
   `{repo_root}/lifecycle/` (parent directory with trailing slash) in
   `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array, replacing
   `{repo_root}/lifecycle/sessions/` for fresh `cortex init` runs. The companion
   `scaffold.check_symlink_safety()` call must be repointed at `lifecycle/` (the new
   registered path) so the symlink-escape gate continues to cover what's actually written
   into `settings.local.json`. Existing registrations of the narrower path are left in
   place (`cortex init` is additive). Security rationale is in Technical Constraints below.
   Acceptance:
   - In a fresh test repo with no prior `cortex init`, after running `cortex init`, `jq -e --arg p "$(realpath .)/lifecycle/" '.sandbox.filesystem.allowWrite | index($p)' ~/.claude/settings.local.json` exits 0.
   - `grep -E 'check_symlink_safety|symlink_safety' cortex_command/init/handler.py | grep -v sessions` returns at least one match (verifies the function call is wired against the parent path, not just `lifecycle/sessions/`).
   - In a test repo that already has `{repo_root}/lifecycle/sessions/` registered, after running `cortex init` again, both entries appear in the array (additive, no removal).
   - With `lifecycle/` symlinked outside the repo, `cortex init` exits non-zero and prints a symlink-escape error (the existing R13-style escape gate is preserved at the new scope).

9. **`requirements/project.md` Architectural Constraints text reflects new sandbox scope**:
   the file's "Per-repo sandbox registration" sentence is updated to name `lifecycle/` instead
   of `lifecycle/sessions/`, eliminating silent drift between the project requirements and
   the actual `cortex init` behavior.
   Acceptance:
   - `grep -F "lifecycle/sessions/" requirements/project.md | grep -i sandbox` returns no matches.
   - `grep -F "lifecycle/' path" requirements/project.md` (or equivalent describing the wider scope) returns at least one match in the Architectural Constraints section.

10. **Local dogfooding documented in `docs/plugin-development.md`**: a new file
    `docs/plugin-development.md` documents the marketplace-add and plugin-install commands
    a maintainer runs to dogfood `cortex-overnight-integration` (and any future in-repo
    plugin) before ticket 122 publishes the production marketplace.
    Acceptance:
    - `test -f docs/plugin-development.md` exits 0.
    - `grep -E '^\s*/plugin marketplace add' docs/plugin-development.md` returns at least one line referencing the repo path or `$PWD`.
    - `grep -E '^\s*/plugin install cortex-overnight-integration' docs/plugin-development.md` returns at least one line.

11. **Plugin enables under marketplace flow**: a maintainer can locally dogfood by following
    `docs/plugin-development.md`, registering this repo as a marketplace and installing
    `cortex-overnight-integration` without ticket 122 having shipped.
    Acceptance: Interactive/session-dependent: from a terminal-launched Claude Code session,
    after `/plugin marketplace add /Users/charlie.hall/Workspaces/cortex-command` and
    `/plugin install cortex-overnight-integration@cortex-command`, `/plugin list` shows
    `cortex-overnight-integration` enabled and `/cortex:overnight` is invocable.
    (Rationale: plugin enable is a Claude-Code session operation; cannot be exercised from a
    shell command alone.)

12. **MCP server connects when plugin enabled in terminal-launched Claude Code**: with
    `cortex` on PATH (the user's actual launch context — terminal), enabling the plugin
    starts `cortex mcp-server` and exposes the five overnight tools.
    Acceptance: Interactive/session-dependent: in a terminal-launched Claude Code session
    with the plugin enabled, `/mcp` lists a server named `cortex-overnight` with status
    `connected`, and the server exposes tools named `overnight_start_run`, `overnight_status`,
    `overnight_logs`, `overnight_cancel`, `overnight_list_sessions`. (Rationale: MCP server
    registration is a Claude-Code session-level concern; not invocable as a shell command.)

13. **Notification hook fires on permission prompts**: enabling the plugin and triggering
    a permission prompt during a Claude Code session causes
    `cortex-permission-audit-log.sh` to append a line to `$TMPDIR/claude-permissions-*.log`
    (the path the script writes to per its top-of-file comment). This guards against the
    silent-dead-hook failure mode where a wrong matcher schema would make the hook
    invocable but never invoked.
    Acceptance: Interactive/session-dependent: with the plugin enabled and a permission
    prompt triggered, `ls $TMPDIR/claude-permissions-*.log 2>/dev/null | head -1 | xargs -I{} test -s {}` exits 0 (file exists and is non-empty). (Rationale: triggering a permission prompt requires an interactive Claude Code session.)

## Non-Requirements

- **Production marketplace.json**: ticket 122 owns the repo-root `.claude-plugin/marketplace.json`
  that lists this and three sister plugins. This ticket exposes the plugin via local dogfooding
  only.
- **Renaming the two "session" concepts**: `lifecycle/sessions/{run_id}/` (runner artifacts) and
  `lifecycle/{feature}/.session` (feature-session marker) overload the word. The naming smell
  predates this ticket (cortex-interactive already ships the lifecycle skill that writes the
  marker). Cleanup belongs in a separate ticket if pursued — relocating the marker out of
  `lifecycle/{feature}/` would also enable a narrower R8 sandbox scope, but that's deferred.
- **IDE-plugin PATH wrapper**: a launcher wrapper that resolves `cortex` against multiple known
  install paths is out of scope. The user's actual workflow is terminal-launched Claude Code,
  where shell PATH is inherited and `~/.local/bin/cortex` resolves cleanly.
- **Moving bin scripts to CLI tier**: `cortex-update-item`, `cortex-generate-backlog-index`,
  `cortex-create-backlog-item` stay in cortex-interactive's `bin/`. The cross-plugin reference
  from cortex-overnight-integration's skills is the architecture (one-directional), not a
  smell.
- **Moving morning-review to cortex-interactive**: morning-review stays in
  cortex-overnight-integration. DR-2 split holds.
- **Runtime enforcement of cortex-interactive presence**: no `command -v cortex-update-item`
  guards inserted into SKILL.md bodies. Plugin.json `description` carries the install
  documentation; the runtime ENOENT signal at first use is sufficient for the rare standalone
  install case.
- **Ticket 118 (curl bootstrap), ticket 119 (cortex init scaffolder), ticket 124 (migration
  script), ticket 125 (homebrew tap)**: all separate tickets in the same epic.
- **Custom version field in plugin.json**: omitted, matching cortex-interactive precedent.
  Git SHA drives plugin updates for git-hosted marketplaces.
- **Adding a `matcher` field for filtering at the hooks.json layer**: omitted on purpose
  (R4). Each hook script self-filters internally; pinning a matcher would either duplicate
  the filter logic or risk drift if the script's filter changes. Omission is the deliberate
  resolution.

## Edge Cases

- **User installs cortex-overnight-integration without cortex-interactive**: `morning-review`
  hits `cortex-update-item: command not found` at the first invocation that needs it; the
  shell error is itself actionable and the plugin.json description told them at install time.
  No code change needed; documented in plugin description.
- **`cortex init` re-run on a repo with the narrower `lifecycle/sessions/` already registered**:
  registration is additive — both entries land in the array. The wider entry supersedes
  semantically; the narrower entry is harmless redundancy.
- **`claude/hooks/cortex-tool-failure-tracker.sh` or `cortex-permission-audit-log.sh` are
  modified upstream after ticket 121 ships**: pre-commit drift check fires (Phase 4) when
  the source file diverges from the plugin copy until the next `just build-plugin` runs.
  This matches the existing cortex-interactive contract.
- **Plugin enabled but `cortex` not on PATH**: the four hooks fail gracefully (`command -v cortex`
  guards already present in `cortex-scan-lifecycle.sh`); the MCP server fails to register and
  surfaces in `/plugin` Errors and `~/.claude/mcp-server-cortex-overnight.log`. The plugin's
  skills and hooks remain installed but the MCP tools become unavailable. No silent failure.
- **`hooks.json` schema shifts upstream (Notification or PostToolUse field requirements
  change)**: a Claude Code update could break the registration. Detected at first session
  via `/plugin` Errors; mitigated by the standard-issue plugin update verb. Out of scope to
  pre-empt — but R4 pins matcher choices explicitly so that R13 (hook-fires smoke test) will
  catch drift on the next run instead of letting a silent-dead-hook ship.
- **Build recipe runs against a not-yet-materialized plugin** (e.g., a hypothetical third
  plugin with no `.claude-plugin/` yet): existing `[[ -d plugins/$p/.claude-plugin ]] || skip`
  guard preserves current behavior. The per-plugin `case` block must include a wildcard
  `*) echo "build-plugin: no manifest for $p" >&2; continue;;` arm so the recipe fails
  loudly instead of silently producing an empty plugin tree when a new plugin is added to
  `BUILD_OUTPUT_PLUGINS` without a corresponding `case` entry.

## Changes to Existing Behavior

- **ADDED**: New plugin tree at `plugins/cortex-overnight-integration/` containing
  `.claude-plugin/plugin.json`, `skills/{overnight,morning-review}/`, `hooks/hooks.json` +
  4 hook scripts, and `.mcp.json`. New install verb (`/plugin install cortex-overnight-integration`)
  becomes available once ticket 122 publishes the marketplace manifest.
- **ADDED**: New file `docs/plugin-development.md` covering the local-marketplace dogfooding
  workflow.
- **MODIFIED**: `justfile` `build-plugin` recipe — was a single hardcoded `SKILLS=(...)`
  array applied to both `BUILD_OUTPUT_PLUGINS`; now per-plugin `case`-dispatched SKILLS and
  HOOKS lists (bash-3.2 compatible). Cortex-interactive's effective output is unchanged
  (same 14 skills, same 1 hook, same 7 bin scripts); cortex-overnight-integration gets its
  own 2 skills + 4 hooks + 0 bin scripts.
- **MODIFIED**: `cortex_command/init/handler.py` `cortex init` — sandbox allowWrite path
  registered widens from `{repo_root}/lifecycle/sessions/` to `{repo_root}/lifecycle/`;
  `scaffold.check_symlink_safety()` (or equivalent) is repointed at the same wider path.
  Existing repo registrations are not modified; only fresh `cortex init` runs use the wider
  scope.
- **MODIFIED**: `requirements/project.md` Architectural Constraints "Per-repo sandbox
  registration" sentence updated from `lifecycle/sessions/` to `lifecycle/` to match.

## Technical Constraints

- **Plugin layout per Claude Code spec**: `.claude-plugin/` contains *only* `plugin.json`;
  skills/, hooks/, bin/, .mcp.json must live at plugin root (not inside `.claude-plugin/`).
  Confirmed via the cortex-interactive plugin's existing layout.
- **Bash 3.2 portability floor**: all bash scripts in this repo, including `justfile` recipes
  and `.githooks/pre-commit`, must run under macOS system bash 3.2.57 (the maintainer's
  primary platform). Avoid bash 4+ idioms: no `declare -A` associative arrays, no
  `mapfile`/`readarray` (use `while read` loops), no `${VAR^^}`/`${VAR,,}` (use `tr`).
  This constraint is documented at `.githooks/pre-commit` lines 27-29 and is load-bearing
  for the entire build pipeline.
- **`hooks.json` schema per event** (verified against `code.claude.com/docs/en/hooks`):
  - `SessionStart`: matcher field is *optional*, filters on session source
    (`startup|resume|clear|compact`). Omitting it fires on every session start.
  - `SessionEnd`: matcher field is not part of the documented schema.
  - `PostToolUse`: matcher field is optional, filters on tool name. Omitting it fires for
    every tool call.
  - `Notification`: matcher field is optional, filters on notification type
    (`permission_prompt|idle_prompt|auth_success|elicitation_dialog`). Omitting it fires
    on every notification. **Do not copy cortex-interactive's `matcher: "Bash"` value into
    Notification entries** — `Bash` is not in the notification type domain and a
    Notification entry with that matcher would never fire (silent-dead-hook risk).
  - All four registrations in this plugin pin matcher omission deliberately (R4); the
    scripts self-filter on the relevant fields internally.
- **Atomic state writes (pipeline.md architectural constraint)**: any code in the runner
  hooks that writes lifecycle state must use tempfile + `os.replace()`. The four hooks
  shipped here are existing scripts; no new write paths are introduced.
- **No version field in plugin.json**: omitted to match cortex-interactive and use git
  SHA for plugin updates. Adding a `version` field would block updates without an explicit
  bump.
- **Hooks must be byte-identical to source**: pre-commit Phase 4 drift detection runs
  `git diff --quiet plugins/$p/`; mismatches fail the commit.
- **Cross-plugin reference is one-directional**: cortex-overnight-integration depends on
  cortex-interactive; the reverse must not hold. Validated structurally —
  cortex-interactive's shipped skills (per `plugins/cortex-interactive/skills/`) do not
  invoke `/cortex:overnight` or `/cortex:morning-review`.
- **Sandbox-scope security rationale (R8)**: widening allowWrite from `lifecycle/sessions/`
  to `lifecycle/` exposes the parent directory to direct shell-tool writes without sandbox
  intervention. The practical security delta is bounded: (a) interactive sessions still
  pass through Claude Code's per-tool permission prompt for unfamiliar Bash commands and
  Write operations — the sandbox is one of two layers, not the only one; (b) the overnight
  runner already executes with `--dangerously-skip-permissions` and runs *outside* the
  sandbox per `requirements/project.md:33`, so this widening does not change what the
  runner can do; (c) only the four runner-only hooks shipped in this plugin write to
  `lifecycle/{feature}/.session*` paths that motivated the change. A narrower future
  alternative — relocating the `.session` marker out of `lifecycle/{feature}/` — is recorded
  as Non-Requirement and would unwind this widening.

## Open Decisions

(none — resolved during the structured interview and the critical-review pass:
`.mcp.json` shape per Alternative A; build recipe in justfile via `case` dispatch
under bash 3.2; sandbox scope widens to `lifecycle/` parent with project.md updated to match;
dogfooding documented in `docs/plugin-development.md`; matcher fields omitted across all
four hook registrations because each script self-filters internally.)
