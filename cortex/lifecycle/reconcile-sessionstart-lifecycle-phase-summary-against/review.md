# Review: reconcile-sessionstart-lifecycle-phase-summary-against

## Stage 1: Spec Compliance

### Requirement 1: Detector recognizes `feature_paused`
- **Expected**: `_detect_lifecycle_phase_inner` in `cortex_command/common.py` returns the derived ladder phase with `-paused` suffix when the most-recent significant event (line-position) is `feature_paused`; suffix NOT applied when a later `phase_transition` resumes; `paused-then-resumed` fixture verifies the resume case.
- **Actual**: `cortex_command/common.py:263-297` tracks `last_significant_event` across events.log lines, sets `paused = last_significant_event == "feature_paused"`, and `_result()` (lines 299-311) appends `-paused` to non-terminal phases. Terminal phases (`complete`, `escalated`) are explicitly excluded from suffixing. Fixtures at `tests/fixtures/lifecycle_phase_parity/paused-implement`, `paused-review`, `paused-then-resumed` exist; parity tests pass.
- **Verdict**: PASS
- **Notes**: Six paused parity tests collected and passing (statusline_ladder + hook_end_to_end x three fixtures).

### Requirement 2: `_encode_phase` carries progress through `-paused` suffix
- **Expected**: `_encode_phase("implement-paused", 3, 5, 0)` returns `"implement-paused:3/5"`; `review-paused` returns bare `review-paused`.
- **Actual**: `cortex_command/hooks/scan_lifecycle.py:68-75` strips `-paused` suffix, switches on `base_phase`, re-appends `-paused` before the payload. Test `test_encode_paused` at `tests/test_hooks_scan_lifecycle.py:1105` asserts all four cases including `implement-rework-paused:2`.
- **Verdict**: PASS

### Requirement 3: `_phase_label` renders `-paused` suffix
- **Expected**: `implement-paused:3/5` → `Implement (3/5 tasks done) — paused`; `review-paused` → `Review — paused`.
- **Actual**: `cortex_command/phase_labels.py:46-50` strips `-paused` (bare and compound forms), recursively computes base label, appends ` — paused`. `_phase_label` in `scan_lifecycle.py:78-90` delegates to it. Test `test_label_paused` covers all three label forms.
- **Verdict**: PASS

### Requirement 4: Statusline bash mirror updated
- **Expected**: `claude/statusline.sh` gains `feature_paused` rung; bash mirror computes same `{phase}-paused` value as Python; parity test passes on new and pre-existing fixtures.
- **Actual**: `claude/statusline.sh:407-419` scans full events.log for significant-event-set via `grep -oE ... | tail -1`, sets `_lc_paused=1`; lines 470-483 splice `-paused` before any `:N/M` payload, excluding terminal phases. Test `test_statusline_ladder_matches_canonical` parametrized over the three paused fixtures passes.
- **Verdict**: PASS

### Requirement 5: Parity test coverage for paused
- **Expected**: ≥2 paused fixtures under `tests/fixtures/lifecycle_phase_parity/`; `grep -c "paused" tests/test_lifecycle_phase_parity.py` ≥2.
- **Actual**: Three fixtures exist (`paused-implement`, `paused-review`, `paused-then-resumed`); test file has 21 `paused` references; mirror helpers `_expected_wire_from_canonical` and `_label_to_wire` widened to handle `-paused` wire/label forms.
- **Verdict**: PASS

### Requirement 6: Dashboard slow-flag classifier widened
- **Expected**: `cortex_command/dashboard/data.py:1191,1197` recognize `-paused` variants in same bucket as base; template renders human-readable label; test exists for paused classifier.
- **Actual**: `data.py:1193` computes `base_phase = current_phase.removesuffix("-paused")` then switches; `data.py:1194-1201` uses `base_phase`. Template `feature_cards.html:62,110` now uses `{{ current_phase | phase_label }}`; `fleet-panel.html:18` also uses the filter. `dashboard/app.py:195-196` registers `phase_label` Jinja filter. Test `test_slow_flag_paused` in new `tests/test_dashboard_data.py` (plus regression-guard `test_slow_flag_implement_unchanged`) — both pass.
- **Verdict**: PASS

### Requirement 7: Lifecycle SKILL.md routing table updated
- **Expected**: SKILL.md documents `-paused` routing rule; kept-pauses parity test continues to pass; `grep -c "paused" skills/lifecycle/SKILL.md` ≥1.
- **Actual**: `skills/lifecycle/SKILL.md:98` adds the prose rule (option-b from spec): "strip the `-paused` portion for routing-table lookup; display the full label including ` — paused`". Plugin mirror `plugins/cortex-core/skills/lifecycle/SKILL.md` regenerated. `test_lifecycle_kept_pauses_parity.py` passes (2 tests).
- **Verdict**: PASS

### Requirement 8: Index.json loaded once per hook invocation
- **Expected**: Helper reads `cortex/backlog/index.json` once, builds slug→status map skipping null/absent slugs; fails open to empty map on absent/unreadable/unparseable; duplicate `lifecycle_slug` → first wins + duplication side output.
- **Actual**: `_load_backlog_status_map` at `scan_lifecycle.py:202-249` covers all cases; returns `(dict, duplicates_list)`. Called once in `main()` at line 855 before per-candidate loop. Tests `test_index_json_loaded`, `test_index_json_absent_empty_map` (covering file-absent, unparseable JSON, wrong shape), `test_index_json_duplicate_first_wins` all pass.
- **Verdict**: PASS
- **Notes**: The duplication diagnostic (R8 mentions "a duplication diagnostic is emitted") is captured as a returned list but is not separately written to the JSONL diagnostic file. The duplicates list is currently discarded (`_backlog_duplicate_slugs` assigned then unused). The spec wording is ambiguous about destination; the side-output exists but no per-duplicate emission to JSONL fires. Minor.

### Requirement 9: Terminal-vs-non-terminal mismatch rule
- **Expected**: `events_terminal = phase in {"complete","escalated"} OR startswith("complete:")`; `backlog_terminal = status in TERMINAL_STATUSES`; mismatch fires on XOR; `*-paused` non-terminal.
- **Actual**: `_is_terminal_mismatch` at `scan_lifecycle.py:166-199` implements exactly this predicate, including `complete:awaiting-merge` handling via `startswith("complete:")`. `backlog_status=None` returns False (no mismatch claim without evidence). Imports `TERMINAL_STATUSES` from `cortex_command.common`. Tests `test_terminal_mismatch_075_shape` and `test_terminal_mismatch_209_shape_no_annotation` pass; the `*-paused` non-terminal behavior is implicitly confirmed by the 209-shape test (paused implement + in_progress → no mismatch).
- **Verdict**: PASS

### Requirement 10: Active-feature header carries the annotation
- **Expected**: When the active feature is mismatched per R9, annotation appears on active header line; `_interrupted_hint()` text driven by events-derived phase (not backlog status).
- **Actual**: `_build_additional_context` at `scan_lifecycle.py:529-536` looks up active feature's mismatch state from the widened tuple; lines 576-582 render `f"Active lifecycle: {active_feature} | Phase: {label}{active_annot}"`. `_interrupted_hint` is called with `active_phase` (events-derived encoded phase), not backlog status. Test `test_active_header_mismatch` confirms `Active lifecycle: 075-shape` line carries `[mismatch: backlog=complete]`.
- **Verdict**: PASS

### Requirement 11: Mismatch-first sort
- **Expected**: "Other incomplete lifecycles" enumeration sorted with mismatches first; stable within groups.
- **Actual**: `_sort_and_truncate` at `scan_lifecycle.py:542-572` performs `indexed.sort(key=lambda x: (0 if x[1][2] else 1, x[0]))` — mismatch-first, original-index-second for stability. Test `test_mismatch_first_sort` confirms `b-second < a-first`, `d-fourth < a-first`, and stable within-group ordering (b<d, a<c).
- **Verdict**: PASS

### Requirement 12: Soft-budget truncation of non-mismatch tail
- **Expected**: When assembled block > 9000 chars, drop non-mismatch entries from end with `  … +N more`; mismatches never truncated.
- **Actual**: `_sort_and_truncate` iteratively increments `dropped` and recomputes `block_size = overhead_chars + sum(len(l) + 1 for l in kept + tail)` until under budget. `max_droppable = len(sorted_entries) - mismatch_count` ensures mismatches are never dropped. The trailing line uses `"  … +{dropped} more"`. Test `test_soft_budget_truncation` stages 200 long-slug non-mismatch features + 1 mismatch, confirms mismatch survives, `  … +` appears, block ≤ 10000.
- **Verdict**: PASS

### Requirement 13: `mismatches: N total` header fragment
- **Expected**: Header carries ` — mismatches: N total` when N≥1; N is pre-truncation count; omitted when N=0.
- **Actual**: `scan_lifecycle.py:598-603` computes `mismatch_count = sum(1 for e in others if e[2])` and appends `f" — mismatches: {mismatch_count} total"` to `header_line` when ≥1. Same logic in the multi-incomplete branch (line 619-624). Test `test_mismatches_header_fragment` confirms `mismatches: 2 total` appears.
- **Verdict**: PASS

### Requirement 14: Session-bound JSONL diagnostic
- **Expected**: For EACH candidate considered (rendered AND excluded), append one single-line JSON to `cortex/lifecycle/sessions/${LIFECYCLE_SESSION_ID}/scan-lifecycle-diag.jsonl`; schema includes `decision` ("included"/"excluded"), `exclude_reason` (when excluded — e.g., "stale", "morning_review"); fail-open; silent drop when `$LIFECYCLE_SESSION_ID` unset.
- **Actual**: `_emit_diag` at `scan_lifecycle.py:320-346` handles directory creation, fail-open writes, silent-no-op on missing session id. Called once per RENDERED candidate at line 912. The schema contains required fields except `decision` is hardcoded `"rendered"` (not `"included"`/`"excluded"`) and `exclude_reason` is absent. **Excluded candidates (stale-filtered at line 841, morning-review-filtered at line 843, complete-no-PR-filtered at line 899) do NOT emit any diagnostic record** — the comment at lines 905-909 claims they are "emitted separately below by the same loop body's continue branches" but no such code exists. Tests `test_session_diagnostic_written` (covers the included case) and `test_session_diagnostic_silent_when_session_id_unset` pass.
- **Verdict**: PARTIAL
- **Notes**: The R14 spec is explicit that excluded candidates must also emit with `exclude_reason`. The implementation covers only the rendered/included path, leaving the post-mortem-debuggability case the spec explicitly motivates (e.g., "future #075 staleness-filter bypass debuggable" in Non-Requirements) partially unmet — if a candidate is suppressed at the stale or morning-review filter, there is no per-candidate trace explaining why. Tests do not exercise an excluded candidate emission. The `decision` value `"rendered"` is also off-spec (spec uses `"included"`/`"excluded"`).

### Requirement 15: Reconciliation regression fixtures
- **Expected**: New fixtures under `tests/fixtures/hooks/scan_lifecycle/` cover #075-shape, #209-shape-post-fix, clean-alignment; referenced from passing tests.
- **Actual**: All three fixture directories exist with `events.log` + `plan.md`. 075-shape: spec_approved + plan_approved events with 1/3 plan tasks done → implement phase + backlog=complete → mismatch. 209-shape-post-fix: same events + trailing feature_paused with 1/3 unchecked → implement-paused + backlog=in_progress → no mismatch, paused label. clean-alignment: same events with 1/3 tasks done → implement + backlog=in_progress → no annotation. Referenced from `test_terminal_mismatch_075_shape`, `test_terminal_mismatch_209_shape_no_annotation`, `test_active_header_mismatch`, `test_e2e_session_start_envelope` and `_stage_t12_fixture` helper.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None. The implementation reads `cortex/backlog/index.json` (existing artifact) and writes only to the already-documented session-bound path `cortex/lifecycle/sessions/<id>/scan-lifecycle-diag.jsonl` (per observability.md's session-bound write surface convention). No new sandbox grants, no schema-of-record changes, no new backlog-status vocabulary. The dashboard slow-flag classifier widening preserves existing semantics. The phase-label hoist into `cortex_command/phase_labels.py` is a refactor that introduces no new behavior visible to the requirements docs. The `-paused` phase vocabulary is an internal detector value; the project.md "phase routing table" (described in SKILL.md, not project.md) absorbs it via a prose rule. observability.md statusline acceptance criteria are preserved (< 500ms, 3-line output, graceful on missing lifecycle).
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. New helpers use `_leading_underscore` for module-internal status (`_load_backlog_status_map`, `_is_terminal_mismatch`, `_events_log_meta`, `_emit_diag`, `_sort_and_truncate`); the cross-module pure helper lives at `cortex_command/phase_labels.py:phase_label` without underscore (publicly importable). Phase vocabulary tokens (`implement-paused`, `review-paused`) follow the existing kebab-case suffix idiom (`implement-rework`). The dashboard Jinja filter is named `phase_label` matching the function. The diagnostic JSON keys are snake_case, matching events.log convention.

- **Error handling**: Strong fail-open discipline. `_load_backlog_status_map` returns `({}, [])` on `OSError`, `JSONDecodeError`, `ValueError`, or shape mismatch. `_events_log_meta` returns `{"latest_ts": None, "last_event": None}` on read failure. `_emit_diag` wraps the entire write in `try/except (OSError, ValueError, TypeError)` and silently drops on missing `LIFECYCLE_SESSION_ID`. `detect_lifecycle_phase` call is wrapped in `try/except Exception` (per-candidate continue). The hook always exits 0. One small concern: the `_backlog_duplicate_slugs` returned by `_load_backlog_status_map` is computed but never consumed — the duplication diagnostic mentioned in R8 has no observable output.

- **Test coverage**: 93 tests pass across the four affected files (38 scan_lifecycle, 51 phase_parity, 2 dashboard, 2 kept-pauses), matching the prompt's expected count. All 17 plan tasks are marked done. Verification steps from the plan execute cleanly: paused parity fixtures collect (6 cases), mismatch tests cover both 075-shape and 209-shape, sort/truncation/header tests pass, e2e envelope test asserts all four acceptance criteria together. Notable coverage gap: no test exercises the excluded-candidate diagnostic path (because the implementation does not emit one — see R14 PARTIAL).

- **Pattern consistency**: Follows existing conventions cleanly. The lazy-import discipline in `main()` is preserved (datetime imported locally at line 910). The bash mirror in `statusline.sh` mirrors the Python rung structure with full-file `grep -oE ... | tail -1` instead of `tail -50` truncation — explicitly matched to Python's semantics per the plan. The shared phase-label module follows the "single source of truth" pattern advocated in project.md (avoids duplicate logic in dashboard and hook). The mismatch-first sort uses a stable sort key idiom standard in the codebase. The fail-open + silent-drop pattern matches `_is_stale` and `_metrics_summary_line` precedents.

## Verdict

```json
{"verdict": "CHANGES_REQUESTED", "cycle": 1, "issues": ["R14 partial: excluded candidates (stale-filtered, morning-review-filtered, complete-no-PR-filtered) emit no JSONL diagnostic record, contradicting the spec's 'For each candidate lifecycle considered in main()' wording and the Non-Requirements motivation that 'future #075 staleness-filter bypass be debuggable'. The misleading code comment at scan_lifecycle.py:905-909 claims excluded candidates 'are emitted separately below by the same loop body's continue branches' but no such code exists. The `decision` field uses 'rendered' instead of the spec's 'included'/'excluded'. The `exclude_reason` field is absent entirely. No test exercises the excluded-candidate emission path. Fix: hoist _emit_diag calls into each `continue` branch (stale, morning_review, complete-no-PR) with the appropriate `exclude_reason`, rename `decision: rendered` → `decision: included`, and add coverage for the stale-excluded case. Minor: the `_backlog_duplicate_slugs` returned by `_load_backlog_status_map` is unused — either pipe it into a R14 duplication diagnostic emission or drop the side-output return."], "requirements_drift": "none"}
```
