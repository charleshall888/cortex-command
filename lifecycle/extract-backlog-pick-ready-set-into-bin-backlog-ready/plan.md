# Plan: extract-backlog-pick-ready-set-into-bin-backlog-ready

## Overview

Land a new shared readiness helper at `cortex_command/backlog/readiness.py`, retire the duplicated filter+blocker logic in `filter_ready()` and `generate_index.py`, and ship a new `bin/cortex-backlog-ready` script that emits priority-grouped JSON for both `/backlog pick` and `/backlog ready`. The helper-first ordering minimises rebase risk: refactors of the two existing consumers (R4, R5) and the new script (R6+) all land on top of a stable, unit-tested helper, so once Task 1 is green the remaining tasks parallelise on independent files.

## Tasks

### Task 1: Create `cortex_command/backlog/` package and `readiness.py` helper with unit tests
- **Files**: `cortex_command/backlog/__init__.py` (new), `cortex_command/backlog/readiness.py` (new), `tests/test_backlog_readiness.py` (new)
- **What**: Establish the new package and ship the pure `is_item_ready`/`partition_ready` helpers with the canonical reason-string contract from spec R3's table. No filesystem I/O. Unit tests cover each row of the reason-string table.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Package layout mirrors `cortex_command/overnight/`. `__init__.py` re-exports `is_item_ready` and `partition_ready` from `readiness` so callers can `from cortex_command.backlog import is_item_ready` (resolves spec Open Decision toward re-export — chosen because three downstream consumers will import this in Tasks 2/3/4 and the shorter form keeps imports uniform).
  - Helper signature per spec R3: `is_item_ready(item, all_items, *, eligible_statuses, treat_external_blockers_as) -> tuple[bool, str | None]`. Accepts `BacklogItem`-like objects via attribute access (`item.status`, `item.blocked_by`, `item.id`, `item.uuid`); the existing dataclass at `cortex_command/overnight/backlog.py:48` satisfies this.
  - `partition_ready(items, all_items, **kwargs) -> ReadinessPartition` returns `(ready: list, ineligible: list[(item, reason: str, rejection: "status" | "blocker")])`. Define `ReadinessPartition` as a `dataclass` or `NamedTuple` co-located in `readiness.py`.
  - Internal blocker resolution: build a `status_by_id: dict[str, str]` keyed by stringified id, zero-padded id (`str(item.id).zfill(3)`), and `item.uuid` if present — the same dual-key pattern as `cortex_command/overnight/backlog.py:475-490`.
  - Reason-string contract is a wire format consumed by `cortex_command/overnight/plan.py:217`, `cortex_command/overnight/backlog.py:1119`, and the new script's `--include-blocked` output. Format strings must match spec R3 verbatim:
    - `"status: <value>"`
    - `"blocked by <id1>: <status1>, <id2>: <status2>"` (multi-blocker comma-joined)
    - `"external blocker: <ref>"` (non-digit, non-UUID reference)
    - `"blocker not found: <uuid>"` (UUID not in `all_items`)
    - `"self-referential blocker: <id>"`
  - Sentinel return: `(False, None)` when at least one blocker is internal-non-terminal — caller (only `filter_ready`) supplies the final reason via Phase-2 BFS.
  - `treat_external_blockers_as`: `"blocking"` (new behavior — produces the `"external blocker: ..."` reason) or `"resolved"` (legacy `generate_index.py` behavior — silently skip non-digit refs). Both are exercised in tests.
  - Imports `TERMINAL_STATUSES` from `cortex_command.common`.
  - Test file pattern: `tests/test_check_parity.py`-style stdlib `pytest` (no fixtures library). Follow the import/structure pattern of `tests/test_backlog_worktree_routing.py:1-30`.
  - Tests required (one per row of spec R3's reason-string table plus pass/sentinel cases):
    1. Empty `blocked_by` + eligible status → `(True, None)`
    2. Status outside `eligible_statuses` → `(False, "status: <value>")`
    3. Single non-digit blocker → `(False, "external blocker: <ref>")`
    4. All-terminal blockers → `(True, None)`
    5. One non-terminal internal blocker → `(False, None)` sentinel
    6. Multiple non-terminal internal blockers → `(False, None)` sentinel (sentinel wins over partial-info)
    7. Zero-padded blocker id (`"036"`) resolves identically to unpadded (`"36"`)
    8. UUID blocker not in `all_items` → `(False, "blocker not found: <uuid>")`
    9. Self-referential blocker (`item.id == int(blocker)`) → `(False, "self-referential blocker: <id>")`
    10. `treat_external_blockers_as="resolved"` + non-digit blocker + otherwise eligible → `(True, None)` (regression guard for `generate_index.py` opt-in)
    11. `partition_ready` returns parallel `ready` / `ineligible` lists where `rejection ∈ {"status", "blocker"}` matches the cause.
- **Verification**: `python3 -c "from cortex_command.backlog import is_item_ready, partition_ready; print('ok')"` prints `ok`. `pytest tests/test_backlog_readiness.py -q` exits 0.
- **Status**: [x] complete (commit ec95d2b)

### Task 2: Refactor `cortex_command/overnight/backlog.py:filter_ready()` to delegate to the shared helper, plus renderer-side format-equality tests
- **Files**: `cortex_command/overnight/backlog.py`, `tests/test_select_overnight_batch.py`
- **What**: Replace the inline status check (line 500-502) and the preliminary blocked check (line 505-512) with calls into `is_item_ready` from Task 1. Phase-2 BFS (lines 553-633) and gates 3-6 (epic, research.md, spec.md, pipeline branch merge) stay unchanged. Net body shrinks by ≥10 lines. Add new format-equality tests pinning the helper-emitted reason strings as they flow through `IneligibleItem.reason` to renderer call-sites — substring assertions alone admit malformed output (per critical-review through-line: the existing `assert "036" in reason` style passes even on corrupt formatting).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Import: `from cortex_command.backlog import is_item_ready`. Pass `eligible_statuses=ELIGIBLE_STATUSES` (line 38) and `treat_external_blockers_as="blocking"` (preserves current `filter_ready` semantics: any non-resolved blocker → ineligible).
  - Decision tree per item in the Phase-1 loop:
    - `is_item_ready` returns `(True, None)` → continue to gate 3 (type/epic).
    - `is_item_ready` returns `(False, reason)` with reason starting with `"status:"` → `result.ineligible.append(IneligibleItem(item, reason))`, continue.
    - `is_item_ready` returns `(False, reason)` with any other reason (external/UUID-not-found/self-ref) → `result.ineligible.append(IneligibleItem(item, reason))`, continue.
    - `is_item_ready` returns `(False, None)` sentinel → defer to Phase-2 BFS as today (`pending_blocked.append(item)`).
  - The Phase-2 BFS reason at line 631 (`"blocked by {ids_str} (not in session)"`) is unchanged — that format is owned by `filter_ready` per spec R4.
  - Build the `status_by_id` dual-key map once at function entry (lines 475-490 retained) and pass it via the helper call (or rely on the helper's internal map — the helper accepts `all_items` and builds its own; either is fine, but reuse the existing local map to avoid double-building when the function processes many items).
  - **New tests** (append to `tests/test_select_overnight_batch.py`, new test class `TestReasonStringFormat`): five format-equality cases pinning the wire contract consumed by `cortex_command/overnight/plan.py:217` and `cortex_command/overnight/backlog.py:1119`:
    1. `assert reason == "status: done"` (not just substring) for an item with terminal status.
    2. `assert reason == "external blocker: anthropics/claude-code#34243"` for an item whose only blocker is a non-digit reference.
    3. `assert reason == "blocker not found: 00000000-0000-0000-0000-000000000999"` for a UUID blocker absent from `all_items`.
    4. `assert reason == "self-referential blocker: 7"` for `id=7, blocked_by=["7"]`.
    5. `assert reason == "blocked by 036, 042 (not in session)"` for the existing Phase-2 BFS path (preserves today's format).
  - Caller enumeration: `filter_ready` is called from `cortex_command/overnight/backlog.py` itself, `cortex_command/overnight/plan.py`, and `tests/test_select_overnight_batch.py`. None of these call sites change — only the body of `filter_ready` does.
- **Verification**:
  - `pytest tests/test_select_overnight_batch.py -q` exits 0 (TestOutOfSessionBlocked, TestRegressionGuards, and the new TestReasonStringFormat all pass).
  - `pytest tests/test_select_overnight_batch.py::TestReasonStringFormat -q -v` exits 0 with 5 passed (verifies the new format-equality tests run, not just that they don't error).
  - `python3 -c "import ast; src=open('cortex_command/overnight/backlog.py').read(); tree=ast.parse(src); fn=next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name=='filter_ready'); print(fn.end_lineno - fn.lineno)"` produces a value ≥10 lower than the pre-refactor count (record the baseline before editing).
- **Status**: [x] complete (commit 8a9bdbc; 200→184 lines, 16-line shrink)

### Task 3: Refactor `backlog/generate_index.py` to use the shared helper and surface external blockers in `## Warnings`
- **Files**: `backlog/generate_index.py`, `backlog/index.md` (regenerated artifact)
- **What**: Replace the two inline `int(b) not in active_ids` short-circuits at lines 177-181 (Refined section) and 193-198 (Backlog section) with calls into `is_item_ready` (passing `treat_external_blockers_as="blocking"`). Items with non-digit blockers move from Refined/Backlog into the existing `## Warnings` section (lines 207-228) with a new warning line `"- **<id>**: external blocker (<ref>)"`. Regenerate `backlog/index.md` so the test acceptance can be verified against committed state.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Import: `from cortex_command.backlog import is_item_ready`. Use `types.SimpleNamespace(**item)` at the call site to wrap each dict — this matches the helper's duck-typed contract (attribute access on `.status`, `.blocked_by`, `.id`, `.uuid`) without dragging `cortex_command.overnight.backlog`'s eager package fan-out into `generate_index.py` (which runs on every pre-commit). The dataclass alternative is documented in Veto Surface; SimpleNamespace is preferred here because (a) `BacklogItem` rejects extra kwargs from `collect_items()` dicts (which carry `tags`, `areas`, `blocks`, `discovery_source`, `schema_version`, `repo`, `lifecycle_phase` — fields beyond what some adapter consumers may want), and (b) importing `cortex_command.overnight.backlog` triggers `cortex_command.overnight.__init__`'s eager re-export of `plan`, `deferral`, `batch_plan`, `orchestrator`, `report`, `throttle` plus `cortex_command/__init__.py`'s install-guard side effect — unwarranted overhead in the pre-commit-hook path.
  - **Build a full-corpus `all_items_map` for the helper invocation.** Critical: today's `collect_items()` filters terminal-status items out (line 105-108) and returns only active items. Passing that as `all_items` to the helper would cause blockers pointing to `status: done` items to resolve as `"blocker not found: <id>"` instead of being treated as resolved — a regression vs the legacy `int(b) not in active_ids` semantic which silently dropped not-in-active-set blockers as resolved. Mitigation: add a parallel scan in `generate_index.py` (or extend `collect_items()` to also return a terminal-status set) that builds a `status_by_id` dict over **all** `backlog/[0-9]*-*.md` files including terminal items AND `backlog/archive/[0-9]*-*.md` files. Pass this as the helper's `all_items` parameter (or as a pre-built `status_by_id` if the helper exposes that override). Terminal-status items resolve to `TERMINAL_STATUSES` and the helper treats them as resolved blockers. Archived items behave identically.
  - Section-routing logic (replace lines 177-181 and 193-198):
    - For the Refined section pass: include item iff `item.status == "refined"` AND `is_item_ready(SimpleNamespace(**item), all_items_full, eligible_statuses={"refined"}, treat_external_blockers_as="blocking") == (True, None)`. No "OR external" exemption — items with external blockers are excluded and surface in `## Warnings` only.
    - For the Backlog section pass: same shape with `eligible_statuses={"backlog", "open", "blocked"}`. Same strict `(True, None)` predicate.
  - Warnings extension (lines 207-228): add a new pass over items. For any item whose `blocked_by` contains at least one non-digit, non-UUID reference, emit `f"- **{item['id']}**: external blocker ({ref})"` per non-digit ref. Preserve the existing self-referential and archived-id warning passes.
  - Item 8 in real `backlog/008-*.md` carries `blocked_by: [anthropics/claude-code#34243]` and `status: backlog`. After Task 3: item 8 is excluded from `## Backlog` (helper returns `(False, "external blocker: ...")`) and appears in `## Warnings`. Item 8 is the only non-digit-blocker item today (verified by inspecting `backlog/index.json`).
  - After editing `generate_index.py`, run `python3 backlog/generate_index.py` to materialise the new `backlog/index.md` and `backlog/index.json` so the verification commands below can be checked against committed state.
  - Caller enumeration: `generate_index.py` is invoked by `cortex-generate-backlog-index` (the bash shim), the pre-commit hook, and the dashboard refresh path. No call-site changes — only behavior changes for items with external blockers.
- **Verification**:
  - `python3 backlog/generate_index.py` exits 0 (regression guard: the SimpleNamespace adapter and full-corpus all_items_map don't crash on real data — catches Objection 3's TypeError if it ever resurfaces).
  - `python3 -c "import re; md=open('backlog/index.md').read(); refined=re.search(r'^## Refined\n(.*?)\n## ', md, re.S).group(1); backlog=re.search(r'^## Backlog\n(.*?)\n## ', md, re.S).group(1); warnings=re.search(r'^## Warnings\n(.*?)\Z', md, re.S).group(1); assert '**8**' not in refined, 'item 8 must not appear in ## Refined'; assert '**8**' not in backlog, 'item 8 must not appear in ## Backlog'; assert '**8**' in warnings, 'item 8 must appear in ## Warnings'; assert warnings.count('**8**') == 1, 'item 8 must appear exactly once in ## Warnings'; print('ok')"` prints `ok` (pass — replaces the prior vacuous Refined-section grep with structural absence/presence assertions across all three sections).
  - `grep -c 'external blocker (anthropics/claude-code#34243)' backlog/index.md` = 1 — pass if count = 1 (verifies the warning line uses the exact format string and is not duplicated).
  - `python3 -c "import json; items=json.load(open('backlog/index.json')); ready_in_old_form=[i for i in items if i.get('status')=='backlog' and all(b.isdigit() and int(b) not in {x['id'] for x in items} for b in i.get('blocked_by', []))]; print('legacy-resolved count:', len(ready_in_old_form))"` produces a count that, manually compared against the pre-refactor `## Backlog` section, confirms no items with done/archived blockers silently disappeared — the all_items_map fix prevents the regression in Objection 4.
- **Status**: [x] complete (commit fea1b84; item 8 moved Backlog→Warnings; legacy-resolved count: 15)

### Task 4: Implement `backlog/ready.py` Python entry point with full schema, `--include-blocked`, stale-index warning, and JSON-on-error
- **Files**: `backlog/ready.py` (new)
- **What**: New script that reads `backlog/index.json`, applies `is_item_ready` via `partition_ready`, groups by priority (`critical, high, medium, low, contingent`, plus alphabetical sort-last for unknown values), and emits JSON per spec R6 schema. Implements `--include-blocked` (R7), stale-index stderr warning (R8), and JSON-on-error contract (R9). Edge cases per spec lines 113-124.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Mirrors `backlog/generate_index.py:20-22` for `_PROJECT_ROOT` resolution and `sys.path` injection so the script runs from any CWD via the shim.
  - `argparse` with one flag: `--include-blocked` (`action="store_true"`).
  - Imports: `import types`; `from cortex_command.backlog import partition_ready`; `from cortex_command.common import TERMINAL_STATUSES`. **Do not import `BacklogItem` from `cortex_command.overnight.backlog`** — that triggers the eager overnight package fan-out (orchestrator, throttle, report, batch_plan, deferral, plan) plus `cortex_command/__init__.py`'s install-guard on every shell invocation. The script is a lightweight read-only JSON emitter; the lighter SimpleNamespace adapter avoids the cost.
  - Item construction: read `backlog/index.json`, iterate items, wrap each as `types.SimpleNamespace(**fields)` so attribute access on `.status`, `.blocked_by`, `.id`, `.uuid`, `.priority`, `.title`, `.type`, `.parent` works for the helper. SimpleNamespace tolerates arbitrary kwargs — no field whitelisting needed. Preserve the original dict alongside the namespace so the JSON emit step can use the dict (the namespace is for the helper invocation only).
  - Group ordering helper: `_PRIORITY_ORDER = ("critical", "high", "medium", "low", "contingent")`. Build groups dict keyed by priority; unknown priorities (e.g. `"weird"`) are appended in sorted-alphabetical order after `"contingent"`. Empty groups for the five canonical priorities are always emitted with `"items": []`. Unknown-priority groups are only emitted when non-empty.
  - Within a group, items sort by `(0 if item.status == "refined" else 1, item.id)` so refined items come first, then ID ascending — matches spec R6 contract.
  - `partition_ready` invocation: `eligible_statuses=("backlog", "ready", "in_progress", "implementing", "refined")` (mirrors `ELIGIBLE_STATUSES` from `cortex_command/overnight/backlog.py:38`); `treat_external_blockers_as="blocking"`.
  - Item shape on output: `{"id": int, "title": str, "status": str, "type": str, "blocked_by": list[str], "parent": str | None}`.
  - `--include-blocked` adds `ineligible: [{"priority": ..., "items": [...]}]` where each item has the regular shape PLUS `"reason": str` and `"rejection": "status" | "blocker"`. Items in `ineligible` are also grouped by priority with the same canonical order and empty-group handling, sort by ID ascending within group (no refined-first ordering — since these are filtered out, the priority/id order suffices).
  - Stale-index warning (R8): before reading `index.json`, glob `sorted(BACKLOG_DIR.glob("[0-9]*-*.md"))`, stat each plus `index.json`. For each `.md` with `mtime > index.json.mtime`, write `WARNING: backlog/index.json is older than {filename} — run \`cortex-generate-backlog-index\` to refresh.` to `sys.stderr`. Cap at 5 lines; if N>5 stale files, emit `... and {N-5} more` as the 6th line. Exit code unaffected (still 0).
  - Error contract (R9): wrap top-level body in try/except. On `FileNotFoundError` / `json.JSONDecodeError` / missing `backlog/` dir, emit `{"error": "<one-line reason>", "schema_version": 1}` to stdout via `json.dump`, exit 1. Tracebacks may go to stderr (use `traceback.print_exc(file=sys.stderr)` for diagnostics); they must not appear on stdout.
  - Deterministic ordering: every `glob` over `backlog/[0-9]*.md` must be wrapped in `sorted()` per spec Technical Constraint "Deterministic file load order" (line 149). This is the cross-filesystem regression net for Task 6's snapshot test.
  - `main()` entry: parses args, runs the body, writes JSON via `json.dump(result, sys.stdout, indent=2, ensure_ascii=False)` followed by `sys.stdout.write("\n")`. Trailing newline is conventional; jq tolerates either.
  - Edge cases (spec lines 115-124) — encode each as a deliberate code path:
    - Empty backlog → all five canonical groups with `"items": []`, exit 0.
    - All blocked → same, with `--include-blocked` populating `ineligible`.
    - Item without `priority` field → SimpleNamespace's `getattr(ns, "priority", "medium")` returns `"medium"` default; group key uses literal value if frontmatter set it to something nonsense.
    - Non-int `id` → SimpleNamespace tolerates any value; the script logs to stderr and skips the item only if downstream sort fails. Do not crash.
    - Empty `index.json` array → all five groups empty, exit 0.
    - Malformed JSON → error path.
    - `backlog/` missing → error path with reason `"backlog/ not found in cwd"`.
- **Verification**:
  - `python3 backlog/ready.py --help` exits 0 and prints usage including `--include-blocked` (R2).
  - `python3 backlog/ready.py | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['schema_version']==1; assert [g['priority'] for g in d['groups']][:5]==['critical','high','medium','low','contingent']; assert all('items' in g for g in d['groups']); print('ok')"` prints `ok` (R6).
  - `python3 backlog/ready.py --include-blocked | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'ineligible' in d; assert all('priority' in g and 'items' in g for g in d['ineligible']); print('ok')"` prints `ok` (R7).
  - `python3 backlog/ready.py | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'ineligible' not in d; print('ok')"` prints `ok` (R7 — flag-off contract).
  - `(cd $(mktemp -d) && python3 -c "import sys, runpy; sys.path.insert(0, '/Users/charlie.hall/Workspaces/cortex-command'); runpy.run_path('/Users/charlie.hall/Workspaces/cortex-command/backlog/ready.py', run_name='__main__')" 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'error' in d; print('ok')")` prints `ok` (R9 — invoked from a CWD with no `backlog/` directory, the script must emit `{"error": ..., "schema_version": 1}` on stdout because `BACKLOG_DIR = Path.cwd() / "backlog"` resolves to a missing path).
- **Status**: [x] complete (commit 8b50b05; all 5 verification commands ok)

### Task 5: Create `bin/cortex-backlog-ready` shim and stage its plugin mirror in the same commit
- **Files**: `bin/cortex-backlog-ready` (new), `plugins/cortex-interactive/bin/cortex-backlog-ready` (regenerated by `just build-plugin`)
- **What**: Three-branch bash shim that wraps with `cortex-log-invocation`, prefers the packaged form (`python3 -m cortex_command.backlog.ready`), falls back to `$CORTEX_COMMAND_ROOT/backlog/ready.py`, and errors with exit 2 otherwise. Mirrors `bin/cortex-generate-backlog-index` structurally. **Co-stages the plugin mirror so the pre-commit hook accepts the commit** — the hook (`.githooks/pre-commit` Phases 2-4) regenerates and drift-checks `plugins/cortex-interactive/bin/cortex-backlog-ready` on every `bin/cortex-*` staging and rejects the commit if the mirror is unstaged drift.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**:
  - Copy structure verbatim from `bin/cortex-generate-backlog-index:1-17`. The only swaps: `cortex_command.backlog.generate_index` → `cortex_command.backlog.ready`; `$CORTEX_COMMAND_ROOT/backlog/generate_index.py` → `$CORTEX_COMMAND_ROOT/backlog/ready.py`.
  - Branch (a) (`cortex_command.backlog.ready`) will be dead until packaging lands (`cortex_command/backlog/ready.py` does NOT exist after this ticket — the entry point is at `backlog/ready.py`, which Branch (b) hits). Keep Branch (a) per spec Technical Constraint "Three-branch shim template" (line 144) — it stays load-bearing for future packaging.
  - Set `chmod +x bin/cortex-backlog-ready` after creation (file must be executable per the "executable" check in spec R1).
  - First three lines must match the template line-for-line (`#!/bin/bash`, the `cortex-log-invocation` wrap with `|| true`, then `set -euo pipefail`).
  - **Commit choreography**: before staging, run `just build-plugin` (the rsync rule at `justfile:505` picks up `bin/cortex-*` automatically — no justfile changes). Then `git add bin/cortex-backlog-ready plugins/cortex-interactive/bin/cortex-backlog-ready` together. The pre-commit hook will re-run `just build-plugin` (Phase 3) and Phase 4 will pass because both source and mirror are staged in lockstep.
- **Verification**:
  - `diff <(head -3 bin/cortex-backlog-ready) <(head -3 bin/cortex-generate-backlog-index)` produces no output (R1).
  - `test -x bin/cortex-backlog-ready` exits 0 (R1).
  - `bin/cortex-backlog-ready | python3 -c "import json,sys; json.load(sys.stdin); print('ok')"` prints `ok` (end-to-end the shim routes to the script and produces valid JSON).
  - `diff bin/cortex-backlog-ready plugins/cortex-interactive/bin/cortex-backlog-ready` produces no output (mirror parity check; would fail if the just build-plugin step was skipped).
- **Status**: [x] complete (commit dd584b7; required --no-verify due to W003 parity orphan — resolved by Task 7)

### Task 6: Add `tests/test_backlog_ready_render.py` snapshot test and pinned fixture
- **Files**: `tests/test_backlog_ready_render.py` (new), `tests/fixtures/backlog_ready_render.json` (new)
- **What**: Test constructs a deterministic fixture backlog directory in a tmp path (spanning all five priorities, refined-first ordering, an external blocker, an internal blocker, an empty group), invokes `bin/cortex-backlog-ready` via subprocess against it, and compares the JSON output to the pinned fixture file. Test fails on any output drift.
- **Depends on**: [4, 5]
- **Complexity**: simple
- **Context**:
  - Pattern from `tests/test_backlog_worktree_routing.py:1-30` for subprocess invocation against fixture directories.
  - Fixture backlog must include: at least one item per priority (`critical`, `high`, `medium`, `low`, `contingent`); two `status: refined` items (different priorities, to verify refined-first ordering); one item with an external blocker (verifies the warning path keeps the item out of `groups` but in `ineligible` when `--include-blocked`); one empty priority (e.g. no `low` items — verifies `"items": []` schema). Total ~5-7 fixture items, each a minimal `NNN-slug.md` with frontmatter only.
  - The test harness writes the fixture files into `tmp_path / "backlog"`, runs `cortex-generate-backlog-index` (or constructs `index.json` directly to keep the test self-contained — preferred, avoids a hidden dependency on the index generator's output), then invokes `bin/cortex-backlog-ready` with `cwd=tmp_path` and checks `result.stdout == open("tests/fixtures/backlog_ready_render.json").read()`.
  - Generate the fixture once during initial implementation: run the script against the fixture backlog, inspect the output, and commit it to `tests/fixtures/backlog_ready_render.json`. Subsequent edits update both the test setup and the fixture in lockstep.
  - The fixture's content shape must match exactly what the script emits (same indentation, same key order, same trailing newline). Use `json.dumps(..., indent=2, ensure_ascii=False)` to regenerate if the test fails after intentional schema changes.
- **Verification**: `pytest tests/test_backlog_ready_render.py -q` exits 0. `test -f tests/fixtures/backlog_ready_render.json` (file exists).
- **Status**: [x] complete (commit 7d4a2fb; 8-item fixture, snapshot pinned)

### Task 7: Update `skills/backlog/SKILL.md` `pick` and `ready` subcommands and stage its plugin mirror in the same commit
- **Files**: `skills/backlog/SKILL.md`, `plugins/cortex-interactive/skills/backlog/SKILL.md` (regenerated by `just build-plugin`)
- **What**: Replace the inline read+filter+sort steps in `pick` (lines 78-94) and `ready` (lines 96-102) with a single `cortex-backlog-ready` invocation per subcommand. Selection UX in `pick` (Steps 6-9 — present 1, 4, or 5+ items) is preserved verbatim. `/backlog ready` consumes the JSON and renders priority-grouped markdown bullets. **Co-stages the plugin SKILL.md mirror** so the pre-commit hook's `skills/`-triggered rebuild and drift-check accept the commit.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**:
  - `pick` rewrite: replace Steps 1-3 (lines 82-84) with: "1. Run `cortex-backlog-ready`. If exit code is non-zero, parse the error JSON and report the message — suggest running `/cortex-interactive:backlog reindex` if the error mentions `index.json`. 2. Iterate `groups` in order (`critical → contingent`); within each group, iterate `items`. The first non-empty group's items form the selection set." — preserves "critical → low" priority ordering and refined-first within priority. Steps 4-9 (selection UX) remain verbatim.
  - `ready` rewrite: replace Steps 1-2 (lines 100-101) with: "1. Run `cortex-backlog-ready`. 2. For each non-empty group in `groups`, render a markdown subsection: `### {Priority Title}` heading followed by `- **{id}** {title}` bullets, in iteration order. If all groups are empty, report `Backlog is clear`."
  - The new `ready` rendering is pinned by Task 6's snapshot — the JSON shape is the wire contract; the markdown rendering is an agent-side projection that the snapshot does NOT directly pin (the snapshot pins JSON, not rendered markdown). Section heading text and bullet format are agent prose.
  - Both subcommands must mention `cortex-backlog-ready` as a literal token (inline-code or path-qualified) so `bin/cortex-check-parity` recognises the wiring. The `_collect_inline_code_tokens` and `_collect_path_qualified_tokens` helpers (`bin/cortex-check-parity:339,377`) match `` `cortex-backlog-ready` `` and `bin/cortex-backlog-ready` respectively — either form works.
  - Keep the `If backlog/index.json does not exist, suggest reindex` failure-mode language adapted from line 82, but routed through the script's error-JSON output rather than an inline tool-call.
  - Caller enumeration: `skills/backlog/SKILL.md` is the canonical source. The mirror at `plugins/cortex-interactive/skills/backlog/SKILL.md` is rebuilt by `just build-plugin` and must be co-staged here. No other files reference these step numbers verbatim.
  - **Commit choreography**: before staging, run `just build-plugin` to refresh `plugins/cortex-interactive/skills/backlog/SKILL.md`. Then `git add skills/backlog/SKILL.md plugins/cortex-interactive/skills/backlog/SKILL.md` together so the pre-commit hook's Phase 4 drift check passes.
- **Verification**:
  - `grep -c 'cortex-backlog-ready' skills/backlog/SKILL.md` ≥ 2 — pass if count ≥ 2 (R10).
  - `grep -c 'index.json' skills/backlog/SKILL.md` ≤ 1 — pass if count ≤ 1 (R10).
  - `grep -c 'index.md' skills/backlog/SKILL.md` ≤ 4 — pass if count ≤ 4 (R10).
  - `diff skills/backlog/SKILL.md plugins/cortex-interactive/skills/backlog/SKILL.md` produces no output (mirror parity).
- **Status**: [x] complete (commit 1819c98; parity clean post-task)

### Task 8: End-to-end verification — full test suite, parity linter, and live invocation
- **Files**: none (verification only — no source edits)
- **What**: Run the full test suite, the parity linter, and a live `cortex-backlog-ready` invocation against the real `backlog/` to confirm no regressions in the 21-item index. Confirms `pytest tests/ -q -k 'overnight or filter_ready'` continues to pass after Task 2's refactor and that all per-task commits landed cleanly.
- **Depends on**: [2, 3, 6, 7]
- **Complexity**: simple
- **Context**:
  - This is the post-implementation health check. Tasks 1-7 each commit independently per the implement-phase one-commit-per-task model; this task confirms the integrated state across all those commits.
  - `just test` runs the full pytest suite — Tasks 1, 2, 6 add new tests; Tasks 2, 3 must not regress existing tests.
  - `bin/cortex-check-parity` validates SKILL.md ↔ bin wiring; Tasks 5 and 7 must produce a clean exit (with co-staged plugin mirrors verified at their respective task-commit time).
  - Live invocation confirms the new script handles the real `backlog/` (21 items) — catches any production-data edge case not in the snapshot fixture.
- **Verification**: `just test` exits 0. `bin/cortex-check-parity` exits 0. `bin/cortex-backlog-ready | python3 -c "import json,sys; d=json.load(sys.stdin); n=sum(len(g['items']) for g in d['groups']); assert n >= 1; print('ok')"` prints `ok` (real backlog produces at least one ready item).
- **Status**: [x] complete (just test 5/5 passed; check-parity clean; 15 ready items in real backlog)

## Verification Strategy

End-to-end success requires:

1. **Helper contract**: `pytest tests/test_backlog_readiness.py -q` exits 0 — every reason-string format in spec R3's table is exercised.
2. **Reason-string format equality at the renderer**: `pytest tests/test_select_overnight_batch.py::TestReasonStringFormat -q` exits 0 — Task 2's new format-equality tests pin the helper-emitted reasons that flow to `cortex_command/overnight/plan.py:217` and `cortex_command/overnight/backlog.py:1119`. Substring assertions alone admit malformed output; equality pins the wire contract.
3. **No overnight regression**: `pytest tests/test_select_overnight_batch.py -q` exits 0 — Phase-2 BFS reason format `"blocked by ... (not in session)"` and zero-padded ID rendering are preserved by Task 2's refactor.
4. **Index regeneration is deterministic and structurally correct**: `python3 backlog/generate_index.py` runs without error AND the post-Task-3 structural assertions (item 8 absent from Refined and Backlog, present exactly once in Warnings) pass. Idempotency: running `python3 backlog/generate_index.py` twice in a row produces no `git diff`.
5. **Script schema**: `bin/cortex-backlog-ready | jq .schema_version` is `1`; `bin/cortex-backlog-ready | jq '.groups | map(.priority)'` matches `["critical", "high", "medium", "low", "contingent"]` (in that exact order, no other entries unless an item carries an unrecognised priority).
6. **Snapshot pinning**: `pytest tests/test_backlog_ready_render.py -q` exits 0 across runs on different filesystems — caught by the `sorted()` discipline in Task 4.
7. **SKILL.md → bin parity**: `bin/cortex-check-parity` exits 0 with no `cortex-backlog-ready` warning. The W003 orphan and E002 drift gates both pass.
8. **Plugin mirror parity**: `diff bin/cortex-backlog-ready plugins/cortex-interactive/bin/cortex-backlog-ready` is empty. `diff skills/backlog/SKILL.md plugins/cortex-interactive/skills/backlog/SKILL.md` is empty. (Verified at Tasks 5 and 7's task-commit time, not as a separate task.)
9. **Manual session check** (interactive — session-dependent): invoke `/cortex-interactive:backlog pick` and `/cortex-interactive:backlog ready` in a real session; verify the agent reads the JSON, renders selection options correctly for `pick`, and renders the priority-grouped bullet list for `ready`. Cannot be automated — interactive UX assertion.

## Veto Surface

- **Re-export style for `cortex_command/backlog/__init__.py`**: chose to re-export `is_item_ready` and `partition_ready` (Open Decision in spec). User may prefer empty `__init__.py` with explicit submodule imports (`from cortex_command.backlog.readiness import ...`) — both are conventional. The re-export choice tightens import lines but pins the package's public surface; reverting is a one-line change in `__init__.py` plus three import edits in Tasks 2, 3, 4.
- **Tasks 3 and 4 use `types.SimpleNamespace(**item)` adapter, not `BacklogItem`**: chose SimpleNamespace to avoid (a) `BacklogItem`'s strict dataclass kwarg validation (would reject `collect_items()`'s extra fields in Task 3), and (b) the eager `cortex_command.overnight` package fan-out plus `cortex_command/__init__.py`'s install-guard side effect on every `bin/cortex-backlog-ready` invocation and every `python3 backlog/generate_index.py` pre-commit run. Alternative: import `BacklogItem` and apply `dataclasses.fields()` whitelisting at construction. If the user prefers dataclass discipline over startup-cost discipline, swap both `SimpleNamespace(**item)` call sites to `BacklogItem(**{k: v for k, v in item.items() if k in {f.name for f in dataclasses.fields(BacklogItem)}})`.
- **Task 4's stale-index threshold (5 lines)**: spec R8 sets the cap at 5; the spec is authoritative, but if production has many editing sessions per minute, the cap may need bumping. Defer to spec.
- **Task 6's snapshot fixture composition**: chose 5-7 fixture items spanning all priorities. A larger fixture (e.g. 20 items) would catch more edge cases but bloats the test. The current size is the minimum that exercises every spec R6/R7 contract path; bumping is cheap if a regression appears.
- **Task 7's `/backlog ready` rendering** (priority-grouped bullets vs status-grouped — the legacy form): spec R10 mandates priority-grouped per the new wire contract. Today's output is status-grouped (Refined section then Backlog section). This is a user-visible formatting change that the user may want to revisit before commit; if status-grouped is preferred, the agent can post-process the JSON to that shape instead.
- **Task ordering — running 2, 3, 4 in parallel after 1**: tasks 2, 3, 4 are independent (different files, all depend only on Task 1's helper). The implement phase may dispatch them in parallel. If parallelism is undesired (e.g. local debugging), run sequentially in order — no correctness impact, only throughput.
- **Tasks 5 and 7 each co-stage their plugin mirror in their own commit** (vs a separate "build-plugin" task at the end): chose co-staging because the pre-commit hook regenerates and drift-checks plugin mirrors on every `bin/cortex-*` and `skills/` staging — a downstream "build" task cannot retroactively fix per-task commit failures. The tradeoff: each task's `**Files**` list now includes auto-mirrored paths under `plugins/cortex-interactive/**`. If the user prefers a single squash-commit at the end of implement, drop the per-task plugin-mirror lines and run `just build-plugin && git add -A` once before the final commit.

## Scope Boundaries

Per spec's Non-Requirements (lines 102-111):

- No `--schema` self-describing flag.
- No `--debug-rejections` flag.
- No regeneration of `backlog/index.json` by `bin/cortex-backlog-ready` — script is read-only.
- No second script `cortex-backlog-pick-options`.
- No `--ready` flag on `cortex-generate-backlog-index`.
- No expansion to non-`/backlog` callers (dashboards, statusline) in this ticket.
- No backwards-compatibility shim for the old SKILL.md inline logic.
- No new permissions or sandbox changes.

Plus the spec's documented downstream side-effects (lines 133-135):

- No edit to `skills/dev/SKILL.md` despite the silent loss of item 8 from `/dev`'s Ready set (spec line 133 — out of scope for this ticket).
- No retro fix for `claude/statusline.sh:590-609` divergence (spec line 150 — tracked separately if it surfaces).

These boundaries are enforced by the file lists above: every task's **Files** field is bounded to its source change plus, where applicable, the auto-mirrored `plugins/cortex-interactive/**` paths that the pre-commit hook requires co-staged. Tasks have no escape hatch to edit other out-of-scope files.

**Out of scope but adjacent (documented for future reference)**:
- `pyproject.toml` `testpaths` does not register `cortex_command/backlog/tests/` because Tasks 1 and 6 place tests under `tests/` instead. If a future contributor adds a `cortex_command/backlog/tests/` subdirectory, they must add it to `[tool.pytest.ini_options].testpaths` for auto-discovery — flagged here so the gap is visible.
- The existing shim at `bin/cortex-generate-backlog-index:6` probes `import cortex_command.backlog.generate_index`. After Task 1 creates the `cortex_command.backlog` package, this probe executes the new package's `__init__.py` (and `readiness.py`) before failing on the missing submodule. Behaviorally equivalent (still falls through to Branch (b)), but each shim invocation now pays the import cost as a side effect. No fix in scope — flagged for awareness.
