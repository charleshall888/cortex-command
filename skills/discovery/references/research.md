# Research Phase

Multi-dimensional investigation to build deep understanding of a topic. Read-only — no code changes, no decisions yet.

## Contents

1. [Define Research Questions](#1-define-research-questions)
2. [Size and Dispatch the Research Fan-Out](#2-size-and-dispatch-the-research-fan-out)
3. [Synthesize the Findings](#3-synthesize-the-findings)
4. [Write Research Artifact](#4-write-research-artifact)
4a. [Orchestrator Review](#4a-orchestrator-review)
4b. [Critical Review](#4b-critical-review)
5. [Transition](#5-transition)

## Protocol

### 1. Define Research Questions

Before investigating, articulate 3-7 specific questions this research needs to answer. These become the acceptance criteria — research isn't done until each question has a confident answer or is explicitly marked as unanswerable.

Present questions to the user for review. Add any questions they raise.

### 1a. Load Requirements Context

Load requirements using the shared tag-based loading protocol (`load-requirements.md`): run `cortex-load-requirements` (discovery has no lifecycle index, so omit `--feature` — the verb falls back to project.md + Global Context), read every listed non-skipped path into context, and inject the printed path list downstream (relay any fallback note). Use requirements to inform research — identify where this topic intersects with established requirements and constraints. If no `cortex/requirements/` directory or files exist, note this and skip this step.

If a concept you need is not yet defined in the glossary, treat the absence as a signal to surface the term in the next requirements interview.

### 1b. Read the Research-Sizing Assessment

Research can be entered independently of Clarify (a fresh `/cortex-core:discovery research <topic>` session), so read the complexity/criticality assessment back from the topic's events.log rather than relying on conversation memory:

```
cortex-discovery read-research-sizing --topic <topic>
```

This returns the assessment Clarify persisted (`complexity` + `criticality`). When none was persisted — a legacy discovery directory, or Research entered before Clarify ran — it returns discovery's floor default `{"complexity":"simple","criticality":"medium"}` (criticality floors at `medium`, never `low`, per discovery's upward bias) and never errors. These two values size the research fan-out for the steps below.

### 2. Size and Dispatch the Research Fan-Out

Discovery's research gathers its findings the same way `/cortex-core:research` does — a sized wave of parallel, angle-specialized agents — but synthesizes them into discovery's own artifact schema (§4), not /research's. The sizing and dispatch engine is shared so the two entry points cannot drift: the authority for the count matrix, the mandatory-core set, the always-last adversarial rule, and the hybrid angle-selection rules is the **fanout** sibling reference at the absolute path the discovery body resolved and propagated (the `${CLAUDE_SKILL_DIR}/../research/references/fanout.md` target established in discovery SKILL.md Step 3). Apply that file; do not re-derive the matrix or the selection rule here.

**Size it.** Look up `agent_count` in the fanout.md count matrix using the `complexity` (tier row) and `criticality` (column) returned by the §1b read-back. The count is an upper bound on investigation breadth, not a quota — dispatch fewer if the topic offers fewer genuinely distinct angles than its cell allows.

**Choose the angles.** Discovery's natural investigation dimensions form the angle pool. The mandatory core — always present at every cell — maps onto discovery's dimensions as:

- **Codebase** — existing patterns and conventions, files/modules/boundaries affected, dependencies and integration points, technical constraints.
- **Web & Documentation** — current best practices, library/API documentation for external dependencies, known pitfalls and failure modes, verification that needed capabilities exist and aren't deprecated.
- **Requirements & Constraints** — the project/area requirements (loaded in §1a) and scope boundaries that bound this topic.

Fill the remaining slots the matrix buys with discovery's other distinct dimensions — **Domain & Prior Art** (competing/analogous implementations, industry patterns, trade-offs others hit, lessons that apply) and **Feasibility** (technical risks, unknowns that could derail, prerequisites, rough S/M/L/XL effort) — plus any finer-grained angle the topic warrants. Choose them by reasoning about the topic, keep each distinct and non-redundant, and subdivide an existing angle by scope only once genuinely distinct angles are exhausted (note that subdivision in §4's Open Questions when it happens). There is no topic→angle keyword router — angle choice beyond the core is your judgment in context.

**Dispatch it.** Follow fanout.md's two-wave protocol with the Agent tool — read-only research agents, no `isolation: "worktree"`, mirroring how `/cortex-core:research` Step 3 dispatches:

1. **Core wave (parallel).** Dispatch the mandatory core plus the chosen angles for the cell — every angle except the always-last adversarial one — as one batch of Agent calls in a single response.
2. **Adversarial wave (last).** For `high`/`critical` criticality, once the core wave returns, summarize its findings briefly and dispatch a final adversarial/critique agent over that summary: it actively hunts for failure modes, unexamined assumptions, and why the obvious decomposition breaks, rather than validating what the others found. At low/medium criticality the core wave is the whole dispatch and there is no second wave (the orchestrator may still add adversarial if the cell's budget allows and the topic warrants).

Each agent returns its findings for synthesis; do not let any agent write project files. Prerequisites entries describing codebase-state checks (e.g., 'Identify pattern X in {file}') belong to the Codebase angle — its findings carry citations, or are reported as `NOT_FOUND(query, scope)`. Entries remaining in §4's Feasibility Prerequisites column are implementation-sequencing only (work to be done after the approach is committed).

### 3. Synthesize the Findings

The fan-out changes how findings are gathered (parallel, angle-specialized), not the shape of the artifact. Compose the returned findings into discovery's own schema in §4 — do **not** adopt `/cortex-core:research`'s Codebase/Web/Tradeoffs/Adversarial artifact schema. Discovery's `## Architecture` → `### Pieces` / `### How they connect` headings are machine-parsed downstream (the Research→Decompose gate and `decompose.md`'s "decomposition source of record"), so the synthesis must land in §4's structure exactly. Where agents contradict each other, surface the contradiction under `## Open Questions` rather than silently picking a side.

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
- Examples (per-claim marker usage):
  - Pattern X used in three callers — `[src/foo.py:42]`, `[src/bar.py:18]`, `[src/baz.py:88]` — all share the same signature.
  - `NOT_FOUND(query="async ContextVar usage", scope="src/**/*.py")` — no callers in scope; topic premise (existing async-ContextVar consumers) is empty.
  - Vendor blog endorses approach Y as "the canonical pattern in $framework"; `[premise-unverified: not-searched]` — no codebase scan attempted to confirm the pattern occurs in this repo, so the endorsement applies to $framework generally, not this codebase.

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
<!--
Describe what each piece does and how they connect. Use plain, direct language —
no jargon for the relationships between pieces.

If the piece count grows large, consider merging pieces that can be described
together without losing meaningful distinction.
-->

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

Before committing, read and follow `references/orchestrator-review.md` for the `research` phase. The orchestrator review must pass before proceeding to §4b (Critical Review).

### 4b. Critical Review

Run `/cortex-core:critical-review` on `cortex/research/{topic}/research.md`. Address any significant challenges raised before proceeding.

### 5. Transition

Stage and commit `cortex/research/{topic}/` using `/cortex-core:commit`. Summarize key findings for the user and proceed to Specify.

## Constraints

- **Read-only**: Do not modify project files except the research artifact
- **All findings in the artifact**: They won't survive in context alone
- **Scope**: Research the topic as described, not adjacent topics
- **Citations**: codebase-pointing claims must carry an inline `[file:line]` citation traceable to codebase-agent findings, OR an explicit inline `[premise-unverified: not-searched]` marker when the author did not investigate the claim.
- **Empty-corpus reporting**: searches that returned no results must be reported inline as `NOT_FOUND(query=<search-string>, scope=<path-or-glob>)` — distinct from the `premise-unverified: not-searched` marker used when no investigation was attempted.

### Signal formats

The following literal markers are stable contract for downstream consumers (e.g., `/cortex-core:discovery decompose`):

- `[file:line]` — inline citation, e.g., `[skills/discovery/references/research.md:42]`
- `[premise-unverified: not-searched]` — marker indicating the author did not attempt investigation
- `NOT_FOUND(query=<string>, scope=<path-or-glob>)` — marker indicating a search was performed and returned no results
