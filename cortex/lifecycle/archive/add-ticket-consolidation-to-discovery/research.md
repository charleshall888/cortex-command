# Research: add-ticket-consolidation-to-discovery

## Codebase Analysis

### Current Decompose Protocol
The discovery skill's decompose phase (`skills/discovery/references/decompose.md`) has 8 steps. The relevant flow:
- **§2 Identify Work Items**: breaks research into discrete items, captures title, description, priority, type, size (S/M/L), and dependencies
- **§3 Determine Grouping**: binary choice — 1 item = single ticket, 2+ items = epic + children
- **§4 Create Backlog Tickets**: creates the actual backlog files

There is **no consolidation guidance** anywhere in the protocol. The agent is instructed to break down but never to evaluate whether items should be recombined.

### Evidence of Over-Decomposition in Past Discoveries

Three clear patterns emerged from past decomposition records:

**Pattern 1 — Sequential S-sized pairs touching the same file:**
- `overnight-merge-conflict-prevention` (015, 016): Both S, both `chore`, both exclusively touch `claude/overnight/report.py`, strictly sequential (016 depends on 015). Ticket 015's body even notes "These may be combined or tracked separately."

**Pattern 2 — Independent S-sized items sharing target files:**
- `generative-ui-harness` (034, 032): Both S, both modify the same dashboard HTML templates, both depend on 035. Together they form a single M-sized template polish ticket.

**Pattern 3 — S-sized items forming a strict chain with no independent value:**
- `requirements-audit` (010, 011): 010 is a path-fix prereq, 011 is the actual redesign. 010 has no standalone user value — it exists only to unblock 011.

### Prior Art — One Consolidation Decision Was Made Manually
In `research/generative-ui-harness/decomposed.md`, one explicit merge was documented: "028 is a merge: Originally separate 'define rubric' and 'create CONTEXT.md' tickets. Merged because both are documentation artifacts produced by the same thought process, one feeds directly into the other." This is the only consolidation decision recorded across all discoveries. The rationale used: same thought process + direct feed relationship.

### Where the Change Should Go

**Primary insertion point**: A new step between §2 (Identify Work Items) and §3 (Determine Grouping) in `decompose.md`. After initial items are identified with sizes and dependencies, the agent reviews the list for consolidation candidates before moving to grouping and ticket creation.

**Not §3 (Determine Grouping)**: §3 handles the binary epic/single decision. Consolidation is a different concern — reducing the item list before that decision is made.

**Not Clarify or Research phases**: Both operate before work items exist.

### Consolidation Heuristics (Candidate Signals)

Based on the three observed patterns, consolidation candidates share one or more of:
1. **Same target files**: Two items that modify the same set of files
2. **Strict sequential dependency with no independent value**: Item A exists only to enable Item B, with no standalone deliverable
3. **Same thought process**: Both items are aspects of a single logical change (the generative-ui-harness rationale)
4. **Both size S**: Small items are the primary over-decomposition risk; M and L items generally represent enough scope on their own

### Size Field Not Persisted
`size:` is decompose-time metadata only — not stored in backlog frontmatter. This means consolidation must happen during decompose, not retroactively.

## Open Questions

- None — the research covered all investigation areas identified in Clarify.
