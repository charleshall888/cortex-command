# Specification: propagate-backlog-criticality-to-lifecycle-start

## Problem Statement

When `/cortex-core:refine` runs from a backlog item with non-default `criticality:` or `complexity:` frontmatter, the value silently fails to reach `cortex/lifecycle/{feature}/events.log`. The canonical state read (`cortex-lifecycle-state --field criticality`/`--field tier`) then returns the default (`medium`/`simple`), so the implement→next-phase gating matrix routes on the wrong value. Feature `discovery-output-density-investigate-author-centric` (backlog #227) was auto-routed to Complete instead of Review because of this demotion. The fix emits `lifecycle_start` as the first event in `events.log` at refine entry, with `tier` and `criticality` read from backlog frontmatter, closing the propagation gap.

## Phases

- **Phase 1: Helper module** — Build `cortex_command/refine.py` with an `emit-lifecycle-start` subcommand that reads backlog frontmatter, applies defaults, and atomically appends a `lifecycle_start` row to `events.log` (idempotent on existence). Cover with unit tests.
- **Phase 2: Skill wiring + regression** — Wire the helper into `skills/refine/SKILL.md` Step 2 (after Check State, before Clarify dispatch), update `bin/.events-registry.md` and `pyproject.toml`, and add a static wiring test that fails if refine SKILL.md no longer invokes the helper.

## Requirements

1. **Helper module produces lifecycle_start row from backlog frontmatter**: A new module `cortex_command/refine.py` exposes a `emit-lifecycle-start` subcommand. Invoked as `cortex-refine emit-lifecycle-start --backlog-slug <slug> --lifecycle-slug <slug>`, it reads `cortex/backlog/{backlog-slug}.md` frontmatter, then appends a single-line JSONL row to `cortex/lifecycle/{lifecycle-slug}/events.log` with shape `{"schema_version": 1, "ts": "<ISO 8601 Zulu>", "event": "lifecycle_start", "feature": "<lifecycle-slug>", "tier": "<simple|complex>", "criticality": "<low|medium|high|critical>", "entry_point": "refine"}`. **Acceptance**: `pytest tests/test_refine_module.py::test_emit_lifecycle_start_writes_backlog_values` exits 0; the test creates a backlog item with `criticality: high` and `complexity: complex`, runs the subcommand, and asserts the appended row carries `criticality: high` and `tier: complex`. **Phase**: Phase 1

2. **Defaults applied when backlog frontmatter is absent**: When the backlog file has no `criticality:` key, `criticality: medium` is emitted. When the backlog file has no `complexity:` key, `tier: simple` is emitted. When the `--backlog-slug` argument is omitted (Context B ad-hoc), both defaults apply (`tier: simple`, `criticality: medium`). **Acceptance**: `pytest tests/test_refine_module.py::test_emit_lifecycle_start_defaults` exits 0; covers three sub-cases — missing criticality, missing complexity, no backlog file. **Phase**: Phase 1

3. **Idempotent on existing lifecycle_start**: When `cortex/lifecycle/{lifecycle-slug}/events.log` already contains a `lifecycle_start` row, the subcommand exits 0 with no append. **Acceptance**: `pytest tests/test_refine_module.py::test_emit_lifecycle_start_idempotent` exits 0; the test pre-seeds an events.log with one `lifecycle_start` row, runs the subcommand, and asserts the file size and row count are unchanged. **Phase**: Phase 1

4. **Atomic append with read-after-write verify**: The subcommand follows `bin/cortex-complexity-escalator`'s pattern — bare `open(..., "a")` append + re-read of the last line to confirm the write landed (exit non-zero with diagnostic if verify fails). **Acceptance**: `grep -c "read_after_write" cortex_command/refine.py` ≥ 1; structural code-grep confirms the verify branch is present. **Phase**: Phase 1

5. **Invalid frontmatter values rejected with diagnostic**: When backlog `criticality:` is set but its value is not one of `low|medium|high|critical`, the subcommand exits non-zero with a clear stderr diagnostic naming the invalid value, the file path, and the allowed set. Same behavior for `complexity:` outside `simple|complex`. **Acceptance**: `pytest tests/test_refine_module.py::test_emit_lifecycle_start_rejects_invalid_value` exits 0; covers `criticality: extreme` and `complexity: medium` (wrong dimension). **Phase**: Phase 1

6. **Console-script entry registered**: `pyproject.toml`'s `[project.scripts]` table contains `cortex-refine = "cortex_command.refine:main"`. **Acceptance**: `grep -c '^cortex-refine = "cortex_command.refine:main"$' pyproject.toml` = 1. **Phase**: Phase 1

7. **Refine SKILL.md invokes the helper at the canonical site**: `skills/refine/SKILL.md` Step 2 (Check State), at the END of the step after the resume-point decision tree but BEFORE Step 3 (Clarify Phase), contains a prose instruction directing the model to invoke `cortex-refine emit-lifecycle-start --backlog-slug {backlog-filename-slug} --lifecycle-slug {lifecycle-slug}` unconditionally for Context A (skipped for Context B since no backlog-slug exists, but still invokable with defaults). **Acceptance**: `grep -c "cortex-refine emit-lifecycle-start" skills/refine/SKILL.md` ≥ 1. **Phase**: Phase 2

8. **Static wiring test catches regressions**: A new test `tests/test_refine_lifecycle_start_wiring.py` asserts that `skills/refine/SKILL.md` contains the literal `cortex-refine emit-lifecycle-start` at least once. **Acceptance**: `pytest tests/test_refine_lifecycle_start_wiring.py` exits 0; deleting the call from refine SKILL.md fails the test. **Phase**: Phase 2

9. **Producers column updated in events-registry**: The `lifecycle_start` row in `bin/.events-registry.md` has its `producers` cell extended with `cortex_command/refine.py:<line>` (specific line at the subcommand's append site). **Acceptance**: `grep -E "^\| .lifecycle_start.* cortex_command/refine\.py" bin/.events-registry.md` exits 0. **Phase**: Phase 2

10. **Refine §5 transition prose updated for the carve-out**: `skills/refine/SKILL.md` §5 (currently "does not log phase transitions") is reworded to specify "does not log `phase_transition` events" and explicitly acknowledges that refine emits `lifecycle_start` as a session-start sentinel. This narrows the scope of the rule without inviting future event-emit additions. **Acceptance**: `grep -c "phase_transition" skills/refine/SKILL.md` ≥ 1 (the precise event name appears) AND `grep -c "lifecycle_start" skills/refine/SKILL.md` ≥ 1. **Phase**: Phase 2

11. **Backlog 227 regression scenario covered**: The unit-test suite includes a scenario that mirrors backlog #227 — a backlog item with `criticality: high` and `complexity: simple` (note: 227 was simple-tier high-crit). After the helper runs, `cortex-lifecycle-state --feature <slug> --field criticality` (or the equivalent `read_criticality` function in `cortex_command/common.py`) returns `high`. **Acceptance**: `pytest tests/test_refine_module.py::test_emit_lifecycle_start_matches_227_repro_scenario` exits 0. **Phase**: Phase 1

## Non-Requirements

- **No drift detection.** This spec does NOT handle the case where backlog `criticality:` is edited between two refine invocations on the same lifecycle. The helper is idempotent on existence (skip if any `lifecycle_start` row present); a manual `criticality_override` event remains the user's affordance for mid-lifecycle changes per `skills/lifecycle/references/criticality-matrix.md:11`. A follow-up ticket may add drift detection if real-world usage demonstrates need.
- **No retrofit for in-flight lifecycles.** Existing lifecycles whose `events.log` already lacks `lifecycle_start` are not corrected. The ticket marked retrofit "Optional"; this spec keeps it out of scope. File a separate backlog item if needed.
- **No fix for `orchestrator-round.md:256` criticality_override read bug.** Research surfaced an adjacent defect where `cortex_command/overnight/prompts/orchestrator-round.md:256` reads `entry.get("criticality")` instead of `entry.get("to")` for `criticality_override` events. This is required for the "user-final at every downstream gate" claim to hold for override events, but is a separate ticket.
- **No change to clarify §5 or §7.** Clarify continues to rederive criticality and write back to backlog independently. The new helper does NOT seed from clarify or modify clarify behavior.
- **No removal of the existing lifecycle SKILL.md §3 step 4 emit prose.** Once the refine helper runs at Step 2, the lifecycle prose emit is redundant for refine-driven flows but remains the fallback for any future entry-point that does not go through refine. (If lifecycle SKILL.md ends up calling refine for every entry-point, the lifecycle prose can be removed in a follow-up; out of scope here.)
- **No new schema_version on `criticality_override` or `complexity_override`.** Only the new `lifecycle_start` emit carries `schema_version: 1`. Existing override emit sites are unchanged.

## Edge Cases

- **Backlog file missing or unreadable**: The subcommand exits non-zero with a clear diagnostic naming the expected path. Refine SKILL.md's prose should not crash the lifecycle in this case — the existing Step 1 input-resolution already exits 70 on IO failure; this helper failing after that point is an internal consistency error, not a user-facing failure mode.
- **Lifecycle directory does not exist yet**: The subcommand creates `cortex/lifecycle/{lifecycle-slug}/` and `events.log` atomically (mkdir parents=True). This matches the existing `_emit_event` pattern in `bin/cortex-complexity-escalator:194`.
- **`events.log` exists but is empty**: Treat as no existing `lifecycle_start` row — append normally.
- **`events.log` contains malformed JSON on prior lines**: Skip unparseable lines silently when scanning for an existing `lifecycle_start` (mirrors `cortex_command/common.py:_read_criticality_inner:435-436` tolerance). Append the new row regardless.
- **Concurrent invocation**: Bare-append + read-after-write verify catches torn writes. Two simultaneous invocations may both write `lifecycle_start` if they race past the idempotency scan; `cortex_command/pipeline/metrics.py:222` (first-wins) handles this — the second emit is shadowed for tier reads. Acceptable tradeoff for a once-per-lifecycle helper; rare in practice.
- **Context B (ad-hoc, no backlog)**: The helper accepts a missing `--backlog-slug` argument and emits with defaults (`tier: simple`, `criticality: medium`). Refine SKILL.md should invoke it without `--backlog-slug` in Context B paths.
- **Permission denied on `events.log`**: Catch `PermissionError`/`OSError` and exit non-zero with a diagnostic mentioning sandbox registration (`cortex init`).
- **schema_version field on read**: The new emit carries `schema_version: 1`. Existing readers (`cortex_command/common.py:_read_criticality_inner`) ignore unknown fields, so this is forward-compatible without any reader change.

## Changes to Existing Behavior

- **MODIFIED**: `skills/refine/SKILL.md` Step 2 (Check State) — adds a final paragraph instructing invocation of `cortex-refine emit-lifecycle-start` before Step 3 (Clarify) dispatch.
- **MODIFIED**: `skills/refine/SKILL.md` §5 (Transition) — rewords "does not log phase transitions" to "does not log `phase_transition` events" and acknowledges the `lifecycle_start` carve-out.
- **ADDED**: `cortex_command/refine.py` module with `emit-lifecycle-start` subcommand.
- **ADDED**: `pyproject.toml` `[project.scripts]` entry `cortex-refine = "cortex_command.refine:main"`.
- **ADDED**: `tests/test_refine_module.py` (unit tests) and `tests/test_refine_lifecycle_start_wiring.py` (static wiring test).
- **MODIFIED**: `bin/.events-registry.md` `lifecycle_start` row — `producers` column extended with `cortex_command/refine.py:<line>`.

## Technical Constraints

- **Event-emit pattern** (per `bin/cortex-complexity-escalator:192-235`): bare `open(events_log_path, "a")` append of a single JSONL line + read-after-write verify by re-reading the last line and comparing event-name/key-fields. Atomicity for sub-PIPE_BUF lines is OS-guaranteed; verify catches torn writes.
- **Canonical reader compatibility** (per `cortex_command/common.py:_read_criticality_inner:425-448` and `_read_tier_inner:497-521`): emit shape must include `event: "lifecycle_start"`, `tier: <str>`, `criticality: <str>`. Additional fields (`schema_version`, `ts`, `feature`, `entry_point`) are tolerated. `cortex_command/pipeline/metrics.py:222` uses `start_events[0]["tier"]` (first-wins, KeyError on missing `tier`) — both fields must be present.
- **Frontmatter parser** (per `cortex_command/backlog/update_item.py:39-53` `_get_frontmatter_value`): regex-based stdlib reader, no PyYAML dependency. Reuse this helper rather than reintroducing yaml.safe_load.
- **Console-script pattern** (per `cortex_command/discovery.py` + `pyproject.toml:35`): emit-* subcommands under a `cortex-<skill>` console-script entry. Subparser dispatch via `argparse`. `main(argv: list[str] | None = None) -> int` signature.
- **Test pattern** (per `tests/test_discovery_module.py`): unit-test scenarios import directly from `cortex_command.refine`; subprocess scenarios use `subprocess.run([sys.executable, "-m", "cortex_command.refine", ...])` with `tmp_path` fixtures. No CORTEX_BACKLOG_DIR env-var dependency needed if the helper accepts explicit `--backlog-slug` and `--lifecycle-slug` arguments.
- **Events-registry gate** (per `docs/internals/events-registry.md`): `lifecycle_start` is already registered with `gate-enforced` scan coverage. Adding the refine SKILL.md emit literal requires no new registry row, but the `producers` column should be updated for documentation.
- **MUST-escalation policy** (per `CLAUDE.md` lines 72-81): new SKILL.md prose uses soft positive-routing phrasing ("Invoke `cortex-refine emit-lifecycle-start`…") rather than MUST/REQUIRED. No evidence artifact justifies escalation.
- **Plugin distribution** (per ADR-0002): `[project.scripts]` entries are CLI-wheel-only. Skills that invoke them assume the CLI wheel is installed alongside the plugin. This matches the existing pattern for `cortex-discovery`, `cortex-update-item`, `cortex-create-backlog-item` invoked from skill prose. No `bin/` shim needed.

## Open Decisions

None. All design choices were resolved during Clarify and Research with research recommendations applied directly to the spec body.

## Proposed ADR

None considered.
