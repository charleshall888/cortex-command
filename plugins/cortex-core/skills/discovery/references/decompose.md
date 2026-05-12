# Decompose Phase

Break the approved Architecture section into backlog tickets. This is the core value of discovery — turning the named pieces into actionable work under a uniform body template.

## Protocol

### 1. Load Context

Read `cortex/research/{topic}/research.md` for findings, feasibility assessment, decision records, and — most importantly — the approved `## Architecture` section. The Architecture section's `### Pieces`, `### Integration shape`, and `### Seam-level edges` sub-sections are the source-of-truth input to decompose. The research→decompose approval gate (per `skills/discovery/SKILL.md`) must have fired before this phase runs.

### 2. Consume the Architecture Section

Each bullet in the approved `### Pieces` sub-section becomes one ticket candidate. Do **not** re-derive pieces from raw findings — the Architecture section already names them by role. The piece-set is fixed at decompose entry; if the agent finds that the piece-set is wrong, return to the research phase rather than mutating the set silently.

For each piece, author a ticket body under the **uniform template**:

```
## Role

What this piece does, named by role (not by mechanism). One paragraph.

## Integration

How this piece connects to the other pieces and to the existing system.
Reference the Integration shape sub-section's contract surfaces.

## Edges

Structural constraints and boundary breaks. Each bullet names a contract
surface by name (e.g., "phase-transition contract", "events-registry schema").
Bullets do NOT cite file paths or section indices.

## Touch points  (optional)

Implementation locations: specific file paths with line numbers, section
indices (§N, RN), or multi-line code excerpts. This is the sole permitted
location for path:line citations and section-index citations.
```

The template applies uniformly to all pieces. There is no defect-vs-novel branching, no per-shape variation. Every ticket body produced from the architecture uses these four headers in this order.

**Edge-vs-Touch-point semantic distinction.** `## Edges` documents structural constraints between pieces, naming each contract surface by name without a file path. `## Touch points` documents implementation locations. If an edge bullet would name a path or line to express its constraint, the path:line moves to `## Touch points` and a structural-constraint summary naming the contract by name remains in `## Edges`.

**Worked example.** A piece that re-shapes how lifecycle state transitions read:

```
## Edges

- Breaks if the phase-transition contract changes shape (new phase enum value, renamed transition function).
- Depends on the events-registry schema for the events this piece emits.

## Touch points

- skills/lifecycle/SKILL.md §3 (phase-transition prose)
- bin/cortex-lifecycle-state:42-58 (transition function)
- bin/.events-registry.md (target enum for emitted events)
```

The Edges bullets name contracts by name. The Touch points bullets cite paths and lines. The path:line citation `bin/cortex-lifecycle-state:42-58` belongs in Touch points; the structural summary "depends on the events-registry schema" belongs in Edges.

For each ticket, also capture:

- **Title**: Short imperative description (≤ 72 chars)
- **Priority**: Derived from research signals — Low effort/Low risk → high priority; High effort or High risk → lower priority unless explicitly critical in decision records
- **Type**: Usually `feature`, but may be `chore` or `spike`
- **Size**: S/M/L (informs ordering, not stored in backlog)
- **Dependencies**: From the Integration shape and Seam-level edges sub-sections

### 3. Consolidation Review

The Architecture section's falsification gate (research-phase R3) has already run the structural-coherence merge test. Do not re-run it here. The piece-set at decompose entry is the merged set.

If during ticket authoring the agent finds that two pieces share identical Touch points and identical Role paragraphs, that is a signal the research-phase merger missed a case — surface this to the user with the option to return to research rather than silently consolidating at decompose time.

If no consolidation candidates surface, proceed to §4.

### 4. Determine Grouping

The grouping is determined by piece_count from the approved Architecture section.

**Single-piece branch** (piece_count = 1): Create one backlog ticket directly. **No epic.** The single ticket is the entire output. Skip to §5.

**Zero-piece branch** (piece_count = 0): No tickets are created. Two sub-cases:

- **Fold-into-#N**: The research surfaced a finding that belongs on an existing open ticket. Record the target ticket number and a one-line rationale in `decomposed.md` under a `## Fold-into` heading. No new backlog entries.
- **No-tickets verdict**: The research surfaced no actionable work (e.g., a diagnostic finding that "the current behavior is correct as designed"). Record the verdict and one-sentence rationale in `decomposed.md` under a `## Verdict` heading.

In both zero-piece sub-cases, `decomposed.md` is **still written** as an audit trail. The frontmatter line `decomposition_verdict: zero-piece` makes the branch machine-readable.

**Epic + children** (piece_count ≥ 2):

1. Create an epic ticket first — a parent backlog item summarizing the full scope
   - `type: epic`
   - `discovery_source: cortex/research/{topic}/research.md`
   - Body references the research artifact
2. Create child tickets — one per piece, each with `parent: <epic-id>` and body authored under the §2 uniform template

### 5. Create Backlog Tickets

Ticket bodies authored under the Role/Integration/Edges/Touch-points template are validated by `bin/cortex-check-prescriptive-prose` at pre-commit time (LEX-1 scanner). The scanner runs section-partitioned: path:line citations, `§N`/`RN` section-index citations, and multi-line fenced code blocks are permitted only in `## Touch points` and are flagged when they appear inside `## Role`, `## Integration`, or `## Edges`.

**LEX-1 regex specification** (the scanner's exact behavior, baked into this prose):

- **Pattern 1 (path:line)**: `\b[\w./\-]+\.(md|py|sh|json|toml|yml|yaml):\d+(?:-\d+)?\b` — matches `decompose.md:147`, `bin/foo.py:42-58`. Bare paths without `:line` do NOT match (narrative references are fine).
- **Pattern 2 (section-index)**: `(?:§|R)\d+(?:[a-z]\)?|\([a-z]\))?\b` — matches `§5`, `§3a`, `§3(a)`, `R2`, `R2(b)`. Single-letter references without a digit do NOT match.
- **Pattern 3 (quoted-prose-patch)**: a fenced code block (` ``` ` or `~~~`) of ≥ 2 non-empty lines appearing inside a forbidden section. Single-line fenced blocks and inline backticks do NOT match.

**Forbidden sections (per ticket body)**: `## Role`, `## Integration`, `## Edges`. **Permitted section**: `## Touch points`.

**Section-boundary detection**: a section begins at a line matching `^## (Role|Integration|Edges|Touch points)$` and ends at the next line matching `^## ` (any sibling-level heading) or end-of-file. Third-level subsections (`### foo`) inside a section are part of that section. Fenced code blocks are tolerated as ranges (do not split sections).

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

The gate presents all ticket titles and bodies via a single AskUserQuestion-style surface and offers three options:

- **`approve-all`** — proceed to write all N tickets to `cortex/backlog/`.
- **`revise-piece <N>`** — open a free-text revision prompt scoped to ticket N's body. The agent re-walks ticket N's `## Role`, `## Integration`, `## Edges`, and `## Touch points` under the user's direction and re-presents the FULL batch (not just ticket N) at the gate. Loop continues until `approve-all` or all pieces are dropped.
- **`drop-piece <N>`** — do not write ticket N to `cortex/backlog/`. Record the dropped piece in `decomposed.md` with a one-sentence rationale under a `## Dropped Items` heading. Continue the gate loop with the remaining tickets.

The gate is user-blocking: no tickets commit to `cortex/backlog/` until `approve-all` fires (or all pieces are dropped).

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

## Created Files
- `cortex/backlog/NNN-slug.md` — [title]
- `cortex/backlog/NNN-slug.md` — [title]
```

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

- **Architecture-section-driven**: The piece-set is the approved `### Pieces` sub-section from research. Do not re-derive pieces from raw findings; do not silently mutate the set at decompose time.
- **Uniform body template**: All tickets use `## Role`, `## Integration`, `## Edges`, and optional `## Touch points`. No per-shape branching.
- **Touch-points exclusivity**: Path:line citations and section-index citations live only in `## Touch points`. The pre-commit scanner enforces this.
- **No implementation planning**: Don't specify HOW to build each piece — that's `/cortex-core:lifecycle`'s plan phase. Ticket bodies describe role, integration, and structural edges; the plan phase fills in mechanism.
- **One epic max**: A single discovery produces at most one epic with children.
- **Respect backlog conventions**: Follow the backlog skill's frontmatter schema exactly.
