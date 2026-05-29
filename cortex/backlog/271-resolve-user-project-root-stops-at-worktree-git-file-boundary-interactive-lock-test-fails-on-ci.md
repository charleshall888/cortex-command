---
schema_version: "1"
uuid: e1e36524-ec46-4937-aced-d8f415db603f
title: "_resolve_user_project_root stops at worktree .git-file boundary (interactive-lock test fails on CI)"
status: complete
priority: medium
type: bug
created: 2026-05-28
updated: 2026-05-29
complexity: complex
criticality: high
spec: cortex/lifecycle/resolve-user-project-root-stops-at/spec.md
areas: ['lifecycle']
lifecycle_phase: plan
---
## Why

`tests/test_interactive_lock_sandbox.py::test_lock_write_from_worktree_cwd` fails whenever it actually runs — i.e. on a host where `sandbox-exec` can apply a fresh profile (vanilla macOS / CI), not inside a nested Seatbelt container. It asserts that `cortex_command.interactive_lock acquire` invoked with CWD inside a git worktree writes its lock to the **main repo's** `cortex/lifecycle/<slug>/interactive.pid`. It fails with `CortexProjectRootError` because `_resolve_user_project_root()` in `cortex_command/common.py` treats any `.git` — file *or* directory — as a hard stop for its upward walk. From a worktree (whose `.git` is a *file* containing `gitdir: <main>/.git`), the walk breaks at that boundary instead of following the pointer to the main repo. `_lock_path`'s docstring explicitly promises "always resolved against the main repo root (never CWD-relative)" — so the resolver contradicts the documented lock contract.

Surfaced during #269's Complete test gate but is **unrelated to #269**: the code is untouched by it and the failure reproduces at the base commit. The test only *runs* when not in a nested sandbox, so it SKIPS (and silently passes) in Claude Code dev sessions and the overnight runner — masking the failure everywhere except vanilla macOS CI.

## Role

Decide and implement the resolver's worktree semantics: when a cortex CLI is invoked from inside a git worktree, should the project root resolve to the **worktree** root or to the **main** repo? Then make `_resolve_user_project_root` (and its `_from_cwd` twin) and the test agree.

## Integration

`_resolve_user_project_root` is foundational — **87 call sites across 17 modules** (backlog, dashboard, overnight orchestrator, CLI, interactive lock, lifecycle events). Any change to worktree-boundary handling redirects where ALL of these resolve the root when run from a worktree, so the decision must be deliberate (this is why it was NOT patched inline during #269). For real interactive worktrees (full checkouts that DO contain `cortex/`), the current resolver returns the *worktree* root on the first iteration — so the interactive lock lands in the worktree, not main, likely defeating the cross-session lock visibility #241 guards. The test encodes the "resolve to main" intent.

## Edges

- The test only runs when not in a nested Seatbelt sandbox; inside Claude Code / overnight it SKIPS (capability probe `_sandbox_exec_can_apply()` → False), so the failure is invisible there but real on vanilla macOS CI.
- Two functions share the buggy walk: `_resolve_user_project_root` (env-first) and `_resolve_user_project_root_from_cwd` (cwd-only). A fix likely touches both.
- `common.py` edits are lifecycle-gated per CLAUDE.md.
- Candidate fix shape: when `.git` is a file, parse `gitdir:` (or shell out to `git rev-parse --git-common-dir`) to locate the main worktree root, then continue the `cortex/` search there — but verify this doesn't regress the 87 call sites that currently expect worktree-local resolution.

## Touch points

- `cortex_command/common.py:56-104` — `_resolve_user_project_root` walk (the `.git`-boundary break).
- `cortex_command/common.py:107-148` — `_resolve_user_project_root_from_cwd` (same walk).
- `cortex_command/interactive_lock.py` — `_lock_path` / `_events_log_path` consumers whose "main repo root" docstring contract is violated.
- `tests/test_interactive_lock_sandbox.py::test_lock_write_from_worktree_cwd` — the failing assertion encoding the intended semantics.

## References

- Area: #241 (interactive worktree concurrency guards — added this test as #241 Task 3), #201 (upward-walking project root detection), #237 (worktree-interactive implement mode).
- Surfaced during #269 Complete gate (pre-existing, unrelated).