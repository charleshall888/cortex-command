---
name: overnight
description: Plan and launch an unattended overnight session — pick refined features, approve the plan, hand off to the runner. Use for "/overnight", "overnight resume", or "overnight status".
disable-model-invocation: true
---

# Overnight

Plan and approve here; the runner executes (`docs/overnight-operations.md`). One session at a time. Features need `research.md` and `spec.md` on disk (from `/cortex-core:refine`) and must not be `type: epic`; a missing `plan.md` is generated in-session. The approved plan is immutable — runtime state lives in `overnight-state.json`. Work merges to `overnight/{session_id}`; the runner opens one PR to main at session end.

Read only the flow you are in.

## New Session Flow (`/overnight`)

Follow [new-session-flow.md](${CLAUDE_SKILL_DIR}/references/new-session-flow.md): guard, prepare, curate and approve, launch (run now or schedule; the runner alone logs `session_start`, at fire time).

## Resume Flow (`/overnight resume`)

Follow [resume-flow.md](${CLAUDE_SKILL_DIR}/references/resume-flow.md).

## Status Flow (`/overnight status`)

Run `cortex overnight status` and relay it.

Any other subcommand → "Unknown subcommand '{variant}'. Use `/overnight`, `/overnight resume`, or `/overnight status`." and stop. An optional time limit must match `\d+(\.\d+)?h` (e.g. `6h`); otherwise "Invalid time-limit format '{value}'. Expected hours, e.g. '6h'." and stop.
