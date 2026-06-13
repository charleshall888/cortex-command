# Review: consolidate-tier-supersession-into-a-shared

## Stage 1: Spec Compliance

### Requirement R1: Pure event-fold reducer exists
- **Expected**: A pure `reduce_lifecycle_events(records)` in `common.py` performing the supersession fold + per-value vocab gating over already-parsed records; no file I/O, no `json.loads`, no line-number tracking; returns the bare accumulated `state` (at most `{"criticality","tier"}`, criticality-then-tier insertion order) plus rejected positions; does NOT return a `LifecycleStateReduction`. `grep -c "def reduce_lifecycle_events" common.py` = 1; reducer tests exit 0.
- **Actual**: `cortex_command/common.py` adds `reduce_lifecycle_events(records: Iterable[dict]) -> tuple[dict[str, str], list[int]]`. It iterates already-parsed records, applies the same `lifecycle_start` seed + `complexity_override`/`criticality_override` `.to`-only supersession with `TIER_VOCABULARY`/`CRITICALITY_VOCABULARY` gating, no I/O, no `json.loads`, no linenos. Returns `(state, rejected_positions)` — criticality is set before tier within a `lifecycle_start`, giving criticality-then-tier insertion order. No `LifecycleStateReduction` constructed in the core. `grep -c` = 1; `tests/test_reduce_lifecycle_state.py` = 22 passed.
- **Verdict**: PASS
- **Notes**: —

### Requirement R2: Path reader delegates with byte-for-byte preserved behavior
- **Expected**: `reduce_lifecycle_state(events_path: Path) -> LifecycleStateReduction` keeps its signature and tolerant-read contract (never raises/None, `errors="replace"`), parses JSONL + tracks 1-based linenos itself, delegates the fold, and produces `skipped_lines` as the ascending-sorted union of parse-failure and vocab-rejection line numbers byte-for-byte identical to today, including interleaving order. All existing reducer tests pass unchanged.
- **Actual**: Signature and `errors="replace"` decode preserved; the same `(FileNotFoundError, IsADirectoryError, NotADirectoryError, PermissionError, OSError)` guard returns the empty `LifecycleStateReduction`. The shell now buckets parse failures and a parallel `linenos`/`records` list, calls the core, maps `rejected_positions` back to line numbers, and emits `skipped = sorted(set(parse_failures) | set(vocab_rejections))`. Parse-failure and vocab-rejection sets are disjoint by construction (a torn line never reaches the core), so the sorted union reproduces the single-pass ascending output. All pre-existing tests (torn-line `:58/:67`, mixed-line `:85`, missing-file `:98`, corruption suite `:134–199`) still pass.
- **Verdict**: PASS
- **Notes**: Non-dict parsed JSON is kept in the `records` list so the core's 0-based positions index it 1:1; the core no-ops on non-dicts — preserving the non-dict-silent-skip rule.

### Requirement R3: `LifecycleStateReduction` is NOT grown
- **Expected**: NamedTuple retains exactly `(state, skipped_lines)`; a structural `_fields` assertion exists; reducer tests exit 0.
- **Actual**: `LifecycleStateReduction` is untouched. `tests/test_reduce_lifecycle_state.py:320` asserts `LifecycleStateReduction._fields == ("state", "skipped_lines")` (`test_lifecycle_state_reduction_not_grown`), which catches a defaulted added field that the missing-file equality assertion would not.
- **Verdict**: PASS
- **Notes**: —

### Requirement R4: Pure-core unit coverage added
- **Expected**: Thin tests on `reduce_lifecycle_events` directly — empty input; seed + complexity_override + criticality_override in insertion order; out-of-vocab dropped + position reported; non-dict silent no-op (not reported); second `lifecycle_start` re-seeds; plus a mixed parse-failure + vocab-rejection interleaving case through the Path reader asserting `skipped_lines == (1, 2)`.
- **Actual**: All present in `tests/test_reduce_lifecycle_state.py`: `test_reduce_lifecycle_events_empty_input` (`:221`), `_seed_and_overrides_insertion_order` (`:228`, also asserts key order), `_out_of_vocab_value_dropped_and_reported` (`:243`, position `[1]`), `_non_dict_record_is_silent_noop` (`:256`), `_second_lifecycle_start_reseeds_tier` (`:265`), and `test_reduce_lifecycle_state_interleaved_vocab_and_torn_ascending` (`:302`) pinning `skipped_lines == (1, 2)`. A bonus `_double_axis_rejection_reports_position_once` (`:277`) pins the per-record-once contract.
- **Verdict**: PASS
- **Notes**: —

### Requirement R5: Metrics final tier comes only from the shared core
- **Expected**: `extract_feature_metrics` computes final `tier` by calling `reduce_lifecycle_events`; the inline `complexity_override`/`lifecycle_start` fold is removed; `metrics.py` imports `reduce_lifecycle_events`. Behavioral test asserts the delegated tier equals the expected superseded value; secondarily no `complexity_override` inside the function body.
- **Actual**: `metrics.py:32` imports `reduce_lifecycle_events`; `extract_feature_metrics` does `state, _ = reduce_lifecycle_events(events); tier = state.get("tier")`. `grep -n "complexity_override" cortex_command/pipeline/metrics.py` returns no occurrences anywhere. `test_extract_feature_metrics_tier_delegates_to_shared_core_value` asserts `m["tier"] == "complex"` against a hand-computed constant (not a tautological live re-fold). Metrics suite = 53 passed.
- **Verdict**: PASS
- **Notes**: —

### Requirement R6: `initial_tier` stays local and shares the core's vocab gate
- **Expected**: `initial_tier` computed locally (not in the core), counting only the first in-vocab seed; in-vocab check reuses canonical `TIER_VOCABULARY` (no re-spelled literal set). Import present; no locally re-spelled tier set for the gate; existing `initial_tier` assertions pass; new test pins out-of-vocab first seed dropped.
- **Actual**: `metrics.py:32` imports `TIER_VOCABULARY`. The local loop sets `initial_tier` only when `isinstance(seed, str) and seed in TIER_VOCABULARY`, then breaks. The R6 grep flags `metrics.py:1110` `tier_labels = {"simple": "Simple", "complex": "Complex"}`, but that is a display-label map inside the calibration-report builder, NOT the vocab gate — a benign false positive; the gate itself uses the imported `TIER_VOCABULARY`. Existing assertions (`:1748` final tier `complex`, `:1752` `initial_tier` `simple`) pass; new `_initial_tier_out_of_vocab_sole_seed_is_none` and the discriminating `_initial_tier_skips_leading_out_of_vocab_seed` (out-of-vocab then in-vocab → `complex`) lock the skip-and-keep-scanning behavior.
- **Verdict**: PASS
- **Notes**: The first-seed latch changed from "first non-None" to "first in-vocab" — an intended behavior change documented in the spec's Changes to Existing Behavior, no-op on real data per the audit.

### Requirement R7: Metrics vocab behavior locked by test
- **Expected**: A test pins that an out-of-vocab `lifecycle_start` tier yields `m["tier"] is None` (matching `read_tier`) and is excluded from `compute_aggregates`.
- **Actual**: `test_extract_feature_metrics_out_of_vocab_tier_dropped_and_excluded` asserts `m["tier"] is None`, `read_tier(...) == "simple"` (its own default projection on the same log), and `compute_aggregates([m]) == {}`. Passes.
- **Verdict**: PASS
- **Notes**: —

### Requirement R8: Intake hardened against non-UTF-8
- **Expected**: `parse_events` decodes with `errors="replace"`, matching `common.py`, so a byte-corrupt log no longer raises `UnicodeDecodeError`. Regression test feeds a non-UTF-8 log through `extract_all_feature_metrics` and asserts no raise. `grep -c 'errors="replace"' metrics.py` ≥ 1.
- **Actual**: `parse_events` now reads `path.read_text(encoding="utf-8", errors="replace")`. `grep -c` = 1. `test_extract_all_feature_metrics_tolerates_non_utf8_log` writes a log with a standalone `\xff\xfe...\xfa` line bracketed by clean lines and asserts `extract_all_feature_metrics` completes, the feature is present, and its tier is `complex`. Passes.
- **Verdict**: PASS
- **Notes**: —

### Requirement R9: Metrics fold joins parity coverage against an independent oracle + intake case
- **Expected**: A parametrized test asserts `extract_feature_metrics`'s tier across a matrix (in-vocab, out-of-vocab, re-seed; each with a `feature_complete`) against a hand-computed independent oracle (not solely `read_tier`), with `read_tier`-agreement as a secondary cross-check, plus a non-UTF-8 fixture where post-R8 both paths complete.
- **Actual**: `tests/test_bin_lifecycle_state_parity.py` adds `test_extract_feature_metrics_tier_matches_oracle` parametrized over `_METRICS_ORACLE_AXES` = `[("in-vocab-escalated","complex",True), ("out-of-vocab-seed",None,False), ("reseed","complex",True)]`. The primary assertion is `m["tier"] == expected_tier` (explicit constant per fixture); `read_tier`-agreement is asserted only where the effective tier is in-vocab. Each fixture carries a clean `feature_complete`. A separate `test_extract_feature_metrics_non_utf8_intake_no_crash` asserts `extract_all_feature_metrics` completes on the corrupt log and agrees with `read_tier` on the clean tier-bearing lines. Parity suite = 15 passed.
- **Verdict**: PASS
- **Notes**: —

### Requirement R9a: The `test_metrics.py:1749` parity assertion is not left as a weak guard
- **Expected**: The `:1749` assertion is either strengthened in place OR annotated as superseded by R9's independent-oracle matrix.
- **Actual**: The assertion (now at `:1758`) carries an inline `NOTE (R9a, feature 301)` comment plus an expanded docstring, both stating it only confirms the parse front-ends agree on clean input post-delegation and that the real drift guard is `test_extract_feature_metrics_tier_matches_oracle` in the parity matrix. The disposition route chosen is annotate-as-superseded.
- **Verdict**: PASS
- **Notes**: The spec cites line `:1749`; the assertion is at `:1758` after the docstring grew, but it is the same assertion (`assert m["tier"] == read_tier(...)`) the spec describes — the line number drifted, not the target.

### Requirement R10: Full suite green
- **Expected**: `just test` exits 0 after both phases.
- **Actual**: `just test` reports 6/7 suites passing. The sole failure is `tests/test_mcp_subprocess_contract.py::test_plugin_path_mismatch_exits_nonzero`, failing on a DNS error fetching `https://pypi.org/simple/packaging/` — the exact sandbox-isolated network test the review brief flagged as unrelated to this change. Every suite touching this feature (reducer, metrics, parity, pipeline, overnight, dashboard) passes.
- **Verdict**: PASS
- **Notes**: The lone failure is a known sandbox network limitation, not a regression introduced by this change. Treated as green per the brief.

## Stage 2: Code Quality
- **Naming conventions**: Consistent with project patterns. `reduce_lifecycle_events` mirrors the existing `reduce_lifecycle_state` name; `rejected_positions`/`parse_failures`/`linenos` are descriptive and match the surrounding style. The `(state, rejected_positions)` tuple return is the deliberate "bare core" shape the spec's Technical Constraints left as an implementation choice (0-based indices variant), and the docstring documents it precisely.
- **Error handling**: Appropriate. The tolerant-read contract is preserved verbatim in the Path shell (same exception tuple, same empty-result fallback, never raises/None). `errors="replace"` is now applied symmetrically in both `common.py` and `metrics.py:parse_events`, closing the intake-divergence the spec identified as more severe than any fold divergence. The core is total over arbitrary `records` (non-dicts and unknown events no-op).
- **Test coverage**: Thorough and matches the plan's verification steps. New tests exercise the pure core directly (R4), behavioral delegation against constants rather than tautologies (R5), both `initial_tier` discrimination cases (R6), the vocab-drop + aggregate-exclusion lock (R7), the intake no-crash regression (R8), and the independent-oracle parity matrix + intake-divergence case (R9). The `:1749` weak-guard disposition (R9a) and the `_fields` growth guard (R3) are both present. All named suites exit 0.
- **Pattern consistency**: Follows the functional-core/imperative-shell split cleanly — the core owns the fold + vocabulary gating, the Path shell owns I/O, JSONL parsing, 1-based linenos, the `skipped_lines` merge, and the `LifecycleStateReduction`/`corrupted` wrapper; metrics calls the bare core and ignores the rejected-position channel exactly as the spec's core/shell boundary prescribes. The #287 invariants (never raise / never None, per-value rejection, criticality-then-tier insertion order, `.to`-only supersession, non-dict silent skip) are preserved by construction and re-verified by the unchanged corruption suite. The `_DAYTIME_DISPATCH_FIELDS` historical-compat shim and the dispatch-pairing tier path are untouched, honoring the Non-Requirements.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
