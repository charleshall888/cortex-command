---
schema_version: "1"
uuid: f5fac405-3dc4-4d4f-b147-3c8084614ea4
title: Add --field to cortex-lifecycle-event and route the hand-written event sites through it
status: backlog
priority: low
type: chore
created: 2026-06-25
updated: 2026-06-26
parent: 336
---
## Why

**12 reference files hand-write raw `{"event":...}` NDJSON** for `events.log`, while `cortex-lifecycle-event` (`cortex_command/lifecycle_event.py`) already exists and does atomic append + schema validation + ISO-8601 timestamping — yet only `implement.md` uses it. Hand-rolled timestamps and inline JSON invite schema drift and are deterministic work narrated for the model. The blocker is that several events carry extra fields the current verb may not accept (`pr_opened`→number/url/repo, `feature_complete`→tasks_total/rework_cycles, `plan_comparison`→disposition, `drift_protocol_breach`→retries). Surfaced in the 2026-06-25 lifecycle reference-file audit; **highest-leverage offload — the infrastructure already exists.**

## Role

Extend `cortex-lifecycle-event log` to accept arbitrary `--field k=v` pairs (typed where needed), then replace the raw JSON blocks at the **inline-emitted** sites with verb invocations. The references keep only the event name and the inputs to pass — the verb owns shape, ordering, and timestamping. (Scope split below: the complete / post-refine / wontfix events are absorbed by their own verbs in #331 and #329, not migrated here.)

## Integration

Edits `cortex_command/lifecycle_event.py` + the inline-emitted reference files across `skills/lifecycle/` (and 2 in `skills/refine/`) (+ mirrors) → lifecycle-gated. **Scope split to avoid double-touching**: this ticket migrates only the sites that stay inline-emitted — plan, review, criticality-matrix, critical-review-gate, refine-delegation, backlog-writeback, implement's extras, and refine's clarify-critic / specify. The complete and post-refine-commit events move into #331's new verbs, and the wontfix event into #329's verb — not migrated here. **PIN the byte-identical-output invariant**: emitted rows must be byte-for-byte identical to today's hand-written rows (key names, field order, timestamp format), since `detect-phase` / `state_cli` / the morning report parse them. Add a round-trip test asserting identical rows for each migrated event type. Foundation for #331 and #332, which emit their events through this verb.

## Edges

- Consumers parse by key, but pin field ordering anyway to avoid a silent diff.
- Distinguish genuinely-deterministic sites (offload) from any that compute a field by judgment (keep the computation in prose; pass the result as `--field`).
- refine's 2 sites (`clarify-critic.md`, `specify.md`) cross the skill boundary — confirm the verb resolves the same `events.log` path when invoked from refine.

## Touch-points

- `cortex_command/lifecycle_event.py` + tests
- the inline-emitted reference files: plan, review, criticality-matrix, critical-review-gate, refine-delegation, backlog-writeback, implement (extras), + refine's clarify-critic / specify (+ mirrors)
- complete / post-refine-commit / wontfix events are excluded here — handled by #331 and #329
- coordinate file-overlap with #332 (implement extras)