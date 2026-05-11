---
name: overnight
description: Plan and launch autonomous overnight development sessions. Selects eligible features from the backlog, presents a session plan for user approval, and hands off to the runner for unattended execution. Use when user says "/overnight", "/overnight resume", "/overnight status", "start overnight session", "overnight plan", "launch overnight", "overnight status", or wants to run multiple features autonomously overnight.
disable-model-invocation: true
inputs:
  - "time-limit: string (optional) — Maximum wall-clock duration for the overnight session (e.g. '6h'). Passed as --time-limit to the runner."
outputs:
  - "lifecycle/sessions/{SESSION_ID}/overnight-plan.md — selected session plan with feature list"
  - "lifecycle/sessions/{SESSION_ID}/overnight-state.json — execution state for the runner"
  - "lifecycle/sessions/{SESSION_ID}/session.json — session manifest (type, id, started, features)"
  - "lifecycle/sessions/{SESSION_ID}/overnight-events.log — session events log"
  - "lifecycle/sessions/{SESSION_ID}/morning-report.md — session morning report"
  - "lifecycle/sessions/latest-overnight — symlink to the current session directory"
preconditions:
  - "lifecycle/{slug}/spec.md exists for each candidate feature"
  - "backlog/NNN-slug.md files exist with status: refined"
  - "Run from project root"
---

# Overnight Session Planning

Interactive entry point for overnight autonomous orchestration. Guides the user through selecting features from the backlog, reviewing a session plan, and launching overnight execution. The skill itself handles planning and approval; execution is delegated to the runner.

For the canonical round-loop and orchestrator behavior that the runner implements after launch, see `docs/overnight-operations.md` (source of truth per CLAUDE.md). This skill stops at handoff — it does not duplicate runner semantics.

## References

Detailed step procedures, worked examples, and success-criteria checklists are extracted to references. Read on demand for the flow you are currently executing:

| Topic | Reference |
|-------|-----------|
| New session flow (Steps 1–7 detail, launch sub-steps) | [new-session-flow.md](${CLAUDE_SKILL_DIR}/references/new-session-flow.md) |
| Resume flow (load state, report, act on choice) | [resume-flow.md](${CLAUDE_SKILL_DIR}/references/resume-flow.md) |
| Output format examples (`overnight-plan.md`, `session.json`) | [output-format-examples.md](${CLAUDE_SKILL_DIR}/references/output-format-examples.md) |
| Success criteria checklists for `/overnight` and `/overnight resume` | [success-criteria.md](${CLAUDE_SKILL_DIR}/references/success-criteria.md) |

Read **only** the reference for the flow you are in. Do not preload all references.

## Invocation

- `/overnight` -- start a new overnight session (select features, build plan, launch)
- `/overnight resume` -- resume an interrupted overnight session or view results
- `/overnight status` -- check the status of a running or recent overnight session

## Input Validation

Validate inputs before entering any flow:

| Input | Type | Valid Values | Error Response |
|-------|------|-------------|----------------|
| `time-limit` | string | `\d+(\.\d+)?h` (e.g., `6h`, `8h`, `1.5h`) | "Invalid time-limit format '{value}'. Expected hours, e.g. '6h'." → stop |

**Precondition checks** (fail fast before any backlog reads):

- **Git repository**: `.git/` must exist in the current directory. If missing: "Not a git repository root. Run `/overnight` from the repository root." → stop.
- **Backlog directory**: `backlog/` must exist. If missing: "No backlog directory found. Run from the project root." → stop.
- **Command variant**: Only `overnight`, `overnight resume`, and `overnight status` are valid. Unknown variants (e.g., `/overnight foobar`) should report: "Unknown subcommand '{variant}'. Use `/overnight`, `/overnight resume`, or `/overnight status`." → stop.

## New Session Flow (`/overnight`)

Operational sequence — execute in order. Full per-step detail (error handling, sub-steps, function signatures) lives in `${CLAUDE_SKILL_DIR}/references/new-session-flow.md`.

1. **Check for existing session** — `load_state()` from `cortex_command.overnight.state`. If a non-`complete` session exists, offer resume or abandon.
2. **Pre-selection index regeneration** — run `cortex-generate-backlog-index`, stage `backlog/index.json` and `backlog/index.md`, commit if changed.
3. **Select eligible features** — `select_overnight_batch()` from `cortex_command.overnight.backlog`. Eligibility requires `lifecycle/{slug}/research.md` and `lifecycle/{slug}/spec.md` on disk and `type != epic`. Missing `plan.md` is generated during the session.
4. **Present selection summary** — `selection.summary` shows eligible items, batches, and ineligible items with reasons.
5. **Render session plan** — `render_session_plan(selection, time_limit_hours=6)` from `cortex_command.overnight.plan`.
6. **Unified plan + spec review** — display rendered plan, then each `lifecycle/{slug}/spec.md` inline. Prompt for `[A]pprove / [R]emove / [T]ime-limit / [Q]uit`. Re-render on Remove/Time-limit.
7. **Launch** — on approval, in order:
   - 7.0 `validate_target_repos(selection)` — stop if any repo path is invalid.
   - 7.1 Pre-flight: block on uncommitted `lifecycle/` or `backlog/` files; offer `/commit`.
   - 7.2 `bootstrap_session(selection, plan_content)` — writes `overnight-state.json`, `overnight-plan.md`, `session.json`; creates worktree at `$TMPDIR/overnight-worktrees/{session_id}/` on branch `overnight/{session_id}`.
   - 7.3 `latest-overnight` symlink — deferred to runner startup.
   - 7.4 `extract_batch_specs(state, worktree_path)` — stage and commit returned paths on the integration branch.
   - 7.5 `log_event(event='session_start', round=1, ...)` from `cortex_command.overnight.events` (lowercase event names; param is `event`, not `event_type`).
   - 7.6 Launch dashboard if not running; poll `localhost:8080/health`. Dashboard is optional.
   - 7.7 Ask run-now vs. schedule-for-later. Run via Bash with `dangerouslyDisableSandbox: true`:
     - Run now: `overnight-start $CORTEX_COMMAND_ROOT/lifecycle/sessions/{session_id}/overnight-state.json 6h`
     - Schedule: `cortex overnight schedule <target-time> --state $CORTEX_COMMAND_ROOT/lifecycle/sessions/{session_id}/overnight-state.json`
   - 7.8 Inform the user; the runner takes over from here.

## Resume Flow (`/overnight resume`)

Operational sequence — full per-step detail in `${CLAUDE_SKILL_DIR}/references/resume-flow.md`.

1. **Load existing state** — scan `$CORTEX_COMMAND_ROOT/lifecycle/sessions/*/overnight-state.json` by mtime; load the first non-`complete` file via `load_state(state_path=<path>)`.
2. **Report session state** — phase, per-feature statuses, rounds completed, current round. When `phase: paused`, surface `paused_reason` with contextual guidance.
3. **Check for deferred questions** — `read_deferrals()` + `summarize_deferrals()` from `cortex_command.overnight.deferral`.
4. **Determine next action** based on phase:

   | Phase | Options |
   |-------|---------|
   | `executing` | Resume execution, or view current progress |
   | `paused` | Address cause (deferred questions, failures), then resume |
   | `complete` | Direct user to `lifecycle/morning-report.md` |
   | `planning` | Should not occur. Offer to restart. |

5. **Act on user choice** — resume runs the same `overnight-start` command as 7.7 above (Bash with `dangerouslyDisableSandbox: true`).

## Status Flow (`/overnight status`)

Run `overnight-status` (the deployed script) and present its output to the user. If the command is not found, instruct the user to install the `cortex-core` plugin.

## Success Criteria

Detailed checklists for `/overnight` and `/overnight resume` outcomes live in `${CLAUDE_SKILL_DIR}/references/success-criteria.md`. The high-level shape:

- New session: plan, state, and manifest written into `lifecycle/sessions/{session_id}/`; integration branch created; runner launched; `session_start` logged.
- Resume: state reported; deferred questions surfaced; phase-appropriate next action offered.

## Output Format Examples

Templates for `overnight-plan.md` and `session.json` live in `${CLAUDE_SKILL_DIR}/references/output-format-examples.md`.

## Overnight vs Pipeline vs Lifecycle

The three orchestration skills are complementary:

- **Lifecycle** (`/lifecycle`): Interactive single-feature development. User present throughout all phases.
- **Pipeline** (`/pipeline`): Batch multi-feature orchestration with an interactive front-end (research, spec, plan) and an execution back-end. User participates in planning, then execution runs autonomously.
- **Overnight** (`/overnight`): Fully autonomous overnight execution of features that already have research and spec artifacts. No interactive research or spec phases -- features must be ready (have completed discovery) before selection. The skill handles plan approval, then hands off entirely to the runner.

The key difference: pipeline creates research and specs interactively during the session; overnight requires them to already exist (produced by `/discovery` or `/lifecycle` earlier).

## Constraints

- **Do not contain implementation code.** This skill is a protocol that the agent follows. It references functions by their module paths (`cortex_command.overnight.backlog`, `cortex_command.overnight.plan`, `cortex_command.overnight.state`, `cortex_command.overnight.events`, `cortex_command.overnight.deferral`).
- **One overnight session at a time.** If a session is active (non-complete state file), the user must resume or abandon it before starting a new one.
- **Features must have `lifecycle/{slug}/research.md` and `lifecycle/{slug}/spec.md` on disk, and must not be `type: epic` (checked after blocked-by, before artifact checks).** The readiness gate in `select_overnight_batch()` enforces this. Features without all required artifacts are reported as ineligible with a reason. `plan.md` is generated during the session if missing — a plan generation sub-agent runs before dispatch and defers the feature (with a captured reason) if it cannot produce a valid plan.
- **The skill does not execute features.** It creates the plan and state, then hands off to the runner. The runner and batch runner handle actual execution.
- **Overnight features do not merge directly to main.** They merge to the session's integration branch (`overnight/{session_id}`). The runner opens a single PR from the integration branch to main at session end, containing all overnight changes for review.
- **Session plan is immutable after approval.** Once written to the session directory (`lifecycle/sessions/{session_id}/overnight-plan.md`), the plan does not change. Runtime state lives in `lifecycle/sessions/{session_id}/overnight-state.json`.
- **Parallel agent dispatch uses `Agent isolation: "worktree"`.** When launching features in parallel, always use the `Agent` tool with `isolation: "worktree"`. Do not call `git worktree add` manually — in sandboxed sessions this fails because `.claude/worktrees/` is Seatbelt-restricted, and a failed checkout leaves an orphaned branch requiring `git branch -d <name>` cleanup before retrying.
