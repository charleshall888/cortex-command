# Research Phase

Multi-dimensional investigation to build deep understanding of a topic.

## Protocol

### 1. Define Research Questions

Before investigating, articulate 3-7 specific questions this research needs to answer — the acceptance criteria; research isn't done until each has a confident answer or is explicitly marked unanswerable. Present them to the user for review and add any they raise.

### 1a. Load Requirements Context

Run `cortex-load-requirements` (omit `--feature`; discovery has no lifecycle index, so it falls back to project.md + Global Context) per the shared tag-based protocol (`load-requirements.md`). Read every listed non-skipped path into context and inject the printed path list downstream (relay any fallback note). Use requirements to identify where this topic intersects with established constraints. No `cortex/requirements/` directory or files → note this and skip.

### 1b. Read the Research-Sizing Assessment

Read the complexity/criticality assessment Clarify persisted (conversation memory does not survive a phase-resume):

```
cortex-discovery read-research-sizing --topic <topic>
```

When none was persisted — a legacy discovery directory, or Research entered before Clarify ran — this returns discovery's floor default `{"complexity":"simple","criticality":"medium"}` (criticality floors at `medium`, never `low`) and never errors. These two values size the fan-out below.

### 2. Size and Dispatch the Research Fan-Out

Gather findings via a sized wave of parallel, angle-specialized agents, then synthesize into discovery's own schema (§4), not /research's. The count matrix, mandatory-core set, always-last adversarial rule, and angle-selection rules are authoritative in the **fanout** sibling reference (`${CLAUDE_SKILL_DIR}/../research/references/fanout.md`, propagated from SKILL.md Step 3). Apply it; do not re-derive here.

**Size it.** Look up `agent_count` in the fanout.md count matrix using the `complexity` (tier row) and `criticality` (column) from §1b. The count is an upper bound on investigation breadth, not a quota — dispatch fewer if the topic offers fewer genuinely distinct angles than its cell allows.

**Choose the angles.** Discovery's natural investigation dimensions form the angle pool: **Domain & Prior Art** (comparable implementations, industry patterns, trade-offs, lessons learned) and **Feasibility** (technical risks, unknowns, prerequisites, rough S/M/L/XL effort) fill the remaining slots, plus any finer-grained angle the topic warrants.

**Dispatch it.** Follow fanout.md's two-wave protocol with the Agent tool — read-only research agents, no `isolation: "worktree"`, mirroring how `/cortex-core:research` Step 3 dispatches. Before the core wave, resolve the gather model in this orchestrator body (not inside any angle-prompt block):

```bash
model=$(cortex-resolve-model --role searcher)
```

Pass the captured `$model` as each core-wave Agent's `model:` parameter, per fanout.md's dispatch-protocol routing rule.

Each agent returns its findings for synthesis; no agent writes project files. Prerequisites entries describing codebase-state checks (e.g., 'Identify pattern X in {file}') belong to the Codebase angle — its findings carry citations, or are reported as `NOT_FOUND(query, scope)`. Entries remaining in §4's Feasibility Prerequisites column are implementation-sequencing only.

### 3. Synthesize the Findings

Compose the returned findings into discovery's own schema in §4 — do **not** adopt `/cortex-core:research`'s Codebase/Web/Tradeoffs/Adversarial schema. Discovery's `## Architecture` → `### Pieces` / `### How they connect` headings are machine-parsed downstream (the Research→Decompose gate and decompose.md's decomposition source of record), so synthesis must land in §4's structure exactly. Where agents contradict each other, surface the contradiction under `## Open Questions` rather than silently picking a side.

### 4. Write Research Artifact

Combine findings into `cortex/research/{topic}/research.md`:

```markdown
# Research: {topic}

## Research Questions
1. [Question] → **[Answer or "Unresolved: reason"]**
2. ...

## Codebase Analysis
- [Existing patterns]
- [Files/modules affected]
- [Integration points]
- [Constraints]

## Web & Documentation Research
<!-- Omit section if skipped -->
- [Best practices]
- [Library/API findings]
- [Pitfalls]

## Domain & Prior Art
<!-- Omit section if skipped -->
- [Similar implementations]
- [Industry patterns]
- [Lessons learned]

## Feasibility Assessment
| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| [A] | S/M/L/XL | [risks] | [prereqs] |

## Architecture

### Pieces
- [Piece name by role, not by mechanism — one bullet per piece]

### How they connect
[How the pieces connect and what each piece's boundaries depend on.]

## Decision Records
<!-- Key trade-offs and alternatives considered, one paragraph each -->

## Open Questions
- [Questions that need answers before spec or implementation]
```

### 4a. Orchestrator Review

<!-- `references/orchestrator-review.md` here intentionally targets discovery's OWN local delta file, NOT the propagated lifecycle canonical — the delta supplies discovery's Post-Research Checklist and fix-agent path/persona substitutions, and itself reads the lifecycle canonical via SKILL.md's propagation. -->
Before committing, read and follow `references/orchestrator-review.md` for the `research` phase. It must pass before §4b.

### 4b. Critical Review

Run `/cortex-core:critical-review` on `cortex/research/{topic}/research.md`. Address any significant challenges before proceeding.

### 5. Transition

Stage and commit `cortex/research/{topic}/` using `/cortex-core:commit`. Summarize key findings and proceed to the Research → Decompose approval gate (SKILL.md) — do not begin Decompose until the user answers it.

## Constraints

- **Read-only**: Do not modify project files except the research artifact
- **All findings in the artifact**: They won't survive in context alone
- **Scope**: Research the topic as described, not adjacent topics
- **Citations**: codebase-pointing claims carry an inline `[file:line]` citation traceable to codebase-agent findings, or an explicit `[premise-unverified: not-searched]` marker when not investigated.
- **Empty-corpus reporting**: a search returning no results is reported inline as `NOT_FOUND(query=<search-string>, scope=<path-or-glob>)` — distinct from `premise-unverified: not-searched` (no investigation attempted).
