# Review: untrack-backlog-index-cache

## Stage 1: Spec Compliance

### Requirement 1: `cortex-backlog-ready` regenerates on missing index
- **Expected**: On `FileNotFoundError` for `index.json`, regenerate records in-process/in-memory via `collect_items` + `generate_json` (no disk write), inside the outer try; exit 0 with a `groups` key.
- **Actual**: `ready.py:431-446` — the `except FileNotFoundError` handler lazily imports `collect_items, generate_json`, calls `collect_items(BACKLOG_DIR, BACKLOG_DIR.parent / "lifecycle")`, and sets `records = json.loads(generate_json(items))`. The handler is nested inside the outer `try` opened at L416 (whose `except Exception` at L460 maps to `_emit_error`). No disk write occurs. Live check: `python -m cortex_command.backlog.ready` with both index files removed exits 0, emits valid JSON with a `groups` key, and writes no `index.json`.
- **Verdict**: PASS
- **Notes**: Module docstring (L31-36) corrected to "A missing `index.json` is treated as a cache miss and regenerated in-memory ... On malformed input ... exits 1." Stale clause removed.

### Requirement 2: New test for the regenerate-on-miss contract
- **Expected**: A pytest asserting exit 0, valid JSON, and no `index.json` written when the index is absent from a populated backlog dir.
- **Actual**: `tests/test_backlog_ready_missing_index.py` exists; writes two `NNN-slug.md` items, asserts no `index.json` pre-exists, monkeypatches `ready_mod.BACKLOG_DIR`, calls `ready_mod.main([])`, asserts `rc == 0`, parses stdout JSON for `groups`, asserts no `index.json` written, and asserts items 1 and 2 surface. `.venv/bin/pytest tests/test_backlog_ready_missing_index.py -q` → 1 passed.
- **Verdict**: PASS
- **Notes**: Imports the module and monkeypatches `BACKLOG_DIR`, so it exercises the working-tree source (not the installed wheel) — exactly the contract the spec requires.

### Requirement 3: Backlog SKILL prose consistent with missing-index behavior
- **Expected**: `list` auto-regenerates via `cortex-generate-backlog-index` (no "suggest reindex first"); `pick`/`ready` drop "missing" → "malformed".
- **Actual**: `skills/backlog/SKILL.md:70` — list step 1: "If `cortex/backlog/index.md` does not exist, run `cortex-generate-backlog-index` to regenerate it (the index is a local cache, not version-controlled)". `grep -c "cortex-generate-backlog-index"` = 2; `grep -c "missing or malformed backlog index"` = 0; "suggest running reindex first" absent. L92 (pick) and L109 (ready) now read "if the error indicates a malformed backlog index".
- **Verdict**: PASS

### Requirement 4: Index files are gitignored
- **Expected**: `.gitignore` ignores both `cortex/backlog/index.json` and `index.md` (anchored, adjacent to the events.jsonl rule).
- **Actual**: `.gitignore:36-37` — `cortex/backlog/index.json` and `cortex/backlog/index.md`, anchored, adjacent to `cortex/backlog/*.events.jsonl` (L33). `git check-ignore cortex/backlog/index.json cortex/backlog/index.md` lists both, exit 0.
- **Verdict**: PASS

### Requirement 5: Canonical index pair untracked, retained on disk
- **Expected**: Both removed from tracking via `git rm --cached`; working-tree files stay.
- **Actual**: `git ls-files cortex/backlog/index.json cortex/backlog/index.md` prints nothing; both files still exist on disk (verified `test -f` for each).
- **Verdict**: PASS
- **Notes**: Earlier `git ls-files cortex/backlog/ | grep index` noise comes from item *filenames* containing "index" (e.g. 272-...-indexmd.md), not the index files; the explicit path-scoped `git ls-files` confirms neither index file is tracked.

### Requirement 6: Stray nested index deleted
- **Expected**: `cortex/backlog/backlog/` removed via `git rm -r`; directory gone.
- **Actual**: `git ls-files cortex/backlog/backlog/` prints nothing; `test -e cortex/backlog/backlog` → STRAY GONE.
- **Verdict**: PASS

### Requirement 7: Overnight pre-flight stops committing the index but still regenerates it
- **Expected**: Remove `git add cortex/backlog/index.*` + the conditional commit; retain `cortex-generate-backlog-index` and its halt-on-non-zero. SKILL.md summary bullet reworded.
- **Actual**: `new-session-flow.md` — `grep -c "git add cortex/backlog/index"` = 0; `grep -c "cortex-generate-backlog-index"` = 1; halt retained at L19: "...→ halt." `skills/overnight/SKILL.md:64`: "Pre-selection index regeneration — run `cortex-generate-backlog-index` (regenerate only; the index is a gitignored local cache and is not staged or committed)." SKILL.md `git add` count = 0.
- **Verdict**: PASS

### Requirement 8: Docs describe index as regenerated local cache, not committed
- **Expected**: `docs/backlog.md` (~L176, ~L92) and `docs/agentic-layer.md` (~L250) say generated-on-demand / not version-controlled.
- **Actual**: `docs/backlog.md:176` — "regenerated local cache and are not version-controlled (gitignored)..."; L92 — "If the index is absent it is regenerated on demand (the index is a local cache, not version-controlled)" (stale "Suggests running reindex" clause removed, count 0). `docs/agentic-layer.md:250` — "Generated locally and not version-controlled; regenerated on demand...".
- **Verdict**: PASS

### Requirement 9: Plugin mirrors regenerated and consistent
- **Expected**: `just build-plugin` then `git status --porcelain plugins/` empty; canonical + mirror committed together.
- **Actual**: `just build-plugin` ok; `git status --porcelain plugins/` empty. `cmp` confirms backlog SKILL, overnight SKILL, and new-session-flow.md all match their mirrors.
- **Verdict**: PASS

### Requirement 10: Full suite green
- **Expected**: `just test` exits 0.
- **Actual**: 1 failed, 1793 passed, 27 skipped, 1 xfailed. The single failure is `tests/test_mcp_subprocess_contract.py::test_plugin_path_mismatch_exits_nonzero`. Inspected stderr: `error: ... Failed to fetch: https://pypi.org/simple/mcp/ ... dns error ... failed to lookup address information` — `uv run --script` cannot fetch deps in the no-network sandbox, so the subprocess never reaches the "plugin path mismatch" assertion. This is the documented environmental failure that passes with network; it is unrelated to this feature's diff.
- **Verdict**: PASS (with environmental-failure call-out)
- **Notes**: The lone failure is a sandbox network block, not a regression. With network it passes. Flagged per spec instruction; does not affect the verdict.

### Requirement 11: Runtime consumers carry the Phase-1 fix on an absent index
- **Expected**: With no `index.json` on disk, the working-tree module `python3 -m cortex_command.backlog.ready` exits 0 with valid JSON (proving shipped source is correct).
- **Actual**: Removed both index files, ran `.venv/bin/python -m cortex_command.backlog.ready` → exit 0, JSON with a `groups` key, no `index.json` written; index restored afterward.
- **Verdict**: PASS
- **Notes**: The spec correctly scopes the actual installed-binstub `uv tool install --reinstall` + plugin re-sync to the Complete/release phase (Technical Constraints "Deployment sequencing"); the working-tree proof is the in-scope acceptance here.

## Requirements Drift
**State**: none
**Findings**:
- The change is a direct application of the Solution-horizon principle (project.md:21): untracking a 100%-deterministic derived aggregate eliminates the parallel-session conflict class entirely rather than patching it with a merge driver. This is durable, not a stop-gap.
- Complexity (project.md:19): the regenerate-on-miss is minimal (a lazy import + a 4-tuple unpack inside the existing handler); no new abstractions or console scripts. Simpler-wins is honored.
- Graceful partial failure (project.md:49) and "destructive operations preserve uncommitted state" (project.md:53): `git rm --cached` retains the on-disk files; the regenerate-on-miss path is fully in-memory and nested inside the outer try so any I/O error maps to the canonical `_emit_error` JSON contract — degrades cleanly, never tracebacks, never writes.
- Dual-source plugin-mirror enforcement: canonical + mirrors committed together per task; clean rebuild produces zero drift.
- Considered whether untracking a previously-committed derived artifact warrants a new project.md "derived-data-not-committed" policy note. It does not rise to a project-level principle on the strength of one artifact: the existing Solution-horizon + Complexity principles already cover the reasoning, and the spec documents the rationale in-place. A general policy would be premature generalization from a single case (itself an anti-pattern under Complexity). State remains `none`.
**Update needed**: None

## Stage 2: Code Quality

**Error handling** — Strong. The regenerate-on-miss is correctly nested inside the outer `try` (opened `ready.py:416`, `except Exception` at L460). `collect_items` performs unguarded `read_text`/`detect_lifecycle_phase` I/O; placing the regenerate inside the outer try means any such raise converts to the canonical `_emit_error("unexpected error: ...")` JSON contract with a stderr traceback, never an uncaught crash — exactly the spec's Technical-Constraints requirement. The `json.JSONDecodeError` branch for malformed input is preserved as a sibling except, so a present-but-corrupt index still exits 1 with a clear message. The non-list guard (L450) and the `_load_full_corpus` OSError tolerance remain unchanged.

**Naming / pattern consistency** — The lazy local `from cortex_command.backlog.generate_index import collect_items, generate_json` is appropriate: it keeps `ready.py` independent of `generate_index` on the common (index-present) hot path (matching the module's stated design intent at L78-80, "keeps ready.py independent of generate_index.py"), and only pays the import cost on the rare cache-miss path. Re-serializing via `json.loads(generate_json(items))` deliberately reuses the exact wire-record shape `ready.py` already consumes from `index.json`, so the downstream `_build_result`/`_item_payload` projection is identical for both the present and regenerated paths — no shape divergence risk. Unused tuple elements are conventionally underscore-prefixed (`_active_ids, _archive_ids, _all_items`). Signatures verified: `collect_items(...) -> tuple[list[dict], set[int], set[int], list[dict]]` (arity matches the 4-element unpack) and `generate_json(items: list[dict]) -> str` (matches `json.loads` of its output).

**Test coverage** — The new test exercises working-tree code (imports the module, monkeypatches `BACKLOG_DIR` to a tmp fixture, calls `main()` in-process), asserts all three contract facets (exit 0, `groups` present, no disk write) plus item surfacing. It mirrors the established `test_backlog_ready_render.py` tmp_path fixture pattern. One minor observation (not a defect): the test runs `main()` in-process via monkeypatch rather than the console-script-via-subprocess form noted as a pattern in the plan; the in-process form is actually the stronger choice for req 2's "exercises working-tree source, not the installed binstub" intent, and the subprocess path is independently covered by the req-11 module invocation. The docstring assertion the plan referenced (`! grep "missing or malformed input the script emits"`) is satisfied — the stale docstring clause is gone.

**Pattern consistency with non-requirements** — Correctly leaves `build_epic_map.py` un-hardened (its exit-1-on-missing is load-bearing for `dev`'s fallback), and does not touch `scan_lifecycle.py`, `dashboard/data.py`, or `overnight/backlog.py`, consistent with the spec's Non-Requirements. No broad `git add -A`/`-u`/`commit -a` was introduced.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
