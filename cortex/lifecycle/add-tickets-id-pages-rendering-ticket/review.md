# Review: add-tickets-id-pages-rendering-ticket — Stage 1 (Spec Compliance)

Reviewed the cumulative diff of six commits (`602ec26f..ef2fe2b7`, `cortex_command/dashboard/`) against `spec.md`'s 19 requirements, Non-Requirements, and Edge Cases. Cycle 1. Tier `moderate` / criticality `high` — Stage 1 only, per assignment; no Stage 2 code-quality pass performed.

Test baseline (given, not re-run): `just test` → 2492 passed, 1 failed (pre-existing, unrelated — `test_orchestrator_prompt_render.py::test_criticality_partition_uses_shared_reducer`, a stale citation from sibling commit f8ed220f, touches no dashboard file), 19 skipped, 1 xfailed. `tests-dashboard` passes in full (311 passed, 154 subtests).

## Requirements

| # | Requirement | Rating | Justification |
|---|---|---|---|
| 1 | Unrecognized angle-bracket tokens survive as literal text | PASS | `_TicketBodySanitizer.handle_starttag`/`handle_endtag` (`data.py:1263-1297`) literalize an attribute-free unrecognized tag via `escape(self.get_starttag_text())`. Verified live: rendering `cortex/lifecycle/<slug>/research.md` produces `cortex/lifecycle/&lt;slug&gt;/research.md`, not the old dropped form. |
| 2 | Tag filtering not weakened by req 1 | PASS | `git diff` of `test_data.py`'s `TestLoadTicketBody` shows zero removed/modified lines — only two new test methods appended. `test_raw_html_in_a_body_is_stripped_not_executed` (unmodified) still passes: `<img onerror=…>` and `<div onclick=…>` carry non-empty `attrs`, so `not attrs` is false and they still hit the drop path (`data.py:1267-1270`), never the literalize branch. |
| 3 | No double-escaping regression | PASS | Independently re-ran the plan's exact corpus check (ten largest `cortex/lifecycle/**/*.md`, `markdown.markdown(...) ` + `_sanitize_ticket_html`): 0 occurrences of `&amp;lt;`/`&amp;gt;`/`&amp;amp;`, and 8/10 files show non-zero `&lt;` (placeholders now surviving). |
| 4 | Placeholder-drop coverage asserted at data layer | PASS | `test_unrecognized_placeholder_tag_in_prose_is_escaped_not_dropped` and `test_unrecognized_placeholder_tag_in_a_fence_is_not_double_escaped` (`test_data.py:1684,1700`) are distinct methods, each asserting its own case independently. |
| 5 | Four test layers for new surfaces | PASS | Route smoke: `/tickets/1`, `/partials/ticket/1/artifact/spec` added to `PAGE_ROUTES`/`PARTIAL_ROUTES`; `test_missing_ticket_returns_404` added. Template/structural: `TestTicketPageBadgeStrip`, `TestTicketPageArtifactPanels`, `TestTicketPageEpicChildren`, `TestTicketPageBackendGate`, `TestTicketArtifactBackendGate` added in the `TestStructuralElements`/`TestBacklogPanelBackendGate` style. Composite-loader: `TestTicketPageDataLayer` (`test_data.py:1111`) covers found/fallback/archive-fallback/neither-key/stale-fallthrough/partial-kinds/unknown-kind/oversized/non-integer/epic paths. |
| 6 | `GET /tickets/{id}` 200/404 | PASS | `app.py:338-349`: `status_code = 404 if ticket is None else 200`, `TemplateResponse` not a raise — matches `session_detail`'s pattern. `test_missing_ticket_returns_404` covers the 404 arm. |
| 7 | Badge strip uses its own mapping, not `_BADGE_CLASS_MAP`/`_STATUS_ICON_MAP` | PASS | `patterns/backlog_badges.html` defines its own `status_class`/`priority_class`/`type_class` dicts (moved from `triage_board.html`, not copied from `app.py:83-107`). `app.py`'s `_BADGE_CLASS_MAP`/`_STATUS_ICON_MAP` are untouched by the diff and `ticket_page.html` imports only `patterns/backlog_badges.html`. |
| 8 | Body reuses `load_ticket_body`, no second render | PASS | `load_ticket_page` (`data.py:366-437`) calls `load_ticket_body(item_id, backlog_dir)` and embeds its return verbatim as `body`. It separately calls `_parse_frontmatter` for structured badge fields, which is frontmatter *parsing* for different fields, not a second body-strip/render implementation — matches the requirement's actual wording. |
| 9 | Two-key artifact join | PASS | `resolve_artifact_dir` (`data.py:254-308`): `spec:` parent tried first, then `lifecycle_slug` against both `lifecycle_dir/<slug>` and `lifecycle_dir/archive/<slug>`, each gated by `is_dir()` + `resolve()` + `is_relative_to()`. Independently re-measured against the live corpus: two-key resolves 291/455 vs. spec-only 263/455 (spec's own numbers, 286/259, were "at spec time" over a then-448-ticket corpus — the corpus has grown since, but the required inequality (two-key > spec-only) still holds). |
| 10 | No artifact render on unhashed load | PASS | `ticket_page.html`'s panels render only a `<p class="empty-state">loading {{ kind }}</p>` placeholder; `hx-trigger="toggle once from:closest details"` never fires without a `toggle` event. `test_page_renders_no_artifact_prose_before_expansion` asserts exactly one `ticket-prose` block (the body) exists pre-expansion. The hash-opening script (`body_extra` block) does nothing when `window.location.hash` is empty. |
| 11 | Both handlers plain `def` | PASS | `app.py:339` `def ticket_page(...)` and `app.py:516` `def ticket_artifact_partial(...)` — confirmed neither is `async def`, unlike every other handler in the file. |
| 12 | Artifact-specific size cap | PASS | `ARTIFACT_MAX_CHARS = 128_000` (`data.py:236`), distinct constant from `TICKET_BODY_MAX_CHARS`, docstring cites the measured corpus (median 19,166 / p99 51,068 / max 63,707). `load_ticket_artifact` sets `truncated` and the template shows a truncation notice — not silent. `test_oversized_artifact_is_truncated_and_flagged` covers it. |
| 13 | Both routes stand down under non-local backend | PASS | Both handlers call `resolve_backlog_backend(root)` before any filesystem read and short-circuit to `ticket = None` / `artifact = None` — no `load_ticket_page`/`load_ticket_artifact` call is made in the gated case, so genuinely "no filesystem read attempted" as the Edge Cases section requires. See note below on the *status code* returned in the gated case, which is a minor observation, not a requirement violation. |
| 14 | Epic children linkified | PASS | `ticket_page.html`: `<a href="/tickets/{{ child.id }}">`. `test_children_render_as_links` and `test_epic_children_resolved_for_an_epic` cover both loader and template. |
| 15 | Route registration order invariant | PASS (manual check, as specified — not machine-enforced) | `grep -n '@app.get('` over `app.py` shows: `/tickets/{item_id}` (line 338) precedes no literal `/tickets` route (none exists), and `/partials/ticket/{item_id}/artifact/{kind}` (line 516) is declared directly below `/partials/ticket/{item_id}` (line 494), after all thirteen literal `/partials/*` routes (371-484). Invariant holds. |
| 16 | Feature-card artifact links resolve | PASS | `feature_cards.html:226-228`: `backlog_id` → `/tickets/{{ feat.backlog_id }}`; `spec_path`/`plan_path` → `/tickets/{id}#spec`/`#plan` only when `backlog_id` is present, else rendered as an inert `<span>` (not a broken `<a>`). |
| 17 | Seed writes numeric `backlog_id` | PASS | `_FEATURE_BACKLOG_IDS` maps slugs to ints 1-5 (zeta stays `None`); `_feature_entry` takes `backlog_id` as a parameter and writes it verbatim. `TestFeatureBacklogIds` asserts int-or-None and that every int resolves to a written backlog filename. |
| 18 | Seed corpus exercises primary (`spec:`) artifact path | PASS | Backlog fixture #2 (`seed-feature-beta`) gains `spec: cortex/lifecycle/seed-feature-beta/spec.md` pointing at a real two-file directory (`research.md`, `spec.md`, no `review.md` — also covers "some kinds only"). `TestFeatureArtifactCompleteness` covers delta's four-kind set (the `lifecycle_slug` path); beta covers the `spec:` path but has no dedicated assertion in `test_seed.py` beyond the backlog_id test — acceptable, since Task 5's `test_spec_key_found_path` already covers the loader behavior against a synthetic corpus, and the ticket's own verification step (b) is a manual corpus grep, not a persisted test. |
| 19 | Board links out to the page | PASS | `triage_board.html`: `<p class="ticket-row__open"><a href="/tickets/{{ item_id }}">open ticket →</a></p>` added to the expanded area, not `<summary>`. `test_row_links_out_to_its_own_ticket_page` asserts exactly one href per row, matching that row's own id. |

**Overall: 19 PASS, 0 PARTIAL, 0 FAIL.**

## Deviations flagged for judgment

1. **Task 2: `ticket_row` signature simplification + test split.** Removing the four now-dead `status_class`/`priority_class`/`type_class`/`fallback_class` params is a correct, necessary consequence of moving those maps into the imported `backlog_badges.html` macros — both call sites were updated consistently, and this isn't scope creep since the maps had to leave the macro's caller-visible surface once they became a shared pattern. The test split (`test_rows_carry_no_navigation_affordance` → `test_summary_carries_no_navigation_affordance` + `test_row_links_out_to_its_own_ticket_page`) is not a coverage loss: the new positive-link test asserts the row's hrefs are *exactly* `[f"/tickets/{item_id}"]` across `row.find_all()`, which is a strictly stronger check than the old blanket "no navigation anywhere" assertion now that req 19 legitimately requires one link. Acceptable.

2. **Task 5: `"open"`/`"medium"` as absent-frontmatter defaults for status/priority.** Not required or forbidden by the spec text. It's inconsistent with the triage board's own fallback (`status or 'unknown'`, `priority or 'unset'`, `triage_board.html`) — the ticket page silently claims a definite state ("open"/"medium") for a ticket that has neither, where the board is explicit about not knowing. In the current corpus every backlog ticket carries both fields, so this is dead-code-in-practice, but if it ever fires it will misrepresent an unknown ticket as an open, medium-priority one rather than surfacing the gap. Minor; not a spec violation (no acceptance criterion addresses this), but worth aligning with the board's convention in a follow-up.

3. **Gated-backend status code (req 13, not explicitly specified).** `ticket_page`'s `status_code = 404 if ticket is None else 200` conflates "unknown id" with "non-local backend, can't tell" — both produce `ticket = None` and thus 404. Requirement 13 only requires "an unavailable state rather than raising," which is satisfied (the three-arm template correctly discriminates gated vs. not-found *content*), and no test or requirement mandates a distinct status code for the gated arm. Noting for awareness, not scoring as a failure.

4. **Minor Edge Case gap not covered by tests or spec text:** a self-closing unrecognized tag (`<slug />`, via `handle_startendtag`) is silently dropped rather than literalized — only `handle_starttag`/`handle_endtag` were extended, per the plan's explicit scoping. Not observed in the real corpus (the placeholder pattern is `<slug>`, not self-closing) and the plan scoped the fix to start/end tags only, so this is a deliberate, documented boundary rather than an oversight — flagging only for completeness.

## Non-Requirements check

- Converting the other sixteen `async def` routes: not done — confirmed only the two new handlers are `def`.
- Reaching the 28 orphaned lifecycle directories: not attempted.
- Slide-over/in-board artifact presentation: not added; board's existing expandable row is otherwise unchanged (only the link-out was added).
- A sanitizer dependency (nh3/etc.): not introduced; still the `HTMLParser`-based allowlist.
- Caching rendered artifacts: `load_ticket_artifact` re-resolves and re-renders per call, no cache.
- A nav-bar entry: `base.html` untouched, confirmed no nav addition.

No Non-Requirement was implemented anyway.

## Edge Cases check

All nine edge cases in spec.md are either directly tested (stale `spec:` fallthrough, neither-key, partial-kinds, oversized-truncated, non-integer id, fenced-code placeholder, frontmatter-only body) or verified by code inspection (non-local backend attempts no filesystem read; `feat.backlog_id is None` renders inert links, not broken ones). No unhandled edge case found.

## Requirements Drift

**State**: none

**Findings**: None. The implementation stays within `observability.md`'s existing Dashboard subsystem description (read-only, no database, in-memory cache only, the four polling loops unextended — the new routes are per-request/on-demand, not part of any polling loop) and within `project.md`'s existing "Dashboard" scope line. No new subsystem, external dependency, or write path is introduced. `glossary.md` is unrelated to this feature (training/cockpit terms only) and untouched.

Note (informational, not scored as drift against the three assigned docs): `docs/dashboard.md`, which owns the dashboard's panel/page inventory per `CLAUDE.md`, was not updated to mention the new `/tickets/{id}` page or artifact partial. That doc is outside this review's three-document scope, but it's worth a follow-up commit before the feature is considered fully documented.

**Update needed**: None.

## Verdict

{"verdict": "APPROVED", "cycle": 1, "issues": ["Task 5 defaults status to \"open\"/priority to \"medium\" on absent frontmatter, inconsistent with the triage board's \"unknown\"/\"unset\" fallback convention — currently unreachable against the real corpus but worth aligning in a follow-up.", "docs/dashboard.md (panel/page inventory owner) was not updated to document the new /tickets/{id} page and artifact partial — outside this review's three requirements documents but worth a follow-up commit."], "requirements_drift": "none"}
