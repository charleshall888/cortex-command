# Research: Publish cortex-overnight-integration plugin (overnight skill + runner hooks)

> Build the second of two plugins from the DR-2 split. Plugin lives at
> `plugins/cortex-overnight-integration/` and contains the `overnight` and
> `morning-review` skills, runner-only hooks, and a `.mcp.json` registering
> `cortex mcp-server`. Surfaces a clear error when the CLI tier isn't on PATH.

## Epic Reference

This ticket lives within the broader **overnight-layer-distribution** epic — see
[research/overnight-layer-distribution/research.md](../../research/overnight-layer-distribution/research.md).
DR-2 establishes the two-plugin split (`cortex-interactive` + `cortex-overnight-integration`)
at the runner boundary; DR-1 commits to building the MCP control plane concurrently with the
CLI; DR-9 keeps the existing `cortex-command-plugins` repo as the "extras" marketplace and
publishes core plugins from this repo. Scope this research to ticket 121 alone — sister tickets
115 (runner CLI), 116 (MCP server impl), 120 (cortex-interactive plugin), and 122 (marketplace
listing) are out of scope. **All four sister tickets are now `status: complete` except 122,
which is `blocked-by: [121]`.**

## Codebase Analysis

### Sister-plugin layout (canonical reference)

`plugins/cortex-interactive/` (shipped by ticket 120) is the closest reference for plugin shape:

```
plugins/cortex-interactive/
├── .claude-plugin/plugin.json    # minimal: name, description, author
├── skills/<name>/SKILL.md        # 14 skills (13 + critical-review)
├── hooks/
│   ├── hooks.json                # PreToolUse → cortex-validate-commit.sh
│   └── cortex-validate-commit.sh
└── bin/                          # 6 utilities auto-PATH'd by Claude Code
    ├── cortex-jcc
    ├── cortex-update-item
    ├── cortex-create-backlog-item
    ├── cortex-generate-backlog-index
    └── ...
```

The sister extras marketplace at `~/Workspaces/cortex-command-plugins/` shows the same
plugin layout — and a marketplace manifest at `.claude-plugin/marketplace.json` listing
`{name, source}` entries for each plugin in the repo.

### Current state of `plugins/cortex-overnight-integration/`

Partially scaffolded: `.mcp.json` already exists and is correctly authored:

```json
{
  "mcpServers": {
    "cortex-overnight": {
      "command": "cortex",
      "args": ["mcp-server"]
    }
  }
}
```

Missing: `.claude-plugin/plugin.json`, `skills/`, `hooks/`, `hooks/hooks.json`, `bin/`.

### `cortex mcp-server` subcommand exists

Confirmed in `cortex_command/cli.py:71-82` (`_dispatch_mcp_server`) and `cli.py:276-286`
(parser registration). Backing implementation at `cortex_command/mcp_server/server.py`,
`tools.py`, `schema.py`. Per `requirements/pipeline.md:153`, the server exposes five stdio
tools: `overnight_start_run`, `overnight_status`, `overnight_logs`, `overnight_cancel`,
`overnight_list_sessions`. **Ticket 116 is complete; the .mcp.json reference will resolve
correctly at runtime, modulo the PATH issue surfaced in §Adversarial Review.**

### Hooks split — TWO directories matter

The repo has hooks in **two** locations, not one:

**`hooks/` (top-level — 3 files)**:
| Hook | Event | Classification | Plugin assignment |
|---|---|---|---|
| `cortex-validate-commit.sh` | PreToolUse | Interactive-usable | **cortex-interactive (already shipped)** |
| `cortex-cleanup-session.sh` | SessionEnd | Runner-only (writes `lifecycle/{feature}/.session`) | **cortex-overnight-integration** |
| `cortex-scan-lifecycle.sh` | SessionStart | Runner-only (reads/writes `lifecycle/overnight-state.json`, injects `LIFECYCLE_SESSION_ID`) | **cortex-overnight-integration** |

**`claude/hooks/` (8+ files — adversarial agent surfaced this directory)**:
| Hook | Event | Plugin assignment |
|---|---|---|
| `cortex-tool-failure-tracker.sh` | PostToolUse (likely) | **cortex-overnight-integration** (per ticket 120 body) |
| `cortex-permission-audit-log.sh` | (likely PostToolUse / permission events) | **cortex-overnight-integration** (per ticket 120 body) |
| `cortex-skill-edit-advisor.sh` | (interactive-usable) | TBD — verify import-graph during impl |
| `cortex-output-filter.sh` | preprocessing filter | TBD |
| `cortex-sync-permissions.py` | (auxiliary) | TBD — ships with CLI tier per DR-2 |
| `cortex-worktree-{create,remove}.sh` | WorktreeCreate/Remove | TBD |

The `just build-plugin` recipe at `justfile:417-428` only rsyncs from `hooks/`, NOT
`claude/hooks/`. Ticket 121's implementation must either (a) move the four
runner-only hooks into a path the build recipe knows about, or (b) extend the recipe
to also rsync runner-specific hooks from `claude/hooks/`.

### `morning-review` skill is markdown-only

`skills/morning-review/SKILL.md` is a protocol document, not Python — it has no module-load
imports. Its hard runtime dependencies (verified by reading SKILL.md):

- **Runner state files** — reads `$CORTEX_COMMAND_ROOT/lifecycle/sessions/latest-overnight/morning-report.md`
  (line 10), `lifecycle/sessions/latest-overnight/overnight-state.json` (line 30).
- **CLI tier (`cortex` command)** — invokes `python3 -m cortex_command.overnight.report` (line 87).
- **`cortex-update-item` script** (line 117) — lives in `cortex-interactive/bin/`.
- **`/commit` skill** (line 230) — lives in `cortex-interactive/skills/commit/`.

The DR-2 placement decision ("morning-review goes in cortex-overnight-integration because it
requires runner state") is sound. But the `/commit`-skill dependency means
**cortex-overnight-integration cannot run morning-review's full protocol without
cortex-interactive also installed** — and Claude Code has no plugin-dependency mechanism today
(upstream issue #9444). Convention only.

### Build recipe pollution risk

`justfile:417-428` (`just build-plugin`):

```just
BUILD_OUTPUT_PLUGINS := "cortex-interactive cortex-overnight-integration"
SKILLS := "(commit pr lifecycle backlog requirements research discovery refine retro dev fresh diagnose evolve critical-review)"
# Recipe iterates BOTH plugins, rsyncs the SAME 14 skills into both
```

The recipe has a guard (`[[ -d plugins/$p/.claude-plugin ]] || skip`) that currently makes it
no-op for cortex-overnight-integration because `.claude-plugin/` doesn't exist there yet.
**The moment ticket 121 creates `plugins/cortex-overnight-integration/.claude-plugin/plugin.json`,
the next `just build-plugin` will pollute the plugin with all 14 cortex-interactive skills**,
contradicting DR-2's split. The build recipe must be refactored as part of this ticket to
support per-plugin skill manifests (e.g., associative array `BUILD_PLUGIN_SKILLS[cortex-interactive]=...`,
`BUILD_PLUGIN_SKILLS[cortex-overnight-integration]="overnight morning-review"`).

A `.githooks/pre-commit` Phase 1 check enforces "every `plugins/*/.claude-plugin/plugin.json`
has a non-empty `.name` field," failing closed if a plugin dir is unclassified. The first
commit landing ticket 121's plugin.json must satisfy this policy.

### Skills inventory and split (final)

| Skill | Plugin assignment | Status |
|---|---|---|
| commit, pr, lifecycle, backlog, requirements, research, discovery, refine, retro, dev, fresh, diagnose, evolve, critical-review | cortex-interactive | shipped (ticket 120) |
| **overnight** | cortex-overnight-integration | this ticket |
| **morning-review** | cortex-overnight-integration | this ticket |

### Files that will be created or modified

**Created in `plugins/cortex-overnight-integration/`**:
- `.claude-plugin/plugin.json` — minimal manifest (`name`, `description`, `author`)
- `skills/overnight/SKILL.md` (+ any `references/`) — copied/synced from `skills/overnight/`
- `skills/morning-review/SKILL.md` (+ `references/walkthrough.md`) — copied/synced from `skills/morning-review/`
- `hooks/hooks.json` — manifest registering SessionStart, SessionEnd, and any PostToolUse runner hooks
- `hooks/cortex-cleanup-session.sh` — synced from `hooks/`
- `hooks/cortex-scan-lifecycle.sh` — synced from `hooks/`
- `hooks/cortex-tool-failure-tracker.sh` — synced from `claude/hooks/`
- `hooks/cortex-permission-audit-log.sh` — synced from `claude/hooks/`

**Modified**:
- `justfile` — `build-plugin` recipe needs per-plugin skill and hook manifests
- `skills/morning-review/SKILL.md` — add precondition surfacing missing `cortex-update-item` / `/commit` (cross-plugin dep)
- `skills/overnight/SKILL.md` — add precondition surfacing missing `cortex` CLI

**Possibly modified (CLI-tier coupling)**:
- `cortex_command/init.py` (or wherever `cortex init` lives) — extend sandbox allowWrite to cover `lifecycle/` parent, not just `lifecycle/sessions/` (see Adversarial Review §5)

### Conventions to follow

1. **Plugin directory**: `plugins/{name}/` with `.claude-plugin/plugin.json` (only file in `.claude-plugin/`); skills, hooks, bin at plugin root.
2. **Plugin invocation namespace**: `/cortex:{skill}` — the plugin name `cortex-overnight-integration` does not become the namespace prefix; `/cortex:overnight` and `/cortex:morning-review` follow the existing convention.
3. **No version field in plugin.json** — per DR-4 / per `cortex-interactive` precedent; git SHA drives plugin updates.
4. **Hook references**: use `${CLAUDE_PLUGIN_ROOT}/hooks/<script>.sh` as the path; the variable resolves to the installed plugin directory.
5. **MCP server reference**: keep `command: "cortex"` bare — but see Adversarial Review §4 for PATH risk.

## Web Research

### Claude Code plugin spec — current state (April 2026)

From the official Plugins reference at `code.claude.com/docs/en/plugins-reference`:

- `.claude-plugin/plugin.json` is technically optional (auto-discovery if absent), but in
  practice this repo's pre-commit hook requires it. **Only `name` is required** if present.
  Other optional fields: `version`, `description`, `author`, `homepage`, `repository`,
  `license`, `keywords`, `userConfig`, `dependencies` (semver constraints — but plugin-level
  deps not yet enforced; #9444 upstream).
- Auto-discovered components from the plugin root: `skills/<name>/SKILL.md`, `commands/*.md`,
  `agents/*.md`, `hooks/hooks.json`, `.mcp.json`, `.lsp.json`, `monitors/monitors.json`, `bin/`.
- **Critical pitfall**: do NOT put components inside `.claude-plugin/` — only `plugin.json` belongs there.

### MCP `.mcp.json` lifecycle and failure surface

- Format identical to user-level `.mcp.json`. Shipped by plugin enables the server.
- **Lifecycle**: server starts at session start (and `/reload-plugins`). No per-tool lazy spawn.
  Disabling a plugin mid-session does not stop the running server.
- **Variable substitution** (works in command/args/env): `${CLAUDE_PLUGIN_ROOT}`,
  `${CLAUDE_PLUGIN_DATA}`, `${user_config.KEY}`, `${ENV_VAR}`. Issue #9427 reported
  expansion was broken in plugin `.mcp.json` (now closed/fixed; verify in current version).
- **ENOENT failure**: command-not-on-PATH surfaces in `/plugin` Errors tab,
  `~/.claude/mcp-server-<NAME>.log`, `claude --debug`, and `/doctor`. **Plugin enables anyway**
  — skills and hooks load fine; only the MCP tools become unavailable.
- **Stderr-as-failure bug**: Issue #17653 — Claude Code interprets ANY stderr output as failure.
  The MCP server must log to a file or stdout-protocol-frames, not stderr.

### No `onEnable` plugin lifecycle hook

- Issue #11240 (request for plugin lifecycle hooks) closed as duplicate.
- Issue #27113 (declarative skill/plugin dependencies) closed as not planned.
- **Canonical alternatives**:
  - `SessionStart` hook with `command -v <bin>` guard + stderr message
  - Per-skill preconditions in SKILL.md frontmatter
  - Surface errors via stderr to `/plugin` Errors tab
- Caveats for SessionStart hooks in plugins:
  - Issue #11649 — `CLAUDE_ENV_FILE` sometimes empty in plugin SessionStart (not project SessionStart). Don't rely on it.
  - Issue #12671 — SessionStart hooks may show "hook error" in UI even on exit 0.

### Plugin → CLI dependency prior art

`trailofbits/skills/plugins/gh-cli` is the cleanest reference: plugin enables unconditionally;
SessionStart hook uses `command -v gh &>/dev/null || { echo "gh not found"; exit 0 }` —
silent passthrough to a no-op when missing. Plugin.json declares no special prerequisite.
LSP-shipping plugins follow the same pattern (Anthropic docs explicitly say "you must install
the language server binary separately"). **The prevailing pattern is graceful degradation,
not refuse-to-enable.**

### Plugin `userConfig` constraints

- Types: `string`, `number`, `boolean`, `directory`, `file`. `directory`/`file` check existence
  but not contents — cannot validate "directory contains a working `cortex` binary."
- Validators: only `required: true`, `min`/`max` for numbers. No regex, no custom predicates.
- `sensitive: true` stores in OS keychain, ~2 KB total budget (shared with OAuth).
- Substitutable as `${user_config.KEY}` and exposed as `CLAUDE_PLUGIN_OPTION_<KEY>` env var.
- **No "refuse to enable" semantics** beyond `required: true` for blank values.

### MCP control-plane pattern (mcp-background-job)

`dylan-gluck/mcp-background-job` ships an MCP server that proxies to long-running CLIs:
single FastMCP stdio server, internal `JobManager` + `ProcessWrapper`, configurable via env vars,
exposes 7 tools (`execute`, `status`, `output`, `tail`, `list`, `interact`, `kill`).
**The cortex MCP server (ticket 116) follows variant 2** — server is a subcommand of the cortex CLI
itself (`cortex mcp-server`); `.mcp.json` simply registers `command: "cortex", args: ["mcp-server"]`.
This matches the dependency-on-external-CLI brief best.

### Web anti-patterns and gotchas (relevant to this ticket)

1. Don't put components inside `.claude-plugin/` — only `plugin.json` lives there.
2. `${CLAUDE_PLUGIN_ROOT}` changes on update; use `${CLAUDE_PLUGIN_DATA}` for persistence.
3. Don't print to stderr in MCP server unless real error (#17653).
4. Don't bump version too rarely — explicit `version` blocks updates without bump.
5. Don't declare hooks twice (in plugin.json AND hooks/hooks.json) — auto-load conflict.
6. **Don't assume PATH inside Claude Code matches the user's interactive shell.** GUI launches
   on macOS inherit launchd PATH (no `~/.local/bin`).
7. Bare `npx`/`npm` on Windows needs `cmd /c` wrapping — not relevant here, but flagged.

## Requirements & Constraints

### project.md

**In Scope** (line 38–47): Overnight execution framework, session management, scheduled launch,
morning reporting, observability, multi-agent orchestration, global agent configuration.

**Out of Scope** (line 49–54):
> "Published packages or reusable modules for others — the `cortex` CLI ships as a local
> editable install (`uv tool install -e .`) for self-hosted use; **publishing to PyPI or other
> registries is out of scope**."

The Out-of-Scope clause specifically restricts PyPI/registry publishing — Claude Code plugin
marketplaces are not registries in that sense. The deferred DR-8 amendment formalizes plugin
distribution but is not load-bearing for this ticket.

**Architectural Constraint** (line 26): `cortex init` additively registers the repo's
`lifecycle/sessions/` path in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite`
array. **This is the only write cortex-command performs inside `~/.claude/`.** Per the adversarial
review, this allowWrite scope is too narrow for runner-only hooks shipped in this plugin —
they write to `lifecycle/{feature}/.session` and `.session-owner`, outside `lifecycle/sessions/`.

### pipeline.md

- All state writes are atomic (tempfile + `os.replace()`). Permanent architectural constraint.
- Integration branches `overnight/{session_id}` persist after session completion.
- Workers run with `_ALLOWED_TOOLS = [Read, Write, Edit, Bash, Glob, Grep]` only — Agent/Task omitted.
  Skills are not re-invoked during overnight execution.
- `cortex mcp-server` exposes 5 stdio tools wrapping `cli_handler` boundaries; server is stateless;
  `confirm_dangerously_skip_permissions: Literal[True]` gates `overnight_start_run`.

### CLAUDE.md

- "Cortex-command ships as a CLI installed via `uv tool install -e .` plus plugins installed via
  `/plugin install`. It no longer deploys symlinks into `~/.claude/`."
- "New global utilities ship via the `cortex-interactive` plugin's `bin/` directory (ticket 120 scope)."
- `jcc` is installed at `~/.local/bin/jcc` to invoke recipes from any directory.

### Epic research DRs that apply

- **DR-1**: MCP control-plane built concurrently with CLI. `.mcp.json` references the
  CLI-deployed server via `command: "cortex", args: ["mcp-server"]`.
- **DR-2**: Two-plugin split at the runner boundary; cortex-overnight-integration ships
  overnight + morning-review skills + runner-only hooks; `notify.sh`/`statusline.sh`/`rules/*`/
  `reference/*` are NOT plugin-distributable (deployed by `cortex setup`).
- **DR-9**: This repo publishes `cortex-interactive` and `cortex-overnight-integration`;
  `cortex-command-plugins` repo continues as the optional/per-project extras marketplace.

### Hard constraint from DR-2 (load-bearing)

> "any plugin split leaves at least three components (`notify.sh`, `statusline.sh`, rules/) that
> must be deployed by the CLI tier. Plugins cannot be 'independently installed' in any meaningful
> sense — they always require the CLI to have run `cortex setup` first."

Plus the cross-plugin dep surfaced by adversarial review: morning-review needs `cortex-update-item`
(cortex-interactive bin/) and `/commit` skill (cortex-interactive skills/). Convention: install
both plugins. No mechanism to enforce.

### Scope boundaries

**In scope for ticket 121**:
- `plugins/cortex-overnight-integration/.claude-plugin/plugin.json` (minimal)
- `plugins/cortex-overnight-integration/skills/{overnight,morning-review}/`
- `plugins/cortex-overnight-integration/hooks/hooks.json` + the 4 runner-only hook scripts
- `.mcp.json` already in place — verify and document
- Build recipe refactor for per-plugin skill/hook manifests (justfile)
- Precondition updates in overnight + morning-review SKILL.md for missing-CLI / missing-cortex-interactive
- Acceptance tests covering local dogfooding via stub marketplace.json

**Out of scope**:
- The runner CLI itself (115, complete)
- The MCP server implementation (116, complete)
- Interactive skills (120, complete)
- Production marketplace.json (122, blocked-by 121)
- Migrating `cortex init` allowWrite scope from `lifecycle/sessions/` to `lifecycle/` —
  this is a CLI-tier change; ticket 121 must surface the dependency or escalate as a separate ticket.

## Tradeoffs & Alternatives

### Alternatives for `.mcp.json` shape (the implementation-prescriptive question)

Sister tickets 115/116/120 are all complete; the "deferred dependency" framing in clarify is
hypothetical. With ticket 116 shipped, **Alternative A (ship `.mcp.json` as prescribed) is the
clear winner**.

| Alt | Description | Verdict |
|---|---|---|
| **A** | Ship `.mcp.json` registering `cortex mcp-server` (already authored) | **Recommended** — matches DR-1, single canonical artifact, no retrofit. |
| B | Ship without `.mcp.json`; defer to follow-up ticket | Loses Claude-initiated overnight start; reintroduces the retrofit DR-1 explicitly rejected. |
| C | Ship `.mcp.json` pointing to a stub command | Stub-MCP-protocol is non-trivial; bash echo doesn't satisfy `initialize`. No realistic regime where this beats A. |
| D | Conditional registration via `userConfig` | Plugin spec doesn't support omitting `mcpServers` block via substitution. Adds friction without value. |
| E | Move `.mcp.json` ownership to ticket 116 | Violates 121's scope ("Claude-side plugin"); requires reorganizing already-complete work. Moot. |

**Recommended approach**: Alternative A. The `.mcp.json` already authored at
`plugins/cortex-overnight-integration/.mcp.json` is correct as-is *modulo* the PATH issue
(adversarial §4) — fix is to either ship a `bin/` wrapper that resolves cortex absolutely, or
require absolute path via `userConfig`.

### Alternatives for skills source-of-truth

| Approach | Pros | Cons | Recommendation |
|---|---|---|---|
| Symlinks from `plugins/.../skills/*` to top-level `skills/*` | Single source, no drift | Symlinks may break under marketplace clone-to-cache; not used by cortex-interactive | Reject — diverges from established pattern. |
| Duplication via build recipe (current cortex-interactive pattern) | Drift detectable at commit (.githooks/pre-commit), auto-syncable via `just build-plugin` | Recipe must be per-plugin-aware (current pollution risk) | **Recommended** — extend recipe with per-plugin manifests. |
| Authoritative location IS `plugins/.../skills/`; top-level `skills/` retired | Cleanest long-term | Massive churn; breaks every existing reference; out of scope for this ticket | Defer — possible follow-up ticket. |

### Sequencing (resolved)

All dependencies satisfied: 115 complete, 116 complete, 120 complete. Ticket 121 unblocks 122.
No further sequencing analysis needed.

## Adversarial Review

The adversarial agent surfaced 8 concrete failure modes that the prior agents missed.
Addressed each in the spec section below as a non-negotiable acceptance criterion.

### 1. Skills source-of-truth (duplication trap surfaced)

`plugins/cortex-interactive/skills/commit/SKILL.md` and `skills/commit/SKILL.md` are
identical content but **separate files (md5 match, not symlinks)** — verified via
`find plugins -type l` returning empty. The maintenance solution is `just build-plugin` +
`.githooks/pre-commit` drift check. Drift is detectable at commit time but silent at edit time.

### 2. Build-recipe pollution (CRITICAL)

`justfile:417-428` `build-plugin` iterates `BUILD_OUTPUT_PLUGINS="cortex-interactive cortex-overnight-integration"`
and rsyncs the SAME 14 skills + same `bin/cortex-*` + same `cortex-validate-commit.sh` into
BOTH plugins. Currently no-op for cortex-overnight-integration only because `.claude-plugin/`
doesn't exist there yet (line 422 guard). **The instant ticket 121 creates plugin.json, the
next pre-commit `just build-plugin` will populate the plugin with all 14 cortex-interactive
skills.** Mitigation must land WITH this ticket: extend the recipe with per-plugin SKILLS and
HOOKS arrays.

### 3. plugin.json optionality vs repo policy

Web docs say plugin.json is optional. Repo's `.githooks/pre-commit` Phase 1 validates that
**every** `plugins/*/.claude-plugin/plugin.json` has a non-empty `.name` and fails closed on
unclassified plugin dirs. **Plugin.json is required in practice for this repo.**

### 4. Missing-hooks misdirection (codebase agent error)

`cortex-tool-failure-tracker.sh` and `cortex-permission-audit-log.sh` DO exist — at
`claude/hooks/`, not `hooks/`. The build recipe only reaches into `hooks/`, so the runner-only
hooks at `claude/hooks/` will not be packaged unless ticket 121 either moves them or extends
the recipe.

### 5. PATH propagation in Claude Code spawn (HIGH RISK)

`cortex` resolves to `~/.local/bin/cortex` → `~/.local/share/uv/tools/cortex-command/bin/cortex`.
`~/.local/bin` is added to PATH by `~/.zshrc`/`~/.bash_profile` only. Claude Code launched from
Finder/Spotlight inherits launchd PATH (`/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin`) — no
`~/.local/bin`. Bare `command: "cortex"` will ENOENT under GUI launch. Plugin `bin/` auto-PATH'ing
applies to the Bash tool environment; it does NOT carry over to MCP child-process spawning
(MCP uses OS spawn PATH).

**Mitigation**: ship `plugins/cortex-overnight-integration/bin/cortex-mcp-server-launcher` —
a small wrapper that resolves `cortex` against a known search list (`~/.local/bin`,
`~/.local/share/uv/tools/cortex-command/bin`, `$CORTEX_COMMAND_ROOT/.venv/bin`). Reference it
in `.mcp.json` as `${CLAUDE_PLUGIN_ROOT}/bin/cortex-mcp-server-launcher`. Acceptance: smoke
test from a clean GUI-launched Claude Code session.

### 6. Sandbox allowWrite gap

`cortex init` registers only `lifecycle/sessions/` in allowWrite. Runner-only hooks shipped
in this plugin write to `lifecycle/{feature}/.session` and `.session-owner` — outside the
allowed scope. In an interactive sandboxed session, these writes will fail.

**Mitigation**: extend `cortex init` (CLI tier) to allowWrite `lifecycle/` (parent). This is a
CLI-tier change; either ship as part of ticket 121 (cross-tier coupling) or escalate as a
separate ticket. **Recommended in this ticket** because the plugin cannot ship correctly
without it.

### 7. No plugin dependency mechanism (#9444 upstream)

Plugin.json `dependencies` field is documented but plugin-level deps are not enforced
(upstream issue #9444). DR-2's "installed on top of cortex-interactive" is convention only.

**What breaks if cortex-overnight-integration is installed standalone**:
- morning-review SKILL.md line 117 calls `cortex-update-item` → ENOENT (script in cortex-interactive bin/).
- morning-review SKILL.md line 230 invokes `/commit` skill → not registered.
- overnight skill: depends on `cortex` CLI (fine if CLI tier installed); not directly coupled to cortex-interactive.

**Mitigation**: morning-review SKILL.md must add a precondition / runtime check:
"morning-review requires cortex-interactive plugin (`/plugin install cortex-interactive@cortex-command`)."
Document the dep in cortex-overnight-integration plugin.json description and in 122's marketplace entry.

### 8. hooks.json schema for SessionStart/SessionEnd

cortex-interactive's hooks.json uses `matcher: "Bash"` for PreToolUse. SessionStart and
SessionEnd have no tool matcher. Naïve copy-paste will misfire.

**Verified schema** (from existing in-repo SessionStart examples):
```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/cortex-scan-lifecycle.sh"}
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/cortex-cleanup-session.sh"}
        ]
      }
    ]
  }
}
```

`matcher` is omitted (or empty string) for session-lifecycle events. Acceptance: smoke test
fires SessionStart hook once per session; SessionEnd fires on exit.

### 9. Local dogfooding without 122

`/plugin marketplace add <local-path>` accepts a local path. Maintainer authors a stub
`.claude-plugin/marketplace.json` at the repo root listing only `cortex-overnight-integration`
during development; production marketplace.json (ticket 122) replaces it. Spec must document
this dogfooding workflow and Acceptance must include a full enable/disable cycle from the stub.

### 10. morning-review pointer-file write

morning-review's Step 0 also writes to `~/.local/share/overnight-sessions/active-session.json`.
Verify allowWrite for that path is registered, or that the skill detects sandbox-blocked write
and degrades gracefully.

## Open Questions

All Open Questions from Clarify have been resolved by Research:

1. **Hooks list** — Resolved: `cortex-cleanup-session.sh` and `cortex-scan-lifecycle.sh` from
   `hooks/`; `cortex-tool-failure-tracker.sh` and `cortex-permission-audit-log.sh` from
   `claude/hooks/`. The build recipe must be extended to reach into both directories or the
   `claude/hooks/` files must be relocated.
2. **Ticket 116 sequencing** — Resolved: 116 is complete; `cortex mcp-server` exists;
   `.mcp.json` already references it correctly.
3. **morning-review import verification** — Resolved: skill is markdown-only, no Python
   imports. Hard runtime deps on runner state files + `cortex-update-item` (cortex-interactive)
   + `/commit` skill (cortex-interactive). Placement in cortex-overnight-integration is sound;
   cross-plugin dep on cortex-interactive must be documented.
4. **Plugin layout reference** — Resolved: cortex-interactive plugin (shipped by ticket 120)
   is the canonical layout; cortex-command-plugins repo is the secondary reference.
5. **PATH-error surface** — Resolved: SessionStart hook with `command -v cortex` guard +
   per-skill preconditions are the canonical pattern. There is NO `onEnable` plugin lifecycle
   hook (#11240 closed). Plugin enables unconditionally; missing CLI surfaces as graceful
   degradation + `/plugin` Errors entry.
6. **Marketplace metadata for dogfooding** — Resolved: stub `.claude-plugin/marketplace.json`
   at repo root for local install during development; production marketplace.json is ticket
   122's deliverable.

### New questions surfaced by research (must be resolved in Spec)

- **Sandbox allowWrite scope change**: extending `cortex init` to allowWrite `lifecycle/`
  (parent) is a CLI-tier change. Resolve in Spec: ship in this ticket as a cross-tier coupling,
  or escalate as a separate ticket and accept that interactive cortex-overnight-integration
  hooks will fail until it lands. **Recommended: ship in this ticket**.

- **Build-recipe refactor scope**: the per-plugin SKILLS/HOOKS manifest refactor is mandatory
  for this ticket but materially expands the implementation. Resolve in Spec: confirm the
  refactor is in scope, identify the manifest format (associative array in justfile vs.
  per-plugin manifest file).

- **MCP launcher wrapper vs. userConfig vs. PATH-fix-at-install**: the Adversarial mitigation
  for the MCP-server PATH issue has three viable shapes (wrapper script, userConfig prompt for
  absolute path, document the requirement and rely on the curl bootstrap to add `~/.local/bin`
  to launchd PATH). Resolve in Spec.

- **morning-review SKILL.md precondition format**: how does the existing skill schema accept
  cross-plugin dependency checks? Use SKILL.md `preconditions` frontmatter or runtime guard?
  Resolve in Spec.
