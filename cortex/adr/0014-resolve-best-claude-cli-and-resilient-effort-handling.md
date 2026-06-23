---
status: accepted
---

# Resolve the best-available claude CLI and handle effort by outcome

## Context

`claude-agent-sdk` bundles its own `claude` binary and prefers it over the operator's system install: `SubprocessCLITransport._find_cli` is bundled-first, only falling back to `shutil.which("claude")` when no bundled binary exists. The hard-pinned 0.1.46 ships claude-code **2.1.69**, which predates the `xhigh` effort level and **hard-rejects** `--effort xhigh` (commander.js arg validation, exit ≠ 0). cortex correctly resolves `model=opus, effort=xhigh` for the `(complex, high)` and `(complex, critical)` cells, but the SDK ran the stale bundled binary, so **every** highest-value implement/review dispatch failed instantly — and, because an `--effort` rejection classified as a retryable `task_failure`, the retry loop re-sent the permanently-invalid flag until the budget burned (#313).

Effort capability cannot be reliably probed: firsthand testing showed modern `claude` (≥2.1.186) **warn-ignores** an unknown effort (exit 0, runs at the default) rather than hard-rejecting, so an `<cli> --effort xhigh --version` exit-code probe cannot distinguish "supported" from "silently ignored." `max` is accepted by every `claude` version including 2.1.69. The operator's priority is that these features **run**.

## Decision

cortex resolves and pins the **newer of system-vs-bundled** `claude` (`cortex_command/cli_resolver.py` → `resolve_claude_cli()`, with a `CORTEX_CLAUDE_CLI_PATH` operator/test override), pins it via `ClaudeAgentOptions(cli_path=…)` at every SDK dispatch site, and uses the same resolved binary for the orchestrator spawn — so the SDK no longer runs its bundled-first selection and the orchestrator and workers run an identical CLI. The resolver is **probe-flake-safe**: when the system CLI is present but its `--version` is unparseable (timeout/parse flake), it prefers the present system CLI (not the stale bundle) and does not memoize that forced result, so a transient flake cannot reproduce the bug or pin a degraded choice.

An unsupported effort is then handled **by outcome, from captured stderr**, not by a preflight capability probe:

- A hard-reject (`option '--effort' … is invalid`, exit ≠ 0 — only reachable on an old CLI) classifies as a distinct `effort_unsupported` error type whose recovery clamps effort **once** to `max` and retries, evaluated before the circuit breaker so the empty diff a CLI rejection produces cannot pause the loop first.
- A warn-ignore (exit 0, ran at default) is detected on the success path and recorded as a `dispatch_effort_ignored` note; the dispatch is **not** failed.

Both degradations render as a loud **Effort Degradations** section in the morning report — degradation is always surfaced, never silent.

## Three-criteria gate clearance

- **Hard to reverse** — once dispatch pins `cli_path` and effort handling keys off captured stderr, reverting to the SDK's bundled-first selection silently re-breaks every `xhigh`-class dispatch the next time the bundled CLI lags; the resolver + clamp/warn handling becomes load-bearing for the highest-value overnight work.
- **Surprising without context** — a fresh contributor would not predict why cortex overrides the SDK's own CLI selection, why effort capability is judged from stderr rather than a preflight probe (the probe cannot distinguish supported from warn-ignored), or why `max` is the clamp target.
- **Real trade-off** — cortex takes on CLI version-comparison and stderr-outcome handling, and depends on the operator's CLI ecosystem for *optimal* (`xhigh`) quality; in exchange it guarantees the features **run** at the best effort any present CLI supports, never silently degrade, and never lag on the stale bundle. This is honest about not granting absolute version control (the operator's installer still drives the system-CLI version) — it grants "use the best available, always run, always visible."

## Rejected alternatives

- **Bump `claude-agent-sdk` off the stale pin** — a snapshot patch: `_find_cli` is still bundled-first, so the bundled CLI lags system again over time and the bug recurs on the next `xhigh`-class need; 0.2.x is alpha. The prefer-newer resolver + clamp safety net make the SDK version non-blocking, so the bump is orthogonal hygiene, not the fix.
- **Exit-code capability probe (`<cli> --effort xhigh --version`)** — cannot detect capability: modern `claude` exits 0 for any effort (valid or bogus), so the probe cannot distinguish supported from warn-ignored. The reliable signal is captured stderr, not a preflight probe.
- **Fail the feature loud on any CLI shortfall** — rejected against the operator's "highest-value features must run" priority. The bundled CLI is the guaranteed-present floor; the clamp guarantees the feature runs at `max` even on the oldest CLI. A loud, degraded run that keeps the flagship work moving beats a hard fail.
- **Silent clamp/downgrade** — forbidden by the no-silent-degradation convention. A clamp or a warn-ignore is always surfaced in the morning report.

## Consequences

- `cortex_command/cli_resolver.py` is a new stdlib-only leaf module that dispatch, discovery, and the orchestrator spawn depend on; correctness for *optimal* effort depends on the operator's system `claude` being current (the `CORTEX_CLAUDE_CLI_PATH` override exists for scheduled-PATH gaps).
- An `--effort` hard-reject is bounded to exactly one clamped retry; the model/effort matrices and the `xhigh` policy (#090) are unchanged.
- The stale "silently downgraded"/`AssertionError` premises in `dispatch.py` and `docs/internals/sdk.md` are corrected to the verified hard-reject-vs-warn-ignore split.

Background lives in `docs/internals/sdk.md`; this ADR is the canonical home for the decision and its rejected alternatives.
