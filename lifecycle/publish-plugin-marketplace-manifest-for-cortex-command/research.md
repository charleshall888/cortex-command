# Research: Publish plugin marketplace manifest for cortex-command (ticket 122)

## Epic Reference

Part of the `overnight-layer-distribution` epic (ticket 113); see `research/overnight-layer-distribution/research.md` for cross-ticket context — this lifecycle scopes to ticket 122's marketplace.json edit and accompanying docs only.

## Codebase Analysis

### Files that will change

- **`.claude-plugin/marketplace.json`** — extend stub from one entry to four; add top-level `metadata.description` (Adversarial finding 9). Optionally add `$schema` for editor validation.
- **`README.md`** — replace the "ships once ticket 122 lands" placeholder note (line 102) and stale `cortex-command-plugins` marketplace URL in Quick Start (line 86) and "Limited / custom installation" (lines 103–107). Update `### Plugin roster` prose around the table (lines 92–115).
- **`docs/setup.md`** — extend the existing "Add and install the plugins" section (lines 32–47) to cover all four plugins with `${CORTEX_COMMAND_ROOT}` for the overnight-runner case. Delete the stale "Symlink Architecture" section (lines 59–69) that contradicts the no-symlinks distribution model.
- **`docs/dashboard.md`** (lines 99, 123) and **`docs/skills-reference.md`** (lines 139, 150) — update stale "install from cortex-command-plugins" pointers for `cortex-ui-extras` (decision needed; see Open Questions).
- **`docs/agentic-layer.md`** (lines 9, 37, 56, 317) and **`docs/plugin-development.md`** (lines 5, 20–23, 81–85) — same stale-pointer pattern, lower priority (decision needed; see Open Questions).
- **Possibly** `plugins/cortex-ui-extras/.claude-plugin/plugin.json` and `plugins/cortex-pr-review/.claude-plugin/plugin.json` — normalize `author` from string form to object form, matching the convention established in commit `1f5745a` for the other two plugins (decision needed; see Open Questions).

### Current marketplace.json (full content)

```json
{
  "name": "cortex-command",
  "owner": {
    "name": "charleshall888",
    "email": "charliemhall@gmail.com"
  },
  "plugins": [
    {"name": "cortex-overnight-integration", "source": "./plugins/cortex-overnight-integration"}
  ]
}
```

The marketplace `name` ("cortex-command") becomes the `@cortex-command` suffix used in `/plugin install <name>@cortex-command`. Plugin `source` paths are relative to the repo root.

### Per-plugin manifests (source of truth for marketplace entries)

| Plugin | name | description | author shape | extras |
|---|---|---|---|---|
| cortex-interactive | `cortex-interactive` | "Interactive Claude Code skills, hooks, and CLI utilities from cortex-command for day-to-day development workflows" | **object** `{name, email}` | — |
| cortex-overnight-integration | `cortex-overnight-integration` | "Overnight skill runner hooks that integrate with the cortex CLI on PATH and the cortex-interactive plugin to drive autonomous lifecycle execution" | **object** `{name, email}` | — |
| cortex-ui-extras | `cortex-ui-extras` | "Experimental UI design skills (brief, setup, lint, a11y, judge, check) for Claude Code interactive workflows" | **string** `"Charlie Hall <…>"` | `"experimental": true` |
| cortex-pr-review | `cortex-pr-review` | "Multi-agent GitHub pull request review pipeline for Claude Code" | **string** `"Charlie Hall <…>"` | — |

Author-shape inconsistency is a residue of the partial fix in commit `1f5745a` ("Fix plugin manifest author field schema (string -> object)"). The Claude Code spec accepts both forms.

**No plugin.json sets a `version` field.** DR-4 git-SHA versioning intent is intact (verified by grep). This is a forward-looking risk surface, not a current bug.

### Plugin contents at a glance

- `cortex-interactive`: `bin/` (7 scripts), `hooks/`, `skills/` (15 skills incl. research, commit, lifecycle, refine, etc.).
- `cortex-overnight-integration`: `hooks/`, `skills/` (overnight, morning-review), `.mcp.json` registering the `cortex-overnight` MCP server (runs `cortex mcp-server`).
- `cortex-ui-extras`: `skills/` only (ui-lint, ui-judge, ui-brief, ui-check, ui-a11y, ui-setup).
- `cortex-pr-review`: `skills/pr-review/` only.

No plugin has its own README — install/walkthrough content must live at the repo root or under `docs/`.

### `${CORTEX_COMMAND_ROOT}` requirement surface

- **Required for `cortex-overnight-integration`**: skill files reference it in 9+ places (`overnight/SKILL.md`: lines 46, 50, 226, 234, 249, 252, 296, 318; `morning-review/SKILL.md`: 10, 82). Used as anchor for `lifecycle/sessions/` paths and as the working-directory base for the overnight pipeline.
- **Required for `cortex-interactive` shell-side use**: `bin/cortex-jcc` errors out with "jcc: CORTEX_COMMAND_ROOT is not set"; bin shims (`cortex-create-backlog-item`, `cortex-update-item`, `cortex-generate-backlog-index`) use it as fallback when the `cortex` CLI isn't on PATH.
- **Not required for** `cortex-ui-extras` or `cortex-pr-review` (pure skill bundles).
- Convention from `install.sh:41` is `target=${CORTEX_COMMAND_ROOT:-$HOME/.cortex}`. Bin shims sanity-check by grepping `pyproject.toml` for `name = "cortex-command"`.

### docs/ inventory

Files: `agentic-layer.md`, `backlog.md`, `dashboard.md`, `interactive-phases.md`, `mcp-server.md`, `overnight-operations.md`, `overnight.md`, `pipeline.md`, `plugin-development.md`, `sdk.md`, `setup.md`, `skills-reference.md`. **No `docs/install.md` exists.** Per CLAUDE.md and the README docs table, `docs/setup.md` is the canonical setup guide.

### README structure (top-level, lines 92–119)

Existing sections in order: title/intro, ASCII diagrams, **Prerequisites**, **Quick Start** (with `### Plugin roster` table — already lists all four plugins with core/extras tiers — and `### Limited / custom installation`), **Authentication**, **What's Inside**, **Customization**, **Distribution**, **Commands**, **Documentation**, **License**.

The README is structurally ready: the right scaffolding (Quick Start → Plugin roster) exists; the work is updating prose, not adding a top-level section.

### Stale pointers to `cortex-command-plugins` (post-122 are wrong)

- `README.md:86, 103–107, 115` — still routes users to old marketplace.
- `docs/setup.md:47` — stale `cortex-command-plugins` pointer for ui-extras.
- `docs/dashboard.md:99, 123` — tells users to install ui-judge/ui-a11y from the old marketplace.
- `docs/skills-reference.md:139, 150` — same pattern.
- `docs/agentic-layer.md:9, 37, 56, 317` — same pattern, multiple mentions.
- `docs/plugin-development.md:5, 20–23, 81–85` — describes ticket 122 as future work; needs past-tense updates.

### Conventions to follow

- Marketplace entries: `"source": "./plugins/<name>"` string form (matches stub and Claude Code spec for in-tree).
- No `version` field in marketplace entries or plugin.json (DR-4 git-SHA versioning).
- Description in marketplace entry should mirror plugin.json's description (single source of truth).
- README "Plugin roster" already uses core/extras tiering — preserve that vocabulary.
- Cross-link rather than duplicate (CLAUDE.md "Overnight docs source of truth" principle).
- Pre-commit hook (`just setup-githooks`) enforces dual-source drift between top-level `skills/`/`hooks/`/`bin/` and the assembled plugin trees (`BUILD_OUTPUT_PLUGINS = "cortex-interactive cortex-overnight-integration"`); marketplace.json has no such drift constraint.

### Integration points

- Marketplace install order: `uv tool install -e .` → `export CORTEX_COMMAND_ROOT=...` → `/plugin marketplace add charleshall888/cortex-command` → `/plugin install <name>@cortex-command` per plugin → `/reload-plugins` → optionally `cortex init` per repo.
- `cortex-overnight-integration`'s `.mcp.json` registers an MCP server requiring `cortex` on PATH and `${CORTEX_COMMAND_ROOT}` set.
- `cortex-pr-review` and `cortex-ui-extras` impose no install prerequisites beyond the plugin step.

## Web Research

### Marketplace schema (canonical: code.claude.com/docs/en/plugin-marketplaces)

**Top-level marketplace fields:**
- Required: `name` (kebab-case, no spaces, public-facing in `@<name>`), `owner` (`{name (req), email (opt)}`), `plugins` (array).
- Optional: `metadata.description` (validator emits non-blocking warning if missing), `metadata.version`, `metadata.pluginRoot`, `allowCrossMarketplaceDependenciesOn`, `$schema` (anthropic.com/claude-code/marketplace.schema.json or json.schemastore.org/claude-code-marketplace.json).
- **Reserved names**: `claude-code-marketplace`, `claude-code-plugins`, `claude-plugins-official`, `anthropic-marketplace`, `anthropic-plugins`, `agent-skills`, `knowledge-work-plugins`, `life-sciences`. `cortex-command` is fine.

**Per-plugin entry fields:**
- Required: `name`, `source`.
- Optional: `description`, `version`, `author`, `homepage`, `repository`, `license`, `keywords`, `category`, `tags`, `strict`.
- `strict: true` (default) — `plugin.json` is authoritative; marketplace entry merges in. `strict: false` — marketplace entry IS the entire definition.

### `source` field shape

Both forms accepted:
- **Relative path string** (canonical for in-tree): `"./plugins/cortex-interactive"`. Must start with `./`. No `../`. Resolves relative to marketplace root (the directory containing `.claude-plugin/`).
- **Object form** for git/url/npm sources: `{source: "github", repo, ref?, sha?}`, `{source: "url", url, ...}`, `{source: "git-subdir", url, path, ...}`, `{source: "npm", package, version?, ...}`.
- **There is no `{type: "directory", path: "..."}` form.** The string form is canonical for in-tree plugins.

**Critical caveat**: relative paths only resolve when the marketplace is added via git (`/plugin marketplace add owner/repo`). If a user adds via direct URL to marketplace.json, relative-path sources fail at install time. → Docs must steer users to the git form.

### Version omission and DR-4 confirmation

> "Claude Code resolves a plugin's version from the first of these that is set: 1. `version` in `plugin.json`, 2. `version` in the marketplace entry, 3. The git commit SHA. For git-based source types and **relative paths inside a git-hosted marketplace, you can omit `version` entirely and every new commit is treated as a new version. This is the simplest setup for internal or actively-developed plugins.**" (code.claude.com/docs/en/plugin-marketplaces#version-resolution-and-release-channels)

**Critical anti-pattern**: "Avoid setting `version` in both `plugin.json` and the marketplace entry. The `plugin.json` value always wins silently." Verified clean for cortex (no plugin.json sets version).

### Skill namespace after install — material UX implication

Plugins namespace their skills/commands as `/<plugin-name>:<skill>`. So:
- After `/plugin install cortex-interactive@cortex-command`, `commit` is invoked as **`/cortex-interactive:commit`**, NOT `/cortex:commit`.
- This contradicts CLAUDE.md and existing skill docs that say "Always commit using the `/cortex:commit` skill."
- A plugin name like `cortex` cannot be used (each plugin needs a unique name within a marketplace).

This collision is **not introduced by ticket 122** — it pre-exists for any user who has installed `cortex-interactive` from the old `cortex-command-plugins` marketplace — but ticket 122 is the moment it becomes the default install path and reaches new users. Memory note `project_skill_namespace_migration.md` confirms `claude -p '/cortex:foo'` already fails when running headless against the plugin install.

### Public marketplace examples

- **anthropics/claude-code (demo, `claude-code-plugins`)**: 13 plugins, all in-tree. Per-entry: `name`, `description`, `source`, `version: "1.0.0"`, `author: {name, email}`, `category`. Top-level: `$schema`, `version`, `description`. Categories used: `development`, `productivity`, `learning`, `security`. (https://github.com/anthropics/claude-code/blob/main/.claude-plugin/marketplace.json)
- **anthropics/claude-plugins-official**: 200+ plugins, auto-added on Claude Code startup. Most omit `version` and rely on `sha` field on the source object. Uses `$schema: "https://anthropic.com/claude-code/marketplace.schema.json"`. (https://github.com/anthropics/claude-plugins-official/blob/main/.claude-plugin/marketplace.json)
- **kivilaid/plugin-marketplace**: 77 plugins; demonstrates `metadata.pluginRoot: "./plugins"` to shorten paths.
- **anthropics/claude-code/plugins/README.md**: Multi-plugin README pattern is **table-of-plugins + single install snippet**. This is what cortex-command should follow.

### Submission to anthropics/claude-plugins-official

The official marketplace is auto-added on Claude Code startup; submission is via in-app forms (https://claude.ai/settings/plugins/submit, https://platform.claude.com/plugins/submit), **not via GitHub PR**. Reviewed by Anthropic. This confirms the ticket's correct framing of submission as optional/deferred — it's gated by an external review process, not a code edit.

### Common install support traps (from web research)

- "Plugin not found in any marketplace" → marketplace listing stale; fix is `/plugin marketplace update cortex-command`.
- Skills don't appear after install → `/reload-plugins`, then if needed `rm -rf ~/.claude/plugins/cache`.
- "/plugin command not recognized" → user on old Claude Code; `npm update -g @anthropic-ai/claude-code` or `brew upgrade claude-code`.

## Requirements & Constraints

### From `requirements/project.md`

- Distribution model (line 53, Out of Scope): "Published packages or reusable modules for others — the cortex CLI ships as a local editable install (`uv tool install -e .`) for self-hosted use; publishing to PyPI or other registries is out of scope." (Plugin marketplace distribution is implicitly in scope; DR-8 in epic research flagged this line for update — deferred.)
- File-based state and per-repo sandbox registration constraints — apply to `cortex init`, not directly to ticket 122.
- No constraints in observability.md / pipeline.md / multi-agent.md / remote-access.md affect this ticket.

### From `CLAUDE.md`

- "Ships as a CLI (`uv tool install -e .`) plus plugins installed via `/plugin install` in Claude Code. ... It no longer deploys symlinks into `~/.claude/`."
- Docs inventory: "setup guide, agentic layer, overnight, skills reference" → `docs/setup.md` is the install doc.
- Cross-link, don't duplicate (overnight docs source-of-truth principle applies to install docs by analogy).

### From epic research (DRs)

- **DR-2** (line 244): two-plugin split at runner boundary (`cortex-interactive` non-runner, `cortex-overnight-integration` runner-coupled). Confirmed in tickets 120/121.
- **DR-4** (line 274): `uv tool install` + `curl | sh` bootstrap as the install path. (Ticket 122 body cites "DR-4 git-SHA versioning" — this is shorthand, not a literal DR quote. Git-SHA versioning is supported by the Claude Code marketplace spec; cite the spec, not DR-4.)
- **DR-9** (line 309): originally kept `cortex-command-plugins` as separate extras marketplace. **Superseded by ticket 122 body**: extras folded for ui-extras/pr-review; android-dev-extras stays in old repo.
- Acknowledged risk (line 387): "Three upgrade verbs (`cortex upgrade` / `/plugin update` / `cortex init --update`) are a real regression vs. today's single `git pull && just setup`. No local mitigation."

### From sibling tickets

- **Ticket 117** (complete): `cortex setup` ships; out of scope for 117 explicitly defers plugin install to "tickets 120, 121, 122 — `cortex setup` does not install plugins, users run `/plugin install` themselves."
- **Ticket 144** (complete): ui-extras and pr-review vendored; `plugins/cortex-ui-extras/` and `plugins/cortex-pr-review/` exist. Ticket 144 also stated: "Update README.md to mention the four shippable plugins and which are core (cortex-interactive, cortex-overnight-integration) vs extras (cortex-ui-extras, cortex-pr-review), if the core/extras distinction is retained" — already done.
- **Ticket 124** (status: backlog, blocked-by: [118, 122]): owns migration narrative for users who already added `cortex-command-plugins`. Step 4 of ticket 124's scope: "Add the marketplace from ticket 122, install `cortex-interactive` (+ optionally `cortex-overnight-integration`)." → Ticket 122's docs need at minimum a one-paragraph hand-off note to ticket 124 for users already on the old marketplace.
- **Ticket 113** (epic): ticket 122 is gated on 115, 116, 117, 120, 121.

## Tradeoffs & Alternatives

### Decision A — Existing stub entry treatment
- **A1** (preserve as-is, append three): smallest diff; risks shipping inconsistent shape (3 entries with `description`, 1 without).
- **A2** (rewrite stub for consistency, add three): one extra line touched; uniform shape; matches per-plugin manifests.
- **A3** (replace entire file): largest diff; needlessly destroys git blame; ignores ticket's "edit, not author" guidance.
- **Recommended: A2.** The ticket explicitly frames this as an edit (rules out A3); shipping four entries with three having `description` and one not is exactly the cosmetic drift that produces a follow-up commit.

### Decision B — Install doc shape
- **B1** (new `docs/install.md`): matches ticket's literal phrasing; creates duplication with existing `docs/setup.md` install section.
- **B2** (per-plugin READMEs in `plugins/<name>/README.md`): four new files; doesn't match user discovery flow.
- **B3** (expand `README.md` "Installation"): conflicts with the README's own pointer to `docs/setup.md` for non-mac users.
- **B4** (extend `docs/setup.md`): zero new files; honors "or equivalent" in ticket; CLAUDE.md and README already point here.
- **Recommended: B4.** `docs/setup.md` is already the canonical install doc. Splitting install across `setup.md` and a new `install.md` creates two-file drift on the same content.

### Decision C — Per-plugin walkthrough structure
- **C1** (per-plugin section, same template): predictable but mostly filler ("no extra prerequisites" repeated).
- **C2** (combined `marketplace add` + per-plugin install commands, then "Plugin-specific prerequisites" subsection for special cases): shortest doc; only the two prerequisites that exist (cortex CLI on PATH for the runner, `${CORTEX_COMMAND_ROOT}` for overnight) get prose.
- **C3** (tabular plugin × prerequisite × install matrix): table cells crowded; README already has the at-a-glance table.
- **Recommended: C2.** Matches the actual asymmetry of the four plugins.

### Decision D — README marketplace section placement
- **D1** (new top-level "Plugins" / "Marketplace" section): duplicates existing `### Plugin roster` under Quick Start.
- **D2** (extend existing Quick Start / Plugin roster section): scaffolding already exists; work is updating prose around the table.
- **D3** (subsection under Distribution): wrong audience (operator vs. new user); worse discoverability.
- **Recommended: D2.** README already has the right scaffolding. Replace the "ships once ticket 122 lands" placeholder with now-true content; make core/extras tiering explicit as install commands; keep the existing one-line android-dev-extras pointer.

### Decision E — anthropics/claude-plugins-official submission
- **E1** (defer to follow-up backlog ticket): scope discipline; aligns with ticket's "don't block on" framing; standard cortex pattern for "consider later."
- **E2** (mention as future work in spec, no implementation): future-work sections drift; backlog is the right home.
- **E3** (implement now): violates "don't block on"; couples ticket to external review timeline.
- **Recommended: E1.** Submission is via in-app form (not a code edit) and gated by Anthropic review — naturally a separate workstream.

## Adversarial Review

### Verified clean

- **Plugin name reservations**: none of `cortex-interactive`, `cortex-overnight-integration`, `cortex-ui-extras`, `cortex-pr-review` collide with reserved names. Marketplace name `cortex-command` is also clean.
- **`version` landmine**: no plugin.json sets `version`. DR-4 intent intact today. Forward-looking: a CI/lint check or CONTRIBUTING note could prevent a future regression — out of strict ticket 122 scope; could be a follow-up.

### High-priority issues — must address in spec

1. **Skill namespace collision (`/cortex:foo` → `/cortex-interactive:foo`)**. After install, `/plugin install cortex-interactive@cortex-command` namespaces skills as `/cortex-interactive:commit`, not `/cortex:commit`. CLAUDE.md and the entire skills inventory still say `/cortex:foo`. A user who installs from the freshly published marketplace, follows CLAUDE.md, and types `/cortex:commit` will get "command not found" and may conclude the marketplace is broken. This is the highest-impact omission in the proposed plan. **Mitigation choice deferred to spec** — see Open Questions.

2. **Stale `docs/setup.md` "Symlink Architecture" section (lines 59–69)**. Directly contradicts the no-symlinks distribution model and CLAUDE.md. If the install walkthrough is extended in this same file without removing the stale section, a user reading top-to-bottom will see contradictions. **Mitigation**: delete lines 59–69 as part of the same edit (the existing `setup.md` extension that B4 calls for).

3. **Ticket 124 interaction — duplicate-named plugins across marketplaces**. A user who already added `cortex-command-plugins` and installed `cortex-ui-extras` from there is, post-122, in an undefined state — two marketplaces declare the same plugin name. Behavior is unspecified across the sources researched. Ticket 124 owns the migration narrative, but ticket 122 is the trigger event. **Minimum mitigation**: a one-paragraph hand-off note in the install walkthrough pointing existing-old-marketplace users to ticket 124's migration steps (or: "remove the plugin from the old marketplace before installing from cortex-command").

4. **Stale doc pointers**. After 122 ships, `docs/dashboard.md:99,123` and `docs/skills-reference.md:139,150` still tell users to install ui-extras from cortex-command-plugins. Shipping a marketplace whose own first-party docs point users at a different marketplace for the same plugin is incoherent. **Mitigation choice deferred to spec** — see Open Questions.

### Medium-priority polish — recommended in spec

5. **`metadata.description` warning**. The current marketplace.json has no `metadata` block; the validator emits a non-blocking warning on every `/plugin marketplace add`. **Mitigation**: add `"metadata": {"description": "..."}` (one line). First-impression polish.

6. **Source-path-via-URL footgun**. Users who copy/paste the raw marketplace.json URL from GitHub's file view will get silent failure (relative paths break). **Mitigation**: a one-sentence note in README and setup.md walkthroughs ("add via `owner/repo` form, not via direct marketplace.json URL").

7. **`/reload-plugins` cache trap**. After install, skills may not appear without `/reload-plugins` (or `rm -rf ~/.claude/plugins/cache`). **Mitigation**: a "Verify install" subsection in setup.md walking through `/plugin list` → `/reload-plugins` → cache nuke as last resort.

8. **DR-4 misattribution in ticket body**. Ticket 122 body cites "git-SHA versioning per research DR-4" but research.md's DR-4 is actually about install path. The technical decision is correct (Claude Code spec supports it); citation is wrong. **Mitigation**: in spec, cite `code.claude.com/docs/en/plugin-marketplaces` directly; this is hygiene, not a blocker.

9. **plugin.json author shape inconsistency**. `cortex-ui-extras` and `cortex-pr-review` use legacy string form; the other two use object form. Spec accepts both, but mixed shapes signal "marketplace isn't carefully curated." Commit `1f5745a` started normalizing 4 days ago; ticket 122 is the natural completion point. **Mitigation choice deferred to spec** — see Open Questions.

## Open Questions

These are decisions the spec phase must resolve with the user. Each has been deferred from research because either (a) the choice depends on user judgment about scope discipline vs. polish, or (b) the cost is low and the benefit is real but the user owns scope.

- **Skill namespace collision strategy**: Ticket 122 must surface the `/cortex:foo` → `/cortex-interactive:foo` change. Options: (a) install walkthrough callout only — point users at the new namespace and the bare-`/foo` workaround; (b) update CLAUDE.md and skill docs to use the new namespace; (c) a hybrid. Updating CLAUDE.md is broader than 122's literal scope but the docs ship a working install path, which depends on the namespace question being addressed. **Deferred: Spec decides.**
- **Stale doc updates scope**: Ticket 122's literal scope is marketplace.json + README + install walkthrough. But shipping it leaves `docs/dashboard.md`, `docs/skills-reference.md`, `docs/agentic-layer.md`, and `docs/plugin-development.md` actively wrong about where to install ui-extras/pr-review. Options: (a) update only README + setup.md (literal scope); (b) also update dashboard.md and skills-reference.md (highest-traffic stale docs); (c) full sweep across all five files. **Deferred: Spec decides.**
- **plugin.json author normalization**: Update `cortex-ui-extras/.claude-plugin/plugin.json:4` and `cortex-pr-review/.claude-plugin/plugin.json:4` from string to object author form? Two trivial Edits matching commit `1f5745a`'s convention. Out of strict ticket scope per a literal read; in-scope under "make the marketplace shippable cleanly." **Deferred: Spec decides.**
- **Ticket 124 hand-off explicitness**: How explicit should ticket 122's docs be about the migration for existing-old-marketplace users? Options: (a) a one-paragraph "if you previously added cortex-command-plugins, see ticket 124"; (b) an inline list of the duplicate plugin names (ui-extras, pr-review) with concrete uninstall-then-reinstall steps; (c) silent (ticket 124 owns it entirely, ticket 122 ships clean docs for new users only). **Deferred: Spec decides.**
- **Removal of `docs/setup.md` "Symlink Architecture" section (lines 59–69)**: Adversarial review judged this in-scope because it contradicts the install walkthrough being added in the same file. Confirm: **Deferred: Spec decides** whether to delete in this ticket or carve out a follow-up.
- **anthropics/claude-plugins-official follow-up ticket**: Confirm we create a new backlog item for the optional submission (E1) rather than dropping the option entirely. **Deferred: Spec decides.** Default: create the follow-up ticket.
