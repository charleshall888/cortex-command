# Specification: add-ticket-consolidation-to-discovery

## Problem Statement

The discovery skill's decompose phase breaks research findings into work items but has no mechanism to evaluate whether items are too granular. Past discoveries have produced sequential S-sized ticket pairs touching the same file, independent S-sized items sharing target files, and prerequisite items with no standalone value — all cases where combining would produce better-scoped tickets for lifecycle execution.

## Requirements

1. **Consolidation review step in decompose.md**: Add a new section §3 (Consolidation Review) between current §2 (Identify Work Items) and current §3 (Determine Grouping, renumbered to §4). Renumber all subsequent sections accordingly (current §3→§4, §4→§5, etc.).
   - Acceptance: `grep -c "Consolidation Review" skills/discovery/references/decompose.md` returns ≥ 1; section headings in decompose.md follow the renumbered scheme (§1 Load Context, §2 Identify Work Items, §3 Consolidation Review, §4 Determine Grouping, §5 Create Backlog Tickets, etc.)

2. **Two consolidation heuristics**: The review step must check for these two signals, either of which suggests items should be combined:
   - (a) **Same-file overlap**: Two or more S-sized items that modify the same set of files
   - (b) **No-standalone-value prerequisite**: A strict sequential dependency where the predecessor has no independent deliverable value — it exists only to enable the successor
   - The agent may suggest additional consolidation beyond (a) and (b), but must provide concrete, verifiable rationale (e.g., overlapping file sets, shared research section reference). Self-referential reasoning ("these share a thought process") is not sufficient rationale.
   - Acceptance: Both heuristics appear as named criteria in the new §3 of `decompose.md`

3. **Consolidation is automatic**: When the heuristics match, the agent combines the items directly — no user confirmation step. The agent notes what it combined and why in its output, but does not pause for approval.
   - Acceptance: The new §3 contains no language requiring user presentation or approval before combining items

4. **Consolidation rationale recorded in decomposed.md**: When items are combined, the rationale must be documented in a "Key Design Decisions" section of `research/{topic}/decomposed.md`.
   - Acceptance: The new §3 references documenting consolidation decisions in `decomposed.md`

## Non-Requirements

- No changes to the discovery clarify or research phases — consolidation applies only at decompose time
- No changes to the backlog skill's frontmatter schema or the `size:` field behavior (remains decompose-time only)
- No retroactive consolidation of existing backlog tickets
- No hard cap on ticket count — the heuristics identify specific anti-patterns, not an arbitrary maximum
- No user confirmation gate — consolidation is automatic, not interactive

## Edge Cases

- **All proposed items are consolidation candidates**: If consolidation would reduce to a single item, the result is a single ticket (no epic needed per existing §4 logic).
- **Consolidation reduces item count from 2+ to 1**: The grouping decision (§4) naturally handles this — single item = single ticket, no epic.
- **No consolidation candidates found**: Skip the step silently and proceed to §4.

## Technical Constraints

- Renumber existing sections in decompose.md: current §2 stays §2, new consolidation review becomes §3, current §3 (Determine Grouping) becomes §4, and so on. Update any internal cross-references within decompose.md to use the new numbering.
- The consolidation step runs after sizes and dependencies are assigned (end of §2) so it has the metadata needed to evaluate heuristics
- Must not introduce prescriptive implementation language — the consolidation guidance describes what to evaluate, not how to code the tickets

## Open Decisions

- None
