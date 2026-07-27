# Decompose Phase

Turn the approved Architecture section into backlog tickets — the core value of discovery.

### 1. Consume the Architecture Section

Read `cortex/research/{topic}/research.md`. `### Pieces` is the analytical piece set (one bullet per piece, named by role); `### How they connect` is where dependencies come from. **Never re-derive pieces from raw findings.**

A piece is not always a ticket — §4 groups tightly-coupled pieces into ticket units. If the piece set itself looks *wrong* (missing, mis-named, mis-split, or two pieces sharing identical Touch points and Role paragraphs), that is research's to fix: surface it and offer to return to research rather than rewriting the research-owned set here. Distinct-but-coupled pieces are a *packaging* question for §4, not a defect.

### 4. Determine Grouping

Grouping coarsens ticket units without mutating `### Pieces`.

**One piece** → one ticket, no epic. **Zero pieces** → no tickets, but still write `decomposed.md` as an audit trail with frontmatter `decomposition_verdict: zero-piece`, holding either `## Fold-into` (the finding belongs on an existing open ticket — its number plus a one-line rationale) or `## Verdict` (no actionable work). **Two or more** → group first, then one epic and one child per *group*.

Group pieces that share a connection seam, form one integration cluster, carry substantially the same role, or deliver operator-visible value only once both land. Grouping is **opportunistic, never forced** — only gross, architecture-visible over-splitting; no evident coupling falls back to 1:1. Subtler couplings surfacing once bodies are drafted belong to `consolidate-pieces` at the §5a gate.

A `blocked-by` relationship *among* grouped pieces becomes an intra-ticket ordering note, never a dropped one: carry it into the body as an explicit sequence and record it in `## Grouping Notes`. Dependencies from outside the group retarget the surviving ticket.

### 5. Create Backlog Tickets

Invoke `/backlog-author compose` per ticket with that piece's context. A multi-piece child gets **one merged body**: Why/Role/Integration prose-merged into one narrative, Edges/Touch-points unioned and deduplicated.

Capture alongside each: **title** (imperative, ≤72 chars), **priority** (low effort/risk → higher; high effort or risk → lower, unless a decision record marks it critical), **type** (usually `feature`, sometimes `chore` or `spike`), **size** (S/M/L, ordering only — not stored), **dependencies** from `### How they connect`.

### 5a. Post-Decompose Batch-Review Gate

After all N bodies are authored and **before any commit to `cortex/backlog/`**, a user-blocking gate fires — the user's first encounter with the bodies. Present every title and body, and offer:

- **`approve-all`** — write all N tickets.
- **`revise-piece <N>`** — free-text revision scoped to ticket N; re-walk it in full, then re-present the FULL batch.
- **`drop-piece <N>`** — don't write it; record it under `## Dropped Items` with a one-sentence rationale.
- **`consolidate-pieces <N,M,…>`** — merge into one ticket (same prose-merge/union rule as §5). The lowest-index named piece survives at the lowest slot; the batch renumbers contiguously from 1 and re-presents in full.
- **`split-piece <N>`** — inverse of grouping: re-derive ticket N into its constituent pieces from the unchanged `### Pieces` source (not the lossy merged body), restoring any `## Grouping Notes` ordering, then re-present the renumbered batch.

Loops until `approve-all` or all pieces are dropped. Consolidations are recorded under `## Consolidation Notes` — which pieces merged into which survivor by post-renumber index, its revised role summary, and a one-sentence rationale.

```
cortex-discovery emit-checkpoint-response --topic <topic> --checkpoint decompose-commit --response <response>
```

### 6. Backend Routing and Creation

After `approve-all`, resolve the backend (SKILL.md § Backend routing). Under `cortex-backlog`, create the epic first so children have its ID. Frontmatter: `parent: <epic-id>` on children (omit on an epic or a lone ticket), `blocked-by: [<ids>]` from Integration-shape dependencies, `tags: [<topic>]`, and `discovery_source: cortex/research/{topic}/research.md` — lifecycle reads that first, with `research:` as the hand-authored fallback.

### 6a. Write Decomposition Record

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

`## Grouping Notes` makes every grouping auditable and gives `split-piece` the ordering to restore — omit when no grouping occurred. The single-piece branch omits the Epic subsection; the zero-piece branch replaces Work Items with `## Fold-into` or `## Verdict`.

### 7. Update Index

Re-resolve the active backend **here** with `cortex-read-backlog-backend` (argless, fail-open) — don't reuse §6's resolution, which is scoped to its create flow and never runs on the zero-piece branch. Under `cortex-backlog` run `cortex-generate-backlog-index` to update the backlog index; any other value (`none` or external) → skip with a one-line advisory, since `cortex-generate-backlog-index` targets the `cortex-backlog` engine and there is no index to regenerate.

### 8. Commit and Summarize

Commit the new backlog files and `decomposed.md` via `/cortex-core:commit`, then present the epic and its children (or the single ticket / zero-piece verdict), the dependency graph and suggested order, and a reminder that `/cortex-core:refine <feature>` is the next step.

**No implementation planning here** — role, integration, and structural edges only; mechanism belongs to lifecycle's plan phase. At most one epic per discovery.
