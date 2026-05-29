# Research: Surface deferred/parked state in the generated backlog index.md

> Topic anchor (clarified intent): Make a deferred/parked backlog item distinguishable in the
> generated `cortex/backlog/index.md` — render a deferred signal in the table AND drop
> deferred-tagged items from the index's own ready/actionable groupings — so the index no longer
> presents parked work as actionable. Change stays **local to `generate_index.py`**; machine-scan
> suppression (`ready.py` / overnight selection honoring the tag) is a research-gated follow-up.

## Codebase Analysis

**Primary file:** `cortex_command/backlog/generate_index.py` (328 lines). Produces both
`cortex/backlog/index.json` (all active-item fields, O(1) index) and `cortex/backlog/index.md`
(human-facing summary table + grouped sections).

- **Frontmatter-only parsing.** `_parse_frontmatter` (lines 46–60) reads the `\A---\n…\n---` block
  into a flat `dict[str,str]`; `_parse_inline_str_list` (lines 63–71) parses `[a, b]` inline lists.
  **There is no body parser** — the generator never reads past the second `---`. (Rules out a
  `## Deferred` body-section signal without new parsing infra.)
- **index.json record** built at lines 181–204; **`tags` is already emitted** (line 187:
  `"tags": _parse_inline_str_list(fm.get("tags", "[]"))`). Status normalized at line 141; terminal
  items dropped (lines 152–153), so index.json holds active items only.
- **index.md table** (`generate_md`, lines 215–308). Header (lines 222–224):
  `| ID | Title | Status | Priority | Type | Blocked By | Parent | Spec |` — **no Tags column.**
  Per-row f-string at lines 226–234. Empty placeholder `—`; spec check `✓`.
- **Grouped sections** (actual headings: `## Refined`, `## Backlog`, `## In-Progress`, `## Warnings`
  — no literal "Ready to Implement"):
  - `## Refined` (lines 242–254): `if item["status"] != "refined": continue` → `is_item_ready(…, eligible_statuses={"refined"})` → append on ready.
  - `## Backlog` (lines 256–268): `if item["status"] not in ("backlog","open","blocked"): continue` → `is_item_ready(…, eligible_statuses={"backlog","open","blocked"})` → append on ready.
  - `## In-Progress` (lines 270–274): plain status filter `("in_progress","implementing","review","in-progress")`, no readiness call.

**Suppression seam — CONFIRMED.** `cortex_command/backlog/readiness.py:is_item_ready` (lines 89–95)
checks **only** (1) `item.status in eligible_statuses` and (2) `item.blocked_by` resolution — it
**never reads `item.tags`** (verified by full read). Each grouping loop already iterates `items`
(dicts carrying the parsed `tags` list) and appends conditionally, so a local
`if "deferred" in item["tags"]: continue` guard inside the `## Refined` / `## Backlog` loops
suppresses deferred-tagged items from those groupings **without touching `readiness.py`,
`ready.py`, or `overnight/backlog.py`**. The `SimpleNamespace(**item)` handed to `is_item_ready`
carries `tags` but the helper ignores it, so machine-scan selection is unaffected.

**Consumers — no positional index.md parser exists.**
- index.json readers: `cortex_command/backlog/ready.py` (`_item_payload`; also reads `tags` for
  `--tag` filtering, line ~317), `cortex_command/overnight/backlog.py:load_from_index` (deserializes
  `tags`, line 365; feeds `select_overnight_batch`), `cortex_command/hooks/scan_lifecycle.py`
  (`lifecycle_slug→status` map, fail-open), `cortex_command/backlog/build_epic_map.py`. None parse
  index.md.
- **index.md readers are prose-only:** `skills/backlog/SKILL.md` and `skills/dev/SKILL.md` read the
  grouped sections as text to answer "what's ready." **The `## Backlog` grouping IS the index-side
  "what's ready" surface** that `/cortex-core:dev` consumes — so dropping a deferred item from it
  directly satisfies "do not surface parked work as actionable" for the index consumer.
- Dashboard (`dashboard/data.py`) and morning report (`overnight/report.py`) **re-scan raw `*.md`
  files**, not index.*. No consumer breaks from adding a column or an inline cell annotation.

**Status-vocabulary surfaces (approach-3 cost).** A first-class `deferred` status would need adding
to ≥8 scattered active-status tuples: `generate_index.py:250,259,264,273`; `ready.py:64–70`
(`_ELIGIBLE_STATUSES`); `overnight/backlog.py:38–42` (`STATUSES`, `ELIGIBLE_STATUSES`);
`common.py:162–171` (`TERMINAL_STATUSES`); `overnight/plan.py:143–145` (`_TERMINAL`).
`normalize_status` (`common.py:736–770`) passes unknown values through unchanged
(`_STATUS_MAP.get(raw, raw)`) — so a new status survives but means nothing. (Unrelated:
`overnight/map_results.py:32` has its own `_TERMINAL_STATUSES = {"merged","failed","deferred"}` —
a *pipeline feature-result* namespace, NOT backlog status; do not conflate.)

**Tests.** No existing test calls `generate_md` or asserts on table/grouping content (only
`_parse_frontmatter` unit coverage). A **new test file** (e.g. `tests/test_generate_backlog_index.py`)
is required. Patterns to mirror: `tests/test_superseded_frontmatter_tolerance.py` (tmp_path +
direct import), `tests/test_select_overnight_batch.py` (`_write_index` / `monkeypatch.chdir`
fixtures), `tests/test_backlog_ready_render.py` (string-assertion on renderer output), and
`tests/test_backlog_ready_tag_filter.py` (pins `ready.py`'s local tag-filter — the sibling of this change).

## Web Research

**Dominant cross-tool convention: a reversible "deferred/parked/snoozed/on-hold" state is modeled
as an attribute/label/flag layered on an UNCHANGED status — never as a distinct workflow status.**

- **Jira** — statuses must map to one of three immutable categories (To Do / In Progress / Done);
  community guidance keeps deferred items in **To Do** and uses the **Flag** (self-loop transition,
  turns card yellow, status unchanged) for "paused/waiting." Won't-Fix/Deferred-as-terminal are
  modeled as **resolutions** on a single Done status, not as statuses.
- **Linear** — explicit split: **status = workflow progression**, **labels = cross-cutting tags**;
  Backlog is itself a status. **Snooze** is orthogonal to status — it hides the item from a
  view/queue and resurfaces it (a *visibility* mechanism, not a status mutation).
- **GitHub Projects** — `blocked`/`deferred` are **labels**; structured single-select fields add
  queryable metadata on top. Governing principle: **single source of truth** — track each fact in
  exactly one place.
- **GitLab** — "Deferred UX" is an explicit **label**.
- **Trello/Kanban** — either a **separate list/"Icebox" area** or a **label**; best practice keeps
  the icebox visually separate from the ready backlog.

**Anti-pattern (multiple independent sources): the dedicated "Blocked/On-Hold" status/column.**
Moving a card into a Blocked/On-Hold *status* destroys the information about where it actually is
and where it returns to. Recommended fix: **highlight in place** (flag/annotation), preserving the
underlying status. This is a direct argument against approach 3 — forcing `status: deferred` would
overwrite the `backlog` position the item must return to on reactivation.

**Markdown table convention.** Keep cells single-purpose; compound cells (`backlog (deferred)`)
conflate two orthogonal axes (lifecycle state vs activation state), which the single-source-of-truth
principle disfavors — but Markdown tables do not *break* from longer cell text (readability/semantics
tradeoff only). A dedicated column keeps each axis queryable but widens an already-8-column table.
Internal precedent worth noting: the table's existing **`Blocked By` column** already surfaces a
secondary state-modifier as its own column rather than folding it into Status.

## Requirements & Constraints

- **Backlog tooling is In Scope** (`project.md`: "Discovery and backlog are documented inline").
  Nothing in Out-of-Scope/Deferred bears on this (the project-level "Deferred" section is about
  file-state migration / cross-repo overnight — a naming coincidence only).
- **Schema defines no `deferred`/`parked` convention.** `skills/backlog/references/schema.md` status
  enum: `backlog | ready | refined | in_progress | implementing | review | complete | abandoned`;
  `tags` is free-form with no reserved values. So a `deferred` tag is a **new soft convention** this
  feature establishes.
- **Already-live undocumented statuses.** `index.md` already renders items at `status: deferred`
  (#156), `proposed` (#186), `archived` (#258). These pass `normalize_status` unchanged and are
  **already silently dropped** from the Refined/Backlog groupings (not in any `eligible_statuses`
  set) — but render no *signal*. The motivating case is different: `status: backlog` + `deferred`
  tag, which DOES land in `## Backlog`.
- **"Backlog status vocabulary" constraint** (`project.md`) governs **terminal** extensions only
  (mirror `common.py:TERMINAL_STATUSES` ↔ `overnight/plan.py:_TERMINAL` + a `normalize_status`
  entry). A `deferred` status is **non-terminal**, so this rule does **not** directly bind — but it
  signals the architectural expectation that approach 3 has a scattered, multi-place cost.
- **No parity / lifecycle-path / events-registry gate binds this edit.** `cortex-check-parity`
  (W003) targets only `bin/cortex-*` scripts, not `cortex_command/` modules; `generate_index.py` is
  not in the lifecycle "Required before editing" path list; `generate_index.py` emits no events.
  (Approach 3 *would* edit `common.py`, which IS lifecycle-required — another mark against it.) The
  console script `cortex-generate-backlog-index` already has SKILL.md/docs wiring references.
- **`index.json` consumer-stability is the binding acceptance constraint** (ticket lines 42/54/78).
  A table-only change (cell annotation or new column) needs **no index.json change**; approach 3
  would mutate the `status` field that `ready.py`/overnight read.
- If acceptance criteria are written as `grep -c "<token>"` Done-When checks, the token must resolve
  per `tests/test_backlog_grep_targets_resolve.py` — relevant only if the spec uses grep tokens.

## Tradeoffs & Alternatives

**Axis A — rendering mechanism.**
- **A1 — inline Status-cell annotation (`backlog (deferred)`):** lowest footprint; preserves the
  8-column table-shape contract every prose reader relies on; one expression at the row f-string;
  index.json `status` stays a pure enum (presentation-only annotation). Con: the rendered Status
  cell is no longer a pure enum echo (no consumer string-matches the *rendered* cell, so harmless).
- **A2 — dedicated column (Tags column or narrow Deferred flag):** cleanest separation; queryable;
  matches the `Blocked By` internal precedent and the single-source-of-truth prior art. Con: widens
  an already-8-column table (changes header + rule); a full Tags column adds noise to surface one bit.
- **A3 — first-class `deferred` status:** largest blast radius; overwrites the `backlog` position the
  item returns to; ripples into ≥8 status tuples + overnight selection. Prior-art anti-pattern.
  "Likely overkill" (ticket's own assessment).

**Axis B — signal source.**
- **B1 — frontmatter `deferred` tag (recommended):** already parsed, already in index.json, zero new
  schema/parsing; mirrors the motivating case and `ready.py`'s tag-as-control-signal pattern.
- **B2 — dedicated `deferred: true` field:** most explicit/type-checkable, but new schema surface
  (collect_items, index.json shape, `BacklogItem`, docs, create/update tooling) for a signal a tag
  already conveys.
- **B3 — `## Deferred` body-section marker:** matches half the motivating data but requires net-new
  body-parsing infra in a generator that today reads only frontmatter — brittle. B1 captures the
  motivating item without B3's cost.

**Axis C — suppression scope.**
- **C1 — local predicate in `generate_index.py` groupings (chosen scope):** blast radius one file;
  the `## Backlog` grouping IS the index "what's ready" surface, so this fully satisfies intent for
  the index consumer; architecturally identical to `ready.py`'s shipped, test-pinned local-tag-filter.
  `is_item_ready` untouched → overnight cannot regress.
- **C2 — change shared `is_item_ready`:** highest blast radius on the most load-bearing predicate;
  overnight depends on it; the ticket explicitly fences this off. Note: even the eventual machine-scan
  follow-up should be a *local filter in the scan caller* (as `ready.py` already does), not a shared-
  helper change — so C1 does not bake in a shape the follow-up must tear out.

**Recommended approach: A1 + B1 + C1** (with A1-vs-A2 flagged for spec, see Open Questions).
Annotate the Status cell inline, derived from a frontmatter `deferred` tag, and drop deferred-tagged
items from the `## Refined` / `## Backlog` grouping passes via a local predicate — leaving
`is_item_ready` and the `all_items` corpus untouched. Lowest complexity, highest pattern-alignment
(mirrors the test-pinned `ready.py` filter), negligible performance cost, and a clean solution
horizon (the follow-up extends the same layering rather than replacing it).

**Implementation guardrail for spec/plan:** the suppression is scoped to the actionable *grouping*
passes only — the deferred item's table row must STILL render (annotated) for grooming, and
index.json must keep emitting deferred-tagged items unchanged so no structured consumer regresses.

## Open Questions

- **Rendering mechanism: A1 inline cell annotation vs A2 dedicated column.** Genuine design fork —
  the Tradeoffs angle favors A1 (preserves the table-shape contract, lowest footprint); the Web/prior-
  art angle favors A2 (single-source-of-truth, queryable, mirrors the existing `Blocked By` column).
  *Deferred: resolved in Spec — the §4 interview will pick the rendering with the user, defaulting to
  A1 per "simpler wins" unless the user prefers a queryable column.*
- **Drop vs relocate in groupings.** Should a deferred-tagged item be silently dropped from
  `## Backlog`, or moved to a dedicated visible `## Deferred / Parked` section (the kanban "icebox as
  separate area" convention)? Silent drop is simplest; a separate section keeps the item discoverable
  in its grouped context. *Deferred: resolved in Spec — depends on the rendering choice above and the
  user's grooming preference.*
- **Signal source.** *Resolved inline: B1 — a frontmatter `deferred` tag.* Convergent across all
  angles (already parsed/emitted, matches the motivating case, no new infra, mirrors `ready.py`). No
  user input needed.
- **Suppression scope.** *Resolved inline: C1 — local predicate in `generate_index.py`.* Confirmed
  feasible without touching shared `is_item_ready`; machine-scan suppression remains a follow-up.
- **Interaction with literal `status: deferred` items.** A `status: deferred` item is already
  excluded from groupings and shows its status in the master table. *Resolved inline: the new signal
  keys off the `deferred` **tag**; literal `status: deferred` is orthogonal and already handled — the
  feature need not add a second signal for it, though the spec may choose to make the annotation also
  recognize the literal status for consistency.*
