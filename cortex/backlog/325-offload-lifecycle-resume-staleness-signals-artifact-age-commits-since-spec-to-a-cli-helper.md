---
schema_version: "1"
uuid: 7fcb306e-9425-48e5-af96-fb498670e435
title: Offload lifecycle resume-staleness signals (artifact age, commits-since-spec) to a CLI helper
status: complete
priority: low
type: chore
created: 2026-06-25
updated: 2026-06-25
---
## Why

lifecycle `SKILL.md` Step 2 (Register session → resume offer) asks the agent to compute two staleness signals by hand: relative age of `spec.md`/`plan.md`, and "count of commits touching spec-named files since spec mtime." The second is a git query the model must construct on the hot path — deterministic work that belongs in code. The signals themselves are load-bearing (a stale spec is a real drift failure on resumed lifecycles); only the computation should move. Surfaced in the 2026-06-25 lifecycle skill-trimming audit.

## Role

A small helper — a new `cortex-*` verb or an addition to `detect-phase` / `cortex-lifecycle-state` — emits `{spec_age_days, plan_age_days, commits_since_spec}` deterministically. The SKILL.md prose collapses to roughly one line: "On resume, surface the staleness fields from <command> above the continue/restart offer; non-blocking, default continue."

## Integration

New or extended `cortex_command` surface + console-script entry → lifecycle-gated. Keep the non-blocking semantics and the "default continue" behavior in prose — those are behavioral guards the CLI cannot carry.

## Edges

- No `plan.md` present → `plan_age_days` null/omitted, not an error.
- Pin the "spec-named files" definition in the helper so it matches the prose's intent (spec.md plus whatever the spec governs).
- Git-less / shallow-clone repos → degrade gracefully (omit `commits_since_spec`, never hard-fail the resume).

## Touch-points

- new or extended `cortex_command` module + console-script entry
- `skills/lifecycle/SKILL.md` Step 2 resume block (+ mirror)
- test for the helper