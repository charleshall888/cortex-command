# Decompose Phase

Break research findings into implementable work items and create backlog tickets. This is the core value of discovery — turning research into actionable work.

## Protocol

### 1. Load Context

Read `research/{topic}/research.md` for findings, feasibility assessment, and decision records.

### 2. Identify Work Items

Analyze the research and break findings into discrete, independently implementable work items. Each should:

- Deliver a testable increment of value
- Be completable in a single `/lifecycle` run
- Have clear boundaries (what's in, what's out)

For each work item, capture:

- **Title**: Short imperative description
- **Description**: What this item delivers, referencing research findings
- **Priority**: Derived from research signals — items flagged as Low effort/Low risk in the feasibility assessment → high priority; items with High effort or High risk → lower priority unless explicitly critical in decision records
- **Type**: Usually `feature`, but may be `chore` or `spike`
- **Size**: S/M/L (informs ordering, not stored in backlog)
- **Dependencies**: Which other work items must complete first

Present the proposed work items to the user for review before creating tickets.

### 3. Consolidation Review

Before creating tickets, review the proposed work items for over-decomposition. Combine items when either of the following signals is present:

**(a) Same-file overlap**: Two or more S-sized items that modify the same set of files. These are aspects of a single change that were split unnecessarily.

**(b) No-standalone-value prerequisite**: A strict sequential dependency where the predecessor has no independent deliverable value — it exists only to enable the successor. Merge the prerequisite into the item it enables.

When combining, merge the descriptions and adjust size accordingly (two S items typically become one M). Update the dependency graph to reflect the combined item.

The agent may also consolidate items beyond (a) and (b) when there is concrete, verifiable rationale (e.g., overlapping file sets, shared research section reference). Self-referential reasoning ("these share a thought process") is not sufficient rationale.

If no consolidation candidates are found, proceed to §4 silently.

When items are combined, document the consolidation decision and rationale in the Key Design Decisions section of `research/{topic}/decomposed.md` (written in §6).

### 4. Determine Grouping

**Single ticket**: If the research produces exactly one work item, create a single backlog ticket. No epic needed.

**Epic + children**: If the spec produces 2+ work items:

1. Create an epic ticket first — a parent backlog item summarizing the full scope
   - `type: epic`
   - `discovery_source: research/{topic}/research.md`
   - Body references the research artifact
2. Create child tickets — one per work item, each with `parent: <epic-id>`

### 5. Create Backlog Tickets

Follow the `/backlog add` conventions for each ticket:

1. Scan filenames matching `[0-9]*-*.md` in both `backlog/` and `backlog/archive/` to find the highest existing numeric ID
2. Create the epic first if applicable (children need its ID for `parent`)
3. Each ticket gets proper frontmatter:
   - `parent: <epic-id>` on children (omit on epic or single tickets)
   - `blocked-by: [<ids>]` based on work item dependencies
   - `tags: [<topic>]` to link back to the discovery topic
   - `created` and `updated` set to today's date
   - `discovery_source: research/{topic}/research.md` — enables `/lifecycle` to auto-load prior discovery context
   <!-- Note: lifecycle reads `discovery_source:` first; `research:` is recognized as a fallback for hand-authored or pre-coupling backlog items. -->

### 6. Write Decomposition Record

Create `research/{topic}/decomposed.md` to record what was produced:

```markdown
# Decomposition: {topic}

## Epic
- **Backlog ID**: NNN
- **Title**: [epic title]

## Work Items
| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| NNN | [title] | high/medium/low | S/M/L | [IDs or —] |

## Suggested Implementation Order
[Brief description of the recommended sequence]

## Created Files
- `backlog/NNN-slug.md` — [title]
- `backlog/NNN-slug.md` — [title]
```

### 7. Update Index

Run `backlog/generate-index.sh` to update the backlog index.

### 8. Commit

Stage and commit the new backlog files and `research/{topic}/decomposed.md` using `/commit`.

### 9. Present Summary

Show the user:

- The epic and its children (or single ticket if no epic)
- The dependency graph and suggested implementation order
- Reminder that `/lifecycle <feature>` is the next step when ready to build

## Constraints

- **No implementation planning**: Don't specify HOW to build each item — that's `/lifecycle`'s plan phase. Ticket bodies must not contain prescriptive section headers like "## Proposed Fix", "## Implementation Steps", or "## How to Fix". Instead, use descriptive headers to summarize research context: "## Research Context", "## Findings", or "## Context from discovery:" are all fine. Tickets may reference findings from `discovery_source` to give implementers background, but should never prescribe solutions
- **One epic max**: A single discovery produces at most one epic with children
- **Respect backlog conventions**: Follow the backlog skill's frontmatter schema exactly
