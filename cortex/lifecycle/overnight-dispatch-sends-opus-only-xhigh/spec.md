# Specification: claude-agent-sdk uses a stale bundled CLI that rejects `--effort xhigh` (#313)

> **Epic reference:** none (standalone bug ticket; the original model/effort-mismatch framing was disproven — see research.md "Root Cause (Confirmed)").
>
> **Revised after critical review.** The first draft proposed an exit-code capability probe + fail-loud-no-run. Firsthand CLI testing (recorded under Technical Constraints) showed (a) the exit-code probe is unreliable — modern `claude` *warn-ignores* unknown efforts (exit 0) rather than hard-rejecting; and (b) `max` is accepted by **every** `claude` version including the stale bundle. That reshaped the fix toward **use the best available CLI + resilient, loud effort handling** (run at the best effort any present CLI supports, always surfaced), which serves the operator's "highest-value features must run" priority better than failing loud.

## Problem Statement

Every `complex` + `high|critical` overnight implement/review dispatch fails instantly because `claude-agent-sdk 0.1.46` (hard-pinned in `pyproject.toml:10`) ships a **bundled** `claude` binary (v2.1.69) that predates the `xhigh` effort level and hard-rejects `--effort xhigh`, and the SDK's `_find_cli()` prefers that bundled binary over the operator's system `claude` (2.1.186, which honors `xhigh`). cortex correctly resolves `model=opus, effort=xhigh`; the failure is purely *which CLI binary the SDK runs* and *how an unsupported effort is handled*. These are the highest-value features, and the operator's priority is that they **run**. The fix makes cortex use the best `claude` available and run each feature at the best effort that CLI supports — honoring `xhigh` when possible, clamping loudly to a universally-accepted ceiling when not — so the work always runs and any degradation is always visible.

## Phases

- **Phase 1: Use the best available CLI** — resolve and pin the newer of system-vs-bundled `claude` for every SDK dispatch (and the orchestrator spawn), instead of the SDK's bundled-first selection.
- **Phase 2: Resilient, loud effort handling** — never blind-retry a rejected `--effort` flag; clamp to a universally-accepted ceiling and surface it; detect a warn-ignored effort from captured stderr and surface it; correct the stale premises.

## Requirements

> **Priority (MoSCoW).** **Must** = R1, R2, R4, R5 (use the best CLI + guarantee the feature runs at the best supported effort, never silently). **Should** = R3 (orchestrator/worker CLI unification — a deliberate solution-horizon choice closing a latent version skew, not required for the immediate bug), R6 (progress.txt surfacing — #309 already captures the stderr in the diagnostics bundle), R7 (doc correction). **Won't** = everything in Non-Requirements. If scope must trim, the Shoulds (R3, R6, R7) are the cut line.

1. **Best-CLI resolver.** _(Must)_ A single cached helper resolves the absolute path of the `claude` binary to dispatch with, selecting the **newer of**: (a) the system `claude` (`shutil.which("claude")` then known fallback locations — `~/.local/bin/claude`, `/usr/local/bin/claude`, `~/.claude/local/claude`), compared by parsed `--version`, and (b) the SDK-bundled `claude`. It never selects a CLI **older** than the bundled floor, so the result is always at least as capable as today's behavior. A `CORTEX_CLAUDE_CLI_PATH` env override short-circuits resolution (operator escape hatch + test seam). Acceptance: unit test — with a fake system CLI newer than bundled it returns the system path; with system older/absent it returns the bundled path; with `CORTEX_CLAUDE_CLI_PATH` set it returns that path; `just test` exits 0. **Phase**: Use the best available CLI

2. **Pin `cli_path` at every SDK site + update the test stub.** _(Must)_ Every `ClaudeAgentOptions`/`_ClaudeAgentOptions` construction in the dispatch path sets `cli_path=<resolved best CLI>` so the SDK does not run its bundled-first selection, AND the shared test stub `cortex_command/tests/_stubs.py` `ClaudeAgentOptions` dataclass gains a `cli_path` field so the pin does not raise `TypeError` in tests. Acceptance: `grep -c "cli_path" cortex_command/pipeline/dispatch.py` ≥ 1 AND `grep -c "cli_path" cortex_command/discovery.py` ≥ 1 AND `grep -c "cli_path" cortex_command/tests/_stubs.py` ≥ 1; the existing `dispatch_task` tests still pass (grounding files: `cortex_command/pipeline/dispatch.py:768`, `cortex_command/discovery.py:724`, `cortex_command/tests/_stubs.py:75-87`). **Phase**: Use the best available CLI

3. **Orchestrator spawn uses the same resolved CLI.** _(Should — deliberate horizon choice)_ The orchestrator subprocess is spawned with the resolved absolute `claude` path rather than the bare literal `"claude"`, so orchestrator and workers run an identical CLI. This is not needed for #313's worker-dispatch bug; it is a deliberate solution-horizon choice to close the latent orchestrator-vs-worker version skew before it becomes its own defect. Acceptance: unit/integration test asserts the orchestrator spawn `argv[0]` equals the resolver's output; `grep -n 'claude_path = "claude"' cortex_command/overnight/runner.py` shows no bare-literal assignment on the spawn path (grounding file: `cortex_command/overnight/runner.py:1482`). **Phase**: Use the best available CLI

4. **Hard-reject → one clamped retry, not a blind-retry budget-burn.** _(Must)_ When a dispatch fails with a captured `--effort` hard-rejection (stderr matching `option '--effort' … is invalid`, exit ≠ 0 — only reachable if the best available CLI is old enough to hard-reject, e.g. the bundled 2.1.69), cortex retries **once** with effort clamped to a universally-accepted ceiling (`max`, accepted by every `claude` version incl. 2.1.69 — verified), and records the clamp for the morning report. The normal retry loop must NOT re-send the same invalid flag (today an `--effort` rejection classifies as `task_failure → retry`, burning the budget on a permanently-invalid flag). Acceptance: unit test — a dispatch whose first attempt raises a `--effort … invalid` `ProcessError` (the rejection text supplied via the `output`/`_stderr_lines` corpus that `classify_error` actually reads — NOT `ProcessError.stderr`, a hardcoded SDK placeholder) results in exactly one clamped retry at `max` rather than N blind retries, and the clamp is recorded; `just test` exits 0 (grounding files: `cortex_command/pipeline/dispatch.py:504-521`, `:641-642`, `cortex_command/pipeline/retry.py:223-280`). **Phase**: Resilient, loud effort handling

5. **Warn-ignored effort is detected and surfaced (never silent).** _(Must)_ When captured stderr contains a warn-ignore signal (modern `claude` emits `Warning: Unknown --effort value '<x>' — ignoring it and using the default effort` and exits 0 — so the dispatch RAN at default effort), cortex records a visible morning-report note that the effort was ignored and the feature ran degraded. The dispatch is NOT failed (it succeeded). This closes the only silent-degradation path the modern CLI can produce. Acceptance: unit test — given a successful dispatch whose captured stderr contains the warn-ignore text, a visible "ran at degraded effort" note is recorded and the dispatch result remains success (grounding files: `cortex_command/pipeline/dispatch.py:307-314` diagnostics capture, `_on_stderr`/`_stderr_lines`). **Phase**: Resilient, loud effort handling

6. **Real CLI error/warning surfaced to learnings.** _(Should)_ The captured child stderr (hard-reject error or warn-ignore warning) appears in `cortex/lifecycle/{feature}/learnings/progress.txt`, not only as an opaque `ProcessError: exit code 1`. Acceptance: unit test asserts the progress/learnings write on the error path includes the captured `child_stderr` text (grounding file: `cortex_command/pipeline/dispatch.py:307-314`). **Phase**: Resilient, loud effort handling

7. **Correct the stale premises.** _(Should)_ The `dispatch.py:592` comment ("`xhigh` … is silently downgraded by non-Opus models") and the corresponding claims in `docs/internals/sdk.md` are corrected to state the truth verified here: old `claude` (≤2.1.69) **hard-rejects** an unsupported `--effort` (exit ≠ 0); modern `claude` (≥2.1.186) **warn-ignores** it (exit 0, runs at default) — neither "silently downgrades" in the sense the comment implies; and the guard raises `ValueError` (not `AssertionError`). Acceptance: `grep -c "silently downgraded" cortex_command/pipeline/dispatch.py` = 0; `docs/internals/sdk.md` reflects the hard-reject-vs-warn-ignore split. **Phase**: Resilient, loud effort handling

## Non-Requirements

- **Does NOT upgrade `claude-agent-sdk`.** Prefer-newer resolution + the clamp-retry safety net make the bundled CLI version non-blocking. Bumping the alpha 0.2.x SDK is orthogonal hygiene (separate follow-up); its 197 MB bundled binary is still downloaded but is the fallback floor, not the default.
- **Does NOT add an exit-code capability probe.** Explicitly rejected: firsthand testing shows modern `claude` exits 0 for *any* effort (valid or bogus), so an `<cli> --effort xhigh` exit-code probe cannot detect capability. The reliable signal is captured stderr (R4/R5), not a preflight probe.
- **Does NOT change the model/effort matrices or the `xhigh` policy** (#090). The `opus + xhigh` pairing is correct; the matrices stay.
- **Does NOT silently degrade.** A clamp (R4) or a warn-ignore (R5) is always surfaced in the morning report. The project's no-downgrade convention forbids *silent* degradation; a *loud* degraded run that keeps the highest-value work moving is the chosen behavior.
- **Does NOT hard-fail the whole session on a CLI shortfall.** The bundled CLI is the guaranteed-present floor; R4 guarantees the feature runs at `max` even on the oldest CLI. No "no system claude → kill every feature" outage.
- **Does NOT change `--tier` semantics** (concurrency/telemetry only).
- **Does NOT address the secondary observations** — review-gate merge-revert is split to **#314**; `#308`/`#312`/`#309` (beyond the R6 surfacing) are out of scope.

## Edge Cases

- **System `claude` newer than bundled (normal operator case)**: R1 selects system; `xhigh` is honored; features run at full intended effort.
- **System `claude` absent or older than bundled**: R1 falls back to the bundled CLI; if that CLI hard-rejects `xhigh`, R4 clamps to `max` and retries once (runs, surfaced). No outage.
- **A modern CLI that does not support `xhigh` (future drift)**: it warn-ignores (exit 0, runs at default); R5 detects the stderr warning and surfaces it. The feature still runs; the degradation is visible.
- **`review-fix`/`integration-recovery` (effort `max`) and `conflict`/`merge` (effort `high`)**: accepted by all `claude` versions incl. 2.1.69 — unaffected by R4/R5.
- **`CORTEX_CLAUDE_CLI_PATH` set**: R1 returns it verbatim (operator pins a specific CLI; tests inject a fake) — bypassing prefer-newer.
- **Mid-run CLI replacement (auto-update)**: resolution is cached at startup; a mid-run replacement is not re-detected, but R4/R5 (stderr-based, per-dispatch) still catch any resulting reject/warn — so a stale cache degrades gracefully, never silently.

## Changes to Existing Behavior

- MODIFIED: SDK worker dispatch and the orchestrator spawn run the resolved **best-available** `claude` (was: SDK bundled-first via `_find_cli()`; orchestrator used bare `"claude"`).
- ADDED: a cached best-CLI resolver (prefer-newer system-vs-bundled, `CORTEX_CLAUDE_CLI_PATH`-overridable).
- MODIFIED: an `--effort` hard-rejection triggers one clamped retry at `max` (was: blind retry loop → budget burn).
- ADDED: warn-ignored-effort detection from captured stderr + a loud morning-report note.
- MODIFIED: `learnings/progress.txt` surfaces the real CLI stderr.
- MODIFIED: test stub `cortex_command/tests/_stubs.py` `ClaudeAgentOptions` gains a `cli_path` field.

## Technical Constraints

- **Firsthand-verified CLI behavior** (run against the installed binaries): system `claude` **2.1.186** *honors* `--effort xhigh` and **warn-ignores** an unknown effort (`Warning: Unknown --effort value '…' — ignoring it and using the default effort. Valid values: low, medium, high, xhigh, max.`, exit 0); the SDK-bundled **2.1.69** **hard-rejects** an unknown effort (`error: option '--effort <level>' argument '…' is invalid. It must be one of: low, medium, high, max`, exit ≠ 0). `max` is accepted by **both**. `--version` does **not** short-circuit effort parsing. ⇒ the reliable signal is captured stderr, not exit code; `max` is a universally-safe clamp target.
- `cli_path` overrides `_find_cli()` entirely (`subprocess_cli.py:46-47`) — passing it is sufficient to bypass the bundled-first selection.
- `classify_error` builds its corpus from `f"{error}" + output`, where the call site passes `output = output_parts + _stderr_lines`; it never reads `ProcessError.stderr` (a hardcoded SDK placeholder). R4's pattern must match against that corpus (`cortex_command/pipeline/dispatch.py:504-521`, `:914-918`).
- The test stub `cortex_command/tests/_stubs.py` `ClaudeAgentOptions` is a fixed-field `@dataclass` installed by the pipeline/overnight conftests — R2 must add `cli_path` to it or every `dispatch_task` test raises `TypeError` at construction.
- Resolution must be injectable (`CORTEX_CLAUDE_CLI_PATH` env or monkeypatch) so existing async dispatch tests can supply a path without a real system `claude` on PATH; resolve once at runner startup and thread the path down rather than resolving per-dispatch.
- Existing effort/guard tests at `cortex_command/pipeline/tests/test_dispatch.py:1042-1265` must continue to pass; the existing model-capability guard (`resolve_effort`/`_MODEL_SUPPORTED_EFFORTS`) is retained unchanged. Add new coverage for the resolver, the clamp-retry, and the warn-ignore detection.
- On the scheduled path, the runner's PATH is snapshotted at schedule time into the plist (`cortex_command/overnight/scheduler/macos.py:_snapshot_env`); R1 resolves against that snapshot, and the `CORTEX_CLAUDE_CLI_PATH` override exists for operators whose scheduled PATH does not expose the intended `claude`.

## Open Decisions

None — the critical-review forks (probe vs no-probe, fail-loud vs degrade-loud, pin-only vs prefer-newer) were resolved by firsthand CLI evidence and the operator's "best long-term fix / must run" directive: prefer-newer CLI + clamp-loud/warn-loud resilience.

## Proposed ADR

### Proposed ADR: 0014-resolve-best-claude-cli-and-resilient-effort-handling

**Context:** `claude-agent-sdk` bundles its own `claude` and prefers it over the system install (`_find_cli()` is bundled-first); the bundled binary lagged and hard-rejected `--effort xhigh`. Effort capability cannot be reliably probed (modern `claude` warn-ignores unknown efforts, exit 0). **Decision:** cortex resolves and pins the **newer of system-vs-bundled** `claude` (`cli_path`, with a `CORTEX_CLAUDE_CLI_PATH` override), uses that same binary for the orchestrator spawn, and handles an unsupported effort by **outcome, from captured stderr** — clamping to a universally-accepted ceiling and retrying once on a hard-reject, or surfacing a loud note on a warn-ignore — rather than failing the feature or trusting a capability probe. **Trade-off:** cortex takes on CLI version-comparison and stderr-outcome handling, and depends on the operator's CLI ecosystem for *optimal* (`xhigh`) quality; in exchange it guarantees the highest-value features **run** at the best effort any present CLI supports, never silently degrade, and never lag on the stale bundle. This is honest about not granting absolute version control (the operator's installer still drives the system-CLI version) — it grants "use the best available, always run, always visible." Surprising without context (overriding the SDK's bundled CLI; clamping effort) and a real, somewhat-hard-to-reverse policy choice — meeting the ADR three-criteria gate.
