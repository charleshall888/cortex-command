# Specification: extract-backlog-pick-ready-set-into-bin-backlog-ready

## Problem Statement

`/backlog pick` and `/backlog ready` (in `skills/backlog/SKILL.md`) currently express the same readiness predicate three different ways: agent prose in SKILL.md, the `int(b) not in active_ids` short-circuit in `backlog/generate_index.py:177-198`, and `filter_ready()` in `cortex_command/overnight/backlog.py:433`. The three disagree on (a) which statuses count as ready, (b) how non-digit blocker references (e.g. `anthropics/claude-code#34243`) are treated, and (c) whether `status:blocked` items with all-resolved blockers leak through. This forces every consumer to reinvent the predicate and creates silent user-visible drift across `/backlog pick`, `/backlog ready`, `index.md`, and the overnight ready-set. This spec extracts the shared filter+sort logic into `bin/cortex-backlog-ready` (a new script that emits priority-grouped ready items as JSON) and consolidates `filter_ready()` and `generate_index.py` to use a single shared `is_item_ready()` helper. The agent retains selection (in `pick`) and rendering (in both subcommands).

## Requirements

1. **New `bin/cortex-backlog-ready` shim**: a bash shim file at `bin/cortex-backlog-ready` follows the existing three-branch pattern (packaged module → `CORTEX_COMMAND_ROOT` fallback → error exit 2) and wraps with `cortex-log-invocation`. Acceptance: `diff <(head -3 bin/cortex-backlog-ready) <(head -3 bin/cortex-generate-backlog-index)` shows the same logging-wrap and `set -euo pipefail` lines; the file is executable (`test -x bin/cortex-backlog-ready`).

2. **Python entry point** at `backlog/ready.py` (mirroring `backlog/generate_index.py`'s top-level location). Acceptance: `test -f backlog/ready.py && python3 backlog/ready.py --help` exits 0 and prints usage including `--include-blocked`.

3. **Shared readiness helper** introduced as `cortex_command/backlog/readiness.py` (creating the `cortex_command/backlog/` package as a side effect — package gets an `__init__.py`). The helper exposes `is_item_ready(item, all_items, *, eligible_statuses, treat_external_blockers_as) -> tuple[bool, str | None]` and a thin `partition_ready(items, all_items, **kwargs) -> ReadinessPartition` that returns `(ready: list[BacklogItem], ineligible: list[(BacklogItem, reason, rejection)])` where `rejection ∈ {"status", "blocker"}`. Predicate semantics:
   - **Status check**: `item.status in eligible_statuses`. On failure, reason string is `"status: <value>"`.
   - **Blocker resolution**: dual-key lookup over plain ID, zero-padded ID, and UUID (matching `filter_ready()`'s existing pattern at lines 471-490). Canonical reason-string formats per rejection cause:

     | Rejection cause | Reason string |
     |-----------------|---------------|
     | Status not in eligible_statuses | `"status: <value>"` |
     | Internal blocker, non-terminal status | `"blocked by <id>: <status>"` (per blocker; multi-blocker → `"blocked by <id1>: <status1>, <id2>: <status2>"`) |
     | External (non-digit, non-UUID) reference | `"external blocker: <ref>"` |
     | UUID not found in all_items | `"blocker not found: <uuid>"` |
     | Self-referential | `"self-referential blocker: <id>"` |
     | Mixed bag from helper-only (Phase-2 BFS not yet run) | None (sentinel — caller decides) |
     | Phase-2 BFS post-resolution (filter_ready only, not in helper) | `"blocked by <id_or_ref> (not in session)"` |

   - The helper returns `(False, None)` as a sentinel when an item has at least one unresolved internal blocker whose final reason depends on session membership — signalling that the caller (e.g. `filter_ready()`) must supply the final reason via Phase-2 BFS.
   - These reason strings are a wire contract consumed by `overnight/plan.py:217`, `overnight/backlog.py:1119`, and the script's `--include-blocked` output. Format changes require coordinated update of all consumers.
   - The helper is pure (no filesystem reads, no logging side effects).

   Acceptance: `python3 -c "from cortex_command.backlog.readiness import is_item_ready, partition_ready; print('ok')"` prints `ok` and exits 0. New unit tests at `tests/test_backlog_readiness.py` cover: (a) item with empty blocked_by passes; (b) item with non-digit blocker fails with reason `"external blocker: <ref>"`; (c) item with all-terminal blockers passes; (d) item with one non-terminal blocker returns `(False, None)` sentinel; (e) zero-padded and UUID forms in blocked_by both resolve correctly; (f) status outside `eligible_statuses` returns False with reason `"status: <value>"`; (g) UUID not in all_items returns reason `"blocker not found: <uuid>"`; (h) self-referential blocker returns reason `"self-referential blocker: <id>"`. Each format string in the reason-string table above is verified by a concrete fixture. `pytest tests/test_backlog_readiness.py -q` exits 0.

4. **`filter_ready()` refactor** in `cortex_command/overnight/backlog.py`: gate 1 (status check) **fully delegates** to `is_item_ready` — the helper owns the `"status: <value>"` reason. Gate 2 (blocked check) **partially delegates**: the helper resolves terminal vs non-terminal blockers and returns reasons for items where all blockers are non-terminal or external (reasons per F4 reason-string table). For items where the helper returns the `(False, None)` sentinel (at least one unresolved internal blocker whose status is active in the session), `filter_ready()` routes those items into `pending_blocked` and Phase-2 BFS owns the final `"blocked by <id_or_ref> (not in session)"` reason at line 631, unchanged. Gates 3-6 (epic, research.md, spec.md, pipeline branch merge) are unchanged. The dual-key `status_by_id` lookup moves into the helper. Passing `eligible_statuses=ELIGIBLE_STATUSES` and `treat_external_blockers_as="blocking"`.

   Acceptance: `pytest tests/ -q -k 'overnight or filter_ready'` exits 0 (existing overnight tests still pass). `pytest tests/test_select_overnight_batch.py::TestOutOfSessionBlocked -q` exits 0 (Phase-2 BFS reason format `"blocked by ... (not in session)"` preserved; substring assertions for `"not in session"` and `"036"` pass). `grep -c 'def filter_ready' cortex_command/overnight/backlog.py` = 1; the function body is shorter than before (line count drops by ≥ 10 lines).

5. **`generate_index.py` refactor**: the inline `int(b) not in active_ids` short-circuits at lines 177-181 and 193-198 are replaced with calls into the shared helper. Because the shared helper returns "blocking" for non-digit references but `generate_index.py`'s historical behavior treated them as resolved, this is a deliberate behavior change: items with external blockers will now appear in `## Warnings` (not `## Refined`/`## Backlog`) until those blockers are resolved or removed. The Warnings section already exists at lines 207-228; extend it to surface "external blocker (not in backlog)" warnings.

   Acceptance: `python3 backlog/generate_index.py && grep -c 'external blocker' backlog/index.md` ≥ 1 (item 8 carries `blocked_by: anthropics/claude-code#34243`, which is a non-digit reference and must surface as an external blocker warning). Additionally: `grep -B 100 '^## Refined' backlog/index.md | tail -100 | grep -c '\*\*8\*\*'` = 0 (item 8 must NOT appear in `## Refined`). Existing item-counts in `## Refined` and `## Backlog` change only for items with external blockers.

6. **`bin/cortex-backlog-ready` JSON output** to stdout. Schema:
   ```json
   {
     "schema_version": 1,
     "groups": [
       {"priority": "critical", "items": [...]},
       {"priority": "high",     "items": [...]},
       {"priority": "medium",   "items": [...]},
       {"priority": "low",      "items": [...]},
       {"priority": "contingent", "items": [...]}
     ]
   }
   ```
   Item shape: `{"id": int, "title": str, "status": str, "type": str, "blocked_by": list[str], "parent": str | null}`. Group ordering: `critical, high, medium, low, contingent` (any unrecognized priority sorts after `contingent` in alphabetical order). Items within a group: `status: refined` first, then ID ascending. Empty groups are emitted with `"items": []` (uniform schema).

   Acceptance: `bin/cortex-backlog-ready | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['schema_version']==1; assert [g['priority'] for g in d['groups']][:5]==['critical','high','medium','low','contingent']; assert all('items' in g for g in d['groups']); print('ok')"` prints `ok`.

7. **`--include-blocked` flag**: when present, the script also emits filtered-out items grouped by priority under a sibling `"ineligible"` array of groups, each item annotated with `"reason": str` and `"rejection": "status" | "blocker"`. Group ordering matches R6's group ordering (`critical, high, medium, low, contingent`). Empty groups are emitted with `"items": []` for uniform schema. Items within a group sort by ID ascending. Without the flag, ineligible items are excluded entirely from output.

   Schema for `--include-blocked` output:
   ```json
   {
     "schema_version": 1,
     "groups": [...],
     "ineligible": [
       {"priority": "critical", "items": [...]},
       {"priority": "high",     "items": [...]},
       {"priority": "medium",   "items": [...]},
       {"priority": "low",      "items": [...]},
       {"priority": "contingent","items": [...]}
     ]
   }
   ```
   Item shape inside `ineligible.[].items`: regular R6 item shape PLUS `"reason": str` and `"rejection": "status" | "blocker"`.

   Acceptance: `bin/cortex-backlog-ready --include-blocked | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'ineligible' in d; assert isinstance(d['ineligible'], list); assert all('priority' in g and 'items' in g for g in d['ineligible']); assert all('reason' in i and 'rejection' in i for g in d['ineligible'] for i in g['items']); print('ok')"` prints `ok`. `bin/cortex-backlog-ready | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'ineligible' not in d; print('ok')"` prints `ok`.

8. **Stale-index stderr warning**: before reading `backlog/index.json`, the script stats every `backlog/[0-9]*.md` file. If any `.md` file's mtime exceeds `index.json`'s mtime, write `WARNING: backlog/index.json is older than {filename} — run \`cortex-generate-backlog-index\` to refresh.` to stderr (one line per stale file, capped at 5 lines, then `... and N more` if needed). Exit code remains 0; the warning does not block the JSON output.

   Acceptance: `touch backlog/index.json && touch -t 999912312359 backlog/108-*.md && bin/cortex-backlog-ready 2>&1 1>/dev/null | grep -c 'older than'` ≥ 1 (test in fixture, not real backlog). Subsequent `cortex-generate-backlog-index && bin/cortex-backlog-ready 2>&1 1>/dev/null | grep -c 'older than'` = 0.

9. **JSON-on-error contract**: on missing or unparseable `backlog/index.json`, the script emits `{"error": "<one-line reason>", "schema_version": 1}` to stdout and exits with non-zero status (exit code 1). It must not produce a Python traceback on stdout. Tracebacks may go to stderr.

   Acceptance: `(cd $(mktemp -d) && bin/cortex-backlog-ready 2>/dev/null)` produces parseable JSON containing an `error` key and exits non-zero: `(cd $(mktemp -d) && bin/cortex-backlog-ready 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'error' in d; print('ok')")` prints `ok`.

10. **`skills/backlog/SKILL.md` update**: both `pick` (lines 78-94) and `ready` (lines 96-102) subcommands replace inline read+filter+sort steps with a single `cortex-backlog-ready` invocation. The selection UX in `pick` (Steps 6-9 — present 1, 4, or 5+ items) is preserved verbatim. `/backlog ready` consumes the JSON and emits a markdown bullet list grouped by priority — the rendered output is pinned by the snapshot test below.

    Acceptance: `grep -c 'cortex-backlog-ready' skills/backlog/SKILL.md` ≥ 2 (both subcommands wired; baseline = 0). `grep -c 'index.json' skills/backlog/SKILL.md` ≤ 1 (inline read replaced; baseline = 2). `grep -c 'index.md' skills/backlog/SKILL.md` ≤ 4 (inline read replaced for ready; baseline = 5).

11. **`/backlog ready` snapshot test**: a new test at `tests/test_backlog_ready_render.py` constructs a fixture backlog directory, runs `cortex-backlog-ready`, and compares the resulting JSON (deterministic across runs) against a pinned fixture at `tests/fixtures/backlog_ready_render.json`. Test fails if output drifts. The implementation must apply `sorted()` to glob results before any grouping pass; the snapshot fixture is the cross-filesystem regression net.

    Acceptance: `pytest tests/test_backlog_ready_render.py -q` exits 0. `test -f tests/fixtures/backlog_ready_render.json`.

12. **Plugin mirror via `just build-plugin`**: the new shim at `bin/cortex-backlog-ready` is automatically copied to `plugins/cortex-interactive/bin/cortex-backlog-ready` by the existing `rsync --include='cortex-*'` rule in `justfile:495-505`. The same-commit invariant (pre-commit hook fails if mirror is stale) is honored: spec writer and implementer must `just build-plugin` before staging.

    Acceptance: `diff bin/cortex-backlog-ready plugins/cortex-interactive/bin/cortex-backlog-ready` produces no output. `just check-parity` exits 0 (no W003 orphan warning for the new script).

13. **`bin/cortex-check-parity` recognition**: the SKILL.md mention of `cortex-backlog-ready` is detected by the parity linter via either `_collect_path_qualified_tokens` or `_collect_inline_code_tokens`. No allowlist row in `bin/.parity-exceptions.md` is required.

    Acceptance: `bin/cortex-check-parity` exits 0 with no error mentioning `cortex-backlog-ready`.

## Non-Requirements

- **No `--schema` self-describing flag**. YAGNI; SKILL.md documents the schema in prose alongside the call site.
- **No `--debug-rejections` flag**. `--include-blocked` already preserves the debug affordance; a second flag is redundant.
- **No regeneration of `backlog/index.json`** by `bin/cortex-backlog-ready`. The script reads only; the agent retains responsibility for invoking `cortex-generate-backlog-index` when reindex is needed (the stale-index warning prompts this).
- **No `cortex-backlog-pick-options` second script**. Both `pick` and `ready` consume the same JSON output and project differently; one script suffices.
- **No `--ready` flag on `cortex-generate-backlog-index`** (Alternative B from research, rejected). Read-side and write-side stay separated.
- **No expansion to non-`/backlog` callers in this ticket**. Dashboards, status lines, etc. that need readiness data are out of scope; they can call the new script or import the shared helper in a follow-up.
- **No backwards-compatibility shim for the old SKILL.md inline logic**. Once SKILL.md is updated, the old prose is gone — no flag to opt out.
- **No new permissions or sandbox changes**. The script is read-only and stays inside the repo.

## Edge Cases

- **Empty backlog (no `[0-9]*.md` files)**: `cortex-backlog-ready` emits all five groups with `"items": []` and exits 0. No stderr output.
- **All items blocked**: all groups emit `"items": []`. With `--include-blocked`, the `ineligible` array contains all items with reasons. Exit 0.
- **Item with no `priority` field**: defaults to sort-last (alphabetical after `contingent`); group key is the literal string from the item (e.g., a nonsense priority `"weird"` produces a `{"priority": "weird", "items": [...]}` group). The script does not error.
- **Item with non-integer `id`** (e.g. string): the script tolerates and sorts by string comparison within the group. Logged warning at stderr.
- **`backlog/index.json` is empty array `[]`**: emits all five groups with `"items": []`. Exit 0.
- **`backlog/index.json` is malformed JSON**: error-path JSON `{"error": "...", "schema_version": 1}` to stdout, exit 1.
- **`backlog/` directory missing entirely**: error-path JSON `{"error": "backlog/ not found in cwd", "schema_version": 1}` to stdout, exit 1. No stale-index check (would crash).
- **`blocked_by` contains a UUID for an item not in `index.json`**: treated as blocking with reason `"blocker not found: <uuid>"`. Same as non-digit external references.
- **Self-referential `blocked_by`** (item references its own ID): treated as blocking; reason includes `"self-referential blocker: <id>"`. (Existing `generate_index.py:217-220` already surfaces this in `## Warnings`; the shared helper preserves the behavior.)
- **Concurrent `cortex-generate-backlog-index` write**: `atomic_write` (tempfile + `os.replace`) ensures readers see old or new state, never partial. No mitigation needed in `cortex-backlog-ready`.

## Changes to Existing Behavior

- **MODIFIED**: `/backlog pick` reads `backlog/index.json` via inline tool calls → invokes `bin/cortex-backlog-ready` and consumes its JSON. Selection UX unchanged.
- **MODIFIED**: `/backlog ready` reads `backlog/index.md` Refined/Backlog sections → invokes `bin/cortex-backlog-ready` and renders priority-grouped bullets from JSON. Output format changes from index.md-quoted bullets (status-grouped) to priority-grouped bullets — pinned by the new snapshot test.
- **MODIFIED**: `/backlog ready` no longer surfaces `status:blocked` items with all-resolved blockers (those are now Warnings in `index.md` if external blockers exist; otherwise data hygiene says they should have their status updated).
- **MODIFIED**: `cortex_command/overnight/backlog.py:filter_ready()` delegates status/blocker checks to `cortex_command.backlog.readiness.is_item_ready`. External-blocker items already produced an ineligible result; the reason string changes from the auto-generated form to one returned by the helper per the F4 reason-string table.
- **MODIFIED**: `backlog/generate_index.py` items with non-digit `blocked_by` entries (e.g. external GitHub issue refs) move from the `## Refined` / `## Backlog` sections to `## Warnings` with reason "external blocker". This is a deliberate behavior change to surface the inconsistency.
- **MODIFIED**: `skills/dev/SKILL.md:143-145` (Step 3b — Read the Ready Section) reads `backlog/index.md` Refined + Backlog sections to build `/dev`'s triage. After R5, items with non-digit `blocked_by` references (today: item 8) silently disappear from `/dev`'s Ready set. The plugin mirror at `plugins/cortex-interactive/skills/dev/SKILL.md` is co-affected. No `/dev` SKILL.md edit is in scope for this ticket — the change is a downstream side-effect of R5 and is documented here for awareness.
- **MODIFIED**: `cortex_command/overnight/plan.py:217` renders `IneligibleItem.reason` strings into `overnight-plan.md` under `## Not Ready (N)`. After R4 + R5, the rendered reason text changes per the F4 reason-string table. This is the morning-review human-readable handoff; format change is intentional and documented.
- **MODIFIED**: `cortex_command/overnight/backlog.py:1119` summary block (`for item, reason in readiness.ineligible: ...`) renders to stderr/orchestrator-tail. Reason text changes per F4 reason-string table.
- **ADDED**: New `bin/cortex-backlog-ready` script and `plugins/cortex-interactive/bin/cortex-backlog-ready` mirror.
- **ADDED**: New `cortex_command/backlog/` package with `__init__.py` and `readiness.py`.
- **ADDED**: New tests `tests/test_backlog_readiness.py` and `tests/test_backlog_ready_render.py` plus fixture `tests/fixtures/backlog_ready_render.json`.

## Technical Constraints

- **`bin/cortex-*` parity (project.md)**: every new bin script must be wired through SKILL.md; the SKILL.md edit lands in the same commit. Pre-commit hook (`just check-parity --staged`) blocks otherwise.
- **Plugin dual-source enforcement**: pre-commit hook fails if `plugins/cortex-interactive/bin/cortex-backlog-ready` is stale relative to `bin/cortex-backlog-ready`. Implementer must run `just build-plugin` and stage the result.
- **Three-branch shim template**: keep branch (a) (packaged-module form) even though `cortex_command.backlog.ready` will exist after this ticket — branch (a) becomes load-bearing. Branch (b) (`CORTEX_COMMAND_ROOT` fallback) remains as the dev-checkout path.
- **`cortex-log-invocation` wrap**: `|| true` short-circuit and internal `trap 'exit 0'` ensure the logging step cannot block the script.
- **JSON to stdout, status to stderr** (clig.dev convention). Any human-readable warnings go to stderr.
- **Closed-enum priority unsafe**: `backlog/index.json` already contains a `priority: contingent` item, and `_PRIORITY_RANK` maps unknown priorities to rank 9. The new schema must enumerate `contingent` and tolerate unknown priorities (sort-last, group preserved).
- **Shared helper purity**: `is_item_ready` does no filesystem I/O — all artifact-existence checks (research.md, spec.md, pipeline-branch-merge) stay in `filter_ready()`. This keeps the helper trivially testable and reusable in non-overnight contexts.
- **Deterministic file load order**: `bin/cortex-backlog-ready` and `backlog/ready.py` must call `sorted()` on the result of any `pathlib.Path.glob` or `glob.glob` over `backlog/[0-9]*.md` before processing. This pins snapshot output across filesystems (HFS+, ext4, tmpfs, NTFS) and is independent of the within-group sort pinned in R6.
- **Statusline divergence (latent)**: `claude/statusline.sh:590-609` computes a "Refined" count from `backlog/[0-9]*-*.md` frontmatter directly, not from `index.md`. After R5, statusline's count and `index.md`'s `## Refined` count can diverge for any future `status:refined` item with an external (non-digit) blocker. No item triggers this today (item 8 is `status:backlog`, not `status:refined`). Documented to prevent surprise; reconciliation is out of scope for this ticket and tracked separately if it becomes an issue.

## Open Decisions

- **`cortex_command/backlog/__init__.py` content**: empty file vs re-exports of `is_item_ready`/`partition_ready`. Defer until implementation: the choice depends on whether downstream callers (e.g. dashboard, future bin scripts) prefer `from cortex_command.backlog import is_item_ready` (re-export) or `from cortex_command.backlog.readiness import is_item_ready` (explicit submodule). Both are conventional; implementer picks based on existing peer-package style in `cortex_command/`.
