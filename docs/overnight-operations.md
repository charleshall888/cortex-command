[← Back to overnight.md](overnight.md)

# Overnight: Operations and Architecture

**For:** operators and contributors debugging overnight. **Assumes:** familiarity with how to run overnight.

> **Jump to:** [Architecture](#architecture) | [Code Layout](#code-layout) | [Tuning](#tuning) | [Observability](#observability) | [Security and Trust Boundaries](#security-and-trust-boundaries) | [Internal APIs](#internal-apis)

This doc applies the **progressive disclosure** model from `claude/reference/claude-skills.md` to human-facing docs rather than to agent skill loading. `docs/overnight.md` stays compact for a reader whose access pattern is "how do I run overnight tonight?" — landing via the README, a peer recommendation, or a getting-started cross-link — and they get Quick-Start plus a one-paragraph pointer here. `docs/overnight-operations.md` is the single source of truth for mechanics, debugging, and recovery for a reader whose access pattern is "something broke at 2am" — landing via a stack trace, a retro back-reference, or a deep cross-link from `pipeline.md` — and they find the complete picture in one file rather than bouncing between two. The split optimizes which doc each reader hits first: new operators hit `overnight.md`; debuggers hit this file. See `CLAUDE.md` under `## Conventions` for the source-of-truth rule that partitions overnight mechanics, pipeline internals, and SDK mechanics across docs.

---

## Architecture

### The Round Loop

The runner loops until one of the stop conditions fires:

```
while rounds < max_rounds AND features pending:
    spawn orchestrator agent (--max-turns 50, no permissions sandbox)
    spawn watchdog (background)
    wait for agent to exit
    count features merged this round
    if stall (0 merges this round, twice): circuit breaker → stop
    if time elapsed ≥ time_limit: stop
    if watchdog detected stall: pause state → stop
    round++
```

Each round spawns a fresh `claude -p` invocation — the orchestrator reads state files each time rather than carrying memory between rounds. The orchestrator's sanctioned I/O surface is `claude/overnight/orchestrator_io.py` (see [orchestrator_io re-export surface](#orchestrator_io-re-export-surface)); at end-of-round it appends a `round_history_notes` entry to `overnight-strategy.json` so the next round has continuity without sharing process memory.

### Circuit Breakers

The runner has three automatic stop conditions:

| Trigger | Condition | Behavior |
|---------|-----------|----------|
| Zero-progress breaker | 0 features merged in 2 consecutive rounds | Stops the session, logs `CIRCUIT_BREAKER` |
| Time limit | Wall-clock elapsed ≥ `--time-limit` | Stops the session, logs `CIRCUIT_BREAKER` |
| Stall watchdog | No event written to events log for 30 minutes | Kills the Claude agent, pauses state, sends notification |

A stopped session enters phase `paused` (not `complete`) if features remain. Use `/overnight resume` to check state and relaunch with `overnight-start`. The numeric thresholds above are current defaults; treat them as pointers to `runner.sh` rather than load-bearing constants — if they diverge, code wins.

### Signal Handling

SIGINT or SIGTERM (e.g. Ctrl-C or `kill`) triggers a graceful shutdown:

1. Transitions state to `paused`.
2. Logs a `CIRCUIT_BREAKER` event with `reason: signal`.
3. Generates a partial morning report.
4. Archives session artifacts to `lifecycle/sessions/{id}/`.
5. Sends a push notification.

Forward-only phase transitions apply — the shutdown path writes `paused` via the same atomic tempfile + `os.replace()` dance used elsewhere, so a concurrent reader sees either the pre-shutdown or post-shutdown state, never a partial record.

### Strategy File (overnight-strategy.json) — mutators and consumers

`overnight-strategy.json` is the cross-round continuity artifact: fields the orchestrator wants this round to know from last round. The on-disk schema is documented under [Strategy File (overnight-strategy.json) schema](#strategy-file-overnight-strategyjson-schema) in Observability — this subsection covers who writes which field and who reads it, without repeating the JSON shape.

**Files**: `claude/overnight/strategy.py` (`OvernightStrategy`, `load_strategy`, `save_strategy`), `claude/overnight/runner.sh` (writes on integration-recovery failure), `claude/overnight/prompts/orchestrator-round.md` (end-of-round writer), `claude/pipeline/batch_runner.py` (reader for conflict-recovery decisions).

**Mutators** (who writes):

- **Orchestrator prompt, end of round.** `orchestrator-round.md`'s end-of-round step appends a `round_history_notes` entry and refreshes `hot_files` and `recovery_log_summary` via `save_strategy()` in `claude/overnight/strategy.py`. `save_strategy()` is atomic (tempfile + `os.replace()`).
- **`runner.sh`, on integration-recovery failure.** When `python3 -m claude.overnight.integration_recovery` exits non-zero, `runner.sh` sets `integration_health="degraded"` in the file and sets `INTEGRATION_DEGRADED=true` in the environment (the warning file is then prepended to the PR body).

**Consumers** (who reads):

- **Orchestrator prompt, round start.** The orchestrator reads the whole file as session context — particularly `recovery_log_summary` and `round_history_notes` for continuity between rounds.
- **`batch_runner.execute_feature()`.** Reads `hot_files` for the trivial-fast-path decision in [Conflict Recovery](#conflict-recovery-trivial-fast-path-and-repair-fallback): a conflicted file that appears in `hot_files` disqualifies the trivial path and forces a repair dispatch.

`load_strategy()` tolerates missing files, invalid JSON, and unexpected shapes by returning a default instance — safe to read at any time, including from external tooling.

### Module Reference

| Module | Role |
|--------|------|
| `runner.sh` | Entry point: orchestrates rounds, owns the overnight loop |
| `state.py` | Core state schema (`OvernightState`, `OvernightFeatureStatus`, `RoundSummary`) + atomic persistence |
| `events.py` | Append-only JSONL event logger; reader utilities for report/resume |
| `backlog.py` | Backlog scanner + weighted scoring for overnight selection |
| `plan.py` | Session plan renderer; writes `overnight-plan.md` |
| `strategy.py` | Cross-round integration health tracking (`OvernightStrategy`) |
| `batch_plan.py` | Per-batch master plan generation; maps pipeline results back to overnight state |
| `batch_runner.py` | Batch execution: dispatches pipeline workers, handles deferrals, merges |
| `brain.py` | Post-retry triage agent (SKIP/DEFER/PAUSE decisions via Claude API) |
| `throttle.py` | Subscription-aware `ConcurrencyManager` with adaptive rate-limit backoff |
| `interrupt.py` | Startup recovery: resets `running` features to `pending` with reason logging |
| `deferral.py` | Question deferral file writer (blocking/non-blocking/informational) |
| `report.py` | Morning report generator (reads state + events + deferrals) |
| `map_results.py` | Maps `batch-{N}-results.json` → `overnight-state.json` + strategy updates |
| `status.py` | Live status display (single-screen snapshot; used by `just overnight-status`) |
| `integration_recovery.py` | Integration branch test-failure recovery; dispatches repair agent |
| `smoke_test.py` | Pre-launch toolchain sanity check |

### Post-Merge Review (review_dispatch)

After a feature merges to the integration branch, `batch_runner.execute_feature()` consults `requires_review(tier, criticality)` in `claude/common.py` — review fires when `tier == "complex"` or `criticality in ("high", "critical")`. Gated features invoke `dispatch_review()` in `claude/pipeline/review_dispatch.py`, which loads `claude/pipeline/prompts/review.md` via `_load_review_prompt()` and runs a review agent against the merged state on the integration branch.

**Files**: `claude/pipeline/review_dispatch.py` (`dispatch_review`, `parse_verdict`, `_write_review_deferral`), `claude/pipeline/prompts/review.md`, `claude/common.py` (`requires_review`), `claude/pipeline/batch_runner.py` (`execute_feature` owns the review/rework loop).

**Inputs**: integration branch HEAD at merge time; feature metadata; prior orchestrator notes at `lifecycle/{feature}/learnings/orchestrator-note.md`.

The verdict is parsed from a ```json``` block inside the review agent's `review.md` artifact — `APPROVED`, `CHANGES_REQUESTED`, or `REJECTED`. The review agent writes only `review.md`; `batch_runner` owns every `events.log` write (`phase_transition`, `review_verdict`, `feature_complete`) so review artifacts and state transitions never interleave.

The rework cycle is single-shot:

- **Cycle 1 `CHANGES_REQUESTED`**: feedback is appended to `lifecycle/{feature}/learnings/orchestrator-note.md`, HEAD SHA is captured as a circuit-breaker baseline, a fix agent is dispatched, the SHA circuit breaker verifies new work landed, and the feature is re-merged with `ci_check=False` (the test gate already passed pre-review). A cycle-2 review then runs.
- **Cycle 2 non-`APPROVED` or any `REJECTED`**: `_write_review_deferral()` emits a blocking `DeferralQuestion` and the feature stops. There is no cycle 3.

Forward-only phase transitions hold throughout: `planning → executing → complete`, or any phase → `paused`. State writes use tempfile + `os.replace()` so a crash mid-review leaves either the pre-merge or post-merge state on disk, never a torn record.

### Per-Task Agent Capabilities (allowed_tools)

Every task-level agent dispatched by `claude/pipeline/dispatch.py` is bound to a fixed tool allowlist at the SDK level. The list is passed as `allowed_tools=_ALLOWED_TOOLS` into `ClaudeAgentOptions` — enforcement is by omission: `Agent`, `Task`, `AskUserQuestion`, `WebFetch`, and `WebSearch` are simply absent, so the subprocess has no capability to invoke them. There is no separate deny list.

```python
_ALLOWED_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]
```

Source of truth: `claude/pipeline/dispatch.py` (`_ALLOWED_TOOLS`). A pytest under `tests/` asserts the documented list above equals `claude.pipeline.dispatch._ALLOWED_TOOLS` as a set, so any drift between code and docs fails CI.

Two corollaries of enforce-by-omission:

- **No peer-agent spawning.** `Agent` and `Task` are withheld so dispatched workers cannot fan out to child agents; the orchestrator owns parallelism and agents never spawn peer agents. `claude/overnight/prompts/repair-agent.md` reinforces this in prose, but the SDK-level bound is the load-bearing constraint.
- **No network I/O from tasks.** `WebFetch` and `WebSearch` are withheld. Anything a task needs from the network must be fetched by the orchestrator and written into the worktree before dispatch.

`dispatch.py` also clears `CLAUDECODE` from the subprocess environment before launching the agent, so the SDK does not trip the nested-session guard when overnight is itself launched from a Claude Code session.

See [Security and Trust Boundaries](#security-and-trust-boundaries) for how `_ALLOWED_TOOLS` relates to `--dangerously-skip-permissions` (they are orthogonal).

### brain.py — post-retry triage (SKIP/DEFER/PAUSE)

`claude/overnight/brain.py` is **not a repair agent**. It does not re-attempt the failed task, re-dispatch a worker, or touch the worktree. By the time `brain.py` runs, retries have already been exhausted upstream — this module is the post-retry *triage* step that decides what happens to a task the pipeline cannot complete on its own. Its decision space is `SKIP / DEFER / PAUSE`, and there is no `RETRY` action by design: a RETRY would re-enter the caller that just gave up, so the omission is load-bearing, not an oversight.

**Files**: `claude/overnight/brain.py` (`request_brain_decision`, `BrainAction`, `_parse_brain_response`, `_default_decision`), `claude/overnight/prompts/batch-brain.md` (triage prompt rendered with `{feature, task_description, retry_count, learnings, spec_excerpt, has_dependents, last_attempt_output}`).

**Inputs**: the exhausted task's feature slug, task description, retry count, accumulated learnings, relevant spec excerpt, a `has_dependents` flag, and the last attempt's output. `request_brain_decision` calls `dispatch_task` directly and is **not** throttled — the caller already holds a concurrency slot, so re-acquiring one here would deadlock.

The three dispositions `brain.py` surfaces:

- **SKIP** — the task is non-blocking and session progress should continue without it. Safe when downstream features do not depend on this one.
- **DEFER** — a human decision is needed before work can proceed. Requires both a `question` and a `severity` in the response; a `DeferralQuestion` is filed to `deferred/*.md` for morning review.
- **PAUSE** — the session itself is too uncertain to continue safely; halt overnight execution and wait for the operator. This is also the `_default_decision()` fallback (confidence 0.3) when `_parse_brain_response()` cannot extract a valid action from the triage agent's output.

`_parse_brain_response()` validates that the returned JSON has `action ∈ {skip, defer, pause}` and a non-empty `reasoning`; DEFER responses additionally require `question` and `severity`. A malformed response never crashes the round — it falls through to the PAUSE default so the operator gets a chance to inspect rather than the session silently skipping work.

### Conflict Recovery (trivial fast-path and repair fallback)

When a feature branch fails to merge cleanly, `batch_runner.execute_feature()` chooses between a trivial fast-path and a full repair dispatch based on the set of conflicted files and the session's `hot_files` list. The policy is declared in the orchestrator prompt at `claude/overnight/prompts/orchestrator-round.md` (the "Conflict Recovery" step) and implemented in `batch_runner.execute_feature()`.

**Files**: `claude/pipeline/batch_runner.py` (`execute_feature`), `claude/pipeline/conflict.py` (`resolve_trivial_conflict`), `claude/pipeline/merge_recovery.py`, `claude/overnight/prompts/repair-agent.md`, `claude/overnight/prompts/orchestrator-round.md` (Conflict Recovery step).

**Inputs**: conflicted file list from the failed merge; `hot_files` read from `overnight-strategy.json`; per-feature `recovery_depth` counter.

The decision:

- **Trivial fast-path** fires iff `len(conflicted_files) <= 3` AND none of the conflicted files appears in `hot_files`. `resolve_trivial_conflict()` in `claude/pipeline/conflict.py` runs a deterministic rebase-and-resolve against the integration branch; no agent is dispatched. This is the common case for a concurrent tiny merge on an unrelated file.
- **Repair fallback** fires otherwise. `dispatch_repair_agent` loads `repair-agent.md` and dispatches at complexity=sonnet; on failure the single Sonnet→Opus escalation described under [Repair caps](#repair-caps) applies. This is the merge-conflict codepath specifically — test-failure repair is a different codepath (`integration_recovery.py`) with a different cap; the two are intentionally not unified.
- **Per-feature budget.** `recovery_depth < 1` gates the repair fallback; a feature that has already consumed one repair attempt this session is deferred on its next conflict rather than looping.

On repair success the feature re-merges and continues; on repair failure the feature is marked failed in the batch results, the integration branch stays at the last clean merge point, and `/morning-review` surfaces it as a blocking item. If the failure path fires on `integration_recovery` (the test-gate sibling), `runner.sh` additionally sets `integration_health="degraded"` in `overnight-strategy.json` so subsequent rounds can consult it in their own conflict-recovery decisions.

### Cycle-breaking for repeated escalations

Workers raise escalations to the Escalation System by appending entries to `lifecycle/escalations.jsonl` — an append-only JSONL log whose writer is `write_escalation()` in `claude/overnight/deferral.py` (re-exported via `claude/overnight/orchestrator_io.py`). Each record carries an `escalation_id` of form `{feature}-{round}-q{N}` and a `type` field — one of `"escalation"` (worker asked), `"resolution"` (orchestrator answered), or `"promoted"` (cycle broken, see below). N is chosen by `_next_escalation_n()`, which counts existing `"escalation"` entries for the same feature+round; a TOCTOU race is acknowledged in code comments and is safe under the per-feature single-coroutine dispatch invariant.

**Files**: `claude/overnight/deferral.py` (`EscalationEntry`, `write_escalation`, `_next_escalation_n`), `claude/overnight/orchestrator_io.py` (re-export), `claude/overnight/prompts/orchestrator-round.md` (Step 0a–0d — the cycle-breaking logic lives in the prompt, not Python).

**Inputs**: `lifecycle/escalations.jsonl`; prior orchestrator feedback at `lifecycle/{feature}/learnings/orchestrator-note.md`.

Cycle-breaking fires when a worker re-asks a question the orchestrator already answered. The orchestrator prompt's Step 0d scans `escalations.jsonl` at round start: if ≥1 `"type": "resolution"` entry exists for the same `feature` and a new worker escalation raises a sufficiently similar question, the orchestrator treats the feature as stuck rather than answering again. The concrete action is:

- Delete `lifecycle/{feature}/learnings/orchestrator-note.md` (the feedback channel clearly did not land — do not accumulate stale guidance).
- Append a `"type": "promoted"` entry to `escalations.jsonl` recording the promotion.
- Call `write_deferral()` to file a blocking deferral for human review at morning.
- Do **not** re-queue the feature for this session.

This keeps a stuck worker from consuming budget round after round on the same question. Because the detector is prompt-implemented, do not quote line numbers from `orchestrator-round.md` — the prompt is edited for clarity routinely; refer to it by filename and step heading only.

### Test Gate and integration_health

The test gate runs in `runner.sh` after `batch_runner.py` has merged all passing features onto the integration branch and before the PR is pushed — it is a branch-level gate, not a per-feature gate. The gate is only armed when `--test-command` is passed; if absent, the runner skips straight to PR creation. Per-feature CI signal is separate (`ci_check` inside `merge_feature()`) and covered under [Post-Merge Review](#post-merge-review-review_dispatch); this subsection covers only the integration-branch gate.

**Files**: `claude/overnight/runner.sh` (the "Integration gate" block around the post-merge PR-prep stage), `claude/overnight/integration_recovery.py`, `claude/overnight/strategy.py` (`integration_health` field).

**Inputs**: `$TEST_COMMAND` (from `--test-command`), the integration worktree path, and the current `overnight-strategy.json` (read to update `integration_health` on failure).

Flow on pass: the gate runs `bash -c "$TEST_COMMAND"` inside the integration worktree, captures stdout/stderr to `$INTEGRATION_TEST_OUTPUT`, and on exit 0 proceeds to PR creation with no state change.

Flow on fail: a non-zero exit invokes `python3 -m claude.overnight.integration_recovery` with the same `--test-command`, the worktree path, and a truncated 20-line head of the test output for the repair agent's context. Recovery dispatch itself obeys the 2-attempt cap documented under [Repair caps](#repair-caps). If recovery succeeds, the runner proceeds to PR creation normally. If recovery fails, three things happen in order: (1) `INTEGRATION_DEGRADED=true` is set in the runner's shell env; (2) `integration_health` is flipped to `"degraded"` in `overnight-strategy.json` via `load_strategy`/`save_strategy`, so subsequent rounds' conflict-recovery decisions can treat the branch with more caution (see [Strategy File mutators](#strategy-file-overnight-strategyjson--mutators-and-consumers)); (3) a warning block containing the first 20 lines of the failing test output is prepended to the PR body so a human reviewer sees it before merging. The PR is still pushed — successful merges are not rolled back by a gate failure.

For tunable surfaces (`--test-command` choice, the unconditional-repair rule, `integration_health` semantics) see [Test Gate and integration_health tuning](#test-gate-and-integration_health-tuning) under Tuning.

### Startup Recovery (interrupt.py)

`claude/overnight/interrupt.py` runs once at session startup to reconcile state that a prior crash or SIGKILL may have left in an inconsistent shape. It is invoked as `python3 -m claude.overnight.interrupt [state_path]` from `runner.sh` before the round loop begins.

**Files**: `claude/overnight/interrupt.py` (`handle_interrupted_features`, `_infer_interrupt_reason`), invoked by `claude/overnight/runner.sh` at session start.

**Inputs**: `lifecycle/overnight-state.json`; per-feature worktree paths and their on-disk state.

Behavior: scan the state file for features whose status is `running`. For each, inspect the worktree to infer why it was stuck (round-end handoff, orchestrator-interrupted mid-dispatch, or crash/SIGKILL), append an `interrupted` event to the per-session events log with the inferred reason, and reset the feature's status to `pending` so the upcoming round can re-dispatch it. `recovery_depth` and feature-level history are preserved — a feature that exhausted its recovery budget before the interruption retains that history and will defer rather than re-enter the repair loop. State writes go through the same atomic tempfile + `os.replace()` pattern used elsewhere.

The reset is conservative: `interrupt.py` never changes features in `complete`, `failed`, or `deferred` states, so an ambiguous `running` row is the only trigger. If the state file is missing or malformed, `interrupt.py` exits cleanly with a logged warning — it cannot create state, only reconcile it.

### Runner Lock (.runner.lock)

`claude/overnight/runner.sh` writes its own PID to `$SESSION_DIR/.runner.lock` (i.e. `lifecycle/sessions/{id}/.runner.lock`) before entering the round loop, and relies on it to serialize runners against the same session.

**Files**: `claude/overnight/runner.sh` (the "Concurrency guard" block that sets `LOCK_FILE`).

**Inputs**: `$SESSION_DIR` derived from the resolved state path.

Behavior: at startup, if `.runner.lock` already exists, `runner.sh` reads the PID and runs `kill -0 $LOCK_PID` to test liveness. A live PID causes an immediate abort with a message pointing at `tmux attach -t overnight-runner`; a dead PID (orphaned after SIGKILL, crash, or reboot) is treated as stale, logged, and overwritten. The file content is just the bare PID — no JSON, no timestamp — so `cat .runner.lock` is the debugging move. The lock is not removed on clean exit; a fresh startup always overwrites whatever PID is there, which means a stale lock never blocks the next session and the check exists only to prevent *two concurrent* runners, not to assert cleanup hygiene.

### Scheduled Launch subsystem

`bin/overnight-schedule` is the delayed-start wrapper that defers invocation of `overnight-start` until a specific wall-clock time, so operators can queue an overnight from the evening for a late-night kickoff without leaving a shell open.

**Files**: `bin/overnight-schedule` (user-facing setup path + internal `__launch` path), `bin/overnight-start` (invoked via `exec` when the delay elapses).

**Inputs**: target time as `HH:MM` or `YYYY-MM-DDTHH:MM`, plus the same positional args `overnight-start` accepts (state path, time limit, max rounds, tier).

Behavior: the setup path validates the target time (rejects past times, caps delay at 7 days, rolls `HH:MM` forward to tomorrow if today has passed), writes `scheduled_start` into the state file for dashboard visibility, and spawns a detached `tmux` session named `overnight-scheduled[-N]` that re-execs itself with a `__launch` argument. Inside `__launch`, the script runs `caffeinate -i sleep $DELAY` to keep the Mac awake through the wait, clears `scheduled_start` from the state file, and `exec`s `overnight-start` with the forwarded args. There is no dedicated log file — the tmux pane is the log; `tmux attach -t overnight-scheduled` is the only way to see what it is doing before the handoff to `overnight-start`.

---

## Code Layout

### claude/pipeline/prompts — per-task dispatched prompts

`claude/pipeline/prompts/` holds prompts that are dispatched into per-feature worktrees by `claude/pipeline/dispatch.py` and `claude/pipeline/review_dispatch.py`. These agents operate on a single feature's code at a time and run under `_ALLOWED_TOOLS`.

**Files**: `claude/pipeline/prompts/implement.md` (implementation agent), `claude/pipeline/prompts/review.md` (post-merge review agent loaded by `_load_review_prompt()`).

**Inputs**: feature metadata and worktree path supplied by the caller; no session-level state.

The naming convention is "per-task, per-feature" — one prompt file per role an orchestrated agent can play inside a worktree.

### claude/overnight/prompts — orchestrator/session-level prompts

`claude/overnight/prompts/` holds prompts loaded by `runner.sh` and overnight subsystems that operate at the session or orchestrator level — not inside a per-feature worktree. These agents reason about the whole session, read session-scoped state files (`overnight-strategy.json`, `escalations.jsonl`), and coordinate work across features.

**Files**: `claude/overnight/prompts/orchestrator-round.md` (the round-loop orchestrator prompt, including the escalations Step 0a–0d cycle-breaking logic), `claude/overnight/prompts/batch-brain.md` (the `brain.py` post-retry triage prompt rendered with `{feature, task_description, retry_count, learnings, spec_excerpt, has_dependents, last_attempt_output}`), `claude/overnight/prompts/repair-agent.md` (conflict-repair and integration-repair agent prose).

**Inputs**: session state loaded by the orchestrator; escalation history; strategy file; feature-level learnings directories.

The two directories are kept separate because their audiences differ: `pipeline/prompts` agents never see session state, and `overnight/prompts` agents never edit a single feature's code directly — they route work through `pipeline/dispatch.py`. Keeping them in sibling trees makes the scope boundary visible from an import path alone.

---

## Tuning

### --tier concurrency (Concurrency Tuning)

The `--tier` CLI flag on `batch_runner.py` selects a throttle profile. Accepted values: `max_5`, `max_100`, `max_200`. Default (flag omitted or unrecognized) is `max_100`.

| Tier | Runners | Workers |
|------|---------|---------|
| `max_5` | 1 | 1 |
| `max_100` | 2 | 2 |
| `max_200` | 3 | 3 |

Defaults live in `claude/overnight/throttle.py` (`load_throttle_config`); the tier value is wired through `BatchConfig.throttle_tier` and consumed by `ConcurrencyManager`. The limit is a hard ceiling — agents cannot raise it at runtime (orchestrator owns parallelism; agents never spawn peer agents).

Adaptive downshift: `report_rate_limit()` prunes a 300-second sliding window; after 3 rate-limit events the effective concurrency drops by 1 (floor of 1). `report_success()` restores the shift after 10 consecutive successes. The escalation ladder itself (haiku → sonnet → opus) does not downgrade.

Tune by matching your API plan's parallelism ceiling to the tier. Picking `max_200` on a plan only capable of `max_5` throughput starves into the adaptive downshift before the first round finishes.

### Test Gate and integration_health tuning

The [Test Gate and integration_health](#test-gate-and-integration_health) subsection under Architecture documents the flow; this subsection calls out the *tunable surfaces*:

- **`--test-command`** (passed to `runner.sh` / `batch_runner.py`). This is the command run after every merge onto the integration branch — a non-zero exit invokes `python3 -m claude.overnight.integration_recovery`. Choosing a slow or flaky command multiplies every round's wall-clock cost; choosing a fast-but-shallow command narrows what the gate catches before repair dispatch.
- **`integration_health` in `overnight-strategy.json`**. `healthy` is the implicit baseline; `degraded` is set by `runner.sh` when `integration_recovery` fails (alongside `INTEGRATION_DEGRADED=true` and a warning file prepended to the PR body). Downstream rounds consult this field in conflict-recovery decisions.
- **Repair dispatch is unconditional** on gate failure — there is no suppression flag. If you need to skip repair, skip the gate (set `--test-command` to a no-op) rather than trying to gate the repair.

### Model selection matrix (tier × criticality → role)

This document owns tier × criticality → role *dispatch*; detailed per-role SDK model configuration lives in [sdk.md](sdk.md) — that file is the source of truth for model IDs, fallback chains, and `ClaudeAgentOptions` plumbing.

| Tier | Criticality | Review required? | Repair role |
|------|-------------|------------------|-------------|
| `simple` | `low`, `medium` | No | Sonnet (first attempt) |
| `simple` | `high`, `critical` | Yes | Sonnet → Opus on escalation |
| `complex` | any | Yes | Sonnet → Opus on escalation |

Review gating is implemented by `requires_review(tier, criticality)` in `claude/common.py`: review runs when `tier == "complex" or criticality in ("high", "critical")`. The escalation ladder is one-directional (haiku → sonnet → opus, no downgrade); see [sdk.md](sdk.md) for the concrete model IDs wired into each role.

### Repair caps

The runner has **two distinct repair caps** with different numbers. They are intentionally *not unified* — the codepaths, artifacts, and recovery semantics differ enough that a single number would hide the divergence.

- **Merge-conflict repair: single Sonnet→Opus escalation.** One attempt at Sonnet, then one escalation to Opus, then give up and defer. Rationale: merge-conflict repair operates on a git-index snapshot; a second Sonnet attempt on the same snapshot is unlikely to succeed where the first failed, so the cap spends its second slot climbing the model ladder rather than retrying at the same tier. Codepath: `claude/pipeline/conflict.py` and `claude/pipeline/merge_recovery.py`.
- **Test-failure repair: max 2 attempts.** Two full repair cycles for the integration test gate. Rationale: test failures often expose a different error on the second attempt (the first fix unblocks the next assertion), so a retry at the same tier has meaningful information gain that a merge-conflict retry does not. Codepath: `claude/overnight/integration_recovery.py`.

Do not describe these as "the repair cap" in prose — collapsing them to one number misleads readers at 2am when observed behavior does not match.

### overnight-strategy.json contents and mutators

The field-by-field writer and reader map is documented under [Strategy File (overnight-strategy.json) — mutators and consumers](#strategy-file-overnight-strategyjson--mutators-and-consumers) in the Architecture section; see [Strategy File (overnight-strategy.json) schema](#strategy-file-overnight-strategyjson-schema) in Observability for the JSON shape. From a tuning perspective, the tunable surfaces are:

- **`hot_files`** — a string list of paths the orchestrator treats as "do not auto-resolve conflicts on." Inflating the list makes the trivial fast-path fire less often (more repair dispatches, more Claude cost); leaving it empty makes every conflict eligible for the trivial path (faster, but higher risk of a stale resolution on a frequently-touched file). The orchestrator prompt populates this from observed round history — manual tuning is rarely needed, but the field is plain JSON and can be edited between sessions.
- **`integration_health`** — `healthy` or `degraded`; consulted by downstream rounds' conflict-recovery decisions. Not typically tuned by hand; `runner.sh` sets `degraded` after an `integration_recovery` failure and the next round treats the integration branch with more caution.
- **`recovery_log_summary`** and **`round_history_notes`** — narrative context threaded from the orchestrator prompt into the next round's context window. Keep them short — the orchestrator prompt budget includes them, so a ballooning `round_history_notes` reduces remaining room for the actual work.

---

## Observability

### State File Locations

Every overnight session persists state as files under `lifecycle/`. The runner resolves a per-session directory (`lifecycle/sessions/{id}/`) and symlinks the canonical top-level paths into it so tools that hard-code `lifecycle/overnight-state.json` keep working mid-session. The table below names the canonical path (what readers use), the on-disk writer, and what the file represents.

| Path | Writer | Role |
|------|--------|------|
| `lifecycle/overnight-state.json` | `claude/overnight/state.py` (`save_state` — atomic tempfile + `os.replace`) | Session state: phase, per-feature status, round counter. Source of truth for "is this session still running." |
| `lifecycle/overnight-events.log` | `claude/overnight/events.py` (`log_event`) | Append-only JSONL event stream at the session level (round boundaries, feature lifecycle, circuit breakers). |
| `lifecycle/sessions/{id}/pipeline-events.log` | `claude/pipeline/events.py` via `batch_runner` | Append-only JSONL of per-task dispatch/merge/test events inside each feature. |
| `lifecycle/sessions/{id}/overnight-strategy.json` | `claude/overnight/strategy.py` (`save_strategy` — atomic tempfile + `os.replace`) | Cross-round strategy: `hot_files`, `integration_health`, `recovery_log_summary`, `round_history_notes`. |
| `lifecycle/escalations.jsonl` | `claude/overnight/deferral.py` (`write_escalation`) | Append-only JSONL of worker escalations, orchestrator resolutions, and cycle-break promotions. |
| `lifecycle/{feature}/events.log` | `claude/pipeline/batch_runner.py` | Per-feature phase-transition journal (`phase_transition`, `review_verdict`, `feature_complete`). Read by `/lifecycle resume` and `/morning-review`. |
| `lifecycle/{feature}/agent-activity.jsonl` | `claude/pipeline/dispatch.py` (`_write_activity_event`) | Per-feature per-turn agent tool-call breadcrumbs (tool names, success/failure, turn cost). |
| `lifecycle/{feature}/learnings/orchestrator-note.md` | orchestrator prompt + `batch_runner` (review rework cycle) | Accumulated orchestrator feedback handed to the next worker dispatch. |
| `lifecycle/morning-report.md` | `claude/overnight/report.py` (`write_report` — atomic tempfile + `os.replace`) | The morning report (see below). Runner emits `morning_report_generate_result` and `morning_report_commit_result` events to `overnight-events.log` around the write + commit so the operator can confirm the file landed on `main`. |
| `lifecycle/.runner.lock` | `runner.sh` | PID lock preventing concurrent overnight sessions. See [Runner Lock](#runner-lock-runnerlock). |
| `deferred/*.md` | `claude/overnight/deferral.py` (`write_deferral`) | Blocking human-decision questions filed during the session. |

State file reads are not lock-protected by design — forward-only phase transitions and atomic replace writes make torn reads impossible. A reader either sees the pre-write state or the post-write state, never a partial record.

### Escalation System (escalations.jsonl)

`lifecycle/escalations.jsonl` is the worker-to-orchestrator side channel. Writer is `write_escalation()` in `claude/overnight/deferral.py` (re-exported from `claude/overnight/orchestrator_io.py`); readers include the orchestrator prompt (Steps 0a–0d) and `_next_escalation_n()` in the same module. Records are one JSON object per line with a `type` discriminator.

**Worker-raised escalation** (`"type": "escalation"`), appended by `write_escalation()`:

```json
{
  "type": "escalation",
  "escalation_id": "{feature}-{round}-q{N}",
  "feature": "my-feature",
  "round": 3,
  "question": "Should the API return 404 or 204 on empty result?",
  "context": "Worker was implementing Task 4 of my-feature and hit an undocumented edge case in the spec.",
  "ts": "2026-04-12T02:17:44Z"
}
```

**Orchestrator resolution** (`"type": "resolution"`), appended inline from `orchestrator-round.md` Step 0d when the orchestrator answers a prior escalation and writes the feedback into `lifecycle/{feature}/learnings/orchestrator-note.md`:

```json
{
  "type": "resolution",
  "escalation_id": "{feature}-{round}-q{N}",
  "feature": "my-feature",
  "round": 3,
  "resolution": "Return 204 — matches the existing convention in endpoints/foo.py.",
  "ts": "2026-04-12T02:18:02Z"
}
```

**Cycle-break promotion** (`"type": "promoted"`), appended when the orchestrator detects a repeat escalation and promotes the question to a blocking deferral — see [Cycle-breaking for repeated escalations](#cycle-breaking-for-repeated-escalations).

```json
{
  "type": "promoted",
  "escalation_id": "{feature}-{round}-q{N}",
  "feature": "my-feature",
  "round": 4,
  "reason": "Worker re-asked after resolution at round 3; promoting to deferral.",
  "ts": "2026-04-12T02:45:11Z"
}
```

`escalation_id` format is `{feature}-{round}-q{N}`. N comes from `_next_escalation_n()`, which counts existing `"escalation"` entries for the same feature+round; the TOCTOU race is acknowledged in code and is safe under the per-feature single-coroutine dispatch invariant.

### Strategy File (overnight-strategy.json) schema

The `OvernightStrategy` dataclass in `claude/overnight/strategy.py` serializes to `lifecycle/sessions/{id}/overnight-strategy.json` via atomic tempfile + `os.replace`. Field semantics and mutators are covered under [overnight-strategy.json contents and mutators](#overnight-strategyjson-contents-and-mutators); the on-disk shape is:

```json
{
  "hot_files": ["src/app.py", "src/router.py"],
  "integration_health": "healthy",
  "recovery_log_summary": "",
  "round_history_notes": [
    "Round 1: merged feature-a clean.",
    "Round 2: feature-b hit a conflict in src/app.py; trivial resolve succeeded."
  ]
}
```

`load_strategy()` tolerates missing files, invalid JSON, and unexpected shapes by returning a default instance — safe to grep or `cat` at any time without crashing the reader.

### Morning Report Generation (report.py)

`claude/overnight/report.py` (`generate_and_write_report`) is invoked by `runner.sh` after the orchestration loop completes. It collects state + events + deferrals, renders the Markdown report, and atomically writes `lifecycle/morning-report.md`.

**Inputs**:

- `lifecycle/overnight-state.json` — phase, per-feature status, round counter (`load_state`).
- `lifecycle/overnight-events.log` — event stream (`read_events`).
- `deferred/*.md` — blocking questions filed during the session.
- Per-feature artifacts under `lifecycle/{feature}/`: `events.log`, `learnings/orchestrator-note.md`, `review.md`, `requirements-drift.md`, recovery log entries.
- Per-session results directory for tool-failure mining (`collect_tool_failures`).

**Assembly**: `generate_report()` concatenates `render_executive_summary`, `render_completed_features`, `render_pending_drift`, `render_deferred_questions`, `render_failed_features`, `render_new_backlog_items`, `render_action_checklist`, `render_run_statistics`, and — when any exist — `render_tool_failures`. Each renderer is a pure function of `ReportData`.

**Output**: `lifecycle/morning-report.md`. `write_report()` uses tempfile + `os.replace()` so the report is never observed half-written. After the write, `runner.sh` emits a `morning_report_generate_result` event (per-session and latest-copy sha256s + byte counts) and then a `morning_report_commit_result` event recording whether the commit landed on `main`. `notify()` then fires `~/.claude/notify.sh` so the operator knows overnight is done.

The morning-report commit is the only runner commit that stays on local `main`; all other artifact commits travel on the integration branch. (Historical reports from 2026-04-07, 2026-04-11, and 2026-04-21 were backfilled retroactively under commits whose subject lines end with `(backfill)`.)

### agent-activity.jsonl

`lifecycle/{feature}/agent-activity.jsonl` is a per-feature append-only breadcrumb trail of a dispatched agent's tool interactions during a single run. Writer is `_write_activity_event()` in `claude/pipeline/dispatch.py`; writes are fire-and-forget and swallow exceptions — activity logging never blocks or interrupts the agent. Each line is one JSON object discriminated by `event`.

**Tool call** (as the agent requests a tool):

```json
{"event": "tool_call", "tool": "Edit", "input_summary": "src/router.py"}
```

**Tool result** (after the tool returns):

```json
{"event": "tool_result", "tool": "Edit", "success": true}
```

**Turn complete** (after the model's response completes):

```json
{"event": "turn_complete", "turn": 12, "cost_usd": 0.0341}
```

`input_summary` is a best-effort one-line preview from `_extract_input_summary()` — typically a path for file tools or a truncated command for `Bash`. Grep this log when you need to reconstruct what a worker actually did in a feature, as opposed to what the orchestrator thought it did.

### Log Disambiguation

Overnight writes several JSONL logs at different scopes. Pick the one that matches your symptom:

| Log file | Grep this when |
|----------|----------------|
| `lifecycle/overnight-events.log` | Investigating round boundaries, session-level circuit breakers, or feature-start/feature-complete markers — anything that needs a chronological view across all features in one session. |
| `lifecycle/sessions/{id}/pipeline-events.log` | Investigating dispatch/merge/test outcomes for individual tasks within a feature (`dispatch_start`, `dispatch_complete`, `merge_start`, `merge_success`, `task_idempotency_skip`). |
| `lifecycle/{feature}/events.log` | Investigating phase transitions, review verdicts, and completion for one feature — what `/lifecycle resume` and `/morning-review` read. |
| `lifecycle/{feature}/agent-activity.jsonl` | Investigating what tools an agent actually invoked inside a dispatch and whether they succeeded — the "what did the worker really do" log. |
| `lifecycle/escalations.jsonl` | Investigating which features blocked on questions, how the orchestrator answered, and which were cycle-break-promoted to deferrals. |

All five are append-only JSONL and safe to `tail -f` live. The first four are written by four different modules — session events by `claude/overnight/events.py`, pipeline events by `claude/pipeline/events.py`, per-feature lifecycle by `claude/pipeline/batch_runner.py`, and agent activity by `claude/pipeline/dispatch.py` — so ownership drift is contained. A symptom that spans "did the orchestrator try to merge?" plus "what did the merge agent do?" requires grepping both `pipeline-events.log` and the feature's `agent-activity.jsonl`.

### Dashboard Polling and dashboard state

The dashboard is a pull-based observer — it never shares memory with the runner, it just re-reads state files on fixed intervals.

**Files**: `claude/dashboard/poller.py` (`_poll_state_files`, `_poll_jsonl_events`, `_poll_slow`, `_poll_alerts`), `claude/dashboard/data.py` (parse helpers).

**Inputs**: `lifecycle/sessions/{id}/overnight-state.json`, `lifecycle/sessions/latest-pipeline/pipeline-state.json`, `lifecycle/sessions/{id}/overnight-events.log` (incremental JSONL tail via byte offset), per-feature `lifecycle/{feature}/events.log` and `agent-activity.jsonl`, `backlog/`.

Polling cadence: state files every 2s, `overnight-events.log` every 1s (offset-tracked so already-seen events are never re-emitted), backlog counts every 30s, alert evaluation every 5s. The TOCTOU concern (what if the writer updates a file mid-read?) is resolved by convention at the write side: the overnight runner writes all state JSON via tempfile + `os.replace()`, which is atomic on the same filesystem, so the poller's `json.loads(path.read_text())` either sees the old bytes or the new bytes — never a torn mix. Append-only JSONL logs (`overnight-events.log`, `agent-activity.jsonl`) are tailed by byte offset, which means a write partway through a line will be re-read on the next tick once the line is complete. The practical consequence: a momentarily-stale dashboard is normal, an internally-inconsistent dashboard view is not.

### Session Hooks (SessionStart, SessionEnd, notification hooks)

Claude Code fires lifecycle hooks at session boundaries and on specific tool/notification events; `claude/settings.json` wires these to shell scripts in `hooks/` (symlinked to `~/.claude/hooks/`).

**Files**: `claude/settings.json` (`hooks` key), `hooks/cortex-scan-lifecycle.sh` (SessionStart — injects `LIFECYCLE_SESSION_ID` + lifecycle state into context), `hooks/cortex-cleanup-session.sh` (SessionEnd — removes `.session` marker unless reason is `clear`), `hooks/cortex-notify.sh` (Notification matcher `permission_prompt` and Stop events — local macOS toast), plus `cortex-validate-commit.sh` (PreToolUse Bash), `cortex-tool-failure-tracker.sh` (PostToolUse Bash), and `cortex-skill-edit-advisor.sh` (PostToolUse Write|Edit).

**Inputs**: JSON payload on stdin from Claude Code (`session_id`, `cwd`, `reason`, `tool_name`, etc.); environment (`CLAUDE_ENV_FILE`).

Debugging note: hooks exit 0 unconditionally and **have no log mechanism** — per `requirements/remote-access.md`, notification and session-management failures are silent by design so that hook bugs never block the Claude session. This is acceptable for personal use but means "I didn't get a notification" has no breadcrumb trail; diagnose by running the hook script manually with a synthetic JSON payload on stdin, not by searching logs. The same silence applies to SessionStart/SessionEnd hooks: if `cortex-scan-lifecycle.sh` fails to inject `LIFECYCLE_SESSION_ID`, the session starts anyway and downstream tooling silently loses session identity.

---

## Security and Trust Boundaries

Overnight runs autonomously against a live working tree on a developer workstation. The trust boundaries below are enumerated once here; safety notes are not scattered elsewhere in this doc.

- **`--dangerously-skip-permissions`.** Overnight launches `claude` subprocesses with this flag, which disables the permission-prompt layer entirely. Threat model: any tool the subprocess is allowed to invoke runs without confirmation against the local filesystem and shell — sandbox configuration (the filesystem/network allowlist applied to the subprocess) becomes the critical security surface for autonomous execution.
- **`_ALLOWED_TOOLS` — SDK-level tool bound.** Task agents dispatched by `claude/pipeline/dispatch.py` are bound to `_ALLOWED_TOOLS` at the SDK layer, orthogonal to `--dangerously-skip-permissions`. Threat model: a compromised or confused task agent cannot reach `WebFetch`, `WebSearch`, `Agent`, `Task`, or `AskUserQuestion` — they are not loaded, not merely denied — so it cannot spawn peer agents or exfiltrate via the web even under skipped permissions.
- **Dashboard binds `0.0.0.0`, unauthenticated, by design.** The dashboard is read-only and listens on all interfaces without auth. Threat model: anyone on the same layer-2 broadcast domain can read session state, feature names, and log excerpts; do not expose to the public internet and do not treat "local network" as equivalent to "home network" — hotel Wi-Fi, coworking Wi-Fi, and shared office VLANs are all "local" to the dashboard and are not trusted peers.
- **macOS keychain prompt as a session-blocking failure mode.** If authentication resolution (see [Internal APIs — Auth Resolution](#auth-resolution-apikeyhelper-and-env-var-fallback-order)) falls through to keychain-backed credentials, the first subprocess spawn may trigger a macOS keychain-access dialog. Threat model: the "runs while you sleep" premise breaks silently — the prompt blocks subprocess spawn until acknowledged, the round stalls, and no notification fires because the failure is pre-notification. Resolve by setting `ANTHROPIC_API_KEY` or configuring `apiKeyHelper` before the session starts.
- **"Local network" ≠ "home network".** This is a corollary of the dashboard boundary but is called out as its own item because the framing trap bites at 2am. Threat model: a reader who conflates the two will expose session state to whatever shared network they happen to be on; the dashboard's design assumes a trusted L2 peer set, which is only true on a network the operator controls end-to-end.

---

## Internal APIs

### orchestrator_io re-export surface

`claude/overnight/orchestrator_io.py` is the sanctioned import boundary for orchestrator-callable I/O primitives. The module itself holds no logic — it re-exports a small, deliberately curated set of functions from `claude.overnight.state` and `claude.overnight.deferral` so the orchestrator prompt's Step 0 file-I/O calls can be imported from one module rather than reaching into internals. See `__all__` in `claude/overnight/orchestrator_io.py` for the sanctioned surface; do not enumerate it here because the list is expected to grow and a doc-side enumeration would rot on the next addition.

**Files**: `claude/overnight/orchestrator_io.py` (source of truth — `__all__`), consumed by `claude/overnight/prompts/orchestrator-round.md`.

Convention: any new orchestrator-callable I/O primitive is added here rather than imported directly from `claude.overnight.state` or `claude.overnight.deferral` by the orchestrator. This keeps the orchestrator's blast radius for internal refactors bounded to one file.

### lifecycle.config.md consumers and absence behavior

`lifecycle.config.md` is a per-project config file (template at `skills/lifecycle/assets/lifecycle.config.md`). There is no centralized Python loader — each consumer reads it directly — so the contract is "template is source of truth for fields; each consumer decides its own absence behavior." Fields include `type`, `test-command`, `demo-command` / `demo-commands`, `default-tier`, `default-criticality`, `skip-specify`, `skip-review`, and `commit-artifacts`.

**Files**: `skills/lifecycle/assets/lifecycle.config.md` (template — source of truth for the field list), plus the consumers in `skills/lifecycle/`, `skills/critical-review/`, and `skills/morning-review/`.

Absence behavior per consumer (what happens when the project has no `lifecycle.config.md`):

- **morning-review**: skips Section 2a (the demo-commands walkthrough) and continues the rest of the review.
- **lifecycle complete**: skips the test step with a note that no `test-command` was configured.
- **critical-review**: omits the `## Project Context` section of the generated review.
- **lifecycle specify/plan**: reads optional defaults (`default-tier`, `default-criticality`, `skip-specify`, `skip-review`) and falls back to skill-level defaults when absent.

Because field drift across consumers is possible, the template is the one place to check before assuming a field exists; do not enumerate fields in more than one doc.

### Auth Resolution (apiKeyHelper and env-var fallback order)

Auth resolution is owned by the shared `claude/overnight/auth.py` module. Both the overnight entry point (`runner.sh`) and the daytime entry point (`daytime_pipeline.py`) delegate to this one module so they share one priority order, one sanitization rule, and one event schema — divergence between the two paths would be a silent correctness hazard.

The module resolves Anthropic authentication in a strict 4-step fallback order before any subprocess is spawned. Each step short-circuits on success.

1. **`ANTHROPIC_API_KEY` already in the environment** — use it as-is and stop. This is the common CI/dev path (vector: `env_preexisting`).
2. **`apiKeyHelper` configured in `~/.claude/settings.json` or `~/.claude/settings.local.json`** — execute the helper command and export its stdout as `ANTHROPIC_API_KEY`. This is the recommended path for machines that keep the key out of shell profiles (vector: `api_key_helper`).
3. **No helper AND no `CLAUDE_CODE_OAUTH_TOKEN`** — try `~/.claude/personal-oauth-token`; if non-empty, export its contents as `CLAUDE_CODE_OAUTH_TOKEN`. This covers OAuth-style authentication for `claude -p` / SDK usage (vector: `oauth_file`).
4. **Fall through to keychain-backed auth** — print a warning and proceed; the first subprocess spawn may block on a macOS keychain-access prompt (see [Security and Trust Boundaries](#security-and-trust-boundaries)). Vector: `none`.

**Files**: `claude/overnight/auth.py` (shared resolver — source of truth), `claude/overnight/runner.sh` (shell delegation), `claude/overnight/daytime_pipeline.py` (in-process delegation inside `run_daytime`), `claude/pipeline/dispatch.py` (re-exports both `ANTHROPIC_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` into SDK subprocesses).

#### Shell entry point: three-exit-code contract

`runner.sh` invokes the helper pre-venv via `python3 -m claude.overnight.auth --shell` and branches on the exit code:

- **exit code 0** — vector resolved. Helper prints `export VAR=VALUE` to stdout; `runner.sh` `eval`s it. Warnings (if any) went to stderr.
- **exit code 1** — no vector resolved. Helper printed a warning to stderr. `runner.sh` continues; the first SDK spawn may prompt for keychain access.
- **exit code 2** — helper-internal failure (malformed `~/.claude/settings.json`, stdlib import regression, other deterministic defect inside the resolver itself). `runner.sh` logs `Error: auth helper internal failure` and exits immediately with status 2. User-environment issues (helper binary missing, helper timeout, helper non-zero exit) are NOT exit code 2 — those fall through to the next resolution step.

#### Daytime entry point: deferred-event-emit pattern

`daytime_pipeline.py::run_daytime` calls `ensure_sdk_auth` in-process rather than shelling out, because it runs inside an existing Python process and needs to classify a no-vector result as a `startup_failure` through the same try/except/finally path that writes `daytime-result.json`. The wiring runs in two phases because the event log path is not known at the moment auth resolves:

- **Phase A** (first statement inside `run_daytime`'s try-block, before any other startup work): call `ensure_sdk_auth(event_log_path=None)`. This writes the credential into `os.environ` and returns the `auth_bootstrap` event dict without emitting it anywhere — no pipeline-events.log exists yet because the feature-scoped directory may not even be populated. A `vector == "none"` result is converted to a `RuntimeError` with `_terminated_via = "startup_failure"` so the outer `finally` writes `daytime-result.json` with the right classification.
- **Phase B** (immediately after `build_config` returns and `pipeline_events_path` is known): append the buffered event dict to `pipeline_events_path` using `json.dumps(event) + "\n"`. This byte-matches `claude.pipeline.state.log_event` output, which is what the R7 byte-equivalence test locks in.

Both phases use the same event payload (built once inside `ensure_sdk_auth` with `ts` first), so there is only ever one `auth_bootstrap` line per daytime run regardless of which phase writes it.

#### Propagation

`dispatch.py` forwards both variables into SDK subprocesses. Note the asymmetry — `CLAUDE_CODE_OAUTH_TOKEN` works only for `claude -p` and the SDK; standalone tools (including most scripts invoked from within a task) still need `ANTHROPIC_API_KEY`. If a worker subprocess reports auth errors but the orchestrator is fine, inspect which variable is reaching it.
