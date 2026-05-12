# Review: extract-overnight-orchestrator-round-state-read-into-bin-orchestrator-context

## Stage 1: Spec Compliance

### Requirement R1: New module `orchestrator_context.py` exporting `aggregate_round_context`
- **Expected**: Module exists; `grep -c '^def aggregate_round_context' ...` = 1; `help()` exits 0 referencing `session_dir`, `round_number`, and `dict`.
- **Actual**: Module at `cortex_command/overnight/orchestrator_context.py`. Grep = 1. `python3 -c "from ...; help(aggregate_round_context)"` exits 0, prints all three terms in Args and Returns sections.
- **Verdict**: PASS

### Requirement R2: Re-export through `orchestrator_io.py`
- **Expected**: `grep -c 'aggregate_round_context' orchestrator_io.py` ≥ 2; module source prints `cortex_command.overnight.orchestrator_context`.
- **Actual**: Count = 2 (one import, one `__all__` entry). `python3 -c "from cortex_command.overnight.orchestrator_io import aggregate_round_context; print(aggregate_round_context.__module__)"` prints `cortex_command.overnight.orchestrator_context`.
- **Verdict**: PASS

### Requirement R3: Returned dict shape — nested per-source sub-objects with `schema_version`
- **Expected**: Per accepted plan deviation, 5 top-level keys (`schema_version`, `state`, `strategy`, `escalations`, `session_plan_text`); `merge_conflict_events` dropped. Tests assert shape and types. `grep -c '"schema_version": 1' ...` ≥ 1.
- **Actual**: `orchestrator_context.py` constructs exactly these 5 keys. `test_dict_shape_returns_six_top_level_keys` asserts each key's presence and type, plus `len(result) == 5`. `"schema_version": 1` literal present (grep count = 1).
- **Verdict**: PASS
- **Notes**: Test name says "six" in the function name (a plan artifact) but the assertion and docstring both clarify it tests for 5 keys per the deviation. This is a minor cosmetic quirk, not a functional defect.

### Requirement R4: Strategy passes through unchanged
- **Expected**: `test_strategy_passthrough_no_truncation` seeds 10 `round_history_notes` entries and asserts `len(...) == 10`.
- **Actual**: Test present and passes. Implementation does `asdict(load_strategy(...))` with no filtering.
- **Verdict**: PASS

### Requirement R5: Tolerate missing input files using existing per-source defaults
- **Expected**: Missing `overnight-state.json` raises `FileNotFoundError`; missing strategy returns default instance; missing escalations returns `{"unresolved": [], "all_entries": []}`; missing session plan returns `""`.
- **Actual**: Implementation re-raises `FileNotFoundError` from `load_state` for missing state. `load_strategy` returns `OvernightStrategy()` defaults on missing file. Escalations path uses `exists()` check, returns empty dict on miss. Session plan uses `exists()` check, returns `""` on miss. `test_missing_files_use_per_source_defaults` covers all four cases and passes.
- **Verdict**: PASS

### Requirement R6: Malformed `escalations.jsonl` line tolerance
- **Expected**: Malformed line skipped, valid lines present in `all_entries`, stderr contains `WARNING`.
- **Actual**: Implementation uses `json.JSONDecodeError` catch with `print("WARNING: Skipping malformed ...", file=sys.stderr)`. `test_malformed_jsonl_line_skipped_with_warning` uses `capsys` to assert all three conditions and passes.
- **Verdict**: PASS

### Requirement R7: Rewrite `orchestrator-round.md` round-startup
- **Expected**: `aggregate_round_context` appears ≥ 1 time; `load_strategy` import/call lines removed (count = 0); cycle-breaker reads `ctx["escalations"]["all_entries"]`; `paused|round_assigned` appears ≥ 4 times; escalation cap in `sorted(ctx["escalations"]["unresolved"], ...)[:5]` form; ≥ 50 lines deleted from file-read pseudocode regions.
- **Actual**:
  - `grep -c 'aggregate_round_context' orchestrator-round.md` = 2 (Step 0b call site + Step 1 prose reference). ≥ 1: PASS.
  - `load_strategy` import/call grep = 0. PASS.
  - Awk-scoped cycle-breaker grep on `ctx["escalations"]["all_entries"]` = 1. PASS.
  - `paused|round_assigned` count = 9. ≥ 4: PASS.
  - `sorted(ctx["escalations"]["unresolved"], ...)[:5]` grep = 1. PASS.
  - Commit `fd681b8` stats: 57 deletions in the orchestrator-round.md file. ≥ 50: PASS.
  - `test_orchestrator_prompt_render.py` passes (2/2).
- **Verdict**: PASS

### Requirement R8: Schema-version check enforced in-process
- **Expected**: `_EXPECTED_SCHEMA_VERSION = 1` constant at module level; `raise RuntimeError` with `"schema_version drift"` substring; test `test_schema_version_drift_raises` fires with monkeypatched constant.
- **Actual**: `grep -cE '^_EXPECTED_SCHEMA_VERSION = 1$' ...` = 1. `grep -cE 'raise RuntimeError.*schema_version drift' ...` = 1. `test_schema_version_drift_raises` monkeypatches `_EXPECTED_SCHEMA_VERSION` to 99, asserts `RuntimeError` with match `"schema_version drift"` — passes.
- **Verdict**: PASS

### Requirement R9: Documentation
- **Expected**: `docs/overnight-operations.md` documents `aggregate_round_context` (count ≥ 1); obsolete "orchestrator reads the whole file" wording removed (count = 0); `docs/pipeline.md` cross-links (count ≥ 1).
- **Actual**: `grep -c 'aggregate_round_context' docs/overnight-operations.md` = 7. Count = 0 for the obsolete phrase. `docs/pipeline.md` contains "Round-startup state assembly is documented in `docs/overnight-operations.md` (see `aggregate_round_context`)" — count = 1.
- **Verdict**: PASS

### Requirement R10: Tests — contract fixture pinning key set
- **Expected**: `just test tests/test_orchestrator_context.py` exits 0 with ≥ 5 distinct test functions; `test_dict_top_level_keys_pinned` asserts 5-key set.
- **Actual**: `python3 -m pytest tests/test_orchestrator_context.py -v` exits 0, 6 tests pass. `grep -cE '^def test_' ...` = 6. All six required function names present (`test_dict_shape_returns_six_top_level_keys`, `test_strategy_passthrough_no_truncation`, `test_missing_files_use_per_source_defaults`, `test_malformed_jsonl_line_skipped_with_warning`, `test_schema_version_drift_raises`, `test_dict_top_level_keys_pinned`). `test_dict_top_level_keys_pinned` asserts the exact 5-key set. Full suite (`just test`) exits 0, 5/5 test files pass.
- **Verdict**: PASS

### Requirement R11: Pre-merge baseline capture
- **Expected**: `verification.md` exists with `baseline_tokens: <int>` in a fenced YAML block.
- **Actual**: `lifecycle/.../verification.md` present. `grep -cE '^baseline_tokens:' ...` = 1. The file documents the static measurement method (prompt-size analysis), the root cause of why the pipeline aggregator could not surface orchestrator-round token data (not instrumented via `dispatch_task`), and the resulting static fallback measurement of 7,063 tokens. The deviation is pre-acknowledged in the review instructions.
- **Verdict**: PASS

### Requirement R12: Post-merge observability note
- **Expected**: Informational only; not a close gate. Post-merge `post_merge_tokens`, `ratio`, `notes` fields after first overnight session. Close does not depend on this.
- **Actual**: `verification.md` notes that R12 will be appended after the first overnight session using the rewritten prompt. Not yet present — this is by design per spec ("not a close gate"; "requires a real overnight session").
- **Verdict**: PASS (informational; no close dependency)

---

## Requirements Drift

**State**: none

**Findings**:
- None

**Update needed**: None

---

## Stage 2: Code Quality

All Stage 1 requirements passed; proceeding to code quality assessment.

**Naming conventions**: Consistent with project patterns. `aggregate_round_context` follows the `verb_noun` convention used by `load_state`, `save_state`, `load_strategy`, and `write_escalation`. Module name `orchestrator_context.py` follows the `{domain}_{function}.py` pattern used by `orchestrator_io.py` and `map_results.py`. Test file at `tests/test_orchestrator_context.py` matches spec R10's placement directive and follows the project's top-level test file convention.

**Error handling**: Appropriate for the context. Missing `overnight-state.json` propagates `FileNotFoundError` from `load_state` without wrapping — consistent with the project's "exceptions propagate" pattern. Malformed JSONL uses `json.JSONDecodeError` with a `print(..., file=sys.stderr)` warning matching the style at the old inline-read code. No new exception types introduced. The schema-drift `RuntimeError` is raised inline before `return`, not in a separate validator — minimal and auditable. `load_strategy` tolerance for missing/invalid files is preserved by delegation rather than re-implemented.

**Test coverage**: Six tests covering R3 (dict shape + key count), R4 (strategy passthrough), R5 (missing-file tolerance for all four sources), R6 (malformed JSONL warning + stderr assertion), R8 (schema drift raise via monkeypatch), and R10 (contract fixture pinning the key set). The contract fixture is the most durable coverage: it breaks on additive key drift, surfacing the schema-version-bump decision at test time rather than at runtime. One minor note: `test_dict_shape_returns_six_top_level_keys` carries a misleading name (leftover from spec R10's naming before the plan deviation dropped `merge_conflict_events`); the docstring documents this discrepancy accurately, but a future rename to `test_dict_shape_returns_five_top_level_keys` would remove the inconsistency.

**Pattern consistency**: Follows existing project conventions throughout. Lock-free reads per `requirements/pipeline.md:127,134`. No in-process caching (fresh read per round per `docs/overnight-operations.md:32-33`). Atomic-write convention is not applicable (aggregator is read-only). The sanctioned import surface rule (`docs/overnight-operations.md:491-498`) is honored — `orchestrator-round.md` imports `aggregate_round_context` via `orchestrator_io`, not directly from `orchestrator_context`. The docs update follows CLAUDE.md's source-of-truth split: `overnight-operations.md` owns the new section, `pipeline.md` cross-links without duplicating content.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
