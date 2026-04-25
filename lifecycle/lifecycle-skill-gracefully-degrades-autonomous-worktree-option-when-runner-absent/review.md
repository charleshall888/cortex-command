# Review: lifecycle-skill-gracefully-degrades-autonomous-worktree-option-when-runner-absent

## Stage 1: Spec Compliance

### Requirement 1: Runtime probe runs in §1 Pre-Flight Check, immediately before the `AskUserQuestion` call
- **Expected**: `grep -nE "import importlib\.util|find_spec\('cortex_command'\)" skills/lifecycle/references/implement.md` ≥ 1 inside §1, 0 outside §1.
- **Actual**: 2 matches total, both inside §1 (lines 25 and 26); 0 outside.
- **Verdict**: PASS
- **Notes**: Probe block sits between the uncommitted-changes guard and the `AskUserQuestion` call site.

### Requirement 2: Probe is a single `python3 -c` call with explicit try/except mapping three exit codes
- **Expected**: §1 region contains `find_spec('cortex_command')` ≥ 1 and `sys.exit(2)` ≥ 1; `try:` present.
- **Actual**: `find_spec('cortex_command')` count = 1; `sys.exit(2)` count = 1; `try:` present.
- **Verdict**: PASS
- **Notes**: Probe form matches the spec's Technical Constraints code block — `try` wraps the import, `except Exception` maps to `sys.exit(2)`, the only path to exit 1 is the explicit `is not None else 1` branch.

### Requirement 3: Probe target is the top-level `cortex_command`, not the full submodule path
- **Expected**: `grep -F "find_spec('cortex_command.overnight.daytime_pipeline')" skills/lifecycle/references/implement.md` returns 0 matches.
- **Actual**: 0 matches.
- **Verdict**: PASS
- **Notes**: The full submodule path is referenced once in surrounding prose (`python3 -m cortex_command.overnight.daytime_pipeline`) for the dispatch description, but never inside `find_spec(...)`.

### Requirement 4: On exit 0 (module present), all three options shown unchanged
- **Expected**: Manual interactive verification.
- **Actual**: Procedural prose in §1 explicitly states: "exit 0 → the `cortex_command` module is present → all three options remain unchanged: `Implement on current branch`, `Implement in autonomous worktree`, and `Create feature branch`."
- **Verdict**: PASS
- **Notes**: Spec acknowledges this is interactive/session-dependent; the prose unambiguously documents the contract.

### Requirement 5: On exit 1, autonomous-worktree option removed silently (no diagnostic)
- **Expected**: `grep -nE "exit 1.*(remove|omit|hide).*autonomous|autonomous.*(remove|omit|hide).*exit 1"` ≥ 1.
- **Actual**: 1 match — "exit 1 → the module is absent → remove `Implement in autonomous worktree` from the options array; this is a silent hide, with no diagnostic surfaced."
- **Verdict**: PASS
- **Notes**: Both "exit 1", "remove", "autonomous", and "silent hide" / "no diagnostic" appear in the same sentence as required.

### Requirement 6: Fail-open on probe error with literal diagnostic
- **Expected**: Diagnostic literal `runtime probe skipped: import probe failed` ≥ 1; routing-rule prose ≥ 1.
- **Actual**: Diagnostic literal count = 1; routing-rule matches = 3.
- **Verdict**: PASS
- **Notes**: Routing rule is enumerated as three explicit bullet points (exit 0 → all options; exit 1 → remove; any other exit → fail-open with diagnostic), and the literal diagnostic appears verbatim.

### Requirement 7: No telemetry, no nag, no events.log entry per probe
- **Expected**: `grep -rnE "runtime_probe|probe_check|graceful_degrade"` over `cortex_command/`, `skills/lifecycle/`, `plugins/cortex-interactive/skills/lifecycle/` (excluding this lifecycle dir and `implement.md`) returns 0 matches.
- **Actual**: 0 matches (grep exit 1).
- **Verdict**: PASS
- **Notes**: No new event-name introduced; only the fail-open diagnostic is user-facing.

### Requirement 8: Two-option degrade respects `AskUserQuestion` `minItems: 2`
- **Expected**: Total label count ≥ 2 in §1 AND at least one line co-locates both labels.
- **Actual**: Label count = 6; co-location matches = 2.
- **Verdict**: PASS
- **Notes**: The exit-1 bullet enumerates the post-degrade option set as `Implement on current branch` and `Create feature branch` on a single line.

### Requirement 9: Both copies of `implement.md` updated together
- **Expected**: `just build-plugin` exits 0; `git diff --no-index --quiet` between source and plugin copy exits 0.
- **Actual**: `just build-plugin` exit 0; `git diff --no-index --quiet` exit 0; `git status --short` shows no drift after rebuild.
- **Verdict**: PASS
- **Notes**: The four-phase pre-commit drift hook would have refused commit `6cdb570` if drift existed.

### Requirement 10: Probe does not interfere with uncommitted-changes guard ordering
- **Expected**: GUARD line < PROBE line < ASK (last `AskUserQuestion` mention) line.
- **Actual**: GUARD=11, PROBE=20, ASK=32; arithmetic chain exits 0.
- **Verdict**: PASS
- **Notes**: Three markers are strictly increasing in the §1 region; demote-in-place mutation of "Implement on current branch" composes cleanly with the probe's removal of "Implement in autonomous worktree".

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent — diagnostic string mirrors the existing uncommitted-changes guard's `<guard> skipped: <reason>` template (`uncommitted-changes guard skipped: git status failed` → `runtime probe skipped: import probe failed`). Probe is described in the same procedural-prose style as the existing guard.
- **Error handling**: Appropriate — explicit `try/except Exception` ensures the only path to exit 1 is the absence-signal branch; all other failure modes (broken `importlib.util`, missing `python3`, permissions) route into fail-open. Three-way exit-code routing (0 / 1 / other) is enumerated in prose so the model executor cannot misroute.
- **Test coverage**: Spec explicitly defers automated runtime tests (no prior art for testing markdown skills' conditional behavior); verification is manual and observable-state grep. All observable-state grep checks for R1, R2, R3, R5, R6, R7, R8 pass; R9's command+output check passes; R10's arithmetic ordering check passes. R4 is the only interactive criterion and the prose unambiguously documents the post-#097 baseline.
- **Pattern consistency**: Follows existing project conventions — fail-open semantics match the precedent at `implement.md:17` for the uncommitted-changes guard; the probe is a model-dispatched Bash call (same execution model as the existing guard); both source and plugin copies are byte-identical, satisfying the dual-source drift contract enforced by the pre-commit hook (`79390c7`).

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
