# Research: Extract optional skills into an in-repo Claude Code plugin

**Clarified intent**: Bundle skills that are not auto-invoked by core workflows (lifecycle, `/refine`, `/research`, `/discovery`, overnight runner, requirements tooling) into a Claude Code plugin that lives in this repo, disabled by default after `just setup`, with opt-in per project. First pass is skills-only. Motivation: reduce per-session context cost by not loading descriptions of skills the user doesn't use.

**Tier**: complex. **Criticality**: high.

## Codebase Analysis

### Skill inventory and core/optional split

26 skills live under `skills/`. Applying the "not auto-invoked by core workflows" criterion yields this split:

**Core (must stay at `skills/`, not extracted)** — invoked or referenced programmatically by a core workflow:

| Skill | Invoked by |
|---|---|
| `lifecycle` | `/refine`, `/dev`, overnight runner, hooks, tests |
| `refine` | `/dev`, overnight runner (`claude/pipeline/backlog.py`) |
| `research` | `/refine` Step 4 |
| `discovery` | `/dev` router, docs |
| `backlog` | every core workflow, bin utilities |
| `commit` | every skill's completion step; `cortex-validate-commit.sh` |
| `pr` | `lifecycle/references/complete.md`, `morning-review/references/walkthrough.md` |
| `dev` | top-level router; `/lifecycle resume` target |
| `critical-review` | `lifecycle/references/specify.md:150`, `lifecycle/references/plan.md:243`, `discovery/references/research.md:128` |
| `requirements` | reads `requirements/*.md` across lifecycle/discovery/refine |
| `overnight` | overnight runner, `bin/overnight-start`, docs |
| `morning-review` | paired with overnight; tightly coupled post-overnight workflow |

**Extractable candidates** — user-invoked only, no programmatic dispatch:

After applying adversarial-review mitigations (see §Adversarial Review), the candidate set shrinks from the initial 14 to ~8–10. Blockers identified:

- `retro`, `diagnose`, `devils-advocate` — referenced by name in the documented call-graph (`skills/skill-creator/SKILL.md:376`) and in extensive retros/lifecycle artifacts. Keep in core; defer.
- `skill-creator` — its `scripts/validate-skill.py` is hardcoded in `justfile:716, 839` and `tests/test_skill_contracts.py:20`. Moving the skill moves its scripts to `~/.claude/plugins/cache/.../`, breaking those paths. Keep in core; defer.

**Final candidate list for first extraction pass (~8 skills)**:

| Candidate | Subfiles | Coupling risk |
|---|---|---|
| `ui-a11y` | `SKILL.md` | Dispatched by `ui-check` → must move together |
| `ui-brief` | `SKILL.md`, `references/` | Part of ui-* cluster |
| `ui-check` | `SKILL.md` | **Has hardcoded `~/.claude/skills/ui-*/SKILL.md` FS probes (lines 11, 74) — must be rewritten before extraction** |
| `ui-judge` | `SKILL.md` | Part of ui-* cluster |
| `ui-lint` | `SKILL.md` | Part of ui-* cluster |
| `ui-setup` | `SKILL.md` | Part of ui-* cluster |
| `harness-review` | `SKILL.md` | No cross-skill references found |
| `pr-review` | `SKILL.md`, `references/` | No programmatic dispatch; purely user-invoked |

`fresh` and `evolve` are edge cases: `fresh` has a file-path coupling (`hooks/cortex-scan-lifecycle.sh` reads `.fresh-resume` marker; hook degrades gracefully when absent), `evolve` reads `retros/` dir (docs coupling only). Both technically extractable; defer decision to spec phase.

### Deployment surface (files that must change)

Source-of-truth paths (not symlinks):

- `justfile` — `setup-force` (L64–73), `deploy-skills` (L224–261), `verify-setup` / `check-symlinks` (L758–762), `validate-skills` (L716, L839). Each iterates `skills/*/SKILL.md`; all must be taught to skip or parallel-walk the plugin path. The justfile repeatedly comments "when adding new symlink targets to any `deploy-*` recipe, also add them here" — a plugin is a new parallel deployment surface.
- `tests/test_skill_contracts.py:20` — hardcodes `REPO_ROOT / "skills" / "skill-creator" / "scripts" / "validate-skill.py"`. Must extend to also scan `plugins/*/skills/`.
- `skills/skill-creator/scripts/validate-skill.py` — takes a directory arg; must be called twice or updated to accept multiple roots.
- `docs/skills-reference.md` (27 occurrences of candidate skill names), `docs/agentic-layer.md` (14 occurrences) — catalog docs need new structure.
- `.claude/skills/setup-merge/scripts/merge_settings.py` — already has `detect_plugins_delta` (L438–448), `--approve-plugins` flag, and Step 7 UI prompt for plugins. Natural integration point for an in-repo plugin entry in `enabledPlugins`.
- `claude/settings.json` — currently has `enabledPlugins` with 3 external plugins (`context7`, `code-review`, `claude-md-management`). New entry: `"cortex-extras@<marketplace>": false`.

### No local plugin scaffolding exists today

No `.claude-plugin/` directory, `plugin.json`, or `marketplace.json` at any path in the repo. The repo authors no plugins today; it only consumes three external ones.

### Cross-reference hazard surface (candidate invocations across repo)

Candidate skill names (`/ui-*`, `/harness-review`, `/pr-review`, `/fresh`, `/evolve`) referenced in 80+ files including:
- `backlog/*.md` (historical)
- `retros/*.md` (historical, immutable)
- `lifecycle/*/events.log` (historical, immutable)
- `docs/skills-reference.md`, `docs/agentic-layer.md`
- `skills/ui-check/SKILL.md` (dispatches other ui-* skills via bare `/ui-*` syntax)
- `skills/retro/SKILL.md:116` (nudges users to `/evolve`)

**Identity change impact**: moving a skill to plugin `cortex-extras` changes its invocation from `/ui-lint` to `/cortex-extras:ui-lint`. Historical artifacts (retros, lifecycle events, backlog items) will not be rewritten. Docs (`docs/skills-reference.md`, `docs/agentic-layer.md`) must be rewritten. Cross-skill invocations (notably `ui-check` dispatching `ui-lint`/`ui-a11y`/`ui-judge`) must be updated to the namespaced form within the plugin.

### Conventions

- **Symlink architecture** (CLAUDE.md): always edit repo copy, never the `~/.claude/` destination. Plugin cache at `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/` is a **copy**, not a symlink — this is a **deviation from the existing convention**. Needs a documented exception or a symlink-preservation strategy at install time.
- **Frontmatter validation**: `tests/test_skill_contracts.py` + `skills/skill-creator/scripts/validate-skill.py` enforce `name` + `description` frontmatter. Must extend to plugin-bundled skills.
- **"Deploy-\* and setup-force must agree"**: justfile comment convention; a plugin deployment must update both.

## Web Research

### Q1 verdict (load-bearing): does disabling a plugin gate skill-description loading?

**Design intent: YES.** Documentation at `code.claude.com/docs/en/plugins-reference` states `enabledPlugins` format `"plugin-name@marketplace-name": true/false` controls which plugins are active; skills from disabled plugins are not discovered. Skills doc: "skill descriptions are loaded into context so Claude knows what's available" — implicit scope is enabled/discovered skills only.

**Publicly reported bug**: [anthropics/claude-code #40789](https://github.com/anthropics/claude-code/issues/40789) (open, labeled `bug` + `has repro`, last activity 2026-03-31, 15 days before this research) — "Disabled plugins' skills still appear in /skills list and in the system prompt's available skills section." Related: #13344 (stale, shared-source marketplace pattern), #40013 (hook firing for disabled plugins).

**Empirical test on this machine, 2026-04-15, Claude Code v2.1.109**:
- Enabled `claude-md-management` plugin → both its command (`revise-claude-md`) and skill (`claude-md-improver`) appear in session catalog as `claude-md-management:*`.
- Disabled `code-review` plugin → its command (`code-review`) does **not** appear anywhere in session catalog. No `code-review:*` entries.
- Session skill list does not distinguish commands from skills — both land in unified catalog.

**Conclusion**: the bug reported in #40789 is **not manifesting on this user's current Claude Code version**. Disabled plugins are correctly gated at the session-catalog layer. Path A (in-repo plugin) delivers real context savings today.

**Durability caveat**: one machine, one version. Claude Code ships daily releases (v2.1.89 → v2.1.109 in the 14-day window before this research). Upstream regressions are possible; a CI canary or manual verification at release adoption is a reasonable mitigation (see Open Questions).

### Plugin mechanics

- **Manifest**: `.claude-plugin/plugin.json` at plugin root. Only `name` required (kebab-case; becomes namespace prefix).
- **Component layout**: `plugins/<name>/skills/<skill>/SKILL.md` (standard path). Custom paths via `skills` field in manifest.
- **Installation scopes**: user (`~/.claude/settings.json`), project (`.claude/settings.json` — team, VCS-shared), local (`.claude/settings.local.json` — gitignored, private), managed (enterprise).
- **Per-project enable**: yes — `enabledPlugins` in `.claude/settings.json` gives per-project granularity.
- **CLI**: `claude plugin install <plugin>@<marketplace>`, `plugin enable/disable`, `plugin uninstall`. Interactive: `/plugin` menu, `/reload-plugins`.
- **Local loading without install**: `claude --plugin-dir ./path` (repeatable).
- **Marketplace**: distribution mechanism via `marketplace.json`. A repo can host its own marketplace referencing its in-tree plugin.
- **Cache**: installed plugins copied to `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`. **Symlinks are preserved** through install caching — relevant for this repo's symlink-driven architecture.
- **Env vars available in plugin context**: `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}`.

### Namespace

Plugin skills appear as `plugin-name:skill-name` — separate namespace from user-level `~/.claude/skills/` (enterprise > personal > project precedence doesn't apply to plugin skills). No naming collisions possible with user-level skills.

### `disable-model-invocation: true` is orthogonal

14 of 26 skills in this repo already carry `disable-model-invocation: true` (all ui-*, fresh, morning-review, evolve, requirements, research, pr-review, overnight, ui-setup). Per Anthropic skills docs, this flag blocks the Skill tool but **does NOT remove descriptions from the session context**. It solves a different problem (preventing Claude from auto-invoking) and is not a substitute for plugin-gating.

### Sources

- [Claude Code Plugins](https://code.claude.com/docs/en/plugins) — quickstart, directory structure, `--plugin-dir`, namespacing.
- [Plugins Reference](https://code.claude.com/docs/en/plugins-reference) — manifest schema, install scopes, CLI commands, path behavior.
- [Claude Code Skills](https://code.claude.com/docs/en/skills) — description loading semantics, `SLASH_COMMAND_TOOL_CHAR_BUDGET`, precedence table.
- [anthropics/claude-code #40789](https://github.com/anthropics/claude-code/issues/40789) — the load-bearing bug report (not manifesting on this machine today).

## Requirements & Constraints

### From `requirements/project.md`

- **Context efficiency** (L33) is a stated quality attribute. Current mechanism (deterministic output filtering) is a different kind of efficiency; this feature is complementary, not overlapping.
- **Maintainability through simplicity** (L30): "Complexity is managed by iteratively trimming skills and workflows." Extraction to a disable-by-default plugin aligns directly.
- **Complexity must earn its place** (L19). This bar is the one #064 failed.
- **Out of scope: "Published packages or reusable modules for others"** (L51). The plugin lives in this repo as opinionated personal tooling, not a distributable module.

### From `CLAUDE.md`

- Symlink architecture is load-bearing. Plugin cache path is a copy, not a symlink — a new exception must be documented or the symlink contract preserved via plugin-install-time symlink preservation.
- `just setup` is the authoritative install command; the plugin path must integrate there, not invent a new one.

### Prior deferral (#063 / #064)

**What was deferred** (quoted from `backlog/064-*.md` L26): *"primary value case (~2.6k tokens/session saved by not loading unused skill frontmatter) is <2% of context, and the implementation commits to ongoing maintenance of a hook-command-string rewriter plus multi-file state coherence. The per-component opt-in work is deferred indefinitely."*

**What would need to change to revisit**: either (a) value grows materially, or (b) implementation escapes the specific costs that killed #064 — namely the R3 hook-command-string rewriter and multi-file state coherence across `lifecycle.config.md` / `merge_settings.py` / SKILL.md / `settings.json`.

**The plugin route was NOT evaluated in #063/#064.** This feature claims to escape the #064 costs because:
- **No hook-command-string rewriter** — plugin gating is upstream-provided, not implemented here.
- **State coherence is reduced** to: (i) the plugin manifest and (ii) one `enabledPlugins` entry per project. `lifecycle.config.md` changes are NOT required.
- **No per-component prompt UX** — `/setup-merge`'s existing plugin-delta path handles the enable/disable prompt.

Residual cost vs. #064's bar:
- The plugin bootstrapping flow (§Adversarial Review Finding 1) adds a one-time-per-machine setup step. This is new complexity #064 did not evaluate.
- The skill-identity change (§Adversarial Review Finding 2) adds a docs/ref-update tax that #064 did not consider.
- The plugin cache copy (§Adversarial Review Finding 10, symlink deviation) is a CLAUDE.md-convention exception that #064 did not consider.

### `#063` DRs that apply

- **DR-2** (no new config files): satisfied. No new config file needed; reuse `enabledPlugins` in `settings.json`.
- **DR-3** (no named bundles): **in tension**. `cortex-extras` IS a named bundle. See §Adversarial Review Finding 6.
- **DR-1/DR-8** (no SessionStart mutation): satisfied. Plugin is upstream-provided; no hook mutation.

## Tradeoffs & Alternatives

Five alternatives evaluated:

| Option | Q1-dependent? | Per-project granularity | Install complexity | Maintenance | Reversibility | Recommendation |
|---|---|---|---|---|---|---|
| **A. In-repo plugin** (user's preferred) | Yes (verified favorable today) | Yes | Medium (see bootstrap question) | Medium-high | Good | **Recommended** |
| B. Separate public repo | Yes | Yes | High | High | Moderate | Reject — no earned benefit over A |
| C. Gitignored / opt-in symlinks | No | No (machine-global) | Low | Low | Trivial | **Viable fallback** if Q1 regresses or bootstrap proves prohibitive |
| D. SessionStart hook prunes skills | No | Yes | Medium | Medium | Easy | Reject — timing fragility, shared-state mutation |
| E. Status quo + audit-only | No | N/A | Trivial | Trivial | N/A | Reject — `just setup` idempotency undoes pruning |

### Recommendation

**Path A (in-repo plugin)** conditional on resolving the bootstrap question (§Open Questions Q1). If bootstrap resolution is too costly, **Path C (gitignored symlinks)** is the fallback; it delivers the context savings with lower mechanism risk at the cost of machine-global-only granularity.

**Why A is recommended despite the adversarial findings**:
- The #064-killing costs (hook-command-string rewriter, multi-file state) are genuinely avoided.
- Per-project granularity matches how the user actually works (different projects need different skills).
- Claude Code's plugin system is the ecosystem's native extension point — aligning now preserves optionality for future external plugins or sharing.

**What Path A must ship with** (from adversarial mitigations):
1. Rewrite `ui-check`'s hardcoded FS probes (SKILL.md L11, L74) before extraction.
2. Shrink candidate set to ~8 (ui-* cluster + `harness-review` + `pr-review`; defer `skill-creator`, `retro`, `diagnose`, `devils-advocate`).
3. Decide bootstrap mechanism (marketplace manifest at repo root + `just setup` step to register, or `--plugin-dir` flag flow) — see Q1.
4. Update `tests/test_skill_contracts.py` + validator scripts to walk `plugins/*/skills/` in addition to `skills/`.
5. Document the plugin-cache-vs-symlink deviation in CLAUDE.md.

## Adversarial Review

### Failure modes and edge cases

1. **Bootstrap loop**: `just setup` runs from shell and cannot invoke session-level plugin-install commands. `/setup-merge`'s `detect_plugins_delta` only flags `enabledPlugins` entries — it does NOT register entries in `~/.claude/plugins/installed_plugins.json`. A plugin enabled in settings but not installed is inert. Resolution requires either (a) a marketplace manifest at the repo root + a `just setup` step that runs `claude /plugin marketplace add .` (requires interactive session), (b) `--plugin-dir` flow (per-invocation, not installed), or (c) writing directly to internal plugin-install files (fragile).

2. **Skill-identity change**: `/ui-lint` → `/cortex-extras:ui-lint`. Historical retros/lifecycle artifacts reference bare names and are immutable; docs can be updated but will stay mixed. `ui-check` dispatches other ui-* skills by bare name — must be rewritten to namespaced form within the plugin, and must handle the "plugin-local invocation" case.

3. **`ui-check` hardcoded FS probes** at `skills/ui-check/SKILL.md:11` and `:74` check `~/.claude/skills/ui-lint/SKILL.md` existence directly. Plugin-cached skills live at `~/.claude/plugins/cache/<marketplace>/cortex-extras/<version>/skills/ui-lint/SKILL.md`. Probes silently fail after extraction. **Must be rewritten to skill-registry lookup or removed before extraction.**

4. **Test/validator coverage**: `tests/test_skill_contracts.py:20` hardcodes `skills/skill-creator/scripts/validate-skill.py`. Extending coverage to plugin skills is straightforward but non-trivial in scope; enumerate all `skills/` iteration sites and add plugin-walk.

5. **`disable-model-invocation` overlap**: 9 of 14 candidates already carry this flag. If the flag doesn't save description tokens (per Anthropic docs), the question of *why* plugin-disable saves them rests entirely on the empirical Q1 test passing. A contrarian reading: Anthropic may treat these as separate concerns (Skill-tool gating vs. catalog gating). The empirical test said catalog gating works today; trust but verify.

6. **Named-bundle tension with DR-3**: `cortex-extras` is a named bundle. Single-plugin all-or-nothing granularity: enabling for one skill pays the token cost for all. Splitting into multiple plugins (ui-extras, dev-extras) restores granularity at the cost of re-introducing the DR-3 pattern, with N marketplace manifests and N per-project enables. Accept all-or-nothing for now; revisit if the granularity cost proves material.

7. **Historical-artifact pollution**: retros and lifecycle events are treated as immutable records. Post-extraction, `/evolve` mining retros for patterns will see stale `/retro` references (because `/retro` stays in core anyway under the narrowed candidate set — so this specific hazard is contained). UI skills' references in historical artifacts may confuse future readers but don't break tooling.

8. **Categorization rot**: no validator enforces "core skills never invoke extracted skills." A future lifecycle edit that adds `/harness-review` as an auto-dispatch silently breaks when the plugin is disabled. Mitigation: one-line test in `tests/test_skill_contracts.py` that scans core SKILL.md bodies for candidate skill names. Cheap; worth adding in the spec.

9. **Plugin cache vs. symlink source of truth**: plugin cache is a copy, not a symlink. CLAUDE.md's "always edit the repo copy" convention is violated. If a user accidentally edits the cache copy, changes are invisible to git. Mitigation: document the exception explicitly; consider `/reload-plugins` re-sync behavior as part of the plugin's contract.

10. **Upstream durability**: plugin system is months old; `#40789` remains open. Upstream regressions could re-introduce the description-loading bug. Symlink-based deployment has been stable for decades. A partial migration (14 of 26 skills to plugin) commits to tracking Anthropic's plugin-system evolution. Mitigation: a CI canary that starts a session with the plugin disabled and asserts no `cortex-extras:*` in its skill catalog.

### Security / anti-pattern concerns

- **Marketplace trust model**: if the repo ships a `marketplace.json`, future contributors could add URL-sourced sibling plugins, expanding the trust surface. Keep marketplace to local-only `./plugins/cortex-extras` entries; reject URL sources.
- **Gitignored enablement**: per-project enable via `.claude/settings.local.json` (gitignored) means state doesn't travel with worktrees. Given this repo's worktree-heavy workflow, opt-in state may be surprising in fresh worktrees. Alternative: use `.claude/settings.json` (VCS-tracked) and have the user explicitly commit their enable choice — friction vs. privacy tradeoff; decide in spec.

## Open Questions

1. **Bootstrap mechanism**: how does `just setup` on a fresh clone produce a plugin entry in `~/.claude/plugins/installed_plugins.json`? Candidate paths (in order of preference):
   - (a) Repo ships `.claude-plugin/marketplace.json` at root listing `cortex-extras` with local `source: ./plugins/cortex-extras`. `just setup` documents that the user must run `claude` once and execute `/plugin marketplace add .` (one-time-per-machine). Disabled-by-default entry ships in `claude/settings.json` template and is merged by `/setup-merge`.
   - (b) `just setup` uses `claude --plugin-dir ./plugins/cortex-extras --print 'noop'` to bootstrap via a headless session (if Claude Code supports `--plugin-dir` in headless mode). Verify capability.
   - (c) Write directly to `installed_plugins.json`. Fragile; reject.
   
   **Deferred to spec phase.** The spec must pick one and document the one-time-per-machine setup friction.

2. **Named-bundle granularity**: accept single `cortex-extras` all-or-nothing for first pass, or split (e.g., `cortex-ui-extras` + `cortex-dev-extras`)? Defer to spec; recommend single bundle for first pass with a note to split if granularity pressure emerges.

3. **Gitignored vs. VCS-shared enable state**: should per-project enable live in `.claude/settings.json` (committed, shared with team/future-self) or `.claude/settings.local.json` (gitignored, private)? This repo's "primarily personal tooling" framing suggests committed is fine. Defer to spec.

4. **Benchmark pre-commit**: before the spec commits the full refactor, should we run an A/B measurement of actual token savings on this Claude Code version (v2.1.109) — disabling `claude-md-management` vs. enabled, measuring the token delta in the system reminder? This would convert the "~2.6k tokens from #064" estimate into a measured number for the plugin path. Deferred to spec; recommend running it in the spec's value-case justification.

5. **`ui-check` rewrite ordering**: should `ui-check`'s FS probes be rewritten as a standalone preparatory ticket BEFORE this feature, or bundled into this feature's implementation? Either works; defer to spec.

6. **CI canary for plugin gating**: should the test suite include a regression test that installs `cortex-extras`, disables it, starts a headless session, and asserts no `cortex-extras:*` skills in the session catalog? This protects against upstream regressions of the #40789 fix. Defer to spec; recommend adding.

All open questions are design decisions appropriate to the spec phase — none block proceeding from research to spec.
