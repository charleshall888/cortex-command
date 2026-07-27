# Research Phase

Multi-dimensional investigation building deep understanding of a topic.

## 1. Set up

Articulate 3–7 specific research questions — the acceptance criteria; research isn't done until each has a confident answer or is explicitly marked unanswerable. Present them for review and add any the user raises.

Load requirements: `cortex-load-requirements` (omit `--feature`), read every listed non-skipped path, relay any fallback note. Use them to find where this topic intersects established constraints.

Read back the sizing Clarify persisted (conversation memory doesn't survive a phase resume):

```
cortex-discovery read-research-sizing --topic <topic>
```

A legacy directory, or Research entered before Clarify ran, returns discovery's floor default `{"complexity":"simple","criticality":"medium"}` and never errors.

## 2. Dispatch the fan-out

Size and dispatch per the **fanout** sibling reference `fanout.md` (propagated absolute path) — count matrix, mandatory core, always-last adversarial rule. Apply it; don't re-derive it.

Beyond the mandatory core, discovery's natural dimensions fill the remaining slots: **Domain & Prior Art** (comparable implementations, industry patterns, trade-offs, lessons learned) and **Feasibility** (technical risks, unknowns, prerequisites, rough S/M/L/XL effort), plus any finer-grained angle the topic warrants.

Agents are read-only — no `isolation: "worktree"`, no project-file writes. Prerequisites that are really codebase-state checks belong to the Codebase angle; §3's Feasibility Prerequisites column carries implementation sequencing only.

## 3. Write the artifact

Compose into **discovery's own schema** below — not `/cortex-core:research`'s. `## Architecture` → `### Pieces` / `### How they connect` are machine-parsed by the Research→Decompose gate and by decompose.md, so synthesis must land in exactly this structure. Where agents contradict each other, surface the contradiction under `## Open Questions` rather than picking a side.

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

Codebase-pointing claims carry an inline `[file:line]` citation or an explicit `[premise-unverified: not-searched]` marker. A search returning nothing reports inline as `NOT_FOUND(query=<search-string>, scope=<path-or-glob>)` — distinct from an uninvestigated premise. Findings live in the artifact, not in context; research the topic as described, not adjacent ones.

## 4. Review and hand off

Run the orchestrator-review protocol (propagated **orchestrator-review** path) for the `research` phase. It must pass before the next step.

In the fix-agent dispatch, substitute `{topic} discovery topic` for `{feature}` and `cortex/research/{topic}/{artifact}` for the lifecycle artifact path; the fix agent returns plain prose (`changed [path] — [rationale]`), not lifecycle's YAML envelope.

Then run `/cortex-core:critical-review` on the artifact and address any significant challenges. Commit `cortex/research/{topic}/`, summarize, and hand off to the Research → Decompose gate — do not begin Decompose until the user answers it.
