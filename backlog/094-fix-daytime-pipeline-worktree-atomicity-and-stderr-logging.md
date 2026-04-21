---
schema_version: "1"
uuid: c5f87db4-a25a-4fdb-a133-debdf84564e0
title: "Fix daytime pipeline worktree atomicity and stderr logging"
status: refined
priority: high
type: feature
created: 2026-04-20
updated: 2026-04-21
parent: "93"
tags: [lifecycle, daytime-pipeline, worktree, reliability]
discovery_source: research/revisit-lifecycle-implement-preflight-options/research.md
areas: [pipeline]
complexity: complex
criticality: high
spec: lifecycle/fix-daytime-pipeline-worktree-atomicity-and-stderr-logging/spec.md
session_id: null
---

# Fix daytime pipeline worktree atomicity and stderr logging

Two defects in `claude/pipeline/worktree.py::create_worktree` cause daytime-pipeline startup failures to leave orphaned branches behind and hide the underlying git error from the operator.

## Findings from discovery

**Atomicity defect**: `git worktree add -b` creates the branch before performing checkout. If checkout fails, the branch persists as an orphan. `create_worktree` has no try/except to clean up. Reproduced on lifecycle 69 (`suppress-internal-narration-in-lifecycle-specify-phase`, 2026-04-17); the user had to manually delete `pipeline/{feature}` before retry could succeed. `_resolve_branch_name` fallback (`-2`, `-3`) *should* make retries work automatically, but only if the orphan-accumulation is bounded — the current code allows unbounded accumulation across failures.

**Logging defect**: `subprocess.run(capture_output=True, check=True)` swallows git's stderr into `CalledProcessError.stderr`, which never reaches `daytime.log`. The user sees only "returned non-zero exit status 128" with no git error text. This is what made lifecycle 69's failure unreadable and left the underlying cause unknown.

## Research Context

See `research/revisit-lifecycle-implement-preflight-options/research.md` DR-4. Important constraint: the ticket ships the *fix*, not a root-cause diagnosis. The Seatbelt hypothesis in the first-draft research was incorrect (contradicted `claude/rules/sandbox-behaviors.md:26-31`). Multiple plausible causes remain (stale `.git/worktrees/{feature}/` dir, unfetched `main`, `.venv` symlink collision, locked worktree). Surface the stderr, then diagnose on next reproduction.

## Acceptance

- `create_worktree` cleans up an orphaned branch if `git worktree add -b` fails after creating the branch.
- `create_worktree` surfaces git's stderr in the exception message (or in a structured log line to `daytime.log`).
- Existing callers (`daytime_pipeline.py`, overnight batch runner) continue to work.
- Tests exist covering the failure-then-cleanup path.

## Out of scope

- Diagnosing the actual root cause of lifecycle 69's exit 128 (tracked as a follow-up; close when either recurrence produces a new stderr or the failure demonstrably stops after the fix).
- Changes to `_resolve_branch_name` fallback logic.
- Any change to the pre-flight in `implement.md`.
