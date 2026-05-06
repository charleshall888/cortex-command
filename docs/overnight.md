[← Back to Agentic Layer](agentic-layer.md)

# Overnight: In Depth

**For:** Users with features ready to run in autonomous overnight sessions.  **Assumes:** Familiarity with the lifecycle skill and at least one backlog item with `status: refined`.

The overnight system runs fully autonomous development sessions while you sleep. You
select features from the backlog, approve a session plan, launch the runner in a
detached tmux session, and go to bed. In the morning, `/morning-review` walks the
results, closes completed features, and surfaces any decisions that needed a human.

This document covers how it all works — the planning step you do before bed, the
execution machinery running while you sleep, and the morning close-out.

For mechanics, state files, recovery, and debugging procedures, see [overnight-operations.md](overnight-operations.md).

> **Jump to:** [Quick-Start](#quick-start-checklist) | [Per-repo Overnight](#per-repo-overnight) | [Prerequisites](#prerequisites--what-makes-a-feature-overnight-ready) | [Planning](#the-planning-phase) | [Deferral System](#the-deferral-system) | [Morning Review](#the-morning-review) | [Commands](#command-reference) | [Best Practices](#best-practices) | [Overnight vs Lifecycle](#overnight-vs-lifecycle)

---

## Quick-Start Checklist

### Evening (before you launch)

- [ ] Features in backlog have `status: refined`
- [ ] Each feature has `research:` and `spec:` frontmatter fields pointing to existing files
- [ ] `lifecycle/{slug}/spec.md` exists for each feature (run `/cortex-core:refine <item>` to produce it)
- [ ] Python venv is set up (`just python-setup` if not done)
- [ ] Run `/overnight` in Claude Code — review and approve the session plan
- [ ] (Optional) Launch the [dashboard](dashboard.md) in a separate terminal: `just dashboard`
- [ ] Run `cortex overnight start` in a terminal

### Morning (after the session)

- [ ] Run `/morning-review` in Claude Code
- [ ] Answer any deferred questions from `deferred/`
- [ ] Review and merge the session PR (from `overnight/{session_id}` to main)
- [ ] Carry over any failed or deferred features to next session

---

## Per-repo Overnight

The overnight runner can be launched from any repo — not just cortex-command.

### Setup: lifecycle.config.md

Before running overnight in a new repo, create a `lifecycle.config.md` at the repo root. A template lives at `skills/lifecycle/assets/lifecycle.config.md` in cortex-command:

```yaml
---
type: web-app              # web-app | cli-tool | library | game | other
test-command: npm test      # shell command to validate merges
# demo-command:             # e.g., godot res://main.tscn, uv run fastapi run src/main.py
# demo-commands:
#   - label: "Godot gameplay"
#     command: "godot res://main.tscn"
#   - label: "FastAPI dashboard"
#     command: "uv run fastapi run src/main.py"
skip-specify: false
skip-review: false
commit-artifacts: true
---
```

The most important field is **`test-command`**. This is the shell command that runs after each feature branch merges to the integration branch during overnight execution. If tests fail, the runner attempts automated repair via a repair agent. If repair fails, the feature is paused and surfaced in the morning report.

**If you don't set `test-command`**: features merge with no validation. The overnight runner assumes success and moves on. This is the most common source of broken integration branches that aren't caught until morning.

Other fields:
- **`type`**: Informs model selection heuristics and review criteria
- **`demo-command`** / **`demo-commands`**: Optional. When `demo-command:` is set to a single string, the morning-review walkthrough (Section 2a) offers to spin up a demo worktree from the overnight integration branch and print that launch command. The agent prints the command for you to run manually — it never executes it. Only offered when the session is local (no `$SSH_CONNECTION`) and the overnight branch exists. Examples: `godot res://main.tscn`, `uv run fastapi run src/main.py`, `npm start`. Alternatively, `demo-commands:` may be configured as a list of `label:` / `command:` entries; the morning-review agent reasons from the completed-feature context (Section 2 "Key files changed") to select the most relevant entry and offer it. If none is relevant to the completed feature, the section is skipped silently.
- **`skip-specify`** / **`skip-review`**: Skip lifecycle phases when they don't add value for this repo
- **`commit-artifacts`**: Whether lifecycle artifacts (spec, plan, review) are committed to the repo

### Launching from another repo

**From the cortex-command repo:** run `cortex overnight start`.

**From any other repo:**

1. Ensure `lifecycle.config.md` exists at the repo root with `test-command` configured.
2. Open a Claude session in that repo's directory.
3. Run `/overnight` — it will generate the session plan and write the state file to `lifecycle/sessions/{session_id}/overnight-state.json` inside that repo.
4. In a terminal, launch the runner with the explicit state file path:
   ```bash
   cortex overnight start --state lifecycle/sessions/{session_id}/overnight-state.json
   ```

**Status and log:**

```bash
cortex overnight status               # current session status
cortex overnight logs                 # tail event log
cortex-jcc overnight-smoke-test       # pre-launch sanity check (Just recipe via plugin wrapper)
```

---

## Prerequisites — What Makes a Feature Overnight-Ready

Overnight does **not** run interactive research or spec phases. Features must be fully
prepared before selection. The readiness gate checks four things:

| Requirement | Where it comes from |
|-------------|-------------------|
| `status: refined` in backlog frontmatter | Set by `/cortex-core:refine` on spec approval, or manually with `/cortex-core:backlog` |
| `research:` field in backlog YAML pointing to an existing file | Produced by `/cortex-core:refine` or `/cortex-core:discovery` |
| `spec:` field in backlog YAML pointing to an existing file | Produced by `/cortex-core:refine` or `/cortex-core:discovery` |
| `lifecycle/{slug}/spec.md` exists on disk | Produced by `/cortex-core:refine <item>` |

A feature that passes all four checks is eligible for overnight selection. Features
that fail the gate are reported as ineligible with a reason — they don't silently drop.

**The typical prep path:**

```
/cortex-core:discovery <topic>          (optional — for topics not yet broken into tickets)
    → writes research + spec artifacts
    → creates backlog tickets with research: and spec: frontmatter

/cortex-core:refine <item>              (for each backlog ticket you want to run overnight)
    → Clarify → Research → Spec phases (interactive, ~15 min)
    → produces lifecycle/{slug}/spec.md
    → sets status: refined on the backlog item

/overnight                  → select features, approve plan, launch
```

`/cortex-core:refine` is the dedicated prep tool for overnight: it stops at spec, writes `status: refined`,
and does not proceed to plan or implement. Use `/cortex-core:lifecycle <feature>` instead when you want
the full interactive research-specify-plan-implement flow for a single feature.

See [Interactive Phases Guide](interactive-phases.md) for details on what `/cortex-core:refine` asks
during each phase and how artifacts flow to the overnight runner.

`plan.md` is generated automatically by the orchestrator on demand — you don't need to
run `/cortex-core:lifecycle plan` before an overnight session.

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
sequentially, and features within a batch execute in parallel.

### 2. Present selection summary

The skill shows:
- How many eligible items exist and how many batches they form
- Per-batch breakdown (batch number, batch context domain, feature titles)
- Ineligible items with their reasons

### 3. Review and adjust the session plan

The rendered plan includes:

- Features table: round assignment, type, priority, pre-work status
- Execution strategy: number of rounds, estimated duration
- Risk assessment: file overlap warnings, dependency concerns
- Stop conditions

You can adjust before approving:
- **Remove features**: exclude specific items; the plan re-renders automatically

### 4. Launch

On approval, the skill:

1. Writes `lifecycle/overnight-plan.md` — the session plan is immutable from this point (per-feature `plan.md` files are generated later by the orchestrator if missing)
2. Initializes `lifecycle/overnight-state.json` with session ID (`overnight-YYYY-MM-DD-HHmm`), feature statuses, round assignments, and phase `executing`
3. Creates git integration branch `overnight/{session_id}`
4. Extracts and commits batch spec sections (if applicable)
5. Logs `SESSION_START` to the event log
6. Prints the runner command

You then run `cortex overnight start` in a terminal (or a separate Ghostty/tmux window). That's it for the evening.

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

> For runner internals, state files, and recovery procedures, see [overnight-operations.md](overnight-operations.md).

---

## Command Reference

| Command | What it does |
|---------|-------------|
| `cortex overnight start` | Launch runner in a detached tmux session (recommended) |
| `cortex overnight start --max-rounds 5` | Launch with round cap |
| `just overnight-run` | Launch runner in foreground (useful for debugging) |
| `cortex overnight status` | Print session status (`--format json` for machine-readable) |
| `cortex overnight logs` | Tail the active session's event log |
| `just overnight-smoke-test` | Verify worker commit round-trip (pre-launch sanity check) |
| `tmux attach -t overnight-runner` | Attach to running session to watch output |
| `/overnight resume` | Check state and relaunch a paused session |
| `/morning-review` | Morning close-out: walk report, answer deferrals, close features |

---

## Best Practices

### Session size

The runner scales well — you can queue as many features as you like. There is no recommended upper limit.

### What to prepare the night before

- Run `/cortex-core:backlog pick` → `/cortex-core:refine <item>` for each target feature
- `/cortex-core:refine` runs Clarify → Research → Spec and sets `status: refined` — takes ~15 min per feature
- Verify `lifecycle/{slug}/spec.md` exists: `ls lifecycle/*/spec.md`
- Run `just overnight-smoke-test` once to verify the toolchain is healthy

### Morning workflow

Don't merge the overnight PR directly from GitHub. Run `/morning-review` first — it
closes lifecycle artifacts and archives backlog items in the right order. Then merge.

### If something goes wrong mid-session

- Attach to the runner: `tmux attach -t overnight-runner`
- Check state: `cortex overnight status`
- If stalled: Ctrl-C exits gracefully. Then `/overnight resume` + `cortex overnight start`
- Check `deferred/` for blocking questions that paused features

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
| **Resume** | `/cortex-core:lifecycle resume` | `/overnight resume` |
| **Morning close-out** | Manual or `/cortex-core:lifecycle complete` | `/morning-review` |

**Choose overnight when**: You have a backlog of prepared features and want to make
progress while not at your computer.

**Choose lifecycle when**: You're working on a single feature and want the full
interactive research-specify-plan-implement flow.
