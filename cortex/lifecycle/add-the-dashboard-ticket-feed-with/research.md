# Research: Dashboard ticket feed with upstream blocker-key hygiene

> Ticket #411 (parent epic #410). Tier `complex`, criticality `high` — 8-agent cell (3 mandatory core + 4 orchestrator-chosen + adversarial last). Requirements loaded: `cortex/requirements/project.md`, `glossary.md`, `observability.md`. Clarify-critic: 12 findings (7 apply / 4 ask / 1 dismiss).

## Epic Reference

Discovery research for the parent epic lives at `cortex/research/dashboard-command-station/research.md` — background only, not reproduced here. This ticket is phase 1+2 of that epic's five-phase plan.

**Clarified intent.** Give the dashboard an in-memory snapshot of backlog truth (active items, epic map, readiness partition, deferred markers, blocked-why joins) inside `_poll_slow`'s existing backend-gated block, so command-station views read persistent zero-token state instead of re-deriving it in token-metered sessions; plus a one-line `blocked_by:` → `blocked-by:` correction in `cortex/backlog/230-*.md:14`.

**Hard constraint added by the operator mid-research (2026-07-21): consumer portability.** The dashboard ships to other repos via `uv tool install`. Nothing may hardcode cortex-command's shape. Five real consumer repos were sampled; this constraint reshaped several conclusions below and is the reason `wild-light` — not this repo — is the primary sizing sample.

## Corpus Measurements (five real repos, 2026-07-21)

| | cortex-command | wild-light | gaggimate-barista | Team-Builder-Bot | hall-dental |
|---|---|---|---|---|---|
| `cortex/backlog/` | 407 items | 371 items | ~40 items | dir, **0 items** | **absent** |
| `cortex/lifecycle/` | 178 dirs | 192 dirs | present | 5 entries | **absent** |
| `lifecycle/archive/` | present | present | **absent** | absent | absent |
| `index.json` | present | present | present | **absent** | absent |
| active items | 9 | **54** | — | 0 | 0 |
| open epics | 1 | **7** | — | — | — |
| active w/ blockers | 2 | **8** | — | — | — |

This repo is a poor sizing proxy: 9 active items against wild-light's 54, and 1 open epic against 7. Every UX judgment sized against this repo's near-empty board would be wrong. `Team-Builder-Bot` (dir present, zero items) and `hall-dental` (dir absent) are ready-made degradation fixtures for two distinct empty states.

**Cost.** `collect_items` ≈ 8.3–8.7ms on both large corpora; `build_epic_map` ≈ 3–13µs; `partition_ready` ≈ 0.12–0.44ms. The cost driver is **total corpus size, not active-item count** (~0.021ms/file, flat) — a repo with thousands of closed tickets pays the full scan every 30s. The existing `_poll_slow` body already costs ~15–16.5ms, so the feed roughly doubles the block to ~25ms: a 0.08% duty cycle over 30s. The event-loop-starvation objection is weaker than it appears — the block already blocks for 15ms today.

**Scaling.** ~0.22ms per active item *that has an on-disk lifecycle dir* (driven by reading `plan.md` + `events.log` content, not item count). N=300 → ~70ms, N=1000 → ~230ms. cortex-command has **1** such item; wild-light has **3**. `run_in_executor`/chunking is premature and fails the front-door evidence bar; record the threshold, don't build for it.

## Codebase Analysis

**Target.** `cortex_command/dashboard/poller.py` — `DashboardState` (`:62-119`) gains the snapshot field; `_poll_slow` (`:353-384`) populates it inside the existing `if backend == "cortex-backlog":` arm (`:364-373`). `cortex_command/dashboard/` is **not** lifecycle-gated (CLAUDE.md:27 omits it; #321 states it explicitly).

**Producer APIs.** `collect_items` / `build_epic_map` / `partition_ready` are pure reads; `atomic_write` fires only from `generate_index.py`'s `main()` (`:327-330`). `is_item_ready`/`partition_ready` are re-exported from `cortex_command/backlog/__init__.py:15-21`; **`build_epic_map` is not** — the feed would be its first in-process caller (its only current caller is its own CLI `main()`, fed from the on-disk `index.json`).

**Two adapters are mandatory, not optional:**
- `partition_ready`/`is_item_ready` use attribute access (`item.status`), but `collect_items` returns plain dicts — calling directly raises `AttributeError` at `readiness.py:116` (reproduced live). The established bridge is `SimpleNamespace(**rec)` (`generate_index.py:242-256`).
- `build_epic_map` must be called with **`strict_schema=False`**. Its default `True` raises `SchemaVersionError` on any `schema_version` != `"1"` (`build_epic_map.py:126-133`). That default exists for the CLI's exit-code contract; a read-only poller in a repo whose schema version it does not control has no business enforcing it. Left at `True`, a future schema bump gives consumers a permanently dead `_poll_slow`.

**In-process, no-disk-write precedent to mirror:** `ready.py:438-445` lazily imports `collect_items` and calls it in memory when `index.json` is missing, never regenerating the file.

**Backend gate (#321 precedent, `poller.py:360-373`)** resolves fresh every cycle, defaults toward `cortex-backlog` on degenerate input, and stands down to empty containers on non-local backends. The feed sits inside this same gate — no new gate. Note the `else:` arm must clear the snapshot; the existing `TestPollSlowBackendGate` spies only on `parse_backlog_counts`/`parse_backlog_titles` and will **not** catch the omission.

**Corpus-test pattern:** `tests/test_backlog_grep_targets_resolve.py` — helper + `tmp_path` positive/negative self-tests + a terminal live-corpus assertion. One file per lint, matching `test_adr_citation_audit.py` and `test_bare_python_import_lint.py`.

## Requirements & Constraints

**The governing authority is narrower than assumed.** `observability.md:102` ("read-only **with respect to session state files**") is textually scoped to session state, and the backlog corpus is not even listed among the dashboard's inputs (`:30`) — this clause does not reach the index question. ADR-0011 is about overnight-runner supervision, unrelated. #306's `untrack-backlog-index-cache` decision was a **git-tracking** decision, not a runtime-write prohibition. The real authority is ticket-level only: epic #410's Edges ("no index-cache writes from the read path") plus the #321 precedent. **No requirements-doc basis exists — record the gap rather than manufacture a citation.**

`observability.md` also contradicts itself (`:9` "first four subsystems" vs `:102` "All three"), and sibling #415 does **not** flag `:102`/`:103` as stale — so the spec cannot claim those clauses were vetted.

**Binding:** `observability.md:103` caps the dashboard at exactly 4 asyncio polling tasks (confirmed in `poller.py:401-417`) — the feed must ride `_poll_slow`, not add a 5th loop. ADR-0001 (no database). ADR-0016 (backend config-declared, never plugin-introspected, fails toward local). `project.md:21/23/25` (harness-policing machinery presumed deletable absent named evidence; the same test applies symmetrically to keeps).

**Vocabularies are documented-closed but open in practice.** `create_item.py:187-191` defines `--status`/`--type`/`--priority` as free-text argparse with **no `choices=`**. Live corpora already carry statuses `wontfix`(24) `superseded`(6) `done`(3) `deferred`(2) `wont-do`(1) and types `task`(8) `needs-discovery` `enhancement` `discovery`; wild-light adds `type: game`. `normalize_status` has no fallback bucket — unknown values pass through unchanged. **No `normalize_priority` exists at all.** Every display switch needs a default branch; `backlog_panel.html:50,56` and `app.py:178-185` are the existing "unknown → safe default" precedents.

## Consumer Portability

**Shipped consumer-hostility bugs found (pre-existing, not introduced here):**

1. **`phase_label` crashes on `None`.** `phase_labels.py:16-17` is annotated `encoded_phase: str` and calls `.endswith()` unguarded. `collect_items` emits `lifecycle_phase=None` for most items (223/371 in wild-light). A template using `item.lifecycle_phase | phase_label` yields an HTTP 500, not a degraded panel.
2. **`backlog_panel.html:64`** tells users to run `just backlog-index`, but `just` is not a dependency of `uv tool install cortex-command` and no consumer repo ships a justfile. Correct pointer: `cortex-generate-backlog-index`.
3. **`seed.py`'s `clean_all` step 8 (`:1221-1227`)** deletes `{990..994}-seed-*.md` by glob with **no content verification**, while steps 1–2 in the same function do verify a marker first. Defused for verb-generated tickets by `create_item.py:44`, but not against a hand-numbered file. Separate ticket.
4. **`_get_next_id`'s reservation has a boundary hole.** `create_item.py:44` excludes 990–999 from the `max(ids)` computation but not from *assignment*: at a highest real id of 989, `next_id` returns 990 — and since 990 is then excluded from the count, it returns 990 forever. Latent and distant; separate ticket.

**The `'none'` hazard, root-caused.** `_opt` (`generate_index.py:79-82`) maps only the literal `"null"` to `None` — there is no `"none"` branch. wild-light therefore carries 4 items whose `lifecycle_phase` is the **string** `"none"`, 5 that are Python `None`, and 223 with the key absent. A display layer must normalize `phase in (None, "none")` into one bucket; it cannot assume the source repo scrubbed this. The raw-frontmatter fallback path (`:176-184`) also lets **arbitrary** phase strings through unvalidated — observed: `"wontfix"` (9 across both repos), `"closed"` (1).

**Root divergence (consumer-specific, missed until adversarial).** `_poll_slow` receives `root` from `_resolve_user_project_root()`, but `_poll_state_files` deliberately re-targets to `state.overnight["project_root"]` (`poller.py:184-201`) when monitoring a *remote* project. A feed resolving `lifecycle_phase` against the local tree while the fleet panel resolves against a remote one shows wrong or absent phases with no signal.

**`collect_items` walks `archive/` (`:116-127`); the existing panels do not** (`parse_backlog_counts`/`parse_backlog_titles` glob non-recursively). That directory grows monotonically and is never displayed.

**Graceful degradation is already structural** — verified against real repos: missing `cortex/backlog/` returns empty tuples (`:107-108`); missing `cortex/lifecycle/` falls through via `lc_dir.is_dir()` returning False; missing `archive/` is guarded (`:117`); `build_epic_map([])`/`partition_ready([],[])` degrade by construction.

## Concurrency & Failure Domain

**Bulkhead is required, not stylistic.** Two claims settled the Web-vs-Concurrency contradiction:
- *"Place the feed last in the block"* protects nothing. `state.pipeline_dispatch`, `state.dispatch_details`, and `state.metrics` are assigned **after** the backend-gate block (`:375-380`), so a raise inside the gate skips all three regardless of ordering within it.
- *"Per-source isolation would be the first such code in the file"* is false. `poller.py:187-192` already carries an inner `try/except OSError: pass  # degrade gracefully to default` scoped to one source.

**Verified crash paths** (empirical, against real fixtures):

| Fault | `parse_backlog_counts` (shipped) | `collect_items` (proposed) |
|---|---|---|
| non-UTF-8 file | **raises** `UnicodeDecodeError` | **raises** `UnicodeDecodeError` |
| permission-denied file | survives (`try/except OSError`, `data.py:993-997`) | **raises** `PermissionError` |
| `schema_version: "2"` | n/a | `build_epic_map` **raises** unless `strict_schema=False` |

`collect_items` is **strictly less defensive than its sibling in the same loop** — it has no per-file guard at `generate_index.py:124,142`. A permission-denied file silently absorbed today would newly crash the whole cycle. Every one of these faults is deterministic and persistent: the failure recurs every 30s forever (~2,880 identical warnings/day). `UnicodeDecodeError` is not an `OSError` subclass, so it defeats even the sibling's guard — a pre-existing latent bug.

**Non-raising degradations:** malformed frontmatter → `fm={}`, item silently skipped (a silent under-count, not a crash); symlink loops → `Path.is_dir()` swallows `ELOOP`.

**Torn reads are exception-induced, not race-induced.** `_poll_slow`'s body is fully synchronous, so no handler can interleave *within* one iteration. But with several parallel `state.x =` writes, a raise after the first leaves fresh `items` paired with a stale `epic_map` — an id-referential graph pointing at absent entries, durable for 30s+. **Mitigation: compute all values as pure calls, then commit one snapshot object in a single assignment.** Any raise then leaves state wholly untouched. This is stricter than the `pipeline_dispatch`/`dispatch_details` precedent and justified by the tighter coupling.

**Cache cliff is a hard step function** (empirical): at N=100 distinct dirs a second pass is 100% hits; at N=150 it is **0%** — `lru_cache(maxsize=128)` on `_detect_lifecycle_phase_inner` (`common.py:242`) pins at 128 and a sequential full-corpus scan evicts every entry before revisiting. The cache is process-**global**, shared with `_poll_state_files`'s 2s loop, so crossing the cliff also evicts that loop's working set. Both repos are far below it (1 and 3 items).

**`partition_ready` is O(n·m):** `_build_status_lookup(all_items)` is rebuilt *inside* the per-item loop (`readiness.py:123`). 0.75ms at wild-light's 54×371; ~75ms at 10× both. A landmine with no guard, not a today-problem.

## Data Model & Display Joins

**Shape: one snapshot object, one assignment.** `DashboardState`'s existing convention is flat parallel dicts keyed by feature-slug, but those are independent per-slug facts; the items/epic-map/readiness triple is one joint derivation from one scan. `metrics: dict | None = None` (`poller.py:97`) is the in-file precedent for a wholesale single assignment, and `| None` additionally distinguishes "never polled" from "polled, empty" — a real distinction for a fresh consumer repo. #411's own Role already calls it "the single in-memory snapshot."

**Blocked-why cannot be served by the feed's own helpers.** Every observed live blocker points at a **terminal** item, which `active_items` excludes by definition; `all_items` carries only `{id, status, uuid}` — no title. `parse_backlog_titles` cannot fill the gap: it is keyed by `slugify(title)` for feature-slug matching, not numeric id, and does not recurse into `archive/`. **Recommendation:** emit an id-keyed title map from the scan that already opens every file, rather than adding a third full-corpus pass. Fall back to `"blocked by #<id> (<status>)"` when a title is unavailable — never blank. Preserve `is_item_ready`'s three-way ref split (internal / external / not-found, `readiness.py:133-167`); do not collapse to found/not-found.

**Deferred must stay two flags.** `partition_ready` never reads `.tags`, and that is deliberate — #272's shipped spec fenced it off (Req 4/6: "readiness.py … not modified"). So `tags:[deferred]` at an eligible status lands in `ready`, while `status: deferred` lands in `ineligible` with the literal reason `"status: deferred"`. Expose `deferred_status` and `deferred_tag` separately so the board can badge "ready but tag-deferred" — the exact case #272 documented as a known limitation. Reimplement the one-line predicate at the feed layer (mirroring `generate_index.py:74-76`); do not export `_is_deferred` (crosses a module #272 fenced) and do not teach `partition_ready` tags (contradicts a shipped spec).

**Epic children:** `build_epic_map` children carry `{id, spec, status, title}` (`:158-163`) — join `child.id → by_id[...]` for badges. Note a structural limit: fed `active_items`, a child that goes terminal **disappears** from its epic's children rather than rendering "done". #412 must take an explicit position.

**Badge map:** `_BADGE_CLASS_MAP` (`app.py:82-93`) is keyed on the overnight + pipeline-dispatch vocabularies, not backlog statuses. Reusing its `"deferred": "badge-amber"` entry would merge all three deferred meanings — exactly what #412's Edges forbid. A separate map plus an unknown-status fallback is needed; `patterns/badge.html:1`'s macro already accepts a `css_class` override (used ad hoc by `pipeline_panel.html:21`), so this is a one-line integration, not a template rewrite.

**Retained scans, honestly scoped.** `parse_backlog_titles` is genuinely unservable by the feed (no titles for terminal items; 398/401 lookups are terminal-only). But the blanket claim that *both* scans are unservable is **half-wrong**: `all_items` covers the full corpus with `{id, status}` and could derive `backlog_counts` exactly, modulo archive inclusion. The honest framing is that the block will read the same corpus **three times per cycle** (~25ms total) — name it under the efficiency-framing rule rather than foreclosing it with an inaccurate justification.

**Four eligible-status sets exist:** `overnight/backlog.py:42` and `ready.py:66-71` (both `backlog, ready, in_progress, implementing, refined`), `generate_index.py:258` (`{refined}`), `:274` (`{backlog, open, blocked}` — whose `open`/`blocked` members are dead post-`normalize_status`). Whichever the feed picks, its "ready" count will disagree with either `index.md` or `cortex-backlog-ready`, on a page whose stated purpose is being the single source of truth.

## Tradeoffs & Alternatives

**Rejected, with reasons:**
- **Read `index.json`** — gitignored cache with no auto-refresh hook (`ready.py`'s own `_check_stale_index` only *warns*); contains **only active items**, so blocker resolution against terminal ids regresses; absent entirely in a never-generated consumer repo (`Team-Builder-Bot`, `hall-dental`).
- **Per-request compute** — the `/sessions/{id}` precedent scans one session directory, not a 400-file corpus, and would multiply the scan per open browser tab. The Backlog panel is already documented at the 30s/≤32s tier, so no NFR pushes toward per-request freshness.
- **A 5th poll loop** — contradicts `observability.md:103`'s documented 4-task cap for no benefit; the data changes at human-edit cadence.
- **Subprocess the CLI verb** — process-spawn cost exceeds the ~9ms in-process call, and reintroduces a parse layer.

**Selected:** in-process import inside the existing gate, one snapshot object, own bulkhead `try`, `strict_schema=False`.

## Adversarial Review

Findings that survived verification and changed the design:

1. **Bulkhead adjudication** (§Concurrency) — both premises of the opposing recommendation were falsified against the code.
2. **`strict_schema=False` is non-negotiable** — otherwise a future schema bump kills `_poll_slow` permanently in consumer repos.
3. **The `#231` tag-collision claim (orchestrator's) was wrong.** #231 is `status: complete` → dropped at `generate_index.py:157` before tags are read. A bare `dashboard-seed` filter would **not** hide a live ticket today. Latent hazard, not observed failure — and under the front-door bar it does not justify machinery.
4. **`_BACKLOG_UUIDS` is the wrong constant.** It creates a *third* source of seed truth beside `create_item.py:44`'s range reservation and `seed.py:1221-1227`'s glob; inverts dependency direction (dev fixture-writer imported into the shipped hot loop); breaks when a user hand-copies a seed file (UUID travels, ticket silently vanishes); and is not contractual across versions — a future `seed.py` UUID change makes old on-disk seeds reappear.
5. **The corpus tripwire is structurally unreachable from consumer repos** — `tests/` is not in the wheel and consumers have no pytest surface. Its honest claim is "regression guard for *this* repo's corpus," not "upstream hygiene."
6. **Block-style YAML lists silently yield `[]`.** `_parse_frontmatter` is line-oriented; given `blocked-by:\n  - 42` it returns `''` → `[]`. Blockers and deferred markers vanish — the *same failure class* the ticket exists to fix, but broader, and reachable by any consumer who hand-edits frontmatter or runs a YAML formatter. Zero live occurrences in all three sampled corpora.
7. **No runtime warn guard — for a stronger reason than deletion bias.** A guard would fire in consumer repos where the maintainer cannot see the log and cannot act: harness-policing machinery shipped into someone else's repo, which the shipped-surfaces rule forbids outright.

## Open Questions

- **Should the feed filter seed fixtures at all?** — **RESOLVED (operator, 2026-07-21): no filter.** The feed renders seed fixtures exactly as every other panel already does. This reverses the Clarify-stage "exclude 990–994" answer on evidence that arrived later: the `#231` tag collision was wrong (terminal item, never reaches the tag read), no instance of seed pollution causing a problem was ever observed, and a filter on this panel alone would make two panels on one page disagree about the same corpus while destroying the fixture's value for developing that very board. Deletion bias puts the burden on adding the filter; nothing met it. **Consequence for the spec: no seed-identity mechanism ships — no `_BACKLOG_UUIDS` import, no tag filter, no ID-range filter.** If pollution ever becomes an observed problem, a filter earns its place then and should cover all backlog panels at once.
- **Which `eligible_statuses` set?** — Resolved by recommendation: `overnight/backlog.py`'s set (matches the scheduler that actually acts on readiness) and label the panel accordingly. Do **not** copy `generate_index.py:274`'s set verbatim — its `open`/`blocked` members are dead post-`normalize_status`.
- **Does the feed pass local or remote `lifecycle_dir`?** — Deferred to spec with a stated default: use the local tree and **document** that `lifecycle_phase` is local-only and wrong when monitoring a remote project, matching `_poll_state_files`'s divergence rather than silently inheriting it.
- **Is the hygiene half still worth its ticket framing?** — **RESOLVED (operator, 2026-07-21): land the one-line fix only; no lint ships.** The corpus tripwire is dropped entirely. Rationale: `tests/` is not in the wheel, so the test is structurally unreachable from any consumer repo and its only claim was guarding this repo's own corpus — too small to justify against the deletion-bias bar. The block-style YAML gap (Adversarial §6) is recorded here as a known, currently-unexercised failure mode with zero live occurrences across all three sampled corpora; it ships no machinery and is not deferred to a ticket. **Consequence for the spec: the entire hygiene half is one frontmatter edit to `cortex/backlog/230-*.md:14` — no test, no guard, no parse-boundary change.** Ticket #411's title and Why substantially overstate this and require correction.
- **Terminal epic children** — deferred to #412, which must take an explicit position on whether completed children render with a "done" badge or disappear.

## Considerations Addressed

- *Blocked-why density* — Addressed. Measured at both extremes: 2/9 here, 8/54 in wild-light. The join is real, not fixture-only; the board must be first-class at both densities, and the title gap (§Data Model) is the binding constraint, not the density.
- *No runtime warning path in the consumer-facing read surface* — Addressed and strengthened. Confirmed the corpus test adds no runtime path, and found the stronger argument: a guard in a shipped surface polices a repo whose maintainer never sees the log.
- *The false "shared parse boundary"* — Addressed. **Six** independent frontmatter parsers verified (`generate_index.py:46`, `resolve_item.py:76`, `load_parent_epic.py:113`, `overnight/backlog.py:232`, plus two hand-rolled regex scans at `dashboard/data.py:971,1028`). Nothing inherits anything. Ticket #411's Role, Integration, and Edges all require correction before implementation (Adversarial §6 of the dispatch summary).
