# Research: requirements-audit

## Research Questions

1. Does `requirements/project.md` accurately reflect the current system? → **Partially. Four specific inaccuracies; dashboard and several pipeline subsystems entirely absent.**
2. What area-level requirements should exist but don't? → **Four areas clearly missing: observability, remote-access, multi-agent, pipeline.**
3. What's missing or weak in the current `/requirements` skill workflow? → **No maintenance output in lifecycle review, no drift artifact, no parent-doc format enforcement, sub-file path bug.**
4. How do other AI-assisted dev frameworks structure living requirements docs? → **Consistently: minimal index at root + linked area sub-docs loaded on demand. The llms.txt pattern and AGENTS.md hierarchy both converge on this.**
5. What are best practices for machine-consumed requirements docs? → **Root doc ≤50 lines; explicit "when to load" guidance per area; file:line refs over inline code; declarative outcomes not implementation steps; no code style.**
6. What would a durable requirements management process look like? → **Bidirectional flow: implementation writes back to spec after each lifecycle phase as a required output, not an advisory prompt. Eight antipatterns to avoid. Clear re-gather triggers.**
7. What parent doc structure best serves both human review and agent consumption? → **Project overview (5 lines) + cross-cutting invariants + area index with descriptions + "when to load" guidance. ~30–50 lines total. Primary value is navigation and maintenance, not token savings (no native conditional loading in Claude Code).**

---

## Codebase Analysis

### Accuracy audit of `requirements/project.md`

**Confirmed accurate:**
- Overview description (agentic workflow toolkit, north-star of autonomous multi-hour development)
- Day/Night/Morning work split philosophy
- File-based state architectural constraint
- Graceful partial failure quality attribute
- Core scope: lifecycle, overnight, skills, backlog, discovery are all present and working

**Specific inaccuracies (must fix):**
- "Cursor, Gemini, Copilot get best-effort" — **stale**. A git commit explicitly removed Cursor and Gemini support to focus exclusively on Claude Code. This claim contradicts the current codebase.
- "remote/SETUP.md" — **broken reference**. `docs/setup.md` tells users to read `remote/SETUP.md` but that file does not exist in the repo.
- "Multi-agent support" described only as "Claude Code is primary, others get best-effort" — **understates**. The actual multi-agent implementation includes worktree isolation, parallel dispatch with a 3-dimensional model selection matrix (complexity × criticality × phase), and a PR review skill using 4 parallel agents + synthesis.

**Major omissions (feature areas that exist but aren't mentioned):**
- **Dashboard** (~1800 LOC, FastAPI, 9 HTML templates, 7 test modules): real-time web monitoring of overnight sessions with session panels, fleet overview, pipeline status, alerts banner. Not in requirements at all.
- **Conflict resolution & merge recovery pipeline** (~2500 LOC, `pipeline/conflict.py`, `merge_recovery.py`): classifies conflicts, dispatches repair agents, retries merges. Critical for overnight reliability but silent in requirements.
- **Deferral system** (`overnight/deferral.py`): enables features that hit unknown questions during overnight execution to park those questions and continue. Fundamental to "graceful partial failure" but not documented.
- **Model selection tier system** (`pipeline/dispatch.py`, 583 LOC): full escalation matrix (Haiku → Sonnet → Opus) with budget controls per tier. Core to how agent quality/cost is managed.
- **Metrics & cost tracking** (`pipeline/metrics.py`, `overnight/report.py`): timing, token usage, cost data, `metrics.json` generation for morning review.
- **Hook system** (7+ hooks in `claude/hooks/`): permission auditing, GPG sandbox setup, tool failure tracking, skill-edit advising. Non-trivial infrastructure.

Note: these omissions accumulated before `requirements/project.md` existed (first gathered 2026-04-01). They are a bootstrapping gap, not a failure of an existing process.

### Area docs that should exist but don't

| Area | Why it warrants its own doc |
|---|---|
| `requirements/observability.md` | Statusline, 3 notification channels (macOS/Android/Windows), dashboard system — substantial and independently navigable |
| `requirements/remote-access.md` | tmux skill, ntfy.sh integration, Tailscale/mosh setup — has an explicit broken reference from setup.md; clearly expected to exist |
| `requirements/multi-agent.md` | Agent spawning, worktree isolation, parallel dispatch constraints, model escalation matrix — 40+ LOC of orchestration code |
| `requirements/pipeline.md` | Overnight runner, conflict resolution, deferral, metrics, model selection — the most complex subsystem; docs/pipeline.md exists but isn't structured as requirements |

### Current skill defects

**Skill path bug (current production defect):** `skills/requirements/SKILL.md` references sub-files with relative links (e.g., `[references/gather.md](references/gather.md)`). When the skill is invoked from any repo other than cortex-command, Claude resolves these as `~/.claude/skills/requirements/references/gather.md`, which is outside the CWD and triggers sandbox permission prompts. Fix: replace relative links with repo-relative absolute paths (e.g., `skills/requirements/references/gather.md`). This affects all skills with sub-files, not just `/requirements`.

**Process gaps in current skill workflow:**
- **No drift output**: The skill has no opinion on *when* to re-run after initial gathering. There is no hook, lifecycle integration, or convention that prompts re-gathering when implementation drifts.
- **No required write-back**: Lifecycle review doesn't require a requirements update as part of its output. Drift can go unnoticed even when agents complete the review phase.
- **No parent-doc format enforcement**: `gather.md` has an artifact format template, but nothing prevents the parent doc from growing into a sprawling single file over time.
- **No "when to load" guidance in artifacts**: Area sub-docs (when they exist) have a "Parent: project.md" link but no specification of when a downstream skill should load them.

---

## Web & Documentation Research

### Progressive disclosure patterns

The **llms.txt standard** is the clearest convergence point: a root index file contains curated links organized by category; an agent reads the index first and fetches sub-docs only when relevant. Sites report 90%+ token savings vs. serving full content at the root. The structural principle applies directly to requirements: a parent doc that describes areas and where to find them, not a parent doc that contains everything.

**AGENTS.md hierarchy** (used in 60,000+ projects, 20+ AI coding agents): root AGENTS.md combines with sub-directory AGENTS.md files. Inner files override outer files on conflicts. The main OpenAI repo uses 88 AGENTS.md files — one per package/area. OpenAI Codex enforces a 32 KiB cap on combined context, making the single-file approach a hard ceiling for any serious project.

**Median effective AGENTS.md** (study of 60,000+ repos): 335 words, one H1, 6–7 H2 sections, 9 H3 sub-sections. Shallow consistent hierarchy outperforms both flat lists and deep nesting.

### Machine-readable requirements

From Addy Osmani, HumanLayer, and Augment Code research:

- **Root doc ≤50 lines** — Anthropic's system prompt uses ~50 of a ~150–200 instruction budget; a 150-line requirements doc competes with itself for attention ("curse of instructions")
- **Lead with executable information** — agents need exact file paths and verifiable criteria; narrative prose should be minimal
- **Three-tier boundaries** work reliably: explicit Always / Ask / Never (or Must / Should / Never) categories are picked up by models more reliably than prose descriptions
- **file:line references over inline code blocks** — code blocks go stale; file references stay fresh
- **Declare outcomes, not steps** — exhaustive acceptance criteria actually reduce agent effectiveness; orient the agent, don't script it
- **"When to load" guidance** — Cursor's glob-scoped rules and Copilot's `applyTo` frontmatter both implement the same insight: area context should only be injected when relevant. Claude Code has no native conditional loading mechanism; prose guidance in the parent index is advisory, not enforced. The restructure's value is navigation and maintenance reduction, not guaranteed token savings.

### Living requirements / drift

Augment Code's **bidirectional flow model** is the key pattern:
1. Developer writes intent → AI expands into structured spec
2. Agents read spec → generate code
3. Implementation updates spec to reflect what was actually built ← **this step is the gap**
4. Production incidents/retros feed back into spec

Step 3 is the missing piece. The lifecycle review phase is the natural integration point, but it must produce a requirements update as a *required output*, not an advisory question. Asking "did anything drift?" is insufficient — the review phase must either update requirements or explicitly log "no drift detected."

**Eight antipatterns to avoid** (from Augment Code):
1. Under-specification (agents fill gaps with assumptions)
2. Over-specification (agents ignore or follow too literally)
3. Mixed concerns (functional requirements + technical mandates in same doc)
4. Lost continuity (agents repeat corrected mistakes)
5. Vague success criteria
6. Solution-jumping (describing implementation instead of outcomes)
7. Environmental blindness (ignoring runtime/deployment context)
8. Token-insensitive specs (unfocused context degrades agent performance)

**Maintenance triggers** (consensus across sources):
- After each lifecycle review phase (required, not optional)
- When an agent surfaces an ambiguity not covered by the spec
- When a retro identifies an unmet assumption
- When data models or core architectural decisions change
- When scope changes after discovery research

---

## Domain & Prior Art

### Tiered loading in AI coding assistants

| Tool | Always-on | Conditional / scoped |
|---|---|---|
| Cursor | `alwaysApply: true` rules | Glob-scoped rules; `alwaysApply: false` (agent decides) |
| GitHub Copilot | `.github/copilot-instructions.md` | `.github/instructions/*.instructions.md` with `applyTo` globs |
| AGENTS.md | Root file | Sub-directory files; `@reference` syntax for explicit includes |
| Claude Code | CLAUDE.md (always loaded) | No native conditional loading — uses explicit Read calls |

**Key pattern**: every mature system separates stable/universal context (always-on) from dynamic/area-specific context (conditional). Claude Code's CLAUDE.md + requirements/ mirrors this split — CLAUDE.md is always-on, requirements/ is on-demand. The gap is that on-demand loading has no enforcement mechanism: nothing compels an agent to load `requirements/observability.md` vs. `requirements/pipeline.md`. Prose triggers in the parent index help orient agents but do not guarantee loading.

### How competing systems handle requirements drift

- **Cursor**: `.mdc` files version-controlled alongside code; drift is surfaced by diffs
- **Copilot**: instructions files in `.github/`; no built-in drift detection
- **AGENTS.md**: no built-in drift detection; relies on team discipline
- **Augment Code's model**: explicit post-implementation spec update as a required workflow step

No reviewed tool has automated drift detection — it's universally a workflow/discipline problem, not a tooling problem. The practical answer is: make re-gathering cheap and *required*, and wire it to natural lifecycle checkpoints as an output step, not an advisory prompt.

---

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|---|---|---|---|
| **A: Minimal content fix** — update project.md inaccuracies, create 4 area docs, fix broken reference, fix skill path bug | S | Low. Content and path changes only. Does not add a maintenance mechanism. | None. |
| **B: Restructure + skill update** — redesign parent doc as 30–50 line index, create area sub-docs with "when to load" guidance, update skill to enforce new format, make lifecycle review require a drift output (update or explicit "no drift" note), fix skill path bug | M | Medium. Downstream skills (lifecycle, discovery) reference requirements/ — need to verify they still load correctly. Prose loading guidance is advisory; agents may still load speculatively or skip area docs. | None beyond this repo. |
| **C: Tiered/glob-scoped loading** — add YAML frontmatter to each requirements doc with `alwaysApply` / `globs` metadata, update consuming skills to respect it | L | High. Requires every consuming skill to parse frontmatter and implement conditional loading. No native Claude Code mechanism for this — would need to build it. | Agreement on loading mechanism; updates to lifecycle, discovery, pipeline. |

**Recommendation: Approach B**, with clear-eyed expectations. The primary gains are: (1) a parent doc that stays navigable as the project grows, (2) area sub-docs that give lifecycle/discovery better-scoped context, (3) a required drift check in lifecycle review that produces a written output. The token-savings framing is secondary and not guaranteed without native conditional loading. Approach A fixes content but leaves no mechanism to prevent re-drift. Approach C over-engineers a mechanism that prose guidance approximates well enough for a personal project.

---

## Decision Records

### DR-1: Parent doc format — index vs. full content

- **Context**: Current `project.md` is 107 lines and growing. As area sub-docs are added, should the parent doc shrink to an index or remain the primary content document?
- **Options considered**: (1) Flat single file containing all project-level content; (2) Thin index pointing to area sub-docs; (3) Hybrid: project-level invariants + index
- **Recommendation**: Hybrid (option 3). The parent doc retains project-wide content that is always relevant (overview, philosophy, cross-cutting constraints, scope boundaries) but becomes authoritative only at the project level. Area-specific detail moves to sub-docs. Target: 50–70 lines.
- **Trade-offs**: Adds maintenance burden (two places to update); mitigated by clear ownership rules (project.md owns only cross-cutting concerns).

### DR-2: "When to load" triggers convention

- **Context**: No current mechanism tells agents when to load area requirements vs. project requirements. Claude Code has no native conditional loading — agents use explicit Read calls. Prose guidance in the parent index is advisory only.
- **Options considered**: (1) Glob-scoped frontmatter (Cursor-style); (2) Explicit prose triggers in the parent doc index; (3) No triggers — rely on agent judgment
- **Recommendation**: Prose triggers in the parent doc index (option 2) as the first step. The restructure's value is navigation and maintenance overhead reduction; token savings are a secondary benefit that only materializes when agents actually follow the guidance. Example trigger: "When working on notifications or the dashboard, read requirements/observability.md." Glob-scoped frontmatter can be added later if prose proves insufficient in practice.
- **Trade-offs**: Prose triggers require agents to parse intent and choose correctly; they don't enforce loading. Acceptable given this is a single-developer personal project where agent behavior can be observed and corrected.

### DR-3: Maintenance cadence and write-back mechanism

- **Context**: The core drift problem is that requirements updates are never in the critical path. Lifecycle review phases complete without requiring a requirements update as an output. Adding an advisory prompt ("did anything drift?") to the review phase repeats the same soft enforcement that already allowed ~4,300 LOC of dashboard and pipeline code to go undocumented. Note: those omissions accumulated before `project.md` existed — this is a bootstrapping gap, not a repeat failure. But preventing future drift requires a harder mechanism than a prompt.
- **Options considered**: (1) Advisory prompt in lifecycle review; (2) Required output: lifecycle review must produce either a requirements update or an explicit "no drift detected" statement in the review artifact; (3) Scheduled periodic re-gather
- **Recommendation**: Required output (option 2). Lifecycle review produces a `requirements_drift` field in its review artifact: either "none detected" or a list of changes with a pointer to the updated requirements file. This makes requirements accuracy a stated deliverable of each lifecycle cycle, not an afterthought. Scheduled re-gather (option 3) is too mechanical for a fast-moving personal project.
- **Trade-offs**: Adds a step to lifecycle review; small overhead. The key difference from option 1 is that option 2 makes absence of an update an explicit decision ("no drift"), not an implicit omission.

---

## Open Questions

- Should `requirements/pipeline.md` be created fresh (area requirements format) or derived from `docs/pipeline.md` (which is implementation-oriented)? The two have different intents — docs/pipeline.md describes how it works; requirements/pipeline.md should say what it must do. May need both to coexist. This is a scope and ownership decision for the user.
- How should overnight handle the case where lifecycle review identifies requirements drift but no human is present? The review phase runs autonomously. Should it write a "requirements drift detected" note to the morning report rather than stalling for a re-gather?
