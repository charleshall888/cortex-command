# Research: docs-setup-audit

Audit cortex-command's user-facing docs (README + `docs/setup.md` + the docs index in README) for information architecture and progressive disclosure. The user posed a binary:

> "consolidate the setup instructions to a separate file unless they can be shortened to a quick setup in the readme and then link out to more indepth setup or how to setup per repo and such (validate lifecycle and all that)"

Two options on the table per the user's wording:
- **(I) Tight quickstart in README + link out to a deeper setup file** (option implied by "shortened to a quick setup in the readme and then link out")
- **(II) Consolidate setup instructions to a separate file** (option implied by "consolidate the setup instructions to a separate file")

The parenthetical "how to setup per repo and such (validate lifecycle and all that)" further specifies that the deeper setup must cover per-repo onboarding (`cortex init` → `lifecycle.config.md` → first `/cortex-interactive:lifecycle` invocation) end-to-end.

Scope is **front door + map only** (README, `docs/setup.md`, and the docs index). Deep reference docs (skills-reference, mcp-server, pipeline, sdk, overnight-operations) are out of scope for restructure but in scope for cross-reference and link-target verification.

## Methodology Note

This research draws on three evidence streams of unequal strength:

1. **Codebase analysis** — file:line citations from direct grep/read of the repo. **Strongest** evidence; mechanically verifiable.
2. **Prior-art survey** — README/docs structure of nine OSS projects (claude-code, just, uv, mise, bun, astro, vite, prisma, shadcn). **Advisory** evidence; subject to survivorship bias and audience-fit caveats (see Domain & Prior Art §).
3. **Cold-reader simulation** — a single LLM agent role-playing "a moderately experienced developer who has never seen this repo" walked through README and `docs/setup.md` and produced a friction inventory with severity tags (blocker, confusion, polish). **Advisory** evidence; not measured user data; severity tags are simulated-persona judgments, not calibrated against real-user behavior. Claims sourced from this stream are flagged inline as "(cold-reader)" so they can be weighed accordingly.

Recommendations and option evaluations downstream weight these streams in that order: codebase facts first, prior art as advisory framing, cold-reader as a hypothesis generator about reader friction.

## Research Questions

1. **What's the right depth model for `README → docs/setup.md → docs index`?** → **Both options (I) and (II) are viable; choice is a user preference.** Codebase evidence: README and `docs/setup.md` currently overlap on auth, plugin install, and prerequisites. Prior art (advisory): nine surveyed projects favor "install-detail in a separate doc" but vary on whether the README quickstart is two steps (claude-code, mise) or pointer-only (shadcn, astro). The decision belongs to the user.

2. **Can a fresh fork-and-go user get to "first useful slash command worked" via a sub-5-minute README quickstart?** → **Two codebase-verified defects must be fixed regardless of option choice; one cold-reader-flagged absence is a preference call.** Verified defects: (a) plugin install command syntax differs between `README.md:86-91` (bare form) and `docs/setup.md:36-42` (`@cortex-command` suffix); (b) plugin count differs (README L97 says "six plugins"; Quick Start at L86-91 installs four; setup.md L34/L44 say "four"). Preference call (cold-reader): no smoke test confirms install worked. The smoke-test absence is not a defect — it's a usability hypothesis whose value depends on whether the user wants to add an explicit verification command.

3. **Is the per-repo flow (`cortex init` → `lifecycle.config.md` → first `/cortex-interactive:lifecycle` → backlog) documented end-to-end?** → **No, codebase-verified.** `cortex init` is described in 6 lines [`docs/setup.md:72-78`]; its actual implementation [`cortex_command/init/handler.py:44-223`] has 7 distinct side effects (scaffold lifecycle/, backlog/, retros/, requirements/; write `.cortex-init` marker; append to `.gitignore`; merge sandbox.filesystem.allowWrite into `~/.claude/settings.local.json`) — none documented at the front door. `lifecycle.config.md` schema is referenced only inside `skills/lifecycle/SKILL.md:29-30` and not surfaced front-of-house. There is no narrative connecting `cortex init` → first `/cortex-interactive:lifecycle` invocation.

4. **What duplicates between README and setup.md and where should each live?** → **Three concrete duplications, all codebase-verified.** (a) Authentication is in both files with setup.md being more complete [README:110-140 vs setup.md:82-132]; (b) Plugin install syntax appears in both with conflicting commands [README:86-91 vs setup.md:36-42]; (c) Plugin roster appears in both with different counts/lists [README:99-106 vs setup.md:44-49]. Where each lives is a function of which option (I or II) the user picks.

5. **What's stale or load-bearing post-#148?** → **Two residual issues, codebase-verified; one false positive corrected.** (a) README "What's Inside" lists 7 utilities `[README.md:152]`; `bin/` contains 9 — `cortex-archive-rewrite-paths` and `cortex-archive-sample-select` exist but are undocumented [`bin/cortex-archive-*`]. (b) README L72 says "These instructions target macOS. For Linux or Windows setup, see docs/setup.md" — but `docs/setup.md` Dependencies table [L266-276] still says `brew install` everywhere; cross-platform setup is not actually delivered. **False positive corrected**: the original audit reported the `#auth-resolution-apikeyhelper-and-env-var-fallback-order` anchor as broken, but the heading exists at `docs/overnight-operations.md:514` ("Auth Resolution (apiKeyHelper and env-var fallback order)") and the GitHub-style anchor matches. The link is valid.

6. **What progressive-disclosure patterns work for a "personal toolkit shared publicly" audience?** → **One deeply-transferable analog (claude-code plugins/README.md); the rest of the prior-art survey is advisory at most.** The closest pattern match is `anthropics/claude-code/plugins/README.md` — same audience (Claude Code users), same content shape (table of opinionated components someone might cherry-pick), same scale (single repo, shipped as plugins). Other patterns from the survey (uv's getting-started/, prisma's two-track quickstart, mise's verification command) are advisory analogies; their applicability depends on audience fit (see survivorship caveat in Domain & Prior Art §).

7. **Should setup docs include a "did it work?" smoke test?** → **The codebase audit doesn't force one; cold-reader recommends one; prior art is n=1 (mise).** Current docs have a "Verify install" subsection [`docs/setup.md:62-70`] that confirms plugins are listed but not that the system works end-to-end. A `cortex --version` style command is cheap to add. Whether to add it is a user preference; no codebase evidence forces it.

## Codebase Analysis

### Documentation surface map

Classifications below use these brackets, defined for this artifact:
- **[decide-to-fork]** — content a fresh reader uses to evaluate "is this for me?"
- **[quickstart-critical]** — content needed to run an install and get to first useful command
- **[setup-detail]** — content needed during install but not on the critical path
- **[reference]** — lookup content not needed during onboarding
- **[duplicate-of-X]** — content present in another doc; coverage gap or canonical source unclear
- **[stale-or-suspect]** — content that may be out of date

The "(cold-reader)" tag on a classification means the assessment came from the cold-reader simulation rather than codebase facts. Mixed-source classifications are noted.

**README.md (196 lines)** — sections by classification:
- Pitch + diagrams [L1-63] — [decide-to-fork] for L1-7; cold-reader marked L9-63 as [overload], but this is preference, not verified
- Prerequisites [L65-72] — [quickstart-critical]
- Quick Start [L74-91] — [quickstart-critical]; codebase-verified conflict with setup.md (plugin install syntax)
- Plugin roster table [L95-108] — [reference]; codebase-verified conflict with setup.md (count, list)
- Authentication [L110-140] — [setup-detail] [duplicate-of-setup.md]
- What's Inside [L142-153] — [reference]; codebase-verified incomplete (utilities list)
- Customization [L154-156] — [setup-detail]
- Distribution [L158-165] — [reference]
- Commands [L167-179] — [reference]
- Documentation index table [L181-193] — [reference]
- License [L194-196] — [reference]

**docs/setup.md (276 lines)** — sections by classification:
- Header + machine-config disclaimer [L1-8] — [decide-to-fork]
- Prerequisites [L11-18] — [setup-detail]; drops `just` and Python that README requires
- Install (3 steps + plugin roster + verify) [L20-78] — [quickstart-critical]
- Authentication (3 sub-modes + SDK note) [L82-132] — [setup-detail] [duplicate-of-README]
- Customization (sandbox + statusLine + permissions + MCP) [L135-211] — [setup-detail]; cold-reader observed drift to reference register mid-document
- Per-repo permission scoping (CLAUDE_CONFIG_DIR + direnv + 4 upstream issue links) [L215-251] — [setup-detail]; cold-reader read this as RFC-style content
- macOS notifications [L255-262] — [setup-detail]
- Dependencies table [L266-276] — [reference]

### `cortex init` actual contract

Implementation: `cortex_command/init/handler.py:44-223`. Seven steps:
1. Resolve repo root via `git rev-parse --show-toplevel`; refuse submodules [`cortex_command/init/handler.py:44-90`]
2. Symlink-safety gate (canonical lifecycle path) [`cortex_command/init/handler.py:149`]
3. Pre-flight settings JSON validation [`cortex_command/init/handler.py:152`]
4. Marker present check (`.cortex-init`) [`cortex_command/init/handler.py:155`]
5. Scaffold dispatch (lifecycle/, backlog/, retros/, requirements/ trees, additive on `--update`, overwrite on `--force`) [`cortex_command/init/handler.py:157-189`]
6. Idempotent `.gitignore` append [`cortex_command/init/handler.py:193`]
7. Merge repo's `lifecycle/` path into `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array via `fcntl.flock` [`cortex_command/init/handler.py:197`, `cortex_command/init/settings_merge.py:139-203`]

User-facing documentation of these effects: only step 5 + 7 are mentioned, in 6 lines [`docs/setup.md:72-78`].

### `lifecycle.config.md` schema

File present: `lifecycle.config.md:1-22`. YAML frontmatter keys:
- `type:` (project type enum — semantics undocumented)
- `test-command:` (validation command)
- `skip-specify:` / `skip-review:` (phase-skip flags — interaction with criticality undocumented)
- `commit-artifacts:` (whether lifecycle artifacts get committed)
- `demo-commands:` (optional CLI demo invocations)

Schema is referenced inside `skills/lifecycle/SKILL.md:29-30` (canonical source for the lifecycle skill) but not surfaced in README, setup.md, or any user-facing doc. `NOT_FOUND(query="lifecycle.config.md schema", scope="README.md docs/")`.

### `/cortex-interactive:lifecycle` first-invocation expectations

`skills/lifecycle/SKILL.md:1-385` documents the canonical flow:
- Marker check (`.cortex-init` must exist) [`skills/lifecycle/SKILL.md:155`]
- Phase detection via artifact reverse-lookup [`skills/lifecycle/SKILL.md:41-65`]
- Backlog status check + auto-close [`skills/lifecycle/SKILL.md:80-110`]
- `lifecycle/{slug}/index.md` creation with YAML frontmatter [`skills/lifecycle/SKILL.md:112-146`]
- Backlog write-back (`status=in_progress`, `lifecycle_phase`, `session_id`) [`skills/lifecycle/SKILL.md:148-172`]
- Epic context discovery via `discovery_source` [`skills/lifecycle/SKILL.md:174-196`]
- `/cortex-interactive:refine` delegation [`skills/lifecycle/SKILL.md:214-265`]
- Auto-escalation simple→complex on ≥2 open questions or ≥3 spec decisions [`skills/lifecycle/SKILL.md:248-264`]

None of the above is summarized for users in README or `docs/setup.md`. The handoff "you have a fresh repo, now what?" has no narrative bridge.

### Constraints from project conventions

`requirements/project.md:7` — "Primarily personal tooling, shared publicly for others to clone or fork. Favors a highly customized, iteratively improved system over generic solutions." Audience: Claude Code users evaluating an opinion. **Maintenance budget**: single maintainer; reader population is small and self-selected.

`CLAUDE.md:21-22` and `requirements/project.md:26` — Distribution invariants:
- No symlinks into `~/.claude/`
- `cortex init`'s only `~/.claude/` write is `sandbox.filesystem.allowWrite`
- Cortex-command does NOT own `~/.claude/CLAUDE.md` or `~/.claude/settings.json`

`CLAUDE.md:50` — Owning-doc rule: `docs/overnight-operations.md` owns overnight; `docs/pipeline.md` owns pipeline-module; `docs/sdk.md` owns SDK model selection. Cross-references rather than duplications.

### Stale or suspect content (post-#148 baseline)

- README L152 utility list has 7 entries; `bin/` contains 9 — missing `cortex-archive-rewrite-paths`, `cortex-archive-sample-select` [`bin/cortex-archive-*`]
- README L97 vs L99-106 vs Quick Start: "ships six plugins" / lists six / installs four — silent contract gap
- README L72 says "These instructions target macOS. For Linux or Windows setup, see docs/setup.md" — but `docs/setup.md` Dependencies table [L266-276] still says `brew install` everywhere; cross-platform setup is not actually delivered
- *(Anchor-link finding from earlier draft: corrected — see Q5)*

## Web & Documentation Research

Surveyed 9 reference projects: `anthropics/claude-code`, `casey/just`, `astral-sh/uv`, `jdx/mise`, `oven-sh/bun`, `withastro/astro`, `vitejs/vite`, `prisma/prisma`, `shadcn-ui/ui`. (Could not reach `docs.claude.com` directly; reasoned from the public claude-code README which deep-links to the hosted docs.)

**Survivorship-bias caveat**: All 9 are popular, surviving projects. Patterns observed in their READMEs are correlated with success but not necessarily causal. Several were optimized for top-of-funnel acquisition (uv, vite, mise) — a context cortex-command does not share. Prior-art findings below should be read as **advisory analogies**, not normative requirements.

**Sample-clustering caveat**: uv/mise/bun are sibling dev-toolchain CLIs sharing ecosystem conventions; astro/vite are JS-tooling peers. Statements of the form "N of 9 projects do X" overstate evidence strength because the sample is clustered, not independent.

**Key findings** (with caveats applied):
- **README opening pattern**: Two clusters across the survey — "value-prop one-liner + 1-paragraph + install" (uv, just, mise, claude-code) or "pointer-only" (shadcn, vite, astro). Zero front-load architecture diagrams in README. Caveat: this may be funnel-optimization rather than evaluation-friendliness.
- **Quickstart depth**: Most surveyed projects bottom out at "tool runs"; non-trivial first project is offloaded. Caveat: most surveyed projects have hosted docs sites; cortex does not.
- **Setup-detail split**: Single `docs/setup.md` is rare for projects above trivial size. The dominant split is `install` / `getting-started` / `guides` / `reference` as separate pages (uv, mise, bun, prisma). Caveat: prisma/uv operate at scales (paid hosted services, dedicated docs teams) that justify their split; cortex is single-maintainer.
- **Per-project init flow**: prisma is the closest analog — named docs for "5min Quickstart" vs "Add Prisma to an existing project". Caveat: prisma's two-track exists because their funnel justifies dual-onboarding maintenance; cortex's reader scale may not.
- **Verification step**: Only **mise** (n=1) has an explicit verification command in the README. Not a pattern; a single example.
- **Reference doc index in README**: Two formats actually used — table (astro packages, claude-code plugins) and nested bullet list (bun "Quick links"). Cortex-command's existing Documentation table [`README.md:181-193`] follows the table pattern.

## Domain & Prior Art

**Strongest analog**: `anthropics/claude-code/plugins/README.md` — directory of opinionated components someone might cherry-pick, presented as a markdown table with name + 1-line value + key bullets. Same audience (Claude Code users post-funnel), same content shape (opinionated components), same scale (single-repo). This is the only deeply-transferable analog in the survey; other analogies (uv, prisma, mise) carry less evidentiary weight against cortex's audience and maintenance profile.

**Advisory analogies** (subject to caveats above):
- **prisma's two-track pattern** — "5min Quickstart" vs "Add to an existing project" — maps structurally onto cortex's "fresh install" vs "wire up a repo" gap, but prisma's maintenance scale doesn't transfer.
- **mise's verification pattern** — `mise --version` printing a logo with version line — is the only surveyed example of explicit verification. n=1; not load-bearing as prior art.
- **uv's documentation split** — `getting-started/` + `concepts/` + `guides/` + `reference/` — illustrates a four-bucket IA but assumes a hosted docs site cortex does not have.

**Patterns that don't transfer:**
- Hosted docs site as canonical source (cortex has no website)
- Marketing-style highlights (audience already knows Claude Code; "blazing fast" doesn't translate)
- One-liner project init (cortex needs CLI install + plugin install + `cortex init` — multi-step is structural)
- Massive single-file README (just) — doesn't fit cortex's surface area
- Funnel-driven structural choices (top-of-funnel diagram avoidance, conversion-optimized copy) — cortex's audience is post-funnel evaluators

## Feasibility Assessment

| # | Approach | Effort | Risks | Prerequisites | User-binary alignment |
|---|----------|--------|-------|---------------|----------------------|
| A | **Light touch**: fix duplications/conflicts/stale data; keep README and setup.md structurally as-is | S | Doesn't address per-repo flow gap (Q3); doesn't engage user's binary | None | Neither (I) nor (II) — preserves status quo |
| B | **Quickstart pivot**: trim README to value-prop + 2-step quickstart + verification + plugin roster + docs index; move setup detail (auth, plugins, customization) to `docs/setup.md` | M | May surprise readers who currently rely on README for auth context | Decide whether one or both architecture diagrams stay in README | **Option (I)** — README quickstart + linked deeper setup |
| C | **Consolidate**: trim README to a paragraph + link to setup.md; setup.md becomes the single canonical source for everything beyond the value prop | M | Loses scan-friendliness for evaluators who don't want to click through; "personal toolkit shared publicly" audience may want more in-README context | None | **Option (II)** — consolidate to setup.md |
| D | **Expand in place**: Approach B (light touch + duplication fixes) PLUS expand the existing `docs/setup.md:72-78` cortex-init subsection to cover side effects, lifecycle.config.md schema, and a first-invocation walkthrough — without creating a new doc | M | Setup.md gets longer (~330 lines); risk of drift between walkthrough register and reference register inside one file | None | **Option (II)** — consolidates per-repo flow into the existing setup.md |
| E | **Three-doc split**: README (quickstart only) + `docs/setup.md` (install + plugins + auth + verify) + new `docs/onboarding.md` (cortex init + lifecycle.config.md schema + first lifecycle walkthrough); customize-reference content moves to `docs/customize.md` or stays in setup.md as appendix | L | Adds new doc surfaces to maintain; cognitive load goes up before it goes down; risk of orphaned content during transition; **outside the user's stated binary** | Approach B as a substep | Outside (I) and (II) — not in user's option set |
| F | **Hosted docs site** (off-table): adopt VitePress/Docusaurus | XL | Out of scope per `requirements/project.md:53` — cortex-command "ships as a local editable install for self-hosted use; publishing to PyPI or other registries is out of scope" | Not recommended; flagged for completeness | Outside (I) and (II) |

The user's binary maps to **B** (option I) and **C or D** (option II). **D** is the most user-aligned execution of option (II) because it covers the per-repo flow gap (Q3) without spawning new docs. **E** was earlier framed as a "Three-doc split" recommendation; it remains a valid IA pattern but is outside the user's stated option set and is preserved here for completeness only.

## Option Evaluations

Each evaluation lays out the options with trade-offs, then ends with a **Recommendation** line. The recommendations are the research output's best read of the evidence; user can override at any point. Evidence weight is codebase facts > prior art (with caveats) > cold-reader (advisory).

**Overall recommended path**: User option **(I)** of the binary, executed via Approach **B + D**: trim README to a quickstart-shaped front door, expand `docs/setup.md` in place to cover the per-repo flow gap, no new docs.

### OE-1: README quickstart depth (option I vs II shapes this)

**Codebase facts**: README is currently 196 lines with two architecture diagrams [L9-63], prerequisites, Quick Start, plugin roster (with count discrepancy), authentication (duplicated with setup.md), "What's Inside" (utilities list incomplete), customization, distribution, commands, and docs index. Setup.md is 276 lines with overlapping auth and plugin install content.

**Options**:
- (a) Keep current depth; fix only duplications and stale content (Approach A)
- (b) Trim to value-prop + 2-step quickstart + plugin roster table + verification + docs index; move auth/customization/distribution/commands to setup.md (Approach B)
- (c) Trim aggressively to value-prop + 1-paragraph + 1 link to docs/setup.md (mirroring shadcn/astro)

**Trade-offs**:
- (a) preserves status quo; doesn't engage user's binary
- (b) maps to user's option (I); plugin roster table stays as the load-bearing "directory of opinionated components" pattern (closest analog: `anthropics/claude-code/plugins/README.md`); cold-reader-flagged "overload" of the second screen (advisory) is mitigated; loses one-shot reading flow for users who currently use README as the single doc
- (c) maps to user's option (II) at the README side; depends on setup.md doing more work (see OE-3)

**Recommendation: (b).** Cortex's audience is post-funnel evaluators, not pointer-redirected installers; they need at least a screen of context to judge fit. Plugin roster table stays in README as the high-signal "directory of opinionated components" surface. Auth + customization + commands + distribution sections move to setup.md.

### OE-2: docs/setup.md scope vs split

**Codebase facts**: setup.md drifts from prose-walkthrough [L1-78] to settings.json reference [L135-211] to RFC-style permission-scoping [L215-251]. Cold-reader (advisory) noted the doc "drifts from prose-doc to reference-doc mid-document."

**Options**:
- (a) Single file; reorder sections so reference content comes after walkthrough — supports Approaches A, B, D
- (b) Split into `docs/setup.md` (install + plugins + auth + verify) + `docs/onboarding.md` (cortex init + lifecycle.config.md + first lifecycle) + leave customize-reference in setup.md as appendix — Approach E (outside user's binary)
- (c) Split four ways: `setup.md`, `onboarding.md`, `customize.md`, `permissions.md`

**Trade-offs**:
- (a) keeps maintenance footprint small; aligns with "primarily personal tooling, shared publicly" (low maintenance budget per `requirements/project.md:7`); the drift cold-reader observed could be addressed by section reordering rather than file splitting
- (b) is what an earlier draft of this artifact recommended; it's outside the user's binary and adds maintenance surface; the prisma analog that justified it (advisory only) operates at a scale cortex-command does not share
- (c) further fragments; not justified by current codebase evidence

**Recommendation: (a) — Approach D.** Single file. Reorder so prose-walkthrough sections (install + plugins + per-repo setup + verification + auth) come first; reference content (sandbox config, MCP, permission scoping) follows. No new docs.

### OE-3: cortex init / lifecycle.config.md / first-lifecycle documentation

**Codebase facts**: `cortex init` has 7 documented side effects [`cortex_command/init/handler.py:44-223`], only 2 surfaced in 6 lines [`docs/setup.md:72-78`]. `lifecycle.config.md` schema is referenced only in `skills/lifecycle/SKILL.md:29-30` (no user-facing doc).

**Options**:
- (a) Expand `docs/setup.md:72-78` in place — document side effects + lifecycle.config.md schema + worked first-invocation example. Lives inside setup.md.
- (b) Move all of this into a new `docs/onboarding.md` with a worked example (cortex init in scratch repo → run `/cortex-interactive:lifecycle test` → see lifecycle/test/index.md created → see backlog auto-update). Approach E.
- (c) Split: side-effects in setup.md, schema in `docs/agentic-layer.md`, walkthrough in `docs/onboarding.md`.

**Trade-offs**:
- (a) is the option-(II) execution. Setup.md's "Per-repo setup" section grows from 6 lines to ~30-50 lines including a worked example. Maintenance cost low (one file); risk: the section register may drift from prose-walkthrough to reference dump if not carefully written.
- (b) Approach E. Closes the gap with a dedicated doc; outside the user's binary.
- (c) Most fragmented; matches no surveyed prior art directly.

**Recommendation: (a).** Expand the existing "Per-repo setup" subsection in `docs/setup.md` to include: (1) what `cortex init` writes (the 7 side effects, condensed); (2) `lifecycle.config.md` schema with comments; (3) a worked first-invocation example (`cortex init` in a fresh repo → `/cortex-interactive:lifecycle test-feature` → expected files in `lifecycle/test-feature/`).

### OE-4: README architecture diagrams

**Codebase facts**: Two diagrams currently span README L9-63. The first (L9-43) shows the requirements → discovery → backlog → lifecycle pipeline; the second (L45-63) shows the lifecycle phase flow with criticality/complexity matrix. Cold-reader (advisory) said "they're reference material, not pitch material."

**Options**:
- (a) Keep both diagrams in README
- (b) Keep the lifecycle-phase flow diagram (L45-63); move the pipeline diagram (L9-43) to `docs/agentic-layer.md`
- (c) Move both diagrams to `docs/agentic-layer.md`; replace with a one-paragraph "what this is" intro

**Trade-offs**:
- (a) preserves current behavior; cold-reader's "overload" claim (advisory) is the only argument against
- (b)/(c) reduce README load. Prior-art datapoint "zero of nine surveyed projects front-load architecture diagrams" (advisory; see survivorship caveat) supports moving them, but cortex's audience is post-funnel evaluators rather than top-of-funnel acquisition targets, so the prior-art weight is reduced.
- The classification of which diagram is "pitch" vs "reference" is cold-reader-derived and not codebase-verified

**Recommendation: (b).** Keep the lifecycle phase flow diagram (L45-63) — it's closer to the value prop and complements the trimmed README. Move the pipeline diagram (L9-43) to `docs/agentic-layer.md` where deep readers will find it. This is a judgment call, not a forced move; (a) is also defensible.

### OE-5: Verification step (smoke test)

**Codebase facts**: `docs/setup.md:62-70` confirms plugins listed but not end-to-end function. `cortex --version` and `cortex --print-root` both exist [`cortex_command/cli.py:305-312`].

**Options**:
- (a) Implicit verification (current state — "if `claude /plugin list` shows the plugins, you're set")
- (b) Explicit single command: `cortex --version` + `claude /plugin list` showing four core plugins
- (c) Explicit walkthrough: scratch-repo + first lifecycle invocation (overlaps with OE-3)

**Trade-offs**:
- (a) zero new content
- (b) one command, low maintenance, aligns with cortex's existing CLI capability
- (c) higher value to fresh forkers but higher maintenance; partly redundant with OE-3 (a) or (b)
- Prior-art weight is n=1 (mise) — not load-bearing
- Cold-reader recommended explicit verification (advisory)

**Recommendation: (b) at the install step + (c) folded into OE-3's worked example.** Install verification: `cortex --version && claude /plugin list` showing the four core plugins. End-to-end verification: the worked first-invocation example in OE-3 doubles as a smoke test.

### OE-6: Plugin install command canonicalization

**Codebase facts**: README L86-91 uses `claude /plugin install cortex-interactive` (bare); setup.md L36-42 uses `/plugin install cortex-interactive@cortex-command` (marketplace-scoped). Setup.md L58-60 warns against the bare `marketplace.json` URL form. **Behavioral equivalence between the bare and `@cortex-command` forms has not been verified in this research** — the codebase evidence is documentation-text only.

**Options**:
- (a) Use `@cortex-command` everywhere
- (b) Use bare form everywhere
- (c) Document both, explain when each applies

**Trade-offs**:
- The conflict between README and setup.md is itself a defect that must be fixed regardless of which form is canonical
- (a) matches setup.md's stated preference; precise but slightly noisier
- (b) shorter; may fail in multi-marketplace setups (unverified)
- (c) explicit but adds documentation overhead

**Recommendation: (a)** with behavioral spot-check during implementation. If both forms work in single-marketplace setups, `@cortex-command` is the more precise default. If the bare form fails under any condition, this is forced. Verification step: run both `claude /plugin install cortex-interactive` and `claude /plugin install cortex-interactive@cortex-command` in a fresh shell; document the result in the implementation PR.

## Open Questions

These items either require user preference input or remain unresolved by the research. They are flagged here so they can be resolved in spec/plan rather than in research.

1. **Which option of the user's binary to pursue: (I) README quickstart + linked deeper setup, or (II) consolidate to setup.md?** All option evaluations downstream depend on this choice.

2. **Should README's value-prop be rewritten?** Cold reader (advisory) said the opening paragraph is "genuinely compelling." Prior art suggests "lead with what this is and who it's for"; the current opening already does this. Voice/tone preference.

3. **Where does `docs/setup.md`'s "Per-repo permission scoping" section (L215-251) belong?** It reads as RFC-style content with four upstream Claude Code issue links. (a) leave in place; (b) move to a research-archive link with one-paragraph summary in setup.md; (c) move to `docs/customize.md` if that file is created. Depth preference.

4. **Should the docs index table in README move to setup.md?** Cold-reader (advisory) flagged it as overload; prior art mixed (claude-code's plugins/README has a table; bun has "Quick links"). Placement preference.

5. **Cross-platform setup**: in scope for this restructure. README L72 promises Linux/Windows coverage in setup.md; setup.md must deliver. Add a "Linux / Windows notes" subsection to setup.md's Dependencies area covering: `apt`/`pacman`/etc. install commands for `just`, `uv`, `gh`, `tmux`; the `terminal-notifier` macOS-only caveat; any platform-specific `cortex init` behavior (none expected, but verify).

6. **Plugin install command behavioral equivalence** (OE-6): both forms need empirical verification during implementation. Spec-phase verification step.

