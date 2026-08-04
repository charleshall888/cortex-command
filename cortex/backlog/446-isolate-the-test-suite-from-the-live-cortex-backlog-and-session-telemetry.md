---
schema_version: "1"
uuid: 5be773ec-dd91-4862-a41c-380f8ab8ffea
title: Isolate the test suite from the live cortex/backlog and session telemetry
status: complete
priority: medium
type: bug
created: 2026-08-03
updated: 2026-08-04
tags: ['harness', 'testing', 'backlog-verbs']
areas: ['backlog']
---
## Why

`uv run pytest tests/` mutates the live `cortex/backlog/` corpus. Measured 2026-08-03: hashed all 441 backlog files, ran the suite, re-hashed — the run rewrote `445-*.md` and `index-full.json`. The same run wrote telemetry into the live `cortex/lifecycle/sessions/<session-id>/bin-invocations.jsonl`, filling the operator's own session log with `cortex-archive-rewrite-paths`, `cortex-morning-review-close-tickets`, `cortex-morning-review-push-closures` and 14 `cortex-update-item` calls that the session never issued.

That log pollution has already caused a wrong conclusion: on 2026-08-03 it was read as evidence that a concurrent session could not have reverted four backlog tickets, because that session's log held only read-only verbs. The reasoning was inverted by the noise, and the real cause went unfound until a memory file confessed it.

## Role

Test isolation for the backlog verbs: a suite run leaves the live `cortex/` tree byte-identical, so `git status` after `just test` reflects only the operator's own edits.

## Integration

The leak is at the module-level `BACKLOG_DIR` resolution, not in the tests. `update_item.py:731` and `create_item.py:263` both compute `BACKLOG_DIR = _resolve_user_project_root() / "cortex" / "backlog"` at call time, so any test that subprocesses `cortex-update-item` or `cortex-create-backlog-item` with cwd at the repo root resolves to the live corpus. `ready.py:58` has the same shape against `Path.cwd()`.

## Edges

- The fix is an env-var or fixture-level redirect honored by the verbs, not a per-test patch — a per-test patch leaves the next new test free to leak again.
- Session telemetry resolves separately from `BACKLOG_DIR`; both need redirecting or the invocation log stays polluted.
- A conftest-level guard that fails the suite when the live tree changes would make regressions self-reporting, and is cheap.
- Consumer repos run these verbs for real, so the redirect must be test-only and must not become a shipped configuration surface.
- Verification is the hash-run-rehash procedure above, not inspection.

## Touch points

- `cortex_command/backlog/update_item.py:731` — `BACKLOG_DIR` from `_resolve_user_project_root()`
- `cortex_command/backlog/create_item.py:263` — same resolution
- `cortex_command/backlog/ready.py:58` — `Path.cwd()` variant
- `tests/test_cortex_morning_review_close_tickets.py`, `tests/test_push_closures.py`, `tests/test_create_index.py` — suites invoking the mutating verbs
