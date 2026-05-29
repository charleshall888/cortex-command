# Review: retire-or-re-establish-the-orphaned

## Stage 1: Spec Compliance

### Requirement 1: `architecture_section_written` event, `emit_architecture_written`, `emit-architecture-written` subcommand, `has_why_n_justification` field/flag, and the now-dead `_coerce_bool_namespace` helper fully removed from `cortex_command/discovery.py`
- **Expected**: `grep -c 'architecture_section_written\|has_why_n_justification\|emit-architecture-written' cortex_command/discovery.py` = 0 AND `grep -c '_coerce_bool_namespace' cortex_command/discovery.py` = 0.
- **Actual**: Both greps return 0. The module no longer defines `emit_architecture_written`, its dispatcher, its subparser, the `--has-why-n-justification` flag, or `_coerce_bool_namespace`. The module imports and `--help` exits 0.
- **Verdict**: PASS
- **Notes**: The plan's dead-residue extension is also satisfied: `grep -c '_validate_architecture_payload\|_validate_prescriptive_payload\|_STATUS_VALUES' cortex_command/discovery.py` = 0, so the two orphaned validators and the `_STATUS_VALUES` frozenset (none of whose names contain a retired event token) were removed alongside the spec-named helper. discovery.py shed 264 lines.

### Requirement 2: `prescriptive_check_run` event, `emit_prescriptive_check`, and `emit-prescriptive-check` subcommand fully removed
- **Expected**: `grep -c 'prescriptive_check_run\|emit-prescriptive-check' cortex_command/discovery.py` = 0.
- **Actual**: Returns 0. Function, dispatcher, and subparser are gone.
- **Verdict**: PASS
- **Notes**: The operator-ratified scope expansion to the second orphan landed as specced.

### Requirement 3: Both orphaned event rows hard-deleted from `bin/.events-registry.md` (no tombstone)
- **Expected**: `grep -c 'architecture_section_written\|prescriptive_check_run' bin/.events-registry.md` = 0.
- **Actual**: Returns 0. No `deprecated-pending-removal` tombstone row was added for either event (consistent with the hard-delete decision).
- **Verdict**: PASS

### Requirement 4: Surviving `approval_checkpoint_responded` row preserved; dangling consumer reference repointed off the nonexistent `tests/test_discovery_events.py`
- **Expected**: `grep -c 'approval_checkpoint_responded' bin/.events-registry.md` = 1 AND `grep -c 'test_discovery_events.py' bin/.events-registry.md` = 0.
- **Actual**: Both hold (1 and 0). Row 115 now points `consumers` at `tests/test_discovery_module.py (tests-only)`; the file `tests/test_discovery_events.py` confirmed nonexistent. Row's `category` (`audit-affordance`), rationale, owner, and other cells unchanged.
- **Verdict**: PASS

### Requirement 5: Stale `### Why N pieces` heading removed from the one fixture that carried it
- **Expected**: `grep -c '### Why N pieces' tests/fixtures/discovery-brief/complex-topic/research.md` = 0 AND `grep -rc '### Why N pieces' tests/fixtures/discovery-brief/` totals 0.
- **Actual**: 0 in the complex-topic fixture; repo-wide total across all three fixtures = 0. The fixture retains `### Pieces` and `### Seam-level edges`, so `test_discovery_gate_brief.py`'s assertions are unaffected.
- **Verdict**: PASS

### Requirement 6: Dead-path test functions removed; `has_why_n_justification` assertions stripped; CLI-help test no longer asserts removed subcommands; degenerate multi-emitter parity test retired with a dedicated single-emitter override-delegation replacement
- **Expected**: `just test` exits 0 AND `grep -c 'architecture_section_written\|prescriptive_check_run' tests/test_discovery_module.py` = 0; the override-delegation property remains covered.
- **Actual**: Grep returns 0. The module-scope imports now bring in only `emit_checkpoint_response` and `resolve_events_log_path`. The retired multi-emitter test `test_emit_subcommands_honor_resolve_events_log_path` is gone; its surviving single-emitter property is covered by the dedicated `test_emit_checkpoint_response_honors_resolve_events_log_path` (lines 277-311), which sets `LIFECYCLE_SESSION_ID`, writes a `.session` file, calls `emit_checkpoint_response`, asserts the returned target equals `feature_dir / "events.log"` (the lifecycle path), and asserts the research-path file is never created. The CLI-help test asserts only `resolve-events-log-path` and `emit-checkpoint-response`. Change-relevant suite (`test_discovery_module.py`, `test_discovery_gate_brief.py`, `test_discovery_gate_presentation.py`) = 86 passed, 2 skipped (SDK-gated).
- **Verdict**: PASS
- **Notes**: The critical-review fix is genuinely covered, not dropped. The replacement is a true single-emitter override-delegation test asserting the returned path value (not just `.exists()`), distinct from the three pre-existing `test_emit_checkpoint_response_*` tests that run with the env override unset.

### Requirement 7: Events-registry gates pass after removals and repoint
- **Expected**: `just check-events-registry` exits 0 AND `just check-events-registry-audit` exits 0.
- **Actual**: Both exit 0.
- **Verdict**: PASS

### Requirement 8: Retirement recorded under the existing `## [Unreleased]` section of `CHANGELOG.md`, noting Tolerant-Reader compatibility
- **Expected**: `grep -c 'architecture_section_written' CHANGELOG.md` ≥ 1 AND the entry sits between `## [Unreleased]` and the next `## [` heading.
- **Actual**: Count = 1, at line 89. `## [Unreleased]` is line 48; the next `## [` heading after it is `## [v0.1.0]` at line 91. The entry (89) is strictly between (48 < 89 < 91), not inside a shipped block. The entry explicitly notes Tolerant-Reader compatibility of already-archived event-log rows (no Python reader parses these names; readers tolerate unknown types; one archived row carries a now-invalid status value) and that historical logs are not migrated.
- **Verdict**: PASS

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality
- **Naming conventions**: Consistent. The surviving `emit_checkpoint_response` / `_validate_checkpoint_payload` / `_cmd_emit_checkpoint_response` / `emit-checkpoint-response` family follows the module's established naming pattern. New test `test_emit_checkpoint_response_honors_resolve_events_log_path` matches the existing `test_*` granular-per-scenario convention documented in the module docstring.
- **Error handling**: Unchanged on the surviving path — `_cmd_emit_checkpoint_response` still distinguishes `ValueError` (exit 2, validation) from `OSError` (exit 2, append failure) and `emit_checkpoint_response` still validates before resolving the path. No error-handling surface was weakened by the deletions.
- **Test coverage**: The plan's verification steps were executed and pass. Critically, the retired multi-emitter path-routing test was replaced by a dedicated single-emitter override-delegation test (lines 277-311) that sets `LIFECYCLE_SESSION_ID`, calls `emit_checkpoint_response`, and asserts the returned target equals the lifecycle `events.log` (and that the research path is NOT created) — the exact critical-review property, covered for real rather than folded into the env-unset checkpoint tests. Module imports + `--help` succeed; `test_check_events_registry.py` (9 passed), `test_backlog_grep_targets_resolve.py` (3 passed), and the three discovery test files all pass. Repo-wide grep finds no dangling reference to any removed function/token outside historical lifecycle/research artifacts and the CHANGELOG. The backlog-grep-target constraint (Technical Constraints) is honored — no `grep -c` Done-When targeting a retired token exists in `cortex/backlog/270-*.md`.
- **Pattern consistency**: Hard-delete (no tombstone) is consistent with the spec's stated approach and with project.md's historical-compatibility-shim pattern (L37), which governs deleted *pipeline modules* with archived-log Python readers — explicitly inapplicable here, as no Python reader parses these discovery event names. The surviving `approval_checkpoint_responded` path is fully intact (emitter, validator, dispatcher, subparser, and registry row all preserved; only the dangling consumer cell corrected). The diff is contained to exactly the declared changed files plus lifecycle bookkeeping artifacts. Note: the pre-existing `_has_rerun_suffix` helper is callerless, but it was already callerless on `main` (not introduced or worsened by this change) and was correctly left out of scope.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
