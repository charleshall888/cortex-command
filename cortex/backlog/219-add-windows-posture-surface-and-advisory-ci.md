---
id: 219
title: "Add Windows posture surface and advisory CI"
type: feature
status: not-started
priority: medium
parent: 215
blocked-by: [216]
tags: [windows-support, posture, docs, sandbox, ci]
created: 2026-05-15
updated: 2026-05-15
discovery_source: cortex/research/windows-support/research.md
---

# Add Windows posture surface and advisory CI

## Role

Materialize the project's "macOS-primary, Windows best-effort" posture as a coherent surface: documentation that names the caveats, a runtime warning that surfaces the transitional sandbox gap at the moment of exposure, an advisory Windows-smoke CI job that catches install-time regressions on every PR, and a reconciliation of the observability docs with the actual logger-only alert dispatch implementation. Documentation separates the transitional safety-property delta (sandbox not yet enforced on native Windows; planned by Anthropic) from ergonomic deltas (tmux is user-managed, caffeinate/osascript are macOS-only with no-op fallbacks, justfile recipes and tests/test_*.sh depend on Git for Windows). The runtime warning fires from both cortex-init startup and overnight-runner startup so a Windows user sees it at the surface where the sandbox gap actually matters. The warning is intentionally transient — it gets deleted from the codebase once Anthropic ships native-Windows sandbox enforcement, with no other code changes required because the JSON config cortex writes is forward-compatible.

The advisory CI job uses `runs-on: windows-latest` and runs cortex --version plus `cortex init --dry-run` plus a pruned subset of the pytest suite that excludes files with module-level POSIX imports (a small `--ignore` list covering test_auth_bootstrap.py and the four test_runner_*.py files that reference fcntl or signal.SIGHUP at import time). The observability docs reconciliation removes the "three notification channels via terminal-notifier and ntfy.sh" wording from observability.md and replaces it with the truthful description (dashboard alerts are logger-only; terminal-notifier and ntfy.sh are user-supplied via `~/.claude/notify.sh`).

## Integration

Reads the WINDOWS boolean from the platform abstraction package to decide whether to fire the warning. Writes the warning emission into two specific lifecycle hooks: cortex-init startup and overnight-runner startup. Modifies the project's three posture-bearing documents (top-level README, setup docs, project-level requirements doc) plus observability.md. Adds one advisory GitHub Actions workflow that runs on Windows hosts.

## Edges

- Breaks if the WINDOWS boolean's contract changes (this piece consumes a boolean from the platform package).
- Depends on the project requirements doc's posture statement remaining the canonical source of cortex's stated platform support.
- The runtime warning's deletion is the cortex-side response when Anthropic ships native-Windows sandbox enforcement — the warning emission is the only code change required at that future moment.
- The advisory CI job is non-blocking; its job-status reporting is the contract surface between the workflow and PR reviewers.
- The CI smoke job's pytest `--ignore` list is a moving target: files added later that import fcntl or signal.SIGHUP at module level will silently start crashing the Windows smoke job until added to the list (or until the imports are guarded inside functions). Documented as a contributor convention.

## Touch points

- `README.md` (Prerequisites section; posture statement)
- `docs/setup.md` (Dependencies section; Windows notes; bash-tool-dependency caveat for justfile + tests/test_*.sh + .githooks/pre-commit)
- `cortex/requirements/project.md` (Project Boundaries and Quality Attributes sections; posture statement)
- `cortex/requirements/observability.md` (Notifications section; reconcile spec text with logger-only dispatch reality)
- `cortex_command/init/handler.py` (cortex-init startup; warning emission point on Windows)
- `cortex_command/overnight/runner.py` (overnight-runner startup; warning emission point on Windows)
- `tests/test_auth_bootstrap.py` (fcntl module-level import — candidate for CI ignore-list or function-level import guard)
- `tests/test_runner_signal.py` and `tests/test_runner_threading.py` and `tests/test_runner_followup_commit.py` and `tests/test_runner_sigterm_propagation.py` (SIGHUP references — candidates for CI ignore-list or function-level import guard)
- `.github/workflows/windows-smoke.yml` (new advisory CI workflow on `runs-on: windows-latest`)
- `.github/workflows/validate.yml` (existing workflow; reference for the new advisory workflow's structure)
