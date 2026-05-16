# Research: cursor-skill-port

## Headline Finding

Cursor 2.4+ reads `SKILL.md` files natively (including from `.claude/skills/` for cross-tool compatibility) and Cursor 2.6 (May 2026) shipped a first-party Team Marketplaces system that imports plugins by GitHub repo URL — collapsing the port from "rewrite skills" to "reorganize a file tree, scrub a few frontmatter fields, synthesize a `.cursor-plugin/plugin.json` manifest." For the 13 in-scope cortex-core skills, **10 of 13 are A-zero-change or B-content-only** if hooks are deferred (4 A, 6 B); 3 are C-behavioral-degradation (`lifecycle`, `research`, `critical-review`) with documented degradation contracts. The headline 10-of-13 number depends on accepting that `commit` ports without its `PreToolUse:Bash` hook — the alternative (port the one hook) is a single schema rename and is presented as a v1-spec choice rather than a closed decision. Combined with the user's "Claude Code primary, Cursor second-class, low maintenance" constraint, the recommended posture is a thin **release-publish path** (canonical `plugins/cortex-core/skills/` here → near-identity converter → push to a separate Cursor-marketplace workspace on cortex-command release tags) with per-release cost bounded but non-zero (auto-refresh support tickets, Cursor-contract evolution review, degradation-comparison complaints).

## Research Questions

1. **What is Cursor's plugin packaging contract, and how does its tool surface compare to Claude Code's?** → **Answered.** Plugins are GitHub repos with `.cursor-plugin/plugin.json` (only `name` required) plus optional component dirs (`skills/`, `agents/`, `commands/`, `rules/`, `hooks/hooks.json`, `mcp.json`). Cursor reads SKILL.md natively from `.cursor/skills/`, `.agents/skills/`, **and `.claude/skills/` for compatibility**. Tool surface: Bash/Read/Edit/Write/WebFetch/WebSearch/Grep/Glob/MCP all equivalent; `Agent` ≈ Subagents in `.cursor/agents/` (dispatched by main agent via Task tool, not by skills); `AskUserQuestion` has **no equivalent** outside Plan mode; skill-to-skill mid-flow invocation is **not documented**. Hooks use a different schema (`hooks/hooks.json` with `version: 1`, camelCase events like `preToolUse`/`afterFileEdit`).

2. **For each of the 13 in-scope skills, what's the porting cost?** → **Answered.** 4 skills are A-zero-change (diagnose, requirements, requirements-gather, requirements-write); 6 are B-content-only (commit, pr, refine, discovery, backlog, dev) — **commit's B classification depends on accepting hook deferral (OQ7)**; 3 are C-behavioral-degradation (lifecycle, research, critical-review) with documented degradation contracts (DR-3). No skill is D-must-disable. See [Codebase Analysis](#codebase-analysis) for the per-skill table.

3. **What source-of-truth & publish path minimizes ongoing maintenance burden?** → **Answered, with per-release cost honestly characterized as bounded-but-non-zero.** Release-publish path. Canonical skills live in this repo at `plugins/cortex-core/skills/`; a converter writes a Cursor-plugin tree to an external workspace; a GitHub Action on release tag automates the push. Initial cost: ~100-line converter + plugin.json template + Action workflow. **Per-release cost is NOT zero**: budget ~1 hour per release for (a) auto-refresh support tickets when coworkers don't see the new version, (b) Cursor-contract conformance review (Cursor surface changed twice in ~12 months — 2.6 Team Marketplaces, 3.2 `/multitask`), (c) degradation-comparison complaints on the 3 C-skills. The hand-port pattern (Mindrally/skills) remains the canonical anti-pattern, but generator-monorepo is *bounded*, not *free*.

4. **Do `bin/cortex-*` scripts work in Cursor, and how do Cursor users acquire them?** → **Answered.** Scripts work — they're plain Python invoked via shell — but Cursor's plugin install flow has no documented `uv tool install`-equivalent bootstrap. Recommended: Cursor users `uv tool install git+https://github.com/charleshall888/cortex-command.git@<tag>` separately, exactly as Claude Code users do. The Cursor plugin documents this prerequisite in its README. **This prerequisite is an architectural piece, not just a doc concern** — see Architecture §3.

5. **For Claude-Code-only surfaces (AskUserQuestion, Agent dispatch, Skill-to-Skill, hooks), what should ported skills do when the surface is absent?** → **Answered, with explicit failure-handling contracts.** (a) AskUserQuestion → Cursor agent asks the same question as free text **with halt-on-ambiguity**: the skill prose instructs the agent to compare the user's free-text answer against each structured choice's label and accept only when exactly one matches (case-insensitive substring or exact); on zero matches OR multiple matches, the agent re-asks and does NOT proceed. Affects `backlog` (4 calls) and `lifecycle` (2 calls). (b) Agent parallel dispatch → Cursor's main agent fans out via Task tool to subagents declared in `.cursor/agents/` or via `/multitask`; skill prose must explicitly say "spawn N subagents in parallel" with a hardcoded N. **For `research`, N=3 (lower bound of the 3-5 Claude Code range — DR-3 acknowledges this collapses the upper half of the range and explicitly accepts the tradeoff)**. Affects `research` and `critical-review`. (c) `Skill` tool mid-flow invocation → user types the slash command themselves between phases; **the worst-case manual-intervention count for the `/cortex-core:dev` → lifecycle → refine → research → commit on-ramp is 4 manual slash transitions** — documented in onboarding. (d) Hooks → see DR-4 and OQ7 — v1 decision deferred to spec phase. (e) `lifecycle`'s `Agent(isolation: "worktree")` Implement-phase dispatch → degrades to Cursor's `/multitask` worktree handling (up to 8 parallel via git worktrees, model-decided) if the main agent picks it up; otherwise falls back to in-place implementation with an explicit warning in the skill prose. Documented in DR-3.

6. **Prior art — has anyone shipped a comparable port?** → **Answered.** Yes. `alirezarezvani/claude-skills` is the canonical reference for the generator-monorepo pattern (263 skills, 12 tools, ~15s rebuild). `sickn33/antigravity-awesome-skills` claims SKILL.md works unmodified across Claude Code, Cursor, Codex, Gemini, Antigravity. The `fieldsphere/cursor-team-marketplace-template` is the recommended skeleton for the external workspace. `Mindrally/skills` is the documented cautionary tale (hand-port, abandoned). Cursor's own `/migrate-to-skills` command translates Rules+Commands→SKILL.md but is not relevant here — we already have SKILL.md upstream.

## Codebase Analysis

### Per-skill portability table

Source: codebase audit subagent reading each `skills/<name>/SKILL.md` and its `references/`. Verified spot-checks: `AskUserQuestion` references confirmed via `grep -c "AskUserQuestion" skills/*/SKILL.md` (only `skills/backlog/SKILL.md:4 refs` and `skills/lifecycle/SKILL.md:2 refs` returned); Agent-dispatch references confirmed via `grep -lc "subagent_type\|Agent tool\|Task tool" skills/*/SKILL.md` (only `skills/critical-review/SKILL.md` and `skills/research/SKILL.md` returned).

| Skill | Claude-Code-only tools | `bin/cortex-*` shells | Hook deps | Sub-skill chain | Porting category |
|-------|----------------------|----------------------|-----------|-----------------|------------------|
| **commit** | — (Bash, Read are universal) | `cortex-commit-preflight`, `cortex-auto-bump-version` | `cortex-validate-commit.sh` (PreToolUse:Bash) `[plugins/cortex-core/hooks/hooks.json:3-12]` — **see OQ7 for v1 port-vs-defer decision** | — | **B: content-only** *(conditional on OQ7 outcome — if hook is ported, classification becomes B+hook-port; if deferred, classification is content-only with a documented commit-hygiene regression)* |
| **pr** | — | minimal | — | invokes `/cortex-core:commit` | **B: content-only** |
| **lifecycle** | `AskUserQuestion` (2 refs), `Agent` (worktree isolation — Implement phase) | `cortex-resolve-backlog-item`, `cortex-lifecycle-state`, `cortex-complexity-escalator`, `cortex-update-item` | `cortex-scan-lifecycle.sh` (audit reference) `[premise-unverified: not-searched]` | invokes `/cortex-core:refine` | **C: behavioral degradation** *(halt-on-ambiguity for AskUserQuestion; `/multitask`-or-in-place fallback for worktree isolation; manual slash-command for sub-skill chain)* |
| **refine** | — | `cortex-resolve-backlog-item`, `cortex-update-item`, `cortex-lifecycle-state` | — | invokes `/cortex-core:research`, `/cortex-core:commit` | **B: content-only** *(manual slash-command for sub-skill chain in Cursor)* |
| **discovery** | — | `cortex-discovery` (helper module) | — | invokes `/cortex-core:research` | **B: content-only** *(manual slash-command for sub-skill chain in Cursor)* |
| **research** | `Agent` (3-5 parallel dispatch) | `cortex-complexity-escalator` | — | dispatched parallel agents | **C: behavioral degradation** *(hardcoded N=3 in Cursor — DR-3 explicitly accepts the loss of 4-5-angle dispatch as the cost of port-and-degrade)* |
| **critical-review** | `Agent` (N reviewers + synthesizer) | `cortex-critical-review` | — | — | **C: behavioral degradation** *(N=reviewer-count hardcoded; synthesizer dispatch made explicit in prose)* |
| **backlog** | `AskUserQuestion` (4 refs) | `cortex-generate-backlog-index`, `cortex-backlog-ready`, `cortex-create-backlog-item`, `cortex-update-item` | — | invokes `/cortex-core:lifecycle` | **B: content-only** *(halt-on-ambiguity for AskUserQuestion; manual slash-command for sub-skill chain)* |
| **dev** | — | `cortex-generate-backlog-index`, `cortex-lifecycle-state`, `cortex-build-epic-map` | — | invokes `/cortex-core:lifecycle`, `/cortex-core:discovery`, `/pipeline`, `/overnight` | **B: content-only** *(manual slash-command for sub-skill chain — worst-case 4 manual transitions on the on-ramp)* |
| **diagnose** | — | minimal | — | — | **A: zero-change** |
| **requirements** | — | minimal | — | invokes `/requirements-gather`, `/requirements-write` | **A: zero-change** |
| **requirements-gather** | — | minimal | — | — | **A: zero-change** |
| **requirements-write** | — | minimal | — | — | **A: zero-change** |

### Dual-source mirror mechanics

`plugins/cortex-core/skills/` is auto-generated from canonical `skills/` via the dual-source enforcement system. Parity is enforced by `bin/cortex-check-parity` (referenced from `CLAUDE.md`) and a pre-commit hook installed via `just setup-githooks` (referenced from `CLAUDE.md`). The full parity-check entry point lives at `bin/cortex-check-parity` `[premise-unverified: not-searched for line-level detail]`. Adding a third sync target (external Cursor-plugin workspace) to this in-tree parity system would be heavyweight — the recommendation is to keep the cortex-command repo's two-way mirror as-is and treat the Cursor workspace as a **downstream consumer**, not a third parity-locked sibling.

### `bin/cortex-*` script invocation model

Skills invoke `cortex-*` scripts via the `Bash` tool (e.g. `cortex-resolve-backlog-item <slug>`), and the scripts shell out to the `cortex_command` Python package distributed via the `cortex-command` CLI wheel (installed via `uv tool install git+...@<tag>` per `CLAUDE.md` Distribution section). No script is invoked via direct file path — they all assume PATH resolution. Cursor users would need `uv tool install` of the cortex-command wheel as a documented prerequisite. **Version skew between the Cursor plugin's release tag and the user's installed cortex-command wheel is a load-bearing failure surface** — see Architecture §3.

### Hooks inventory (cortex-core)

`plugins/cortex-core/hooks/hooks.json` registers three hooks `[plugins/cortex-core/hooks/hooks.json:1-32]`:
- `PreToolUse` (matcher: `Bash`) → `cortex-validate-commit.sh` (validates `git commit -m` invocations)
- `WorktreeCreate` → `cortex-worktree-create.sh`
- `WorktreeRemove` → `cortex-worktree-remove.sh`

Only the commit-validation hook is referenced by an in-scope skill (`commit`); the worktree hooks support `lifecycle` worktree isolation but are not blocking — they fire when worktrees are created/removed, not as a precondition.

**Cost-of-port for the commit-validation hook is small**: one schema rewrite (`hooks.json` PascalCase `PreToolUse`/`matcher: "Bash"` → Cursor's camelCase `beforeShellExecution` with `version: 1`) plus a directory rename. The script (111-line pure bash reading `tool_name`/`tool_input.command`) has direct Cursor analogs in the `beforeShellExecution` payload. **Cursor's hook `loop_limit` default is 5 vs. Claude Code's `null`** — any port MUST explicitly set `loop_limit: null` or narrow the matcher to `git commit` only, otherwise the hook fires on every Bash call and silently disables mid-session before the commit it was meant to gate. This trap applies to any future v2 port too.

### `AskUserQuestion` usage

Confirmed via `grep -c`: `skills/backlog/SKILL.md` (4 refs) and `skills/lifecycle/SKILL.md` (2 refs). All other 11 in-scope skills: `NOT_FOUND(query="AskUserQuestion", scope="skills/*/SKILL.md")`.

### `Agent` / sub-agent dispatch usage

Confirmed via `grep -lc`: `skills/critical-review/SKILL.md` and `skills/research/SKILL.md` reference the Agent tool surface (subagent_type / Task tool dispatch). `skills/lifecycle/SKILL.md` references `isolation: "worktree"` (used during the Implement phase) — this is also Agent-tool semantics. All other in-scope skills: `NOT_FOUND(query="Agent tool|subagent_type|Task tool", scope="skills/*/SKILL.md")`.

### MCP server dependencies

`NOT_FOUND(query="mcp__", scope="skills/")` for all 13 in-scope skills. No MCP server bindings in the cortex-core skill pack. (The MCP control plane is exposed by `cortex-overnight`, which is out of scope.)

## Web & Documentation Research

### Cursor's plugin contract

- **Manifest**: `.cursor-plugin/plugin.json`, only `name` required. Optional: `description`, `version`, `author`, `homepage`, `repository`, `license`, `keywords`, `logo`, plus path overrides for components (`rules`, `agents`, `skills`, `commands`, `hooks`, `mcpServers`). Source: <https://cursor.com/docs/plugins/building>.
- **Multi-plugin repo**: `.cursor-plugin/marketplace.json` at repo root with `name`, `owner`, `plugins[]` (max 500). Source: <https://github.com/cursor/plugins>.
- **Skills**: SKILL.md with frontmatter `name` (kebab-case, required) + `description` (required), optional `paths`/`disable-model-invocation`/`metadata`. Loaded from `.cursor/skills/`, `.agents/skills/`, **and `.claude/skills/`, `.codex/skills/` for compatibility**. Source: <https://cursor.com/docs/skills>.
- **Slash commands** (separate from skills): files under `commands/` with `.md`/`.mdc`/`.markdown`/`.txt`; frontmatter `name` + `description`; body is a markdown prompt. Source: <https://cursor.com/docs/plugins/building>.

### Team Marketplaces (the user's distribution channel)

- Cursor 2.6 (May 2026) shipped Team Marketplaces for plugin distribution. Teams plan: 1 marketplace; Enterprise: unlimited.
- **Admin flow**: Dashboard → Settings → Plugins → Team Marketplaces → Import, paste a **GitHub repo URL**, parse plugins, set distribution group. Modes: **Required** (auto-installed for team members) and **Optional** (developer chooses). Source: <https://cursor.com/changelog/2-6>.
- **Updates**: webhook-driven dashboard refresh; community reports IDE-side sync is unreliable; **no version-pinning mechanism documented**. Source: <https://forum.cursor.com/t/cursor-2-6-team-marketplaces-for-plugins/153484>.
- **Private plugins are fine**: the "all plugins must be open source + manually reviewed" constraint applies only to the public marketplace, not team marketplaces.

### Tool surface gaps vs. Claude Code

| Claude Code | Cursor | Gap severity |
|-------------|--------|--------------|
| `Bash`, `Read`, `Edit`, `Write`, `Grep`, `Glob`, `WebFetch`, `WebSearch` | All equivalent | None |
| `Agent` (sub-agent dispatch, `isolation: "worktree"`) | Subagents in `.cursor/agents/` (also reads `.claude/agents/`), `/multitask` (up to 8 parallel via git worktrees), Task tool from main agent | Near-equivalent feature surface, but **skills cannot directly invoke subagents** — dispatch is main-agent-driven only. Fan-out reliability is model-instruction-driven and reportedly unreliable for N>3 without hardcoded counts. Source: <https://cursor.com/docs/subagents>, <https://forum.cursor.com/t/subagents-dont-maximize-parallel-dispatch/152679>. |
| `AskUserQuestion` (structured multi-choice prompts mid-flow) | Cursor 2.1 has clarifying-questions UI **inside Plan mode only**; no first-class equivalent for arbitrary skill flows. Community workaround: AUQ MCP server. Source: <https://www.digitalapplied.com/blog/cursor-2-1-clarifying-questions-plans>. | Real gap; degrade to free-text prompts **with halt-on-ambiguity** (DR-3). |
| `Skill` tool (mid-flow skill-to-skill invocation) | Manual `/skill-name` works; programmatic skill→skill chaining **not documented**. | Documented degradation: user types the next slash command themselves. **Worst-case manual-intervention count = 4** on the dev → lifecycle → refine → research → commit on-ramp. |
| MCP servers | First-class: `mcp.json` in plugin root, autodiscovered, or `mcpServers` override in plugin.json; v2.6 adds MCP Apps (UI widgets). | None (Cursor stronger in some ways). |
| Hooks | `hooks/hooks.json` with `version: 1`; camelCase events (`preToolUse`, `afterFileEdit`, `beforeShellExecution`, etc.); **`loop_limit` default `5` (Claude Code: `null`)** — any port must explicitly override or narrow matcher to avoid silent mid-session disable. Source: <https://cursor.com/docs/hooks>. | Schema rewrite for any ported hook (single file for the in-scope commit-validate case); v1 decision deferred to spec phase per OQ7. |

### Known pitfalls (from Cursor docs & community)

- **Frontmatter sensitivity**: colon in description silently drops the skill in some agents; multi-line wrapped description silently ignored by Claude Code; Claude-only fields (`model`, `disable-model-invocation`, `hooks`) are ignored or error elsewhere. Source: <https://github.com/anthropics/claude-code/issues/9817>. **Specifically dangerous for cortex-command**: concatenating `when_to_use` (which often contains commas and colons) into `description` is the *highest-risk vector* for colon-in-description silent drops — DR-5 addresses this.
- **Directory-name must match frontmatter `name`** in VS Code Copilot (silent skip); Cursor's behavior `[premise-unverified]` but likely follows VS Code. Source: <https://dev.to/moonrunnerkc/your-skillmd-works-in-claude-code-but-silently-fails-in-vs-code-k9b>.
- **`.cursor-plugin/` vs `.claude-plugin/`**: silent no-load trap when copy-pasting plugin scaffolds. Source: <https://medium.com/@v.tajzich/how-to-write-and-test-cursor-plugins-locally-the-part-the-docs-dont-tell-you-4eee705d7f76>.
- **Team-marketplace auto-refresh unreliable**: cache-clear + reinstall reportedly required after plugin updates. **This is a recurring per-release support tail** — budget ~1 hour per release for the "my plugin is on the old version" coworker tickets. Source: <https://forum.cursor.com/t/team-marketplace-auto-refresh-does-not-pick-up-plugin-changes-manual-refresh-cache-clear-reinstall-required/154675>.
- **External-repo plugin references in marketplace.json do not index** — keep all plugins in the same repo as marketplace.json.
- **No hot-reload**: full Cursor restart required to test plugin changes.
- **Cursor surface evolution rate**: 2 major plugin/agent-surface changes within ~12 months (2.6 Team Marketplaces in May 2026; 3.2 `/multitask` in April 2026). The converter must be reviewed against a pinned Cursor version on each release; conformance check should ideally compare emitted manifest fields against a golden current-Cursor-spec file.

## Domain & Prior Art

### Existing translators / generators

- **`alirezarezvani/claude-skills`** — 263+ skills, 12 tool targets; `./scripts/convert.sh --tool all` regenerates per-tool outputs in ~15s. Active 2026. Source: <https://github.com/alirezarezvani/claude-skills>. **Strongest reference implementation for the generator-monorepo pattern.**
- **`sickn33/antigravity-awesome-skills`** — 1,400+ skills, npm installer CLI; claims SKILL.md works unmodified across Claude Code, Cursor, Codex, Gemini, Antigravity. Source: <https://github.com/sickn33/antigravity-awesome-skills>.
- **`mxyhi/ok-skills`** — AGENTS.md + SKILL.md playbooks targeting the same multi-tool set. Source: <https://github.com/mxyhi/ok-skills>.
- **`Mindrally/skills`** — Cursor-rules→Claude-Code conversion, one commit, no automation. Cautionary tale of hand-port abandonment. Source: <https://github.com/Mindrally/skills>.
- **akm (Agent Knowledge Manager)** — index-in-place pattern, zero drift but no marketplace deliverable. Source: <https://dev.to/itlackey/stop-copying-skills-between-claude-code-cursor-and-codex-olb>.
- **`fieldsphere/cursor-team-marketplace-template`** — recommended skeleton for the external workspace; ships `scripts/validate-template.mjs` for pre-publish validation. Source: <https://github.com/fieldsphere/cursor-team-marketplace-template>.
- **Cursor's `create-plugin` plugin** — scaffolds manifest + handles pre-submission checks. Source: <https://cursor.com/en-US/marketplace/cursor/create-plugin>.

### Cross-IDE source-of-truth patterns

| Pattern | Initial cost | Per-change cost | Drift risk | Fit for cortex-command |
|---------|--------------|-----------------|------------|------------------------|
| Generator-script monorepo (alirezarezvani) | Low (~100 LOC converter) | **Bounded but non-zero** (~1hr/release for auto-refresh tickets + Cursor-surface conformance review + C-degradation comparison complaints) | Low (regenerated each time; subject to converter-bitrot if Cursor schema evolves silently) | **Recommended.** Best fit for low-maintenance constraint among realistic options. |
| `git subtree split/push` | Moderate | Per-tag subtree push (CI-able) | Low | Viable but mixes git semantics; converter is simpler. |
| Hand-port | Zero | Linear in change rate | High | **Anti-pattern.** Documented in Mindrally/skills. |
| Index-in-place (akm) | Minimal | Zero | Zero | Doesn't yield a marketplace plugin deliverable; rejected. |
| Lerna/Nx/Turborepo | High | Low | Low | Overkill for markdown-only payloads. |

### Cursor agent fan-out (relevant for `research` and `critical-review`)

- Cursor 2.4+ supports parallel subagent dispatch via Task tool from the main agent (not from inside skills directly). Up to 8 parallel via git worktrees.
- Cursor 3.2 added `/multitask` for async subagent fan-out with auto-decomposition.
- **Known issue**: subagent count is model-decided, not slot-maxing — users report only 3 launching when 4+ are requested. Workaround: hardcode count in prompt ("up to N in parallel").
- Sources: <https://cursor.com/docs/subagents>, <https://www.agentpatterns.ai/tools/cursor/multitask-subagents/>, <https://forum.cursor.com/t/subagents-dont-maximize-parallel-dispatch/152679>.

**Implication for the port**: `research` and `critical-review` skill prose must be edited to explicitly say "spawn N subagents in parallel" with a hardcoded N (3 for research, N=reviewer-count for critical-review) so Cursor's main agent doesn't under-parallelize. **DR-3 explicitly accepts the loss of the 4-5-angle option in research** as the cost of port-and-degrade — Cursor users get a fixed 3-angle research, Claude Code users keep the variable 3-5 range.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **(A) Release-publish path (converter + CI publish + external Cursor workspace)** (recommended) | **S–M** (~1-2 weeks initial; ~1 hr/release ongoing) | (1) Cursor frontmatter field divergence creates silent skips (DR-5 mitigation: conformance check against pinned Cursor version). (2) Team-marketplace auto-refresh unreliability → recurring "my coworkers don't see updates" support tickets. (3) The 3 C-degradation skills feel worse in Cursor than Claude Code — *and* these are the natural on-ramp surface (`backlog` → `lifecycle` → `refine` → `research`), so first-impression risk is concentrated, not peripheral. (4) Version-skew between Cursor plugin tag and user's installed cortex-command wheel breaks 9 of 13 skills silently (Architecture §3). | Decide canonical-vs-mirror source path for the converter; create the external repo; write `plugin.json` template; document `uv tool install` prerequisite; decide v1 hook-port policy (OQ7). |
| **(B) Hand-port (one-shot manual copy)** | **S** initial, **L+** lifetime | Drift within months (Mindrally pattern). Violates "low maintenance" constraint hard. | None — but creates maintenance debt. |
| **(C) Index-in-place (akm pattern)** | **S** | No marketplace deliverable. Doesn't meet stated requirement. | Ruled out. |
| **(D) Full parity (port hooks + AskUserQuestion shim + Agent surface)** | **L** (~4-6 weeks) | MCP shim for AskUserQuestion adds external runtime dependency. Hook event-name + schema rewrite (though small for the in-scope cases). Violates "Cursor is second-class" intent. | Explicit re-scope from user; not in this discovery's envelope. |

Approach A wins on all axes against the stated constraints.

## Architecture

### Pieces

1. **Release-publish path** — the converter logic plus the CI mechanism that delivers it. The converter (`bin/cortex-cursor-port` or `cortex_command/cursor_port.py` subcommand) reads `plugins/cortex-core/skills/<name>/` for the 13 in-scope skills, applies frontmatter scrubbing (keep `name`+`description`, strip Claude-only fields, **handle colon-in-description risk per DR-5**), applies prose neutralization (rewrite `AskUserQuestion`/`Agent`/`Skill`-tool/CLAUDE.md references into Cursor-equivalent language with hardcoded fan-out counts and halt-on-ambiguity rules per DR-3), enforces directory-name-equals-frontmatter-`name`, and emits a Cursor-plugin tree. The CI mechanism (`.github/workflows/publish-cursor.yml`) wraps the converter: on cortex-command release tag, it invokes the converter, commits/tags the external workspace, and reports status. **Failure-isolation contract**: a Cursor publish failure during a cortex-command release MUST NOT block the cortex-command release itself — the Cursor publish job is `continue-on-error: true`, surfaces as a workflow warning, and is retriable manually.

2. **External Cursor-plugin workspace** — separate GitHub repo (e.g. `cortex-cursor-skills`) under the user's GitHub org, structured per Cursor's plugin contract: `.cursor-plugin/plugin.json` (synthesized by converter), `.cursor-plugin/marketplace.json` (single-plugin), `skills/<name>/SKILL.md` (converter output), `README.md` (onboarding + degradation doc — content of this piece, not a separate piece), `LICENSE`, `CHANGELOG.md`. Imported by URL into the user's internal Cursor Team Marketplace. The README content covers: (a) install via internal marketplace; (b) `uv tool install` prerequisite (Piece 3); (c) explicit degradation list — which skills use free-text-with-halt-on-ambiguity instead of multi-choice (`backlog`, `lifecycle`); which use hardcoded N=3 fan-out (`research`); which require manual `/<skill>` typing with a worst-case 4 transitions on the dev on-ramp; the v1 commit-hook policy outcome (OQ7); the `/multitask`-or-in-place fallback for lifecycle worktree isolation; (d) "force-refresh" workaround for the team-marketplace auto-refresh bug.

3. **`cortex-command` CLI prerequisite** — the `uv tool install git+https://github.com/charleshall888/cortex-command.git@<tag>` step Cursor users must run before 9 of 13 skills work. This is *not optional documentation* — it is an architectural gate. Edges land on (a) cortex-command wheel hosted on GitHub releases (host availability), (b) **version skew between Cursor plugin tag and user's installed wheel** (the failure mode: a Cursor user on plugin-tag v0.5 with wheel-tag v0.4 sees Bash errors when skills invoke a `cortex-*` subcommand that doesn't exist yet on their wheel — or vice versa when v0.4 plugin calls a script the v0.5 wheel renamed), (c) user's shell PATH (resolution failure: `command not found`), (d) the user's onboarding journey (no enforcement surface in v1 — the only signal is failed Bash calls; see OQ8 for whether to ship a startup conformance check in v2).

### Integration shape

The pieces flow left-to-right: **canonical skill source (this repo) → Release-publish path (Piece 1) → External workspace (Piece 2) → internal Cursor marketplace (user-owned, out of band)**. Piece 3 (CLI prerequisite) is orthogonal: it sits in the user's local environment, separate from the publish flow, gating runtime behavior in Cursor sessions. The README inside Piece 2 is the contract surface to the human user — it documents Piece 3 as a prerequisite and the degradation behaviors of Piece 1's output.

Named contract surfaces between pieces:

- **Release-publish path ↔ canonical skill source**: read-only access to `plugins/cortex-core/skills/<name>/SKILL.md` and `references/`. Converter does NOT mutate canonical sources.
- **Release-publish path ↔ External workspace**: git push (HTTPS or SSH from GitHub Actions). Workspace's `main` branch is the canonical published state.
- **External workspace ↔ Cursor team marketplace**: GitHub repo URL → Cursor dashboard import. The marketplace polls the repo; no API call from this system.
- **CLI prerequisite ↔ External workspace**: the workspace's README is the documentation surface for the prerequisite; the workspace itself does NOT bundle the CLI.
- **CLI prerequisite ↔ user's Cursor session**: PATH resolution at runtime. The plugin's skills shell out to `cortex-*` scripts via Cursor's Bash; resolution failures surface as Bash errors with no plugin-level handling in v1.

### Seam-level edges

- **Release-publish path**: edges land on (a) `plugins/cortex-core/skills/` filesystem tree (read), (b) `cortex_command/` Python package if implemented as a subcommand, (c) external workspace directory (write via git), (d) GitHub Actions runner, (e) cortex-command release events (tag push trigger, e.g. `on: push: tags: ['v*']`), (f) Action notification surface (Slack/email on Cursor-publish failure — surfaced but non-blocking per failure-isolation contract).
- **External Cursor-plugin workspace**: edges land on (a) GitHub repo hosting (under user's org), (b) Cursor's `.cursor-plugin/plugin.json` + `marketplace.json` schemas (versioned by Cursor), (c) Cursor team-marketplace import flow (URL-based), (d) workspace's own git history (immutable releases), (e) the version-mismatch caveat (no Cursor version pinning) — newer Cursor versions may load the plugin differently.
- **`cortex-command` CLI prerequisite**: edges land on (a) cortex-command wheel hosted at `git+https://github.com/charleshall888/cortex-command.git@<tag>`, (b) the user's local Python env / `uv tool install` state, (c) the user's shell PATH at Cursor-session start, (d) **version-skew failure mode**: Cursor plugin tag and installed wheel tag are independent; mismatch causes silent Bash errors with no plugin-level diagnostic in v1.

(piece_count = 3; "Why N pieces" subsection skipped per template R3 — fires only when piece_count > 5. The honest decomposition omits the converter/publish split that earlier drafts presented separately, and folds the onboarding doc into Piece 2 where it lives as content.)

## Decision Records

### DR-1: Source-of-truth pattern → generator-script monorepo with bounded per-release cost

- **Context**: The user has hard-constraint "low maintenance burden, Cursor is second-class." Multiple SOT patterns are available.
- **Options considered**: (A) generator-monorepo, (B) git subtree split, (C) hand-port, (D) index-in-place, (E) Lerna/Nx.
- **Recommendation**: (A) generator-monorepo. Canonical `plugins/cortex-core/skills/` stays here; a converter emits a Cursor-plugin tree to a separate workspace; CI auto-publishes on release tags. **Per-release cost is bounded but non-zero**: ~1 hour per release for auto-refresh support tickets, Cursor-contract conformance review (Cursor surface changed twice within ~12 months), and degradation-comparison complaints.
- **Trade-offs**: Initial converter cost (~1 week) PLUS ongoing Cursor-contract evolution review (no fixed time budget — depends on Cursor's release cadence; expect quarterly review minimum given the 2.6/3.2 evolution rate). Adds a CI workflow to maintain (small but real). Forfeits the option of Cursor users contributing back via the Cursor workspace (PRs would need to be redirected upstream — accept as part of the second-class posture).

### DR-2: `bin/cortex-*` distribution → external `uv tool install`, no vendoring, no v1 enforcement

- **Context**: Cursor plugins have no documented Python-installer bootstrap. The 13 in-scope skills include 9 that shell out to `cortex-*` scripts.
- **Options considered**: (A) require `uv tool install git+https://github.com/charleshall888/cortex-command.git@<tag>` separately, (B) vendor a subset of bin scripts inside the Cursor plugin, (C) repackage cortex-command as a Cursor MCP server.
- **Recommendation**: (A). Cursor plugin README documents the prerequisite; coworkers run `uv tool install` once. Matches Claude Code's own install flow.
- **Trade-offs**: Users who skip the prereq see Bash errors with no plugin-level diagnostic in v1. **Version-skew between Cursor plugin tag and installed wheel is a real failure surface** (Architecture Piece 3, OQ8). Mitigation in v1: README + onboarding doc. v2 consideration: a `cortex-cursor-startup-check` skill that warns when the CLI is missing or version-skewed.

### DR-3: AskUserQuestion / Agent / Skill-tool degradation → port-and-degrade with explicit failure-handling contracts

- **Context**: 3 skills (`lifecycle`, `backlog`, `research`/`critical-review`) use Claude-Code-only tool surfaces (AskUserQuestion, parallel Agent dispatch, worktree isolation).
- **Options considered**: (A) port the skills with prose degradation + explicit contracts, (B) ship an MCP shim that re-implements AskUserQuestion semantics, (C) drop the affected skills from the Cursor plugin.
- **Recommendation**: (A) port-and-degrade with explicit contracts:
  - **AskUserQuestion → free-text with halt-on-ambiguity** (`backlog` 4 calls, `lifecycle` 2 calls): the skill prose instructs the Cursor agent to compare the user's free-text answer against each structured choice's label and accept only when exactly one matches (case-insensitive substring or exact). On zero matches OR multiple matches, the agent re-asks and does NOT proceed. No best-guess routing. This preserves the structural-gate intent that CLAUDE.md requires for sequential gates.
  - **Agent parallel dispatch → hardcoded N** (`research`: N=3, `critical-review`: N=reviewer-count): skill prose makes the count explicit so Cursor's main agent doesn't under-parallelize. For `research`, this explicitly **drops the 4-5-angle upper range** that Claude Code uses — the loss is accepted as the cost of port-and-degrade. The C-not-D classification stands because the skill still produces useful output at N=3; it just doesn't reach the upper bound.
  - **lifecycle worktree isolation** (`Agent(isolation: "worktree")` in Implement phase): degrades to Cursor's `/multitask` worktree handling if the main agent picks it up (up to 8 parallel via git worktrees, model-decided); otherwise falls back to in-place implementation with an explicit warning in the skill prose. Documented in onboarding.
  - **`Skill` tool mid-flow invocation → manual slash-command**: user types the next command between phases. **Worst-case manual-intervention count is 4** on the `/cortex-core:dev` → `/cortex-core:lifecycle` → `/cortex-core:refine` → `/cortex-core:research` → `/cortex-core:commit` on-ramp. Documented in onboarding.
- **Trade-offs**: Cursor users get a worse UX on these 3 skills compared to Claude Code, and the degraded surface is concentrated on the natural on-ramp (`backlog` → `lifecycle` → `refine` → `research`), so first-impression risk is real, not peripheral. The halt-on-ambiguity rule mitigates silent-mis-routing risk on AskUserQuestion gates. The N=3 hardcoding is a real capability reduction for `research`. Cursor coworkers will encounter the manual-slash-command degradation often on multi-phase flows — onboarding doc must call this out prominently.

### DR-4: Hooks → v1 port-vs-defer decision deferred to spec phase (OQ7); loop_limit trap recorded for any port

- **Context**: `plugins/cortex-core/hooks/hooks.json` registers commit-validation (PreToolUse:Bash → `cortex-validate-commit.sh`) and worktree-create/remove hooks. The commit skill is the only in-scope skill that *depends* on its hook for behavioral correctness. The hook port is small (one schema-renamed file), but adds engineering scope to v1.
- **Options considered**: (A) port the commit-validate hook in v1 — schema rewrite (PreToolUse → beforeShellExecution), explicit `loop_limit: null` override or matcher narrowing, ships inside Cursor plugin; (B) defer in v1 with honest gap acceptance — Cursor users get the commit skill's prose guidance only, and the commit-hygiene regression is documented in onboarding with the understanding that the user reviews their coworkers' commits manually; (C) defer hook port but add a CI commit-format check to this repo so bad-format commits actually get caught somewhere downstream.
- **Recommendation**: **Deferred to spec phase.** This research artifact presents the corrected cost analysis (port is one file; no PR-review safety net exists in current CI) and elevates the v1 choice to OQ7. The decompose phase emits tickets for both port-in-v1 and defer-with-gap-acceptance; the user picks at refine/spec time.
- **Trade-offs (port-in-v1 / option A)**: Small additional engineering scope in v1 (~half-day for schema rewrite + loop_limit testing). Preserves the only structural commit-validation gate Cursor users would otherwise lose. Avoids the "10 of 13 are clean" headline depending on accepting a regression.
- **Trade-offs (defer / option B)**: Cursor coworkers can commit with bad-format messages; the user catches them in code review manually. Acceptable if the Cursor coworker count stays small and commit volume from Cursor is low. Worsens with adoption.
- **Trade-offs (CI gate / option C)**: Adds a project-wide enforcement that benefits Claude Code AND Cursor users; more engineering scope but solves the gap for both surfaces.
- **`loop_limit` trap** (applies to any port): the existing hook is registered on `PreToolUse:Bash` and exits 0 for non-`git commit` Bash calls. Mapped to Cursor's `beforeShellExecution`, the same pattern fires on every Bash invocation. At Cursor's `loop_limit: 5` default, a normal session triggers the hook six times and silently disables it for the rest of the session — including the commit it was meant to gate. Any port MUST explicitly set `loop_limit: null` OR narrow the matcher to git-commit-only.

### DR-5: Frontmatter scrubbing → minimum-viable (name+description only), with explicit colon-handling + Cursor-version-pinned conformance

- **Context**: Cursor SKILL.md frontmatter schema accepts `name`, `description`, optional `paths`/`disable-model-invocation`/`metadata`. Claude Code skills carry additional fields (`when_to_use`, `model`, etc.). Colons in `description` silently drop the skill in some agents. Concatenating `when_to_use` into `description` is the highest-risk vector for colons.
- **Options considered**: (A) strip all non-Cursor-schema fields, keep `name`+`description`, concatenate `when_to_use` into `description` with colon-handling, (B) preserve Claude Code fields as `metadata.claude_*` for round-tripping, (C) preserve as-is and let Cursor silently ignore.
- **Recommendation**: (A) with explicit colon-handling and a conformance check:
  - **Colon handling**: the converter MUST strip or escape colons in the concatenated `description` value. Implementation choice (strip vs. replace with hyphen vs. quote the YAML value with `"..."`) is for the spec phase; the requirement is that no resulting `description` contains a bare colon outside YAML-string-quoting.
  - **Schema-conformance check**: the converter SHOULD compare emitted manifest fields against a Cursor-version-pinned golden spec file checked into this repo (e.g. `tests/golden/cursor-plugin-manifest-v2-6.json`). Updated on each Cursor-contract review. **This is a v2 follow-up, not a v1 requirement** — but it's the durable fix for silent-skip drift as Cursor's schema evolves. Recorded in OQ as a follow-up consideration.
- **Trade-offs**: Cursor plugin loses the structured `when_to_use:` field for downstream tooling (acceptable — existing convention already concatenates). Colon-handling adds a small amount of converter complexity. Schema-conformance check is real engineering scope deferred to v2.

## Open Questions

These genuinely depend on user decisions or external state and could not be resolved through investigation:

1. **External Cursor workspace name and hosting location** — under the user's personal GitHub org or the company's? Naming convention (e.g. `cortex-cursor-skills`, `cortex-skills-cursor`, `cortex-command-cursor`)? *Decompose ticket needs this to scope the workspace bootstrap.*

2. **Should the Cursor plugin's frontmatter `description` strings be edited for tone/voice neutrality** (e.g. removing references to "Claude Code" in skill descriptions), or kept verbatim with the assumption that Cursor coworkers will read past it? *Affects converter's prose-neutralization scope.*

3. **What internal Cursor marketplace constraints exist** (manifest schema validation, auth, telemetry, naming conflicts with first-party plugins) at the user's company? Could not investigate — this is internal infrastructure. *Surface to user before publish-pipeline implementation; may add prerequisites.*

4. **Versioning policy** — should the Cursor plugin's version track cortex-command's semver tag exactly, or have an independent version stream (in case the Cursor plugin needs hotfix releases independent of cortex-command)? *Affects DR-1's CI workflow design and the version-skew failure mode (Piece 3, OQ8).*

5. **Should the converter run as a `cortex_command/cursor_port.py` subcommand (`cortex-cursor-port`) or as a standalone `bin/cortex-*` script?** Both are viable; the subcommand approach inherits parity-check coverage, but the standalone script keeps the converter loosely coupled from the rest of the CLI surface. *Affects DR-1's scope of code under parity.*

6. **Compatibility with Cursor's `.claude/skills/` loader** — could the Cursor plugin simply re-export under `skills/` and trust Cursor's compatibility loader to read it, or must the Cursor plugin use `.cursor/skills/`? Source ambiguous: docs say Cursor reads both, but plugin manifest spec lists `skills` (no prefix). `[premise-unverified]` whether the compatibility loader applies inside a plugin manifest or only inside repos. *Convert to `.cursor/skills/` path to be safe; revisit if Cursor docs clarify.*

7. **v1 commit-validate hook policy** — port to Cursor's `hooks/hooks.json` schema in v1, defer with honest gap acceptance, or add a project-wide CI commit-format check that benefits both harnesses? Cost analysis (DR-4): porting is one schema-renamed file; PR-review fallback doesn't exist. **The decompose phase should emit alternative tickets for each option; the user picks at refine/spec time.** Any port MUST handle the `loop_limit: 5` trap (set `null` or narrow matcher).

8. **v2 follow-up: cortex-command CLI prerequisite enforcement surface** — should v2 ship a `cortex-cursor-startup-check` skill or hook that warns when the CLI is missing/version-skewed, or stay with v1's documentation-only approach? Architecture Piece 3 leaves no enforcement in v1; the version-skew failure mode is real but currently bounded to early-adopter pain. *Decide based on adoption volume after v1 ships.*

9. **v2 follow-up: Cursor-schema conformance check** — should the converter compare emitted manifest fields against a Cursor-version-pinned golden file (e.g. `tests/golden/cursor-plugin-manifest-v2-6.json`) to detect silent-skip drift when Cursor evolves its schema? DR-5 calls this the durable fix for the schema-evolution problem but doesn't require it in v1. *Decide based on Cursor's release cadence after v1 ships.*
