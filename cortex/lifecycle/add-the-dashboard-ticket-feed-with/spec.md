# Specification: add-the-dashboard-ticket-feed-with

> Epic reference: `cortex/research/dashboard-command-station/research.md` (parent #410) — background only, scoped to this ticket. Ticket-level research: `cortex/lifecycle/add-the-dashboard-ticket-feed-with/research.md`.

## Problem Statement

The dashboard re-reads the entire backlog every thirty seconds but retains only status counts and title strings, so no view can show a ticket's priority, epic, blockers, or deferral — that picture exists only in session commands that cost tokens every time they run. This builds the single in-memory snapshot of backlog truth that the triage board (#412) and ticket reader (#413) will consume, so status-checking moves out of token-metered sessions into a persistent surface. Because those two tickets consume it rather than re-derive it, **the snapshot's schema is the deliverable** (R4) — not merely the code that populates it.

It ships to consumer repos via `uv tool install`, so it must tolerate corpora unlike this one. The evidence base is honest about its limits: four sampled repos, all under one GitHub account and substantially one author, with structurally identical frontmatter (same field set, same ordering, same hyphenated `blocked-by` spelling). They establish a **scale delta** — 9 active items / 1 epic here versus 54 / 7 in `wild-light` — and an availability delta (`hall-dental` has no `cortex/backlog/` at all). They do **not** establish convention diversity; a stranger's repo could drift in ways none of these four exercise. The design compensates by refusing closed-set assumptions wherever a value originates in user-authored frontmatter.

## Phases

- **Phase 1: Render-safety prerequisite** — make `phase_label` safe for the `None` the feed will emit. The only Phase-2 blocker.
- **Phase 2: Ticket feed snapshot** — the schema, and the bulkheaded single-assignment population inside `_poll_slow`'s existing backend gate.
- **Phase 3: Record reconciliation** — correct the inert frontmatter key and reconcile #411's body. No code; no dependency either direction.

## Requirements

1. **`phase_label` tolerates `None`**: `cortex_command/phase_labels.py:16` is annotated `encoded_phase: str` and calls `.endswith()` unguarded; the feed emits a null phase for the majority of items (223/371 in `wild-light`). Accept `str | None` and return `""` for `None`, leaving every existing mapping — including the verbatim fallthrough for unrecognized strings — unchanged. Acceptance: `python3 -c "from cortex_command.phase_labels import phase_label; print(repr(phase_label(None)))"` prints `''` and exits 0; existing `tests/test_lifecycle_phase_parity.py` still passes. **Phase**: Render-safety prerequisite

2. **`DashboardState` gains one snapshot field**: `backlog_snapshot: dict | None = None`, mirroring the existing `metrics: dict | None = None` idiom (`poller.py:97`) rather than `field(default_factory=dict)` — `None` must remain distinguishable from "polled, empty" so a fresh consumer repo can render an honest never-polled state. Acceptance: `grep -c 'backlog_snapshot: dict | None = None' cortex_command/dashboard/poller.py` = 1. **Phase**: Ticket feed snapshot

3. **The snapshot's schema is pinned, versioned, and documented**: `#412` and `#413` must be implementable against this specification alone, without reading the merged implementation. Every imported helper publishes its own return shape (`build_epic_map`'s docstring gives a self-versioned envelope down to key-insertion order; `partition_ready` returns a typed `ReadinessPartition`); this ticket's own output gets the same treatment. Items are an **id-keyed dict** so `#413`'s "resolves one item from ticket-feed state" is O(1). Exact shape — string keys throughout, ids stringified:

   ```
   {
     "schema_version": "1",
     "polled_ts":   "<ISO8601 UTC>",   # written ONLY by _poll_slow; see R7
     "stale":       false,             # true when a caught fault retained a prior snapshot; see R7
     "items":       {"<id>": {<collect_items record>, "deferred_status": bool,
                              "deferred_tag": bool, "phase": "<str>|null"}},
     "item_order":  ["<id>", ...],     # collect_items' priority-then-id order, preserved
     "epics":       {<build_epic_map envelope verbatim>},
     "ready":       ["<id>", ...],
     "ineligible":  [{"id": "<id>", "reason": "<str>", "kind": "status"|"blocker"}],
     "blocked_why": {"<id>": [{"ref": "<str>", "kind": "internal"|"external"|"not_found",
                               "status": "<str>|null", "title": "<str>|null"}]},
     "active_ids":  [<int>, ...],
     "archive_ids": [<int>, ...],
     "counts":      {"active": <int>, "archived": <int>}
   }
   ```

   Acceptance: a test asserts `sorted(snapshot.keys())` equals the exact key list above, that `snapshot["schema_version"] == "1"`, and that for a fixture item every per-item key above is present; `snapshot["items"]["<id>"]` resolves by direct subscript with no iteration. **Phase**: Ticket feed snapshot

4. **The snapshot carries the active/archive split**: `collect_items` already returns `active_ids` and `archive_ids`; both reach the snapshot along with `counts`, per R3's schema. Without this, #412's landscape strip — whose Integration states it renders "the active/archive split the feed already computes" — has no source, and its author would discover the absence only after #411 unblocks it. Acceptance: on a corpus with a populated `cortex/lifecycle/archive/`, `snapshot["counts"]["archived"]` is non-zero and equals `len(snapshot["archive_ids"])`. **Phase**: Ticket feed snapshot

5. **The snapshot is computed as pure calls, then committed in exactly one assignment**: `collect_items` → `build_epic_map` → `partition_ready` → feed-layer joins all resolve to local values before any write to `state`. Acceptance, all three conjuncts: (a) `grep -c 'state\.backlog_snapshot' cortex_command/dashboard/poller.py` = 3 — the commit, the R6 `else` clear, and the R7 stale-marking read — with **no** occurrence followed by `.update(`, `[`, or preceded by `del `, so in-place mutation is excluded rather than merely uncounted; (b) a test forcing `build_epic_map` to raise asserts the pre-existing `state.backlog_snapshot` is retained with its `polled_ts` unchanged; (c) that same test asserts no partially-populated snapshot was ever observable. **Phase**: Ticket feed snapshot

6. **The non-local backend arm clears the snapshot**: `state.backlog_snapshot = None` in the `else` arm, matching the stand-down discipline at `poller.py:369-373` so a mid-session backend switch never leaves stale local data on screen. Acceptance: `TestPollSlowBackendGate` is extended to assert `state.backlog_snapshot is None` after a real poll iteration under both `none` and an external backend, having first been populated. **Phase**: Ticket feed snapshot

7. **A retained-on-fault snapshot is marked stale and rate-limits its own logging**: R5 deliberately retains the prior snapshot when the bulkhead catches a fault, but `DashboardState`'s only timestamp — `last_updated` — is written unconditionally every 2s by `_poll_state_files` (`poller.py:325`), a different loop, so it reads fresh while `backlog_snapshot` may have been frozen for days. On a caught fault, set `stale: true` and leave `polled_ts` at its last successful value; clear `stale` on the next success. Log the **first** fault of an episode at warning and suppress until recovery — at `_poll_slow`'s 30s cadence an unsuppressed persistent fault emits 2,880 lines/day, and no rotation is configured anywhere in `cortex_command/`. Acceptance: a test drives three consecutive failing cycles and asserts `snapshot["stale"] is True`, `polled_ts` unchanged across all three, and exactly **one** warning logged; a fourth, succeeding cycle asserts `stale` returns to `False` and `polled_ts` advances. **Phase**: Ticket feed snapshot

8. **The snapshot computation is bulkheaded**: it carries its own `try/except Exception` inside the backend gate. This is a **new pattern, not an inherited one** — `poller.py`'s only two nested handlers (`:135-144`, `:187-192`) and the sibling guard at `data.py:993-997` all catch narrowly and swallow silently, so the precedent supports nested isolation but not this catch breadth or its logging. It is justified on its own terms: `state.pipeline_dispatch`, `state.dispatch_details`, and `state.metrics` are assigned *after* the gate block (`poller.py:375-380`), so an unguarded raise anywhere inside the gate skips all three shipped panels. Acceptance: a test injecting a raising `collect_items` asserts that in the same cycle all three of those fields are still updated. **Phase**: Ticket feed snapshot

9. **`build_epic_map` is called with `strict_schema=False`**: its default `True` raises `SchemaVersionError` on any `schema_version` != `"1"` (`build_epic_map.py:126-133`), which would give consumers a permanently dead `_poll_slow` after any future schema bump. Acceptance: a fixture corpus containing an item with `schema_version: "2"` yields a populated snapshot with no raise and no warning. **Phase**: Ticket feed snapshot

10. **Readiness helpers receive attribute-access records**: `partition_ready`/`is_item_ready` read `item.status` etc. but `collect_items` returns plain dicts, raising `AttributeError` at `readiness.py:116` if passed directly. Use the established `SimpleNamespace(**rec)` bridge (`generate_index.py:242-256`). Acceptance: a poll cycle over the live corpus completes and `snapshot["ready"]` is non-empty, with no `AttributeError` logged. **Phase**: Ticket feed snapshot

11. **Readiness eligibility is imported from the scheduler, not re-encoded**: import `cortex_command/overnight/backlog.py`'s `ELIGIBLE_STATUSES` so the board's eligibility cannot drift from the scheduler that acts on it. Note for accuracy: that set also carries a dead member — `_STATUS_MAP` maps `"ready" → "refined"` and `collect_items` normalizes before returning, so `"ready"` can never match at `readiness.py:114`. The justification for importing it is **single-sourcing with the actor**, not superior hygiene; `generate_index.py:274`'s set has the same class of dead member and is rejected only because nothing acts on it. Acceptance: no status-string literal set appears in the new poller code — `grep -c '"refined"\|"implementing"' cortex_command/dashboard/poller.py` = 0. **Phase**: Ticket feed snapshot

12. **Deferral is exposed as two independent flags per item**, not one collapsed boolean: `deferred_status` (`status == "deferred"`) and `deferred_tag` (`deferred` in tags, matching `generate_index.py:74-76`'s case-normalized predicate). `partition_ready` never reads `.tags` — deliberately, per #272's shipped spec (Req 4/6: "readiness.py … not modified") — so a tag-deferred item at an eligible status legitimately lands in `ready` and the board must be able to badge that distinctly. Reimplement the one-line predicate at the feed layer; do not export `_is_deferred` and do not teach `partition_ready` tags. Acceptance: a fixture with `status: backlog` + `tags: [deferred]` yields `deferred_tag` true, `deferred_status` false, and its id appears in `snapshot["ready"]`. **Phase**: Ticket feed snapshot

13. **Blocked-why resolves ids to status *and* title, spanning terminal items**: every observed live blocker points at a terminal item, which `active_items` excludes, and `all_items` carries only `{id, status, uuid}`. Populate `blocked_why` per R3's schema, preserving `is_item_ready`'s three-way internal/external/not-found split (`readiness.py:133-167`) rather than collapsing to found/not-found. The id-keyed title map must come from the corpus pass that already opens every file for `parse_backlog_titles`; **a third full-corpus scan must not be added**. Acceptance: `grep -c 'glob("\[0-9\]\*-\*\.md")' cortex_command/dashboard/data.py` = 2 (unchanged from baseline — currently `data.py:989` and `:1049`); and a fixture where an active item is blocked by a `status: complete` item yields that blocker's title in `blocked_why`. **Phase**: Ticket feed snapshot

14. **`lifecycle_phase` null spellings collapse to one value, case-insensitively**: `_opt` (`generate_index.py:79-82`) case-folds only `null`, so `none` survives as the string `"none"` (4 items in `wild-light`) alongside Python `None` (5) and absent keys (223) — and `None`, `NONE`, `nil`, `~` would all survive too. Normalize against a case-insensitive null-token set (`null`, `none`, `nil`, `~`, empty, whitespace-only) to a single `null` phase. Out-of-vocabulary *non-null* phases (`wontfix` ×2 in `wild-light` and ×7 here, `closed` ×1) pass through verbatim by design — see Edge Cases. Acceptance: fixtures carrying `none`, `None`, `NONE`, `null`, `nil`, `~`, an empty value, and an absent key all produce the same `phase` value in the snapshot. **Phase**: Ticket feed snapshot

15. **The feed sits inside the existing backend gate, adding no new gate and no new poll task**: populated within `_poll_slow`'s `if backend == "cortex-backlog":` arm. Acceptance: `run_polling` still creates exactly four tasks — `grep -c 'create_task' cortex_command/dashboard/poller.py` = 4 (unchanged from baseline — currently `poller.py:414-417`). **Phase**: Ticket feed snapshot

16. **Correct the underscore blocker key**: `cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md:14` uses `blocked-by:` rather than `blocked_by:`. This is **not** justified by observed failure — the item is terminal and skipped before the key is read, so the correction is inert. It is included as a zero-cost correctness tidy riding an already-open ticket, not as evidence-bearing work; the front-door bar is met by the feed, not by this line. Acceptance: `grep -c '^blocked_by:' cortex/backlog/230-*.md` = 0 AND `grep -c '^blocked-by:' cortex/backlog/230-*.md` = 1. **Phase**: Record reconciliation

17. **Reconcile ticket #411 by appending, not deleting**: its Role, Integration, and Edges assert a "shared parse boundary" whose correction three readers inherit (false — six independent frontmatter parsers), a warn guard that will not be built, and a "reserved seed-ID range" position that was reversed. This repo's precedent for superseded claims is **append-and-preserve** — `f26c139` added an `## Update` section to #230 keeping the original as "real history … not retroactively invalidated", and `a0beb72a` likewise only added notes. Follow it: append a `## Update — reconciled at spec time (#411)` section stating what research falsified and what replaced it, leaving the original prose intact as the record of what was believed at authoring time. Separately, amend the frontmatter `title:` to drop `with upstream blocker-key hygiene`, which R16 reduces to one inert line. Acceptance: the ticket contains a `## Update — reconciled at spec time` heading whose body names all three falsified claims; the original Role/Integration/Edges text is byte-unchanged (`git diff` shows additions only, no deletions, outside the `title:` line); and `grep -c 'upstream blocker-key hygiene' cortex/backlog/411-*.md` = 0 outside that Update section. **Phase**: Record reconciliation

## Non-Requirements

- **No seed filtering of any kind.** No `_BACKLOG_UUIDS` import, no `dashboard-seed` tag filter, no 990–999 ID-range filter. The feed renders seed fixtures exactly as every other panel already does. Reversed from the Clarify-stage position on evidence; rationale in research.md Open Questions.
- **No corpus lint and no runtime warn guard.** A test in `tests/` is unreachable from consumer repos (not shipped in the wheel), and a runtime guard would fire in repos whose maintainer never sees the log — the same premise that R7's log-once rule now applies consistently to this ticket's own warnings.
- **No lifecycle-directory sweep status.** #412's Role names a three-way split — "active vs archived vs completed-but-unswept" — whose third term is `cortex/lifecycle/` directory sweep state. This pipeline is scoped to `cortex/backlog/` items and produces the backlog active/archive split only (R4). #412 must source the sweep story itself or drop it.
- **No change to any frontmatter parser**, and no attempt to unify the six independent implementations.
- **No changes to `collect_items`, `build_epic_map`, `partition_ready`, or `readiness.py` internals** — imported and adapted, never modified or re-encoded.
- **Never writes `index.json` or any other on-disk cache** from the read path.
- **No board, reader, or landscape views** — those are #412 and #413. This ticket produces state and its schema, not templates or routes.
- **Does not fix** `backlog_panel.html:64`'s `just backlog-index` reference (belongs to #415), `seed.py`'s unverified glob deletion in `clean_all`, or `_get_next_id`'s 990–999 boundary hole. All three are recorded in research.md.
- **Does not widen the frontmatter-quote allowlist.**
- **Does not retire `parse_backlog_counts`/`parse_backlog_titles`.** `parse_backlog_titles` is genuinely unservable by the feed (no titles for terminal items). `backlog_counts` is *technically* derivable from `all_items`, so the honest framing is retention for consistency, not impossibility.

## Edge Cases

- **Non-local backlog backend**: snapshot cleared to `None`; no local read attempted.
- **`cortex/backlog/` absent** (measured: `hall-dental`): `collect_items` returns empty tuples; snapshot is a populated, schema-complete structure with empty collections — not `None`.
- **`cortex/backlog/` present with zero numbered items** (measured: `Team-Builder-Bot`): same as above — distinct from "never polled".
- **`cortex/lifecycle/` absent**: every phase resolves null; no raise.
- **`cortex/lifecycle/archive/` absent** (measured: `gaggimate-barista`): guarded at `generate_index.py:117`; `archive_ids` is empty and `counts.archived` is 0 — distinct from a populated archive.
- **Permission-denied backlog file**: `collect_items` raises `PermissionError` (no per-file guard, unlike its sibling at `data.py:993-997`). The bulkhead catches it, the prior snapshot is retained and marked `stale: true`, the three post-gate panels still update, and one warning is logged for the episode (R7).
- **Non-UTF-8 backlog file**: raises `UnicodeDecodeError`, which is not an `OSError` subclass and so defeats even `parse_backlog_counts`' guard. Pre-existing; the bulkhead contains the feed's share and marks the snapshot stale.
- **Item with `schema_version: "2"`**: no raise (R9).
- **Out-of-vocabulary `lifecycle_phase`** (`wontfix`, `closed` observed): passes through verbatim and renders as its raw string via `phase_label`'s documented fallthrough. Deliberate — the phase vocabulary is open wherever the raw-frontmatter fallback path (`generate_index.py:176-184`) is taken, and inventing a display mapping here would be a closed-set assumption.
- **Unknown status / type / priority**: carried through raw; consumers supply a default branch. No `normalize_priority` exists.
- **Zero epics / zero blocked items**: `build_epic_map([])` and `partition_ready([], [])` degrade to empty containers by construction; no special-casing.
- **Blocker pointing at an archived item**: resolves through `all_items`, which spans the archive; `title` may be `null` — consumers render `blocked by #<id> (<status>)` rather than blank.
- **Malformed/unterminated frontmatter**: `_FRONTMATTER_RE` fails to match, the item is silently skipped (`generate_index.py:143-144`) — a silent under-count, not a crash. Accepted, unchanged.
- **Block-style YAML list** (`blocked-by:` then `  - 42`): `_parse_frontmatter` is line-oriented and silently yields `[]`, so blockers vanish. Zero live occurrences across all three populated corpora; recorded, not defended against.
- **Dashboard monitoring a remote project**: `_poll_state_files` re-targets to `state.overnight["project_root"]` (`poller.py:184-201`) but the feed uses the local root, so ticket phases will be local-only and may disagree with the fleet panel. Accepted and documented, not fixed.

## Changes to Existing Behavior

- **ADDED**: `DashboardState.backlog_snapshot` and its pinned schema — a new state surface, and a contract #412/#413 build against.
- **MODIFIED**: `_poll_slow` gains a bulkheaded computation inside its existing backend-gate arm; the block's cost roughly doubles (~15ms → ~25ms measured), reading the corpus a third time per 30s cycle.
- **MODIFIED**: `phase_label` accepts `str | None`; previously `str`-only and crashing on `None`.
- **MODIFIED**: `cortex/backlog/230-*.md:14` frontmatter key spelling — inert (the item is terminal and skipped before the key is read).
- **MODIFIED**: `cortex/backlog/411-*.md` — `title:` amended; body reconciled by appended `## Update` section, original prose preserved.

## Technical Constraints

- `observability.md:103` caps the dashboard at four asyncio polling tasks — the feed rides `_poll_slow`, no fifth loop.
- The never-write-the-index constraint rests on epic #410's Edges and the #321 precedent, **not** on `observability.md:102` (textually scoped to session state; the backlog corpus is not among the dashboard's listed inputs) and **not** on ADR-0011 (overnight-runner supervision, unrelated). No requirements-doc basis exists; the gap is recorded rather than papered over.
- Status, type, and priority vocabularies are documented as closed enums but are **open in practice** — `create_item.py:187-191` applies no `choices=` restriction. Observed beyond the documented enums: statuses `wontfix`, `superseded`, `done`, `wont-do`; types `task`, `needs-discovery`, `enhancement`, `game`; priorities `contingent`, `should-have`. All three fields are open; the snapshot carries raw values through.
- Coupling to `collect_items`' return shape is API-level with no schema-stability promise anywhere in the repo. Named, accepted — and the reason R3 pins this ticket's *own* output shape rather than propagating the same gap downstream.
- `partition_ready` is O(n·m) — `_build_status_lookup(all_items)` is rebuilt inside the per-item loop (`readiness.py:123`). 0.75ms at `wild-light`'s 54×371; ~75ms at 10× both. Recorded as a threshold, not addressed.
- `lru_cache(maxsize=128)` on `_detect_lifecycle_phase_inner` (`common.py:242`) is a hard cliff: measured 100% hits at N=100, **0%** at N=150. It is process-global and shared with the 2s loop, so crossing it also evicts that loop's working set. Both target repos sit at 1 and 3 items with on-disk lifecycle dirs — far below. Recorded, not engineered for.
- `collect_items` walks `archive/` and the existing panels do not — but R4 now surfaces that walk's output as `archive_ids`/`counts.archived`, so it is a consumed input rather than pure overhead.
- No logging configuration exists anywhere in `cortex_command/` — no `basicConfig`, `dictConfig`, or rotating handler. R7's log-once rule is the only volume control available.
- `cortex_command/dashboard/` is **not** lifecycle-gated (CLAUDE.md:27; #321 precedent).

## Open Decisions

None outstanding. Resolved at spec time: seed filtering and lint scope (operator decision), eligibility set and phase normalization (research recommendation), the remote-root divergence (explicit acceptance with documentation), and — surfaced by critical review rather than research — the snapshot schema, now pinned in R3, and the reconciliation method for #411, now append-and-preserve per R17.

## Proposed ADR

None considered.
