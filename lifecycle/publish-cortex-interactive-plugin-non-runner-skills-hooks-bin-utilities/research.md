# Research: Publish cortex-interactive plugin (non-runner skills + hooks + bin utilities)

## Epic Reference

Epic research lives at [`research/overnight-layer-distribution/research.md`](../../research/overnight-layer-distribution/research.md). This ticket (#120) implements DR-2's "two plugins at runner boundary" decision — `cortex-interactive` is the non-runner plugin, paired with `cortex-overnight-integration` in #121. Epic covers the broader three-tier distribution architecture (plugin tier + CLI tier + per-repo scaffold via `cortex init`); this ticket is scoped narrowly to the first plugin's structure, skill migration, and conditional hook placement.

---

## Codebase Analysis

### Files that will change

**New files to create under `plugins/cortex-interactive/`:**

- `.claude-plugin/plugin.json` — plugin manifest
- `hooks/hooks.json` — conditional, if `cortex-output-filter.sh` is included
- `hooks/cortex-output-filter.sh` — copy or build-output of source at `claude/hooks/cortex-output-filter.sh`
- `hooks/output-filters.conf` — template config (filter is a no-op without it)
- `skills/<name>/SKILL.md` + full `references/` subdirs for: `commit`, `pr`, `lifecycle`, `backlog`, `requirements`, `research`, `discovery`, `refine`, `retro`, `dev`, `fresh`, `diagnose`, `evolve` (13 base)
- `skills/critical-review/SKILL.md`, `skills/morning-review/SKILL.md` (conditional — require import-path fixes before inclusion; see Adversarial §9 and §4 below)
- `bin/jcc`, `bin/count-tokens`, `bin/audit-doc`, `bin/git-sync-rebase.sh` (4 present in repo today)
- `bin/cortex-update-item`, `bin/cortex-create-backlog-item`, `bin/cortex-generate-backlog-index` (3 new shims — scripts do not exist today; Python sources at top-level `backlog/*.py`)
- `README.md` — plugin-scope documentation

**Files NOT in this plugin (per post-117 hook ownership split):**

- `cortex-validate-commit.sh`, `cortex-skill-edit-advisor.sh` — project scope (`cortex-command/.claude/settings.json`)
- `cortex-scan-lifecycle.sh`, `cortex-cleanup-session.sh`, `cortex-tool-failure-tracker.sh`, `cortex-permission-audit-log.sh` — overnight plugin (#121)
- `cortex-notify.sh` — machine-config
- `cortex-worktree-create.sh`, `cortex-worktree-remove.sh` — not plugin-scoped (CWD-from-stdin pattern)

### Integration points and dependencies

- **Cross-skill invocations**: `lifecycle` invokes `/commit`, `/backlog`, `/research`, `/dev`; `morning-review` invokes `/commit`; `dev` routes to most other skills. All become `/cortex:*` under the plugin.
- **Python-module coupling**: `lifecycle/SKILL.md` suggests `python3 -m cortex_command.overnight.daytime_pipeline` as a user-chosen path (not at module load — conditional UX). `morning-review` suggests `python3 -m cortex_command.overnight.report` in documentation strings (not imported).
- **`critical-review` has an unguarded import** (contrary to initial read): `from cortex_command.common import atomic_write` inside a `python3 -c` snippet at Step 2e runs unconditionally when a lifecycle session + ≥1 B-class finding exist. Not behind `try/except`. See Adversarial §9.
- **`${CORTEX_COMMAND_ROOT}` references** in `morning-review/SKILL.md` (~4 locations) — plugin-only install without CLI tier will fail these invocations.
- **`/evolve` resolves repo root via `readlink` on its own SKILL.md path** — this pattern breaks in plugin-cache layout; repo-root resolution must be reworked.

### Existing patterns and conventions

- No `plugins/` directory exists in the repo today — this ticket establishes the pattern.
- Prior art in sibling repo `cortex-command-plugins`: `.claude-plugin/plugin.json` + `plugins/<name>/` layout; `.claude-plugin/marketplace.json` at repo root (scope of #122).
- Skills each have `SKILL.md` + optional `references/` subdirectory.
- `${CLAUDE_SKILL_DIR}` appears in 6 skills' SKILL.md bodies (backlog, discovery, morning-review, lifecycle, requirements, refine) — substitution reliability is questionable in plugin SKILL.md bodies per open issue #9354.

### Bin utilities inventory

| Utility | Present? | Type | Coupling |
|---|---|---|---|
| `jcc` | yes (`bin/jcc`) | bash | wraps `just -f $CORTEX_COMMAND_ROOT/justfile` — env-var coupling |
| `count-tokens` | yes | `uv run --script` Python | uses anthropic SDK; no cortex imports |
| `audit-doc` | yes | `uv run --script` Python | uses anthropic SDK; no cortex imports |
| `git-sync-rebase.sh` | yes | bash | references `cortex_command/overnight/sync-allowlist.conf` — path rewire needed |
| `update-item` | **NO** | — | Python source at `backlog/update_item.py` (top-level, not `cortex_command/backlog/`) — needs a shim |
| `create-backlog-item` | **NO** | — | Python source at `backlog/create_item.py` — needs a shim |
| `generate-backlog-index` | **NO** | — | Python source at `backlog/generate_index.py` — needs a shim |

**Note**: `backlog/` is simultaneously a Python module directory AND a user-data directory — the skills invoke these as bare PATH commands (`update-item {id}`), and no shims exist today. This is a spec-level gap the plugin build must resolve.

### Namespace migration footprint

~3,387 references to the 13 base skill names across markdown, shell, and Python. Highest-volume: `/lifecycle` (987), `/research` (823), `/dev` (464), `/discovery` (299), `/commit` (225), `/refine` (210), `/backlog` (191), `/pr` (127), `/requirements` (69), `/diagnose` (47), `/evolve` (24), `/fresh` (23), `/retro` (22).

Mass find/replace is **not mechanical** (see Adversarial §3 for false-match risks and retros/ carve-out).

---

## Web Research

### Plugin manifest + hook manifest essentials

- `.claude-plugin/plugin.json` has no `schemaVersion` field; feature-complete as of Claude Code 2.1.105+. Only `name` is required (kebab-case, drives namespace). All component paths relative (`./`). Recent additions: `dependencies`, `monitors`, `channels`.
- `hooks/hooks.json` shape: `{"hooks": {"<EventName>": [{"matcher": "...", "hooks": [...]}]}}`. Event names case-sensitive. Hook action `type` values: `command`, `http`, `mcp_tool`, `prompt`, `agent`. Scripts must be chmod +x with shebang.
- `${CLAUDE_PLUGIN_ROOT}` → `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/` — **wiped on every update**. Use for read-only assets only.
- `${CLAUDE_PLUGIN_DATA}` → `~/.claude/plugins/data/{id}/` — persists across updates. Auto-created on first reference. Use for venvs, caches, generated state.

### Plugin-command namespacing

- **Plugin commands are ALWAYS namespaced as `/plugin-name:command-name`** (issue #15882 closed by docs correction). You cannot ship unprefixed commands from a plugin.
- Namespace is derived from `plugin.json` `name` field; directory name is fallback.
- User/project-space skills (`/name`, `/user:name`, `/project:name`) live in a separate namespace from `/plugin-name:name` — no collision during migration.

### `bin/` PATH behavior

- Plugin `bin/` is auto-added to the Bash tool's PATH when enabled. Files must be under `${CLAUDE_PLUGIN_ROOT}/bin/`, executable, with shebang.
- **No documented ordering/conflict rules for same-named bin commands across plugins**. No opt-out mechanism. Name collisions with other plugins or system tools are undefined behavior.
- Bin/ PATH injection is Bash-tool-scoped — hook/MCP commands still need explicit `${CLAUDE_PLUGIN_ROOT}/bin/<tool>` paths.

### Known upstream gaps

- **#9444** (plugin dependency sharing): OPEN as of 2026-03-31. No 2026 release has addressed it. `cortex-interactive` is self-contained so not directly blocked, but any future split into a shared-code plugin would hit this.
- **#9354** (`${CLAUDE_PLUGIN_ROOT}` substitution in command/skill markdown): OPEN. Substitution works in JSON hook/MCP/LSP/monitor configs and (claimed) in skill bodies but practitioners hit gaps. Any SKILL.md using `${CLAUDE_SKILL_DIR}` or `${CLAUDE_PLUGIN_ROOT}` in prose paths is at risk.
- **#27145** (`CLAUDE_PLUGIN_ROOT` unset at SessionStart): marked closed in 2026; verify end-to-end post-upgrade.

### Canonical reference plugins

- `anthropics/claude-plugins-official/plugins/hookify` — minimal `plugin.json` (name/description/author only), relies on git-SHA versioning, bundles `skills/`, `commands/`, `agents/`, `hooks/` plus internal support dirs.
- **None of the official plugins currently use `bin/`** — this surface area is newer and less exercised, a mild risk signal.

### Anti-patterns to avoid

- Writing state to `${CLAUDE_PLUGIN_ROOT}` (wiped on update)
- `version` pinning without bumping (users silently miss updates — either bump religiously or omit)
- Paths outside plugin root (`../...`) — broken after marketplace cache copy
- Components nested inside `.claude-plugin/` (only `plugin.json` belongs there)
- Non-executable hook scripts / missing shebang (silent failure)
- Case-wrong event names (`postToolUse` vs `PostToolUse`)
- Relying on `${CLAUDE_PLUGIN_ROOT}` in skill markdown bodies (issue #9354)
- Bin-script name collisions with other plugins or system tools — namespace with `cortex-*` prefix

---

## Requirements & Constraints

### Current `requirements/project.md` wording (line 52)

> "Published packages or reusable modules for others — the `cortex` CLI ships as a local editable install (`uv tool install -e .`) for self-hosted use; publishing to PyPI or other registries is out of scope."

DR-8 proposes removing this and adding "Plugin-based distribution of skills, hooks, and CLI utilities via Claude Code's plugin marketplace; `curl | sh`-installable runner CLI" to In Scope. Orchestrator decision at clarify: **this update is assigned to #122 (marketplace manifest + install docs)**, not #120. Spec phase for #120 should not block on the project.md update.

### Defense-in-depth permissions constraint

`project.md` line 32: plugins cannot distribute `settings.json` permissions (upstream limitation — plugin `settings.json` supports only `agent` and `subagentStatusLine` keys). #120's skills and bin utilities inherit permissions from the user's existing `~/.claude/settings.json`. No new constraint; users already run these skills under current permissions.

### File-based state constraint

`project.md` line 25: lifecycle artifacts, backlog items, pipeline state, session tracking all use plain files in the user's repo. `${CLAUDE_PLUGIN_DATA}` is for plugin cache/venv state only, never for pipeline state. The 13 shipped skills already satisfy this — no rework needed.

### Maintainability through simplicity

Plugin layout (`plugins/cortex-interactive/skills/`, `/hooks/`, `/bin/`) is a necessary concession to plugin-authoring conventions; simplicity applies at the user-facing slash-command surface (still one `/cortex:<name>` per skill).

### Conditional loading

- `requirements/multi-agent.md` applies: shipped skills include `lifecycle`, `dev`, `research` which use `Agent(isolation: "worktree")`. Known silent-isolation-failure (upstream #39886) affects any caller; no mitigation today.
- `requirements/pipeline.md` applies: graceful degradation when runner CLI is absent is a first-class requirement (ticket #123 scope, but #120 skills must be compatible).

### Scope boundaries this ticket respects

- **In scope**: `plugins/cortex-interactive/` layout, 13 base skills + conditional 2 + bin shims + conditional hook; namespace migration of all shipped skills to `/cortex:*`.
- **Out of scope**: CLI-tier work (owned by #114/#117/#119); overnight plugin (#121); marketplace manifest (#122); project.md DR-8 update (#122); migration guide (#124).

---

## Tradeoffs & Alternatives

Six alternatives explored; **Alternative A (ticket's prescribed approach) is recommended** because DR-2 explicitly resolved the two-plugin split at the runner boundary and revisiting that decision absent new evidence violates project norms. Summary of each:

| Alt | Shape | Verdict | Key reason |
|---|---|---|---|
| **A** | `plugins/cortex-interactive/` monorepo, `/cortex:*` namespace | **Recommended** | Implements DR-2 directly; monorepo coordination preserved; matches `cortex-command-plugins` prior art |
| B | Keep symlink deploy + plugin as secondary | Reject | Contradicts #117 retirement; two deploy mechanisms double maintenance; no user benefit |
| C | Monolithic `cortex` plugin (interactive + overnight together) | Reject | Contradicts DR-2 option (a); re-entangles runner boundary epic 113 is separating |
| D | One plugin per skill (13 plugins) | Reject | Cross-plugin calls fragile; upstream #9444 prevents shared-dep resolution; DR-2 option (c) already rejected |
| E | Unnamespaced commands (`/commit` not `/cortex:commit`) | Reject | Plugins are always namespaced per #15882; fragile to any future `/commit`-shipping plugin |
| F | Extract cortex-interactive to its own repo | Reject | Breaks monorepo coordination; single maintainer → multi-repo PR tax; contradicts ticket's "in this repo" wording |

### Namespace-rename timing

Three sequences considered: (a) rename first in a separate ticket, (b) ship plugin with unprefixed names and rename later, (c) ship plugin with prefixed names in one go (current plan).

**Recommendation: (c)** — one cutover day, rename causally linked to plugin ship. (a) leaves an intermediate state with no distribution after #117 retired symlinks; (b) doubles the breaking change and violates namespace norms.

---

## Adversarial Review

Agent 5 surfaced failure modes and edge cases that corrected several Agent 1 findings. Significant items below; full list preserved in orchestrator memory.

### Critical corrections to earlier findings

1. **`critical-review` is NOT safe for plugin-only install** (contradicts Agent 1). `skills/critical-review/SKILL.md:255` contains `from cortex_command.common import atomic_write` inside an inline `python3 -c` snippet at Step 2e (B-class residue write). This runs unconditionally when a lifecycle session exists AND there is ≥1 B-class finding — no `try/except ImportError`. Plugin-only users will hit a mid-workflow `ModuleNotFoundError`. **Mitigation**: inline atomic_write as a ~6-line Python function in the snippet, or gate the import and emit a graceful warning.

2. **`morning-review` has `$CORTEX_COMMAND_ROOT` references** (~4 locations in SKILL.md — lines 10, 82, 86, 114, 117). Plugin-only install fails these invocations. Must either gate these paths or remove (move to #121).

3. **Cross-skill `${CLAUDE_SKILL_DIR}/../lifecycle/references/` traversal** in `skills/refine/SKILL.md` (lines 26, 60, 81, 130). Only works if (a) `${CLAUDE_SKILL_DIR}` substitutes reliably in SKILL.md bodies (issue #9354 — not reliable) AND (b) plugin cache layout preserves sibling skill dirs. **Mitigation**: duplicate shared content into plugin-level `shared/` dir, or use agent-tool file reads with the SKILL.md's own resolved path as anchor.

4. **Hardcoded `~/.claude/skills/lifecycle/references/...` paths** in `skills/lifecycle/references/clarify.md`, `research.md`, `specify.md`, `plan.md`, and `skills/discovery/references/research.md`. Plugin-installed skills live at `~/.claude/plugins/cache/.../plugins/cortex-interactive/skills/...` — the hardcoded paths don't resolve. Agent-based reads of these files would note "file not found" and silently skip the orchestrator-review gates. **Mitigation**: replace hardcoded absolute paths with relative paths or SKILL-dir-relative resolution.

5. **`skills/evolve/SKILL.md` (lines 54–58)** resolves repo root by `readlink`-ing its own SKILL.md path. Plugin layout breaks this — there's no symlink, and plugin-cache path has no relationship to user's working repo. **Mitigation**: read `$PWD` or a user-confirmed repo root marker file.

6. **`cortex-output-filter.sh` location**: the hook is at `claude/hooks/cortex-output-filter.sh`, not `hooks/`. The hook loads patterns from `$HOME/.claude/hooks/output-filters.conf` by default — without the conf, filter is a no-op. Plugin must either ship `output-filters.conf` at `${CLAUDE_PLUGIN_ROOT}/hooks/` and set `OUTPUT_FILTERS_CONF` env var in the hook registration, or accept that the filter is inert until the user manually configures it.

### Failure modes

- **Missing bin shims** (`update-item`, `create-backlog-item`, `generate-backlog-index`): don't exist as scripts or as `python3 -m cortex_command.backlog.*` targets (Python sources live at top-level `backlog/`, not `cortex_command/backlog/`). Skills invoke them as PATH commands (`update-item {id}`). **Mitigation**: build the 3 shims as part of #120. Additionally namespace all bin names as `cortex-*` (recommended for collision avoidance — see §10 below).
- **Namespace find/replace minefield**: naive `/commit` → `/cortex:commit` rewrites retros/ historical logs, URLs like `github.com/.../commit/abc123`, prose like "git commit", substring matches like `/commit/` inside path segments, and word-boundary false-positives (`/pr` vs `/presentation`, `/fresh` vs `/freshwater`). **Mitigation**: scoped rewrite tool that skips retros/, .claude/worktrees/, lifecycle/sessions/; only matches `/<name>` after whitespace/backtick/parenthesis; uses an explicit skill-name allowlist.
- **Plugin → CLI coupling failures on plugin-only install**: `/morning-review` crashes at `$CORTEX_COMMAND_ROOT` refs; `/critical-review` crashes mid-workflow at the Python import; `/lifecycle implement` autonomous-worktree path fails; `/backlog *` hits "command not found" on missing shims; `jcc` errors on `$CORTEX_COMMAND_ROOT` unset. **None of these fail at install time** — all deep in workflow. No preflight-check exists today.
- **Silent orchestrator-review gate skip** if `~/.claude/skills/lifecycle/references/clarify-critic.md` etc. aren't found in plugin cache — clarify and specify phase critic reviews would just not run, quietly.

### Security / anti-patterns

- **Bin PATH shadowing**: a second plugin installed after `cortex-interactive` could ship `bin/update-item`, `bin/commit`, etc. and shadow cortex's bins. `update-item` mutates backlog/ state — silent corruption vector. No documented ordering rule; no opt-out. **Mitigation**: namespace all bins `cortex-*` (requires updating all call sites in skills).
- **`jcc` forwards arbitrary args to `just`** — no allowlist. Acceptable for local dev; as plugin-distributed PATH binary, a malicious sibling plugin's justfile could be invoked. **Mitigation**: restrict `jcc` to cortex-command justfile only (already its design intent — tighten the check).
- **`git-sync-rebase.sh` takes an allowlist file path from `$1`** — path traversal possible (user's own shell, low severity).
- **Python import-injection in critical-review**: `sys.path.insert(0, '$REPO_ROOT')` means `cortex_command.common` could be resolved from a malicious user repo's top-level `cortex_command/` directory. Low-risk (user owns their repo) but pattern deserves a note.

### Assumptions that may not hold

- "Skills that don't `import cortex_command` are safe" — false (inline `python3 -c` imports not caught by grep).
- "`${CLAUDE_SKILL_DIR}` resolves in plugin SKILL.md bodies" — unreliable per #9354.
- "Plugin updates preserve state" — `${CLAUDE_PLUGIN_ROOT}` is wiped; any script caching anything must use `${CLAUDE_PLUGIN_DATA}`.
- "The 13 skills are self-contained" — refine→lifecycle traversal and backlog→bin-shim breaks this.
- "Plugin ships without settings.json permissions" — correct, but hook registration is via `hooks/hooks.json`, not settings.json; spec should clarify.

---

## Open Questions

Resolved items have inline answers. Deferred items carry an explicit "Deferred:" note with rationale.

- **Should `critical-review` and `morning-review` ship in `cortex-interactive` (#120) or `cortex-overnight-integration` (#121)?**
  Deferred: resolved at spec phase. Current evidence points toward **move both to #121** because (a) `critical-review` has an unguarded `cortex_command.common` import that requires spec-level remediation (inline the atomic_write) before it's safe for plugin-only distribution, and (b) `morning-review` has multiple `$CORTEX_COMMAND_ROOT` references and explicit ties to overnight-runner state/reports. Spec phase decides between (i) do the remediation work in #120 and ship them here, vs (ii) move both to #121 where the CLI coupling is acceptable. Recommend (ii) unless remediation cost is low.

- **Namespace for bin utilities: bare names or `cortex-*` prefixed?**
  Deferred: resolved at spec phase. Adversarial recommendation is to prefix all as `cortex-*` (e.g., `cortex-update-item`, `cortex-jcc`) to eliminate cross-plugin collision risk, at the cost of updating all skill call sites. Spec weighs collision-risk vs call-site-churn.

- **Should skills be copies or build-output symlinks from top-level `skills/`?**
  Deferred: resolved at spec phase. Marketplace cache-copy does NOT preserve symlinks to files outside the plugin directory (broken symlink after install). Recommended pattern: keep top-level `skills/` as source of truth; add a `just build-plugin` recipe that copies into `plugins/cortex-interactive/skills/` at publish time; plugin dir is gitignored or committed as generated output. Decision: commit vs. gitignore the generated plugin dir.

- **`${CLAUDE_PLUGIN_DATA}` declaration: keep speculatively or drop?**
  Deferred: resolved at spec phase. No concrete state requires it today. Recommend dropping the line from scope and adding back when a concrete use case appears; premature policy text is spec-creep.

- **`cortex-output-filter.sh` placement: cortex-interactive plugin or machine-config?**
  Deferred: resolved at spec phase. Hook is content-generic (zero repo-specific coupling) but requires `output-filters.conf` to be useful. If shipped in plugin, must also ship a default `output-filters.conf` and set `OUTPUT_FILTERS_CONF` env override. Alternative: leave as machine-config-deployed and remove all hooks from this plugin entirely. Lean toward the latter — reduces plugin surface and matches the ticket's "may live here or in machine-config; decide during spec phase" stance.

- **How are the 3 missing bin shims built?**
  Deferred: resolved at spec phase. Python sources at top-level `backlog/*.py`; shims need to resolve these given `backlog/` is also a user-data dir name. Options: (a) shell shim `#!/bin/bash\nexec python3 "$CORTEX_COMMAND_ROOT/backlog/update_item.py" "$@"` — requires `$CORTEX_COMMAND_ROOT`; (b) move Python sources into `cortex_command/backlog/` package and invoke via `python3 -m`; (c) ship full Python source inside plugin and resolve via `${CLAUDE_PLUGIN_ROOT}`. Spec decides.

- **Namespace migration executor**: what tool actually does the rewrite safely?
  Deferred: resolved at spec phase. Not a mechanical find/replace (see adversarial §3). Options: custom Python script with explicit skill allowlist + path-skip list; codemod-style AST rewrite for markdown; manual per-file review of ~3,387 call sites. Spec defines the executor and validation pass.

- **Graceful-degradation mechanism for plugin-only install (#123 scope, but #120 interacts)**:
  Deferred: #123 ticket owns the mechanism; #120 spec must enumerate every `${CORTEX_COMMAND_ROOT}` / `cortex_command.*` / `python3 -m cortex_command...` reference in the 13 shipped skills and decide per-site whether to: (a) gate with a `command -v cortex` / `python3 -c 'import cortex_command'` check and emit a user-visible warning, (b) remove the reference entirely (move to #121), or (c) inline the dependency.

- **Should bin script name collisions be detectable at install time?**
  Deferred: upstream Claude Code does not surface plugin bin/PATH conflicts at install time. Open possibility: ship a `cortex doctor` preflight script (owned by #117 or a new ticket) that checks for shadowed bins. Not this ticket's scope.
