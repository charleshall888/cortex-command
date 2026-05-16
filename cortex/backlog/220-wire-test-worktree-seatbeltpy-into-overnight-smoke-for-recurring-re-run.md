---
schema_version: "1"
uuid: 1d44844b-a690-4eeb-97e3-31a176af2e80
title: "Wire test_worktree_seatbelt.py into overnight smoke for recurring re-run"
status: backlog
priority: should-have
type: feature
tags: [overnight, sandbox, worktree, evidence-durability]
created: 2026-05-15
updated: 2026-05-15
---

Originated from critical-review of `cortex/lifecycle/restore-worktree-root-env-prefix/plan.md` (Objection: R10/R11 evidence chain not re-validated after lifecycle close).

## Context

The seatbelt-active integration test `tests/test_worktree_seatbelt.py` is gated by `pytest.mark.skipif(os.environ.get("CLAUDE_CODE_SANDBOX") != "1", ...)`, and CI does not set that env var. The parent lifecycle's `f_row_evidence` event records a one-time manual pass under sandbox; a future regression in `resolve_worktree_root()` that breaks Seatbelt-writability surfaces only when the next implementer manually re-runs.

## Proposed approach

Wire the seatbelt test into the overnight smoke test. Overnight runs are Claude Code sessions where `CLAUDE_CODE_SANDBOX=1` is set by default, so every overnight session would re-verify the property and emit a fresh F-row analogue to the session's events.log.

## Why deferred from parent lifecycle

Out-of-scope for `restore-worktree-root-env-prefix` because it touches the overnight smoke wiring, which is the parent spec's Non-Requirements boundary. The parent lifecycle's plan strengthens evidence integrity for the one-time gate (Task 11's `pytest_summary`/`stdout_sha256` fields); recurring re-run is the orthogonal hardening pass tracked here.

## Acceptance

- Overnight smoke runs invoke `tests/test_worktree_seatbelt.py` with `CLAUDE_CODE_SANDBOX=1`.
- A passing run records a fresh F-row analogue to the overnight session's events.log (durable, integrity-bound to the pytest run via `stdout_sha256`).
- A regression in `resolve_worktree_root()` that breaks Seatbelt-writability surfaces in the morning report rather than only on manual re-run.

## Linked artifacts

- `cortex/lifecycle/restore-worktree-root-env-prefix/plan.md` — Risks block (residual)
- `cortex/lifecycle/restore-worktree-root-env-prefix/critical-review-residue.json` — full B-class findings
