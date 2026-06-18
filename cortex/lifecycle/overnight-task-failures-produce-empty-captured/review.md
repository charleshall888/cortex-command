# Review: overnight-task-failures-produce-empty-captured

## Stage 1: Spec Compliance

### R1: Broaden secret redaction in `_on_stderr` (cue-anchored, no prefixless blobs)
- **Expected**: Value-level, cue-anchored redaction of GitHub/Slack/`Bearer`/`password=`/`token=`/URL-userinfo shapes plus AWS `AKIA`/`ASIA`; constrained to secret-shaped values so benign cued-keyword text survives; PEM line-level masking; NO prefixless fixed-length blob matcher. Over-redaction guard test must cover cued-keyword-in-benign cases, not just prefixless blobs.
- **Actual**: `_REDACTION_RULES` (`cortex_command/pipeline/dispatch.py:412-447`) is entirely prefix/keyword-anchored. The A-class fix is present: a `_SECRET_VALUE = r"[A-Za-z0-9_\-./+=]{16,}"` length/charset floor constrains the `Bearer`/`password=`/`token=` keyword-delimiter rules (`dispatch.py:405,430-446`), and `_PEM_CUE` (`dispatch.py:452`) masks the PEM block line-level. AWS `AKIA`/`ASIA` is in the rule set (`dispatch.py:421`). No prefixless blob matcher exists. The over-redaction guard `test_cued_keyword_benign_context_survives` (`test_dispatch.py:899-909`) asserts `token=RPAREN`, `token='EOF'`, `Bearer of bad news`, `password=changeme` all SURVIVE byte-for-byte; `test_prefixless_blobs_survive` (`test_dispatch.py:885-897`) covers git SHA / UUID / base64. Cue-anchored redaction asserted in `test_prefix_cued_shapes_redacted` / `test_keyword_delimiter_secret_shaped_values_redacted` (`test_dispatch.py:815-872`).
- **Verdict**: PASS
- **Notes**: The critical-review fix is fully realized and exactly matches the acceptance criterion's cued-keyword-in-benign requirement.

### R2: Add a byte cap to `_on_stderr` capture
- **Expected**: Captured stderr bounded by total bytes (in addition to the 100-line cap); tail-anchored truncation; a test asserting a single >cap-byte line yields a stored tail ≤ the byte cap.
- **Actual**: `_MAX_STDERR_BYTES = 65536` (`dispatch.py:385`); `_on_stderr` (`dispatch.py:755-766`) measures the post-redaction line and tail-truncates at a UTF-8 boundary. `test_single_oversize_line_capped_to_byte_bound` (`test_dispatch.py:915-926`) asserts `len(out.encode("utf-8")) <= _MAX_STDERR_BYTES` and that the kept slice is the tail (`oversize.endswith(out)`).
- **Verdict**: PASS

### R3: Stop tracking new `pipeline-events.log` (scoped)
- **Expected**: `cortex/.gitignore` ignores `pipeline-events.log` under `cortex/lifecycle/`, scoped so the test-fixture path is NOT ignored. Acceptance keys on `git check-ignore` of the lifecycle path (0) vs. the fixture path (1).
- **Actual**: Rule `lifecycle/**/pipeline-events.log` present at `cortex/.gitignore:29`. The lifecycle copy is currently tracked (verified `git ls-files --error-unmatch` exit 0), so plain `git check-ignore` returns 1 by design — the correct verification is `git check-ignore --no-index`, which the review instructions confirm. With `--no-index`: `cortex/lifecycle/pipeline-events.log` exits 0 and `cortex/lifecycle/<slug>/pipeline-events.log` exits 0, while `cortex_command/pipeline/tests/fixtures/pipeline_logs/pipeline-events.log` exits 1. The rule ignores NEW pipeline-events.log under lifecycle and leaves the test fixture tracked.
- **Verdict**: PASS
- **Notes**: The already-tracked lifecycle copy is intentionally not retroactively untracked (Non-Requirement: "applies to new commits only"). Verification approach is sound.

### R4: Add a diagnostics bundle to `DispatchResult`, populated from real capture locals
- **Expected**: `DispatchDiagnostics(child_stderr, exit_code, cwd)` value object; `diagnostics` optional field on `DispatchResult`; populated at the two exception error returns from `_stderr_lines`/`exit_code`/`worktree_path`; None on success and budget-exhausted paths. Behavioral test asserts captured values surface and None on success.
- **Actual**: `DispatchDiagnostics` dataclass (`dispatch.py:299-315`); `diagnostics` field follows the `cost_usd` optional-field template (`dispatch.py:340`). Populated at both exception returns (`dispatch.py:940-944`, `969-973`) from the computed locals; left None on the success return (`dispatch.py:907-911`) and budget-exhausted return (`dispatch.py:899-905`). `test_diagnostics_populated_on_process_error` (`test_dispatch.py:632-663`) drives a real stderr line through `_on_stderr` and asserts the bundle carries those exact values; `test_diagnostics_none_on_success` (`test_dispatch.py:665-695`) asserts None on success.
- **Verdict**: PASS

### R5: Thread the diagnostics bundle through `RetryResult` from the same final attempt
- **Expected**: One optional `last_dispatch_diagnostics` field on `RetryResult`, set from the final attempt's `result.diagnostics` at every failure-path exit; same-attempt provenance with `final_output`; per-site test guarding the silent-drop risk.
- **Actual**: `last_dispatch_diagnostics` field (`retry.py:75`). Set at all 5 failure-path exits: circuit-breaker (`retry.py:357`), pause_human (`retry.py:387`), pause_session (`retry.py:410`), escalation-exhausted (`retry.py:438`), all-retries-exhausted (`retry.py:472`) — each as `result.diagnostics` from the loop's final `result` binding. The success exit (`retry.py:300-307`) omits it. Per-site tests in `test_retry.py:298-470` cover each exit; `test_all_retries_exhausted_surfaces_final_attempt_diagnostics` (`test_retry.py:411`) constructs a 4-attempt retry with distinct per-attempt stderr and asserts the FINAL one surfaces and matches `final_output` (same-attempt provenance).
- **Verdict**: PASS
- **Notes**: Spec text says "~7 sites"; the actual failure-path exit count is 5 (the per-site coverage is complete regardless of the estimate). The same-attempt invariant is preserved by sourcing both from the one `result` binding.

### R6: Feed diagnostics into the brain context and prompt (values + framing)
- **Expected**: `BrainContext` gains a diagnostics field, populated in `_handle_failed_task` via defensive `getattr`; `batch-brain.md` gains a `## Final Attempt Diagnostics` section rendering exit_code/cwd/stderr framed with limits. Test asserts values AND the limits-framing text render, not just heading presence.
- **Actual**: `last_attempt_diagnostics` on `BrainContext` (`brain.py:88`); assembled in `_handle_failed_task` via `getattr(retry_result, 'last_dispatch_diagnostics', None)` (`feature_executor.py:265`). `_format_diagnostics` (`brain.py:133-167`) renders exit_code (`unknown` when None), cwd, stderr tail (`(empty)` when blank) plus explicit limits framing (generic-exit-1, timeout-unknown, silent-failure, learnings-primary). `batch-brain.md:31-35` carries the `## Final Attempt Diagnostics` section. `test_known_values_and_framing_rendered` (`test_brain.py:509-531`) asserts the stderr value, exit code, cwd, AND framing tokens ("generic", "learnings file", "not a") render; None-exit and empty-stderr marker tests at `test_brain.py:533-552`.
- **Verdict**: PASS

### R7: Carry diagnostics on the `task_output` event (every task)
- **Expected**: The unconditional `task_output` event gains diagnostics as DISTINCT fields (not folded into `output`), sourced from the same `RetryResult` bundle; failing task carries them, successful task omits/null-defaults.
- **Actual**: `feature_executor.py:705-727` emits `task_output` unconditionally with `task_number`, then conditionally adds `child_stderr`/`exit_code`/`cwd` as distinct keys only when the bundle is non-None (emitter omits on success). `test_failing_task_output_carries_diagnostics_fields` (`test_feature_executor_boundary.py:154-184`) and `test_successful_task_output_omits_diagnostics_fields` (`test_feature_executor_boundary.py:188-213`) cover both branches.
- **Verdict**: PASS

### R8: Render diagnostics in the morning report failed-feature section
- **Expected**: `render_failed_features` shows exit_code/cwd/stderr-tail (`(empty)` marker, `unknown` for None exit) read via a sibling reader (NOT a signature change to `_read_last_task_output`); tail cap larger than the 500-char `output` cap; report markers byte-identical to brain's (parity test).
- **Actual**: A NEW sibling reader `_read_last_task_diagnostics` (`report.py:2009-2058`) reads the distinct fields and leaves `_read_last_task_output` (`report.py:1956-1989`) untouched, so its existing caller is unaffected. `render_failed_features` (`report.py:1290-1312`) renders exit_code (`unknown` when None), cwd, and a tail-anchored stderr tail with `_STDERR_TAIL_CAP = 2000` (`report.py:1998`, > the 500 `output` cap). Report-local markers `_DIAGNOSTICS_UNKNOWN_EXIT`/`_DIAGNOSTICS_EMPTY_STDERR` (`report.py:2005-2006`) are byte-identical to the brain's; `test_report_diagnostics_markers_match_brain_constants` (`test_report.py:1220-1236`) asserts equality with the brain constants. Render tests at `test_report.py:1093-1196` cover exit_code/stderr, `(empty)`, `unknown`, and tail-not-clipped.
- **Verdict**: PASS
- **Notes**: Sibling-reader approach and the parity test both match the A-class fix exactly.

### R9: Register event field-additive extensions (row-scoped)
- **Expected**: `bin/.events-registry.md` documents `cwd` under `dispatch_error` and the diagnostics fields under `task_output` as field-additive (omit-when-None), no new event-name row; section-scoped placement; registry audit recipe passes.
- **Actual**: `bin/.events-registry.md:155-157` adds `cwd` under a `### dispatch_error (#309 diagnostics)` block; `:159-166` adds `child_stderr`/`exit_code`/`cwd` under a `### task_output (#309 diagnostics)` block, both under the "Field-additive schema extensions" section with the omit-when-None/tolerate-absence semantics stated. No new event-name row. `bin/cortex-check-events-registry --audit` exits 0 (the only warnings are pre-existing unrelated STALE_DEPRECATION rows).
- **Verdict**: PASS

### R10: End-to-end fidelity: real captured stderr reaches the surfaces
- **Expected**: An integration test drives a single captured stderr sentinel and asserts that same sentinel reaches BOTH the brain prompt (via the carrier) AND the morning report (via the `task_output` event), closing the per-layer-stub gap.
- **Actual**: `test_diagnostics_fidelity.py:139-181` defines `_SENTINEL_STDERR` once, constructs ONE `DispatchDiagnostics` bundle, and feeds it into both surfaces: the brain render path (`_render_template` + `_format_diagnostics`) and the report path (`task_output` event written to a temp `pipeline-events.log`, then `render_failed_features` reading via `_read_last_task_diagnostics`). Asserts the sentinel + exit_code + cwd appear in both. A stub at either layer would fail to surface the single-source sentinel.
- **Verdict**: PASS
- **Notes**: The report side hand-builds the `task_output` event dict mirroring the emitter shape rather than invoking `feature_executor`'s emit. The emit shape itself is independently covered by R7's boundary test, so end-to-end source→both-surfaces identity is genuinely exercised.

### R11: Preserve metrics pairing and report fixtures
- **Expected**: New `dispatch_error`/`task_output` fields do not break `pair_dispatch_events` (keys on event type) or the daytime-skip field-presence heuristic; failure-path fixtures regoldened; a metrics guard asserts `dispatch_error` with new fields still pairs.
- **Actual**: `test_dispatch_error_with_cwd_still_pairs` (`test_metrics.py:297-328`) asserts a `dispatch_error` carrying `cwd`/`child_stderr`/`exit_code` still pairs (outcome="error", not dropped). `test_dispatch_error_cwd_does_not_trip_daytime_discriminator` (`test_metrics.py:330+`) asserts none of the new field names collide with `_DAYTIME_DISPATCH_FIELDS`. Full suite passes (see below).
- **Verdict**: PASS

### Non-Requirements respected
- No raw child stdout capture (no `stdout` handling in `dispatch.py`). PASS
- No literal failing-command capture (the only `"command"` reference is the pre-existing `_extract_input_summary` Bash-input helper at `dispatch.py:68`, unrelated). PASS
- No change to `error`/`error_type` halt vocabulary — the 9 closed-vocab error_type literals are unchanged; `_SESSION_HALT_ERROR_TYPES`/`_SYSTEMIC_ERROR_TYPES` (in `constants.py`) are untouched by the diff. PASS
- No new event-name row (field-additive only). PASS

## Stage 2: Code Quality
- **Naming conventions**: Consistent with project patterns. `DispatchDiagnostics` mirrors the existing `DispatchResult`/`RetryResult` dataclass style; the optional `diagnostics`/`last_dispatch_diagnostics`/`last_attempt_diagnostics` fields follow the `cost_usd: Optional[...] = None` template named in the spec. Module-private constants (`_MAX_STDERR_BYTES`, `_SECRET_VALUE`, `_REDACTION_RULES`, `_STDERR_TAIL_CAP`, the `_DIAGNOSTICS_*` markers) all use the leading-underscore convention.
- **Error handling**: Appropriate. The carrier-shape-tolerant defensive `getattr` idiom is used at both consumer boundaries (`feature_executor.py:265` for the brain context; `feature_executor.py:718-726` for the task_output emit). Field-additive omit-when-None is honored on the emitter (task_output only adds keys when the bundle is non-None) and tolerated on the consumer (`_read_last_task_diagnostics` returns None when no diagnostics keys are present, so the renderer skips cleanly). `_format_diagnostics` tolerates a None bundle.
- **Test coverage**: Strong. Every requirement's load-bearing behavioral test is present and passing (194 diagnostics-related tests pass under `CORTEX_COMMAND_FORCE_SOURCE=1`). The R10 fidelity test genuinely drives both surfaces from one source bundle. The over-redaction guard (R1) covers the cued-keyword-in-benign cases the critical review demanded. The R5 provenance test proves the FINAL attempt's diagnostics surface (distinct per-attempt stderr). `just test` is 6/7 group-pass; the single failing group is `tests/test_mcp_subprocess_contract.py::test_plugin_path_mismatch_exits_nonzero`, which failed ONLY because the sandbox blocks the test subprocess's `uv run --script` fetch of `mcp` from pypi.org (DNS error). Re-running that test outside the sandbox passes in 1.14s; it touches no #309 file and is unrelated to this change.
- **Pattern consistency**: Redact-at-source (every downstream sink reads the pre-scrubbed `_stderr_lines`), field-additive events (no new rows, omit-when-None), and same-attempt provenance (both sinks source the one `RetryResult.last_dispatch_diagnostics`) are all consistently applied. The brain/report marker-parity constants and the parity tests enforce the cross-surface label invariant.

## Requirements Drift
**State**: detected
**Findings**:
- The change introduces a **cue-anchored credential-redaction posture** (`_redact` + `_REDACTION_RULES` scrubbing GitHub/Slack/AWS/`Bearer`/`password=`/`token=`/URL-userinfo/PEM shapes from captured subprocess stderr). `project.md`'s "Defense-in-depth for permissions" quality attribute records only settings.json allow/deny + sandbox; it does not record that captured subprocess output is now scrubbed of an enumerated (defense-in-depth, non-complete) credential allowlist. A future change could silently broaden or remove this redaction with no requirement anchoring it.
- The change makes **subprocess stderr (post-redaction) a new sink in the committed morning report** (`render_failed_features` renders the captured stderr tail into `cortex/lifecycle/morning-report.md`, which the runner commits to local `main`). `observability.md` describes the morning report's surfaces but does not record that arbitrary child stderr now reaches a committed artifact, nor the redaction that bounds the resulting credential-leak surface.

**Update needed**: `cortex/requirements/project.md` (primary — defense-in-depth/redaction posture); secondarily `cortex/requirements/observability.md` (morning report as a redacted-stderr sink).

## Suggested Requirements Update
**File**: `cortex/requirements/project.md`
**Section**: Quality Attributes → Defense-in-depth for permissions
**Content**:
```markdown
- **Defense-in-depth for captured subprocess output**: Child stderr captured for diagnostics (`pipeline/dispatch.py:_redact`) is scrubbed at source with a cue-anchored credential allowlist (prefix-cued: `sk-ant-`/`gh?_`/`xox[bp]-`/AWS `AKIA`/`ASIA`; keyword-delimiter secret-shaped: `Bearer`/`password=`/`token=`/URL-userinfo; PEM line-level) before it reaches the brain prompt or the morning report committed to local `main`. The allowlist is defense-in-depth, NOT complete (prefixless secrets and uncued families may pass); it deliberately uses no prefixless fixed-length blob matcher so benign high-entropy diagnostics (SHAs, UUIDs, base64) survive. → #309.
```

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
