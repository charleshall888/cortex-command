# Decomposition: lifecycle-discovery-token-audit

## Epic
- **Backlog ID**: 187
- **Title**: Lifecycle/discovery token-waste cuts and architectural cleanup

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 188 | Reduce sub-agent dispatch artifact duplication | high | M | — |
| 189 | Clean up events.log emission and reader discipline | high | M | — |
| 190 | Promote lifecycle state out of events.log full-reads | high | M | 189 |
| 191 | Reduce boot-context surface (CLAUDE.md + SKILL.md) | high | M | — |
| 192 | Reference-file hygiene (cross-skill + ceremonial + #179 extractions) | medium | M | — |
| 193 | Lifecycle and hook hygiene one-offs | medium | S | — |
| 194 | Investigate epic-172 closure-inaccuracy base rate | high | S | — |

## Suggested Implementation Order

1. **#194** first — closure-inaccuracy spike. Cheap NOW while #172 context is fresh; gates whether any future closure-gate work is justified and may inform #192's #179-extractions component.
2. **#192 + #189** in parallel — `#192` settles canonical reference files (cross-skill collapse + ceremonial deletions) before #193 touches the same families. `#189` settles the events.log emission shape that `#190` depends on.
3. **#188, #191, #193** in parallel — minimal file overlap with the above and with each other.
4. **#190** after #189 — designs against a stable events.log baseline.

Cross-cutting note: research phases for #188, #189, #190, #191 each commit to specific architectural choices that the audit's critical-review and alternative-exploration outputs have already evaluated. Tickets describe the problem-space and constraints; the lifecycle's research/spec/plan phases re-evaluate and commit.

## Key Design Decisions

**Tickets are intentionally non-prescriptive.** Each ticket states the problem with file:line evidence and the constraints that any solution must respect, but the specific mechanism is left to the ticket's research phase. The audit's findings + alternative-exploration outputs are surfaced as *inputs to* each ticket's research, not as pre-baked answers. Three structural areas where alternative-exploration meaningfully shifted the original audit recommendation:

- **#190 (lifecycle state)**: original proposal was "promote to index.md frontmatter"; alternative-exploration challenged this on grounds that index.md is a passive wikilink hub and the project's existing pattern for structured state is JSON files. Ticket leaves the storage choice open.
- **#191 (SKILL.md descriptions)**: original proposal was "introduce `triggers:` frontmatter field"; alternative-exploration found no evidence Anthropic's loader routes against non-`description` fields, making the move a silent regression risk. Ticket leaves the approach open and surfaces conservative-compression and skill-consolidation as candidates.
- **#189 (events emission discipline)**: original proposal was "runtime registry rejection"; alternative-exploration challenged this in favor of a CI-time check that inverts the cost asymmetry without runtime coupling. Ticket leaves the mechanism open.

**Consolidation choices made before file creation**:

- Original audit identified 22 cuttable items; per-slice auditing reduced this to 17-20 via mergers (1+4, 7+206, 195+197+198, 202+203, 189+199); user requested further consolidation to coherent problem-spaces.
- Final 7-child structure groups by problem-space (dispatch / events / state / boot-context / refs / hygiene / process), not by mechanism. Each child fits one `/cortex-core:lifecycle` run.
- Two optional structural follow-ups identified during alternative-exploration (skill consolidation after invocation audit; large-body trims) are folded into #191's scope rather than separate tickets.

## Created Files
- `backlog/187-lifecycle-discovery-token-waste-cuts-and-architectural-cleanup.md` — Epic
- `backlog/188-reduce-sub-agent-dispatch-artifact-duplication.md`
- `backlog/189-clean-up-events-log-emission-and-reader-discipline.md`
- `backlog/190-promote-lifecycle-state-out-of-events-log-full-reads.md`
- `backlog/191-reduce-boot-context-surface-claudemd-and-skillmd.md`
- `backlog/192-reference-file-hygiene-cross-skill-and-ceremonial-content.md`
- `backlog/193-lifecycle-and-hook-hygiene-one-offs.md`
- `backlog/194-investigate-epic-172-closure-inaccuracy-base-rate.md`
