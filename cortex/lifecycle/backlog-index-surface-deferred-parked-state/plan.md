# Plan: backlog-index-surface-deferred-parked-state

## Overview
Add a presentation-only `deferred`-tag signal to `cortex_command/backlog/generate_index.py`:
annotate a deferred-tagged item's Status cell as `<status> (deferred)` in the master table and
drop deferred-tagged items from the `## Refined` / `## Backlog` actionable groupings, leaving the
raw `status`, `index.json`, and the shared `is_item_ready` helper untouched. Pin the behavior with a
new test file and document the tag convention in the canonical backlog schema doc.

## Outline

### Phase 1: Deferred signal (tasks: 1)
**Goal**: A `deferred`-tagged item renders `<status> (deferred)` in the index.md master table, with
its raw `status` and `index.json` record unchanged.
**Checkpoint**: `generate_md` annotates a deferred-tagged item's Status cell while a non-deferred
control renders the bare status; `generate_json`/`index.json` output is unaffected by construction
(Task 1 touches neither `generate_json` nor `collect_items`), with Task 3 asserting the two
observable record fields (`status`, `tags`).

### Phase 2: Actionable suppression + regression guard (tasks: 2, 3, 4)
**Goal**: Deferred-tagged items are excluded from `## Refined` / `## Backlog`, the table row is
preserved, the convention is documented, and the whole feature plus the untouched shared modules are
pinned by tests.
**Checkpoint**: `just test` is green (new file collected, existing readiness/ready/overnight suites
still pass), the merge-base diff touches only `generate_index.py` under `cortex_command/`, and the
schema doc carries the `deferred`-tag note.

## Tasks

### Task 1: Add deferred predicate + Status-cell annotation
- **Files**: `cortex_command/backlog/generate_index.py`
- **What**: Introduce a module-level predicate `_is_deferred(item: dict) -> bool` that returns true
  iff some element of the item's parsed `item["tags"]` list equals `deferred` after `.strip().lower()`
  normalization (Req 1, whole-element match — compare with `==` on each normalized element, NOT
  substring `in`, so `deferred-feature-work` must NOT fire). Use it in the row-rendering loop (lines 226–234) to
  render the Status cell as `f"{item['status']} (deferred)"` when the predicate matches, else the bare
  `item['status']` as today (Req 2). The record's `status` value must NOT be mutated — the annotation
  is local to the rendered cell string only, so `generate_json` and `index.json` stay unchanged (Req 3).
- **Depends on**: none
- **Complexity**: simple
- **Context**: `item['tags']` is the parsed list already present on every record dict (built at
  `generate_index.py:187`, `"tags": _parse_inline_str_list(...)`). The row f-string is at lines
  230–234; derive the annotated status into a local (mirroring the existing `blocked_display` /
  `parent_display` / `spec_display` locals at 227–229) rather than inlining branch logic in the
  f-string. Place the predicate `_is_deferred` as a small module-level helper near the other parse
  helpers (`_parse_inline_str_list` at 63–71) so Task 2 can call it by name. Do NOT touch `generate_json`
  (lines 210–212) or `collect_items` (the `item['status']` field stays the raw enum).
- **Verification**: `python3 -c "from cortex_command.backlog.generate_index import generate_md; mk=lambda t:dict(id=1,title='T',status='backlog',priority='low',type='chore',tags=t,areas=[],blocked_by=[],parent=None,spec=None); yes=generate_md([mk(['Deferred'])],set(),set(),[mk(['Deferred'])]); no=generate_md([mk(['deferred-feature-work'])],set(),set(),[mk(['deferred-feature-work'])]); print('OK' if ('| backlog (deferred) |' in yes and '(deferred)' not in no) else 'FAIL')"` — pass if it prints `OK`. This pins BOTH Req 1 axes in the smoke gate: the case-insensitive `Deferred` positive AND the whole-element negative (`deferred-feature-work` must NOT annotate, so a substring regression prints `FAIL`). Durable coverage is in Task 3; this gate does not depend on the test file.
- **Status**: [ ] pending

### Task 2: Suppress deferred-tagged items from ## Refined and ## Backlog
- **Files**: `cortex_command/backlog/generate_index.py`
- **What**: In the `## Refined` grouping loop (lines 242–254) and the `## Backlog` grouping loop
  (lines 256–268), skip (`continue`) any item for which `_is_deferred(item)` (the module-level
  predicate added in Task 1) returns true, before the `is_item_ready` call (Req 4). The master-table row from Task 1 still renders for the item — only
  the actionable groupings exclude it (Req 5). `is_item_ready` / `readiness.py` are neither modified
  nor passed any new argument; the guard is a local `continue` in the generator's own loops.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Both loops already iterate `items` (dicts carrying `tags`) and conditionally append a
  `- **{id}** {title}` bullet. Add the deferred-skip guard alongside the existing status filters
  (`if item["status"] != "refined": continue` at 245; `if item["status"] not in (...): continue` at
  259). Call `_is_deferred(item)` — do not re-implement the tag check or its `.strip().lower()`
  whole-element normalization inline (a divergent inline copy risks a substring match that would
  over-fire on `deferred-feature-work`). Leave `## In-Progress`
  (270–274) and `## Warnings` (276–306) untouched (Non-Requirements: in-progress/warnings out of scope).
- **Verification**: `python3 -c "from cortex_command.backlog.generate_index import generate_md; mk=lambda i,t:dict(id=i,title='T',status='backlog',priority='low',type='chore',tags=t,areas=[],blocked_by=[],parent=None,spec=None); items=[mk(1,['deferred']),mk(2,['deferred-feature-work'])]; out=generate_md(items,set(),set(),items); seg=out.split('## Backlog')[1].split('## In-Progress')[0]; print('OK' if ('- **1**' not in seg and '- **2**' in seg and '| backlog (deferred) |' in out) else 'FAIL')"` — pass if it prints `OK` (the `deferred` item is absent from the `## Backlog` grouping yet still an annotated table row, while the whole-element-negative `deferred-feature-work` item is NOT suppressed). Durable coverage in Task 3.
- **Status**: [ ] pending

### Task 3: Pin behavior with a new test file
- **Files**: `tests/test_generate_backlog_index.py`
- **What**: Create the test file required by Req 7, covering Reqs 1–5 by building item-dict fixtures
  and asserting on `generate_md` / `generate_json` output: (a) a deferred-tagged `status: backlog`
  item, (b) a non-deferred ready `status: backlog` control, (c) a deferred-tagged `status: refined`
  item, (d) a `Deferred`-cased item, (e) a `deferred-feature-work`-tagged `status: backlog`
  whole-element negative control. Assertions: full rendered table row equality containing
  `| backlog (deferred) |` for (a) and `| backlog |` (no suffix) for (b) (Req 2); `(a)` absent as a
  `- **<id>**` bullet under `## Backlog` while `(b)` present (Req 4); `(c)` absent under `## Refined`
  (Req 4); `(d)` annotated + suppressed identically to a lowercase `deferred` item (Req 1 case-variant);
  `(e)` NOT annotated (its row contains `| backlog |` with no `(deferred)` suffix) AND NOT suppressed
  (appears as a `- **<id>**` bullet under `## Backlog`) — this pins Req 1's whole-element `==` match so
  a substring (`"deferred" in tag`) regression fails the suite; `(a)` id present in the table region
  (Req 5); `generate_json([...])` record for `(a)` has `record["status"] == "backlog"` and
  `"deferred" in record["tags"]` (Req 3).
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: Import the module directly — `from cortex_command.backlog import generate_index as
  _gen_index` then call `_gen_index.generate_md(items, active_ids, archive_ids, all_items)` and
  `_gen_index.generate_json(items)` (mirror the direct-import + dict-fixture style of
  `tests/test_select_overnight_batch.py`; use the renderer-output string-assertion style of
  `tests/test_backlog_ready_render.py`). Item dicts must carry the keys `generate_md` reads: `id`,
  `title`, `status`, `priority`, `type`, `tags`, `areas`, `blocked_by`, `parent`, `spec` (see the
  record shape at `generate_index.py:181–204`). `generate_md` signature:
  `generate_md(items: list[dict], active_ids: set, archive_ids: set, all_items: list[dict]) -> str`;
  `generate_json(items: list[dict]) -> str`. For the grouping assertions, pass the same dict in
  `all_items` so `is_item_ready` can resolve (empty `blocked_by` → ready). Use full-row equality (not
  bare substring) for the Status-cell assertions per Req 2.
- **Verification**: `just test` — pass if exit 0 (the new file is collected and its Req 1–5 assertions
  pass, and the existing `readiness.py` / `ready.py` / overnight-selection suites still pass, which is
  the durable Req 6 guarantee). AND `git diff --name-only "$(git merge-base HEAD main)" -- cortex_command/`
  lists `cortex_command/backlog/generate_index.py` as the sole `cortex_command/` entry (Req 6 boundary
  check; merge-base, not live `main` tip).
- **Status**: [ ] pending

### Task 4: Document the deferred-tag convention in the schema doc
- **Files**: `skills/backlog/references/schema.md`
- **What**: Add a note in the `tags`-field region of the canonical backlog schema doc stating that a
  `deferred` tag is recognized by the index generator as a parked-state signal — annotated in the
  master table as `<status> (deferred)` and excluded from the `## Refined` / `## Backlog` actionable
  groupings — and that it is an index-view flag only: it does NOT remove the item from overnight
  selection (set a non-eligible `status` to fully park) (Req 8). Edit the canonical source only; the
  `plugins/cortex-core/skills/backlog/references/schema.md` mirror regenerates via the pre-commit hook.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `skills/backlog/references/schema.md` is the canonical schema doc; locate the `tags`
  field description and append the note there (placement matters — Req 8 acceptance verifies the note
  is within the `tags` region, not merely present somewhere in the file). No new `bin/cortex-*` script
  is deployed, so the `cortex-check-parity` (W003) orphan check does not apply.
- **Verification**: `grep -c 'deferred' skills/backlog/references/schema.md` ≥ 1 AND a read confirms
  the note sits within the `tags`-field region (grep count alone does not prove placement, per Req 8).
- **Status**: [ ] pending

## Risks
- **Compound Status cell (`backlog (deferred)`) breaks a consumer**: Mitigated — research confirmed no
  code parses the `index.md` table positionally; every structured consumer reads `index.json` (raw
  status, unchanged by Req 3). The lone `index.md` reader is the `/cortex-core:dev` degraded-fallback
  (exit-1) path, an LLM prose-read of the table columns; `backlog (deferred)` in a table cell reads as
  human-intended. (Caveat surfaced in review: that fallback's prose still names a `## Ready` section
  the generator no longer emits — `dev/SKILL.md:145` — a pre-existing dev-SKILL vocabulary drift that
  is out of scope here and does not affect table-cell readability.) If a future machine consumer of
  `index.md` is introduced, this annotation would need revisiting.
- **`deferred` becomes a reserved magic string**: Accepted and mitigated by Req 8 (documented
  convention). A typo'd tag (`defered`, `parked`) fails open — item stays visible as today, no worse
  than status quo.
- **Index hides a deferred item that overnight can still select** (`status: backlog`/`refined` + tag):
  Deliberate, documented interim divergence (spec Problem Statement / Edge Cases) — but a genuine
  tool-internal inconsistency to name plainly, not bury: the autonomous overnight runner can pick up an
  item a human has marked parked, with no warning at selection time, because `is_item_ready` is
  untouched. The machine-scan follow-up (teaching `ready.py`/overnight to honor the tag) is explicitly
  out of scope. The operator workaround to also hide the item from overnight — set a non-eligible
  `status` — comes at a cost: it overwrites the `backlog` position the item auto-returns to on
  reactivation (the very anti-pattern the spec rejected for approach 3), which is precisely why the
  tag, not a status, is the default signal. An operator who needs reversible parking keeps the tag and
  accepts the overnight divergence.

## Acceptance
Regenerating `cortex/backlog/index.md` for a backlog containing a `deferred`-tagged `status: backlog`
item shows `backlog (deferred)` in that item's master-table row and omits it from the `## Backlog`
grouping, while a non-deferred ready control still appears under `## Backlog`; the item's `index.json`
record keeps `"status": "backlog"` with `"deferred"` in its `tags`; `just test` exits 0 with the new
`tests/test_generate_backlog_index.py` collected; and `skills/backlog/references/schema.md` documents
the `deferred`-tag convention as an index-view-only signal. By design the deferred-tagged item remains
selectable by the overnight runner (`is_item_ready` untouched) — the parked signal is index-view-only,
and this divergence is intentional and documented, not a defect. The only `cortex_command/` source file
changed is `generate_index.py`.
