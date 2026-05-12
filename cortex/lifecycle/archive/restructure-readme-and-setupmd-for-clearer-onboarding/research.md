# Research: Restructure README and docs/setup.md for clearer onboarding (ticket 150)

## Epic Reference

This ticket is decomposed from the **docs-setup-audit** epic. The full epic audit lives at `research/docs-setup-audit/research.md` and contains the codebase-verified defect list, OE-1 through OE-6 option evaluations, and the cold-reader simulation methodology note (advisory, not measured). This ticket is the README/setup.md restructure scope; sibling tickets in the epic (if any) are out of scope here. Cross-platform delivery was dropped from this ticket per user decision during Clarify — README.md:72's unmet "see docs/setup.md for Linux/Windows" promise will be removed rather than authoring untested Linux/Windows install steps.

## Codebase Analysis

### Files in scope

| File | Lines | Role in restructure |
|---|---|---|
| `README.md` | 196 | Trim per OE-1; remove cross-platform line at L72; standardize plugin install syntax in Quick Start (L86-91); fix plugin count drift (L97 vs. L99-106 vs. install steps); complete utilities list at L152; relocate auth section (L110-140) and pipeline diagram (L9-43) |
| `docs/setup.md` | 276 | Reorder per OE-2 (prose-walkthrough first, reference content after); expand per-repo flow (L72-78) per OE-3; fix plugin install syntax at L36-42 (already uses `@cortex-command` form — confirm canonicalization here); remove brew-only Dependencies table cross-platform pretense (L266-276) |
| `docs/agentic-layer.md` | 320+ | Receive pipeline diagram from README L9-43. **Caveat**: existing Mermaid "Diagram A — Main Workflow Flow" at L72-114 already covers similar pipeline content at different fidelity — relocation must reconcile this (replace or coexist) |
| `lifecycle.config.md` | 22 | Reference for OE-3 schema documentation; the file itself is project config, not a doc — but its schema must be surfaced in `docs/setup.md` |

### Plugin install syntax (OE-6) — codebase findings

- `README.md:86-91` uses bare form: `claude /plugin install cortex-interactive`
- `docs/setup.md:36-42` uses scoped form: `/plugin install cortex-interactive@cortex-command`
- `docs/dashboard.md`, `docs/agentic-layer.md`, `docs/plugin-development.md`, `docs/skills-reference.md` consistently use the scoped `@cortex-command` form
- `.claude-plugin/marketplace.json` defines 6 plugins
- No tests in `cortex_command/` exercise plugin install syntax verification
- Audit at `research/docs-setup-audit/research.md:100-103` explicitly leaves equivalence unverified

### `lifecycle.config.md` schema (OE-3)

Six frontmatter keys, all defined in `lifecycle.config.md:1-22`. Only `test-command` is actively consumed by code:

| Key | Type | Consumer | Behavior if missing |
|---|---|---|---|
| `type` | enum (e.g., `"other"`) | None — semantics undocumented in any user-facing doc | N/A |
| `test-command` | string | `cortex_command/overnight/daytime_pipeline.py:173-191` | Defaults to `"just test"` |
| `skip-specify` | boolean | None (defined, not read) | N/A |
| `skip-review` | boolean | None (defined, not read) | N/A |
| `commit-artifacts` | boolean | None (defined, not read) | N/A |
| `demo-commands` | array of `{label, command}` | None (defined, not read) | N/A |

The 5 unread keys are an open question for spec: document them as advisory placeholders, or document only `test-command` and stub the rest with a "reserved" note. The body of `lifecycle.config.md` (lines 12-22) currently contains a Review Criteria section in prose — that's the project-specific override surface for `/cortex-interactive:lifecycle`'s review phase per `skills/lifecycle/SKILL.md:29-30`.

### `cortex init`'s 7 side effects (OE-3) — verified

Implementation at `cortex_command/init/handler.py:44-223`. Audit's count of 7 is confirmed:

| # | Side effect | File:line | Notes |
|---|---|---|---|
| 1 | Resolve repo root via `git rev-parse --show-toplevel`; refuse submodules | `handler.py:44-90` | Raises `ScaffoldError` if not in git repo or in submodule |
| 2 | Symlink-safety gate on canonical lifecycle path | `handler.py:149` (calls `scaffold.check_symlink_safety`) | |
| 3 | Pre-flight `~/.claude/settings.local.json` validation | `handler.py:152` (calls `settings_merge.validate_settings`) | Aborts if malformed |
| 4 | Marker check (`.cortex-init`) gates additive vs. overwrite | `handler.py:155` | |
| 5 | Scaffold dispatch — creates `lifecycle/`, `backlog/`, `retros/`, `requirements/` trees + writes `.cortex-init` marker | `handler.py:157-189` | |
| 6 | Idempotent `.gitignore` append (lifecycle/ entries) | `handler.py:193` | |
| 7 | Merge repo's lifecycle path into `~/.claude/settings.local.json:sandbox.filesystem.allowWrite` (with `fcntl.flock` serialization) | `handler.py:197` + `settings_merge.py:139-203` | The only write cortex-command does inside `~/.claude/` |

Currently `docs/setup.md:72-78` mentions only side effects 5 and 7. Side effects 1–4 and 6 are entirely undocumented at the front door.

### `docs/agentic-layer.md` anchor for pipeline diagram (OE-4)

Current section structure has an existing `## Workflow Diagrams` heading at line 68, with two subsections:
- `### Diagram A — Main Workflow Flow` (L70) — Mermaid graph covering pipeline at different fidelity
- `### Diagram B — Lifecycle Phase Sequence` (L116) — phase flow

**The natural anchor for the README pipeline ASCII diagram is `## Workflow Diagrams`**, but coexisting with Mermaid Diagram A risks visual redundancy at different fidelities. Spec must decide: (a) replace Mermaid Diagram A with the ASCII pipeline diagram (consolidates), (b) keep both as A1/A2 with a "high-level" / "narrative" labeling, or (c) merge content of A and the ASCII into a single canonical version. **Open question for spec.**

### CLI utilities count

`bin/` (canonical source) contains 9 `cortex-*` utilities:

```
cortex-archive-rewrite-paths      ← undocumented in README:152
cortex-archive-sample-select      ← undocumented in README:152
cortex-audit-doc
cortex-count-tokens
cortex-create-backlog-item
cortex-generate-backlog-index
cortex-git-sync-rebase
cortex-jcc
cortex-update-item
```

`plugins/cortex-interactive/bin/` mirrors all 9 (dual-source enforcement per `CLAUDE.md`).

### `CLAUDE.md:50` owning-doc rule (verbatim)

> Overnight docs source of truth: `docs/overnight-operations.md` owns the round loop and orchestrator behavior, `docs/pipeline.md` owns pipeline-module internals, and `docs/sdk.md` owns SDK model-selection mechanics. When editing overnight-related docs, update the owning doc and link from the others rather than duplicating content.

This rule is the basis for the ticket's OOS section. README and `docs/setup.md` are not on the protected list and are safe to restructure. `docs/agentic-layer.md` is also not on the protected list.

### Conventions to follow

- Settings JSON files must remain valid after any edit (per `lifecycle.config.md` review criteria).
- Single-source-of-truth: when content overlaps, designate one owning doc and link from others.
- Plugin install: the codebase already uses `@cortex-command`-scoped form everywhere except `README.md:86-91` — standardization on scoped form (OE-6) restores consistency rather than introducing it.
- Dual-source mirroring for `bin/` utilities applies to code, not to docs — but if the README utilities list is consolidated, both `bin/` and the plugin's `bin/` reflect the same set, so no mirroring concern for docs.

## Web Research

### Plugin install command equivalence (OE-6) — strong evidence for scoped form

Anthropic's official Claude Code docs ([code.claude.com/docs/en/discover-plugins](https://code.claude.com/docs/en/discover-plugins)) document **only the scoped form** `/plugin install plugin-name@marketplace-name`. Findings:

- Every install example in the canonical docs is scoped — even for the auto-added `claude-plugins-official` marketplace, examples consistently include the `@claude-plugins-official` suffix.
- The bare-name form is **not documented as supported syntax** anywhere on the Anthropic site.
- [GitHub issue anthropics/claude-code#20593](https://github.com/anthropics/claude-code/issues/20593) — "Plugin install matches wrong marketplace when same plugin name exists in multiple marketplaces" — confirms a bare-name resolution path *exists internally* but is unreliable when marketplaces collide.
- Custom marketplaces require `/plugin marketplace add` first (which `docs/setup.md` already documents).

**Implication**: OE-6's recommendation to standardize on `@cortex-command` is the correct alignment with Anthropic's documented patterns. The "verification" requirement reduces from "verify behavioral equivalence" to "verify the scoped form works as documented" — the bare form being unreliable is the documented Anthropic position, not a hypothetical risk.

### README quickstart patterns (5 prior-art examples)

| Project | Quickstart length | Recommended path | Docs strategy | First-run walkthrough |
|---|---|---|---|---|
| `uv` (astral-sh) | ~20-25 lines | 1 standalone installer + 2 alternates | Heavy delegation to `docs.astral.sh/uv/` | Yes — multi-step `init → add → run → lock → sync` |
| `bun` (oven-sh) | ~20-25 lines | install script marked "(recommended)" + 3 alternates | Banner: "Read the docs →" | No first-run walkthrough in README |
| `mise` (jdx) | ~15-20 lines | One primary `curl https://mise.run \| sh` + link | Heavy delegation per section | Yes — exec → install → set env → run tasks |
| `just` (casey) | Long install section | Many platforms exhaustive | Explicit: README also as a book | Demonstrative example, no scaffold walkthrough |
| `gitleaks` | Compact | Homebrew + Docker + Go + binary | Project page + docs site | Three scan modes as quick examples |

**Common dimensions**: Healthy READMEs cap install at ~20 lines, pick **one recommended path** with alternates terse, and push detailed configuration to `docs/`. The `mise` model (one install + link to "Getting started") fits cortex-command best because cortex has a `docs/` directory, no hosted docs site, and a single primary install path.

### Init side-effects documentation patterns

- **Strong examples**: `cargo new` (Rust Book walks every file generated), `astro create` (interactive prompts shown verbatim + completion messages + explicit next-step commands), `terraform init` (community fills the gap the official docs leave).
- **Weak examples**: `git init` (high-level only, no enumeration), `npm init` (says it asks questions, doesn't enumerate fields populated).

**Pattern that fits `cortex init`**: cargo-book + astro completion-message — show the directory tree created, then for any file modified outside the project (cortex-command writes to `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite`), explicitly say *which file*, *which key*, *what value*. The cortex doc has a domain-specific reason to be more explicit than `git init`'s docs: it touches the user's global Claude Code settings, which is a higher-trust action.

### Docs index placement convention

- README links to **named entry-points** in `docs/` (e.g., "Setup guide", "Skills reference") rather than reproducing a full TOC.
- `docs/README.md` or `docs/index.md` is idiomatic for the docs index itself.
- A separate "docs index" section in the top-level README that lists every doc is generally an **anti-pattern** when `docs/` exists.

### Anti-patterns to avoid

- Listing every install method with equal weight — pick one and mark "(recommended)".
- Burying prerequisites — state them *before* the install command.
- Glossing over global side effects — tools that mutate user-global state without disclosure violate trust expectations.
- Bare-name install commands when scoped form is the documented standard (per Anthropic's own pattern).

Sources: [discover-plugins](https://code.claude.com/docs/en/discover-plugins), [plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces), [anthropics/claude-code#20593](https://github.com/anthropics/claude-code/issues/20593), [astral-sh/uv](https://github.com/astral-sh/uv), [oven-sh/bun](https://github.com/oven-sh/bun), [jdx/mise](https://github.com/jdx/mise), [casey/just](https://github.com/casey/just), [Rust Book — Hello, Cargo!](https://doc.rust-lang.org/book/ch01-03-hello-cargo.html), [terraform init reference](https://developer.hashicorp.com/terraform/cli/commands/init), [Astro install guide](https://docs.astro.build/en/install-and-setup/), [makeareadme.com](https://www.makeareadme.com/), [The Good Docs Project README template](https://www.thegooddocsproject.dev/template/readme).

## Requirements & Constraints

### Project posture (`requirements/project.md:7`)

> Primarily personal tooling, shared publicly for others to clone or fork. Favors a highly customized, iteratively improved system over generic solutions.

**Tension acknowledged**: doc restructure focused on forker onboarding works *with* the "shared publicly" clause and *against* the "highly customized" clause. Resolution: the audit's defects are correctness fixes (regardless of audience); the per-repo flow gap closes a friction surface that affects both the maintainer and forkers. Cross-platform was dropped during Clarify in deference to the "highly customized" posture.

### Owning-doc rule (`CLAUDE.md:50`, verbatim above)

Protected from this restructure (do not move/duplicate content into):
- `docs/overnight-operations.md`
- `docs/pipeline.md`
- `docs/sdk.md`
- `docs/mcp-server.md` (implicit per `requirements/pipeline.md`)

Free to restructure: `README.md`, `docs/setup.md`, `docs/agentic-layer.md`.

### Distribution constraint (`CLAUDE.md`)

> Cortex-command ships as a CLI installed via `uv tool install -e .` plus plugins installed via `/plugin install`. It no longer deploys symlinks into `~/.claude/`.

The README and setup.md must accurately describe this three-step flow: `uv tool install -e .` → `/plugin install` → `cortex init`. Not PyPI, not brew, not symlinks.

### Sandbox / per-repo registration constraint (`requirements/project.md:26`)

> **Per-repo sandbox registration**: `cortex init` additively registers the repo's `lifecycle/` path in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array. This is the only write cortex-command performs inside `~/.claude/`; it is serialized across concurrent invocations via `fcntl.flock` on a sibling lockfile.

OE-3's expanded cortex init flow must accurately describe: (a) **additive** append (not overwrite); (b) the file path (`~/.claude/settings.local.json`); (c) the key (`sandbox.filesystem.allowWrite`); (d) `fcntl.flock` serialization across concurrent invocations.

### Defense-in-depth permissions (`requirements/project.md:33`)

> The global `settings.json` template ships conservative defaults — minimal allow list, comprehensive deny list, sandbox enabled. The overnight runner bypasses permissions entirely (`--dangerously-skip-permissions`), making sandbox configuration the critical security surface for autonomous execution.

OE-3's expanded cortex init flow should note that cortex init's sandbox registration is the supported path — users do **not** hand-edit `sandbox.filesystem.allowWrite` (per `docs/setup.md:180`'s existing wording).

## Tradeoffs & Alternatives

For each major OE recommendation, alternatives explored and verdicts. Detail abridged; full analysis in `research/docs-setup-audit/research.md`.

| OE | Recommendation | Strongest alternative | Verdict |
|---|---|---|---|
| OE-1 README depth | Trim to value-prop + 2-step quickstart + plugin roster + verification + docs index | Status quo (fix point defects only) | **Validate.** Status-quo leaves verified duplications live; minimal-skeleton would lose the plugin-roster table (the strongest pattern match). |
| OE-2 setup.md ordering | Approach D — single file, prose-walkthrough first, reference content second | TOC-driven with anchors at top | **Validate.** TOC signals "reference material" and pulls against OE-3's prose-walkthrough goal. Reorder achieves the same scannability via section structure. |
| OE-3 cortex init flow | Expand `docs/setup.md:72-78` in place — 7 side effects + lifecycle.config.md schema + worked first-invocation example | Dedicated `docs/cortex-init.md` | **Validate.** A dedicated doc maps to the rejected Approach E (out-of-scope per ticket). Splitting the worked example into a separate file is strictly worse — severs the abstract-spec/concrete-example link. |
| OE-4 diagrams | Keep lifecycle phase flow in README; move pipeline diagram to `docs/agentic-layer.md` | Keep both in README | **Validate WITH FLAG.** Weakest evidentiary basis (cold-reader judgment, not codebase-verified). Defensible either way; tie-broken by `CLAUDE.md:50`'s owning-doc spirit. **Open issue**: agentic-layer.md already has Mermaid Diagram A — spec must reconcile (replace, coexist, or merge). |
| OE-6 plugin install canonicalization | Standardize on `@cortex-command` form everywhere | Bare form everywhere | **Validate.** Web research shows Anthropic docs only document the scoped form; bare-name resolution is unreliable per [issue #20593](https://github.com/anthropics/claude-code/issues/20593). The verification step reduces from "behavioral equivalence" to "scoped form works as documented." |

### Hidden risks not surfaced by the original audit

1. **OE-3 register drift**: setup.md grows to ~330 lines with worked example sitting alongside reference JSON. Mitigation: hard horizontal-rule separators between walkthrough and reference registers; consistent "What this does / Why" framing for prose, raw config snippets for reference.

2. **OE-1 plugin roster duplication tax**: keeping the roster table in *both* README and setup.md creates a permanent two-file edit surface for new plugins. A pre-commit drift check could mitigate but is out of OE-1 scope. **Decision for spec**: accept the tax, or pick one canonical home (push to setup.md, leave a "see setup.md" pointer in README, with the README quickstart still showing one example install).

3. **OE-4 diagram split → potential third copy**: agentic-layer.md already has Mermaid Diagram A covering similar pipeline content. Moving the README ASCII diagram in without addressing Diagram A creates two fidelities of the same content. **Open question for spec.**

4. **OE-6 verification scope**: spec must pin which marketplace state to test under (single vs. multiple) and what "works" means (skill loads vs. listed in `/plugin list`). Web research supplies most of this — Anthropic's documented form is scoped — but the cortex-specific check (does `@cortex-command` work after `/plugin marketplace add charleshall888/cortex-command`) still needs a one-time confirmation in a clean Claude Code session.

5. **OE-5 verification surfaces**: the audit recommends `cortex --version && claude /plugin list` at the install step *and* folded into OE-3's worked example. Risk: three verification surfaces (README quickstart, setup.md install, setup.md per-repo) drifting into slightly different copies. Spec must specify exactly one verification block per surface and what each verifies.

6. **Cross-platform was OUT-OF-SCOPE per Clarify decision** (resolved, not open). Implementation will remove README.md:72's unmet promise and the setup.md Dependencies table's brew-only ambiguity will be left as-is or annotated as macOS-only.

## Open Questions

These require user input during the Spec phase — they cannot be answered by reading code or web sources.

- **Pipeline diagram placement in `docs/agentic-layer.md` (OE-4)**: agentic-layer.md already has `### Diagram A — Main Workflow Flow` (Mermaid, L72-114) covering the requirements→discovery→backlog→lifecycle pipeline at a different fidelity. When the README ASCII pipeline diagram (currently L9-43) lands in agentic-layer.md, should it: (a) replace Mermaid Diagram A; (b) coexist as a "narrative" companion to the Mermaid "structural" Diagram A; or (c) get merged into a single consolidated diagram (likely Mermaid)? Deferred: will be resolved in Spec by asking the user.

- **`lifecycle.config.md` schema documentation depth (OE-3)**: only `test-command` is actively read by code; the other 5 keys (`type`, `skip-specify`, `skip-review`, `commit-artifacts`, `demo-commands`) are defined but never consumed. Should the schema doc in `docs/setup.md`: (a) document all 6 keys with a "currently advisory; future-reserved" caveat for the unread 5; (b) document only `test-command` and stub the rest as "reserved fields, see CHANGELOG"; or (c) document all 6 as fully active (risk: over-promising current behavior)? Deferred: will be resolved in Spec by asking the user.

- **README auth section disposition (OE-1)**: `README.md:110-140` and `docs/setup.md:82-132` overlap with setup.md being the more complete copy. Should README: (a) keep a 2-3 line pointer/teaser ("see [Authentication](docs/setup.md#authentication) for API Key, OAuth, and dual-mode setup"); (b) remove auth from README entirely (keep only in setup.md, no pointer in README body — auth would still be reachable via the docs index); or (c) keep a one-line mention only in the Quick Start verification step ("…then authenticate per [setup.md](docs/setup.md#authentication)"). Deferred: will be resolved in Spec by asking the user.

- **OE-5 verification surface boundaries**: pin exactly which verification command appears at: (i) the README Quick Start tail; (ii) the `docs/setup.md` install section tail (after plugin install); (iii) the `docs/setup.md` per-repo section tail (OE-3's worked example). Each surface verifies a different thing — but the audit suggested overlap. Spec must specify which surface owns which check (e.g., README = `cortex --version`, setup.md install = `claude /plugin list`, setup.md per-repo = first lifecycle invocation). Deferred: will be resolved in Spec by asking the user.

- **Plugin roster duplication tax (OE-1, surfaced by Tradeoffs agent)**: keep the plugin roster table in both README and setup.md (accept the two-file edit surface for future plugin changes), or pick one canonical home? Deferred: will be resolved in Spec by asking the user.
