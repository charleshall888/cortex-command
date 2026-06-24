# Review: harden-overnight-review-agents-reviewmd-artifact

## Stage 1: Spec Compliance

### Requirement 1: Agent writes to the absolute main-repo path (writer side), at every render seam
- **Expected**: The review prompt names an absolute `{review_md_path}` (not relative). `_load_review_prompt` gains a `{review_md_path}` substitution, `prompts/review.md` uses it, and both cycle-1 and cycle-2 invocations pass the absolute path; the new parameter is required (no default). Unit test renders each seam and asserts the rendered prompt contains the absolute path and no bare-relative literal.
- **Actual**: `_load_review_prompt` (`review_dispatch.py:108-142`) takes `review_md_path: str` as a **required** positional parameter (no default) and adds it to the substitution dict (`:139`). `prompts/review.md:51` write target is now `` `{review_md_path}` `` (grep: bare-relative literal count = 0, `{review_md_path}` count = 1). Both render seams — cycle-1 (`:252`) and cycle-2 (`:529`) — pass `review_md_path=str(review_md_path)`. `test_review_path_contract.py::test_cycle1_render_names_absolute_path` and `::test_cycle2_render_names_absolute_path` assert (a) the absolute path is present and (b) `_BARE_RELATIVE.search(rendered) is None` for each seam; `::test_required_param_fails_loud_when_missing` asserts a missing param raises `TypeError`. All pass.
- **Verdict**: PASS
- **Notes**: Exactly two production `_load_review_prompt` call sites exist (`:250`, `:527`); both covered. No seam missed.

### Requirement 2: Gate reads the absolute main-repo path (reader side), at both cycle seams
- **Expected**: `dispatch_review` resolves `review_md_path` to an absolute path under the main-repo lifecycle base (via `_resolve_lifecycle_base()`), passes that same value into both `_load_review_prompt` calls, and both cycle reads consult it. Unit test asserts `review_md_path.is_absolute()` and `== lifecycle_base / feature / "review.md"`.
- **Actual**: `review_md_path = lifecycle_base / feature / "review.md"` (`:215`) is computed once and consulted by both reads: cycle-1 `parse_verdict(review_md_path)` (`:301`) and cycle-2 `parse_verdict(review_md_path)` (`:572`). The same value (`str(review_md_path)`) is threaded into both render seams. `test_review_path_contract.py::test_review_md_path_resolution_is_absolute` mirrors line 215 and asserts `.is_absolute()` and equality. Pass.
- **Verdict**: PASS
- **Notes**: Reader/writer use one source value; the env contract (`CORTEX_REPO_ROOT`-pinned `_resolve_lifecycle_base()`) makes the absolute base deterministic.

### Requirement 3: All three review-gate call sites anchored to an absolute base
- **Expected**: Primary (`apply_feature_result`), recovery (`_recovery_review_gate`), and repair-completed (`_repair_review_or_revert`) `dispatch_review` calls each pass an absolute `lifecycle_base` via `_resolve_lifecycle_base()`. Test asserts value-level absoluteness (not a grep) for all three.
- **Actual**: All three `dispatch_review` calls (`outcome_router.py:1115`, `:1523`, `:1834`) now pass `lifecycle_base=_resolve_lifecycle_base()` (grep count = 3, matching exactly the three production call sites). `_resolve_lifecycle_base` is imported from `common` (`:22`). `test_review_path_contract_callsites.py` patches `dispatch_review` with a capturing `AsyncMock`, drives each of the three entry points, and asserts the captured `lifecycle_base` kwarg is **present** (fail-closed against an omit-regression) and `Path(...).is_absolute()`, with `CORTEX_REPO_ROOT` monkeypatched to an absolute root. All 3 tests pass; each `assert_awaited_once()` confirms the gate actually reached the call.
- **Verdict**: PASS
- **Notes**: The test is a genuine value-level assertion on the kwarg actually passed, not a source grep — exactly what R3 demands. Key-presence is asserted explicitly so a dropped kwarg fails on a clear assertion rather than masking via a defensive `.get`.

### Requirement 4: Regression guard pins the bug-distinguishing property (not a same-source tautology)
- **Expected**: A test guarding that the path the agent is told to write equals the absolute path the gate reads AND that the rendered prompt has no bare-relative literal, for both seams. A bare same-source `writer_path == reader_path` equality is explicitly insufficient.
- **Actual**: `test_review_path_contract.py` makes (a) absoluteness of the parsed write target and (b) `_BARE_RELATIVE.search(rendered) is None` the primary checks at both seams. The "no bare-relative" check uses a negative-lookbehind regex `(?<!/)cortex/lifecycle/[^\`\n]+/review\.md` so the absolute path's identical suffix does not false-positive. `::test_bare_relative_regex_is_non_vacuous` proves non-vacuity: it injects the pre-fix bare-relative literal and asserts the regex catches it while leaving the absolute path uncaught (i.e. the guard genuinely fails on the bug). `::test_writer_target_matches_independent_reader_path` derives the reader path **independently** (`_ABS_BASE / _FEATURE / "review.md"`, computed from the controlled base, not from the value passed into the render), renders, parses the target back OUT of the prompt text via regex, and asserts equality — substitution fidelity, not same-source equality. Both pass.
- **Verdict**: PASS
- **Notes**: This is the requirement the spec emphasized. The guard is non-tautological on two counts: the load-bearing checks (absolute + no-bare-relative) are the ones that fail on pre-fix code, and the parity check derives the reader path independently and round-trips through the rendered text rather than comparing two in-process copies of one value.

### Requirement 5: Suite green
- **Expected**: `just test` exits 0; external/environmental failures (concurrent-fixture races, sandbox-network MCP) excluded per precedent.
- **Actual**: The two directly-affected suites are fully green: pipeline `363 passed` (incl. new `test_review_path_contract.py`, 6 passed) and overnight `624 passed, 1 skipped` (incl. new `test_review_path_contract_callsites.py`, 3 passed). The plan's two excluded failures are confirmed external and untouched by this change: `test_no_order_drift_against_baseline` (`tests/test_resolve_backlog_item.py`) reads `tests/fixtures/predicate_a_baseline.json`, which is uncommitted from a concurrent session and not in this lifecycle's diff; `test_mcp_subprocess_contract` is a sandbox-network/DNS failure. Neither external failure touches any of the 7 files this lifecycle changed.
- **Verdict**: PASS
- **Notes**: Full `just test` not re-run end-to-end in review (slow; would re-trip the same concurrent-session external failures); affected suites verified directly and external failures attributed via git status corroboration, consistent with the plan's documented R5 outcome.

## Stage 2: Code Quality
- **Naming conventions**: Consistent with project patterns. `_resolve_lifecycle_base()` mirrors the existing `_resolve_user_project_root()` underscore-prefixed module-private resolver convention and is co-located beside it in `common.py`. Test names are descriptive and seam-specific (`test_cycle1_render_...`, `test_recovery_gate_passes_absolute_...`). The `review_md_path` parameter name matches the existing `Path` variable it carries.
- **Error handling**: Appropriate. Making `review_md_path` a required parameter (no default) is the correct fail-loud choice — a missed render seam fails at construction (`TypeError`) rather than silently emitting an unsubstituted `{review_md_path}` literal that would re-resolve against the worktree cwd. The pre-existing `(FileNotFoundError, OSError)` handling around the render is preserved. The `could_not_run` safety net for a denied/absent write is unchanged (correctly out of scope per spec).
- **Test coverage**: Genuinely non-vacuous. The R4 guard includes an explicit non-vacuity self-test (`test_bare_relative_regex_is_non_vacuous`) and an independent-derivation parity test, directly addressing the spec's "explicitly insufficient" warning about same-source equality. The R3 call-site test is value-level (capturing mock on the real kwarg), fail-closed on key presence, and env-pinned for determinism — not a grep. Both new files pass standalone and within their suites.
- **Pattern consistency**: Follows conventions well. The resolver was relocated to `common.py` (the lowest-level shared module both `feature_executor` and `outcome_router` already import) to pre-empt the `feature_executor`↔`outcome_router` import cycle, with a back-compat re-import in `feature_executor` so its existing call site and the `feature_executor._resolve_lifecycle_base` name keep resolving — verified by the resolver-parity smoke (`c() == f()`, both absolute). The test files mirror established patterns: the call-site test reuses `test_outcome_router._make_ctx`; the contract test reuses the `conftest._install_sdk_stub` + `import cortex_command.overnight.deferral` ordering from `test_review_dispatch.py` to avoid the import-cycle-at-import-time hazard.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
