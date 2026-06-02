# Review: make-cortex-resolve-backlog-item-ambiguous

## Stage 1: Spec Compliance

### Requirement 1: Ambiguous stderr structural assertion
- **Expected**: `test_stderr_parity` special-cases `title_phrase_ambiguous`, asserts exit 2, header `^ambiguous: (\d+) matches$` with N > 1, `min(N, 5)` candidate lines each splitting on first TAB into `.md` filename + non-empty title, and `^\.\.\. \((\d+) more\)$` iff N > 5 with correct arithmetic.
- **Actual**: `_assert_ambiguous_stderr_structure` at lines 163–200 implements exactly this. `test_stderr_parity` special-cases the case at line 251, calls the helper, returns before any `_read_expected_stderr` call.
- **Acceptance command**: `uv run pytest "tests/test_cortex_resolve_backlog_item_parity.py::test_stderr_parity[title_phrase_ambiguous]" -q` — **exit 0, 1 passed**.
- **Verdict**: PASS

### Requirement 2: Ambiguous formatter stays genuinely under test (no no-op)
- **Expected**: The assertion fails on real `_format_candidates` regressions. Realized as committed meta-test `test_ambiguous_structure_rejects_malformed` that feeds crafted bad stderr and asserts `AssertionError` for each mutation.
- **Actual**: The meta-test at lines 259–287 covers three distinct mutation patterns: reworded header (`ambig: 7 match`), space-for-TAB separator, and wrong truncation count (99 instead of 2). One well-formed sample is asserted to pass. All `pytest.raises(AssertionError)` blocks succeed.
- **Acceptance command**: `uv run pytest "tests/test_cortex_resolve_backlog_item_parity.py::test_ambiguous_structure_rejects_malformed" -v` — **exit 0, 1 passed**.
- **Verdict**: PASS

### Requirement 3: Ambiguous drift immunity across backlog growth
- **Expected**: The ambiguous case passes for any N > 1. `just test` exits 0 on current working tree (live count ~34) and after `git add` of #277/#278.
- **Actual**: Structural helper pins format, not the count. Verified by staging the untracked backlog items (#277/#278) and running the test — exit 0 in both states.
- **Acceptance commands**: `just test` — **exit 0 ([PASS] on all suites)**; `git add cortex/backlog/277-* cortex/backlog/278-*` then `uv run pytest "test_stderr_parity[title_phrase_ambiguous]" -q` — **exit 0**.
- **Verdict**: PASS

### Requirement 4: Numeric stdout structural assertion
- **Expected**: `test_stdout_parity` special-cases `numeric_unambiguous`, parses stdout as JSON, asserts four keys present, `filename` and `backlog_filename_slug` match `^252-`, `title` non-empty string, `lifecycle_slug` non-empty.
- **Actual**: `_assert_numeric_stdout_structure` at lines 203–221 matches exactly. `test_stdout_parity` special-cases at line 300, calls helper, returns before any `_read_expected_stdout` call.
- **Acceptance command**: `uv run pytest "tests/test_cortex_resolve_backlog_item_parity.py::test_stdout_parity[numeric_unambiguous]" -q` — **exit 0, 1 passed**.
- **Verdict**: PASS

### Requirement 5: No committed fixture pins volatile live content
- **Expected**: `title_phrase_ambiguous.stderr` and `numeric_unambiguous.stdout` not present, or structural branch runs before any byte-read for those cases.
- **Actual**: Both files deleted (confirmed by `ls` of fixture dir). Structural branches precede `_read_expected_stderr`/`_read_expected_stdout` calls at lines 251–252 and 300–301.
- **Acceptance commands**: `test ! -f tests/fixtures/cortex-resolve-backlog-item/title_phrase_ambiguous.stderr` — **exit 0**; `test ! -f tests/fixtures/cortex-resolve-backlog-item/numeric_unambiguous.stdout` — **exit 0**.
- **Verdict**: PASS

### Requirement 6: Case discovery preserved
- **Expected**: `_discover_cases()` still discovers all three cases (globs `*.argv`).
- **Actual**: Three `*.argv` files remain in the fixture directory. Collect count ≥ 3.
- **Acceptance command**: `uv run pytest tests/test_cortex_resolve_backlog_item_parity.py --collect-only -q | grep -c -E 'title_phrase_ambiguous|numeric_unambiguous|no_match'` — **9 (≥ 3)**.
- **Verdict**: PASS

### Requirement 7: Documented structural exceptions in the test docstring
- **Expected**: Module docstring states `title_phrase_ambiguous` (stderr) and `numeric_unambiguous` (stdout) use structural assertions; corrects false "reproduce byte-for-byte" framing; updates the quintuple note to record that structurally-asserted cases omit their de-pinned snapshot.
- **Actual**: Module docstring (lines 1–40) explicitly: (a) states both cases use structurally-asserted output (lines 3–6); (b) documents that the two cases omit their de-pinned snapshot with the precise filenames (lines 16–21); (c) calls out "Structural exceptions (Abseil Tip #135)" and states they are asserted "rather than byte-compared" (lines 28–35); (d) names `no_match` as the sole byte-exact case (lines 37–39). The word "structural" appears 12 times across the file.
- **Acceptance command**: `grep -c -i 'structural' tests/test_cortex_resolve_backlog_item_parity.py` — **12 (≥ 1)**.
- **Verdict**: PASS

### Requirement 8: Fixture README de-drifted, including the recapture recipe
- **Expected**: README no longer pins stale "32 matches" count, no longer claims affected cases reproduce byte-for-byte, backlog-snapshot line corrected or de-pinned, recapture recipe no longer regenerates `title_phrase_ambiguous.stderr` or `numeric_unambiguous.stdout`.
- **Actual**: README "Structural assertions" section (lines 27–35) explains both cases are now format/shape asserted against live output. Cases table shows "shape asserted" / "count read live". Backlog-snapshot section (lines 50–59) explicitly says no pinned snapshot for either live-data case. Recapture recipe (lines 126–153) explicitly warns "Do NOT regenerate the de-pinned snapshots" and routes stdout/stderr for the two affected cases to `/dev/null`.
- **Acceptance commands**: `grep -c '32 matches' tests/fixtures/cortex-resolve-backlog-item/README.md` — **0**; `grep -c 'title_phrase_ambiguous.stderr' tests/fixtures/cortex-resolve-backlog-item/README.md` — **0**.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. Helpers `_assert_ambiguous_stderr_structure` and `_assert_numeric_stdout_structure` follow the existing `_read_argv` / `_invoke_case` private-helper naming. The structural assertion comment block (`# Structural assertion helpers`) mirrors the layout of the existing invocation helper block.
- **Error handling**: Appropriate. All assertion failure messages include the actual value (`f"header line did not match: {lines[0]!r}"`), which is the project norm for test diagnostics. The `_cp` factory in the meta-test is minimal and correct — avoids subprocess overhead by constructing `CompletedProcess` directly.
- **Test coverage**: Full parity suite (`uv run pytest tests/test_cortex_resolve_backlog_item_parity.py -q`) — **13 passed, exit 0**. The meta-test covers header, separator, and truncation mutations (three distinct regression classes), matching the spec's requirement that "an assertion checking only exit 2 + non-empty stderr does NOT satisfy this." All acceptance commands specified in the spec were run and passed.
- **Pattern consistency**: Follows existing project conventions. In-test case branching (the `if case == "..."` guard-and-return pattern) is consistent with how `test_cortex_lifecycle_state_parity.py` handles per-case tolerances, except appropriately not routing through the closed `TOLERANCE_CATEGORIES` set (per non-requirement). The `_result_cache` memoization is unchanged. The `_invoke_with_argv` helper (lines 314–324) provides a clean parallel to `_invoke_case` for the edge-case suite, which was pre-existing. No new patterns introduced without justification.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
