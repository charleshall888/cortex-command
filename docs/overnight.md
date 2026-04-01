[← Back to Agentic Layer](agentic-layer.md)

# Overnight: In Depth

**For:** Users with features ready to run in autonomous overnight sessions.  **Assumes:** Familiarity with the lifecycle skill and at least one backlog item with `status: refined`.

The overnight system runs fully autonomous development sessions while you sleep. You
select features from the backlog, approve a session plan, launch a bash runner in a
detached tmux session, and go to bed. In the morning, `/morning-review` walks the
results, closes completed features, and surfaces any decisions that needed a human.

This document covers how it all works — the planning step you do before bed, the
execution machinery running while you sleep, and the morning close-out.

> **Jump to:** [Quick-Start](#quick-start-checklist) | [Prerequisites](#prerequisites--what-makes-a-feature-overnight-ready) | [Planning](#the-planning-phase) | [Deferral System](#the-deferral-system) | [Morning Review](#the-morning-review) | [Commands](#command-reference) | [Advanced Reference](#advanced--operator-reference)

---

## Quick-Start Checklist

### Evening (before you launch)

- [ ] Features in backlog have `status: refined`
- [ ] Each feature has `research:` and `spec:` frontmatter fields pointing to existing files
- [ ] `lifecycle/{slug}/spec.md` exists for each feature (run `/refine <item>` to produce it)
- [ ] Python venv is set up (`just python-setup` if not done)
- [ ] Run `/overnight` in Claude Code — review and approve the session plan
- [ ] (Optional) Launch the [dashboard](dashboard.md) in a separate terminal: `just dashboard`
- [ ] Run `overnight-start` in a terminal

### Morning (after the session)

- [ ] Run `/morning-review` in Claude Code
- [ ] Answer any deferred questions from `deferred/`
- [ ] Review and merge the session PR (from `overnight/{session_id}` to main)
- [ ] Carry over any failed or deferred features to next session

---

## Per-repo Overnight

The overnight runner can be launched from any repo — not just cortex-command.

**From the cortex-command repo:** both `overnight-start` and `just overnight-start` work. Use whichever is convenient.

**From any other repo:**

1. Open a Claude session in that repo's directory.
2. Run `/overnight` — it will generate the session plan and write the state file to `lifecycle/sessions/{session_id}/overnight-state.json` inside that repo.
3. In a terminal, launch the runner with the explicit state file path:
   ```bash
   overnight-start lifecycle/sessions/{session_id}/overnight-state.json
   ```

**Status and log tools are cortex-command tools** — invoke them via `jcc` from any terminal:

```bash
jcc overnight-status
jcc overnight-logs
jcc overnight-smoke-test
```

---

## Prerequisites — What Makes a Feature Overnight-Ready

Overnight does **not** run interactive research or spec phases. Features must be fully
prepared before selection. The readiness gate checks four things:

| Requirement | Where it comes from |
|-------------|-------------------|
| `status: refined` in backlog frontmatter | Set by `/refine` on spec approval, or manually with `/backlog` |
| `research:` field in backlog YAML pointing to an existing file | Produced by `/refine` or `/discovery` |
| `spec:` field in backlog YAML pointing to an existing file | Produced by `/refine` or `/discovery` |
| `lifecycle/{slug}/spec.md` exists on disk | Produced by `/refine <item>` |

A feature that passes all four checks is eligible for overnight selection. Features
that fail the gate are reported as ineligible with a reason — they don't silently drop.

**The typical prep path:**

```
/discovery <topic>          (optional — for topics not yet broken into tickets)
    → writes research + spec artifacts
    → creates backlog tickets with research: and spec: frontmatter

/refine <item>              (for each backlog ticket you want to run overnight)
    → Clarify → Research → Spec phases (interactive, ~15 min)
    → produces lifecycle/{slug}/spec.md
    → sets status: refined on the backlog item

/overnight                  → select features, approve plan, launch
```

`/refine` is the dedicated prep tool for overnight: it stops at spec, writes `status: refined`,
and does not proceed to plan or implement. Use `/lifecycle <feature>` instead when you want
the full interactive research-specify-plan-implement flow for a single feature.

See [Interactive Phases Guide](interactive-phases.md) for details on what `/refine` asks
during each phase and how artifacts flow to the overnight runner.

`plan.md` is generated automatically by the orchestrator on demand — you don't need to
run `/lifecycle plan` before an overnight session.

---

## The Planning Phase

Run `/overnight` to start the interactive planning session. The skill walks five steps:

### 1. Select eligible features

`select_overnight_batch()` scans `backlog/NNN-*.md`, parses YAML frontmatter, applies
the readiness gate, and scores eligible items using a weighted algorithm:

- **Dependency structure** — unblocked features rank higher
- **Priority** — critical > high > medium > low
- **Tag cohesion** — features sharing knowledge domain cluster into the same batch
  to reduce context-switching overhead across batches
- **Type routing** — bugs, features, and chores can be separated into different batches

Items are grouped into **batches** (rounds). Each batch runs as a unit; batches execute
sequentially, and features within a batch execute in parallel up to the concurrency limit.

### 2. Present selection summary

The skill shows:
- How many eligible items exist and how many batches they form
- Per-batch breakdown (batch number, batch context domain, feature titles)
- Ineligible items with their reasons

### 3. Review and adjust the session plan

The rendered plan includes:

- Features table: round assignment, type, priority, pre-work status
- Execution strategy: number of rounds, concurrency, estimated duration
- Risk assessment: file overlap warnings, dependency concerns
- Stop conditions

You can adjust before approving:
- **Concurrency limit** (default 2): number of features executing in parallel per round
- **Remove features**: exclude specific items; the plan re-renders automatically

### 4. Launch

On approval, the skill:

1. Writes `lifecycle/overnight-plan.md` — the session plan is immutable from this point (per-feature `plan.md` files are generated later by the orchestrator if missing)
2. Initializes `lifecycle/overnight-state.json` with session ID (`overnight-YYYY-MM-DD-HHmm`), feature statuses, round assignments, and phase `executing`
3. Creates git integration branch `overnight/{session_id}`
4. Extracts and commits batch spec sections (if applicable)
5. Logs `SESSION_START` to the event log
6. Prints the runner command

You then run `overnight-start` in a terminal (or a separate Ghostty/tmux window). That's it for the evening.

---

## Advanced / Operator Reference

*The sections below cover runner internals, state files, and recovery procedures. On your first run, skip ahead to [Command Reference](#command-reference).*

---

## The Execution Phase

### Architecture

```
overnight-start
    → validates state file (phase must be 'executing')
    → launches runner.sh in tmux session 'overnight-runner'

runner.sh (outer loop)
    → spawns one Claude orchestrator agent per round
    → monitors progress via overnight-state.json
    → enforces time limit, circuit breakers, stall detection

orchestrator agent (per round)
    → reads state + plan
    → generates any missing plan.md files (sub-agents, parallel)
    → generates batch master plan for this round
    → runs batch runner

batch runner (python3 -m claude.overnight.batch_runner)
    → creates git worktrees (one per feature)
    → dispatches parallel pipeline workers
    → enforces concurrency limit
    → handles retries, deferrals, merges
    → writes batch-{N}-results.json

pipeline worker (one per feature)
    → reads plan.md + spec.md
    → implements tasks, commits to feature branch
    → merges feature branch to integration branch on success
    → on merge conflict: marks feature failed, writes error to batch results
```

Merge conflicts are reported as `failed` in the batch results and morning report — the
integration branch is left at the last successful merge point. See
[Recovery: merge conflict](#recovery-merge-conflict-on-integration-branch) if this occurs.

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

Each round spawns a fresh `claude -p` invocation — the orchestrator reads state files
each time rather than carrying memory between rounds.

### Circuit Breakers

The runner has three automatic stop conditions:

| Trigger | Condition | Behavior |
|---------|-----------|----------|
| Zero-progress breaker | 0 features merged in 2 consecutive rounds | Stops the session, logs `CIRCUIT_BREAKER` |
| Time limit | Wall-clock elapsed ≥ `--time-limit` | Stops the session, logs `CIRCUIT_BREAKER` |
| Stall watchdog | No event written to events log for 30 minutes | Kills the Claude agent, pauses state, sends notification |

A stopped session enters phase `paused` (not `complete`) if features remain. Use
`/overnight resume` to check state and relaunch with `overnight-start`.

### Signal Handling

SIGINT or SIGTERM (e.g. Ctrl-C or `kill`) triggers a graceful shutdown:

1. Transitions state to `paused`
2. Logs a `CIRCUIT_BREAKER` event with `reason: signal`
3. Generates a partial morning report
4. Archives session artifacts to `lifecycle/sessions/{id}/`
5. Sends a push notification

### Concurrency

The batch runner uses a `ConcurrencyManager` from `throttle.py` to cap parallel
workers. Default is 2. Setting it higher than 3 risks git conflicts and API rate
limiting — keep it at 2 for most sessions, 3 only when features are clearly independent
(non-overlapping file sets).

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
| `batch_runner.py` | Batch execution: dispatches pipeline workers, enforces concurrency, handles deferrals, merges |
| `brain.py` | Post-retry triage agent (SKIP/DEFER/PAUSE decisions via Claude API) |
| `throttle.py` | Subscription-aware `ConcurrencyManager` with adaptive rate-limit backoff |
| `interrupt.py` | Startup recovery: resets `running` features to `pending` with reason logging |
| `deferral.py` | Question deferral file writer (blocking/non-blocking/informational) |
| `report.py` | Morning report generator (reads state + events + deferrals) |
| `map_results.py` | Maps `batch-{N}-results.json` → `overnight-state.json` + strategy updates |
| `status.py` | Live status display (single-screen snapshot; used by `just overnight-status`) |
| `integration_recovery.py` | Integration branch test-failure recovery; dispatches repair agent |
| `smoke_test.py` | Pre-launch toolchain sanity check |

---

## The Deferral System

When a pipeline worker encounters a question it cannot resolve without human input, it
does **not** block the entire session. Instead it defers the question:

| Severity | Meaning | Worker behavior | Feature status |
|----------|---------|-----------------|----------------|
| `blocking` | Decision required to proceed | Writes deferral, stops work | `paused` |
| `non-blocking` | Made a reasonable default; validate later | Writes deferral, **continues and commits** | Work continues |
| `informational` | Something unexpected found; FYI only | Writes deferral, continues | Work continues |

Deferral files are written to `deferred/{feature-slug}-q{NNN}.md`. The morning report
surfaces them grouped by severity. `/morning-review` presents blocking questions first
and lets you answer them before proceeding to feature close-out.

**Important: non-blocking deferrals mean committed code, not just a logged note.**
When a worker classifies a deferral as non-blocking, it has already written and committed
code based on its "reasonable default" assumption. By morning, that assumption may be
built upon by other tasks in the same feature. If the default was wrong, you are
reversing committed git history — not answering a question before work begins. Treat
non-blocking deferrals in the morning report as code review items, not informational
messages.

---

## State Files and Artifacts

| File | Description |
|------|-------------|
| `lifecycle/overnight-plan.md` | Approved session plan (immutable after approval). Symlink to latest session. |
| `lifecycle/overnight-state.json` | Live execution state during session. Symlink → `sessions/{id}/overnight-state.json`. |
| `lifecycle/overnight-events.log` | Append-only structured event log. Symlink → `sessions/{id}/overnight-events.log`. |
| `lifecycle/morning-report.md` | Generated at session end by `report.py`. Symlink → `sessions/{id}/morning-report.md`. |
| `lifecycle/sessions/{id}/` | Archive directory: contains plan, state, events, report for each session. |
| `lifecycle/batch-plan-round-{N}.md` | Per-round batch master plan (ephemeral; generated by orchestrator). |
| `lifecycle/batch-{N}-results.json` | Per-round batch runner results (ephemeral). |
| `deferred/{slug}-q{NNN}.md` | Deferral question files for morning review. |

The canonical files (`overnight-plan.md`, `overnight-state.json`, etc.) are symlinks to
the latest session's archive directory. This means reading them always gives you the
current session's data, while old sessions remain accessible at their archive paths.

### Reading State Manually

```bash
# What features are pending/merged/failed?
python3 -c "
import json
state = json.load(open('lifecycle/overnight-state.json'))
for name, f in state['features'].items():
    print(f['status'].ljust(12), name)
"

# What events have fired?
cat lifecycle/overnight-events.log | python3 -c "
import json, sys
for line in sys.stdin:
    e = json.loads(line)
    print(e['ts'][:19], e['event'])
"
```

---

## The Morning Review

Run `/morning-review` the morning after an overnight session.

The skill:

1. **Reads `lifecycle/morning-report.md`** — the full session summary
2. **Walks each report section** in order (executive summary, feature outcomes, deferred questions)
3. **Presents deferred questions** for you to answer; answers are written back and features can resume
4. **Advances completed lifecycles** — features marked merged get their `events.log` closed out
5. **Archives closed backlog items** — resolved items move to `backlog/archive/`

The session PR (from `overnight/{session_id}` to `main`) is created automatically at
session end. `/morning-review` surfaces its URL so you can review and merge.

> For runner internals, state files, and recovery procedures, see [Advanced / Operator Reference](#advanced--operator-reference) below.

---

## Command Reference

| Command | What it does |
|---------|-------------|
| `overnight-start` | Launch runner in a detached tmux session (recommended) |
| `overnight-start --max-rounds 5` | Launch with round cap |
| `just overnight-run` | Launch runner in foreground (useful for debugging) |
| `just overnight-status` | Live auto-refreshing status display |
| `just overnight-logs` | Tail the active session's event log |
| `just overnight-smoke-test` | Verify worker commit round-trip (pre-launch sanity check) |
| `tmux attach -t overnight-runner` | Attach to running session to watch output |
| `/overnight resume` | Check state and relaunch a paused session |
| `/morning-review` | Morning close-out: walk report, answer deferrals, close features |

---

## Best Practices

### Session size

**3–5 features per session** is the sweet spot. Too few (1–2) wastes the overhead of
spinning up the session infrastructure; too many (8+) increases the chance that a single
failure in a shared file causes cascading conflicts that waste the session. The upper
bound is also driven by context budget: each orchestrator agent reads all selected
features' specs and plans, and loading too many at once risks overflowing the agent's
context window.

### Concurrency

Keep `--concurrency 2` (the default) unless you're confident the features touch
non-overlapping files. The `overnight-start` flags override the plan's default:

```bash
overnight-start
```

To override concurrency, set it during `/overnight` plan approval, not at runner launch.

**How concurrency interacts with git conflict detection:** Conflicts are detected at
merge time, not at dispatch time. When parallel features both modify the same file,
the second feature to attempt merging its branch to the integration branch will
encounter a conflict. On conflict, the pipeline first attempts a trivial fast-path
resolution (`--theirs` strategy); if that fails, it calls `dispatch_repair_agent()`
which creates an isolated repair worktree and dispatches a Claude agent (Sonnet,
escalating to Opus on quality failure) to resolve the conflict. If the repair agent
also fails, the feature is marked `paused` and carried to the next session. Higher
concurrency increases the probability of two features touching the same file in the
same round, which is why 2 is the safe default and 3 should only be used for clearly
non-overlapping feature sets.

### What to prepare the night before

- Run `/backlog pick` → `/refine <item>` for each target feature
- `/refine` runs Clarify → Research → Spec and sets `status: refined` — takes ~15 min per feature
- Verify `lifecycle/{slug}/spec.md` exists: `ls lifecycle/*/spec.md`
- Run `just overnight-smoke-test` once to verify the toolchain is healthy

### Morning workflow

Don't merge the overnight PR directly from GitHub. Run `/morning-review` first — it
closes lifecycle artifacts and archives backlog items in the right order. Then merge.

### If something goes wrong mid-session

- Attach to the runner: `tmux attach -t overnight-runner`
- Check state: `just overnight-status`
- If stalled: Ctrl-C exits gracefully. Then `/overnight resume` + `overnight-start`
- Check `deferred/` for blocking questions that paused features

### Recovery: corrupt or inconsistent state

A feature can show `running` status in three distinct ways:

1. **Crash with no graceful shutdown** — power loss, OOM kill, or `SIGKILL` left the
   state file unmodified mid-execution. The status is stale: the feature was executing
   when the process died and was never transitioned to a terminal state.
2. **Normal round end while feature was still executing** — the batch runner closed
   the round (e.g. hit the round time limit or a circuit breaker fired) while a
   pipeline worker was still mid-execution. `map_results.py` maps any feature whose
   pipeline status is still `pending` or `executing` at round-end to `running` in
   overnight state. The feature was live when the round closed.
3. **Orchestrator marks pending features running at round start** — at the beginning
   of each round, the orchestrator reads features in `pending` state and transitions
   them to `running` before dispatching workers. If the orchestrator itself is
   interrupted after this point but before dispatch completes, features appear `running`
   with no active worker.

Symptoms: `just overnight-status` shows `running` features with no runner process
visible, `/overnight resume` reports unexpected phase, or `just overnight-status`
errors (if the JSON was partially written).

**Diagnosis:**
```bash
# Validate JSON is parseable
python3 -c "import json; json.load(open('lifecycle/overnight-state.json')); print('valid')"

# Check which features are stuck in 'running'
python3 -c "
import json
state = json.load(open('lifecycle/overnight-state.json'))
for name, f in state['features'].items():
    if f['status'] == 'running':
        print('stuck running:', name)
"
```

**Recovery:** Features stuck in `running` are reset to `pending` automatically by
`claude/overnight/interrupt.py` when the runner starts — this runs as the first step of
every `overnight-start`. If the JSON itself is corrupt, restore from the session
archive (`lifecycle/sessions/{id}/overnight-state.json` from a prior round) and replay
the missing round by relaunching.

### Recovery: merge conflict on integration branch

If a feature fails with a merge conflict (visible in morning report as `failed` with
a merge error), the integration branch may have a half-applied merge. **Do not run
`/morning-review` and merge the PR if you see unexplained failed features without
checking the branch first.**

**Diagnosis:**
```bash
git log --oneline overnight/{session_id} | head -20
git status  # if you're on the integration branch
```

**Recovery options:**
1. If the conflict is small: checkout the integration branch, resolve manually, commit
2. If the failed feature is not critical: leave it out of this PR, carry it to the next
   session (it stays `failed` in state; `/morning-review` will report it as carried over)
3. If the integration branch is badly tangled: create a new integration branch from
   the last clean merge point and cherry-pick the successful feature commits

### Readiness gate: file existence, not quality

The readiness gate checks that `research:` and `spec:` paths exist on disk — it does
not evaluate their content. A two-sentence spec passes. A six-month-old research file
passes. Quality of the artifacts is your responsibility before setting a feature to
`status: refined`. Features with thin specs are the most common source of blocking
deferrals and plan-generation failures during overnight execution.

---

## Overnight vs Lifecycle

Both are development orchestration skills — they differ in interactivity and
required preparation:

| | Lifecycle | Overnight |
|--|-----------|-----------|
| **User present** | Throughout all phases | Approval only |
| **Features** | Single | 2+ (fully prepared) |
| **Research needed** | Runs it | Must exist already |
| **Spec needed** | Runs it | Must exist already |
| **Plan** | Runs it | Auto-generated if missing |
| **Execution** | Interactive | Bash runner + tmux |
| **Resume** | `/lifecycle resume` | `/overnight resume` |
| **Morning close-out** | Manual or `/lifecycle complete` | `/morning-review` |

**Choose overnight when**: You have a backlog of prepared features and want to make
progress while not at your computer.

**Choose lifecycle when**: You're working on a single feature and want the full
interactive research-specify-plan-implement flow.
