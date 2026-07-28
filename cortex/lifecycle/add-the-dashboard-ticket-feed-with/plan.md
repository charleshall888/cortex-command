# Plan: add-the-dashboard-ticket-feed-with

## Overview

Add one in-memory backlog snapshot to `DashboardState`, built by a new leaf module
(`cortex_command/dashboard/ticket_feed.py`) from the three existing producer helpers, and
committed inside `_poll_slow`'s existing backend gate in a single assignment guarded by its own
bulkhead. The snapshot's schema — not the code — is the deliverable that #412/#413 build against,
so it is pinned in a module docstring and asserted key-for-key by a test. Two decisions carry the
design: the builder is a **pure function** taking `backlog_dir`, `lifecycle_dir`, a caller-supplied
`polled_ts`, and the id→title map, so it is unit-testable without driving the async loop; and the
id→title map rides `parse_backlog_titles`' **existing** corpus pass rather than adding a fourth
scan. Phase 3 is a two-file record correction with no code and no dependency either direction.

**Architectural Pattern**: shared-state

## Outline

### Phase 1: Render-safety prerequisite (tasks: 1)
**Goal**: `phase_label` returns `""` for `None` so the snapshot's null phases cannot 500 a renderer.
**Checkpoint**: `phase_label(None)` returns `''`; every existing mapping, including the verbatim
fallthrough, is byte-unchanged.

### Phase 2: Ticket feed snapshot (tasks: 2, 3, 4)
**Goal**: `state.backlog_snapshot` carries the pinned schema, populated by one bulkheaded
single-assignment inside the existing backend gate, cleared on non-local backends, and marked
stale (log-once) on a caught fault.
**Checkpoint**: a real poll cycle over this repo's corpus yields a schema-complete snapshot with a
non-empty `ready` list; a raising producer leaves the prior snapshot intact, marks it `stale`, and
still updates `pipeline_dispatch` / `dispatch_details` / `metrics` in the same cycle.

### Phase 3: Record reconciliation (tasks: 5, 6)
**Goal**: correct the inert `blocked_by:` spelling in #230 and reconcile #411's falsified prose by
appending, not deleting.
**Checkpoint**: #230 carries the hyphenated key only; #411 carries an `## Update` section naming
all three falsified claims with its original Role/Integration/Edges text byte-unchanged.

## Tasks

### Task 1: Make `phase_label` tolerate `None`
- **Files**: `cortex_command/phase_labels.py`, `tests/test_phase_labels_none.py` (new)
- **What**: Widen the annotation to `encoded_phase: str | None` and return `""` for `None` before
  the first `.endswith()` call. Every existing branch — including the final verbatim fallthrough —
  stays unchanged. Satisfies R1.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `cortex_command/phase_labels.py:16` is annotated `str` and calls
  `encoded_phase.endswith("-paused")` unguarded at `:46`. The function is pure (no I/O) and its
  bash mirror lives in `hooks/cortex-scan-lifecycle.sh`; the parity test at
  `tests/test_lifecycle_phase_parity.py` covers the mapping table and must keep passing untouched —
  `None` has no bash counterpart, so the new case belongs in its own module, matching the repo's
  one-file-per-concern test convention. Second caller: `cortex_command.hooks.scan_lifecycle._phase_label`
  (delegating wrapper); registered as a Jinja filter in `cortex_command/dashboard/app.py`. Widening
  the accepted type is backward-compatible for both.
- **Verification**: `uv run python -c "from cortex_command.phase_labels import phase_label; print(repr(phase_label(None)))"`
  prints `''` and exits 0; `uv run pytest tests/test_phase_labels_none.py tests/test_lifecycle_phase_parity.py -q`
  passes.
- **Status**: [x] done (16b52d4c 2026-07-27T22:14:41-04:00)

### Task 2: Emit an id-keyed title map from the existing title scan
- **Files**: `cortex_command/dashboard/data.py`, `cortex_command/dashboard/poller.py`,
  `cortex_command/dashboard/tests/test_data.py`
- **What**: Change `parse_backlog_titles` to return a `BacklogTitles` NamedTuple with fields
  `by_slug: dict[str, str]` (today's return, unchanged semantics) and `by_id: dict[str, str]`
  (stringified item id → title), both built in the function's one existing pass. Update the single
  production caller to take `.by_slug`. Serves R13's title source without a fourth corpus scan.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `cortex_command/dashboard/data.py:1028` owns the pass; its glob is at `:1049` and
  `parse_backlog_counts`' at `:989` — R13 pins `grep -c 'glob("\[0-9\]\*-\*\.md")'` in this file at
  **2**, so the map must ride the existing loop, not a new one. The id is already in the filename
  (`[0-9]*-*.md`); extract it with the same `^(\d+)-` shape `generate_index.py:130` uses and key on
  the unpadded stringified form, matching R3's "ids stringified". The glob is non-recursive, so
  `archive/` is excluded by construction — that is the documented source of `blocked_why`'s
  `title: null` for archived blockers, not a defect. Caller enumeration (complete, grepped):
  `data.py:20` (module docstring line), `data.py:1028` (def), `poller.py:29` (import — name
  unchanged), `poller.py:368` (call site → `.by_slug`),
  `cortex_command/dashboard/tests/test_poller.py:231` (`mock.patch` target in the non-local arm,
  where the function is asserted *never called* and the `else` arm supplies `{}` — verified
  unaffected by the return-type change; the other two gate tests assert only on `backlog_counts`).
  `state.backlog_titles` template consumers (`feature_cards.html:47`,
  `escalations_panel.html:19`) keep receiving the slug map.
- **Verification**: `grep -c 'glob("\[0-9\]\*-\*\.md")' cortex_command/dashboard/data.py` = 2;
  `uv run pytest cortex_command/dashboard/tests/ -q` passes (whole-directory regression gate — a
  failure outside this task's Files is a blocker to surface, not to patch).
- **Status**: [x] done (65ebee59 2026-07-27T22:16:30-04:00)

### Task 3: Build the snapshot module and pin its schema
- **Files**: `cortex_command/dashboard/ticket_feed.py` (new),
  `cortex_command/dashboard/tests/test_ticket_feed.py` (new)
- **What**: Add `build_backlog_snapshot(backlog_dir, lifecycle_dir, titles_by_id, polled_ts)`
  returning R3's exact envelope, plus `mark_snapshot_stale(prior)` returning a shallow copy with
  `stale=True` (and `None` unchanged when `prior is None`). The module docstring publishes the
  schema verbatim — it is the artifact #412/#413 implement against. Satisfies R3, R4, R9, R10, R11,
  R12, R13, R14.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**:
  - **Producers**: `collect_items(backlog_dir, lifecycle_dir)` →
    `(active_items, active_ids, archive_ids, all_items)` (`generate_index.py:93-212`), active items
    already sorted priority-then-id. `build_epic_map(items, strict_schema=False)`
    (`cortex_command/backlog/build_epic_map.py:93`) — **not** re-exported from
    `cortex_command.backlog`, import the module directly; `strict_schema=False` is mandatory (R9),
    its `True` default raises `SchemaVersionError` at `:126-133`. `partition_ready(items, all_items,
    eligible_statuses=…)` → `ReadinessPartition(ready, ineligible)` where `ineligible` is
    `(item, reason, "status"|"blocker")` triples (`readiness.py:178-220`).
  - **Adapters (both mandatory)**: wrap every record passed to readiness helpers as
    `SimpleNamespace(**rec)` — the established bridge at `generate_index.py:242-256`; passing dicts
    raises `AttributeError` at `readiness.py:116` (R10).
  - **Eligibility (R11)**: `from cortex_command.overnight.backlog import ELIGIBLE_STATUSES` — no
    literal status set anywhere in this module. Measured at plan time: this import pulls
    `cortex_command/overnight/__init__.py`'s eager fan-out (orchestrator → pipeline →
    lifecycle.advance), ~60–200 ms once per process, and it **does** succeed with
    `claude_agent_sdk` absent — i.e. under a `cortex-command[dashboard]`-only install. That is the
    first dashboard→overnight coupling in the tree, so add the import-surface test below.
  - **Blocked-why (R13)**: reuse `readiness._build_status_lookup` (dual unpadded/padded/uuid keys,
    `:71-88`) and `readiness._looks_like_uuid` (`:50`) against the SimpleNamespace-wrapped
    `all_items` rather than re-encoding padding or UUID semantics. Per-ref classification mirrors
    `readiness.py:133-167`'s three-way split: resolved in the lookup → `internal`; unresolved and
    UUID-shaped → `not_found`; unresolved and non-digit/non-UUID → `external`. `title` comes from
    `titles_by_id` and is `None` when absent (archived blockers).
  - **Deferral (R12)**: two independent flags. `deferred_status` is `rec["status"] == "deferred"`;
    `deferred_tag` reimplements `generate_index.py:74-76`'s one-line case-normalized whole-element
    tag predicate at this layer — do not import `_is_deferred` and do not teach `partition_ready`
    tags (#272 fenced both).
  - **Phase normalization (R14)**: collapse `lifecycle_phase` to `None` when it is `None` or, after
    `.strip().lower()`, one of the null tokens `null`, `none`, `nil`, `~`, `""`. Every other value
    passes through verbatim — `wontfix`/`closed` are observed and deliberate (open vocabulary via
    `generate_index.py:176-184`). The raw `lifecycle_phase` stays in the record; `phase` is the
    normalized field R3 names.
  - **Purity**: `polled_ts` is a caller-supplied string, never stamped here — that is what keeps
    R3's "written ONLY by `_poll_slow`" true while leaving unit tests deterministic. `stale` is
    `False` on every fresh build.
  - **Degradation (no special-casing)**: absent `cortex/backlog/` → `collect_items` returns empty
    tuples at `generate_index.py:107-108`; absent `archive/` guarded at `:117`;
    `build_epic_map([])` / `partition_ready([], [])` degrade by construction. All yield a populated,
    schema-complete envelope with empty collections — never `None`.
  - **Tests** (`test_ticket_feed.py`, `tmp_path` fixture corpora): exact `sorted(keys())` equality
    against R3's key list; `schema_version == "1"`; every per-item key present; O(1)
    `snapshot["items"]["<id>"]` subscript with no iteration; a populated `archive/` giving non-zero
    `counts["archived"]` equal to `len(archive_ids)` (R4); an item with `schema_version: "2"`
    producing no raise and no warning (R9); `status: backlog` + `tags: [deferred]` yielding
    `deferred_tag` true / `deferred_status` false / id present in `ready` (R12); a `status: complete`
    blocker resolving to its title in `blocked_why` (R13); the eight phase spellings (`none`, `None`,
    `NONE`, `null`, `nil`, `~`, empty, absent) collapsing to one value (R14); and an import-surface
    test asserting this module imports with `claude_agent_sdk` blocked from `sys.modules`.
- **Verification**: `uv run pytest cortex_command/dashboard/tests/test_ticket_feed.py -q` passes;
  `grep -c '"refined"\|"implementing"\|"backlog"\|"in_progress"' cortex_command/dashboard/ticket_feed.py`
  = 0; and against this repo's **live** corpus (not a fixture),
  `uv run python -c "from pathlib import Path; from cortex_command.dashboard.ticket_feed import build_backlog_snapshot as b; s=b(Path('cortex/backlog'), Path('cortex/lifecycle'), {}, 'T'); print(sorted(s), len(s['items']), len(s['ready']))"`
  prints R3's key list, a non-zero item count, and a non-zero ready count, and exits 0.
- **Status**: [x] done (731b46de 2026-07-27T22:20:55-04:00)

### Task 4: Wire the snapshot into `_poll_slow` behind its own bulkhead
- **Files**: `cortex_command/dashboard/poller.py`, `cortex_command/dashboard/tests/test_poller.py`
- **What**: Add `backlog_snapshot: dict | None = None` to `DashboardState` (plus its docstring
  entry), and inside `_poll_slow`'s existing `if backend == "cortex-backlog":` arm compute the
  snapshot under its own `try/except Exception`, committing exactly one assignment; clear to `None`
  in the `else` arm; on a caught fault retain the prior snapshot marked stale and log the episode's
  first fault only. Satisfies R2, R5, R6, R7, R8, R15.
- **Depends on**: [1, 3]
- **Complexity**: complex
- **Context**:
  - **Shape (load-bearing for R5's grep)**: the arm computes into a local, then commits once —
    `snapshot = build_backlog_snapshot(...)` in the `try`; `snapshot = mark_snapshot_stale(state.backlog_snapshot)`
    in the `except`; a single `state.backlog_snapshot = snapshot` after the handler but still inside
    the local arm; `state.backlog_snapshot = None` in the `else`. That is exactly **three**
    `state.backlog_snapshot` occurrences, none followed by `.update(` or `[` and none preceded by
    `del ` — the R5(a) conjunct. Both `_poll_slow` dirs already exist at `poller.py:354-355`;
    `polled_ts` comes from the file's own `_now_iso()` (`:55-57`). The `DashboardState` docstring
    entry must describe the field without repeating the literal string
    `backlog_snapshot: dict | None = None`, which R2 pins at exactly one occurrence in the file.
  - **Bulkhead placement (R8)**: the `try` sits *inside* the backend gate, not around it.
    `state.pipeline_dispatch`, `state.dispatch_details`, and `state.metrics` are assigned after the
    gate block at `:375-380`, so an unguarded raise inside the gate skips all three regardless of
    ordering within it. The catch breadth (`Exception`) is wider than the file's two existing nested
    handlers (`:135-144`, `:187-192`, both narrow-and-silent) — a deliberate new pattern, justified
    by those three shipped panels.
  - **Log-once (R7)**: a `feed_fault_logged` flag local to `_poll_slow`, initialized before
    `while True:` and reset to `False` on each successful build. Chosen over a second
    `DashboardState` field (R2 grants exactly one) and over deriving suppression from
    `prior["stale"]`, which cannot suppress when no successful poll has ever occurred (`prior is
    None`, so nothing carries the episode). At 30 s an unsuppressed persistent fault emits ~2,880
    lines/day and no rotation is configured anywhere in `cortex_command/`.
  - **Title map**: `state.backlog_titles, titles_by_id = ...` is not the shape — Task 2 returns a
    NamedTuple; assign `.by_slug` to state and pass `.by_id` to the builder. `parse_backlog_titles`
    stays *outside* the bulkhead: its failure modes are pre-existing and already owned by the outer
    handler, and moving it inside would silently widen this ticket's blast-radius claim.
  - **Tests** (extend `test_poller.py`, reusing `TestPollSlowBackendGate._run_one_cycle` at
    `:207-224`): extend the backend-gate test to populate `state.backlog_snapshot` first, then
    assert it is `None` after a real cycle under both `none` and an external backend (R6 — the
    existing spies would not catch the omission); a raising `build_epic_map` leaving the prior
    snapshot object and its `polled_ts` intact and never exposing a partial value (R5 b/c); a
    raising `collect_items` still leaving `pipeline_dispatch`, `dispatch_details`, and `metrics`
    updated in the same cycle (R8); three consecutive failing cycles yielding `stale is True`,
    unchanged `polled_ts`, and exactly one warning under `assertLogs`, with a fourth succeeding
    cycle returning `stale` to `False` and advancing `polled_ts` (R7 — drive multiple cycles by
    patching `cortex_command.dashboard.poller.asyncio.sleep`).
  - **Non-goals here**: no fifth poll task, no new gate, no template or route work.
- **Verification**: `uv run pytest cortex_command/dashboard/tests/ -q` passes;
  `grep -c 'state\.backlog_snapshot' cortex_command/dashboard/poller.py` = 3;
  `grep -c 'backlog_snapshot: dict | None = None' cortex_command/dashboard/poller.py` = 1;
  `grep -c 'create_task' cortex_command/dashboard/poller.py` = 4;
  `grep -c '"refined"\|"implementing"' cortex_command/dashboard/poller.py` = 0.
- **Status**: [x] done (7da75de9 2026-07-27T22:30:27-04:00)

### Task 5: Correct #230's blocker-key spelling
- **Files**: `cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md`
- **What**: Change frontmatter line 14 from `blocked_by: [228]` to `blocked-by: [228]`, the spelling
  every reader keys on. Satisfies R16.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Readers key on the hyphenated form — `generate_index.py:197`
  (`fm.get("blocked-by", "[]")`) and `overnight/backlog.py:328` (same). The item is
  `status: complete`, dropped at `generate_index.py:157` before the key is read, so the correction
  is **inert** by design: a zero-cost tidy riding an already-open ticket, not evidence-bearing work.
  Note R16's prose transposes the two spellings; its acceptance greps, the ticket's own Why, and the
  two readers above all agree on underscore → hyphen, which is what this task does.
- **Verification**: `grep -c '^blocked_by:' cortex/backlog/230-*.md` = 0 AND
  `grep -c '^blocked-by:' cortex/backlog/230-*.md` = 1.
- **Status**: [x] done (cf42a9f4 2026-07-27T22:16:43-04:00)

### Task 6: Reconcile ticket #411's falsified claims by appending
- **Files**: `cortex/backlog/411-add-the-dashboard-ticket-feed-with-upstream-blocker-key-hygiene.md`
- **What**: Amend the frontmatter `title:` to drop `with upstream blocker-key hygiene`, and append a
  `## Update — reconciled at spec time (#411)` section naming the three claims research falsified
  and what replaced each. Leave Role, Integration, and Edges byte-unchanged. Satisfies R17.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The three falsified claims, all to be named in the Update body: (1) the "shared parse
  boundary" whose correction three readers inherit — research verified **six** independent
  frontmatter parsers (`generate_index.py:46`, `resolve_item.py:76`, `load_parent_epic.py:113`,
  `overnight/backlog.py:232`, and two hand-rolled regex scans at `dashboard/data.py:971,1028`);
  nothing inherits anything; (2) the warn guard on unrecognized blocker-key variants — not built, a
  runtime guard in a shipped surface polices a repo whose maintainer never sees the log; (3) the
  "explicit position on the reserved seed-ID range" — reversed by operator decision on 2026-07-21 to
  **no filter of any kind**. Precedent for superseded claims is append-and-preserve: `f26c139` added
  an `## Update` section to #230 keeping the original as "real history … not retroactively
  invalidated", and `a0beb72a` likewise only added notes. The filename is unchanged — only the
  frontmatter `title:` value moves. Do not quote the phrase `upstream blocker-key hygiene` inside
  the Update body; describe the amendment without reproducing it, so the R17 grep is a plain zero.
- **Verification**: `git diff -U0 -- cortex/backlog/411-*.md | grep -c '^-[^-]'` = 1 (only the
  `title:` line is removed; every other change is an addition);
  `grep -c 'upstream blocker-key hygiene' cortex/backlog/411-*.md` = 0; and
  `grep -c '^## Update — reconciled at spec time' cortex/backlog/411-*.md` = 1.
- **Status**: [x] done (0a48668e 2026-07-27T22:17:45-04:00)

## Risks

- **First dashboard→overnight import coupling (Task 3).** R11 mandates importing
  `ELIGIBLE_STATUSES` from `cortex_command/overnight/backlog.py`, which triggers
  `cortex_command/overnight/__init__.py`'s eager orchestrator fan-out. Measured at plan time: it
  imports cleanly with `claude_agent_sdk` blocked (so a `[dashboard]`-only install is fine today)
  and costs ~60–200 ms once at startup. The exposure is future-tense — a module-scope
  `claude_agent_sdk` import added anywhere in that chain would break dashboard-only installs. I add
  one import-surface test in Task 3 to catch that in this repo's CI. It is the only piece of this
  plan not traceable to a spec requirement, and it is cheap to strike if you'd rather accept the
  exposure than ship a test the Non-Requirements' reasoning arguably reaches.
- **`parse_backlog_titles` changes return type (Task 2).** A NamedTuple keeps the name honest and
  the diff to three files, but it is a signature change to a function the spec never asked to
  touch. The alternative — a second function — would add a fourth corpus scan, which R13 forbids;
  renaming to `scan_backlog_titles` would be more honest still but adds churn for no behavior.
- **Log-once state is a loop-local, not a `DashboardState` field (Task 4).** Deriving suppression
  from the retained snapshot's own `stale` flag would be more elegant but cannot suppress the case
  where no poll has *ever* succeeded, which is exactly the consumer-repo case R7 exists for.
- **Graph depth (3 levels, 6 tasks) sits at the restructure signal.** It is real, not padding: the
  chain is contract (2) → builder (3) → wiring (4), and both 3 and 4 are `complex`, so neither
  should share a wave with the simple tasks. The four independent tasks are batched at level 1.
- **Not addressed, per Non-Requirements**: `backlog_panel.html:64`'s `just backlog-index` pointer
  (#415), `seed.py`'s unverified glob deletion, `_get_next_id`'s 990–999 boundary hole, the
  block-style-YAML blocker gap (zero live occurrences), and the local-vs-remote-root phase
  divergence (documented, not fixed).

## Acceptance

A dashboard poll over this repo's live corpus produces `state.backlog_snapshot` matching R3's key
set exactly, with a non-empty `ready`, no `AttributeError` logged, and at least one terminal blocker
resolved to a real title in `blocked_why`. A non-local backlog backend clears it to `None` within
one cycle. A raising producer retains the prior snapshot and its `polled_ts`, flags `stale: true`,
logs one warning per fault episode, and still updates the pipeline-dispatch, dispatch-detail, and
metrics panels in that same cycle.
