# Decompose Phase

Turn the approved Architecture section into backlog tickets.

### 1. Consume Architecture

Read `cortex/research/{topic}/research.md`. `### Pieces` is the piece set (one bullet per piece, named by role); `### How they connect` yields dependencies. Never re-derive pieces from raw findings. A piece set that looks *wrong* (missing, mis-named, mis-split, or two pieces with identical Touch points and Role) is research's to fix — surface it and offer to return to research. Distinct-but-coupled pieces are a packaging question for §4.

### 4. Group

Grouping coarsens ticket units without mutating `### Pieces`. **One piece** → one ticket, no epic. **Zero** → no tickets, but still write `decomposed.md` with frontmatter `decomposition_verdict: zero-piece` holding `## Fold-into` (an existing ticket number plus rationale) or `## Verdict` (no actionable work). **Two or more** → group, then one epic and one child per group.

Group pieces that share a connection seam, form one integration cluster, carry the same role, or deliver visible value only together. Opportunistic, never forced — only gross, architecture-visible over-splitting; no evident coupling → 1:1. Subtler couplings are a `revise-piece` at §5a. A `blocked-by` *within* a group becomes an intra-ticket ordering note recorded in `## Grouping Notes`; outside dependencies retarget the surviving ticket.

### 5. Author tickets

`/backlog-author compose` per ticket with that piece's context. A multi-piece child gets one merged body: Why/Role/Integration prose-merged, Edges/Touch-points unioned and deduplicated. Capture **title** (imperative, ≤72 chars), **priority** (low effort/risk → higher; high → lower, unless a decision record marks it critical), **type** (usually `feature`; sometimes `chore` or `spike`), **size** (S/M/L, ordering only), **dependencies** from `### How they connect`.

### 5a. Batch-review gate

After all N bodies and before any commit to `cortex/backlog/`, a user-blocking gate — the user's first sight of the bodies. Present every title and body, then offer:

- **`approve-all`** — write all N.
- **`revise-piece <N>`** — free-text revision scoped to ticket N; re-walk it, re-present the full batch.
- **`drop-piece <N>`** — don't write it; record under `## Dropped Items` with one sentence.

Loops until `approve-all` or all pieces are dropped.

```
cortex-discovery emit-checkpoint-response --topic <topic> --checkpoint decompose-commit --response <response>
```

### 6. Create

After `approve-all`, resolve the backend (SKILL.md § Backend routing). Under `cortex-backlog` create the epic first so children have its ID; pass `--parent <epic-id>` on children (omit on an epic or lone ticket), `--blocked-by <ids>` from Integration-shape dependencies, `--tags <topic>`, and `discovery_source: cortex/research/{topic}/research.md`.

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

Omit `## Grouping Notes` when nothing grouped; the single-piece branch omits Epic; the zero-piece branch replaces Work Items with `## Fold-into` or `## Verdict`.

### 7. Index

Under `cortex-backlog` (as resolved at §6; resolve now on the zero-piece branch) → `cortex-generate-backlog-index`; anything else → skip with a one-line advisory.

### 8. Commit and summarize

Commit the backlog files and `decomposed.md`; present the epic and children (or the single ticket / zero-piece verdict), the dependency graph and order, and that `/cortex-core:refine <feature>` is next. No implementation planning here — role, integration, and structural edges only. At most one epic per discovery.
