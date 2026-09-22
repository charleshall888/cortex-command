# Research Phase

## 1. Set up

Write 3–7 research questions. Research is done only when each has a confident answer or is marked unanswerable. Show them and add any the user raises.

Run `cortex-load-requirements` (no `--feature`), read every listed path that is not skipped, and tell the user about any fallback note. Use them to find where the topic meets existing constraints.

Read Clarify's sizing. An old directory, or Research run before Clarify, returns a default and never errors:

```
cortex-discovery read-research-sizing --topic <topic>
```

## 2. Fan out

Choose the agent count and angles from the **fanout** reference (SKILL.md gives its path): count matrix, required core angles, adversarial last. Fill the remaining slots with discovery's own angles: **Domain & Prior Art** (similar implementations, industry patterns, trade-offs), **Feasibility** (risks, unknowns, prerequisites, rough S/M/L/XL effort), and any finer angle the topic needs. Agents are read-only: no worktree isolation, no project-file writes. Prerequisites about the state of the code belong to the Codebase angle. The Prerequisites column of §3's Feasibility table holds build order only.

## 3. Write the artifact

This is discovery's own layout, not `/cortex-core:research`'s. The gate and decompose.md parse `## Architecture` → `### Pieces` / `### How they connect`, so use exactly this structure. Where agents disagree, put it under `## Open Questions` — never pick a side silently.

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

Each claim about the code carries a `[file:line]` citation or a `[premise-unverified: not-searched]` marker. A search that finds nothing reports `NOT_FOUND(query=<search-string>, scope=<path-or-glob>)`. Put findings in the artifact, not just in the conversation. Research the topic as described, not nearby ones.

## 4. Review and hand off

Run the orchestrator-review protocol (SKILL.md gives its path) for `research`; it must pass. In its fix-agent prompt, replace `{feature}` with `{topic} discovery topic` and the lifecycle path with `cortex/research/{topic}/{artifact}`. The fix agent returns plain prose (`changed [path] — [rationale]`).

Commit `cortex/research/{topic}/`, summarize, and go to the Research → Decompose gate. No Decompose work until the user answers it.
