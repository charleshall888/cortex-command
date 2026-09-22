---
name: overnight
description: Plan and launch an unattended overnight session — pick refined features, approve the plan, hand off to the runner. Use for "/overnight", "overnight resume", or "overnight status".
disable-model-invocation: true
---

# Overnight

Plan and approve the session here. The runner does the work (`docs/overnight-operations.md`). One session at a time.

A feature needs `research.md` and `spec.md` (from `/cortex-core:refine`) and must not be `type: epic`. A missing `plan.md` is written in-session. The approved plan never changes; live state is in `overnight-state.json`. Work merges to `overnight/{session_id}`, and the runner opens one PR to main at session end.

Read only the flow you are in.

## New Session Flow (`/overnight`)

Follow [new-session-flow.md](${CLAUDE_SKILL_DIR}/references/new-session-flow.md): guard, prepare, curate and approve, launch now or on a schedule. Only the runner logs `session_start`.

## Resume Flow (`/overnight resume`)

Follow [resume-flow.md](${CLAUDE_SKILL_DIR}/references/resume-flow.md).

## Status Flow (`/overnight status`)

Run `cortex overnight status` and show the output.

Any other subcommand → "Unknown subcommand '{variant}'. Use `/overnight`, `/overnight resume`, or `/overnight status`." and stop. An optional time limit must match `\d+(\.\d+)?h` (e.g. `6h`); else → "Invalid time-limit format '{value}'. Expected hours, e.g. '6h'." and stop.
