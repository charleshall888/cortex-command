---
schema_version: "1"
uuid: a1f29ece-2e13-4f04-b2f1-ac04d6ba43cc
title: _resolve_main_repo_root validates its CWD branch but returns CORTEX_REPO_ROOT unchecked
status: backlog
priority: medium
type: bug
created: 2026-08-13
updated: 2026-08-13
tags: ['lifecycle', 'worktree', 'env', 'resolver']
areas: ['lifecycle']
---
Split out of #487, which guarded verb-locally rather than touch this shared resolver.

## Why

`interactive_lock._resolve_main_repo_root` is internally inconsistent about trust. Its CWD branch guards the parsed candidate with `(candidate / "cortex").is_dir()` (`:186`) and falls through when that fails; its env branch returns `Path(env_root).resolve()` verbatim (`:177-179`) — no existence check, no `cortex/` check. The env path is strictly **less** validated than the CWD path inside one function.

Every verb pinned by #484 resolves through this, so a poisoned value silently redirects the log every one of them reads and appends to.

## Evidence

Measured 2026-08-13: `CORTEX_REPO_ROOT=/nonexistent/bogus` yields `resolve_main_repo_root() -> /nonexistent/bogus` and `resolve_events_log(slug)` beneath it, with `exists: False`. The variable is not obscure — `docs/setup.md:66,158` instruct operators to export it to run the `cortex-*` shims from outside a project, and `cortex_command/cli.py:476` already calls it "the unvalidated root funnel read by dozens of modules".

Three sibling resolvers already validate it and fall through on failure: `log_invocation.py:78-83` (`.git` marker), `backlog/_telemetry.py:54-58` (marker, else `git rev-parse --show-toplevel`), `overnight/cli_handler.py:175,190`. ADR-0013:37 states the rule directly: "a poisoned value (`/`, marker-less, missing) is rejected and falls through rather than being trusted."

## Role

Decide whether the shared resolver should honour ADR-0013 like its siblings, and if so apply the same fall-through.

## Edges

- **This is a behavior change for every pinned verb**, which is exactly why #487 declined it and added a verb-local guard (its Req 2a) instead. Weigh the blast radius on its own terms; do not treat #487 as precedent for changing it.
- The overnight paths set the variable deliberately and correctly (`runner.py:1964,2902`; `dispatch.py:700`), so validation must not break them — all three point at real trees.
- A fall-through changes failure mode from "silently wrong root" to "walks from CWD", which is not free: a verb legitimately run from outside any project would start erroring instead of using the env pin. Check that population before changing it.

## Touch-points

- `cortex_command/interactive_lock.py:149-200` — `_resolve_main_repo_root`, `:177-179` env branch vs `:186` CWD guard
- `cortex_command/lifecycle/log_resolver.py` — the public alias every pinned verb calls
- `cortex/adr/0013-*.md` — the stated rule this diverges from
