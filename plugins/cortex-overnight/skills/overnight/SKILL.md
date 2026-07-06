---
name: overnight
description: Plan and launch autonomous overnight development sessions. Selects eligible backlog features, presents a session plan for approval, and hands off to the runner for unattended execution. Use when user says "/overnight", "start overnight session", "launch overnight", or wants to run features autonomously overnight.
disable-model-invocation: true
inputs:
  - "time-limit: string (optional) — Maximum wall-clock duration for the overnight session (e.g. '6h'). Passed as --time-limit to the runner."
outputs:
  - "cortex/lifecycle/sessions/{SESSION_ID}/overnight-plan.md — selected session plan with feature list"
  - "cortex/lifecycle/sessions/{SESSION_ID}/overnight-state.json — execution state for the runner"
  - "cortex/lifecycle/sessions/{SESSION_ID}/session.json — session manifest (type, id, started, features)"
  - "cortex/lifecycle/sessions/{SESSION_ID}/overnight-events.log — session events log"
  - "cortex/lifecycle/sessions/{SESSION_ID}/morning-report.md — session morning report"
  - "cortex/lifecycle/sessions/latest-overnight — symlink to the current session directory"
preconditions:
  - "cortex/lifecycle/{slug}/spec.md exists for each candidate feature"
  - "cortex/backlog/NNN-slug.md files exist with status: refined"
  - "Run from project root"
---

# Overnight Session Planning

Interactive entry point for overnight autonomous orchestration — guides the user through selecting features from the backlog, reviewing a session plan, and launching execution. The skill handles planning and approval; execution is delegated to the runner.

For the canonical round-loop and orchestrator behavior the runner implements after launch, see `docs/overnight-operations.md`.

## References

Detailed step procedures, worked examples, and success-criteria checklists are extracted to references:

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

Validate before entering any flow:

| Check | Requirement | Error Response |
|-------|-------------|-----------------|
| `time-limit` | matches `\d+(\.\d+)?h` (e.g., `6h`, `1.5h`) | "Invalid time-limit format '{value}'. Expected hours, e.g. '6h'." → stop |
| Git repository | `.git/` exists in the cwd | "Not a git repository root. Run `/overnight` from the repository root." → stop |
| Backlog directory | `cortex/backlog/` exists | "No backlog directory found. Run from the project root." → stop |
| Command variant | one of `overnight`, `overnight resume`, `overnight status` | "Unknown subcommand '{variant}'. Use `/overnight`, `/overnight resume`, or `/overnight status`." → stop |

## New Session Flow (`/overnight`)

Full per-step detail (error handling, sub-steps, function signatures) lives in `${CLAUDE_SKILL_DIR}/references/new-session-flow.md`. Execute in order:

1. **Check for existing session** — offer resume or abandon if a non-`complete` session is active.
2. **Regenerate the backlog index** — `cortex-generate-backlog-index` (gitignored cache; not staged or committed).
3. **Select eligible features** — `cortex overnight prepare` groups items with `research.md` and `spec.md` on disk and `type != epic`; missing `plan.md` is generated during the session.
4. **Present the selection summary** — eligible items, batches, ineligible items with reasons.
5. **Render the session plan** — `cortex overnight prepare --format json` (read-only).
6. **Unified plan + spec review** — display the plan and each active spec inline; triage suitability once, on first entry, into three pools: active (runs), suitability set-aside (excluded by default, re-addable), hard-ineligible (display-only). Re-display all pools before every approval prompt: `[A]pprove / [R]emove / [I]nclude-set-aside / [T]ime-limit / [Q]uit`. Full triage rubric and re-add semantics in the reference.
7. **Launch** — on approval, in order:
   - 7.1 Pre-flight: block on uncommitted `cortex/lifecycle/` or `cortex/backlog/` files; offer `/commit`.
   - 7.2 `cortex overnight launch --format json --only <active slugs>` (must be exactly the approved active pool) — bootstraps the session; capture `state_path`, `worktree_path`, `extracted_specs` from the envelope.
   - 7.3 `latest-overnight` symlink — deferred to runner startup.
   - 7.4 Stage + commit `extracted_specs` (if any) on the integration branch.
   - 7.5 No `session_start` log here — deferred to the run-now branch (7.7); the runner is the sole fire-time author.
   - 7.6 Launch the dashboard if not already running (optional).
   - 7.7 Ask run-now vs. schedule-for-later, via Bash with `dangerouslyDisableSandbox: true`:
     - Run now: log `session_start` first, then `cortex overnight start --state {state_path} --time-limit 21600`.
     - Schedule (no prep-time log): `cortex overnight schedule <target-time> --state {state_path}`.
   - 7.8 Inform the user; the runner takes over.

## Resume Flow (`/overnight resume`)

Full per-step detail in `${CLAUDE_SKILL_DIR}/references/resume-flow.md`.

1. **Load existing state** — most-recent non-`complete` `overnight-state.json` under `cortex/lifecycle/sessions/`.
2. **Report session state** — phase, per-feature statuses, rounds completed, current round; surface `paused_reason` when `phase: paused`.
3. **Check for deferred questions** — via `cortex_command.overnight.deferral`.
4. **Determine next action** — depends on phase (`executing` / `paused` / `complete` / `planning`); full table in the reference.
5. **Act on user choice** — resume runs the same `cortex overnight start` command as 7.7 above.

## Status Flow (`/overnight status`)

Run `overnight-status` (the deployed script) and present its output to the user. If the command is not found, instruct the user to install the `cortex-core` plugin.

## Success Criteria

Detailed checklists for `/overnight` and `/overnight resume` outcomes live in `${CLAUDE_SKILL_DIR}/references/success-criteria.md`. The high-level shape:

- New session: plan, state, and manifest written into `cortex/lifecycle/sessions/{session_id}/`; integration branch created; runner launched; `session_start` logged.
- Resume: state reported; deferred questions surfaced; phase-appropriate next action offered.

## Output Format Examples

Templates for `overnight-plan.md` and `session.json` live in `${CLAUDE_SKILL_DIR}/references/output-format-examples.md`.

## Overnight vs Pipeline vs Lifecycle

Complementary orchestration skills: **Lifecycle** (`/lifecycle`) is interactive single-feature development, user present throughout. **Pipeline** (`/pipeline`) is batch orchestration — interactive front-end (research, spec, plan), autonomous execution back-end. **Overnight** (`/overnight`) is fully autonomous execution of features whose research and spec artifacts already exist (from `/discovery` or `/lifecycle`) — no interactive research/spec phase; handles plan approval, then hands off entirely to the runner.

## Constraints

- **Protocol only, no implementation code.** References functions by module path: `cortex_command.overnight.{backlog,plan,state,events,deferral}`.
- **One overnight session at a time** — an active (non-complete) session must be resumed or abandoned before starting a new one.
- **Features must have `research.md` and `spec.md` on disk and must not be `type: epic`** (eligibility detail in new-session-flow.md Step 3). Missing `plan.md` is generated during the session — a plan sub-agent runs before dispatch and defers the feature (with a reason) if it cannot produce one.
- **The skill does not execute features.** It creates the plan and state, then hands off to the runner.
- **Overnight features merge to the session's integration branch** (`overnight/{session_id}`), not directly to main. The runner opens a single PR to main at session end covering all changes.
- **Session plan is immutable after approval** — once written to `overnight-plan.md`, it does not change. Runtime state lives in `overnight-state.json`.
- **Parallel agent dispatch uses `Agent isolation: "worktree"`.** Same-repo worktrees resolve to `<repo>/.claude/worktrees/{feature}/` via `cortex-worktree-resolve` — repo-relative, under the project's trust scope, no per-shell sandbox registration needed. The `.mcp.json` sandbox deny is filename-scoped and does not block `git worktree add`. A failed checkout leaves an orphaned branch — clean up with `git branch -d <name>` before retrying.
