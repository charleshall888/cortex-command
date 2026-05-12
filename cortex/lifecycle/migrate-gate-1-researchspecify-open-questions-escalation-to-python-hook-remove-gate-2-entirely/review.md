# Review: migrate-gate-1-researchspecify-open-questions-escalation-to-python-hook-remove-gate-2-entirely

## Stage 1: Spec Compliance

### Requirement R1: Hook script exists at canonical path with telemetry shim
- **Expected**: `bin/cortex-complexity-escalator` exists, executable, telemetry shim within first 50 lines.
- **Actual**: File present, `test -x` passes, line 21 invokes `cortex-log-invocation` via subprocess. `head -50 | grep -c 'cortex-log-invocation'` = 1.
- **Verdict**: PASS
- **Notes**: Matches the inline-shim pattern used in other `bin/cortex-*` scripts.

### Requirement R2: `--gate` parameter selects evaluation mode
- **Expected**: `--help` mentions both gate values; invalid gate exits non-zero with stderr.
- **Actual**: argparse `choices=[GATE_RESEARCH, GATE_SPECIFY]`; `--help` mentions each name three times (count = 6). Invalid gate exits 2 with stderr `invalid choice: 'invalid_gate'`. Nonexistent feature behaves per R11 graceful no-op (covered by tests).
- **Verdict**: PASS

### Requirement R3: Gate 1 algorithm (Open Questions) — top-level bullet counting
- **Expected**: Count top-level bullets (`-`, `*`, `1.` …) under `## Open Questions`; exclude nested, fenced, blockquoted. Test cases per bullet shape.
- **Actual**: `_count_top_level_bullets` implements the rules. `test_open_questions_bullet_counting` parametrized over six cases (dash, star, numbered, nested, fenced, blockquoted) — all PASS.
- **Verdict**: PASS

### Requirement R4: Gate 2 algorithm (Open Decisions) — idiom exclusions
- **Expected**: Same marker/exclusion rules plus three idiom exclusions: `^\[`, `^[Nn]one\b`, `^\([Nn]one\b`. Tests for each idiom + real-decision case.
- **Actual**: Gate-2 branch in `_count_top_level_bullets` applies all three regex checks (lines 180–187). `test_open_decisions_bullet_counting` covers template placeholder, `None.`/`none.`, `(none)`/`(None ...)`, plus real decision — all PASS.
- **Verdict**: PASS

### Requirement R5: Thresholds preserved (Gate 1 ≥2, Gate 2 ≥3)
- **Expected**: pytest cases assert thresholds; 1/2/3 effective bullets behavior.
- **Actual**: `GATE_CONFIG` sets threshold 2 / 3. `test_threshold_gate1_below/at` and `test_threshold_gate2_below/at` all PASS.
- **Verdict**: PASS

### Requirement R6: Hook skips silently when already at Complex tier
- **Expected**: Pre-existing complexity_override → exit 0, empty stdout, no event appended.
- **Actual**: `read_effective_tier` returns `"complex"`; main exits 0 before any further logic. `test_skip_when_already_complex` asserts pre/post events.log byte-equality and empty stdout — PASS.
- **Verdict**: PASS
- **Notes**: Spec named `cortex_command/common.py:read_tier()` for the API; plan deviated to in-script `read_effective_tier` for R7 coverage (documented in plan Veto Surface). Behaviorally equivalent on the skip semantic.

### Requirement R7: Three payload-shape recognition for guard
- **Expected**: Standard `{from,to}`, YAML-style bare event, test-fixture `tier` — all skip.
- **Actual**: Cascade in `read_effective_tier` (lines 84–89): prefers `tier`, then `to`, else defaults to `"complex"` for bare event. `test_skip_recognizes_payload_shape_{standard,yaml_style,tier}` all PASS.
- **Verdict**: PASS

### Requirement R8: Event emission shape with `gate` field
- **Expected**: Appended event has `ts`, `event=complexity_override`, `feature`, `from=simple`, `to=complex`, `gate=<gate-name>`.
- **Actual**: `_emit_event` assembles exactly that dict (lines 195–202). `test_event_emission_shape` validates Gate 1 fields and asserts Gate 2 sibling produces `gate=specify_open_decisions` — PASS.
- **Verdict**: PASS

### Requirement R9: Read-after-write verification before announcing
- **Expected**: On verification failure, non-zero exit, stderr names failure mode, empty stdout, no announcement.
- **Actual**: `_verify_last_event` returns `(False, "read_after_write_io_error" | "read_after_write_mismatch")`. main writes message to stderr and returns 2 before printing announcement. `test_read_after_write_failure` monkeypatches the helper and asserts exit non-zero, captured stdout empty, stderr contains `read_after_write_mismatch` — PASS.
- **Verdict**: PASS

### Requirement R10: Path-traversal hardening
- **Expected**: Regex `^[a-zA-Z0-9._-]+$` + realpath containment; on failure exit non-zero with stderr naming the slug.
- **Actual**: Lines 280–292 enforce both. Smoke test: `bin/cortex-complexity-escalator '../foo' --gate research_open_questions` → exit 2, stderr `rejected feature slug: '../foo'`. `test_path_traversal_rejection` parametrized over `../foo`, `foo/bar`, `..` plus positive case — all PASS.
- **Verdict**: PASS

### Requirement R11: Graceful no-op on missing inputs
- **Expected**: Missing artifact, missing section, empty section, below-threshold → exit 0 silent, no events.log modification.
- **Actual**: Each path returns 0 silently (artifact check L303, empty slice L313, threshold L318). Five pytest cases under `test_missing_inputs_graceful_*` all PASS.
- **Verdict**: PASS

### Requirement R12: Announcement format
- **Expected**: Exact strings `Escalating to Complex tier — research surfaced N open questions` / `... spec contains N open decisions`.
- **Actual**: Composed at L338 from `GATE_CONFIG.noun` (em dash present). `test_announcement_format_gate1` (N=4) and `_gate2` (N=5) assert exact string equality — PASS.
- **Verdict**: PASS

### Requirement R13: SKILL.md Gate 1 prose collapse with exit-code branching
- **Expected**: Replacement block at Step 3 §5; specific `grep -F` strings present; line count ≤369.
- **Actual**: `skills/lifecycle/SKILL.md` lines 259–262 contain the exact four-line replacement. Grep `cortex-complexity-escalator <feature> --gate research_open_questions` returns 1; `On non-zero exit: surface the stderr` returns 1. `wc -l` = 365 (well under 369).
- **Verdict**: PASS

### Requirement R14: SKILL.md Gate 2 prose collapse with exit-code branching
- **Expected**: Replacement at Step 3 §6 (2 lines); grep for the Gate 2 invocation; line count ≤366.
- **Actual**: Lines 264–265 contain the two-line replacement. Grep returns 1. `wc -l` = 365 ≤ 366.
- **Verdict**: PASS

### Requirement R15: Parity linter passes
- **Expected**: `bin/cortex-check-parity` exits 0; new script NOT in `bin/.parity-exceptions.md`.
- **Actual**: `bin/cortex-check-parity` exits 0. Grep of `bin/.parity-exceptions.md` for `cortex-complexity-escalator` returns no matches.
- **Verdict**: PASS

### Requirement R16: Plugin-mirror dual-source drift passes
- **Expected**: Plugin mirrors byte-identical to canonical sources.
- **Actual**: `diff bin/cortex-complexity-escalator plugins/cortex-core/bin/cortex-complexity-escalator` → no output. `diff skills/lifecycle/SKILL.md plugins/cortex-core/skills/lifecycle/SKILL.md` → no output.
- **Verdict**: PASS

### Requirement R17: Test file exists with ≥15 passing cases
- **Expected**: `tests/test_complexity_escalator.py` exists and pytest passes with ≥15 cases.
- **Actual**: `uv run pytest tests/test_complexity_escalator.py` → 35 passed in 1.65s.
- **Verdict**: PASS
- **Notes**: 35 cases (parametrization-expanded) exceeds the 15-case minimum comfortably.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality
- **Naming conventions**: Consistent. Script follows the `bin/cortex-*` shebang+telemetry-shim+stdlib-only pattern (`bin/cortex-resolve-backlog-item` precedent). Module-private helpers prefixed with `_`; public constants `GATE_RESEARCH`/`GATE_SPECIFY`/`GATE_CONFIG`/`SLUG_RE` use upper-snake. Test names follow `test_<requirement>_<scenario>` pattern matching the plan.
- **Error handling**: Appropriately scoped. Slug-validation and realpath errors exit 2 with named stderr. UnicodeDecodeError on artifact read is caught and surfaced. OSError on append exits 2 with file path. Read-after-write distinguishes IO-error vs mismatch modes per spec R9. Graceful no-ops (R11) return 0 silently on all expected absence paths.
- **Test coverage**: All verification steps from the plan executed successfully. 35 pytest cases all PASS; subprocess + importlib test mixture per `tests/test_resolve_backlog_item.py` precedent. Parity linter exit 0; plugin-mirror diffs empty; `--help` shows both gates; positive and negative slug paths exercised.
- **Pattern consistency**: Inline `log_event` idiom (per spec Technical Constraints; avoids `cortex_command/__init__.py` install_guard blast radius). `read_effective_tier` is local rather than calling `cortex_command/common.py:read_tier()` — documented deviation in plan Veto Surface; necessary to recognize the standard `{from,to}` payload that `read_tier()` is structurally blind to. The SKILL.md replacement prose uses the soft positive-routing phrasing for the fire path and imperative non-MUST phrasing for the failure path, complying with CLAUDE.md OQ3.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
