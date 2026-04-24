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
- **Value**: What problem this solves and why it's worth the effort in *this* codebase. One sentence. Apply both checks below; flag the item when EITHER (a) fails OR (b) indicates an unverified premise.
  - **(a) Local grounding check**: Produce a locally-written `[file:line]` citation that grounds the Value claim in this codebase (the specific file/line where the problem manifests or where the solution will land). If no such citation can be produced — because the target does not exist, the search was inconclusive, or the Value rests on a premise that is not codebase-local — flag the item.
  - **(b) Research-side premise check**: Cross-check `research/{topic}/research.md` for the section substantiating this Value claim. Flag the item when EITHER branch holds: (i) a `[premise-unverified: not-searched]` marker appears adjacent to the Value-supporting claim (per #138's signal, codified at `skills/discovery/references/research.md:148-154`), OR (ii) there is an absence of any `[file:line]` citation within that claim's research section/bullet (no citation at all in the supporting prose). Per E1, branch (ii) — citation-absence — is the dominant path for the current research corpus and should be treated as a primary route, not a legacy fallback; branch (i) becomes primary once #138's marker adoption saturates. This is a lexical check: it catches citation-absence but not citation-incorrectness.
  - **(E9) Ad-hoc fallback**: When no `research/{topic}/research.md` exists (ad-hoc discovery / no research.md), R2(b) is skipped and R2(a) alone governs flagging.
  - **Surface-pattern helper (non-gating hint)**: The following vendor/authority phrasings in the Value prose are a prompt-level signal to apply (a)/(b) with extra care — they do NOT by themselves flag the item: `"vendor X recommends"`, `"Anthropic says"`, `"CrewAI docs"`, `"industry best practice"`, `"canonical pattern in $framework"`, `"recommended approach"`, `"current conventions suggest"`, `"standard pattern"`, `"widely adopted"`, `"accepted convention"`. This list is non-exhaustive; treat the pattern family (external authority cited in place of codebase grounding) as reason to scrutinize.
- **Priority**: Derived from research signals — items flagged as Low effort/Low risk in the feasibility assessment → high priority; items with High effort or High risk → lower priority unless explicitly critical in decision records
- **Type**: Usually `feature`, but may be `chore` or `spike`
- **Size**: S/M/L (informs ordering, not stored in backlog)
- **Dependencies**: Which other work items must complete first

**Flagged-item routing and batch review**: Route flagged items and unflagged items separately before creating tickets.

(i) **R4 cap check (pre-consolidation)**: If any items are flagged per R2, first evaluate the cap on the **pre-consolidation** flag set (before §3 Consolidation Review runs). The cap fires when EITHER (a) **more than 3** items are flagged in the pre-consolidation set, OR (b) **all items are flagged** and N ≥ 2. When the cap fires, skip per-item pauses and halt with a single escalation: "{N} of {total} flagged items (pre-consolidation) — recommend re-running research with premise verification." Offer the user "Return to research" or "Proceed anyway" (the latter resumes the per-item ack flow in (ii)).

(ii) **Per-item acknowledgment for flagged items**: If the cap did not fire, present each flagged item one at a time via `AskUserQuestion`. Each prompt must:
  - Quote the proposed Value string verbatim.
  - State which R2 branch flagged the item: `R2(a)-no-grounding`, `R2(b)-research-absent`, or `both`.
  - Offer three choices: "Acknowledge and proceed", "Drop this item", "Return to research".

If the user chooses "Drop this item", remove the item from the decomposition (no ticket is created later) and continue to the next flagged item. If the user chooses "Return to research", halt decomposition — do not proceed to ticket creation. If the user chooses "Acknowledge and proceed", keep the item and continue.

(iii) **Unflagged items — batch review**: Present the proposed work items to the user for review before creating tickets. Unflagged items (including flagged items the user acknowledged in (ii)) continue through this existing batch-review behavior unchanged.

(iv) **Event logging (R7)**: When a flag is raised, when the user acknowledges a flagged item, or when the user drops a flagged item, append an event to the active discovery topic's event stream (the same stream used by `orchestrator-review.md:22-30`, e.g., `research/{topic}/events.log`). If no event stream exists for the topic, skip silently — do not create new infrastructure.

```
{"ts": "<ISO 8601>", "event": "decompose_flag", "phase": "decompose", "item": "<title>", "reason": "<R2(a)|R2(b)|both>", "details": "<short>"}
{"ts": "<ISO 8601>", "event": "decompose_ack", "phase": "decompose", "item": "<title>"}
{"ts": "<ISO 8601>", "event": "decompose_drop", "phase": "decompose", "item": "<title>", "reason": "<R2 basis from flag event>"}
```

### 3. Consolidation Review

Before creating tickets, review the proposed work items for over-decomposition. Combine items when either of the following signals is present:

**(a) Same-file overlap**: Two or more S-sized items that modify the same set of files. These are aspects of a single change that were split unnecessarily.

**(b) No-standalone-value prerequisite**: A strict sequential dependency where the predecessor has no independent deliverable value — it exists only to enable the successor. Merge the prerequisite into the item it enables.

When combining, merge the descriptions and adjust size accordingly (two S items typically become one M). Update the dependency graph to reflect the combined item.

The agent may also consolidate items beyond (a) and (b) when there is concrete, verifiable rationale (e.g., overlapping file sets, shared research section reference). Self-referential reasoning ("these share a thought process") is not sufficient rationale.

If no consolidation candidates are found, proceed to §4 silently.

When items are combined, document the consolidation decision and rationale in the Key Design Decisions section of `research/{topic}/decomposed.md` (written in §6).

**R5 flag propagation through consolidation**: When consolidation merges two or more work items, flags from inputs propagate to the merged output. Specifically: (i) if any input item to a consolidation merge carried a flag per R2, the merged output item carries the flag for R3 ack-display purposes — the merged item carries the flag of any flagged input, and flag propagation is inherited rather than re-derived on the merged Value prose; (ii) the R4 cap evaluates on the **pre-consolidation** flag count, not the post-consolidation count, so consolidation cannot mask a cap-triggering flag burden by collapsing flagged items into fewer merged items; (iii) the R3 ack prompt for a merged flagged item must surface the **originating** flagged input's Value string and its R2 premise (branch and basis) so the user sees the actual basis of the flag rather than the merged Value prose — per E5, this preserves the originally flagged premise through the merge; (iv) **E10 invariant**: consolidation cannot reduce the flagged set to zero — propagation ensures any input flag survives merging, so the count of flagged items after consolidation is always ≥ 1 whenever the pre-consolidation count was ≥ 1.

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

## Dropped Items
| Title | Reason (R2 branch) | Originating Value |
|-------|--------------------|-------------------|

Include this subsection only when items were dropped at R3's ack prompt; omit when no drops occurred.

## Suggested Implementation Order
[Brief description of the recommended sequence]

## Created Files
- `backlog/NNN-slug.md` — [title]
- `backlog/NNN-slug.md` — [title]
```

### 7. Update Index

Run `cortex-generate-backlog-index` to update the backlog index.

### 8. Commit

Stage and commit the new backlog files and `research/{topic}/decomposed.md` using `/commit`.

### 9. Present Summary

Show the user:

- The epic and its children (or single ticket if no epic)
- The dependency graph and suggested implementation order
- Reminder that `/lifecycle <feature>` is the next step when ready to build

## Constraints

- **Codebase-grounded Value**: Vendor guidance, best practices, and industry standards are not sufficient Value on their own — the Value field must state what problem this solves in *this* codebase.
- **No implementation planning**: Don't specify HOW to build each item — that's `/lifecycle`'s plan phase. Ticket bodies must not contain prescriptive section headers like "## Proposed Fix", "## Implementation Steps", or "## How to Fix". Instead, use descriptive headers to summarize research context: "## Research Context", "## Findings", or "## Context from discovery:" are all fine. Tickets may reference findings from `discovery_source` to give implementers background, but should never prescribe solutions
- **One epic max**: A single discovery produces at most one epic with children
- **Respect backlog conventions**: Follow the backlog skill's frontmatter schema exactly
