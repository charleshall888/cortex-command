---
schema_version: "1"
uuid: f5c58535-ce2b-4bb1-8e73-26cf71ea0cca
title: "Investigate daytime pipeline blockers: subprocess auth + task-selection re-runs completed tasks"
status: complete
priority: medium
type: bug
created: 2026-04-22
updated: 2026-04-22
tags: [overnight, daytime-pipeline, auth, parser]
session_id: null
lifecycle_phase: complete
lifecycle_slug: investigate-daytime-pipeline-blockers-subprocess-auth-task-selection-re-runs-completed-tasks
complexity: complex
criticality: high
spec: lifecycle/investigate-daytime-pipeline-blockers-subprocess-auth-task-selection-re-runs-completed-tasks/spec.md
areas: [overnight-runner]
---

## Context

After `f1caec4` (CORTEX_WORKTREE_ROOT override) unblocked the `.claude/worktrees/` sandbox issue, end-to-end testing of `claude/overnight/daytime_pipeline.py` against lifecycle 100 surfaced two further blockers. Worktree creation, file checkout, PID write, and dispatch loop startup all succeed. Then the first task dispatch fails, pauses, and exits.

## Problem 1: Subprocess auth failure

`claude_agent_sdk` spawns the `claude` CLI to execute tasks. The CLI returns `"Not logged in · Please run /login"` even when invoked from a parent interactive Claude Code session that is authenticated.

Sequence from `lifecycle/rewrite-verification-mindsetmd-to-positive-routing-structure-under-47-literalism/events.log` (2026-04-23T00:30:29Z–00:30:32Z):

```
dispatch_start     feature=... model=sonnet effort=medium max_turns=20 max_budget_usd=25
dispatch_progress  message_type=assistant content_preview="Not logged in · Please run /login"
dispatch_complete  cost_usd=0 duration_ms=42 num_turns=1
dispatch_error     error_type=unknown detail="Exception: Command failed with exit code 1"
brain_unavailable  retry_count=2
brain_decision     action=pause reasoning="Brain agent unavailable"
feature_paused     details.error="Task 2 failed after 2 attempts"
```

The dispatch loop retries twice, then pauses. The subprocess auth resolution does not inherit from the parent session. The overnight runner (`claude/overnight/runner.sh`) must solve this problem to work unattended — compare launch contexts to see how auth is propagated there.

Possible lines of investigation:
- Env vars the overnight runner sets before invoking the pipeline (`ANTHROPIC_API_KEY`, `CLAUDE_CODE_*`, etc.)
- Whether the SDK uses `~/.claude/credentials.json` or a similar user-scoped auth file the subprocess can read
- Whether `claude -p` honors an explicit `--api-key` flag or config that the SDK could pass through

## Problem 2: Pipeline picks `[x] complete` tasks

The pipeline dispatched Task 2 (`"Capture baseline commit SHA and reference-file line counts"`) even though its Status field in `lifecycle/.../plan.md` reads `[x] complete`.

`claude/pipeline/parser.py::_parse_field_status` (line 385) handles `[x]` correctly — its test suite is green. So the pipeline's task-selection path is either:
- Not calling `_parse_field_status` at all (uses a different code path)
- Calling it but ignoring the `done` result
- Reading a stale or different plan.md than the one on disk

The failing task in the events.log includes the `[x]` suffix I added to the heading line (`"task": "Capture baseline commit SHA and reference-file line counts [x]"`), which confirms the pipeline read the heading but not the Status filter result.

## Reproduction

```bash
DAYTIME_DISPATCH_ID=$(python3 -c 'import uuid; print(uuid.uuid4().hex)') \
CORTEX_WORKTREE_ROOT=$TMPDIR/cortex-worktrees \
.venv/bin/python3 -m claude.overnight.daytime_pipeline \
  --feature <lifecycle-slug-with-mixed-done-and-pending-tasks>
```

Any lifecycle dir where `plan.md` has both `[x] complete` and `[ ] pending` Status lines reproduces Problem 2. Problem 1 reproduces on any pipeline run from an interactive session without explicit auth env propagation.

## Scope

- Root-cause both issues; land fixes or file follow-up tickets per issue.
- Fixes must not couple to lifecycle 100 — these are harness-level blockers for any daytime pipeline run.

## Out of scope

- The CORTEX_WORKTREE_ROOT fix itself — landed in `f1caec4`.
- The `events.log` YAML-header parser noise (`events.py:251: skipping malformed JSON line`) from the pre-existing `clarify_critic` YAML block at the top of older events.log files. Cosmetic, pre-existing, track separately if actionable.

## Related

- `f1caec4` — CORTEX_WORKTREE_ROOT override (this fix's immediate predecessor)
- Ticket #128 — pre-commit hook rejecting main commits during overnight sessions (adjacent harness reliability work)
- Lifecycle 100 — first real-world lifecycle blocked by these issues; can be hand-finished by invoking `probe-apparatus.sh` directly for the remaining 28 hedge trials once auth is sorted
