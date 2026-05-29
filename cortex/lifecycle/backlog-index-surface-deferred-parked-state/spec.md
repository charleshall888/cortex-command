# Specification: backlog-index-surface-deferred-parked-state

## Problem Statement

The generated backlog index (`cortex/backlog/index.md`, produced by
`cortex_command/backlog/generate_index.py`) renders a Status column but no signal for items that are
*parked/deferred* while their frontmatter `status` stays `backlog`. Such an item reads as a ready,
actionable feature in the index's `## Backlog` grouping — the index-side "what's ready" surface that
`/cortex-core:dev` and `/cortex-core:backlog` consume as prose. This feature makes a deferred item
distinguishable in `index.md` without opening the file, and stops the **index's grooming view** from
listing it as actionable. The beneficiary is the human grooming the backlog or reading the index for
ready work. The motivating wild-light case: a `status: backlog` item carrying a `## Deferred` body
section and a `deferred` tag, invisible as parked in the index.

**Scope honesty (the signal is index-view-only).** This feature acts only on `index.md` rendering.
It deliberately does NOT change what the autonomous overnight runner selects: overnight reads
`index.json` (which Req 3 keeps unchanged) via `is_item_ready`, which this feature does not touch. So
an item tagged `deferred` but left at an overnight-eligible status (`backlog`/`refined`) with
`research.md` + `spec.md` present is hidden from the index grooming view yet **still selectable by
overnight**. The conceptual model that resolves this: the `deferred` **tag** is an index-view flag for
items kept at an active status; to fully park an item from overnight, set its **`status`** to a
non-eligible value (a literal `status: deferred` is already excluded everywhere today). Teaching the
machine scans (`ready.py`/overnight) to honor the tag is a deliberately-scoped follow-up (see
Non-Requirements); this spec documents the interim divergence as a known limitation rather than
silently shipping it.

## Phases
- **Phase 1: Deferred signal** — render `<status> (deferred)` in the index.md Status cell for any item carrying a `deferred` frontmatter tag (case-insensitive), leaving `index.json` and the raw status untouched.
- **Phase 2: Actionable suppression + regression guard** — drop deferred-tagged items from the `## Refined` and `## Backlog` groupings via a local predicate, preserve the table row and `index.json` record, document the tag convention, and pin all of it with tests.

## Requirements

_Priority (MoSCoW): Requirements 1–5 and 7 are **must-have** — the feature and its regression-proof.
Requirement 6 is a **must-have guard** (pins the no-shared-change boundary). Requirement 8 (documenting
the convention) is **must-have**: the critical review established that `deferred` is a behavior-bearing
reserved string, so leaving it undocumented would ship a magic string — it is not a droppable nicety._

1. **`deferred` tag is the recognized signal source, matched case-insensitively**: `generate_index.py`
   treats an item as deferred iff some element of its parsed frontmatter `tags:` list equals
   `deferred` after `.strip().lower()` normalization (so `Deferred`, `DEFERRED`, and surrounding
   whitespace all fire; an unrelated tag like `deferred-feature-work` does NOT, since the match is
   whole-element). No new frontmatter field and no body-section parsing are introduced (the generator
   parses frontmatter only).
   **Acceptance**: Covered behaviorally by the Req 2 and Req 4 tests (which exercise the live predicate
   in the render and grouping paths) plus a dedicated case-variant test asserting a `Deferred`-tagged
   item is annotated and suppressed identically to a `deferred`-tagged one. (A `grep` for the literal
   predicate is intentionally NOT the acceptance — it cannot distinguish a live guard from a comment.)
   **Phase**: Deferred signal.

2. **Status-cell annotation**: In the `index.md` master table, a deferred-tagged item's Status cell
   renders `<raw-status> (deferred)` (e.g. `backlog (deferred)`). The annotation is derived in the
   row-rendering path (`generate_index.py` ~lines 230–234); the record's `status` value is not mutated.
   **Acceptance**: A `generate_md` unit test (new file, Req 7) asserts the **full rendered table row**
   for a `status: backlog` item tagged `deferred` equals the expected row string containing
   `| backlog (deferred) |`, and that a non-deferred control item's row contains `| backlog |` with no
   `(deferred)` suffix. Full-row equality (not bare substring) is required so the assertion pins
   placement, not mere presence. **Phase**: Deferred signal.

3. **`index.json` is unchanged**: The `index.json` record for a deferred-tagged item keeps `"status"`
   as the raw enum value (e.g. `"backlog"`) and continues to emit the `tags` array including
   `"deferred"`. No `index.json` field is added, removed, or reshaped.
   **Acceptance**: A test asserts `generate_json([...])` for a deferred-tagged `status: backlog` item
   yields a record with `record["status"] == "backlog"` and `"deferred" in record["tags"]`.
   **Phase**: Deferred signal.

4. **Suppress deferred items from `## Refined` and `## Backlog`**: A deferred-tagged item is excluded
   from the `## Refined` and `## Backlog` actionable groupings by a local predicate in
   `generate_index.py` (skip when the deferred predicate from Req 1 matches), evaluated in the
   generator's own grouping loops. `is_item_ready` is neither modified nor relied upon to know about
   tags.
   **Acceptance**: A `generate_md` test asserts a deferred-tagged, otherwise-ready `status: backlog`
   item does NOT appear as a `- **<id>**` bullet under `## Backlog`, while a non-deferred ready control
   item DOES. An analogous assertion covers a `deferred`-tagged `status: refined` item under
   `## Refined`. **Phase**: Actionable suppression + regression guard.

5. **Table row is preserved**: The deferred item still renders as a row in the master table (so it
   stays visible for grooming) — suppression applies only to the grouped/actionable sections.
   **Acceptance**: The Req 2 test additionally confirms the deferred item's `id` appears in the table
   region of `generate_md` output (its row is present). **Phase**: Actionable suppression + regression guard.

6. **No shared-logic or consumer change**: `cortex_command/backlog/readiness.py`,
   `cortex_command/backlog/ready.py`, `cortex_command/overnight/backlog.py`, and
   `cortex_command/common.py` are not modified. The only non-test, non-doc source file changed is
   `cortex_command/backlog/generate_index.py`.
   **Acceptance**: `git diff --name-only "$(git merge-base HEAD main)" -- cortex_command/` lists only
   `cortex_command/backlog/generate_index.py` (merge-base, not the live `main` tip, so the check is
   stable under an advanced `main` and in worktree/feature-branch contexts; pass if that is the sole
   `cortex_command/` entry). This is a point-in-time boundary check; the durable guarantee that the
   shared modules' behavior is unchanged is that the existing `tests/` suites for `readiness.py` /
   `ready.py` / overnight selection still pass under `just test` (Req 7). **Phase**: Actionable
   suppression + regression guard.

7. **Tests**: A new test file `tests/test_generate_backlog_index.py` covers Reqs 1–5 by building a
   `tmp_path` backlog with (a) a deferred-tagged `status: backlog` item, (b) a non-deferred ready
   control, (c) a deferred-tagged `status: refined` item, and (d) a `Deferred`-cased item, then
   asserting on `generate_md` / `generate_json` output. The file must contain the specific assertions
   named in the Req 1–5 acceptance clauses — a placeholder/no-op test does not satisfy this
   requirement. Mirror the fixture style of `tests/test_select_overnight_batch.py` and the
   string-assertion style of `tests/test_backlog_ready_render.py`.
   **Acceptance**: `just test` exits 0 (pass if exit code = 0); the new file is collected and the
   Req 1–5 assertions it contains pass. **Phase**: Actionable suppression + regression guard.

8. **Document the `deferred` tag convention** (must-have): Add a note to the canonical backlog schema
   doc (`skills/backlog/references/schema.md`) under the `tags` field description stating that a
   `deferred` tag is recognized by the index generator as a parked-state signal — annotated in the
   table and excluded from the actionable groupings — and that it is an index-view flag that does NOT
   remove the item from overnight selection (use a non-eligible `status` for that). (The plugin mirror
   regenerates via the pre-commit hook; edit the canonical source only.)
   **Acceptance**: `grep -c 'deferred' skills/backlog/references/schema.md` ≥ 1 AND the note appears
   within the `tags`-field region of the doc (verified by reading, since `grep` count alone does not
   prove placement). **Phase**: Actionable suppression + regression guard.

## Non-Requirements

- **Does NOT auto-detect body-only deferral.** The signal requires an author-applied frontmatter
  `deferred` tag. An item parked only via a `## Deferred` body section (no tag) is NOT captured — the
  generator parses frontmatter only, and body-section parsing would be net-new brittle infrastructure.
  Adopting this convention means existing body-only-deferred items must be tagged to benefit. (The
  motivating wild-light item already carries both the tag and the body section, so it is captured.)
- **Does NOT add a first-class `deferred` status** (ticket approach 3). Rejected: a reversible/parked
  state modeled as a workflow status overwrites the `backlog` position the item returns to on
  reactivation (cross-tool anti-pattern), and would touch ≥8 scattered active-status tuples plus
  `TERMINAL_STATUSES` — disproportionate for a low-priority chore. (Note: a literal `status: deferred`
  already exists informally in the backlog and is already excluded from the groupings — this feature
  does not formalize it; it adds the orthogonal tag signal.)
- **Does NOT add a dedicated column** (ticket approach 2 / a Tags or Deferred-flag column).
  Considered: a column is more queryable and matches the `Blocked By` precedent, but it widens an
  already-8-column table and shifts the signal away from where a reader judges actionability. The
  inline Status-cell annotation is chosen because the only structured consumers read `index.json`
  (raw status, unaffected) and the only `index.md` reader is an LLM prose-read — so corrupting a
  machine-parsed Status token is not a real risk here (see Technical Constraints).
- **Does NOT change shared `is_item_ready`, `ready.py`, or overnight selection**. Machine-scan
  suppression (teaching `ready.py` / overnight to honor the `deferred` tag) is a deliberately-scoped
  follow-up; its correct durable form is also a local filter in the scan caller (as `ready.py`'s
  existing `--tag` filter demonstrates), so this scope does not bake in a shape the follow-up must tear
  out. The interim consequence (index hides the item; overnight may still select it) is documented in
  the Problem Statement and Edge Cases, with the tag-vs-status parking model as the operator workaround.
- **Does NOT add a dedicated `## Deferred` grouping section** to `index.md`. The annotated master-table
  row is the discoverability surface; a separate section is a possible future refinement.
- **Does NOT alter the `## In-Progress` or `## Warnings` sections**. Those are not "ready to pick up"
  surfaces; an in-progress or data-integrity-flagged item is out of this feature's scope.

## Edge Cases

- **Mis-cased / whitespace-padded tag (`Deferred`, ` deferred `)**: Fires — Req 1's match is
  `.strip().lower()`-normalized, so case and surrounding whitespace do not cause a silent miss.
- **Typo'd tag (`defered`, `parked`, `on-hold`)**: Does NOT fire (no normalization rescues a different
  string). This fails *open* — the item remains visible in the grouping exactly as today, no worse than
  the status quo; the convention doc (Req 8) is the mitigation.
- **Topical use of the tag** (an item *about* deferral incidentally tagged `deferred`): Would be
  suppressed/annotated as if parked. The convention is "the `deferred` tag means this item is parked";
  authors must not use it as a topic tag. (Req 8 documents this; the work ticket #272 itself, despite
  "deferred" in its title, carries no `tags:` line and so is unaffected.)
- **Deferred-tagged item also overnight-eligible** (`status: backlog`/`refined`, `research.md` +
  `spec.md` present): Hidden from the index grouping but still selectable by overnight (the documented
  interim divergence). Operator workaround: set a non-eligible `status` to fully park. Closed by the
  machine-scan follow-up.
- **Deferred-tagged item with unresolved blockers**: Suppressed from the grouping by the tag predicate
  regardless of blocker state; its table row still renders annotated.
- **Item at literal `status: deferred` with no `deferred` tag**: Already excluded from all groupings
  (its status is in no `eligible_statuses` set) and its Status cell already reads `deferred`. The
  annotation keys off the tag, so no `(deferred)` suffix is added — no double-signal.
- **Deferred-tagged item also at `status: in_progress`**: Left in `## In-Progress` (work underway);
  reconciling contradictory data is not this feature's job.
- **Item with empty/no `tags`**: Unchanged behavior — no annotation, no suppression.
- **Degraded index.md fallback read** (dev SKILL exit-1 path when `index.json` is missing): The
  fallback is an LLM reading the table prose; `backlog (deferred)` reads as human-intended ("backlog,
  deferred") and does not mis-route. The normal dev SKILL path branches on `status` from the
  `index.json`-derived child map, which keeps the raw value (Req 3) and is unaffected.

## Changes to Existing Behavior

- **MODIFIED**: `index.md` Status cell for a `deferred`-tagged item → renders `<status> (deferred)`.
- **MODIFIED**: `## Refined` and `## Backlog` groupings → exclude `deferred`-tagged items.
- **ADDED**: `deferred` becomes a recognized/reserved backlog tag convention (documented in
  `skills/backlog/references/schema.md`).
- **UNCHANGED (explicitly)**: `index.json` shape; overnight selection (`is_item_ready`); the dev/backlog
  SKILL normal path (reads `status` from `index.json`).

## Technical Constraints

- All logic is local to `cortex_command/backlog/generate_index.py`: the annotation in the table
  row-rendering path (~lines 230–234) and the deferred-tag-skip guard in the `## Refined` (lines
  244–254) and `## Backlog` (lines 258–268) loops. `is_item_ready` is untouched, so overnight selection
  (which calls the shared helper directly) is behaviorally unchanged.
- **Why the inline annotation is safe for consumers** (precise version of the consumer-stability
  argument): every *structured* consumer reads `index.json` — `ready.py`, `overnight/backlog.py:
  load_from_index`, `hooks/scan_lifecycle.py`, `build_epic_map.py` — and Req 3 keeps that artifact's
  `status` field a raw enum, so none of them sees the annotation. No code parses the `index.md` table
  at all (confirmed in research); the lone `index.md` reader is the `/cortex-core:dev` degraded
  fallback, which is an LLM prose-read that interprets `backlog (deferred)` correctly. The risk a
  compound Status cell would otherwise pose (breaking a string-equality parser) does not exist here
  because no such parser consumes `index.md`.
- `index.json` shape is frozen by the consumer-stability acceptance constraint above.
- No new events are emitted; `generate_index.py` is not a `bin/cortex-*` script and is outside the
  `cortex-check-parity` (W003) target set. The console script `cortex-generate-backlog-index` already
  has SKILL.md/docs wiring references.
- `item["tags"]` is available in `generate_md` — the record dict built by `collect_items` includes the
  parsed `tags` list (`generate_index.py:187`).

## Open Decisions

None. The design forks from research are resolved in this spec: inline annotation over a dedicated
column (justified by the consumer analysis in Technical Constraints — no machine-parsed index.md
consumer exists, so the single-source-of-truth concern that favors a column does not bind here);
drop-from-grouping over a separate `## Deferred` section; tag (case-insensitive) over body-marker;
index-view-only suppression with the machine-scan path as a scoped follow-up. Each is surfaced at
approval with its trade-off.

## Proposed ADR

None considered.
