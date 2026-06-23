# Review: overnight-dispatch-sends-opus-only-xhigh

## Stage 1: Spec Compliance

### Requirement R1: Best-CLI resolver (prefer-newer system-vs-bundled, env-overridable, cached)
- **Expected**: A single cached helper resolves the absolute `claude` path as the newer of system (`shutil.which` + known fallbacks, compared by parsed `--version`) vs SDK-bundled; never older than the bundled floor; `CORTEX_CLAUDE_CLI_PATH` short-circuits; unit tests cover newer/older/absent/override; `just test` exits 0.
- **Actual**: `cortex_command/cli_resolver.py` implements `resolve_claude_cli()` with `_find_system_cli_path` (which + the three specced fallbacks `~/.local/bin/claude`, `/usr/local/bin/claude`, `~/.claude/local/claude`), `_find_bundled_cli_path` (package-relative `_bundled/claude`), `_probe_version`/`_parse_cli_version` comparison, env override returned verbatim and never memoized, and memoization via a `_UNSET` sentinel. Probe-flake safety prefers the present system CLI without memoizing (a deliberate #313 regression guard beyond the spec letter). Tests `test_cli_resolver.py` cover system-newer→system, system-older→bundled, system-absent→bundled, env-override-verbatim, neither→None, memoization, probe-flake-no-memoize, and version parsing. All pass.
- **Verdict**: PASS
- **Notes**: The "never older than bundled floor" guarantee holds: when both versions parse, `system if system_version >= bundled_version else bundled`; when system version is unparseable it prefers the present (operator-intended) system CLI rather than silently downgrading.

### Requirement R2: Pin `cli_path` at every SDK site + update the test stub
- **Expected**: Every `ClaudeAgentOptions` construction in the dispatch path sets `cli_path=<resolved>`; the test stub gains a `cli_path` field. Acceptance: `grep -c cli_path` ≥ 1 in dispatch.py, discovery.py, _stubs.py; existing dispatch tests pass.
- **Actual**: `dispatch.py:803` and `discovery.py:733` both set `cli_path=resolve_claude_cli()`; `_stubs.py:92` adds `cli_path: str | None = None` appended last so positional constructions stay valid. Grep counts: dispatch.py=1, discovery.py=1, _stubs.py=2 (all ≥ 1). All `test_dispatch.py` tests pass.
- **Verdict**: PASS
- **Notes**: `None ≡ field-absent ≡ today's bundled-first behavior` is documented at the pin site, so degraded environments are unaffected.

### Requirement R3: Orchestrator spawn uses the same resolved CLI (Should — horizon choice)
- **Expected**: Orchestrator subprocess spawned with the resolved absolute path, not bare `"claude"`. Acceptance: test asserts spawn `argv[0]` equals resolver output; `grep -n 'claude_path = "claude"'` shows no bare-literal assignment.
- **Actual**: `runner.py:1486` uses `claude_path = resolve_claude_cli() or "claude"`; the grep for `claude_path = "claude"` returns nothing. `test_spawn_resolved_cli.py::test_spawn_uses_resolved_cli` asserts `argv[0] == "/best/claude"`; `test_spawn_falls_back_to_bare_claude_when_unresolved` asserts `argv[0] == "claude"` when resolution returns None.
- **Verdict**: PASS
- **Notes**: The `or "claude"` fallback preserves today's behavior when resolution yields None — consistent with the R2 pin's None-safe semantics.

### Requirement R4: Hard-reject → one clamped retry, not a blind-retry budget-burn
- **Expected**: A captured `--effort … is invalid` (exit ≠ 0) classifies distinctly and triggers exactly one clamped retry at `max`, recorded for the report; the normal loop must not re-send the invalid flag. Acceptance: unit test — first attempt raises the rejection (text via the `output`/`_stderr_lines` corpus, NOT `ProcessError.stderr`) → exactly one clamped retry at `max`; `just test` exits 0.
- **Actual**: `classify_error` (dispatch.py:532) matches `"option '--effort"` + `"is invalid"` in the corpus and returns `effort_unsupported`; `ERROR_RECOVERY["effort_unsupported"] = "clamp_effort"` (dispatch.py:361). The corpus is built at the call site (dispatch.py:957) from `output_parts + _stderr_lines`, not `ProcessError.stderr`. `retry.py:353-369` clamps once (`clamped_once` guard) to `max` via `effort_override`, evaluated BEFORE the circuit breaker so an empty diff cannot pause first; logs `retry_effort_clamped`. Tests `test_clamps_once_on_first_attempt` (asserts exactly 2 dispatches, second at `max`, one clamp event) and `test_clamps_on_attempt_2_despite_empty_diff_circuit_breaker` both pass.
- **Verdict**: PASS
- **Notes**: One-shot is guaranteed by construction — `max` is universally accepted so it cannot re-classify as `effort_unsupported`. The final-attempt edge (rejection with no remaining budget) correctly falls through to the exhausted return.

### Requirement R5: Warn-ignored effort detected and surfaced (never silent)
- **Expected**: Captured stderr containing the warn-ignore signal records a visible "ran degraded" note; the dispatch is NOT failed (it succeeded). Acceptance: unit test — successful dispatch with warn-ignore stderr records the note and stays success.
- **Actual**: dispatch.py:937-948 scans `_stderr_lines` on the success path for `"unknown --effort value"` + `"ignoring"` and emits `dispatch_effort_ignored` without failing the dispatch; returns `success=True`. Test `test_warn_ignore_recorded_and_success_preserved` asserts `result.success` is True, exactly one `dispatch_effort_ignored` event, and `effort == "xhigh"`. Passes.
- **Verdict**: PASS
- **Notes**: Detection is on the lowercased line, matching the firsthand-verified CLI wording. `render_effort_degradation` (report.py:2521) surfaces both `dispatch_effort_ignored` and `retry_effort_clamped` in a loud "Effort Degradations" section, de-duplicated by `(event, feature, model)` and wired into `generate_report` (report.py:2618-2620).

### Requirement R6: Real CLI error/warning surfaced to learnings (Should)
- **Expected**: Captured child stderr appears in `learnings/progress.txt`, not only an opaque `ProcessError: exit code 1`. Acceptance: unit test asserts the progress write on the error path includes the captured `child_stderr`.
- **Actual**: `DispatchResult.diagnostics.child_stderr` is populated on all exception paths (dispatch.py:983-986, 1012-1015). `retry.py:331-334` threads `result.diagnostics.child_stderr` into `_append_learnings`, which writes `CLI stderr:\n{child_stderr}` (retry.py:127-128). Test `test_child_stderr_written_to_progress` asserts the effort-rejection sentinel and `"CLI stderr:"` appear in progress.txt. Passes.
- **Verdict**: PASS
- **Notes**: Stderr is already redacted/capped by `_on_stderr` before it reaches progress.txt, consistent with the #309 defense-in-depth scrubbing contract.

### Requirement R7: Correct the stale premises (Should)
- **Expected**: The `dispatch.py` "silently downgraded" comment and `docs/internals/sdk.md` corrected to the hard-reject (old, exit ≠ 0) vs warn-ignore (modern, exit 0, runs at default) split; the guard raises `ValueError` (not `AssertionError`). Acceptance: `grep -c "silently downgraded" dispatch.py` = 0; sdk.md reflects the split.
- **Actual**: `grep -c "silently downgraded" cortex_command/pipeline/dispatch.py` = 0. The dispatch.py docstring (lines 606-616) now describes the hard-reject/warn-ignore split explicitly and points at `cli_resolver`. `docs/internals/sdk.md:110-112` states the guard raises `ValueError` and describes the hard-reject vs warn-ignore behavior with version anchors (2.1.69 / 2.1.186), neither "silently downgrades." The `resolve_effort` guard at dispatch.py:284 raises `ValueError`.
- **Verdict**: PASS
- **Notes**: ADR-0014 exists and records the prefer-newer + outcome-based-effort-handling decision with context, decision, and trade-off sections.

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. The resolver follows the leaf-module convention (stdlib-only, documented no-import-of-dependents rule). New events `retry_effort_clamped` / `dispatch_effort_ignored` follow the `<verb>_<noun>` event-name idiom and are registered in `bin/.events-registry.md` with source/sink/status columns. The render function follows the `render_*(data: ReportData) -> str` pattern and returns `""` to omit the section, matching sibling renderers (`render_complexity_normalized`). `effort_unsupported` / `clamp_effort` are clear, distinct vocabulary.
- **Error handling**: Appropriate and defensive. `_probe_version` swallows `OSError`/`SubprocessError` → `None`; resolution returns `None` to mean "fall back to today's behavior" rather than raising, so a degraded environment never crashes dispatch. The probe-flake path logs a warning and deliberately does not memoize an indeterminate result — a thoughtful guard against pinning a degraded choice for the process lifetime. The clamp is evaluated before the circuit breaker, correctly handling the empty-diff interaction the spec flagged. Final-attempt rejection falls through to the exhausted return rather than looping.
- **Test coverage**: Strong. 136 feature tests pass plus the two runner tests (`test_runner_signal.py`, `test_runner_followup_commit.py`) pass. Coverage spans the resolver (8 cases incl. probe-flake regression and version-parse parametrization), classification (`effort_unsupported` vs `task_failure`), the recovery-table mapping, clamp-once on attempt 1 and clamp-despite-empty-diff on attempt 2, warn-ignore success preservation, progress.txt stderr surfacing, the report renderer (list/dedup/empty/heading-wiring), and the orchestrator spawn argv. The two KNOWN-EXTERNAL failures (sandbox-network MCP, concurrent-session backlog-fixture order-drift) are unrelated to this feature.
- **Pattern consistency**: Follows existing conventions throughout — `render_*` section pattern with empty-string omission and `generate_report` wiring; `classify_error` structure (corpus-from-`error`+`output`, hard-typed exceptions first, content patterns, distinct return); event-logging idiom via `log_event` with `event`/`feature` keys; `DispatchDiagnostics` dataclass threaded through result carriers consistent with the #309 diagnostics-capture design. The corpus-not-`ProcessError.stderr` constraint is honored and documented at the call site.

## Requirements Drift
**State**: none
**Findings**:
- None. The implementation realizes the spec without introducing behavior absent from project.md. The "loud degradation" pattern (clamp surfaced / warn-ignore surfaced) is the no-silent-degradation contract from the Quality Attributes / Defense-in-depth sections applied to a new degradation surface, not a new policy. The best-CLI resolver and `cli_path` pin operate within the existing distributed-CLI dependency-bounds posture (the operator's CLI ecosystem drives optimal quality; cortex guarantees the work runs at the best available effort) — an honest extension already named in the spec's ADR-0014, which is recorded under the existing `cortex/adr/` architectural-constraint mechanism. The new events are registered per the events-registry constraint; the renderer follows the established report pattern. No requirements file needs updating.
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
