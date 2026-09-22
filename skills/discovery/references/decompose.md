# Decompose Phase

Turn the approved Architecture section into backlog tickets.

### 1. Consume Architecture

Read `cortex/research/{topic}/research.md`. `### Pieces` lists the pieces (one bullet each, named by role). `### How they connect` gives the dependencies. Never rebuild the pieces from raw findings. Pieces that look *wrong* (missing, mis-named, mis-split, or two with the same Touch points and Role) are research's to fix: tell the user and offer to go back. Pieces that are distinct but closely tied are a grouping question for §4.

### 4. Group

Grouping merges pieces into fewer tickets; it never edits `### Pieces`.

- **One piece** → one ticket, no epic.
- **Zero** → no tickets. Still write `decomposed.md` with frontmatter `decomposition_verdict: zero-piece` and either `## Fold-into` (an existing ticket number plus the reason) or `## Verdict` (no work to do).
- **Two or more** → group, then one epic and one child per group.

Group pieces that share a connection point, form one integration cluster, have the same role, or only deliver visible value together. Group only when the Architecture plainly shows over-splitting. No clear tie → one ticket per piece. A subtler tie is a `revise-piece` at §5a. A `blocked-by` *inside* a group becomes an ordering note in `## Grouping Notes`. A dependency crossing the group boundary, either way, names the merged ticket.

### 5. Author tickets

Run `/backlog-author compose` per ticket with that piece's context. A child made of several pieces gets one merged body: merge the Why/Role/Integration prose, and combine Edges/Touch-points without duplicates. Record **title** (imperative, ≤72 chars), **priority** (low effort/risk → higher; high → lower, unless a decision record marks it critical), **type** (usually `feature`; sometimes `chore` or `spike`), **size** (S/M/L, ordering only), **dependencies** from `### How they connect`.

### 5a. Batch-review gate

After all N bodies and before anything goes to `cortex/backlog/`, stop for the user — their first look at the bodies. Show every title and body, then offer:

- **`approve-all`** — write all N.
- **`revise-piece <N>`** — free-text changes to ticket N only; rework it and show the full batch again.
- **`drop-piece <N>`** — don't write it; record it under `## Dropped Items` with one sentence.

Repeat until `approve-all` or every piece is dropped.

```
cortex-discovery emit-checkpoint-response --topic <topic> --checkpoint decompose-commit --response <response>
```

### 6. Create

After `approve-all`, resolve the backend (SKILL.md § Backend routing). Under `cortex-backlog`, create the epic first so children have its ID. Pass `--parent <epic-id>` on children (omit on an epic or lone ticket), `--blocked-by <ids>` from Integration-shape dependencies, `--tags <topic>`, and `discovery_source: cortex/research/{topic}/research.md`.

### 6a. Decomposition record

`cortex/research/{topic}/decomposed.md`:

```markdown
# Decomposition: {topic}

## Epic
- **Backlog ID**: NNN
- **Title**: [epic title]

## Work Items
| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|

## Suggested Implementation Order

## Grouping Notes
- **Ticket NNN** ← pieces P, Q, R. [Rationale.] Intra-group order: P → Q.

## Created Files
- `cortex/backlog/NNN-slug.md` — [title]
```

Omit `## Grouping Notes` when nothing was grouped. With one piece, omit Epic. With zero pieces, replace Work Items with `## Fold-into` or `## Verdict`.

### 7. Index

Under `cortex-backlog` (resolved at §6; resolve now if there were zero pieces) → run `cortex-generate-backlog-index`. Anything else → skip with a one-line note.

### 8. Commit and summarize

Commit the backlog files and `decomposed.md`. Show the epic and children (or the single ticket, or the zero-piece verdict), the dependency graph and order, and say that `/cortex-core:refine <feature>` is next. Do no implementation planning here — role, integration, and structural edges only. At most one epic per discovery.
