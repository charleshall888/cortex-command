# Review: remove-daytime-autonomous-pipeline-and-cancel

## Stage 1: Spec Compliance

### Requirement R1: Verify `implement.md` is already daytime-free at PR base
- **Expected**: `grep -c 'Daytime Dispatch\|cortex-daytime' skills/lifecycle/references/implement.md` outputs `0`
- **Actual**: Command outputs `0`; `implement.md` contains no daytime-pipeline tokens at HEAD
- **Verdict**: PASS

### Requirement R2: Add structural pin test for `implement.md`
- **Expected**: New test at `tests/test_lifecycle_implement_md_daytime_free.py` asserting both `"cortex-daytime"` and `"Daytime Dispatch"` absent from `implement.md`; pytest exits 0
- **Actual**: File exists; asserts both tokens absent; `pytest tests/test_lifecycle_implement_md_daytime_free.py` exits 0
- **Verdict**: PASS

### Requirement R3: Add structural contract test for worktree-interactive dispatch surface
- **Expected**: `tests/test_implement_worktree_interactive_contract.py` asserts menu label, lock-acquire call, and two `_interactive_overnight_check.sh` guard occurrences; pytest exits 0
- **Actual**: File exists with three test functions covering all three assertions; `pytest tests/test_implement_worktree_interactive_contract.py` exits 0
- **Verdict**: PASS

### Requirement R4: Delete daytime modules
- **Expected**: `find cortex_command/overnight -maxdepth 1 -name 'daytime_*.py' -o -name 'readiness.py' | wc -l` outputs `0`
- **Actual**: Command outputs `0`; all four daytime modules deleted
- **Verdict**: PASS

### Requirement R5: Delete daytime + dispatch-parity + dispatch-readiness tests
- **Expected**: `find . -name 'test_daytime_*.py' -not -path '*/worktrees/*'` outputs nothing AND `ls ... | grep -c 'No such'` outputs `2`
- **Actual**: No `test_daytime_*.py` files found; both `tests/test_dispatch_parity.py` and `cortex_command/overnight/tests/test_dispatch_readiness.py` absent; grep outputs `2`
- **Verdict**: PASS

### Requirement R6: Unregister daytime console-scripts
- **Expected**: `grep -c 'cortex-daytime' pyproject.toml` outputs `0`
- **Actual**: Command outputs `0`
- **Verdict**: PASS

### Requirement R7: Delete daytime parity-exception rows
- **Expected**: `grep -c 'cortex-daytime-' bin/.parity-exceptions.md` outputs `0`
- **Actual**: Command outputs `0`
- **Verdict**: PASS

### Requirement R8: Drop `DaytimeResult` and `save_daytime_result` from state.py
- **Expected**: `grep -c 'DaytimeResult\|save_daytime_result' cortex_command/overnight/state.py` outputs `0`
- **Actual**: Command outputs `0`
- **Verdict**: PASS

### Requirement R9: Remove justfile dispatch-parity recipe
- **Expected**: `grep -c 'test-dispatch-parity-launchd-real' justfile` outputs `0`
- **Actual**: Command outputs `0`
- **Verdict**: PASS

### Requirement R10: Remove `.gitignore` daytime tempfile patterns
- **Expected**: `grep -c 'daytime' .gitignore` outputs `0`
- **Actual**: Command outputs `0`
- **Verdict**: PASS

### Requirement R11: Remove daytime audit allowlist entries
- **Expected**: `grep -c 'daytime' bin/.audit-bare-python-m-allowlist.md` outputs `0`
- **Actual**: Command outputs `0`
- **Verdict**: PASS

### Requirement R12: Adapt dashboard PR-url rendering to worktree-interactive shape
- **Expected**: (a) `grep -c 'daytime_result\|daytime_state' feature_cards.html` = `0`; (b) `grep -c 'feature_pr\[\|feature_pr.get' feature_cards.html` ≥ 1; (c) new dashboard test exits 0
- **Actual**: (a) outputs `0`; (b) outputs `1` (template at line 125); (c) `pytest cortex_command/dashboard/tests/test_feature_cards_pr_url.py` exits 0. `parse_feature_pr_artifact` exists in `data.py:1365`; `DashboardState.feature_pr` field at `poller.py:105`; `_poll_state_files` populates it at lines 276-278; template renders nothing when absent
- **Verdict**: PASS

### Requirement R13: Drop dashboard daytime parsing helpers and dataclass fields
- **Expected**: Grep over `cortex_command/dashboard/` for all daytime symbol names sums to `0`
- **Actual**: Command outputs `0`; all daytime symbols removed from `data.py`, `poller.py`, `seed.py`, and templates
- **Verdict**: PASS

### Requirement R14: Keep `_DAYTIME_DISPATCH_FIELDS` filter as historical compat shim
- **Expected**: `grep -c '_DAYTIME_DISPATCH_FIELDS' cortex_command/pipeline/metrics.py` ≥ 1; metrics test exits 0; `grep -c 'Historical compatibility' cortex_command/pipeline/metrics.py` ≥ 1
- **Actual**: All three acceptance criteria pass (counts of 2, 1 pass, and 1 respectively). However, the `_DAYTIME_DISPATCH_FIELDS` constant's own `#:` comment (lines 332-334) was **not** retitled — it still reads the old wording ("Fields whose presence identifies a daytime-schema `dispatch_complete` event..."). The phrase "Historical compatibility — skip pre-#246 daytime-schema rows in archived event logs." appears only in the `pair_dispatch_events` function's docstring (line 360), not on the constant itself. The grep-based acceptance criteria passes, but the constant's own comment wasn't updated as the spec requested.
- **Verdict**: PARTIAL
- **Notes**: The retitle ended up on the function docstring rather than the constant's `#:` comment. Functionally harmless, but a future reader looking at `_DAYTIME_DISPATCH_FIELDS` definition sees no signal that this is a historical shim; they must read the function body to find that context. Low severity.

### Requirement R15: Clean up `auth.py` daytime references
- **Expected**: `grep -c 'daytime' cortex_command/overnight/auth.py` = `0`; `--help` output contains no 'daytime'; argparse description = "Resolve the SDK auth vector for the overnight runner."
- **Actual**: Grep outputs `0`; `--help` outputs `0`; description at line 552 matches verbatim
- **Verdict**: PASS

### Requirement R16: Drop Sphinx xref in `cli_handler.py:61`
- **Expected**: `grep -c 'daytime_pipeline' cortex_command/overnight/cli_handler.py` = `0`
- **Actual**: Command outputs `0`
- **Verdict**: PASS

### Requirement R17: Update `bin/.events-registry.md` `auth_probe` row
- **Expected**: `grep -c 'daytime_pipeline' bin/.events-registry.md` = `0`
- **Actual**: Command outputs `0`
- **Verdict**: PASS

### Requirement R18: Rewrite orphan comments in `runner.py`, `interactive_lock.py`, `_interactive_overnight_check.sh`
- **Expected**: `grep -c 'daytime'` across all three files outputs `0`
- **Actual**: All three files output `0`; sum is `0`
- **Verdict**: PASS

### Requirement R19: Update `cortex/requirements/observability.md:144` catalog
- **Expected**: `grep -c 'daytime' cortex/requirements/observability.md` = `0`
- **Actual**: Command outputs `0`
- **Verdict**: PASS

### Requirement R20: Update docs
- **Expected**: `grep -c daytime` across four docs files sums to `0`
- **Actual**: Aggregate sum is `0`
- **Verdict**: PASS

### Requirement R21: Add `superseded` to `TERMINAL_STATUSES` and module-local terminal sets
- **Expected**: `grep -c '"superseded"' cortex_command/common.py` ≥ 2; `grep -c '"superseded"' cortex_command/overnight/plan.py` ≥ 1; `pytest cortex_command/tests/test_terminal_statuses.py` exits 0
- **Actual**: `common.py` outputs `2` (at line 170 in frozenset, line 779 in `normalize_status` map); `plan.py` outputs `1` (at line 144 in `_TERMINAL` tuple); both tests pass. Note: the spec references `plan.py:213` for `_TERMINAL` but the actual location is line 144 — the spec's line reference was a stale pointer; the content requirement is satisfied at the correct location.
- **Verdict**: PASS

### Requirement R22: Cancel #228 with supersedence record
- **Expected**: `grep -c '^status: superseded' 228-*.md` = `1`; `grep -c '## Superseded by' 228-*.md` = `1`
- **Actual**: Both outputs are `1`
- **Verdict**: PASS

### Requirement R23: Annotate #230 without frontmatter change
- **Expected**: `grep -c '^status: complete' 230-*.md` = `1`; `grep -c 'release-gate procedure no longer applies' 230-*.md` = `1`
- **Actual**: Both outputs are `1`
- **Verdict**: PASS

### Requirement R24: Add CHANGELOG `### Removed` entry
- **Expected**: `grep -c '### Removed' CHANGELOG.md` ≥ 1; `grep -c 'uv tool uninstall cortex-command' CHANGELOG.md` ≥ 1; entry describes what was removed (three daytime modules, `readiness.py`, three console-scripts, seven test files, etc.); replacement; verbatim migration note
- **Actual**: Both greps pass (counts 2 and 1). The verbatim migration note is present at line 85. However, the descriptive content of the entry is **factually wrong** — it lists module paths that never existed in this repo (`cortex_command/daytime/pipeline.py`, `cortex_command/daytime/session.py`, `cortex_command/daytime/dispatcher.py`) and console-scripts that were never registered (`cortex-daytime-run`, `cortex-daytime-status`, `cortex-daytime-cancel`). The actual modules removed were `cortex_command/overnight/{daytime_pipeline.py, daytime_dispatch_writer.py, daytime_result_reader.py, readiness.py}` and the actual scripts removed were `cortex-daytime-pipeline`, `cortex-daytime-dispatch-writer`, `cortex-daytime-result-reader`. The spec requirement for item (a) — "what was removed" — is materially unmet despite the acceptance greps passing.
- **Verdict**: PARTIAL
- **Notes**: The CHANGELOG permanently records wrong artifacts for this removal. An operator reading this entry cannot reconcile it with the actual repo state. The wrong paths appear to have been hallucinated from a different (hypothetical) design rather than reflecting the actual `cortex_command/overnight/` module layout. The verbatim migration note and replacement description are correct; only the deleted-artifact list is wrong.

### Requirement R25: All tests pass
- **Expected**: `just test` exits 0
- **Actual**: `just test` exits 0; all 6 test suites pass
- **Verdict**: PASS

---

## Requirements Drift
**State**: detected
**Findings**:
- `superseded` added to `TERMINAL_STATUSES` and `normalize_status` map in `cortex_command/common.py`, and to `_TERMINAL` in `cortex_command/overnight/plan.py` — this extends the backlog status vocabulary with a new canonical terminal value. The project-level requirements (`project.md`) describe the backlog system and its `grep -c` resolution rule but nowhere enumerate the canonical status vocabulary or define which values are terminal. Adding `superseded` is a backlog-vocabulary extension not reflected there.
- `_DAYTIME_DISPATCH_FIELDS` retained in `cortex_command/pipeline/metrics.py` as a "historical compatibility shim" for archived event-log rows. No pattern for historical compatibility shims on retired pipeline schemas is documented in `project.md` or any area requirements file. The pattern (retain a filter to avoid contaminating historical metric aggregation after a module is deleted) is load-bearing for future similar removals but exists only in the spec and inline comments.
- The distinction between `cortex-update-item` (wheel-binstub, reads installed `common.py`) vs `python3 -m cortex_command.backlog.update_item` (runs against working tree) is mentioned in Technical Constraints as the intra-Phase-5 operation-order constraint (R21 must land before R22). The `project.md` architectural constraint for skill-helper modules says "`python3 -m cortex_command.<skill> <subcommand>` is retained as a readable fallback for ad-hoc invocation" but does not document the semantic difference between the two invocation paths when `common.py` has been edited in the working tree but not yet reinstalled as a wheel.

**Update needed**: `cortex/requirements/project.md`

## Suggested Requirements Update
**File**: `cortex/requirements/project.md`
**Section**: Architectural Constraints (after the "Skill-helper modules" bullet)
**Content**:
```
- **Backlog status vocabulary**: Canonical terminal statuses are maintained in `cortex_command/common.py:TERMINAL_STATUSES` (frozenset) and mirrored in `cortex_command/overnight/plan.py:_TERMINAL`. Extensions to terminal status vocabulary (e.g. adding `superseded`) must update both locations and add a corresponding `normalize_status` map entry. The frozenset in `cortex_command/overnight/backlog.py` is a known divergence tracked for a separate follow-up.
- **Historical compatibility shim pattern**: When a pipeline module is deleted, read-side filters that detect that module's schema in archived event logs (e.g. `_DAYTIME_DISPATCH_FIELDS` in `pipeline/metrics.py`) are retained as historical compat shims rather than deleted. Shim docstrings are retitled to "Historical compatibility — skip pre-#NNN <schema-name> rows in archived event logs." This preserves correct behavior for operators replaying or aggregating historical `pipeline-events.log` data after the module is gone.
- **Wheel-binstub vs working-tree invocation**: `cortex-<skill>` binstubs execute against the installed wheel's `site-packages/`; `python3 -m cortex_command.<skill>` runs against the working tree. When a Phase N commit edits `common.py` and a subsequent Phase N+1 step must invoke a binstub that reads `common.py` at runtime, Phase N's working-tree changes must be complete before invoking the binstub — the binstub reads the installed wheel, not the working tree. Use `python3 -m` invocation to run against the working tree when wheel reinstall between phases is not feasible.
```

---

## Stage 2: Code Quality

All Stage 1 requirements are PASS or PARTIAL (no FAIL); Stage 2 proceeds.

- **Naming conventions**: Consistent with project patterns. `parse_feature_pr_artifact` in `data.py` follows the `parse_*` naming convention used by other dashboard parsers. `DashboardState.feature_pr` is a clear dict field name. `_TERMINAL` and `TERMINAL_STATUSES` naming carried through unchanged. Test file names follow `test_<module>_<contract>.py` convention.

- **Error handling**: `parse_feature_pr_artifact` returns `None` when `pr.json` is absent; the template uses `state.feature_pr.get(slug)` as the conditional gate — renders no element when absent, which matches the R12 specification exactly. No broken-link or placeholder rendering. The `pair_dispatch_events` compat shim silently skips daytime-schema rows (correct for archival data; no side effects to callers).

- **Test coverage**: New tests cover the spec's structural contract requirements. `test_feature_cards_pr_url.py` covers both the "present" and "absent" pr.json paths. `test_terminal_statuses.py` covers both `common.TERMINAL_STATUSES` and `plan._TERMINAL`. `test_implement_worktree_interactive_contract.py` covers menu label, lock acquire, and dual guard sidecar. `test_lifecycle_implement_md_daytime_free.py` covers the negative-pin invariant. The deleted `test_daytime_schema_skipped` test is retained in `test_metrics.py` per R14.

- **Pattern consistency**: The `feature_pr` dict field in `DashboardState` and its per-feature loop population in `_poll_state_files` follow the same pattern as other per-feature state fields in the dashboard poller. The `_TERMINAL` frozenset comment in `plan.py` (lines 139-142) correctly documents the independent-of-common.py design and the sync requirement. The `#:` comment on `_DAYTIME_DISPATCH_FIELDS` was not retitled (see R14 PARTIAL), but the function docstring carrying the retitled wording is clear; the inconsistency is low-severity and doesn't affect runtime behavior.

---

## Verdict
```json
{"verdict": "CHANGES_REQUESTED", "cycle": 1, "issues": ["R14: _DAYTIME_DISPATCH_FIELDS #: constant comment not retitled — 'Historical compatibility' phrase appears only in pair_dispatch_events function docstring (line 360), not on the constant definition at lines 332-334", "R24: CHANGELOG Removed entry lists wrong module paths (cortex_command/daytime/ directory never existed) and wrong console-script names (cortex-daytime-run/status/cancel never registered); actual removals were cortex_command/overnight/{daytime_pipeline,daytime_dispatch_writer,daytime_result_reader,readiness}.py and cortex-daytime-{pipeline,dispatch-writer,result-reader} — the permanent CHANGELOG record is factually incorrect and irreconcilable with the actual repo state"], "requirements_drift": "detected"}
```
