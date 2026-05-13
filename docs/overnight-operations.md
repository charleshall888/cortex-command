[← Back to overnight.md](overnight.md)

# Overnight: Operations and Architecture

**For:** operators and contributors debugging overnight. **Assumes:** familiarity with how to run overnight.

> **Jump to:** [Architecture](#architecture) | [Code Layout](#code-layout) | [Tuning](#tuning) | [Observability](#observability) | [Security and Trust Boundaries](#security-and-trust-boundaries) | [Internal APIs](#internal-apis)

> **Driving overnight from a Claude Code conversation?** See [`docs/mcp-server.md`](mcp-server.md) for the `cortex mcp-server` control-plane interface — registration, the five MCP tools (`overnight_start_run`, `overnight_status`, `overnight_logs`, `overnight_cancel`, `overnight_list_sessions`), cursor pagination, and recovery procedures.

This doc applies the **progressive disclosure** model from Anthropic's [Agent Skills overview](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) to human-facing docs rather than to agent skill loading. Agent Skills load in three levels — Level 1 (metadata: name + description always in context), Level 2 (instructions: SKILL.md body loaded on trigger), Level 3 (resources/code: referenced files read on demand) — so the model only pays the context cost for what it actually needs at each step. `docs/overnight.md` stays compact for a reader whose access pattern is "how do I run overnight tonight?" — landing via the README, a peer recommendation, or a getting-started cross-link — and they get Quick-Start plus a one-paragraph pointer here. `docs/overnight-operations.md` is the single source of truth for mechanics, debugging, and recovery for a reader whose access pattern is "something broke at 2am" — landing via a stack trace or a deep cross-link from `pipeline.md` — and they find the complete picture in one file rather than bouncing between two. The split optimizes which doc each reader hits first: new operators hit `overnight.md`; debuggers hit this file. See `CLAUDE.md` under `## Conventions` for the source-of-truth rule that partitions overnight mechanics, pipeline internals, and SDK mechanics across docs.

---

## Architecture

### The Round Loop

The runner loops until one of the stop conditions fires:

```
while rounds < max_rounds AND features pending:
    spawn orchestrator agent (--max-turns 50, per-spawn sandbox via --settings tempfile)
    spawn watchdog (background)
    wait for agent to exit
    count features merged this round
    if stall (0 merges this round, twice): circuit breaker → stop
    if time elapsed ≥ time_limit: stop
    if watchdog detected stall: pause state → stop
    round++
```

Each round spawns a fresh `claude -p` invocation — the orchestrator reads state files each time rather than carrying memory between rounds. The orchestrator's sanctioned I/O surface is `cortex_command/overnight/orchestrator_io.py` (see [orchestrator_io re-export surface](#orchestrator_io-re-export-surface)); at end-of-round it appends a `round_history_notes` entry to `overnight-strategy.json` so the next round has continuity without sharing process memory.

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
4. Archives session artifacts to `cortex/lifecycle/sessions/{id}/`.
5. Sends a push notification.

Forward-only phase transitions apply — the shutdown path writes `paused` via the same atomic tempfile + `os.replace()` dance used elsewhere, so a concurrent reader sees either the pre-shutdown or post-shutdown state, never a partial record.

### Strategy File (overnight-strategy.json) — mutators and consumers

`overnight-strategy.json` is the cross-round continuity artifact: fields the orchestrator wants this round to know from last round. The on-disk schema is documented under [Strategy File (overnight-strategy.json) schema](#strategy-file-overnight-strategyjson-schema) in Observability — this subsection covers who writes which field and who reads it, without repeating the JSON shape.

**Files**: `cortex_command/overnight/strategy.py` (`OvernightStrategy`, `load_strategy`, `save_strategy`), `cortex_command/overnight/runner.sh` (writes on integration-recovery failure), `cortex_command/overnight/prompts/orchestrator-round.md` (end-of-round writer), `cortex_command/pipeline/batch_runner.py` (reader for conflict-recovery decisions).

**Mutators** (who writes):

- **Orchestrator prompt, end of round.** `orchestrator-round.md`'s end-of-round step appends a `round_history_notes` entry and refreshes `hot_files` and `recovery_log_summary` via `save_strategy()` in `cortex_command/overnight/strategy.py`. `save_strategy()` is atomic (tempfile + `os.replace()`).
- **`runner.sh`, on integration-recovery failure.** When `cortex-integration-recovery` exits non-zero, `runner.sh` sets `integration_health="degraded"` in the file and sets `INTEGRATION_DEGRADED=true` in the environment (the warning file is then prepended to the PR body).

**Consumers** (who reads):

- **Orchestrator prompt, round start.** Round-startup state assembly is mediated by `aggregate_round_context` (see [aggregate_round_context — round-startup state aggregator](#aggregate_round_context--round-startup-state-aggregator)), which reads `overnight-strategy.json` (alongside `overnight-state.json`, `escalations.jsonl`, and `session-plan.md`) and returns a single dict. The orchestrator accesses `recovery_log_summary` and `round_history_notes` via the `strategy` key of that dict rather than reading the file directly.
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
| `throttle.py` | Subscription-aware ConcurrencyManager enforcing tier-bound concurrency cap |
| `interrupt.py` | Startup recovery: resets `running` features to `pending` with reason logging |
| `deferral.py` | Question deferral file writer (blocking/non-blocking/informational) |
| `report.py` | Morning report generator (reads state + events + deferrals) |
| `map_results.py` | Maps `batch-{N}-results.json` → `overnight-state.json` + strategy updates |
| `status.py` | Live status display (single-screen snapshot; used by `just overnight-status`) |
| `integration_recovery.py` | Integration branch test-failure recovery; dispatches repair agent |
| `smoke_test.py` | Pre-launch toolchain sanity check |

### Post-Merge Review (review_dispatch)

After a feature merges to the integration branch, `batch_runner.execute_feature()` consults `requires_review(tier, criticality)` in `cortex_command/common.py` — review fires when `tier == "complex"` or `criticality in ("high", "critical")`. Gated features invoke `dispatch_review()` in `cortex_command/pipeline/review_dispatch.py`, which loads `cortex_command/pipeline/prompts/review.md` via `_load_review_prompt()` and runs a review agent against the merged state on the integration branch.

**Files**: `cortex_command/pipeline/review_dispatch.py` (`dispatch_review`, `parse_verdict`, `_write_review_deferral`), `cortex_command/pipeline/prompts/review.md`, `cortex_command/common.py` (`requires_review`), `cortex_command/pipeline/batch_runner.py` (`execute_feature` owns the review/rework loop).

**Inputs**: integration branch HEAD at merge time; feature metadata; prior orchestrator notes at `cortex/lifecycle/{feature}/learnings/orchestrator-note.md`.

The verdict is parsed from a ```json``` block inside the review agent's `review.md` artifact — `APPROVED`, `CHANGES_REQUESTED`, or `REJECTED`. The review agent writes only `review.md`; `batch_runner` owns every `events.log` write (`phase_transition`, `review_verdict`, `feature_complete`) so review artifacts and state transitions never interleave.

The rework cycle is single-shot:

- **Cycle 1 `CHANGES_REQUESTED`**: feedback is appended to `cortex/lifecycle/{feature}/learnings/orchestrator-note.md`, HEAD SHA is captured as a circuit-breaker baseline, a fix agent is dispatched, the SHA circuit breaker verifies new work landed, and the feature is re-merged with `ci_check=False` (the test gate already passed pre-review). A cycle-2 review then runs.
- **Cycle 2 non-`APPROVED` or any `REJECTED`**: `_write_review_deferral()` emits a blocking `DeferralQuestion` and the feature stops. There is no cycle 3.

Forward-only phase transitions hold throughout: `planning → executing → complete`, or any phase → `paused`. State writes use tempfile + `os.replace()` so a crash mid-review leaves either the pre-merge or post-merge state on disk, never a torn record.

### Per-Task Agent Capabilities (allowed_tools)

Every task-level agent dispatched by `cortex_command/pipeline/dispatch.py` is bound to a fixed tool allowlist at the SDK level. The list is passed as `allowed_tools=_ALLOWED_TOOLS` into `ClaudeAgentOptions` — enforcement is by omission: `Agent`, `Task`, `AskUserQuestion`, `WebFetch`, and `WebSearch` are simply absent, so the subprocess has no capability to invoke them. There is no separate deny list.

```python
_ALLOWED_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]
```

Source of truth: `cortex_command/pipeline/dispatch.py` (`_ALLOWED_TOOLS`). A pytest under `tests/` asserts the documented list above equals `claude.pipeline.dispatch._ALLOWED_TOOLS` as a set, so any drift between code and docs fails CI.

Two corollaries of enforce-by-omission:

- **No peer-agent spawning.** `Agent` and `Task` are withheld so dispatched workers cannot fan out to child agents; the orchestrator owns parallelism and agents never spawn peer agents. `cortex_command/overnight/prompts/repair-agent.md` reinforces this in prose, but the SDK-level bound is the load-bearing constraint.
- **No network I/O from tasks.** `WebFetch` and `WebSearch` are withheld. Anything a task needs from the network must be fetched by the orchestrator and written into the worktree before dispatch.

`dispatch.py` also clears `CLAUDECODE` from the subprocess environment before launching the agent, so the SDK does not trip the nested-session guard when overnight is itself launched from a Claude Code session.

See [Security and Trust Boundaries](#security-and-trust-boundaries) for how `_ALLOWED_TOOLS` relates to `--dangerously-skip-permissions` (they are orthogonal).

### brain.py — post-retry triage (SKIP/DEFER/PAUSE)

`cortex_command/overnight/brain.py` is **not a repair agent**. It does not re-attempt the failed task, re-dispatch a worker, or touch the worktree. By the time `brain.py` runs, retries have already been exhausted upstream — this module is the post-retry *triage* step that decides what happens to a task the pipeline cannot complete on its own. Its decision space is `SKIP / DEFER / PAUSE`, and there is no `RETRY` action by design: a RETRY would re-enter the caller that just gave up, so the omission is load-bearing, not an oversight.

**Files**: `cortex_command/overnight/brain.py` (`request_brain_decision`, `BrainAction`, `_parse_brain_response`, `_default_decision`), `cortex_command/overnight/prompts/batch-brain.md` (triage prompt rendered with `{feature, task_description, retry_count, learnings, spec_excerpt, has_dependents, last_attempt_output}`).

**Inputs**: the exhausted task's feature slug, task description, retry count, accumulated learnings, relevant spec excerpt, a `has_dependents` flag, and the last attempt's output. `request_brain_decision` calls `dispatch_task` directly and is **not** throttled — the caller already holds a concurrency slot, so re-acquiring one here would deadlock.

The three dispositions `brain.py` surfaces:

- **SKIP** — the task is non-blocking and session progress should continue without it. Safe when downstream features do not depend on this one.
- **DEFER** — a human decision is needed before work can proceed. Requires both a `question` and a `severity` in the response; a `DeferralQuestion` is filed to `deferred/*.md` for morning review.
- **PAUSE** — the session itself is too uncertain to continue safely; halt overnight execution and wait for the operator. This is also the `_default_decision()` fallback (confidence 0.3) when `_parse_brain_response()` cannot extract a valid action from the triage agent's output.

`_parse_brain_response()` validates that the returned JSON has `action ∈ {skip, defer, pause}` and a non-empty `reasoning`; DEFER responses additionally require `question` and `severity`. A malformed response never crashes the round — it falls through to the PAUSE default so the operator gets a chance to inspect rather than the session silently skipping work.

### Conflict Recovery (trivial fast-path and repair fallback)

When a feature branch fails to merge cleanly, `batch_runner.execute_feature()` chooses between a trivial fast-path and a full repair dispatch based on the set of conflicted files and the session's `hot_files` list. The policy is declared in the orchestrator prompt at `cortex_command/overnight/prompts/orchestrator-round.md` (the "Conflict Recovery" step) and implemented in `batch_runner.execute_feature()`.

**Files**: `cortex_command/pipeline/batch_runner.py` (`execute_feature`), `cortex_command/pipeline/conflict.py` (`resolve_trivial_conflict`), `cortex_command/pipeline/merge_recovery.py`, `cortex_command/overnight/prompts/repair-agent.md`, `cortex_command/overnight/prompts/orchestrator-round.md` (Conflict Recovery step).

**Inputs**: conflicted file list from the failed merge; `hot_files` read from `overnight-strategy.json`; per-feature `recovery_depth` counter.

The decision:

- **Trivial fast-path** fires iff `len(conflicted_files) <= 3` AND none of the conflicted files appears in `hot_files`. `resolve_trivial_conflict()` in `cortex_command/pipeline/conflict.py` runs a deterministic rebase-and-resolve against the integration branch; no agent is dispatched. This is the common case for a concurrent tiny merge on an unrelated file.
- **Repair fallback** fires otherwise. `dispatch_repair_agent` loads `repair-agent.md` and dispatches at complexity=sonnet; on failure the single Sonnet→Opus escalation described under [Repair caps](#repair-caps) applies. This is the merge-conflict codepath specifically — test-failure repair is a different codepath (`integration_recovery.py`) with a different cap; the two are intentionally not unified.
- **Per-feature budget.** `recovery_depth < 1` gates the repair fallback; a feature that has already consumed one repair attempt this session is deferred on its next conflict rather than looping.

On repair success the feature re-merges and continues; on repair failure the feature is marked failed in the batch results, the integration branch stays at the last clean merge point, and `/morning-review` surfaces it as a blocking item. If the failure path fires on `integration_recovery` (the test-gate sibling), `runner.sh` additionally sets `integration_health="degraded"` in `overnight-strategy.json` so subsequent rounds can consult it in their own conflict-recovery decisions.

### Cycle-breaking for repeated escalations

Workers raise escalations to the Escalation System by appending entries to `cortex/lifecycle/sessions/{session_id}/escalations.jsonl` — an append-only JSONL log whose writer is `write_escalation()` in `cortex_command/overnight/deferral.py` (re-exported via `cortex_command/overnight/orchestrator_io.py`). Each record carries an `escalation_id` of form `{feature}-{round}-q{N}` and a `type` field — one of `"escalation"` (worker asked), `"resolution"` (orchestrator answered), or `"promoted"` (cycle broken, see below). N is chosen by `_next_escalation_n()`, which counts existing `"escalation"` entries for the same feature+round; a TOCTOU race is acknowledged in code comments and is safe under the per-feature single-coroutine dispatch invariant.

**Files**: `cortex_command/overnight/deferral.py` (`EscalationEntry`, `write_escalation`, `_next_escalation_n`), `cortex_command/overnight/orchestrator_io.py` (re-export), `cortex_command/overnight/prompts/orchestrator-round.md` (Step 0a–0d — the cycle-breaking logic lives in the prompt, not Python).

**Inputs**: `cortex/lifecycle/sessions/{session_id}/escalations.jsonl`; prior orchestrator feedback at `cortex/lifecycle/{feature}/learnings/orchestrator-note.md`.

Cycle-breaking fires when a worker re-asks a question the orchestrator already answered. The orchestrator prompt's Step 0d scans `cortex/lifecycle/sessions/{session_id}/escalations.jsonl` at round start: if ≥1 `"type": "resolution"` entry exists for the same `feature` and a new worker escalation raises a sufficiently similar question, the orchestrator treats the feature as stuck rather than answering again. The concrete action is:

- Delete `cortex/lifecycle/{feature}/learnings/orchestrator-note.md` (the feedback channel clearly did not land — do not accumulate stale guidance).
- Append a `"type": "promoted"` entry to `cortex/lifecycle/sessions/{session_id}/escalations.jsonl` recording the promotion.
- Call `write_deferral()` to file a blocking deferral for human review at morning.
- Do **not** re-queue the feature for this session.

This keeps a stuck worker from consuming budget round after round on the same question. Because the detector is prompt-implemented, do not quote line numbers from `orchestrator-round.md` — the prompt is edited for clarity routinely; refer to it by filename and step heading only.

### Test Gate and integration_health

The test gate runs in `runner.sh` after `batch_runner.py` has merged all passing features onto the integration branch and before the PR is pushed — it is a branch-level gate, not a per-feature gate. The gate is only armed when `--test-command` is passed; if absent, the runner skips straight to PR creation. Per-feature CI signal is separate (`ci_check` inside `merge_feature()`) and covered under [Post-Merge Review](#post-merge-review-review_dispatch); this subsection covers only the integration-branch gate.

**Files**: `cortex_command/overnight/runner.sh` (the "Integration gate" block around the post-merge PR-prep stage), `cortex_command/overnight/integration_recovery.py`, `cortex_command/overnight/strategy.py` (`integration_health` field).

**Inputs**: `$TEST_COMMAND` (from `--test-command`), the integration worktree path, and the current `overnight-strategy.json` (read to update `integration_health` on failure).

Flow on pass: the gate runs `bash -c "$TEST_COMMAND"` inside the integration worktree, captures stdout/stderr to `$INTEGRATION_TEST_OUTPUT`, and on exit 0 proceeds to PR creation with no state change.

Flow on fail: a non-zero exit invokes `cortex-integration-recovery` with the same `--test-command`, the worktree path, and a truncated 20-line head of the test output for the repair agent's context. Recovery dispatch itself obeys the 2-attempt cap documented under [Repair caps](#repair-caps). If recovery succeeds, the runner proceeds to PR creation normally. If recovery fails, three things happen in order: (1) `INTEGRATION_DEGRADED=true` is set in the runner's shell env; (2) `integration_health` is flipped to `"degraded"` in `overnight-strategy.json` via `load_strategy`/`save_strategy`, so subsequent rounds' conflict-recovery decisions can treat the branch with more caution (see [Strategy File mutators](#strategy-file-overnight-strategyjson--mutators-and-consumers)); (3) a warning block containing the first 20 lines of the failing test output is prepended to the PR body so a human reviewer sees it before merging. The PR is still pushed — successful merges are not rolled back by a gate failure.

For tunable surfaces (`--test-command` choice, the unconditional-repair rule, `integration_health` semantics) see [Test Gate and integration_health tuning](#test-gate-and-integration_health-tuning) under Tuning.

### Startup Recovery (interrupt.py)

`cortex_command/overnight/interrupt.py` runs once at session startup to reconcile state that a prior crash or SIGKILL may have left in an inconsistent shape. It is invoked as `cortex-interrupt [state_path]` from `runner.sh` before the round loop begins.

**Files**: `cortex_command/overnight/interrupt.py` (`handle_interrupted_features`, `_infer_interrupt_reason`), invoked by `cortex_command/overnight/runner.sh` at session start.

**Inputs**: `cortex/lifecycle/overnight-state.json`; per-feature worktree paths and their on-disk state.

Behavior: scan the state file for features whose status is `running`. For each, inspect the worktree to infer why it was stuck (round-end handoff, orchestrator-interrupted mid-dispatch, or crash/SIGKILL), append an `interrupted` event to the per-session events log with the inferred reason, and reset the feature's status to `pending` so the upcoming round can re-dispatch it. `recovery_depth` and feature-level history are preserved — a feature that exhausted its recovery budget before the interruption retains that history and will defer rather than re-enter the repair loop. State writes go through the same atomic tempfile + `os.replace()` pattern used elsewhere.

The reset is conservative: `interrupt.py` never changes features in `complete`, `failed`, or `deferred` states, so an ambiguous `running` row is the only trigger. If the state file is missing or malformed, `interrupt.py` exits cleanly with a logged warning — it cannot create state, only reconcile it.

### Runner concurrency guard (runner.pid + .runner.pid.takeover.lock)

The legacy `$SESSION_DIR/.runner.lock` PID file written by the retired `runner.sh` no longer exists — `runner.sh` was retired in favor of the `cortex overnight {start|status|cancel|logs}` Python CLI per `cortex/requirements/pipeline.md:28`. The runner-concurrency guard is now the per-session `runner.pid` JSON artifact written by `cortex_command/overnight/ipc.py` plus a sibling `flock`-based lockfile that serializes the read-verify-claim critical section.

**Files**: `cortex_command/overnight/ipc.py` (`_acquire_takeover_lock`, `_check_concurrent_start`, `write_runner_pid`, `verify_runner_pid`, `handle_cancel`).

**Inputs**: `session_dir` (`cortex/lifecycle/sessions/{id}/`).

`runner.pid` carries the magic header, schema version, session id, OS pid, and `start_time` that `verify_runner_pid` cross-checks against `psutil.Process.create_time()` before any signal is sent.

`{session_dir}/.runner.pid.takeover.lock` is a sibling lockfile whose sole purpose is to serialize the read-verify-claim critical section across `_check_concurrent_start`, `write_runner_pid`, and the non-force path of `handle_cancel`. The file is `O_CREAT | O_RDWR`'d at mode `0o600` and held under `fcntl.flock(LOCK_EX | LOCK_NB)` with a 5-second polling budget; only the kernel `flock` state is load-bearing, the file content is unused.

Discipline obligations on every future production code site (the static gate at Task 11 enforces these):

- The lockfile is **never written** to by any production module other than `ipc.py:_acquire_takeover_lock`. Production code never appends, truncates, or otherwise modifies its bytes.
- The lockfile is **never unlinked** by production code. `clear_runner_pid` removes `runner.pid` but leaves the takeover lockfile in place; the file persists for the lifetime of the session directory.
- The lockfile is **never durable_fsync**'d (nor `os.fsync`'d, `F_FULLFSYNC`'d, or otherwise flushed for durability). It carries no content worth persisting — kernel `flock` state is in-memory coordination, not durable file content.
- The lockfile must **never be matched by a `*.lock` glob** in any auto-cleanup, archival, or worktree-teardown sweep outside `ipc.py`. The audit at `cortex_command/overnight/daytime_pipeline.py:152` shows that today's `*.lock` rglob targets per-feature `worktree_path` rather than `session_dir`, so the two paths do not currently overlap; future glob callers must keep that invariant or explicitly exclude `.runner.pid.takeover.lock`.

The file persists indefinitely under current archival policy: this project does not auto-archive `cortex/lifecycle/sessions/`, so directories (and their lockfiles) accumulate until manually cleaned. After a reboot the kernel `flock` state is gone but the 0-byte file remains; the next runner reopens it on a fresh inode-with-no-locks and acquires immediately. This is benign for correctness and is the documented backwards-compat / rollback path.

### Scheduled Launch (LaunchAgent-based scheduler)

`cortex overnight schedule <target>` schedules a single overnight run at a future time without requiring tmux or a persistent shell session. Under the hood it delegates to `MacOSLaunchAgentBackend.schedule()`, which renders a plist into `$TMPDIR/cortex-overnight-launch/`, writes a paired bash launcher alongside it, and calls `launchctl bootstrap gui/$(id -u)` to register the job with launchd. At fire time launchd executes the launcher, which detaches `cortex overnight start --launchd` into its own process group. No tmux session is created or required; the runner writes its own `runner.pid` artifact and operates identically to a manually-launched session.

**Usage**:

```sh
# Schedule for a specific time (ISO-8601 or plain HH:MM on today's date)
cortex overnight schedule 23:30

# List pending scheduled runs
cortex overnight cancel --list

# Cancel a pending scheduled run by session_id
cortex overnight cancel <session_id>
```

**Operational caveats**:

- **Machine must be powered on and awake at fire time.** macOS lid-close sleep suspends launchd job firing. A laptop closed before the scheduled time will not fire until the machine wakes — by which point the scheduled time has passed and the job will not retry. Keep the machine powered on and not sleeping (display sleep is fine; system sleep is not).
- **Locked screen is fine.** A locked screen does not block launchd execution; scheduled runs fire normally when the screen is locked.
- **Reboot drops pending schedules.** launchd's bootstrap namespace is rebuilt on each boot from persistent plist sources in `/Library/LaunchAgents/` and `~/Library/LaunchAgents/`; cortex registers into the per-session `gui/$(id -u)` namespace using plists in `$TMPDIR`, which is not persisted across reboots. After a reboot, re-schedule any pending runs with `cortex overnight schedule <target>`.
- **SSH and headless contexts are not supported.** The LaunchAgent backend targets the logged-in GUI session (`gui/$(id -u)`). Running `cortex overnight schedule` over SSH or in a headless CI context where no GUI session exists will fail at bootstrap time.

**TCC / Full Disk Access requirement**: the cortex binary needs Full Disk Access on macOS to read and write `cortex/lifecycle/` paths during overnight execution. Grant access to the binary path printed by `which cortex` in **System Settings → Privacy & Security → Full Disk Access**. TCC authorization is not checked at schedule time — a missing grant surfaces only at fire time as a fail marker in the morning report, not as an error when you run `cortex overnight schedule`.

**Cancel and list**:

```sh
cortex overnight cancel --list    # show pending LaunchAgent jobs and their fire times (also shows active runners)
cortex overnight cancel <session_id>  # unbootstrap and remove the pending job by session_id
```

---

## Code Layout

### cortex_command/pipeline/prompts — per-task dispatched prompts

`cortex_command/pipeline/prompts/` holds prompts that are dispatched into per-feature worktrees by `cortex_command/pipeline/dispatch.py` and `cortex_command/pipeline/review_dispatch.py`. These agents operate on a single feature's code at a time and run under `_ALLOWED_TOOLS`.

**Files**: `cortex_command/pipeline/prompts/implement.md` (implementation agent), `cortex_command/pipeline/prompts/review.md` (post-merge review agent loaded by `_load_review_prompt()`).

**Inputs**: feature metadata and worktree path supplied by the caller; no session-level state.

The naming convention is "per-task, per-feature" — one prompt file per role an orchestrated agent can play inside a worktree.

### cortex_command/overnight/prompts — orchestrator/session-level prompts

`cortex_command/overnight/prompts/` holds prompts loaded by `runner.sh` and overnight subsystems that operate at the session or orchestrator level — not inside a per-feature worktree. These agents reason about the whole session, read session-scoped state files (`overnight-strategy.json`, `sessions/{session_id}/escalations.jsonl`), and coordinate work across features.

**Files**: `cortex_command/overnight/prompts/orchestrator-round.md` (the round-loop orchestrator prompt, including the escalations Step 0a–0d cycle-breaking logic), `cortex_command/overnight/prompts/batch-brain.md` (the `brain.py` post-retry triage prompt rendered with `{feature, task_description, retry_count, learnings, spec_excerpt, has_dependents, last_attempt_output}`), `cortex_command/overnight/prompts/repair-agent.md` (conflict-repair and integration-repair agent prose).

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

Defaults live in `cortex_command/overnight/throttle.py` (`load_throttle_config`); the tier value is wired through `BatchConfig.throttle_tier` and consumed by `ConcurrencyManager`. The limit is a hard ceiling — agents cannot raise it at runtime (orchestrator owns parallelism; agents never spawn peer agents).

Rate-limit pauses are routed through the pipeline api_rate_limit → pause_session path; no in-process shrinkage.

Tune by matching your API plan's parallelism ceiling to the tier. Picking `max_200` on a plan only capable of `max_5` throughput surfaces transient 429s as `api_rate_limit` events that pause the session before the first round finishes.

### Test Gate and integration_health tuning

The [Test Gate and integration_health](#test-gate-and-integration_health) subsection under Architecture documents the flow; this subsection calls out the *tunable surfaces*:

- **`--test-command`** (passed to `runner.sh` / `batch_runner.py`). This is the command run after every merge onto the integration branch — a non-zero exit invokes `cortex-integration-recovery`. Choosing a slow or flaky command multiplies every round's wall-clock cost; choosing a fast-but-shallow command narrows what the gate catches before repair dispatch.
- **`integration_health` in `overnight-strategy.json`**. `healthy` is the implicit baseline; `degraded` is set by `runner.sh` when `integration_recovery` fails (alongside `INTEGRATION_DEGRADED=true` and a warning file prepended to the PR body). Downstream rounds consult this field in conflict-recovery decisions.
- **Repair dispatch is unconditional** on gate failure — there is no suppression flag. If you need to skip repair, skip the gate (set `--test-command` to a no-op) rather than trying to gate the repair.

### Model selection matrix (tier × criticality → role)

This document owns tier × criticality → role *dispatch*; detailed per-role SDK model configuration lives in [sdk.md](internals/sdk.md) — that file is the source of truth for model IDs, fallback chains, and `ClaudeAgentOptions` plumbing.

| Tier | Criticality | Review required? | Repair role |
|------|-------------|------------------|-------------|
| `simple` | `low`, `medium` | No | Sonnet (first attempt) |
| `simple` | `high`, `critical` | Yes | Sonnet → Opus on escalation |
| `complex` | any | Yes | Sonnet → Opus on escalation |

Review gating is implemented by `requires_review(tier, criticality)` in `cortex_command/common.py`: review runs when `tier == "complex" or criticality in ("high", "critical")`. The escalation ladder is one-directional (haiku → sonnet → opus, no downgrade); see [sdk.md](internals/sdk.md) for the concrete model IDs wired into each role.

### Repair caps

The runner has **two distinct repair caps** with different numbers. They are intentionally *not unified* — the codepaths, artifacts, and recovery semantics differ enough that a single number would hide the divergence.

- **Merge-conflict repair: single Sonnet→Opus escalation.** One attempt at Sonnet, then one escalation to Opus, then give up and defer. Rationale: merge-conflict repair operates on a git-index snapshot; a second Sonnet attempt on the same snapshot is unlikely to succeed where the first failed, so the cap spends its second slot climbing the model ladder rather than retrying at the same tier. Codepath: `cortex_command/pipeline/conflict.py` and `cortex_command/pipeline/merge_recovery.py`.
- **Test-failure repair: max 2 attempts.** Two full repair cycles for the integration test gate. Rationale: test failures often expose a different error on the second attempt (the first fix unblocks the next assertion), so a retry at the same tier has meaningful information gain that a merge-conflict retry does not. Codepath: `cortex_command/overnight/integration_recovery.py`.

Do not describe these as "the repair cap" in prose — collapsing them to one number misleads readers at 2am when observed behavior does not match.

### Effort policy rationale and rollback monitoring

This subsection covers *why* the effort matrix flipped Sonnet baseline to `high` and lifted Opus complex+high/critical to `xhigh`, *what framing* bounds the cost-regression risk, and *how* an operator detects regression and reverts. The matrix mechanics (the 12 cells, the `review-fix` / `integration-recovery` overrides, the runtime guard) live in [sdk.md](internals/sdk.md) — do not duplicate the table here.

**Anthropic guidance.** Per Anthropic's Claude 4.7 migration guide, `xhigh` is "the best setting for most coding and agentic use cases," and `high` is recommended as the minimum for intelligence-sensitive workloads. Sonnet 4.6 carries an elevated baseline expectation that the prior `medium` setting did not meet. The flip aligns the dispatch policy with that recommendation across the matrix.

**#089 closure rationale.** Backlog ticket #089 previously parked the `xhigh` adoption decision pending a stronger empirical signal. It was closed because the available data — n=1 + a single synthetic task — could not carry the decision weight needed to overturn vendor guidance. The community estimate (~1.5× tokens for ~5–6% quality boost on agentic coding) is the pre-flip prior we accepted in lieu of a controlled local benchmark. The post-flip rollback monitoring procedure below is the empirical check that runs continuously now, replacing the one-shot benchmark that #089 was waiting on.

**Adaptive-thinking framing.** Per Anthropic's effort docs, `effort` is a behavioral signal that caps the *maximum reasoning depth* the model may use — it is not a strict token budget. The model adapts thinking down for simpler tasks: a simple task running under `xhigh` may consume little more than under `high`, while a complex task may meaningfully exceed it. So the cost regression from the flip is bounded by *task complexity*, not by the effort setting alone. This is why the `metrics.json` rollback check below buckets by `(model, tier, skill, effort)` — a per-effort regression at the same complexity is the signal worth investigating; an aggregate cost rise that tracks complexity mix is not.

**Rollback monitoring procedure.** `metrics.py` now buckets dispatch aggregates by `(model, tier, skill, effort)` (see Task 6 of the implementation plan). The post-flip cost watch is a per-bucket comparison against the pre-flip baseline. Query the per-effort cost mean from `metrics.json` like so:

```sh
# Per-effort cost mean for opus on complex/high dispatches under xhigh:
jq '.model_tier_dispatch_aggregates["opus,complex,xhigh"].cost_usd_mean' \
  cortex/lifecycle/sessions/<session_id>/metrics.json

# Pre-flip baseline (same skill/tier under high) for direct comparison:
jq '.model_tier_dispatch_aggregates["opus,complex,high"].cost_usd_mean' \
  cortex/lifecycle/sessions/<previous_session_id>/metrics.json

# Quick sweep across all post-flip buckets:
jq '.model_tier_dispatch_aggregates | to_entries | map({key, mean: .value.cost_usd_mean})' \
  cortex/lifecycle/sessions/<session_id>/metrics.json
```

Bucket key shape after Task 6 is `"<model>,<tier>,<effort>"` (e.g. `"opus,complex,xhigh"`, `"sonnet,simple,high"`); skill-specific aggregates use the analogous `skill_tier_dispatch_aggregates` slice with skill in the key. The exact aggregate field names are owned by `cortex_command/pipeline/metrics.py` — if the path above does not resolve in a given `metrics.json`, dump the top-level keys with `jq 'keys' metrics.json` and follow the structure from there.

**Threshold that triggers human investigation: > 2× per-bucket mean cost over 2–3 overnight rounds.** A single round can spike on outliers (one truncated dispatch, one unusually deep reasoning chain); two-to-three consecutive rounds at >2× baseline mean for the same `(model, tier, skill, effort)` bucket is the signal that the flip is paying more than the quality boost is worth on this workload.

**Rollback path.** Revert the matrix flip — the SDK upgrade can stay in place. Concretely: revert the commits that changed cell values in `_EFFORT_MATRIX` and the skill-override gate (the Task 2/3/4 commits in this implementation plan). The SDK pin in `pyproject.toml`, the `stop_reason` plumbing on `dispatch_complete` / `dispatch_truncation` events, and the per-effort `metrics.py` bucketing can all stay — they are observability infrastructure that has value independent of the effort policy and is what enabled the rollback decision in the first place.

### overnight-strategy.json contents and mutators

The field-by-field writer and reader map is documented under [Strategy File (overnight-strategy.json) — mutators and consumers](#strategy-file-overnight-strategyjson--mutators-and-consumers) in the Architecture section; see [Strategy File (overnight-strategy.json) schema](#strategy-file-overnight-strategyjson-schema) in Observability for the JSON shape. From a tuning perspective, the tunable surfaces are:

- **`hot_files`** — a string list of paths the orchestrator treats as "do not auto-resolve conflicts on." Inflating the list makes the trivial fast-path fire less often (more repair dispatches, more Claude cost); leaving it empty makes every conflict eligible for the trivial path (faster, but higher risk of a stale resolution on a frequently-touched file). The orchestrator prompt populates this from observed round history — manual tuning is rarely needed, but the field is plain JSON and can be edited between sessions.
- **`integration_health`** — `healthy` or `degraded`; consulted by downstream rounds' conflict-recovery decisions. Not typically tuned by hand; `runner.sh` sets `degraded` after an `integration_recovery` failure and the next round treats the integration branch with more caution.
- **`recovery_log_summary`** and **`round_history_notes`** — narrative context threaded from the orchestrator prompt into the next round's context window. These fields are surfaced to the orchestrator via the `strategy` key returned by `aggregate_round_context` (see [aggregate_round_context — round-startup state aggregator](#aggregate_round_context--round-startup-state-aggregator)) rather than via a direct file read. Keep them short — the orchestrator prompt budget includes them, so a ballooning `round_history_notes` reduces remaining room for the actual work.

---

## Observability

### State File Locations

Every overnight session persists state as files under `cortex/lifecycle/`. The runner resolves a per-session directory (`cortex/lifecycle/sessions/{id}/`) and symlinks the canonical top-level paths into it so tools that hard-code `cortex/lifecycle/overnight-state.json` keep working mid-session. The table below names the canonical path (what readers use), the on-disk writer, and what the file represents.

| Path | Writer | Role |
|------|--------|------|
| `cortex/lifecycle/overnight-state.json` | `cortex_command/overnight/state.py` (`save_state` — atomic tempfile + `os.replace`) | Session state: phase, per-feature status, round counter. Source of truth for "is this session still running." |
| `cortex/lifecycle/overnight-events.log` | `cortex_command/overnight/events.py` (`log_event`) | Append-only JSONL event stream at the session level (round boundaries, feature lifecycle, circuit breakers). |
| `cortex/lifecycle/sessions/{id}/pipeline-events.log` | `cortex_command/pipeline/events.py` via `batch_runner` | Append-only JSONL of per-task dispatch/merge/test events inside each feature. |
| `cortex/lifecycle/sessions/{id}/overnight-strategy.json` | `cortex_command/overnight/strategy.py` (`save_strategy` — atomic tempfile + `os.replace`) | Cross-round strategy: `hot_files`, `integration_health`, `recovery_log_summary`, `round_history_notes`. |
| `cortex/lifecycle/sessions/{session_id}/escalations.jsonl` | `cortex_command/overnight/deferral.py` (`write_escalation`) | Append-only JSONL of worker escalations, orchestrator resolutions, and cycle-break promotions. |
| `cortex/lifecycle/{feature}/events.log` | `cortex_command/pipeline/batch_runner.py` | Per-feature phase-transition journal (`phase_transition`, `review_verdict`, `feature_complete`). Read by `/cortex-core:lifecycle resume` and `/morning-review`. |
| `cortex/lifecycle/{feature}/agent-activity.jsonl` | `cortex_command/pipeline/dispatch.py` (`_write_activity_event`) | Per-feature per-turn agent tool-call breadcrumbs (tool names, success/failure, turn cost). |
| `cortex/lifecycle/{feature}/learnings/orchestrator-note.md` | orchestrator prompt + `batch_runner` (review rework cycle) | Accumulated orchestrator feedback handed to the next worker dispatch. |
| `cortex/lifecycle/morning-report.md` | `cortex_command/overnight/report.py` (`write_report` — atomic tempfile + `os.replace`) | The morning report (see below). Runner emits `morning_report_generate_result` and `morning_report_commit_result` events to `overnight-events.log` around the write + commit so the operator can confirm the file landed on `main`. |
| `cortex/lifecycle/.runner.lock` | `runner.sh` | PID lock preventing concurrent overnight sessions. See [Runner Lock](#runner-lock-runnerlock). |
| `deferred/*.md` | `cortex_command/overnight/deferral.py` (`write_deferral`) | Blocking human-decision questions filed during the session. |

State file reads are not lock-protected by design — forward-only phase transitions and atomic replace writes make torn reads impossible. A reader either sees the pre-write state or the post-write state, never a partial record.

The allowlist of event names emitted across the three `events.log` surfaces above, together with their documented consumers and the pre-commit gate that enforces producer registration, lives in `bin/.events-registry.md` — see [`docs/internals/events-registry.md`](internals/events-registry.md) for the schema, scope split, and `--staged`/`--audit` modes.

### Escalation System (escalations.jsonl)

`cortex/lifecycle/sessions/{session_id}/escalations.jsonl` is the worker-to-orchestrator side channel. Writer is `write_escalation()` in `cortex_command/overnight/deferral.py` (re-exported from `cortex_command/overnight/orchestrator_io.py`); readers include the orchestrator prompt (Steps 0a–0d) and `_next_escalation_n()` in the same module. Records are one JSON object per line with a `type` discriminator.

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

**Orchestrator resolution** (`"type": "resolution"`), appended inline from `orchestrator-round.md` Step 0d when the orchestrator answers a prior escalation and writes the feedback into `cortex/lifecycle/{feature}/learnings/orchestrator-note.md`:

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

The `OvernightStrategy` dataclass in `cortex_command/overnight/strategy.py` serializes to `cortex/lifecycle/sessions/{id}/overnight-strategy.json` via atomic tempfile + `os.replace`. Field semantics and mutators are covered under [overnight-strategy.json contents and mutators](#overnight-strategyjson-contents-and-mutators); the on-disk shape is:

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

`cortex_command/overnight/report.py` (`generate_and_write_report`) is invoked by `runner.sh` after the orchestration loop completes. It collects state + events + deferrals, renders the Markdown report, and atomically writes `cortex/lifecycle/morning-report.md`.

**Inputs**:

- `cortex/lifecycle/overnight-state.json` — phase, per-feature status, round counter (`load_state`).
- `cortex/lifecycle/overnight-events.log` — event stream (`read_events`).
- `deferred/*.md` — blocking questions filed during the session.
- Per-feature artifacts under `cortex/lifecycle/{feature}/`: `events.log`, `learnings/orchestrator-note.md`, `review.md`, `requirements-drift.md`, recovery log entries.
- Per-session results directory for tool-failure mining (`collect_tool_failures`).

**Assembly**: `generate_report()` concatenates `render_executive_summary`, `render_completed_features`, `render_pending_drift`, `render_deferred_questions`, `render_failed_features`, `render_new_backlog_items`, `render_action_checklist`, `render_run_statistics`, and — when any exist — `render_tool_failures`. Each renderer is a pure function of `ReportData`.

**Output**: `cortex/lifecycle/morning-report.md`. `write_report()` uses tempfile + `os.replace()` so the report is never observed half-written. After the write, `runner.sh` emits a `morning_report_generate_result` event (per-session and latest-copy sha256s + byte counts) and then a `morning_report_commit_result` event recording whether the commit landed on `main`. `notify()` then fires the user's desktop-notifier hook (user/machine-config responsibility, not shipped by this repo) so the operator knows overnight is done.

The morning-report commit is the only runner commit that stays on local `main`; all other artifact commits travel on the integration branch. (Historical reports from 2026-04-07, 2026-04-11, and 2026-04-21 were backfilled retroactively under commits whose subject lines end with `(backfill)`.)

### Sandbox-Violation Telemetry

`render_sandbox_denials` (in `cortex_command/overnight/report.py`) emits the morning report's `## Sandbox Denials` section by classifying Bash-routed `Operation not permitted` failures at render time. There is no separate sandbox-violation hook — classification reuses two existing signal sources:

- **Tool-failure tracker** (`hooks/cortex-tool-failure-tracker.sh`, PostToolUse Bash) writes each failed Bash invocation's `command` and truncated `stderr` to `cortex/lifecycle/sessions/<id>/tool-failures/bash.log` as YAML literal block scalars.
- **Per-spawn sidecar deny-lists** at `cortex/lifecycle/sessions/<id>/sandbox-deny-lists/<spawn-id>.json`, written by both overnight spawn sites (`cortex_command/overnight/runner.py` for the orchestrator and `cortex_command/pipeline/dispatch.py` for per-feature dispatches) immediately after each spawn's `--settings` deny-list is constructed. Files are never overwritten — each spawn writes a uniquely-keyed file (e.g. `orchestrator-1.json`, `feature-foo-1.json`) and the aggregator unions them.

`collect_sandbox_denials(session_id)` reads both sources, filters the bash log to entries whose `stderr` contains `Operation not permitted`, and applies a 4-layer classifier to each entry's command:

1. **Shell-redirection layer** — scans the command for `>file`, `>>file`, `tee file`, `echo … > file`, etc., and extracts the redirect target.
2. **Plumbing-tool mapping layer** — if the leading word (after an optional `cd <dir> && …` prefix) is in `PLUMBING_TOOLS` (`git`, `gh`, `npm`, `pnpm`, `yarn`, `cargo`, `hg`, `jj`) and the subcommand is in the known-target mapping (e.g. `git commit` → `<repo>/.git/refs/heads/<HEAD>`, `<repo>/.git/HEAD`, `<repo>/.git/packed-refs`, `<repo>/.git/index`), generates the candidate write targets relative to the inferred repo root.
3. **Plumbing-tool fallback layer** — leading word is in `PLUMBING_TOOLS` but the subcommand is unmapped: classify as `plumbing_eperm`.
4. **Unclassified fallthrough** — none of the above: classify as `unclassified_eperm`.

Layer-1/Layer-2 candidate targets are then matched against the union of all sidecar `deny_paths` and bucketed by path pattern. Categories:

- `home_repo_refs`, `home_repo_head`, `home_repo_packed_refs` — denials against the home cortex repo's `.git/` tree.
- `cross_repo_refs`, `cross_repo_head`, `cross_repo_packed_refs` — denials against an integration worktree's `.git/` tree.
- `other_deny_path` — Layer-1/Layer-2 target matched a sidecar path not in the git-ref enumeration above.
- `plumbing_eperm` — Layer 3: a `PLUMBING_TOOLS` command (likely sandbox, but the subcommand wasn't in the mapping so the precise target is unknown).
- `unclassified_eperm` — Layer 4: leading command not in `PLUMBING_TOOLS`. Likely non-sandbox EPERM (chmod, ACL, EROFS, gpg against `~/.gnupg/`, cargo link-time, etc.) — disclosed as such in the report's prose paragraph.

**Bash-only scope caveat.** Sandbox enforcement covers Bash-tool subprocess writes only. Write/Edit/MCP escape paths are not observed by this telemetry — see #163's V1 threat-model boundary above. Telemetry on MCP writers is deferred to epic #162's child #164.

**Within-Bash plumbing caveat.** Within Bash scope, `git`/`gh`/`npm`-class plumbing denials are classified by command-target inference, which is precise only when the subcommand appears in the known mapping. Subcommand variants outside the mapping (e.g. `git config --global …`, `git rev-parse … | xargs git update-ref`) fall through to the `plumbing_eperm` bucket — still useful as a flag, but the specific target is not attributed.

**Manual smoke recipe.** This path cannot be exercised in automated CI because it requires a sandboxed `claude -p` invocation. To smoke-test by hand: (1) create a temp git repo and stage it as the home repo for an overnight session; (2) construct a per-spawn deny-list that includes `<repo>/.git/refs/heads/main`; (3) drive a sandboxed `claude -p` invocation whose prompt instructs the orchestrator's Bash tool to run `cd $REPO_ROOT && git commit --allow-empty -m 'sandbox test'`; (4) let the round complete and trigger morning-report generation; (5) confirm `cortex/lifecycle/morning-report.md` contains a `## Sandbox Denials` section with a non-zero `Home-repo refs` line (the `home_repo_refs` category). If the count appears under `plumbing_eperm` instead, the sidecar deny-list path did not match the inferred target — re-check the deny-list paths and the inferred home-repo root in `cortex/lifecycle/overnight-state.json`.

### agent-activity.jsonl

`cortex/lifecycle/{feature}/agent-activity.jsonl` is a per-feature append-only breadcrumb trail of a dispatched agent's tool interactions during a single run. Writer is `_write_activity_event()` in `cortex_command/pipeline/dispatch.py`; writes are fire-and-forget and swallow exceptions — activity logging never blocks or interrupts the agent. Each line is one JSON object discriminated by `event`.

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
| `cortex/lifecycle/overnight-events.log` | Investigating round boundaries, session-level circuit breakers, or feature-start/feature-complete markers — anything that needs a chronological view across all features in one session. |
| `cortex/lifecycle/sessions/{id}/pipeline-events.log` | Investigating dispatch/merge/test outcomes for individual tasks within a feature (`dispatch_start`, `dispatch_complete`, `merge_start`, `merge_success`, `task_idempotency_skip`). |
| `cortex/lifecycle/{feature}/events.log` | Investigating phase transitions, review verdicts, and completion for one feature — what `/cortex-core:lifecycle resume` and `/morning-review` read. |
| `cortex/lifecycle/{feature}/agent-activity.jsonl` | Investigating what tools an agent actually invoked inside a dispatch and whether they succeeded — the "what did the worker really do" log. |
| `cortex/lifecycle/sessions/{session_id}/escalations.jsonl` | Investigating which features blocked on questions, how the orchestrator answered, and which were cycle-break-promoted to deferrals. |

All five are append-only JSONL and safe to `tail -f` live. The first four are written by four different modules — session events by `cortex_command/overnight/events.py`, pipeline events by `cortex_command/pipeline/events.py`, per-feature lifecycle by `cortex_command/pipeline/batch_runner.py`, and agent activity by `cortex_command/pipeline/dispatch.py` — so ownership drift is contained. A symptom that spans "did the orchestrator try to merge?" plus "what did the merge agent do?" requires grepping both `pipeline-events.log` and the feature's `agent-activity.jsonl`.

### Dashboard Polling and dashboard state

The dashboard is a pull-based observer — it never shares memory with the runner, it just re-reads state files on fixed intervals.

**Files**: `cortex_command/dashboard/poller.py` (`_poll_state_files`, `_poll_jsonl_events`, `_poll_slow`, `_poll_alerts`), `cortex_command/dashboard/data.py` (parse helpers).

**Inputs**: `cortex/lifecycle/sessions/{id}/overnight-state.json`, `cortex/lifecycle/sessions/latest-pipeline/pipeline-state.json`, `cortex/lifecycle/sessions/{id}/overnight-events.log` (incremental JSONL tail via byte offset), per-feature `cortex/lifecycle/{feature}/events.log` and `agent-activity.jsonl`, `cortex/backlog/`.

Polling cadence: state files every 2s, `overnight-events.log` every 1s (offset-tracked so already-seen events are never re-emitted), backlog counts every 30s, alert evaluation every 5s. The TOCTOU concern (what if the writer updates a file mid-read?) is resolved by convention at the write side: the overnight runner writes all state JSON via tempfile + `os.replace()`, which is atomic on the same filesystem, so the poller's `json.loads(path.read_text())` either sees the old bytes or the new bytes — never a torn mix. Append-only JSONL logs (`overnight-events.log`, `agent-activity.jsonl`) are tailed by byte offset, which means a write partway through a line will be re-read on the next tick once the line is complete. The practical consequence: a momentarily-stale dashboard is normal, an internally-inconsistent dashboard view is not.

### Session Hooks (SessionStart, SessionEnd, notification hooks)

Claude Code fires lifecycle hooks at session boundaries and on specific tool/notification events; plugin hook manifests wire these to shell scripts in `hooks/`.

**Files**: plugin hook manifests (hook registrations), `hooks/cortex-scan-lifecycle.sh` (SessionStart — injects `LIFECYCLE_SESSION_ID` + lifecycle state into context), `hooks/cortex-cleanup-session.sh` (SessionEnd — removes `.session` marker unless reason is `clear`), a user-supplied desktop-notifier hook (Notification matcher `permission_prompt` and Stop events — local macOS toast; user/machine-config responsibility), plus `cortex-validate-commit.sh` (PreToolUse Bash), `cortex-tool-failure-tracker.sh` (PostToolUse Bash), and `cortex-skill-edit-advisor.sh` (PostToolUse Write|Edit).

**Inputs**: JSON payload on stdin from Claude Code (`session_id`, `cwd`, `reason`, `tool_name`, etc.); environment (`CLAUDE_ENV_FILE`).

Debugging note: hooks exit 0 unconditionally and **have no log mechanism** — per `cortex/requirements/remote-access.md`, notification and session-management failures are silent by design so that hook bugs never block the Claude session. This is acceptable for personal use but means "I didn't get a notification" has no breadcrumb trail; diagnose by running the hook script manually with a synthetic JSON payload on stdin, not by searching logs. The same silence applies to SessionStart/SessionEnd hooks: if `cortex-scan-lifecycle.sh` fails to inject `LIFECYCLE_SESSION_ID`, the session starts anyway and downstream tooling silently loses session identity.

---

## Security and Trust Boundaries

Overnight runs autonomously against a live working tree on a developer workstation. The trust boundaries below are enumerated once here; safety notes are not scattered elsewhere in this doc.

- **`--dangerously-skip-permissions`.** Overnight launches `claude` subprocesses with this flag, which disables the permission-prompt layer entirely. Threat model: any tool the subprocess is allowed to invoke runs without confirmation against the local filesystem and shell — sandbox configuration (the filesystem/network allowlist applied to the subprocess) becomes the critical security surface for autonomous execution.
- **`_ALLOWED_TOOLS` — SDK-level tool bound.** Task agents dispatched by `cortex_command/pipeline/dispatch.py` are bound to `_ALLOWED_TOOLS` at the SDK layer, orthogonal to `--dangerously-skip-permissions`. Threat model: a compromised or confused task agent cannot reach `WebFetch`, `WebSearch`, `Agent`, `Task`, or `AskUserQuestion` — they are not loaded, not merely denied — so it cannot spawn peer agents or exfiltrate via the web even under skipped permissions.
- **Dashboard binds `0.0.0.0`, unauthenticated, by design.** The dashboard is read-only and listens on all interfaces without auth. Threat model: anyone on the same layer-2 broadcast domain can read session state, feature names, and log excerpts; do not expose to the public internet and do not treat "local network" as equivalent to "home network" — hotel Wi-Fi, coworking Wi-Fi, and shared office VLANs are all "local" to the dashboard and are not trusted peers.
- **macOS keychain prompt as a session-blocking failure mode.** If authentication resolution (see [Internal APIs — Auth Resolution](#auth-resolution-apikeyhelper-and-env-var-fallback-order)) falls through to keychain-backed credentials, the first subprocess spawn may trigger a macOS keychain-access dialog. Threat model: the "runs while you sleep" premise breaks silently — the prompt blocks subprocess spawn until acknowledged, the round stalls, and no notification fires because the failure is pre-notification. Resolve by setting `ANTHROPIC_API_KEY` or configuring `apiKeyHelper` before the session starts.
- **"Local network" ≠ "home network".** This is a corollary of the dashboard boundary but is called out as its own item because the framing trap bites at 2am. Threat model: a reader who conflates the two will expose session state to whatever shared network they happen to be on; the dashboard's design assumes a trusted L2 peer set, which is only true on a network the operator controls end-to-end.

### Per-spawn sandbox enforcement

Overnight spawns two distinct kinds of `claude` subprocess: the per-round orchestrator (via `_spawn_orchestrator` in `cortex_command/overnight/runner.py`) and per-feature dispatched task agents (via `cortex_command/pipeline/dispatch.py`). Both spawn sites construct a per-spawn settings JSON file in `<session_dir>/sandbox-settings/` and pass `--settings <tempfile>` to the subprocess, so that OS-kernel sandbox enforcement (Seatbelt on macOS) is applied to each agent independently. The two surfaces share the same canonical JSON shape; the differences are in the deny-set and allow-set contents.

- **Orchestrator deny-set.** For the home repo and each cross-repo present in `state.integration_worktrees.keys()`, the orchestrator's `sandbox.filesystem.denyWrite` includes four git-state path suffixes per repo:
  - `<repo>/.git/refs/heads/main`
  - `<repo>/.git/refs/heads/master`
  - `<repo>/.git/HEAD`
  - `<repo>/.git/packed-refs`

  This is a static four-entry enumeration per repo — no dynamic `git symbolic-ref` resolution. Repos with custom default branches (e.g., `develop`, `trunk`) are not covered by V1 and are documented as a limitation. Denying entire `<repo>` paths would override cortex-init's user-scope `allowWrite` for `<repo>/cortex/` under the documented `denyWrite > allowWrite` precedence and crash the runner on the first events-log write; enumerating the specific git paths sidesteps this collision.

- **Dispatch allow-set.** Per-feature dispatch's `sandbox.filesystem.allowWrite` includes the worktree path plus six risk-targeted out-of-worktree writers cortex actively uses: `~/.cache/uv/`, `$TMPDIR/`, `~/.claude/sessions/`, `~/.cache/cortex/`, `~/.cache/cortex-command/`, and `~/.local/share/overnight-sessions/`. Per-entry rationale lives in `docs/internals/pipeline.md`'s "Allowed write paths" subsection. The dispatched-agent env locks `TMPDIR=$TMPDIR` to prevent the unset-TMPDIR fallback to `/tmp/`, which is not on the allow-set.

- **`CORTEX_SANDBOX_SOFT_FAIL` kill-switch.** Set the env var `CORTEX_SANDBOX_SOFT_FAIL=1` to downgrade `sandbox.failIfUnavailable` from `true` to `false` for new spawns within the session. This is the user-facing recovery path for Anthropic open sandbox-runtime regressions [#53085](https://github.com/anthropics/claude-code/issues/53085) and [#53683](https://github.com/anthropics/claude-code/issues/53683). The orchestrator's own per-spawn settings JSON is built once at orchestrator-spawn and is not re-read mid-process; the env var is re-read at each per-feature dispatch's settings-builder invocation, so toggling between dispatches affects only subsequent spawns. The morning report unconditionally surfaces a `CORTEX_SANDBOX_SOFT_FAIL=1 was active for this session` header line whenever the env var was truthy at any builder invocation during the session.

- **Threat-model boundary (Bash-only).** Sandbox enforcement covers Bash-tool subprocess writes via OS-kernel rules. It does NOT cover Write-tool or Edit-tool calls (which run in-process in the SDK and bypass the sandbox per Anthropic [#26616](https://github.com/anthropics/claude-code/issues/26616) and the official sandboxing docs at https://code.claude.com/docs/en/sandboxing) nor MCP-server-routed subprocess writes (MCP servers run unsandboxed at hook trust level). Telemetry on MCP writers is deferred to epic #162's child #164. The Write-then-Bash-execute composite vector (drop a script via Write, then `bash script.sh`) is coincidentally covered for git-state mutations because the deny-set targets the final filesystem write regardless of which tool initiated it.

- **Operational story for sandbox-denial command failures.** When a Bash command attempts a write to a deny-set path, the kernel returns EPERM and the command exits non-zero with `Operation not permitted` in stderr. The orchestrator's tool-failure tracker records the failure under `${TMPDIR:-/tmp}/claude-tool-failures-${SESSION_KEY}/` (migrated from `/tmp/` so the tracker writes are themselves on the allow-set), and the morning report surfaces the failure count by tool. If denial is unexpected (e.g., a legitimate write to a path that should be allowed), confirm whether the path is on the documented allow-set in `docs/internals/pipeline.md` "Allowed write paths" and either migrate the writer to a covered location or open a ticket to extend the allow-set with a one-sentence rationale entry.

- **Cross-repo dispatched agents lose home-repo cortex project hooks.** Pre-conversion, `_load_project_settings` blob-injected the home repo's project hooks at `--settings` top precedence regardless of dispatch CWD. Post-conversion, only the sandbox subtree is plumbed via `--settings`; project hooks merge naturally via Claude Code's multi-scope merge from project scope. For cross-repo dispatches the CWD is `state.integration_worktrees[repo_key]`, so the home cortex repo's `.claude/settings.json` is out of project scope — cortex's project hooks (skill-edit-advisor, tool-failure-tracker) do not load there. This is intentional: those hooks are cortex-internal observability and are not relevant when the dispatched agent is operating on a different repo's files.

- **Linux invocation advisory.** Sandbox enforcement is macOS-Seatbelt-only per parent epic #162. On non-Darwin platforms the settings-builder emits a one-line stderr warning at first invocation and continues; behavior under Linux/bwrap is undefined.

### Edge Cases

- **Hardcoded binary denies for `.vscode/` and `.idea/`.** Claude Code's binary contains a hardcoded `_SBX` deny list that permanently blocks writes to `.vscode/` and `.idea/` directories regardless of what is present in `sandbox.filesystem.allowWrite`. These denies are in the binary itself and cannot be overridden via settings JSON — they apply even when the worktree path or any ancestor is listed in the allow-set. The underlying issue is tracked at [anthropics/claude-code#51303](https://github.com/anthropics/claude-code/issues/51303). Three workarounds are available, ordered by invasiveness:
  1. **Sparse checkout** (preferred): untrack `.vscode/` and `.idea/` from the worktree via `git sparse-checkout` so the agent never attempts to write there. The directories become invisible to the agent and no deny is triggered.
  2. **`excludedCommands`**: add the relevant `git` subcommands to `excludedCommands` in the spawn settings so `git` runs outside the sandbox — useful when the IDE directory must be tracked but the agent needs to commit changes that touch it.
  3. **`dangerouslyDisableSandbox`** (last resort): pass `--dangerously-skip-permissions` to the `claude` subprocess to disable sandbox enforcement entirely for that spawn. This removes all OS-kernel write protection for the duration of the spawn and should be reserved for debugging or one-off manual runs, never for automated overnight sessions.

---

## Internal APIs

### orchestrator_io re-export surface

`cortex_command/overnight/orchestrator_io.py` is the sanctioned import boundary for orchestrator-callable I/O primitives. The module itself holds no logic — it re-exports a small, deliberately curated set of functions from `claude.overnight.state` and `claude.overnight.deferral` so the orchestrator prompt's Step 0 file-I/O calls can be imported from one module rather than reaching into internals. See `__all__` in `cortex_command/overnight/orchestrator_io.py` for the sanctioned surface; do not enumerate it here because the list is expected to grow and a doc-side enumeration would rot on the next addition.

**Files**: `cortex_command/overnight/orchestrator_io.py` (source of truth — `__all__`), consumed by `cortex_command/overnight/prompts/orchestrator-round.md`.

Convention: any new orchestrator-callable I/O primitive is added here rather than imported directly from `claude.overnight.state` or `claude.overnight.deferral` by the orchestrator. This keeps the orchestrator's blast radius for internal refactors bounded to one file.

### aggregate_round_context — round-startup state aggregator

`aggregate_round_context` consolidates the four scattered file reads that the orchestrator-round prompt previously performed at round startup into a single in-process function call. It is the canonical way to assemble round-startup state; direct file reads from orchestrator code are not the supported path.

**Import surface**: `from cortex_command.overnight.orchestrator_io import aggregate_round_context` (re-exported via `orchestrator_io.py`; do not import directly from `cortex_command.overnight.orchestrator_context`).

**Files**: `cortex_command/overnight/orchestrator_context.py` (implementation), `cortex_command/overnight/orchestrator_io.py` (re-export).

**Signature**: `aggregate_round_context(session_dir: Path, round_number: int) -> dict`

`session_dir` is the path to the session directory (e.g. `cortex/lifecycle/sessions/<session_id>/`). `round_number` is the current round number; it is included for schema-version tracing and is not used for filtering — callers retain round-filter logic.

The returned dict has five top-level keys:

| Key | Type | Content |
|-----|------|---------|
| `schema_version` | `int` | Contract version (currently `1`). Consumers must check this and handle drift explicitly — do not assume the value. |
| `state` | `dict` | Full overnight state from `asdict(load_state(session_dir / "overnight-state.json"))` — phase, per-feature status, round counter. |
| `strategy` | `dict` | Full overnight strategy from `asdict(load_strategy(session_dir / "overnight-strategy.json"))` — `hot_files`, `integration_health`, `recovery_log_summary`, `round_history_notes`. |
| `escalations` | `dict` | Pre-computed escalation sets: `{"unresolved": [...], "all_entries": [...]}`. `unresolved` is the set of escalation entries with no matching resolution or promoted entry (same logic as orchestrator-round.md Steps 0a–0d). `all_entries` is the full entry list from `escalations.jsonl`; the cycle-breaker reads `all_entries` directly. |
| `session_plan_text` | `str` | Contents of `session_dir / "session-plan.md"`, or `""` if the file is absent. |

**Error behavior**: `aggregate_round_context` raises `FileNotFoundError` if `overnight-state.json` is missing (propagated from `load_state`). It raises `RuntimeError` with the substring `"schema_version drift"` if the assembled dict's `schema_version` does not match the module-level `_EXPECTED_SCHEMA_VERSION` constant — this is the in-process safety net for contract changes. `load_strategy` tolerates missing/invalid `overnight-strategy.json` by returning a default instance; escalation lines that fail JSON parsing are skipped with a stderr warning. The function is read-only with respect to all state files and performs no in-process caching — each call reads fresh from disk.

### cortex/lifecycle.config.md consumers and absence behavior

`cortex/lifecycle.config.md` is a per-project config file (template at `skills/lifecycle/assets/lifecycle.config.md`). There is no centralized Python loader — each consumer reads it directly — so the contract is "template is source of truth for fields; each consumer decides its own absence behavior." Fields include `type`, `test-command`, `demo-command` / `demo-commands`, `default-tier`, `default-criticality`, `skip-specify`, `skip-review`, and `commit-artifacts`.

**Files**: `skills/lifecycle/assets/lifecycle.config.md` (template — source of truth for the field list), plus the consumers in `skills/lifecycle/`, `skills/critical-review/`, and `skills/morning-review/`.

Absence behavior per consumer (what happens when the project has no `cortex/lifecycle.config.md`):

- **morning-review**: skips Section 2a (the demo-commands walkthrough) and continues the rest of the review.
- **lifecycle complete**: skips the test step with a note that no `test-command` was configured.
- **critical-review**: omits the `## Project Context` section of the generated review.
- **lifecycle specify/plan**: reads optional defaults (`default-tier`, `default-criticality`, `skip-specify`, `skip-review`) and falls back to skill-level defaults when absent.

Because field drift across consumers is possible, the template is the one place to check before assuming a field exists; do not enumerate fields in more than one doc.

### Auth Resolution (apiKeyHelper and env-var fallback order)

Auth resolution is owned by the shared `cortex_command/overnight/auth.py` module. Both the overnight entry point (`runner.sh`) and the daytime entry point (`daytime_pipeline.py`) delegate to this one module so they share one priority order, one sanitization rule, and one event schema — divergence between the two paths would be a silent correctness hazard.

The module resolves Anthropic authentication in a strict 4-step fallback order before any subprocess is spawned. Each step short-circuits on success.

1. **`ANTHROPIC_API_KEY` already in the environment** — use it as-is and stop. This is the common CI/dev path (vector: `env_preexisting`).
2. **`apiKeyHelper` configured in `~/.claude/settings.json` or `~/.claude/settings.local.json`** — execute the helper command and export its stdout as `ANTHROPIC_API_KEY`. This is the recommended path for machines that keep the key out of shell profiles (vector: `api_key_helper`).
3. **No helper AND no `CLAUDE_CODE_OAUTH_TOKEN`** — try `~/.claude/personal-oauth-token`; if non-empty, export its contents as `CLAUDE_CODE_OAUTH_TOKEN`. This covers OAuth-style authentication for `claude -p` / SDK usage (vector: `oauth_file`).
4. **Fall through to keychain-backed auth** — print a warning and proceed; the first subprocess spawn may block on a macOS keychain-access prompt (see [Security and Trust Boundaries](#security-and-trust-boundaries)). Vector: `none`.

**Files**: `cortex_command/overnight/auth.py` (shared resolver — source of truth), `cortex_command/overnight/runner.sh` (shell delegation), `cortex_command/overnight/daytime_pipeline.py` (in-process delegation inside `run_daytime`), `cortex_command/pipeline/dispatch.py` (re-exports both `ANTHROPIC_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` into SDK subprocesses).

#### Shell entry point: three-exit-code contract

`runner.sh` invokes the helper pre-venv via `cortex-auth --shell` and branches on the exit code:

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

### Lifecycle-archive recovery procedure

The `just lifecycle-archive` recipe (housekeeping that moves long-completed feature directories from `cortex/lifecycle/` into `cortex/lifecycle/archive/` and rewrites cross-references) is git-recoverable by design. There is no manifest-driven rollback — recovery is a single git command from the main repo CWD.

The recipe asserts a clean working tree on entry (`git diff --quiet HEAD && git diff --quiet --cached HEAD`) so that any subsequent change in the working tree is unambiguously attributable to this run. If that precheck fails, the recipe aborts before touching anything; if a mid-run abort occurs (a `set -euo pipefail` exit, a partial `mv`, a `sed`/path-rewrite error, or operator interrupt), the working tree contains only this run's incomplete edits.

Recovery is three steps:

1. **Confirm the failure mode** — either the precheck error (recipe never ran) or a mid-run abort (partial moves and/or rewrites visible in `git status`).
2. **Revert from the main repo CWD**: `git checkout -- .` discards all uncommitted moves and `*.md` rewrites since the clean-tree baseline. This restores the pre-run state in one command.
3. **Treat the manifest as audit-only** — `cortex/lifecycle/archive/.archive-manifest.jsonl` (NDJSON, appended atomically before each `mv`) records what the recipe attempted, but it exists for inspection and audit (e.g., morning-report integration) only. Do NOT script a manifest-driven rollback; the supported recovery path is `git checkout -- .` and nothing else. The manifest persists across the abort because it lives under `cortex/lifecycle/archive/` (which the recipe creates outside the moved-set), so it remains readable for post-mortem after the checkout.

For larger archive runs, prefer the two-phase pattern documented in N6.4 of the apply-post-113-audit-follow-ups spec (a deterministic 5-dir sample run, commit, then the full run on remaining dirs), which keeps each commit boundary small enough that a `git checkout -- .` recovery never crosses a successful prior phase.
