---
schema_version: "1"
uuid: 9589303b-4ce4-43b6-9841-aa432b068550
title: task_git_state captures every untracked file at task exit and nothing reads it, so an unstaged new file reaches main unflagged
status: should-have
priority: low
type: bug
created: 2026-08-07
updated: 2026-08-11
tags: ['overnight-runner', 'pipeline', 'gates']
areas: ['pipeline']
complexity: moderate
criticality: high
lifecycle_slug: verification-runs-in-the-dirty-worktree
---
## Why

**Re-aimed 2026-08-11.** The original Why claimed a feature's Verification runs against the
working tree so "a never-committed file passes every gate", and that "nothing in the gate chain
compares them". Verification against both repos refuted the framing: the sweep exists, the
post-merge test hook exists, and the gates were not green — the pipeline recorded the feature as
**failed** and a human merged around it. What survives is narrower and real: **the signal is
captured and no consumer reads it.**

`cortex_command/overnight/feature_executor.py:749` writes a `task_git_state` event at every
implement-task exit carrying raw `git status --short` output. In the source incident
(wild-light `overnight-2026-08-07-0252`, feature `no-gate-anywhere-runs-pytest-so`) it recorded
the defect verbatim, twice:

```
{"ts": "2026-08-07T06:18:32Z", "event": "task_git_state", "task_number": 3,
 "git_status": "?? .venv\n?? scripts/tools/run_python_tests.py\n", "new_commit_count": 2}
```

That is 44 minutes before the merge commit `db94189c` at 07:02:39. The file was never
`git add`ed, so `test-command` died with `Failed to spawn ... No such file or directory` after
merge, and the feature's own goal — making pytest run in a gate — went unmet.

**The only consumer of `task_git_state` in the repo is `cortex_command/overnight/smoke_test.py:219`,
which prints it.** No gate, no report, no morning-report classifier reads it. The evidence was
captured, timestamped, written to disk, and never looked at.

## Role

Give `task_git_state` a consumer, so an untracked file at implement exit produces an observable
consequence rather than a log line nobody reads.

## Integration

The second, separable half is that `merge_feature` already implements the expensive remedy and it
is not armed:

- `cortex_command/pipeline/merge.py:193` — `merge_feature` accepts `test_command` and reverts the
  merge commit on test failure.
- `cortex_command/overnight/runner.py:3259` — passes `test_command=None` into the batch runner;
  `batch_runner.py:32` defaults it to `None` as well.
- `cortex_command/lifecycle_config.py:45` — `test-command` sits in `_LIVE_PROSE_KEYS`, "consumed
  by skill prose (the model reads the value), no Python parser by design". So the
  `lifecycle.config.md` value never reaches `merge_feature`; the `test_command` that flows through
  `outcome_router.py:894/2030/2442` comes from `pipeline/parser.py:65` and CLI flags.

Whether arming that path is in scope is a plan-time decision, not a settled one — `test-command`
being prose-only is a deliberate design choice, and reversing it is a larger change than adding a
reader.

## Edges

- **The `.venv` noise is real and measured, not hypothetical.** The same captured status line
  carries `?? .venv` directly above the real signal, 1:1 in the only sample. A reader that reports
  every `??` entry reproduces that ratio. Scoping to paths referenced by a gate/config surface
  needs shell-string tokenization across `&&` and `;` (the source value is
  `uv run validate_project.py && uv run run_unit_tests.py; uv run run_python_tests.py`), which is
  where the actual design cost sits — not in the `git ls-files` call.
- **Non-goal: recovering the source incident.** Repaired by hand in wild-light `9cde2d0f`.
- **Non-goal: making the SubagentStop tripwire run over a clean tree.** Note that wild-light
  ADR-0045 is `status: proposed`, so this boundary rests on an unratified decision.
- **Do not restate "every gate was green".** The pipeline logged 7 `integration_worktree_missing`
  and 2 `feature_failed`; `db94189c`'s subject lacks the `pipeline/` prefix that
  `merge.py:297` produces, so `merge_feature` never ran on it. The proximate cause is **#465**
  (`$TMPDIR` worktree purge, now `complete`) — #465 is a dependency of this incident, not a sibling.
- **The existing review already worked.** Merge 07:02:39 → repair `9cde2d0f` 07:51:30 is **49
  minutes**, caught by the first Lifecycle Review after landing. Any proposal here is an
  improvement on a 49-minute detection time, not a fix for an undetected class. Price it that way.

## Evidence bar

Deletion bias (`project.md:23`) requires observed failure, not a hypothetical, for new harness
machinery. What is observed: **one** incident where a captured signal had no reader, plus one
thinner precedent (wild-light `b1f04cac`, an unstaged `.uid` sidecar, 3 days earlier; a sweep of
the current corpus finds zero untracked sidecars). The original ticket's generalisation to "a gate
command, a config value pointing at a file, a fixture path, a scene reference" has **zero**
observed instances across those four and should not be carried forward. No incidence data exists
for gaggimate, Team-Builder-Bot, or hall-dental.

Adding a *reader* for an event the runner already writes is close to free and is the version this
ticket should be judged on. Adding a new gate is not, and does not clear the bar on this evidence.

## Touch points

- `cortex_command/overnight/feature_executor.py:726-753` — the sweep that already runs
- `cortex_command/overnight/smoke_test.py:213-219` — the only consumer today
- `cortex_command/pipeline/merge.py:193` — post-merge test-and-revert, unarmed
- `cortex_command/overnight/runner.py:3259` — the hardcoded `test_command=None`
- `cortex_command/lifecycle_config.py:45` — `test-command` as `_LIVE_PROSE_KEYS`
- Source incident: wild-light `overnight-2026-08-07-0252`; wiring `7f8e2d9c`, manual merge
  `db94189c`, repair `9cde2d0f`, and the feature's own `review.md`
