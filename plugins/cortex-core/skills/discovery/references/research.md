# Research Phase

Multi-dimensional investigation to build deep understanding of a topic.

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

**Choose the angles.** Discovery's natural investigation dimensions form the angle pool.

Fill the remaining slots the matrix buys with discovery's other distinct dimensions — **Domain & Prior Art** (competing/analogous implementations, industry patterns, trade-offs others hit, lessons that apply) and **Feasibility** (technical risks, unknowns that could derail, prerequisites, rough S/M/L/XL effort) — plus any finer-grained angle the topic warrants.

**Dispatch it.** Follow fanout.md's two-wave protocol with the Agent tool — read-only research agents, no `isolation: "worktree"`, mirroring how `/cortex-core:research` Step 3 dispatches. Before the core wave, resolve the gather model in this orchestrator body (not inside any angle-prompt block):

```bash
model=$(cortex-resolve-model --role searcher)
```

Dispatch the mandatory core plus the chosen angles for the cell — every angle except the always-last adversarial one — as one batch of Agent calls in a single response, passing the captured `$model` (sonnet) as each core-wave Agent's `model:` parameter, per fanout.md's dispatch-protocol routing rule.

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
