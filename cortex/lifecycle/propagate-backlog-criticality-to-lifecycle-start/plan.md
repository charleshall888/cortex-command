# Plan: propagate-backlog-criticality-to-lifecycle-start

## Overview

Build `cortex_command/refine.py` exposing a `cortex-refine emit-lifecycle-start` console-script subcommand that reads backlog frontmatter, applies defaults, and atomically appends a `lifecycle_start` row to `events.log` (idempotent on existence). Wire the helper into `skills/refine/SKILL.md` Step 2 so every refine invocation produces the seed event before clarify_critic runs. Guard the wiring with a static regression test that fails if the SKILL.md call site is deleted.
**Architectural Pattern**: plug-in
<!-- The helper is a discrete plug-in to the refine clarify flow: a new console-script entry that the skill prose invokes once at Step 2. It composes alongside the existing cortex-resolve-backlog-item / cortex-update-item ceremony without modifying any other skill or subsystem. -->

## Outline

### Phase 1: Helper module + tests (tasks: 1, 2, 3, 4)
**Goal**: Produce a unit-tested `cortex_command/refine.py` with an `emit-lifecycle-start` subcommand whose behavior matches all 11 spec acceptance criteria when invoked directly.
**Checkpoint**: `pytest tests/test_refine_module.py` exits 0; `cortex-refine emit-lifecycle-start --help` exits 0 after `pip install -e .` (or equivalent).

### Phase 2: Skill wiring + regression guard (tasks: 5, 6, 7)
**Goal**: Wire the helper invocation into `skills/refine/SKILL.md`, update `bin/.events-registry.md` producers, and add a static wiring test that catches a missing call site.
**Checkpoint**: `pytest tests/test_refine_lifecycle_start_wiring.py` exits 0; `grep -c "cortex-refine emit-lifecycle-start" skills/refine/SKILL.md` ≥ 1; `grep -c "cortex_command/refine\.py" bin/.events-registry.md` ≥ 1.

## Tasks

### Task 1: Scaffold cortex_command/refine.py module and console-script entry
- **Files**: `cortex_command/refine.py`, `pyproject.toml`
- **What**: Create `cortex_command/refine.py` with an `argparse`-based `main(argv: list[str] | None = None) -> int` function that dispatches to subcommands via `subparsers.required = True`. Add the `emit-lifecycle-start` subparser accepting `--backlog-slug` (optional string) and `--lifecycle-slug` (required string). Stub the handler to return 0. Add `cortex-refine = "cortex_command.refine:main"` to `pyproject.toml`'s `[project.scripts]` table immediately after the `cortex-pipeline-metrics` entry to preserve alphabetical ordering.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Mirror `cortex_command/discovery.py`'s `_build_parser` (lines 1027-1206) and `main` (lines 1207+) — same argparse pattern, same subcommand layout, same `int` return convention. Argparse subcommand signature: `sub.add_parser("emit-lifecycle-start", help="...")`. Console-script entries in `pyproject.toml` follow the `cortex-<name> = "cortex_command.<module>:main"` pattern visible at lines 22-41.
- **Verification**: `python3 -c "from cortex_command.refine import main; import sys; sys.exit(main(['emit-lifecycle-start', '--help']))"` — pass if exit 0. Also `grep -c '^cortex-refine = "cortex_command.refine:main"$' pyproject.toml` = 1 — pass if count = 1.
- **Status**: [x] completed (commit 60ed781f)

### Task 2: Implement backlog frontmatter reader with defaults and validation
- **Files**: `cortex_command/refine.py`
- **What**: Add a private helper `_read_backlog_frontmatter(backlog_slug: str | None) -> tuple[str, str]` that returns `(tier, criticality)`. When `backlog_slug` is None or the backlog file does not exist, return `("simple", "medium")`. When the file exists, read `cortex/backlog/{backlog_slug}.md` and extract `criticality:` and `complexity:` via `_get_frontmatter_value` from `cortex_command.backlog.update_item`. Apply defaults (`simple`/`medium`) for absent keys. Validate `criticality ∈ {low, medium, high, critical}` and `complexity ∈ {simple, complex}`; on invalid value, print a stderr diagnostic naming the invalid value, file path, and allowed set, then exit 64 (usage error).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: `_get_frontmatter_value(text: str, key: str) -> str | None` lives in `cortex_command/backlog/update_item.py:39-53` — regex-based stdlib reader, no PyYAML dependency. Allowed criticality values come from the canonical state read at `cortex_command/common.py:_read_criticality_inner:425-448`. Allowed tier values come from `cortex_command/common.py:_read_tier_inner:497-521`. Backlog file path convention: `cortex/backlog/{slug}.md` resolved against repo root via `git rev-parse --show-toplevel` or `Path.cwd()` (the existing `_parse_frontmatter` in `bin/cortex-resolve-backlog-item:56-72` uses repo-relative paths via working directory).
- **Verification**: Phase 1 Checkpoint — Task 4's pytest unit tests will exercise this helper directly. Standalone: `python3 -c "from cortex_command.refine import _read_backlog_frontmatter; print(_read_backlog_frontmatter(None))"` outputs `('simple', 'medium')` — pass if output matches.
- **Status**: [x] completed (commit e8521217)

### Task 3: Implement idempotency scan, atomic append, and read-after-write verify
- **Files**: `cortex_command/refine.py`
- **What**: Add a private helper `_lifecycle_start_present(events_log: Path) -> bool` that returns True when the file exists and any line parses as JSON with `event == "lifecycle_start"`. Skip unparseable lines silently (mirrors `_read_criticality_inner:435-436`). Implement the `emit-lifecycle-start` subcommand handler: (a) compute `events_log = Path("cortex/lifecycle") / lifecycle_slug / "events.log"`; (b) call `events_log.parent.mkdir(parents=True, exist_ok=True)`; (c) if `_lifecycle_start_present(events_log)`, exit 0 silently; (d) call `_read_backlog_frontmatter(backlog_slug)` to get (tier, criticality); (e) construct the row dict `{"schema_version": 1, "ts": _now_iso(), "event": "lifecycle_start", "feature": lifecycle_slug, "tier": tier, "criticality": criticality, "entry_point": "refine"}`; (f) open the file `"a"` mode and append `json.dumps(row) + "\n"`; (g) re-read the last line and assert it parses as JSON with matching `event`, `tier`, `criticality` — on read_after_write mismatch, print "read_after_write_mismatch" to stderr and exit 70 (IO error). Catch `PermissionError`/`OSError` around the open/write and exit 70 with a diagnostic mentioning `cortex init` sandbox registration.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Pattern source — `bin/cortex-complexity-escalator:192-235` (`_emit_event` + `_verify_last_event`). Reuse the same bare-append + last-line re-read pattern. `_now_iso()` can be a one-liner: `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`. Keep the JSON key order as listed above for grep stability (schema_version, ts, event, feature, tier, criticality, entry_point). The read_after_write_mismatch literal "read_after_write" appears in the source — R4 acceptance grep depends on this.
- **Verification**: `grep -c "read_after_write" cortex_command/refine.py` ≥ 1 — pass if count ≥ 1. End-to-end: Task 4's tests exercise the full subcommand flow.
- **Status**: [x] completed (commit 0985da20)

### Task 4: Write tests/test_refine_module.py covering all 11 spec acceptance scenarios
- **Files**: `tests/test_refine_module.py`
- **What**: Write a pytest module that imports from `cortex_command.refine` and covers the following test functions: `test_emit_lifecycle_start_writes_backlog_values` (backlog `criticality: high` + `complexity: complex` → row matches), `test_emit_lifecycle_start_defaults` (parametrized: missing criticality, missing complexity, no backlog file → defaults applied), `test_emit_lifecycle_start_idempotent` (pre-seeded events.log with one lifecycle_start row → second invocation no-ops, file size and row count unchanged), `test_emit_lifecycle_start_rejects_invalid_value` (parametrized: `criticality: extreme`, `complexity: medium` → non-zero exit with diagnostic), `test_emit_lifecycle_start_matches_227_repro_scenario` (backlog with `criticality: high` + `complexity: simple` → `read_criticality` returns "high" and `read_tier` returns "simple"). Use `tmp_path` fixtures with `monkeypatch.chdir(tmp_path)` to control the events.log and backlog paths. Tests call `main(["emit-lifecycle-start", "--backlog-slug", "234-foo", "--lifecycle-slug", "feat"])` directly (no subprocess overhead) and assert against the resulting events.log content via `json.loads` of each line.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Test pattern source — `tests/test_discovery_module.py` (lines 137-280 show emit-* test scenarios using direct function imports and `tmp_path`-based fixtures). `tests/test_common_utils.py:150-210` shows `read_criticality(feature, lifecycle_base=tmp_path)` invocation pattern. Import `read_criticality` and `read_tier` from `cortex_command.common` for the 227-repro test. Backlog frontmatter format: standard YAML between `---` delimiters at file head.
- **Verification**: `pytest tests/test_refine_module.py -v` — pass if exit 0 and all 5 test functions show PASSED.
- **Status**: [x] completed (commit 255bc007)

### Task 5: Wire helper invocation and update §5 prose in skills/refine/SKILL.md
- **Files**: `skills/refine/SKILL.md`
- **What**: Two edits to the same file. **Edit A**: At the end of Step 2 (Check State), after the resume-point decision tree and before "## Step 3: Clarify Phase" begins, insert a paragraph: "After determining the resume point, invoke `cortex-refine emit-lifecycle-start --backlog-slug {backlog-filename-slug} --lifecycle-slug {lifecycle-slug}` (omit `--backlog-slug` for Context B) so `events.log` carries the seed `lifecycle_start` row before any other event is logged. The subcommand is idempotent — safe on resume." **Edit B**: In §5 (Transition) of the spec adaptation block — the current text reads "Skip — /cortex-core:refine does not log phase transitions… the caller (/cortex-core:lifecycle) owns phase-transition logging and commit-artifacts." Reword to: "Skip the `phase_transition` event emission — /cortex-core:refine does not log `phase_transition` events; the caller (/cortex-core:lifecycle) owns phase-transition logging and commit-artifacts. The `lifecycle_start` session-start sentinel emitted at Step 2 is a deliberate carve-out from this rule and is owned by refine."
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: refine SKILL.md Step 2 ends with the resume-point decision tree (look for the `if/elif/else` block ending with `resume = clarify phase`). The §5 transition adaptation is in the bullet list under "Read /Users/charlie.hall/.claude/plugins/cache/cortex-command/cortex-core/44306f127714/skills/refine/../lifecycle/references/specify.md and follow it (its full protocol) with these adaptations:". Both literals `cortex-refine emit-lifecycle-start` and `lifecycle_start` plus `phase_transition` must appear in the file post-edit for R7 and R10 acceptance.
- **Verification**: `grep -c "cortex-refine emit-lifecycle-start" skills/refine/SKILL.md` ≥ 1 AND `grep -c "phase_transition" skills/refine/SKILL.md` ≥ 1 AND `grep -c "lifecycle_start" skills/refine/SKILL.md` ≥ 1 — pass if all three counts are ≥ 1.
- **Status**: [x] completed (commit 56c2652c)

### Task 6: Add static wiring test that fails on missing call site
- **Files**: `tests/test_refine_lifecycle_start_wiring.py`
- **What**: A single-function pytest module that reads `skills/refine/SKILL.md` and asserts the literal string `cortex-refine emit-lifecycle-start` appears at least once. The test resolves the SKILL.md path relative to `git rev-parse --show-toplevel` to stay robust to test invocation directory. Test name: `test_refine_skill_wires_emit_lifecycle_start`. On failure, the assertion message should explicitly say "refine SKILL.md no longer invokes cortex-refine emit-lifecycle-start; the session-start sentinel will not fire" so future developers understand what regressed.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: Pattern reference — `tests/test_lifecycle_kept_pauses_parity.py` reads SKILL.md files and asserts structural properties. Use `subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip()` for repo root resolution.
- **Verification**: `pytest tests/test_refine_lifecycle_start_wiring.py -v` — pass if exit 0. Sanity check: temporarily remove the literal from skills/refine/SKILL.md (do NOT commit) and rerun the test — it must fail; then restore.
- **Status**: [x] completed (commit c1bfe55a; sanity-check verified)

### Task 7: Update bin/.events-registry.md producers column for lifecycle_start
- **Files**: `bin/.events-registry.md`
- **What**: Find the `| `lifecycle_start` | ...` row and extend the `producers` cell. Current value: `` `skills/lifecycle/SKILL.md`; `cortex_command/dashboard/seed.py:506` ``. New value: append `; `cortex_command/refine.py:<line>`; `skills/refine/SKILL.md`` where `<line>` is the line number where the `lifecycle_start` JSONL literal is constructed inside `cortex_command/refine.py` (i.e., where `"event": "lifecycle_start"` appears). Use the exact line number from the implemented file.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: Existing entries follow the `path:line` convention for Python producers and bare `path` for skill prompts (see `phase_transition` row at the top of `bin/.events-registry.md` which lists `cortex_command/pipeline/review_dispatch.py:190,281,529`). The `cortex-check-events-registry --audit` gate checks scan-surface presence; producer-list completeness is documentation discipline, not gate-enforced. Use grep on the cortex_command/refine.py file to find the line: `grep -n '"event": "lifecycle_start"' cortex_command/refine.py`.
- **Verification**: `grep -E "^\\| .lifecycle_start.* cortex_command/refine\\.py" bin/.events-registry.md` exits 0 — pass if exit 0. Also `bin/cortex-check-events-registry --audit` exits 0 — pass if exit 0.
- **Status**: [x] completed (bundled in commit c1bfe55a; --audit exits 0)

## Risks

- **lru_cache invalidation in same-process emit-then-read scenarios**: `cortex_command/common.py:read_criticality` is `@lru_cache(maxsize=128)` keyed on `(path, exists, mtime_ns, size)`. The test harness imports `read_criticality` and may have already populated the cache with `exists=False` before the helper emits. Tests must either clear the cache (`read_criticality.cache_clear()`) between operations or rely on the mtime_ns/size key change to trigger invalidation naturally. Flagging because forgetting this is a common test-flake source.
- **Backlog frontmatter parser divergence**: Reusing `_get_frontmatter_value` from `cortex_command/backlog/update_item.py` means any bug in that regex (e.g., not handling multi-line values, BOM, CRLF) propagates to refine. The parser is regex-based stdlib (no PyYAML), which is intentional for ADR-0001-aligned simplicity but means edge cases like quoted values or list-shape values for `tags:` are not handled. The spec's R5 (invalid value rejection) implicitly tests that single-string values parse correctly; multi-line/list-valued criticality is out of spec.
- **Schema_version conflict with existing readers**: `cortex_command/common.py:_read_criticality_inner` only checks `event` and `criticality` fields — it tolerates `schema_version: 1` as an unknown key. But `cortex_command/pipeline/metrics.py:222-223` uses `start_events[0]["tier"]` (KeyError on missing `tier`); the spec mandates both fields are present, so this is safe. Future readers adding stricter schema_version checks could break — but that's a forward-compat decision out of scope here.
- **Plugin install without CLI wheel**: ADR-0002 splits CLI wheel and plugin distribution. Skills invoking `cortex-refine` assume the CLI wheel is installed. A plugin-only install would fail. This matches the existing pattern (skills already invoke `cortex-discovery`, `cortex-update-item`), but worth flagging as a known constraint.
- **The deliberate non-fix of `orchestrator-round.md:256`**: The spec excludes the criticality_override read-bug fix at `cortex_command/overnight/prompts/orchestrator-round.md:256`. Until that fix lands separately, the "user-final at every downstream gate" claim holds only for the initial seed value — manually-emitted criticality_override events are silently ignored by the orchestrator's planning fan-out. Captured as Non-Requirement #3 in the spec; revisit if the follow-up ticket gets prioritized.

## Acceptance

After Phase 2 completes: the canonical bug repro scenario — a fresh backlog item with `criticality: high` and `complexity: simple` running through `/cortex-core:refine` — produces an `events.log` whose first JSON event is `lifecycle_start` with `criticality: "high"` and `tier: "simple"`, and `cortex-lifecycle-state --feature <slug> --field criticality` returns `high`. The wiring test `tests/test_refine_lifecycle_start_wiring.py` fails if the refine SKILL.md call site is deleted, and `pytest tests/test_refine_module.py` exercises all five test functions corresponding to spec R1, R2, R3, R5, R11. `bin/cortex-check-events-registry --audit` exits 0 with the updated producers column.
