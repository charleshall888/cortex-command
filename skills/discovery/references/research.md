# Research Phase

## 1. Set up

Articulate 3–7 research questions — the acceptance criteria: research isn't done until each has a confident answer or is marked unanswerable. Present them and add any the user raises.

`cortex-load-requirements` (no `--feature`), read every listed non-skipped path, relay any fallback note; use them to find where the topic meets established constraints.

Read back Clarify's sizing (a legacy directory, or Research before Clarify, returns the floor default and never errors):

```
cortex-discovery read-research-sizing --topic <topic>
```

## 2. Fan out

Size and dispatch per the **fanout** sibling reference (propagated path) — count matrix, mandatory core, adversarial-last. Beyond the core, discovery's natural angles fill remaining slots: **Domain & Prior Art** (comparable implementations, industry patterns, trade-offs) and **Feasibility** (risks, unknowns, prerequisites, rough S/M/L/XL effort), plus finer angles the topic warrants. Agents are read-only — no worktree isolation, no project-file writes. Codebase-state prerequisites belong to the Codebase angle; §3's Feasibility Prerequisites column carries implementation sequencing only.

## 3. Write the artifact

Discovery's own schema, not `/cortex-core:research`'s. `## Architecture` → `### Pieces` / `### How they connect` are machine-parsed by the gate and by decompose.md, so land exactly this structure. Agent contradictions go under `## Open Questions`, never silently picked.

```markdown
# Research: {topic}

## Research Questions
1. [Question] → **[Answer or "Unresolved: reason"]**

## Codebase Analysis
[Existing patterns, files/modules affected, integration points, constraints]

## Web & Documentation Research
<!-- Omit if skipped -->

## Domain & Prior Art
<!-- Omit if skipped -->

## Feasibility Assessment
| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|

## Architecture

### Pieces
- [Piece named by role, not by mechanism — one bullet per piece]

### How they connect
[How the pieces connect and what each piece's boundaries depend on.]

## Decision Records
<!-- Key trade-offs and alternatives considered, one paragraph each -->

## Open Questions
- [Questions needing answers before spec or implementation]
```

Codebase-pointing claims carry an inline `[file:line]` citation or an explicit `[premise-unverified: not-searched]` marker; a search returning nothing reports `NOT_FOUND(query=<search-string>, scope=<path-or-glob>)`. Findings live in the artifact, not in context; research the topic as described, not adjacent ones.

## 4. Review and hand off

Run the orchestrator-review protocol (propagated path) for `research`; it must pass. In its fix-agent dispatch substitute `{topic} discovery topic` for `{feature}` and `cortex/research/{topic}/{artifact}` for the lifecycle path; the fix agent returns plain prose (`changed [path] — [rationale]`).

Commit `cortex/research/{topic}/`, summarize, and hand off to the Research → Decompose gate — no Decompose work until the user answers it.
