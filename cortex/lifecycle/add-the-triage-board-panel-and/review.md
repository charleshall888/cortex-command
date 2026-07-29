# Review: add-the-triage-board-panel-and

Reviewed commits `465c5acd..f9f411a8` on `pipeline/add-the-triage-board-panel-and`
(5 feature commits + the plan commit). Files touched:
`cortex/backlog/412-*.md`, `cortex_command/dashboard/app.py`,
`templates/base.html`, `templates/triage_board.html`,
`tests/backlog_fixtures.py`, `tests/test_routes_smoke.py`,
`tests/test_templates.py`, plus `cortex/lifecycle/.../plan.md`.

Verification run in the worktree: `.venv/bin/pytest cortex_command/dashboard/tests/ -q`
→ **240 passed, 219 subtests passed**. `test_routes_smoke.py` alone exits 0.

## Stage 1: Spec Compliance

### R1: A `/partials/triage-board` route and panel exist and are smoke-tested
- **Expected**: Route in `app.py` following the `@app.get("/partials/<name>")` shape; fragment `templates/triage_board.html` with no `<section>` wrapper; `<section id="triage-board" hx-get="/partials/triage-board" hx-trigger="load, every 30s" hx-swap="morph">` in `base.html`. `"/partials/triage-board"` in `PARTIAL_ROUTES`; smoke test exits 0.
- **Actual**: `app.py:431-439` adds `triage_board()` returning `templates.TemplateResponse(request, "triage_board.html", {"request": request, "state": state})` — byte-identical in shape to the ten siblings. `base.html:2210-2214` registers the section with exactly the specified attribute set (plus `aria-label`/`aria-live`, matching `backlog-panel` at `:2205`). `grep -c '<section' triage_board.html` = 0, and `test_fragment_carries_no_section_wrapper` asserts it over all three render states. `test_routes_smoke.py:51` adds the route; the docstring/comment counts were updated ten → eleven. Smoke test: 15 passed, exit 0.
- **Verdict**: PASS
- **Notes**: The two extra ARIA attributes are convention-conforming, not scope creep — every polled section in `base.html` carries them.

### R2: The section is appended as `§ 11` and its label is emitted twice
- **Expected**: Multiset of `§ NN` labels across `templates/` = pre-change value + exactly two `§ 11`, one in `base.html`, one in `triage_board.html`. No renumbering.
- **Actual**: Measured the multiset on `main` and on `HEAD`. `main`: `§ 00`×1, `01`×4, `02`×3, `03`×2, `04`×2, `05`×2, `06`×2, `07`×2, `08`×2, `09`×1, `10`×2. `HEAD`: identical, plus `§ 11`×2 — `base.html:2211` and `triage_board.html:29`. No other label changed.
- **Verdict**: PASS

### R3: Board tests render against the real feed, never a hand-written snapshot dict
- **Expected**: ≥1 template test builds input by calling `ticket_feed.build_backlog_snapshot` over an on-disk fixture corpus, and asserts on rendered row content.
- **Actual**: `tests/backlog_fixtures.py` writes real markdown frontmatter under a caller-owned tmpdir and `_board_snapshot()` (`test_templates.py:537-556`) reads it back through `build_backlog_snapshot` with the production `parse_backlog_titles` scan. `grep -c 'build_backlog_snapshot' test_templates.py` = 2 (import + call). Every one of the ~20 board tests routes through it; assertions are on parsed element text (`test_epic_child_renders_title_and_status_text`, `test_ineligible_rows_display_their_reason`, …), not on "did not raise". No hand-built snapshot dict is used as a *substitute* — the only two direct mutations (`snapshot["epics"]["epics"]["not-an-id"]`, `{**snapshot, "stale": True}`) perturb a real snapshot to reach states the corpus cannot produce.
- **Verdict**: PASS
- **Notes**: The fixture writer encodes the non-obvious `collect_items` facts (id-from-filename, `blocked-by` vs `blocked_by`, inline-list-only parsing, the empty-lifecycle-tree requirement for frontmatter `lifecycle_phase` to be honored) in its module docstring. That is the right home for them.

### R4: Every active item reaches a row
- **Expected**: Row set is `snapshot["item_order"]`, not `ready`. A fixture with non-empty `ineligible` produces a row for every `item_order` id including each `ineligible` id, and each such row displays its `reason`.
- **Actual**: `triage_board.html:197` (epic rows) and `:224` (flat rows) both iterate `item_order`; `ready`/`ineligible` are used only as classifiers at `:95-97` and `:121`. `test_every_active_item_reaches_a_row` asserts `set(rows) == set(snapshot["item_order"])` and that every `ineligible` id is present; `test_ineligible_rows_display_their_reason` asserts each entry's `reason` string is inside that row's text. The fixture includes `#156` at `status: deferred`, reproducing the live `{"id": "156", "reason": "status: deferred", "kind": "status"}` case. `test_each_active_item_renders_exactly_one_row` additionally pins that the union of epic groups + flat list is a partition, not an overlap.
- **Verdict**: PASS

### R5: The epic map is read at `snapshot["epics"]["epics"]`
- **Expected**: One epic → exactly one epic section; no section titled or keyed `schema_version`.
- **Actual**: `triage_board.html:148` reads `snap['epics']['epics']`, guarded by the envelope's own presence. `test_one_epic_renders_one_section_and_no_schema_version` asserts `len(epic-group) == 1` and `assertNotIn("schema_version", html)`. `test_epic_with_zero_active_children_says_so` further pins `list(snapshot["epics"]["epics"]) == ["500"]`, so the envelope shape itself is asserted against the shipped builder.
- **Verdict**: PASS

### R6: Child ids are stringified before joining `items`
- **Expected**: A fixture epic with ≥1 child renders that child's title and status text; assertion on visible text.
- **Actual**: `triage_board.html:165` and `:194` both apply `child['id'] | string` before appending. `test_epic_child_renders_title_and_status_text` asserts `"Ticket feed"` and `"backlog"` are in the parsed text of row `411` — and does so via `cls.epic_rows`, which is scoped to the epic section rather than the document, so a child that renders blank under its epic but correctly in the flat list would still fail. That scoping is exactly the discrimination this requirement needs.
- **Verdict**: PASS

### R7: Per-row fields come from `items`, never from child records
- **Expected**: Every row resolves display fields through `snapshot["items"][str(id)]`. An epic child with `priority: high` + `tags: [deferred]` renders both. `lifecycle_phase: none` renders no phase; `lifecycle_phase: implement` renders `implement`.
- **Actual**: `ticket_row()` (`:73-134`) takes `record` as an argument and both call sites pass `snap_items.get(item_id, {})` (`:210`, `:236`) — no child record ever reaches the macro. `:94`/`:109` read `record.get('phase')`, never `lifecycle_phase`. `test_child_display_fields_come_from_the_items_map` asserts `"high"` and `"tag · deferred"` on child `411`'s row; `test_rows_read_normalized_phase_not_raw_lifecycle_phase` asserts `"phase · implement"` on `412` and `assertNotIn("phase", rows["300"].text)` for the `lifecycle_phase: none` item.
- **Verdict**: PASS
- **Notes**: `assertIn("high", child_row.text)` is a bare substring check that a token like `"highlight"` would satisfy. The badge-level form used elsewhere (`[b.text for b in _badges(row)]`) is stricter and would have been the tighter assertion. Cosmetic; the requirement is still genuinely exercised.

### R8: Grouping is presence-based, with no count threshold
- **Expected**: One section per epic id in the map listing its children; every non-child `item_order` id in one flat list below. 1-epic and 6-epic fixtures produce the same structural shape. `grep -cE '\| *(length|count) *[<>]=? *[0-9]'` = 0 over the template.
- **Actual**: `:186` loops the epic map unconditionally; `:223-226` builds `flat_ids` as `item_order` minus `child_ids`; the flat group at `:227-244` always renders. `test_grouping_shape_is_identical_at_one_and_six_epics` asserts `shape(1) == (1, 1)` and `shape(6) == (6, 1)`. `test_no_count_threshold_selects_the_layout` runs the specified regex over the template source → `[]`. I re-ran the acceptance grep directly: **0**.
- **Verdict**: PASS
- **Notes**: Epic items are themselves nobody's child, so an epic appears twice on screen — once as a group `<h3>` header and once as a row in the flat list. This is what R8's literal wording produces, is documented in the template comment at `:157-161`, is asserted by `test_unparented_items_land_in_the_flat_list`, and is what keeps disclosure element ids unique. Reported for awareness, not as a defect.

### R9: Backlog statuses map to existing `badge-*` classes through a template-local dict
- **Expected**: Template-local status→class map calling `badge(css_class=…, label=…)`. Every rendered badge carries `^badge-(red|amber|gray|green|blue|purple)$`; none contains `var(--`. No `badge(status=…)`.
- **Actual**: `:40-63` defines local `status_class` / `priority_class` / `type_class` / `fallback_class` maps, all valued to `badge-*` names. Every call site (`:87-90`) uses `badge(css_class=…, label=…)`; `grep` finds no `badge(status=` in the template. The macro (`patterns/badge.html`) emits `class="badge {{ css_class }}"` and skips the icon span when `status is None`, so the output is `class="badge badge-gray"`. All six class names are confirmed defined in `base.html`. `test_every_badge_uses_a_base_html_badge_class` walks every parsed badge span, requires a modifier matching the regex, and asserts no `var(--`.
- **Verdict**: PASS

### R10: Unrecognized status, type, and priority values render verbatim
- **Expected**: A fixture with `status: needs-triage`, `type: architecture`, `priority: contingent` renders all three strings visibly with a fallback badge class and no exception.
- **Actual**: Item `300` in `_BOARD_CORPUS` carries exactly those three values. Every lookup is `.get(value, fallback_class)` with the raw value passed as `label=`. `test_unknown_status_type_and_priority_render_verbatim` asserts each string is a rendered badge label and that its class matches the badge regex. `status: deferred` (item `156`) is separately covered by `test_status_deferred_renders_as_a_status_badge`.
- **Verdict**: PASS

### R11: Blocked state comes from `blocked_why` / `ineligible`, not from truthy `blocked_by`
- **Expected**: An item blocked only by a `status: complete` item renders not blocked; an item blocked by a non-terminal item renders blocked and displays the blocker's id and status as `#<ref> (<status>)`.
- **Actual**: `:82` sets `is_blocked = ineligible and ineligible.get('kind') == 'blocker'` — never `blocked_by` truthiness. `readiness.py:212-218` confirms `"blocker"` is the literal rejection value. `:128` renders `#{{ entry.ref }} ({{ entry.status or entry.kind }})`. `test_blocked_only_by_a_complete_item_is_not_blocked` pins `201` into `snapshot["ready"]` and asserts no `blocked` badge; `test_blocked_by_a_live_item_shows_the_blocker_id_and_status` asserts both the badge and the literal `"#411 (backlog)"` on `412`. `test_blocker_without_a_title_still_renders_id_and_status` covers the live `title: null` case via an archived blocker (title scan is non-recursive), asserting `"#502 (backlog)"`.
- **Verdict**: PASS
- **Notes**: Because `readiness.py` evaluates status ineligibility first, an item rejected on *status* that also has live blockers renders no `blocked` badge — its blockers still appear in the readiness detail block. Both of R11's acceptance conjuncts hold, and the behaviour is consistent with the partition's own precedence, so this is a narrowing worth knowing rather than a gap.

### R12: The two backlog deferral flags render distinctly
- **Expected**: `status: backlog` + `tags: [deferred]` appears in the ready set, shows the tag flag, shows no status badge reading `deferred`, and its markup contains no `badge-amber`.
- **Actual**: `:93` renders the tag flag as `<span class="phase-label">tag · deferred</span>` — no `badge-` prefix, so it cannot be confused with `alerts.py:81`'s run-outcome `deferred`. `deferred_status` reaches the status badge through the `status` value itself (`:87`) and gets a separate `<dt>deferral</dt>` row at `:124`. `test_tag_deferred_is_a_flag_not_a_badge` asserts `"700" in snapshot["ready"]`, the `"tag · deferred"` text, absence of `deferred` from the row's badge labels, and `assertNotIn("badge-amber", html)`.
- **Verdict**: PASS

### R13: Rows are non-navigational disclosures with ticket-derived ids
- **Expected**: `<details>`/`<summary>` rows with `id="ticket-{{ id }}"`, stable across an `item_order` reversal; no `href`, `hx-get`, `hx-push-url`, or `onclick` on any row element.
- **Actual**: `:83` emits `<details class="ticket-row" id="ticket-{{ item_id }}">` with `<summary class="card-row">` at `:84`; `base.html:2252` selects `details[id]` and keys `sessionStorage` on `d.id`, so the join holds. `test_row_ids_are_ticket_derived_and_survive_reordering` renders forward and reversed, asserts `id="ticket-412"` in both, asserts the id *sets* match, and — well done — guards the guard with `assertNotEqual(forward, backward)` so the test would fail if the reversal were a no-op. `test_rows_carry_no_navigation_affordance` walks every row and every descendant against all four attributes.
- **Verdict**: PASS

### R14: Never-polled, polled-and-empty, and stale are three distinct renders
- **Expected**: Three mutually different rendered strings; all three contain `§ 11`; no state self-hides.
- **Actual**: `snap is none` → `loading triage board` (`:141`, matching `base.html:2207`'s placeholder idiom); populated + empty `item_order` → `no active backlog items · corpus polled and empty` (`:180`); `stale` → the h2 tag `· stale` (`:136`) plus a `stale · frozen at {{ polled_ts | format_elapsed }}` span in the doc line (`:175`), using the frozen `polled_ts` rather than `last_updated`, exactly as the requirement's rationale demands. `test_three_states_render_three_different_strings` asserts `len(set(renders)) == 3`; `test_every_state_keeps_the_section_label` asserts `§ 11` in all three (line `:29` sits above every branch). Three further tests pin each state's distinguishing string and its absence from the others.
- **Verdict**: PASS

### R15: An epic with zero active children renders honestly
- **Expected**: A fixture with one epic and zero children renders that epic's section with an explicit "no active children" line — not an empty body, not a suppressed section.
- **Actual**: `:215-219` emits `<p class="empty-state">no active children</p>` in the `{% else %}` of `{% if epic_rows %}`; the section shell and its `0 active` count still render. `test_epic_with_zero_active_children_says_so` first asserts the feed really does seed the map (`list(snapshot["epics"]["epics"]) == ["500"]`) and then asserts the line inside the group's text.
- **Verdict**: PASS

### R16: The panel conforms to the dashboard's design system
- **Expected**: `grep -cE '#[0-9a-fA-F]{3,6}\b'` = 0, `grep -cE '(bg|text)-gray-'` = 0, `grep -cE 'style="[^"]*[0-9]+px'` = 0, `grep -c 'refresh · 30s'` ≥ 1 and inside the template's `stream-line` div.
- **Actual**: I ran all four greps against `triage_board.html`: **0 / 0 / 0 / 1**. The match sits at `:176`, inside the `.stream-line` div spanning `:169-177`, as the trailing `ml-auto` span — the `backlog_panel.html:28` shape verbatim, including the leading `doc · cortex/backlog/*.md frontmatter` span. `test_no_forbidden_design_patterns` and `test_doc_line_carries_the_refresh_cadence` encode the same checks, the latter over parsed elements rather than the raw string.
- **Verdict**: PASS
- **Notes**: The interactive half is explicitly routed to screenshot review by the requirement itself, and one thing that review should look at: five new class hooks — `ticket-row`, `epic-group`, `epic-head`, `flat-group`, `flat-head` — have no rules in `base.html`. In particular `base.html:1773-1774` scopes `list-style: none` and `::-webkit-details-marker { display: none }` to `summary.feature-row`, and the board's summaries use `summary.card-row`, so rows will likely show a native disclosure triangle *alongside* the template's own `▸` chevron at `:98`; and `details.ticket-row` inherits none of `details.feature-block`'s border/padding treatment (`:1775-1786`). Every string-level acceptance criterion passes, so this is a rendered-view observation for the screenshot pass, not a spec failure.

### R17: Reconcile #412's own record by appending, not deleting
- **Expected**: A `## Update — reconciled at spec time (#412)` section naming all five falsified claims plus the dropped strip; `title:` amended to drop the strip; `git diff` shows additions only outside the `title:` line; `grep -c 'landscape strip' cortex/backlog/412-*.md` = 0 outside the Update section.
- **Actual**: `cortex/backlog/412-…-landscape-strip.md:51` carries the exact heading. Items 1–5 name, in order: the 170/177 → measured-178/167 correction; #294's `status: complete` with the `report.py:924` / `:1341` consumer-side gates; the 2026-07-27 manifest entry and the 111-of-145 `--dry-run` incident window at `justfile:191`; the backlog-vs-lifecycle conflation of the "active/archive split" (8 active / 0 archived); and the #306:53 inversion with its joint-reconsideration clause. The `justfile:150-152` → `justfile:184` touch-point correction is appended below them, and the closing paragraph states the strip's removal with its four-part rationale. The diff is additions-only outside the one `title:` line (the sole other hunk line is the pre-existing final bullet, re-emitted only because the file previously had no trailing newline — content byte-identical). `grep -c 'landscape strip'` = **1**, at line 84, inside the Update section — so 0 outside it.
- **Verdict**: PASS
- **Notes**: The filename still contains `landscape-strip`. That is correct: `collect_items` derives the id from the filename, so renaming would be a gratuitous identity change, and the acceptance criterion is scoped to file content.

## Requirements Drift

**State**: detected
**Findings**:
- `docs/dashboard.md`'s panel inventory ("What It Shows", §§ 1–10, ending at `### 10. Backlog`) does not list the new § 11 Triage Board. `cortex/requirements/observability.md:29` explicitly names `docs/dashboard.md` as the owner of that inventory, so the requirement chain now points at a doc that is one panel behind.
- `cortex/requirements/observability.md:100` states "dashboard total refresh ≤ 7s". The new panel polls at 30s, extending an existing divergence (`backlog_panel.html`, `metrics_baseline.html`) to a third panel without the requirement being restated.

Both are deliberate: the spec's Non-Requirements section forbids editing `observability.md` and `docs/dashboard.md` and assigns the regather to #415, and Technical Constraints names the ≤7s conflict explicitly as input to that ticket. Recorded as observation only; no bearing on the verdict.

**Update needed**: `docs/dashboard.md` and `cortex/requirements/observability.md` — both owned by #415, not by this ticket.

## Stage 2: Code Quality

- **Naming conventions**: Consistent. The route handler name (`triage_board`), template filename, section id, and partial path all follow the ten existing partials. Template-local maps (`status_class`, `priority_class`, `type_class`, `fallback_class`) mirror `backlog_panel.html`'s `status_color` naming without inheriting its values. Fixture module names (`write_item`, `write_corpus`, `build_snapshot`) read as verbs and are unambiguous. Test helper names are private-prefixed and match the file's existing `_render_partial` / `_fake_request` style.

- **Error handling**: Correct for a Jinja fragment, and notably careful. Every snapshot key is read by subscript rather than dotted access — the template's own header comment explains why (`dict.items` would resolve to the bound method). Every collection read is `| default(…, true)`-guarded, so a schema-incomplete snapshot degrades to an empty group rather than raising. The epic-key join uses `snap_items.get(epic_key, {})` and renders the raw key on a miss, which is the explicitly-required improvement over `triage.py:263-265`'s whole-map-swallowing `except Exception`; `test_unjoinable_epic_key_renders_under_its_raw_key` proves the rest of the board survives. The fixture writer raises loudly (`KeyError` on missing id, `ValueError` on a multi-line frontmatter value) precisely where silence would produce a mysteriously empty snapshot — the right place to be strict.

- **Verification coverage**: The strongest part of this change. The whole suite passes (240 tests, 219 subtests, 10.2s) and I independently re-ran every grep-form acceptance criterion in R2, R8, R16 and R17 — all match. Three choices deserve specific credit: (1) the HTML parse into an `_Element` tree, so "this row shows its reason" is asserted about one element's content rather than about a substring of the document — the spec's own Technical Constraints warn that `grep -c` over rendered output is line-break-sensitive, and this sidesteps it; (2) `_row_map` being *scoped* to the epic section in `TestTriageBoardRows`, which is what makes the R6 stringification test actually discriminating; (3) `assertNotEqual(forward, backward)` in the row-identity test, which guards against the reversal being a no-op and thereby stops R13's test from passing vacuously for a positional id. The one soft spot is `assertIn("high", …)` noted under R7.

- **Pattern consistency**: High. The fragment opens with a `sec-num` label + `<h2>` + `phase-tag` count, then a `stream-line` doc line — the shape of `feature_cards.html` and `backlog_panel.html`. Disclosure rows follow `feature_cards.html:50-101`'s `<details id>`/`<summary>`/`feature-detail` structure. The `{% set _ = list.append(…) %}` accumulation idiom matches `backlog_panel.html`'s bucket loop. The stream-line living inside the populated branch rather than being rendered unconditionally also matches `backlog_panel.html:26-29`. The only divergence is the un-styled class hooks flagged under R16.

- **Scope discipline**: Clean. Exactly the files the spec's "Changes to Existing Behavior" section names, and nothing else. `ticket_feed.py`, `poller.py`, `triage.py`, `readiness.py`, `build_epic_map.py`, `_BADGE_CLASS_MAP`, `_STATUS_ICON_MAP` and the `badge()` macro are all untouched — I diffed the full branch to confirm. No `patterns/data-table.html`, no `/tickets/{id}` route, no row links, no landscape strip, no `lifecycle_landscape` field, no `index.json` write, no `conftest.py`, no `templates/__init__.py`. The `test_routes_smoke.py` edit is three lines and confined to the route list plus its two "ten" → "eleven" count references.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
