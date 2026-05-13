---
schema_version: "1"
uuid: d5bbd0b7-7968-4c1f-b4fc-2a2ef3669800
title: "Harden autonomous-dispatch path for interactive Claude Code sessions"
status: in_progress
priority: high
type: chore
tags: [overnight, lifecycle, daytime-pipeline, sandbox, auth, packaging]
created: 2026-05-12
updated: 2026-05-12
complexity: complex
criticality: high
spec: cortex/lifecycle/harden-autonomous-dispatch-path-for-interactive/spec.md
areas: [overnight-runner]
session_id: f073ff5d-c2e5-41c5-91e0-12e13cb2a16d
lifecycle_phase: plan
---

# Harden autonomous-dispatch path for interactive Claude Code sessions

## Context

`/cortex-core:lifecycle implement` → "Implement in autonomous worktree" launched from an interactive Claude Code session fails three times in succession before reaching the first task dispatch. Each failure is a different symptom of the same root: `skills/lifecycle/references/implement.md` §1a hardcodes a runtime contract that the launchd-fired runner satisfies but the Bash-tool–invoked dev path does not.

## Findings

### F1. Auth path — `vector="none"` semantics inconsistent and unverified

- `cortex_command/overnight/runner.py:2042-2045` wraps `ensure_sdk_auth` in `try/except` and continues regardless. `cortex_command/overnight/daytime_pipeline.py:341-352` hard-failed on `vector="none"` with `startup_failure`. Two related code paths, opposite policies, no shared abstraction enforcing parity.
- `ensure_sdk_auth`'s own warning text says "claude -p will use Keychain auth if available" — implying Keychain is a valid fallback — but no probe verifies Keychain actually resolves in subprocess context. Inferred behavior is treated as fact.
- Uncommitted local patch on `daytime_pipeline.py` removes the hard-fail to match runner. Achieves parity but does not probe — failures now happen per-task inside the pipeline instead of cleanly at startup. The patch should be replaced by a real Keychain probe; see [[208-runner-keychain-probe]] if split out.

### F2. Sandbox/.mcp.json — escape hatch designed, never wired into the skill

- `cortex_command/pipeline/worktree.py:11-14` documents the issue: "Claude Code Seatbelt profile blocks .mcp.json checkout into .claude/worktrees/". Escape hatch exists: `CORTEX_WORKTREE_ROOT` env var relocates worktrees to a sandbox-friendly path.
- `skills/lifecycle/references/implement.md:91` launches `python3 -m cortex_command.overnight.daytime_pipeline` without setting `CORTEX_WORKTREE_ROOT`. The skill's only authored test bed (launchd) doesn't hit the sandbox, so the gap survived review.
- Result: every interactive autonomous dispatch dies at `git worktree add` with "unable to create file .mcp.json: Operation not permitted" unless the operator manually disables sandbox.

### F3. Python env / entry-point gap

- `pyproject.toml` `[project.scripts]` covers 6 entries (`cortex`, `cortex-batch-runner`, `cortex-update-item`, `cortex-create-backlog-item`, `cortex-generate-backlog-index`, `cortex-build-epic-map`).
- Skills, hooks, docs, and bin shims invoke ~13 additional modules via bare `python3 -m cortex_command.<x>`: `overnight.daytime_pipeline`, `overnight.daytime_dispatch_writer`, `overnight.daytime_result_reader`, `overnight.report`, `overnight.integration_recovery`, `overnight.interrupt`, `overnight.complete_morning_review_session`, `critical_review`, `discovery`, `common`, `backlog.ready`, `pipeline.metrics`, `overnight.auth` (`--shell`).
- Bare `python3` resolves to system Python. `cortex_command/` is importable because CWD is on `sys.path`; `claude_agent_sdk` is in `.venv/` and is NOT importable. Partial-resolution masks the env mismatch until module-load time, at which point the daytime pipeline aborts with "claude_agent_sdk is not installed". Same risk for any other skill that runs from a cloned repo rather than a `uv tool install` deployment.
- Existing bin shims like `bin/cortex-morning-review-complete-session:14` manually prepend `PYTHONPATH=$CORTEX_COMMAND_ROOT` as a workaround. Inconsistent — most modules have no wrapper.
- `skills/overnight/references/new-session-flow.md:3` documents the intent: "after `uv tool install`, the cortex console script is available globally and `cortex_command.*` is importable inside the tool venv." The dev-clone path is not covered.

### Cross-cutting

The three findings are symptoms of the same root: **the autonomous-dispatch skill was authored against the launchd-fired path** (sandbox-free, runs `cortex` from an absolute path produced at schedule time, env vars set explicitly). **The Claude Code Bash-tool path was never on the test matrix**, so every assumption that holds for launchd but fails under a sandboxed, PATH-derived `python3` made it through review.

Same pattern likely exists for `/cortex-core:discovery`, `/cortex-core:critical-review`, `/cortex-core:morning-review`, and lifecycle `detect-phase`, all of which use bare `python3 -m cortex_command.<x>`. Not verified — listed as suspects.

## Suggested boundaries

- One lifecycle covering F1+F2+F3 as a unit (user-requested).
- Replace the uncommitted `daytime_pipeline.py` auth patch with a probe-based solution, not extend it.
- Out-of-scope (worth flagging): a `cortex doctor` / preflight that checks all three before dispatch. File separately if confirmed.

## References

- `cortex_command/overnight/daytime_pipeline.py:336-352` — auth check site (currently soft-fall-through, uncommitted)
- `cortex_command/overnight/auth.py:128-152, 183-246` — `_read_oauth_file` + `ensure_sdk_auth`
- `cortex_command/overnight/runner.py:2042-2045` — runner's existing non-fatal pattern
- `cortex_command/pipeline/worktree.py:1-14, 70-` — `CORTEX_WORKTREE_ROOT` doc + `create_worktree`
- `skills/lifecycle/references/implement.md:78-100` — §1a Daytime Dispatch launch sequence
- `pyproject.toml` `[project.scripts]` — current entry points
- `bin/cortex-morning-review-complete-session` — existing PYTHONPATH workaround pattern
- `skills/overnight/references/new-session-flow.md:3` — documented intent (uv-tool-install)
- `cortex/lifecycle/requirements-skill-v2/daytime.log` + this session's events.log — three failed dispatches that surfaced F1/F2/F3 in order

