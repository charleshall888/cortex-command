# Decompose Phase

Break the approved Architecture section into backlog tickets. This is the core value of discovery — turning the named pieces into actionable work under a uniform body template.

## Protocol

### 1. Load Context

Read `cortex/research/{topic}/research.md` for findings, feasibility assessment, decision records, and — most importantly — the approved `## Architecture` section. The Architecture section's `### Pieces` sub-section (one role bullet per piece) and `### How they connect` sub-section (the connection/boundary prose) are the source-of-truth input to decompose: `### Pieces` names the analytical piece-set, and `### How they connect` carries the relationships from which dependencies are derived. The research→decompose approval gate (per `skills/discovery/SKILL.md`) must have fired before this phase runs.

> See ADR `cortex/adr/0007-decompose-groups-pieces-into-tickets.md` for why §4 groups coupled pieces into tickets (M pieces → 1 ticket) and the residual anchoring risk that `split-piece` at the R15 gate reduces.

### 2. Consume the Architecture Section

Each bullet in the approved `### Pieces` sub-section is a piece. A piece is not always a ticket: §4 groups tightly-coupled pieces into ticket units, so M pieces may map to 1 ticket. Pieces that share no coupling each become one ticket of their own. Do **not** re-derive pieces from raw findings — the Architecture section already names them by role. The analytical piece-set is fixed at decompose entry; if the agent finds that the piece-set itself is *wrong* (a piece is missing, mis-named, or wrongly split at the analytical level), return to the research phase rather than mutating the set silently. Grouping pieces into ticket units at §4 is a packaging decision over the *right* set, not a mutation of the set — the two are distinct (see §3 and §4).

For each piece, invoke `/backlog-author compose` with the piece's context; the canonical body template lives at `skills/backlog-author/references/body-template.md`.

The template applies uniformly to all pieces. There is no defect-vs-novel branching, no per-shape variation. Every ticket body produced from the architecture uses the template's sections in order.

**Edge-vs-Touch-point semantic distinction.** `## Edges` documents structural constraints between pieces, naming each contract surface by name without a file path. `## Touch points` documents implementation locations. If an edge bullet would name a path or line to express its constraint, the path:line moves to `## Touch points` and a structural-constraint summary naming the contract by name remains in `## Edges`.

**Worked example.** A piece that re-shapes how lifecycle state transitions read:

```
## Edges

- Breaks if the phase-transition contract changes shape (new phase enum value, renamed transition function).
- Depends on the events-registry schema for the events this piece emits.

## Touch points

- skills/lifecycle/SKILL.md §3 (phase-transition prose)
- cortex-lifecycle-state:42-58 (transition function)
- bin/.events-registry.md (target enum for emitted events)
```

The Edges bullets name contracts by name. The Touch points bullets cite paths and lines. The path:line citation `cortex-lifecycle-state:42-58` belongs in Touch points; the structural summary "depends on the events-registry schema" belongs in Edges.

For each ticket, also capture:

- **Title**: Short imperative description (≤ 72 chars)
- **Priority**: Derived from research signals — Low effort/Low risk → high priority; High effort or High risk → lower priority unless explicitly critical in decision records
- **Type**: Usually `feature`, but may be `chore` or `spike`
- **Size**: S/M/L (informs ordering, not stored in backlog)
- **Dependencies**: Derived from the `### How they connect` sub-section — the connection and boundary relationships it describes are what one piece depends on from another

### 3. Consolidation Review

The Architecture section's falsification gate (research-phase R3) has already run the structural-coherence merge test. Do not re-run it here. The analytical piece-set at decompose entry is the merged set.

Two outcomes are distinct here:

- **The piece-set is *wrong* (research owns this).** If the agent finds that two pieces share identical Touch points and identical Role paragraphs — i.e. they are not really two distinct pieces — that is a signal the research-phase merger *missed a case* at the analytical level. Surface this to the user with the option to return to the research phase rather than silently re-deriving or mutating the set at decompose time. The `### Pieces` set is research-owned and must not be rewritten here.
- **The piece-set is *right but over-split for ticketing* (§4 owns this).** Distinct pieces that are nonetheless tightly coupled — they share a connection seam, sit in one integration cluster, carry near-identical roles, or only deliver value when shipped together — are not a research defect. They are a *packaging* question, handled by §4 grouping, which coarsens ticket units without touching the analytical `### Pieces` set.

Proceed to §4. Grouping in §4 is the explicit packaging step; it is never a silent consolidation of the analytical set.

### 4. Determine Grouping

Grouping decides how the analytical pieces are *packaged* into tickets. It reads only the approved Architecture content — `### Pieces` (the role bullets) and `### How they connect` (the connection/boundary prose) — and the dependency relationships derived from them. It never rewrites the `### Pieces` set; it only coarsens ticket units over the *right* set (per §3). See ADR `cortex/adr/0007-decompose-groups-pieces-into-tickets.md`.

**Single-piece branch** (piece_count = 1): Create one backlog ticket directly. **No epic.** The single ticket is the entire output. Skip to §5.

**Zero-piece branch** (piece_count = 0): No tickets are created. Two sub-cases:

- **Fold-into-#N**: The research surfaced a finding that belongs on an existing open ticket. Record the target ticket number and a one-line rationale in `decomposed.md` under a `## Fold-into` heading. No new backlog entries.
- **No-tickets verdict**: The research surfaced no actionable work (e.g., a diagnostic finding that "the current behavior is correct as designed"). Record the verdict and one-sentence rationale in `decomposed.md` under a `## Verdict` heading.

In both zero-piece sub-cases, `decomposed.md` is **still written** as an audit trail. The frontmatter line `decomposition_verdict: zero-piece` makes the branch machine-readable.

**Epic + children** (piece_count ≥ 2): First group the pieces into ticket units, then create one epic and one child per *group*.

**Group tightly-coupled pieces into single tickets.** Before deciding ticket count, weigh the pieces against each other for tight coupling, reasoning over the emitted Architecture content (`### Pieces` roles + `### How they connect` prose) plus the derived dependencies. Group pieces into one ticket when the connection content shows they are obviously one unit of work. Infer the coupling from these indicators, any one of which is enough to consider a group:

- **Shared connection seam** — the pieces meet at the same boundary or contract described in `### How they connect`, so changing one without the other leaves a half-built seam.
- **One integration cluster** — `### How they connect` describes them as a single cluster that integrates together rather than as independently-landing units.
- **Near-identical role** — their `### Pieces` role bullets describe substantially the same job, differing only in detail an implementer would naturally handle together.
- **Value only when shipped together** — neither piece delivers operator-visible value on its own; the value appears only once both land. This is an inferred judgment from the roles and connections, not a literal field the template emits.

Grouping is **opportunistic, never forced**: group only the *gross*, architecture-visible over-splitting (pieces obviously one unit by role or connection). When no coupling is evident, fall back to the 1:1 mapping — one piece, one ticket. Subtle couplings that surface only once bodies are drafted are not §4's job; they remain the manual `consolidate-pieces` fallback's domain at the R15 gate (§5). Grouping is an explicit packaging decision, surfaced to the operator at R15 with its rationale — it is never a silent mutation of the `### Pieces` set, which stays unchanged in `research.md` as the authoritative per-piece record that `split-piece` re-derives from.

**Preserve intra-group ordering.** When grouped pieces have `blocked-by` relationships *among themselves*, the cross-piece ordering does not disappear — it becomes an intra-ticket ordering constraint. Carry it into the grouped body as an explicit sequence note and record it in `## Grouping Notes` (§6), mirroring the corpus precedent's internal phase boundary. Dependencies from *outside* the group retarget the surviving grouped ticket. (Edge case: if all N pieces group into one ticket, the output collapses to a single ticket with no epic, reusing the single-piece branch semantics; the `## Grouping Notes` record still makes the N→1 collapse auditable.)

Then:

1. Create an epic ticket first — a parent backlog item summarizing the full scope
   - `type: epic`
   - `discovery_source: cortex/research/{topic}/research.md`
   - Body references the research artifact
2. Create child tickets — one per *group* (an ungrouped piece is its own group of one), each with `parent: <epic-id>`. A child wrapping multiple pieces gets one coherent merged body (§5); a single-piece child uses the §2 uniform template directly.

### 5. Create Backlog Tickets

**Authoring a grouped ticket's body.** For a child that wraps a single piece, author the body straight from the §2 uniform template. For a child that wraps *multiple* grouped pieces (§4), author **one merged body** that covers the whole group — mirroring the R15 `consolidate-pieces` body-merge convention (§5, the R15 gate sub-section below): the grouped pieces' `## Why`, `## Role`, and `## Integration` are **prose-merged** into one coherent narrative (not concatenated piece-by-piece), and their `## Edges` and `## Touch points` bullets are **unioned and deduplicated**. When the grouped pieces carried a `blocked-by` ordering among themselves (§4), fold that surviving order into the merged body as an explicit intra-ticket sequence note, framed as an internal phase boundary rather than a cross-ticket dependency. The research-phase Architecture `### Pieces` source in `research.md` is **not** touched by this merge — it stays unchanged as the authoritative per-piece record, so the retained source is exactly what a later `split-piece <N>` re-derives the constituent piece bodies from.

Ticket bodies authored under the Role/Integration/Edges/Touch-points template are validated by `cortex-check-prescriptive-prose` at pre-commit time (LEX-1 scanner). The scanner runs section-partitioned: path:line citations, `§N`/`RN` section-index citations, and multi-line fenced code blocks are permitted only in `## Touch points` and are flagged when they appear inside `## Role`, `## Integration`, or `## Edges`.

**LEX-1 regex specification** (the scanner's exact behavior, baked into this prose):

- **Pattern 1 (path:line)**: `\b[\w./\-]+\.(md|py|sh|json|toml|yml|yaml):\d+(?:-\d+)?\b` — matches `decompose.md:147`, `bin/foo.py:42-58`. Bare paths without `:line` do NOT match (narrative references are fine).
- **Pattern 2 (section-index)**: `(?:§|R)\d+(?:[a-z]\)?|\([a-z]\))?\b` — matches `§5`, `§3a`, `§3(a)`, `R2`, `R2(b)`. Single-letter references without a digit do NOT match.
- **Pattern 3 (quoted-prose-patch)**: a fenced code block (` ``` ` or `~~~`) of ≥ 2 non-empty lines appearing inside a forbidden section. Single-line fenced blocks and inline backticks do NOT match.

**Forbidden sections (per ticket body)**: `## Why`, `## Role`, `## Integration`, `## Edges`. **Permitted section**: `## Touch points`.

**Section-boundary detection**: a section begins at a line matching `^## (Why|Role|Integration|Edges|Touch points)$` and ends at the next line matching `^## ` (any sibling-level heading) or end-of-file. Third-level subsections (`### foo`) inside a section are part of that section. Fenced code blocks are tolerated as ranges (do not split sections).

**Worked examples**:

- **PASSES** (no flag): `## Edges` followed by "This piece breaks if the phase-transition contract changes." (named contract, no path:line)
- **PASSES** (no flag): `## Role` followed by "The role is to track lifecycle state. See `cortex-update-item` for the helper." (inline backtick narrative)
- **FLAGS**: `## Edges` followed by "This piece must update decompose.md:147 to replace the ban." (path:line in forbidden section)
- **FLAGS**: `## Integration` followed by "Follows the pattern in §3a." (section-index in forbidden section)
- **NOT flagged** (anti-pattern: false positive on legitimate narrative): `## Edges` followed by "The phase-transition contract is documented in skills/lifecycle/SKILL.md." (bare path, no `:line`, no `§`)
- **NOT flagged** (anti-pattern: false positive on inline code): `## Role` followed by "The helper `cortex-update-item` writes the state." (inline backtick code reference, not a fenced block)

The scanner runs once at decompose ticket-write time. Defense-in-depth at architecture-write time is deferred. The pre-commit hook is the second-actor surface that re-runs the check before any ticket lands in `cortex/backlog/`.

#### Post-decompose batch-review gate (R15)

After all N ticket bodies are authored AND the internal prescriptive-prose scanner has passed, BUT BEFORE any tickets commit to `cortex/backlog/`, a user-blocking gate fires. This restores the per-ticket review affordance that the prior R3 per-item-ack flow provided; without it, the user's first encounter with ticket bodies would be a pre-commit hook failure.

The gate presents all ticket titles and bodies via a single AskUserQuestion-style surface and offers four options:

- **`approve-all`** — proceed to write all N tickets to `cortex/backlog/`.
- **`revise-piece <N>`** — open a free-text revision prompt scoped to ticket N's body. The agent re-walks ticket N's `## Why`, `## Role`, `## Integration`, `## Edges`, and `## Touch points` under the user's direction and re-presents the FULL batch (not just ticket N) at the gate. Loop continues until `approve-all` or all pieces are dropped.
- **`drop-piece <N>`** — do not write ticket N to `cortex/backlog/`. Record the dropped piece in `decomposed.md` with a one-sentence rationale under a `## Dropped Items` heading. Continue the gate loop with the remaining tickets.
- **`consolidate-pieces <N,M,...>`** — open a free-text revision prompt scoped to merging pieces N,M,…  into a single ticket. The agent drafts a merged body in which the `## Why`, `## Role`, and `## Integration` paragraphs are prose-merged into one coherent narrative and the `## Edges` and `## Touch points` bullets are unioned (deduplicated). The user revises the draft via free text under the same UX as `revise-piece`. On approval of the merged body, the lowest-index named piece survives carrying the revised body and lands at the lowest-named slot; the other named pieces are removed from the batch. Surviving pieces then renumber contiguously from 1 in the next R15 presentation (this is agent-context bookkeeping during composition, not a structural property of the helper or event), and the FULL renumbered batch re-presents at R15. The loop continues until `approve-all` or all pieces are dropped/consolidated to one. If the user names only a single index (e.g. `consolidate-pieces 3`), the agent re-prompts naturally ("consolidate piece 3 with what?") rather than rejecting the invocation. Piece-index references inside OTHER tickets' bodies are not assumed to exist by index — `## Edges` and `## Touch points` bullets reference contracts and files by name, not by piece-index, so cross-ticket index drift is a non-issue; the merged body itself should be re-read for any literal piece-index references it contains and rewritten if found. A subsequent `drop-piece` on a consolidation survivor needs no slot reclamation: the batch simply renumbers contiguously from 1 again on the next round.

The gate is user-blocking: no tickets commit to `cortex/backlog/` until `approve-all` fires (or all pieces are dropped).

Consolidation approvals are recorded under a `## Consolidation Notes` heading in `cortex/research/{topic}/decomposed.md` — the agent creates the heading on the first consolidation and appends to it on subsequent ones. This heading is distinct from `## Dropped Items` (the Title-keyed Markdown table for fully-rejected tickets used by `drop-piece`). Each entry is prose, in the agent's natural voice, naming (i) which pieces merged into which surviving piece by their current (post-renumber) index, (ii) the surviving piece's revised role summary, and (iii) a one-sentence rationale for why the merge holds. This matches the corpus precedent at `cortex/research/swap-daytime-autonomous-for-worktree-interactive/decomposed.md` and `cortex/research/archive/gpg-signing-claude-code-sandbox/decomposed.md`.

On each user response, emit one `approval_checkpoint_responded` event with `checkpoint: decompose-commit` and the chosen response. Use the helper module per the `cortex_command/discovery.py` interface (event emission lives in the helper; the prose here only names the event by its literal name `"event": "approval_checkpoint_responded"`).

Follow the `/cortex-core:backlog add` conventions for each ticket:

1. Scan filenames matching `[0-9]*-*.md` in both `cortex/backlog/` and `cortex/backlog/archive/` to find the highest existing numeric ID
2. Create the epic first if applicable (children need its ID for `parent`)
3. Each ticket gets proper frontmatter:
   - `parent: <epic-id>` on children (omit on epic or single tickets)
   - `blocked-by: [<ids>]` based on Integration-shape dependencies
   - `tags: [<topic>]` to link back to the discovery topic
   - `created` and `updated` set to today's date
   - `discovery_source: cortex/research/{topic}/research.md` — enables `/cortex-core:lifecycle` to auto-load prior discovery context
   <!-- Note: lifecycle reads `discovery_source:` first; `research:` is recognized as a fallback for hand-authored or pre-coupling backlog items. -->

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
- **Ticket NNN** ← pieces P, Q, R. [One-sentence rationale for why these pieces are one unit of work.] Intra-group order: P → Q (Q was `blocked-by` P among the grouped pieces; preserved as an internal phase boundary inside the ticket, not a cross-ticket dependency).

## Created Files
- `cortex/backlog/NNN-slug.md` — [title]
- `cortex/backlog/NNN-slug.md` — [title]
```

`## Grouping Notes` is parallel to the R15-gate `## Consolidation Notes` / `## Dropped Items` headings. When §4 groups pieces into a ticket, record one entry per grouped ticket naming (i) which pieces were grouped into which ticket, (ii) a one-sentence rationale for why the group is one unit, and (iii) any **surviving intra-group ordering** — when grouped pieces carried `blocked-by` relationships *among themselves*, that order is preserved as an explicit intra-ticket sequence note (an internal phase boundary, mirroring the corpus precedent at `cortex/research/swap-daytime-autonomous-for-worktree-interactive/decomposed.md`), never silently dropped. This makes every grouping — including an all-N-pieces-into-one-ticket collapse — auditable, and gives `split-piece <N>` the recorded ordering to restore when it re-derives the constituent pieces. Omit the heading entirely when no grouping occurred (the no-coupling 1:1 fallback produces no entries). The `### Pieces` source in `research.md` stays unchanged regardless; `## Grouping Notes` records only the packaging decision, not a mutation of the analytical set.

For the single-piece branch, omit the Epic subsection and list one ticket. For the zero-piece branch, write `decomposition_verdict: zero-piece` in frontmatter and include either a `## Fold-into` or `## Verdict` section instead of Work Items.

### 7. Update Index

Run `cortex-generate-backlog-index` to update the backlog index.

### 8. Commit

Stage and commit the new backlog files and `cortex/research/{topic}/decomposed.md` using `/cortex-core:commit`.

### 9. Present Summary

Show the user:

- The epic and its children (or single ticket / zero-piece verdict)
- The dependency graph and suggested implementation order
- Reminder that `/cortex-core:lifecycle <feature>` is the next step when ready to build

## Constraints

- **Architecture-section-driven**: The analytical piece-set is the approved `### Pieces` sub-section from research, and dependencies derive from the `### How they connect` sub-section — the headings the research template actually emits. Do not re-derive pieces from raw findings; do not silently mutate the analytical set at decompose time. Grouping pieces into ticket units (§4) is permitted and distinct: it is an explicit, R15-surfaced packaging decision that coarsens ticket *count* without touching the `### Pieces` set, which stays unchanged as the per-piece record `split-piece` re-derives from. See ADR `cortex/adr/0007-decompose-groups-pieces-into-tickets.md`.
- **Uniform body template**: All tickets use `## Role`, `## Integration`, `## Edges`, and optional `## Touch points`. No per-shape branching.
- **Touch-points exclusivity**: Path:line citations and section-index citations live only in `## Touch points`. The pre-commit scanner enforces this.
- **No implementation planning**: Don't specify HOW to build each piece — that's `/cortex-core:lifecycle`'s plan phase. Ticket bodies describe role, integration, and structural edges; the plan phase fills in mechanism.
- **One epic max**: A single discovery produces at most one epic with children.
- **Respect backlog conventions**: Follow the backlog skill's frontmatter schema exactly.
