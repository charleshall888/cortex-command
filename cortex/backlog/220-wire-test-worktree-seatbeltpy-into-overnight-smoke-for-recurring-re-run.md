---
schema_version: "1"
uuid: 1d44844b-a690-4eeb-97e3-31a176af2e80
title: "Re-validate test_worktree_seatbelt.py on a recurring sandbox-active run"
status: refined
priority: should-have
type: feature
tags: [overnight, sandbox, worktree, evidence-durability]
created: 2026-05-15
updated: 2026-05-16
spec: cortex/lifecycle/re-validate-test-worktree-seatbeltpy-on/spec.md
---

Originated from critical-review of `cortex/lifecycle/restore-worktree-root-env-prefix/plan.md` (Objection: R10/R11 evidence chain not re-validated after lifecycle close).

## Context

The seatbelt-active integration test `tests/test_worktree_seatbelt.py` is gated by `pytest.mark.skipif(os.environ.get("CLAUDE_CODE_SANDBOX") != "1", ...)`. The parent lifecycle's `f_row_evidence` event records a one-time manual pass under sandbox; a future regression in `resolve_worktree_root()` that breaks Seatbelt-writability surfaces only when the next implementer manually re-runs the test.

## Premise check (done 2026-05-16)

The parent lifecycle's first draft of this ticket proposed "wire the test into the overnight smoke test." A premise check confirmed only **half** of that holds:

- **Confirmed**: overnight runs spawn a Claude Code session via `cortex_command/overnight/runner.py:1037` with `--settings <sandbox-file>` enforcing `sandbox.filesystem.{denyWrite,allowWrite}` and `failIfUnavailable: true` (`cortex_command/overnight/sandbox_settings.py:195`). `--dangerously-skip-permissions` suppresses permission prompts but does **not** disable Seatbelt. Inside that session's Bash tool, `CLAUDE_CODE_SANDBOX=1` is set by Claude Code — pytest invocations from there would unskip the seatbelt test.
- **Refuted**: `cortex_command/overnight/smoke_test.py` itself is **not** a Claude Code session. It is the orchestrator-level integration test invoked as a regular Python subprocess (`uv run python3 -m cortex_command.overnight.smoke_test`). Its env does not have `CLAUDE_CODE_SANDBOX=1`. Adding a `subprocess.run(["pytest", "tests/test_worktree_seatbelt.py"])` to `smoke_test.py` would leave the test skipped, defeating the purpose.

The right surface is **inside the orchestrator session that `smoke_test.py` spawns** (or any equivalent live Claude Code session), not the smoke wrapper that surrounds it.

## Three implementation shapes (pick one in scope-defining session)

### Shape A: Inject the seatbelt test into the orchestrator's prompt

The smoke batch plan's task work is rewritten to invoke `pytest tests/test_worktree_seatbelt.py` via a Bash tool from inside the orchestrator session. The orchestrator's stdout captures the result. The smoke wrapper greps the captured output for "passed=2" and an F-row event analogous to `f_row_evidence` is appended to the overnight session's events.log.

**Tradeoffs**: real signal (test runs in an actually-sandboxed session); requires authoring an orchestrator prompt that does pytest as its primary work (a new pattern — current smoke task is a 1-line markdown write); the smoke runner becomes coupled to the seatbelt test's pass/fail.

### Shape B: New one-shot sandbox-active probe alongside the existing smoke

A new top-level script (e.g., `cortex_command/overnight/seatbelt_probe.py` or a `cortex-seatbelt-probe` console script) spawns `claude -p "echo $CLAUDE_CODE_SANDBOX && uv run pytest tests/test_worktree_seatbelt.py -v" --settings <sandbox-file> --dangerously-skip-permissions --max-turns 4 --output-format=json` and parses the orchestrator's stdout for the pytest summary. Emits an integrity-bound F-row event matching the schema in `tests/test_worktree.py::TestVerifyR10`. Runnable on demand, e.g., wired into a justfile recipe (`just seatbelt-probe`) or a scheduled overnight cron.

**Tradeoffs**: smallest blast radius (doesn't disturb the smoke runner); adds a new top-level script; requires its own invocation cadence (recurring via cron, pre-merge hook, or manual) to actually re-validate.

### Shape C: Hook into per-feature overnight runs (not smoke)

Every overnight feature run (not just smoke) has its orchestrator prompt augmented to invoke the seatbelt test once at session start. F-row evidence accumulates across all overnight sessions, surfacing regressions on the next feature run after a breaking change lands.

**Tradeoffs**: most recurring signal (every overnight session re-validates); high blast radius (every per-feature prompt is touched); easiest to land as a `cortex_command/overnight/orchestrator.py` prompt-prefix change but creates noise (orchestrator's primary task work shouldn't be infrastructure validation).

## Recommendation

Shape B is the best fit for `should-have` priority — it isolates the probe from the orchestrator, is testable from a maintainer terminal, and aligns with `cortex_command/overnight/sandbox_settings.py`'s existing "settings JSON + claude -p" pattern. Shape A is the right answer if the smoke runner itself needs to fail when the property regresses (a stronger guarantee); Shape C is the right answer if R7-class regressions must surface within a single overnight cycle. The pick depends on the recurrence cadence the project wants.

## Acceptance

- A recurring invocation path is wired in (script + recipe, or smoke modification, or per-feature prompt prefix) such that `tests/test_worktree_seatbelt.py` actually runs (not skips) at least once per chosen cadence.
- Each successful run appends an F-row analogue event to a durable log (events.log on a per-session basis, or a top-level seatbelt-probe log) with `pytest_exit_code`, `pytest_summary`, and `stdout_sha256` matching the schema from `cortex/lifecycle/restore-worktree-root-env-prefix/spec.md` (R10/R11).
- A regression in `resolve_worktree_root()` that breaks Seatbelt-writability surfaces in the chosen path (morning report, justfile output, etc.) rather than only on manual re-run.
- A docs note in `docs/internals/sdk.md` or `docs/overnight-operations.md` documents the cadence and where evidence lands.

## Why deferred from parent lifecycle

Out-of-scope for `restore-worktree-root-env-prefix` because it touches the overnight-runner subsystem, which is the parent spec's Non-Requirements boundary. The parent lifecycle's plan strengthens evidence integrity for the one-time gate (Task 11's `pytest_summary`/`stdout_sha256` fields); recurring re-run is the orthogonal hardening pass tracked here.

## Linked artifacts

- `cortex/lifecycle/restore-worktree-root-env-prefix/plan.md` — Risks block (residual)
- `cortex/lifecycle/restore-worktree-root-env-prefix/critical-review-residue.json` — full B-class findings
- `cortex_command/overnight/runner.py:1037` — orchestrator spawn site (sandbox-active)
- `cortex_command/overnight/sandbox_settings.py:195` — `failIfUnavailable: true` default
- `cortex_command/overnight/smoke_test.py` — current smoke (NOT a Claude Code session; wrong surface)
- `tests/test_worktree_seatbelt.py` — the test that needs recurring re-validation
