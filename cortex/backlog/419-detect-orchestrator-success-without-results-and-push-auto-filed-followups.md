---
schema_version: "1"
uuid: 9c77ddc8-71d1-4c78-8774-55d1eb1ccffa
title: Detect orchestrator success-without-results and push auto-filed followups
status: backlog
priority: high
type: bug
created: 2026-07-28
updated: 2026-07-28
tags: ['harness', 'overnight', 'observability']
areas: ['tooling']
---
## Why

Session `overnight-2026-07-28-0256` (2026-07-28) burned **$7.60 and 14m32s of a 6h budget across 13 orchestrator turns, produced zero implementation, and reported the cause as two feature failures.** Both defects below are measured from that session's artifacts, not hypothesised.

**Defect A — an orchestrator that does a fraction of its job exits `success`.** The round-1 orchestrator completed plan generation (its Steps 1–4), wrote `batch-plan-round-1.md`, and returned `subtype: "success"`, `is_error: false`, `permission_denials: []`. Its own closing summary ends at "**Step 4** — `generate_batch_plan` produced `batch-plan-round-1.md`" and notes "Plans not committed, per instruction" — it treated Step 4 as terminal. It never dispatched implementation agents and never wrote `batch-1-results.json`.

Nothing checks for that. `map_results.py:244` tests `results_path.exists()`, misses, and falls through to `_handle_missing_results()` (`:150-176`), which walks the batch plan and stamps **every** feature `status: failed` with the hardcoded string `"batch_runner.py did not produce results file"`. The resulting morning report blamed both features and auto-filed two "Follow up: … — failed" tickets. The only evidence the implementation phase never began was `started_at: null` on both features, which no surface reads. An operator without a transcript would have retried two correctly-specced features against a harness fault.

**Defect B — the followup commit lands after the push, so auto-filed tickets never leave the machine.** In `_post_loop`, the integration branch is pushed (`runner.py:2083`) and the PR opened (`:2234-2256`) *before* `_commit_followup_in_worktree` (`:1017`, `:2532`) runs. Measured on this session: `session_complete` at 02:14:40 EDT, push and PR between 02:14:40–02:14:42, followup commit `d883ea16` at 02:14:44. The remote branch head was `06ca7d68`; PR #26 merged that alone. Tickets #419 and #420 existed only on the unpushed local branch tip and became unreachable when the merged branch was deleted. Every auto-filed followup ticket is silently lost this way — the loss is invisible because the morning report lists the items it *created*, not the ones that survived.

## Role

Close both holes so a partial orchestrator run is reported as a harness fault against the orchestrator, and so auto-filed followups reach the remote.

- **A**: after a round's orchestrator exits, treat "exited success but wrote no `batch-{N}-results.json`" as a distinct, named condition rather than an alias for per-feature failure. Attribute it to the round, keep the features at their pre-round status, and surface the discrepancy (agent said success; contract artifact absent) where the operator reads it.
- **B**: ensure the followup commit is part of what gets pushed — either by committing followups before the push/PR step, or by pushing again after them.

## Integration

Defect A sits between `runner.py`'s round loop and `map_results.py`'s state mapping; the generic error string at `map_results.py:175` is the surface that currently absorbs it. Defect B is an ordering fix inside `_post_loop`. Both are independently landable; A is the one that cost the night.

## Edges

- `_handle_missing_results` must keep its current behaviour when the orchestrator genuinely fails (non-zero exit, `is_error: true`) — the fix is to distinguish success-with-no-artifact from failure, not to remove the fallback.
- `started_at: null` is the existing signal that a feature never entered implementation; whatever reports Defect A should key off something at least that reliable.
- Defect B's fix must not push a branch the PR-gating step deliberately declined to push.
- Non-goal: changing the orchestrator prompt so it doesn't stop at Step 4. Worth doing, but a prompt fix cannot be relied on to hold — the harness needs the guard regardless.
- Non-goal: re-running session `overnight-2026-07-28-0256`. Its two plans landed on main via PR #26 and are reusable as-is.

## Touch points

- `cortex_command/overnight/map_results.py:150-176,244-256` — the missing-results fallback and its hardcoded error string
- `cortex_command/overnight/runner.py:1344-1360` — `_apply_batch_results` and its own `results_path.exists()` branch
- `cortex_command/overnight/runner.py:2083,2234-2256` — push and PR creation
- `cortex_command/overnight/runner.py:619-689,1017,2532` — `_commit_followup_in_worktree` and its callsites
- `cortex_command/overnight/report.py` — morning-report rendering of failed features
- Evidence: `cortex/lifecycle/sessions/overnight-2026-07-28-0256/` (`overnight-events.log`, `runner-stdout.log`, `orchestrator-round-1.stdout.json`, `batch-plan-round-1.md`); dangling commit `d883ea16`