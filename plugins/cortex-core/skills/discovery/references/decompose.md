# Decompose Phase

Break the approved Architecture section into backlog tickets — the core value of discovery, turning named pieces into actionable work under a uniform body template.

## Protocol

### 1. Load Context

Read `cortex/research/{topic}/research.md`: `### Pieces` (one role bullet per piece) is the analytical piece-set, `### How they connect` carries the relationships dependencies derive from — decompose's source-of-truth input. The research→decompose approval gate (`skills/discovery/SKILL.md`) must have fired before this phase runs.

### 2. Consume the Architecture Section

Each bullet in the approved `### Pieces` sub-section is a piece. A piece is not always a ticket: §4 groups tightly-coupled pieces into ticket units, so M pieces may map to one ticket; uncoupled pieces each become their own. Do **not** re-derive pieces from raw findings — the Architecture section already names them by role. If the piece-set itself looks *wrong* (missing, mis-named, mis-split), return to research rather than mutating it here (§3).

For each piece, invoke `/backlog-author compose` with the piece's context; the canonical body template lives at `skills/backlog-author/references/body-template.md`. The template applies uniformly — no per-shape branching.

**Edge-vs-Touch-point.** `## Edges` names structural constraints between pieces by contract surface, no file path. `## Touch points` holds implementation locations. If an edge bullet would need a path:line to express its constraint, the path:line moves to `## Touch points` and a structural-constraint summary stays in `## Edges`.

For each ticket, also capture:

- **Title**: Short imperative description (≤ 72 chars)
- **Priority**: low effort/risk → high; high effort or risk → lower, unless critical in decision records
- **Type**: Usually `feature`, but may be `chore` or `spike`
- **Size**: S/M/L (informs ordering, not stored in backlog)
- **Dependencies**: derived from `### How they connect` — what one piece depends on from another

### 3. Consolidation Review

The `### Pieces` set arrives already merged — do not re-derive or re-merge it here. Distinguish two cases:

- **Wrong (research owns).** Two pieces sharing identical Touch points and Role paragraphs may not be distinct — a case the research-phase merger missed. Surface it to the user with the option to return to research rather than rewriting the research-owned set here.
- **Over-split for ticketing (§4 owns).** Distinct-but-tightly-coupled pieces (shared seam, one integration cluster, near-identical roles, or value only when shipped together) are a *packaging* question for §4, not a defect.

Proceed to §4.

### 4. Determine Grouping

Grouping packages the analytical pieces into tickets, reading only `### Pieces`, `### How they connect`, and derived dependencies — coarsening ticket units without rewriting the `### Pieces` set (per §3).

**Single-piece branch** (piece_count = 1): One backlog ticket, directly. **No epic.** Skip to §5.

**Zero-piece branch** (piece_count = 0): No tickets created. Two sub-cases:

- **Fold-into-#N**: the research surfaced a finding belonging on an existing open ticket. Record the target ticket number and a one-line rationale in `decomposed.md` under `## Fold-into`.
- **No-tickets verdict**: the research surfaced no actionable work (e.g. "current behavior is correct as designed"). Record the verdict and one-sentence rationale under `## Verdict`.

Either way `decomposed.md` is **still written** as an audit trail; the frontmatter line `decomposition_verdict: zero-piece` makes the branch machine-readable.

**Epic + children** (piece_count ≥ 2): group the pieces into ticket units first, then create one epic and one child per *group*.

**Group tightly-coupled pieces into single tickets**, reasoning over `### Pieces` roles, `### How they connect` prose, and derived dependencies: group when pieces share a connection seam, form one integration cluster, carry substantially the same role, or deliver operator-visible value only once both land.

Grouping is **opportunistic, never forced** — group only gross, architecture-visible over-splitting. No evident coupling falls back to 1:1. Subtler couplings surfacing once bodies are drafted are the `consolidate-pieces` fallback's domain at the R15 gate (§5).

**Preserve intra-group ordering.** A `blocked-by` relationship *among* grouped pieces becomes an intra-ticket ordering constraint, not a dropped one: carry it into the grouped body as an explicit sequence note and record it in `## Grouping Notes` (§6). Dependencies from *outside* the group retarget the surviving grouped ticket. (If all N pieces group into one ticket, the output collapses to the single-piece branch; `## Grouping Notes` still records the N→1 collapse.)

Then:

1. Create an epic ticket first — a parent backlog item summarizing the full scope: `type: epic`, `discovery_source: cortex/research/{topic}/research.md`, body references the research artifact.
2. Create child tickets — one per *group* (an ungrouped piece is its own group of one), each with `parent: <epic-id>`. A multi-piece child gets one coherent merged body (§5); a single-piece child uses the §2 uniform template directly.

### 5. Create Backlog Tickets

**Authoring a grouped ticket's body.** A single-piece child's body comes straight from the §2 uniform template; a multi-piece child (§4) gets **one merged body** per the `consolidate-pieces` convention below: Why/Role/Integration prose-merged into one narrative, Edges/Touch-points unioned and deduplicated.

Path:line citations, `§N`/`RN` section-index citations, and multi-line fenced code blocks belong only in `## Touch points` — never in `## Role`, `## Integration`, or `## Edges`.

**Forbidden sections (per ticket body)**: `## Why`, `## Role`, `## Integration`, `## Edges`. **Permitted section**: `## Touch points`. (The scanner owns the exact match patterns; author against the worked examples below.)

**Worked examples**: `## Edges` → "Breaks if the phase-transition contract changes" passes (named contract, no path:line). `## Edges` → "must update decompose.md:147 to replace the ban" flags (path:line in a forbidden section). `## Integration` → "Follows the pattern in §3a" flags (section-index in a forbidden section). `## Role` → "The helper `cortex-update-item` writes the state" does not flag (inline backtick, not a fenced block, no path:line or section-index).

The scanner runs once at ticket-write time; the pre-commit hook re-runs it before any ticket lands in `cortex/backlog/`.

#### Post-decompose batch-review gate (R15)

After all N ticket bodies are authored and the prescriptive-prose scanner has passed, but before any commit to `cortex/backlog/`, a user-blocking gate fires: without it, the user's first encounter with ticket bodies would be a pre-commit hook failure.

The gate presents all ticket titles and bodies via a single AskUserQuestion-style surface and offers five options:

- **`approve-all`** — write all N tickets to `cortex/backlog/`.
- **`revise-piece <N>`** — free-text revision scoped to ticket N's body: the agent re-walks it in full, then re-presents the FULL batch (not just N). Loops until `approve-all` or all pieces drop.
- **`drop-piece <N>`** — don't write ticket N; record it in `decomposed.md` with a one-sentence rationale under `## Dropped Items`. Gate loop continues with the remaining tickets.
- **`consolidate-pieces <N,M,...>`** — free-text revision merging pieces N,M,… into one ticket: `## Why`/`## Role`/`## Integration` prose-merge into one narrative, `## Edges`/`## Touch points` union and dedupe. Same revision UX as `revise-piece`. On approval the lowest-index named piece survives at the lowest-named slot; the others are removed and the batch renumbers contiguously from 1, then re-presents in full. Loops until `approve-all` or all pieces are dropped/consolidated to one.
- **`split-piece <N>`** — inverse of grouping: re-derives ticket N back into its constituent pieces, re-authoring each body from the retained Architecture `### Pieces` source in `research.md` (unchanged by §4 grouping) rather than the lossy merged body, restoring any `## Grouping Notes` ordering onto the re-derived pieces. Re-presents the FULL renumbered batch (mirrors `consolidate-pieces` bookkeeping).

The gate is user-blocking: no tickets commit to `cortex/backlog/` until `approve-all` fires (or all pieces are dropped).

Consolidation approvals are recorded under `## Consolidation Notes` in `decomposed.md` (created on first consolidation, appended after) — distinct from `## Dropped Items` (`drop-piece`'s table). Each entry names (i) which pieces merged into which surviving piece by post-renumber index, (ii) its revised role summary, and (iii) a one-sentence rationale for the merge.

On each response, emit one `approval_checkpoint_responded` event with `checkpoint: decompose-commit` via the discovery helper module (never hand-roll the emission).

**Backend routing.** After `approve-all` fires and before creating any ticket, resolve the active backend once with `cortex-read-backlog-backend` (argless); route:

- **`cortex-backlog`** (default) → create the epic and children via the conventions below.
- **`none`** → skip the create CLI; write each full title + body into `cortex/research/{topic}/decomposed.md` (alongside the §6 Decomposition Record) so no authored work is lost, with a one-line advisory that ticket creation is disabled for this repo. No writes land in `cortex/backlog/`.
- **any other value** (external tracker) → create the equivalent items best-effort per `backlog.instructions` (e.g. `gh issue create`), surfacing composed bodies inline if they can't be filed.

Under the `cortex-backlog` arm, follow `/cortex-backlog:backlog add` conventions:

- Create the epic first if applicable (children need its ID for `parent`)
- Each ticket gets proper frontmatter: `parent: <epic-id>` on children (omit on epic or single tickets); `blocked-by: [<ids>]` from Integration-shape dependencies; `tags: [<topic>]`; `discovery_source: cortex/research/{topic}/research.md` (lifecycle reads this first, `research:` is a fallback for hand-authored items) to enable `/cortex-core:lifecycle` auto-load.

### 6. Write Decomposition Record

Create `cortex/research/{topic}/decomposed.md` to record what was produced:

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

## Grouping Notes
- **Ticket NNN** ← pieces P, Q, R. [Rationale.] Intra-group order: P → Q (internal phase boundary, not a cross-ticket dependency).

## Created Files
- `cortex/backlog/NNN-slug.md` — [title]
- `cortex/backlog/NNN-slug.md` — [title]
```

`## Grouping Notes` parallels the R15-gate's `## Consolidation Notes` / `## Dropped Items`: one entry per grouped ticket, naming the pieces grouped, a one-sentence rationale, and any surviving intra-group ordering (per §4) — this makes every grouping, including an all-N-into-one collapse, auditable and gives `split-piece <N>` the ordering to restore. Omit the heading when no grouping occurred. `research.md`'s `### Pieces` source stays unchanged regardless — this heading records only the packaging decision.

For the single-piece branch, omit the Epic subsection and list one ticket. For the zero-piece branch, write `decomposition_verdict: zero-piece` in frontmatter and include either a `## Fold-into` or `## Verdict` section instead of Work Items.

### 7. Update Index

Resolve the active backlog backend **here at §7** with `cortex-read-backlog-backend` (argless, fail-open) — do not reuse §5's resolution, which is scoped to its create flow and never runs on the zero-piece branch; re-resolving here keeps zero-piece, single-piece, and epic+children all correctly gated. Route on the value:

- **`cortex-backlog`** (default) → run `cortex-generate-backlog-index` to update the backlog index.
- **any other value** (`none` or external) → skip with a one-line advisory: `cortex-generate-backlog-index` targets the `cortex-backlog` engine, so there is no index to regenerate under this backend.

### 8. Commit

Stage and commit the new backlog files and `cortex/research/{topic}/decomposed.md` using `/cortex-core:commit`.

### 9. Present Summary

Show the user:

- The epic and its children (or single ticket / zero-piece verdict)
- The dependency graph and suggested implementation order
- Reminder that `/cortex-core:lifecycle <feature>` is the next step when ready to build

## Constraints

- **Architecture-section-driven**: pieces come only from the approved `### Pieces` set (§2); never re-derive them from raw findings. Grouping (§4) coarsens ticket *count* without mutating that set — `split-piece` re-derives from it.
- **Uniform body template** (§2): no per-shape branching.
- **Touch-points exclusivity** (§5): the pre-commit scanner enforces it.
- **No implementation planning**: role, integration, and structural edges only — mechanism is `/cortex-core:lifecycle`'s plan phase.
- **One epic max**: a single discovery produces at most one epic with children.
- **Respect backlog conventions**: follow the backlog skill's frontmatter schema exactly.
