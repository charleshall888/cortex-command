---
schema_version: "1"
uuid: 9c77ddc8-71d1-4c78-8774-55d1eb1ccffa
title: Run the overnight batch child inside the repo and report its failures honestly
status: complete
priority: high
type: bug
created: 2026-07-28
updated: 2026-07-28
tags: ['harness', 'overnight', 'observability']
areas: ['tooling']
---
## Why

Session `overnight-2026-07-28-0256` burned **$7.60 and 14m32s of a 6h budget, produced zero implementation, and reported the cause as two feature failures.** Fixed in this session; the commits are the record. This ticket is kept as the written diagnosis because the failure was expensive and the symptom pointed at the wrong component.

> **Correction.** This ticket originally claimed the *orchestrator agent* stopped after Step 4 without dispatching implementation. That was wrong. `batch_runner.py` is a thin CLI wrapper around `orchestrator.run_batch()` — a Python subprocess, not an agent. The orchestrator agent's job genuinely ends at producing `batch-plan-round-1.md`, and it did that correctly (`subtype: "success"`, 13 turns).

**Root cause — the batch child ran in `/`.** `scheduler/launcher.sh` never chdirs, and says so twice ("cwd is `/` under launchd"). `_spawn_batch_runner` called `Popen` with no `cwd`, so the child inherited it. `pipeline/worktree.py:_repo_root()` shells `git rev-parse --show-toplevel` with `check=True` and no `cwd`, which raises `CalledProcessError(128)` from `/`. That call sits in `run_batch`'s unguarded `create_worktree` loop, so the child died ~167 ms after emitting `BATCH_ASSIGNED`, before dispatching a single feature. Reproduced directly. **Every scheduled overnight run failed this way; run-now worked only because its cwd happened to be the repo.**

**Why it was undiagnosable.** `_spawn_batch_runner` used `stdout=PIPE, stderr=PIPE`, and nothing ever drained them — `_poll_subprocess` only calls `proc.wait()`. The traceback died with the process. This was also a latent deadlock: Python's docs warn `wait()` with `PIPE` hangs once the child fills the buffer.

**Why it blamed the features.** The non-zero exit logged `ORCHESTRATOR_FAILED` (the orchestrator had already succeeded), and `map_results._handle_missing_results` stamped every feature `failed` with the hardcoded `"batch_runner.py did not produce results file"`. The only evidence the features never ran was `started_at: null`, which no surface reads.

**Followups never left the machine.** `_post_loop` pushes the branch and opens the PR *before* `_commit_followup_in_worktree`. Measured: push 02:14:40–42, followup commit `d883ea16` at 02:14:44. PR #26 merged `06ca7d68` alone; the auto-filed tickets were unreachable once the merged branch was deleted.

**Bonus, found while recovering.** `git pull --rebase` refuses on a dirty tree (exit 128) without starting a rebase; `sync_rebase` entered its resolution loop anyway and ran `git rebase --continue` against "fatal: no rebase in progress" ten times before reporting an exhausted conflict budget for a sync that never began.

## What shipped

- `be1df1b5` — batch child spawns with `cwd` + `CORTEX_REPO_ROOT` (fixes the whole class of cwd-dependent resolvers at the boundary, rather than patching `worktree.py` and `merge.py` separately); stdout/stderr to per-round files; new `BATCH_RUNNER_FAILED` event carrying exit code and stderr path; per-feature errors now say `harness fault, feature did not run: …`; followup commit pushed once written.
- `8732f503` — `sync_rebase` detects that no rebase started and surfaces git's error; `_advance_rebase` extracted so the no-conflict path also chooses `--skip`; git's stderr logged instead of discarded.
- `7199d881` — test-isolation fix.

Regression tests pin all of it, verified to fail against the pre-fix code.

## Not done

- The signal-shutdown followup path (`runner.py` callsite ~1090) still does not push. Left alone deliberately: a network call during SIGTERM handling risks stalling teardown, and that path's work is recoverable via `/overnight resume` rather than lost to a branch deletion.
- No guard was added for an orchestrator agent that genuinely under-delivers. That failure mode was hypothesised here, not observed — the front-door evidence bar (`cortex/requirements/project.md`) says it needs its own evidence first.
