# Research: Audit epic 113 wrap-up and post-113 distribution-doc cleanup

Whole-repo audit of pre-epic-113 install-flow references and 113-era transition scaffolding, plus rewrite of `docs/plugin-development.md` as a post-122 maintainer dogfood guide. Ticket 124 (migration guide) stays `wontfix` — no pre-113 migration aside.

## Codebase Analysis

Inventory of stale references, grouped by category. Each finding is `path:line — text — why stale`.

### Confirmed-stale (will change)

**`docs/plugin-development.md` — full rewrite target**

The whole doc is 113-transition scaffolding. Current premise: *"before ticket 122 publishes the production marketplace manifest, maintainers need a way to install the in-repo plugin reproducibly."* That premise is dead — 122 has shipped, the stub is the production manifest. Five distinct future-tense ticket-N references:

- `docs/plugin-development.md:5` — «before ticket 122 publishes the production marketplace manifest»
- `docs/plugin-development.md:16` — «cortex-interactive (already shipped in ticket 120)»
- `docs/plugin-development.md:20` — «Until ticket 122 lands the production marketplace manifest»
- `docs/plugin-development.md:22` — «The committed stub at `.claude-plugin/marketplace.json` (ticket 121, Task 10)»
- `docs/plugin-development.md:81` — «When ticket 122 lands, `.claude-plugin/marketplace.json` will be edited»

The mechanics it describes (`/plugin marketplace add $PWD`, `just build-plugin`, dual-source pre-commit) are still valid post-122. Verdict: rewrite as a steady-state dogfood guide, drop all ticket-N temporal coupling.

**`docs/skills-reference.md`**

- Line 6 — «Assumes: Claude Code is set up and skills are symlinked.» Skills aren't symlinked anymore; they ship via plugins.

**`README.md`**

- Line 187 — table cell for `docs/setup.md`: «Installation, symlinks, authentication, customization». "symlinks" is dead — setup.md no longer covers symlink-based install.

**`.claude-plugin/marketplace.json`**

- Line 19 — `cortex-overnight-integration` description: «Hosts the canonical cortex MCP server (PEP 723 single-file server.py) plus overnight skill runner hooks; integrates with the cortex CLI on PATH and the cortex-interactive plugin to drive autonomous lifecycle execution». Mixes implementation detail ("PEP 723 single-file server.py") with product purpose. Anthropic's own marketplaces use one-sentence verb-first product descriptions; this should match.

**`lifecycle.config.md`**

- Line 20 — «New config files must follow the symlink pattern (source in repo, symlinked to system location)». This is a review-criteria line that is now actively wrong — epic 113 retired symlink deployment. Will reject correct PRs.

**`CLAUDE.md`** (project instructions, not user-facing docs, but in scope per "whole repo")

- Line 48 — «Run `just setup-githooks` after clone to enable the dual-source drift pre-commit hook.» Codebase agent flagged that this overstates importance — hooks live in `.githooks/` and are enabled per-clone via `git config core.hooksPath` (which `setup-githooks` does). Keep but ideally clarify it's contributor-only, not user-onboarding.

**`docs/setup.md`**

- Line 180 — «You do not need to hand-edit this. Run `cortex init` (ticket 119)…». The `(ticket 119)` parenthetical is no longer useful — drop the ticket number, keep the sentence.
- Line 194 — «see the pre-117 version of `claude/settings.json` in this repo's git history (it contains roughly 80 curated entries).» Historical pointer to a pre-cleanup template.
- Line 196 — «git show HEAD:claude/settings.json on the pre-117 commit». Same — archaeology instructions for users.

**`docs/backlog.md`**

- Line 205 — «post-epic-120, bin/ deployment is plugin-owned» — "post-epic-120" is now historical, not transitional; reword as steady-state.
- Lines 208–210 — symlink-resolution explanation references `~/.local/bin/` symlink, which was the pre-113 distribution surface. Plugin-owned `bin/` is on PATH via plugin install; the symlink-resolution preamble is no longer accurate.

### Confirmed-clean (already correct, no change)

- `README.md` lines 1–186, 188+ — accurate post-113 phrasing.
- `CLAUDE.md` lines 1–47, 49+ — accurate.
- `docs/agentic-layer.md` — symlink references (line 311) describe the legitimate `lifecycle/sessions/latest-overnight` runner-state symlink, not install-flow symlinks. Verify wording during spec but expected fine.
- `docs/overnight-operations.md`, `docs/overnight.md`, `docs/pipeline.md`, `docs/sdk.md` — symlink references are runner-state internals, not install guidance.
- All four `plugins/*/.claude-plugin/plugin.json` description fields — clean (only top-level `marketplace.json` description for `cortex-overnight-integration` reads transitional).
- `justfile` — recipes themselves are clean. `setup-githooks` recipe is fine; the issue is messaging in CLAUDE.md, not the recipe.
- All skill `SKILL.md` files in `skills/` and `plugins/*/skills/` — no pre-113 patterns.
- `retros/*.md` — append-only convention; **out of scope** for editing.

### Existing patterns and conventions to follow

- **Heading style**: level-1 (`#`) for title, level-2 (`##`) for major sections.
- **Backlink convention**: user-facing guides start with `[← Back to README](../README.md)`.
- **Code fences**: triple backticks with language (`bash`, `json`).
- **Plugin description style**: one sentence, present tense, product-focused (what it does, not what it hosts or how it's wired).
- **Doc ownership** (per `CLAUDE.md` lines 50–51): `docs/overnight-operations.md` owns round loop and orchestrator behavior; `docs/pipeline.md` owns pipeline-module internals; `docs/sdk.md` owns SDK model-selection. Update the owning doc; link from others.

## Web Research

Grounding in current Claude Code plugin marketplace conventions (2026), so the cleanup aligns with canonical patterns rather than drifting.

### Canonical Anthropic documentation

- **Plugins**: https://docs.claude.com/en/docs/claude-code/plugins
- **Plugin marketplaces**: https://docs.claude.com/en/docs/claude-code/plugin-marketplaces
- **Skills**: https://docs.claude.com/en/docs/claude-code/skills

### Reference marketplace shape (anthropics/claude-code itself)

Anthropic dogfoods the same in-tree marketplace pattern cortex-command uses. Their `.claude-plugin/marketplace.json` (https://github.com/anthropics/claude-code/blob/main/.claude-plugin/marketplace.json):

```json
{
  "$schema": "https://json.schemastore.org/claude-code-marketplace.json",
  "name": "claude-code-plugins",
  "version": "1.0.0",
  "description": "Bundled plugins for Claude Code...",
  "owner": { "name": "Anthropic", "email": "support@anthropic.com" },
  "plugins": [
    {
      "name": "agent-sdk-dev",
      "description": "Development kit for working with the Claude Agent SDK",
      "source": "./plugins/agent-sdk-dev",
      "category": "development"
    }
  ]
}
```

**Conventions cortex-command does not currently follow:**
- `$schema` field at top of `marketplace.json` (json.schemastore.org/claude-code-marketplace.json)
- `version: "1.0.0"` field
- `category` field per plugin (Anthropic uses: `development`, `productivity`, `security`, `learning`, `database`, `deployment`, `monitoring`, `math`, `design`, `location`)
- `owner.email` (cortex-command has this — clean)

**Description style:**
- Sentence case, not title case
- One concise line, action-oriented
- Verb-first or noun-phrase product statements
- Examples: *"Development kit for working with the Claude Agent SDK"*, *"Migrate your code and prompts from Sonnet 4.x to Opus 4.5"*

### Local dogfood pattern — directly answered

Anthropic's plugin-marketplaces doc (under "Test locally before distribution"):

> ```
> /plugin marketplace add ./my-local-marketplace
> /plugin install test-plugin@my-local-marketplace
> ```

CLI form is also documented: `claude plugin marketplace add ./my-marketplace`.

**Conclusion: `/plugin marketplace add <local-path>` is the current officially documented dogfood pattern for testing a multi-plugin marketplace from a local checkout.** This is what `docs/plugin-development.md`'s rewrite should describe. There is also `claude plugin validate .` for linting plugin.json + marketplace.json + skill/agent/command frontmatter before publishing — worth mentioning.

### Per-plugin layout convention

From `anthropics/claude-code/plugins/README.md`:

```
plugin-name/
├── .claude-plugin/plugin.json
├── commands/   (optional)
├── agents/     (optional)
├── skills/     (optional)
├── hooks/      (optional)
├── .mcp.json   (optional)
└── README.md
```

cortex-command's plugins follow this layout. Anti-patterns flagged in the canonical docs:

- Don't put `commands/`/`agents/`/`skills/`/`hooks/` inside `.claude-plugin/` — only `plugin.json` goes there.
- Don't use `../` in plugin source paths (plugins are copied into a cache).
- Don't reuse reserved names (`claude-code-marketplace`, `anthropic-marketplace`, etc.).
- Omitting `version` in `plugin.json` means every commit counts as a new release.

### Closest CLI+plugin prior art

- `pchalasani/claude-code-tools` (https://github.com/pchalasani/claude-code-tools) — Python CLI installable via `uv tool install` plus a Claude Code marketplace via `claude plugin marketplace add`. Documents the two installs as **independent steps**. cortex-command's existing two-step quick-start (CLI bootstrap → `/plugin marketplace add`) matches this pattern.

## Requirements & Constraints

### Distribution model (`requirements/project.md`)

- Line 7 — *"Primarily personal tooling, shared publicly for others to clone or fork."* Audience: personal use, public visibility, not a vendor product.
- Lines 53–54 — *"The `cortex` CLI ships as a local editable install (`uv tool install -e .`) for self-hosted use; publishing to PyPI or other registries is out of scope."* Hard constraint: docs must not reference PyPI or registry installs.

### Doc ownership (`CLAUDE.md`)

- Lines 50–51 — `docs/overnight-operations.md` owns round-loop and orchestrator behavior; `docs/pipeline.md` owns pipeline-module internals; `docs/sdk.md` owns SDK model-selection. *"When editing overnight-related docs, update the owning doc and link from the others rather than duplicating content."*
- Line 22 — *"Cortex-command ships as a CLI installed via `uv tool install -e .` plus plugins installed via `/plugin install`. It no longer deploys symlinks into `~/.claude/`."* This is the canonical statement of the post-113 model — all install docs must align with it.

### Out of scope (`requirements/project.md`, lines 36–54)

- Dotfiles, machine configuration, application code, published packages, setup automation for new machines.
- Implication for audit: nothing here changes scope, but confirms the audit shouldn't try to document machine-config (separate repo).

### Retros (`CLAUDE.md`)

- *"Session retrospectives (dated problem-only logs)"* — append-only by convention. **Out of scope** for editing.

### Requirements docs themselves are silent on doc completeness

- No quality gate, no completeness checklist for user-facing docs in `requirements/`. The audit's depth is bounded by user request ("whole-repo sweep") not by a written constraint.

### Adjacent gap (not in scope, surfaced for awareness)

- `requirements/remote-access.md` line 60 notes a known broken link: `docs/setup.md` references `remote/SETUP.md` which does not exist. Documented as an open issue, separate from epic 113. Listed under Open Questions below for the spec to decide whether to fix opportunistically.

## Tradeoffs & Alternatives

### Cleanup execution strategy

| Approach | Complexity | Maintainability | Alignment |
|---|---|---|---|
| (A) Surgical edits everywhere | Lowest | Mediocre for plugin-development.md (premise is dead) | Strong with [Prefer minimal fixes] |
| (B) Section-level rewrites | Medium | Best for clusters | Reasonable |
| (C) Full rewrites of plugin-development.md + setup.md | Highest | Wrong for setup.md (mostly correct) | Misaligned for setup.md; aligned for plugin-development.md |
| **(D) Mixed — surgical for most, full rewrite for plugin-development.md only** | Slightly higher upfront | Best overall — each doc gets the treatment its staleness justifies | Best alignment with [Prefer minimal fixes] AND user instruction |

**Recommendation: (D) Mixed.**

### plugin-development.md rewrite scope

| Approach | Recommendation |
|---|---|
| (A) Maintainer-only dogfood guide — `/plugin marketplace add $PWD`, `just build-plugin`, `setup-githooks`, drift-fix workflow, build-output vs hand-maintained plugins | **Recommended.** Bounded audience, scope already matches the doc's title, mechanics still valid post-122. |
| (B) Plugin-author guide — how to author a new plugin from scratch | Misaligned. No third-party author audience today; would rot fast. |
| (C) Both | Worst — diffuse audience, double rot risk. |

### Sequencing

| Approach | Recommendation |
|---|---|
| (A) Single PR touching every file | Worst review experience. |
| (B) Stack of focused PRs (P1 onboarding → P2 plugin-development → P3 metadata → P4 sweep) | Over-engineered for solo doc-only work. |
| (C) Single PR with structured commit history (one commit per category) | **Recommended.** Per-category commits give reviewer a clean reading order; one CI run, one merge. |

### Verification

| Approach | Recommendation |
|---|---|
| (A) Manual review only | Brittle — phrasing can creep back in. |
| (B) Grep-based CI linter | False-positive risk (the word "symlink" is legitimate for `latest-overnight`); needs narrow regex; rot vs. prevention is a wash at this scale. |
| (C) Manual + one-time grep audit at the end of cleanup | **Recommended.** Captures audit gain at completion without recurring infra. Revisit (B) only if regression happens within 90 days. |

### Summary recommendation stack

Mixed-strategy edits (D) → maintainer-only dogfood rewrite of plugin-development.md (A) → single PR with per-category commits (C) → one-time grep audit at the end (C).

## Open Questions

1. **`docs/setup.md:194,196` "pre-117" historical pointers.** **Resolved: Delete them.** The surrounding text already advises composing your own permission list; pre-117 is opaque to anyone outside the ticket history.
2. **Adopt `marketplace.json` schema-alignment with Anthropic's reference?** **Resolved: Yes — add `$schema`, `version: "1.0.0"`, and per-plugin `category`.** Aligns with `anthropics/claude-code`'s own marketplace and unblocks editor schema validation.
3. **`docs/setup.md:286` references missing `remote/SETUP.md`.** **Resolved: Drop the broken link.** Don't leave a 404 in the install doc; remote/SETUP.md creation is a separate concern.
4. **CLAUDE.md:48 `setup-githooks` framing.** **Deferred to spec implementation: leave as-is.** The line is correct for contributors (including the maintainer); rewording is low-value.
5. **`docs/agentic-layer.md:311` "symlink" usage.** **Deferred to spec edit pass: verify only.** Tradeoffs agent confirmed it refers to the legitimate `latest-overnight` runner-state symlink; no rewrite expected.
