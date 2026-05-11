# Review: clean-up-eventslog-emission-and-reader-discipline

## Stage 1: Spec Compliance

### Requirement R1: Per-event remediation table applied
- **Expected**: 11 dead-event emissions deleted from canonical skill prompts (confidence_check, task_complete, decompose_flag/ack/drop, discovery_reference, implementation_dispatch, orchestrator_review, orchestrator_dispatch_fix, orchestrator_escalate, requirements_updated). clarify_critic preserved (R3 schema). plan_comparison preserved verbatim. walkthrough.md Section 2c deleted.
- **Actual**: Repo-wide `grep -rn '"event":\s*"<name>"' skills/ plugins/cortex-core/skills/` for every DELETE-row event returns zero matches. `clarify_critic` emit preserved at `skills/refine/references/clarify-critic.md:177` (now schema v3). `plan_comparison` preserved at `skills/lifecycle/references/plan.md:109-112` and `cortex_command/overnight/prompts/orchestrator-round.md:296,331-337,376`. `Section 2c` and `requirements_updated` references removed from `skills/morning-review/references/walkthrough.md`. Mirror in `plugins/cortex-core/skills/` matches canonical.
- **Verdict**: PASS
- **Notes**: None.

### Requirement R2: Verified-dead claim re-validated per event before deletion
- **Expected**: PR description (or equivalent artifact) contains a per-event consumer-grep table proving zero non-test/non-emitter/non-legacy-tolerance hits across the listed scopes.
- **Actual**: `lifecycle/clean-up-eventslog-emission-and-reader-discipline/r2-consumer-grep.md` exists as the lifecycle-side consumer-grep artifact, satisfying the verification mandate before deletion.
- **Verdict**: PASS
- **Notes**: Artifact lives in lifecycle rather than the PR description; spec language accepts either surface.

### Requirement R3: clarify_critic payload pruning via schema v2 → v3 (inline-only)
- **Expected**: v3 row contains only count fields (no `findings[]`, `dismissals[]`, `applied_fixes[]`); legacy-tolerance table extended to v3 plus all prior shapes; existing test gates pass; canonical-to-mirror parity holds.
- **Actual**: `skills/refine/references/clarify-critic.md:177` example renders the v3 single-line JSONL with `findings_count`, `dispositions`, `applied_fixes_count`, `dismissals_count`, `parent_epic_loaded`, `status`. Legacy-tolerance table at lines 162-168 enumerates v1, v1+dismissals, v2, YAML-block, v3 with v3 marked as canonical write shape. Mirror at `plugins/cortex-core/skills/refine/references/clarify-critic.md` is identical to canonical. `tests/test_clarify_critic_alignment_integration.py` listed in the changed-files set was updated but the `detections >= 1` invariant is preserved.
- **Verdict**: PASS
- **Notes**: None.

### Requirement R4: escalations.jsonl re-inline bounded via read-shape index
- **Expected**: `aggregate_round_context(session_dir, round_number)` returns dict whose `escalations` contains exactly `unresolved` and `prior_resolutions_by_feature`; `_EXPECTED_SCHEMA_VERSION = 2` and inline `schema_version` literal in lockstep at 2; consumer prompt uses precomputed dict via `.get(entry["feature"], [])`; round-trip test guards lockstep.
- **Actual**: `cortex_command/overnight/orchestrator_context.py:20` sets `_EXPECTED_SCHEMA_VERSION = 2`; payload literal at line 118 sets `schema_version: 2` in lockstep; strict-equality guard at 128-129 raises RuntimeError on drift with updated message. Function signature is `(session_dir: Path, round_number: int)` per spec. Escalations sub-dict (lines 121-124) contains only `unresolved` and `prior_resolutions_by_feature`; `all_entries` removed. Consumer at `cortex_command/overnight/prompts/orchestrator-round.md:57` uses `ctx["escalations"]["prior_resolutions_by_feature"].get(entry["feature"], [])`. Round-trip test at `cortex_command/overnight/tests/test_orchestrator_context_schema_roundtrip.py` asserts (a) no RuntimeError, (b) exact escalations key set `{unresolved, prior_resolutions_by_feature}`, (c) `all_entries` absent. Both tests pass locally.
- **Verdict**: PASS
- **Notes**: Producer + consumer ship in the same diff range; CHANGELOG documents the operator-side mid-session-upgrade hazard per the spec's deployment-atomicity contract.

### Requirement R5: CI-time emission-registry gate
- **Expected**: `bin/cortex-check-events-registry` exists, stdlib-only, executable, contains `cortex-log-invocation` shim in first 50 lines, supports `--staged`/`--audit`/`--root`, fails closed on missing registry with `MISSING_REGISTRY`, positive-routing error messages, ≥8 self-tests covering the enumerated cases.
- **Actual**: Script exists at `bin/cortex-check-events-registry` and at mirror `plugins/cortex-core/bin/cortex-check-events-registry` (identical). Stdlib-only (`argparse`, `datetime`, `os`, `re`, `subprocess`, `sys`, `dataclasses`, `pathlib`). `cortex-log-invocation` shim is at line 28 (within first 50). Mutually-exclusive `--staged`/`--audit` group with required `True`. `--root` flag exists for testability (lines 527-536) and is exercised by every self-test fixture. `MISSING_REGISTRY` returned by both staged and audit modes on missing file (lines 391-401 and 458-467). Error messages use positive-routing form ("Create ...", "add a row to ...", "coordinate with owner ... to complete the cleanup PR or bump the date") with no MUST/CRITICAL/REQUIRED. `justfile` recipe `check-events-registry` at line 348 plus tests/test_check_events_registry.py satisfies the parity contract. Self-tests at `tests/test_check_events_registry.py` cover: case1 unregistered (error staged), case2 registered (pass staged), case3 stale deprecation (error audit), case4 staged ignores stale (pass staged), case5 missing owner (error audit), case6 missing registry staged (error), case6 missing registry audit (error), case7 non-live row missing rationale (error), case8 staged passes when no scan files (pass). 9 functions / 10 collected pytest cases; passing locally.
- **Verdict**: PASS
- **Notes**: All 10 tests pass under `uv run pytest`. `--audit --root .` against the current tree exits 0 as expected.

### Requirement R6: Pre-commit wiring for the new gate
- **Expected**: A new pre-commit phase between log-invocation shim (Phase 1.6) and dual-source drift (Phase 2) that triggers narrowly on `skills/*`, `cortex_command/overnight/prompts/*`, the gate script, and the registry — never on `cortex_command/**/*.py`. Failure output points at the registry/script error; no MUST phrasing. `justfile` recipes `check-events-registry` (staged) and `check-events-registry-audit` (audit) exist.
- **Actual**: `.githooks/pre-commit` Phase 1.8 (between existing Phase 1.7 backlog-telemetry and Phase 2 short-circuit) at lines 146-170. The spec said "Phase 1.7" but a Phase 1.7 already existed in-tree for backlog entry-point telemetry; the plan's critical-review pass identified this and bumped the new phase to 1.8 while preserving the spec-intent (between log-invocation shim and dual-source drift). Trigger case-match restricted to `skills/*|cortex_command/overnight/prompts/*|bin/cortex-check-events-registry|bin/.events-registry.md`; `cortex_command/**/*.py` is not in the trigger set. Failure message at line 167 points at `bin/.events-registry.md` and the script's stderr; no MUST/CRITICAL/REQUIRED phrasing. `justfile:347-353` defines both `check-events-registry` (staged) and `check-events-registry-audit` (audit).
- **Verdict**: PASS
- **Notes**: Phase number drift between spec text ("Phase 1.7") and actual hook ("Phase 1.8") is reflected in `CHANGELOG.md:11` and `docs/internals/events-registry.md:49,93`, which both still say "Phase 1.7". This is documentation drift only; the wiring itself is correct and the spec-intent (after 1.6 log-invocation, before Phase 2 dual-source drift) is preserved. Flagged for follow-up update of the doc strings.

### Requirement R7: Initial registry population
- **Expected**: Rows for all live skill-prompt-emitted events (`scan_coverage: gate-enforced`), all `EVENT_TYPES` overnight constants (`scan_coverage: manual`, `target: overnight-events-log`), Python emission sites in `cortex_command/pipeline/` and `bin/cortex-*` (`scan_coverage: manual`), plus `deprecated-pending-removal` rows for each R1-deleted event with `deprecation_date = today+30` and a non-empty `owner` field. Pre-commit + audit invocations exit 0 on the post-implementation tree.
- **Actual**: `bin/.events-registry.md` has 97 data rows. All 9 live skill-prompt events present (R7 list verified). All 36 EVENT_TYPES overnight-scope events present as `scan_coverage: manual`. Python emission sites covered (dispatch_*, merge_*, ci_check_*, repair_agent_*, complexity_override, etc.). All 11 R1 DELETE events have `deprecated-pending-removal` rows with `deprecation_date: 2026-06-10` (today=2026-05-11 + 30 days), `owner: charliemhall@gmail.com`, and ≥30-char rationales. `bin/cortex-check-events-registry --audit --root .` exits 0 against the current tree.
- **Verdict**: PASS
- **Notes**: Date arithmetic: 2026-05-11 + 30 days = 2026-06-10. Correct.

### Requirement R8: CHANGELOG.md and docs updates
- **Expected**: CHANGELOG entry summarizing removed events, clarify_critic schema bump, orchestrator_context schema bump, and the new gate. `docs/internals/events-registry.md` describes registry schema, gate-enforced vs manual scope split, pre-commit-vs-audit two-mode design, deprecation lifecycle, day-15/stale-row recovery. Linked from pipeline.md and overnight-operations.md.
- **Actual**: `CHANGELOG.md` contains entries for the gate (R5/R6), the clarify_critic v2→v3 bump, and the orchestrator_context v1→v2 bump, including operator guidance on mid-session-upgrade hazard. `docs/internals/events-registry.md` (8.9 KB) describes the schema, scope split, two-mode design, and stale-row recovery path. `docs/internals/pipeline.md` and `docs/overnight-operations.md` appear in the changed-files set.
- **Verdict**: PASS
- **Notes**: CHANGELOG and docs/internals/events-registry.md repeat the "Phase 1.7" naming from the spec text where the actual hook is at Phase 1.8 (see R6 Notes). Recommend a one-line doc fix.

## Stage 2: Code Quality

### Naming conventions
Consistent with project patterns. The gate script's `RegistryRow` / `GateError` dataclasses, `parse_registry` / `load_registry` / `run_staged_gate` / `run_audit_gate` mirror the function-and-dataclass style of `bin/cortex-check-parity`. Test names follow `test_caseN_<scenario>` convention with one-sentence docstrings.

### Error handling
Appropriate. Missing registry fails closed with `MISSING_REGISTRY` (correctly overriding the `cortex-check-parity` fail-open precedent per the spec). Malformed registry rows surface as `INVALID_ROW` diagnostics that block any in-scope commit. `RuntimeError` from registry read is caught at `main()` and surfaced as `REGISTRY_READ_ERROR`. `subprocess.CalledProcessError` / `FileNotFoundError` on `git diff --cached` and `git show :path` swallow gracefully and return empty/None — safe given the staged-paths set is the source of truth and root-override path is always present in test fixtures. Producer-side strict-equality schema guard at `orchestrator_context.py:128-129` raises RuntimeError with a clear drift-context message; the round-trip test guards regressions.

### Test coverage
≥ 8 self-test cases requirement met: 9 test functions in `tests/test_check_events_registry.py` (case1 unregistered staged, case2 registered staged, case3 stale audit, case4 staged-ignores-stale, case5 missing-owner audit, case6 missing-registry both modes, case7 non-live-missing-rationale, case8 staged-passes-when-no-scan-files). Round-trip test exists at `cortex_command/overnight/tests/test_orchestrator_context_schema_roundtrip.py`. Existing tests in `tests/test_clarify_critic_alignment_integration.py`, `tests/test_daytime_preflight.py`, `tests/test_decompose_rules.py`, `tests/test_mcp_integration_end_to_end.py`, and `cortex_command/overnight/tests/test_orchestrator_context.py` appear in the changed-files set, suggesting alignment work for the R1 deletions and R4 schema bump. All 10 new-test cases pass locally.

### Pattern consistency
Gate models on `bin/cortex-check-parity` precedent correctly: positive-routing error messages, `cortex-log-invocation` shim in first 50 lines, stdlib-only, justfile recipe wiring, parity-side test surface. The `--root` flag pattern follows the cortex-check-parity testability override style. The two-mode `--staged`/`--audit` split (one for critical-path enforcement, one for off-path deprecation review) is a new structural pattern not present in cortex-check-parity; this is documented in `docs/internals/events-registry.md` and CHANGELOG.

## Requirements Drift

**State**: detected
**Findings**:
- New pre-commit phase (Phase 1.8 events-registry enforcement) introduces a second instance of the "two-mode static gate" pattern (`--staged` for critical-path, `--audit` for off-path time-based checks). This deliberately diverges from `cortex-check-parity`'s single-mode design by moving deprecation-date staleness off the critical path to avoid day-15 tripwires on unrelated commits. The pattern is sound and well-aligned with `requirements/project.md` Workflow Trimming intent, but the two-mode-gate structural choice is not currently expressible in project.md's gate/discipline section (which currently documents only `cortex-check-parity` as the single-gate precedent).
- The MISSING_REGISTRY fail-closed posture explicitly inverts the `cortex-check-parity` fail-open-on-missing-allowlist precedent. This is a deliberate, documented choice in spec R5 and `docs/internals/events-registry.md`, but project.md's Gate Discipline section does not yet articulate the "fail-closed vs fail-open" decision criterion that future gate authors should consult.
- The pre-commit hook now uses a path-trigger pattern (`skills/*|cortex_command/overnight/prompts/*|bin/cortex-check-events-registry|bin/.events-registry.md`) explicitly engineered to NOT trigger on `cortex_command/**/*.py`. This narrow-trigger pattern is a deliberate Workflow Trimming alignment (unrelated backend commits never run this phase), but project.md's gate discipline section does not yet articulate the "scope the trigger to what the gate can enforce" principle.

**Update needed**: requirements/project.md

## Suggested Requirements Update
**File**: requirements/project.md
**Section**: "## Gate Discipline" (under the existing parity-linter bullet at line 29)
**Content**:
```
- **Two-mode gate pattern**: pre-commit critical-path gates may pair a `--staged` mode (referential schema check on staged diffs) with an `--audit` mode (time-based or repo-wide check) wired off the critical path via `just <recipe>-audit`. Time-based checks (date staleness, calendar windows) must NOT block unrelated commits — they belong in `--audit` mode surfaced via morning-review or on-demand. The pre-commit trigger MUST be scoped to staged paths the gate can actually enforce; backend-only commits must not invoke skill-prompt-only gates. Fail-closed-vs-fail-open on missing allowlist is a per-gate design decision: fail-closed when the allowlist's absence indicates incomplete authoring (e.g., `bin/.events-registry.md`); fail-open when the allowlist is opt-in or backward-compat (e.g., legacy parity exceptions). Document the choice in the gate's docstring and the relevant `docs/internals/<gate>.md`. See `bin/cortex-check-events-registry` for the two-mode precedent.
```

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [
    "Documentation drift: CHANGELOG.md:11 and docs/internals/events-registry.md:49,93 say 'Phase 1.7' but the actual hook wiring is at Phase 1.8 (Phase 1.7 was already occupied by backlog telemetry enforcement). One-line doc fix; does not affect behavior."
  ],
  "requirements_drift": "detected"
}
```
