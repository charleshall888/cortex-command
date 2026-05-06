---
schema_version: "1"
uuid: 067e739f-eda7-4ea6-88c9-c4c76e219e68
title: "Clarify-critic schema validator + warning-template runtime validator (per #178 R7 follow-on)"
type: feature
status: proposed
priority: medium
parent: 178
blocked-by: []
tags: [oq3, schema-validator, clarify-critic, follow-on, events-log]
created: 2026-05-06
updated: 2026-05-06
complexity: simple
criticality: medium
areas: [skills, hooks]
---

# Clarify-critic schema validator + warning-template runtime validator

Filed per #178 R7 as the structural mitigation for the OQ3 soften applied to `skills/refine/references/clarify-critic.md` MUST/REQUIRED imperatives at lines 26, 155, and 159. The CLAUDE.md text itself anticipates this validator: "neither is programmatically validated in this version, but a future ticket may add a validator covering both."

## Context from #178

#178 softened 3 prose MUSTs in `clarify-critic.md` to declarative-behavioral phrasing per OQ3 default, since CLAUDE.md's closed evidence list (events.log F-row OR commit-linked transcript URL) was not satisfied for any of them. The softening shipped without a co-landing gate — this ticket files the mitigation that makes the now-implicit invariants enforceable programmatically.

## What to land

### 1. Schema validator for `events.log` post-feature events

Validates two invariants on every post-feature event written to `lifecycle/{feature}/events.log`:

- **Dismissals invariant**: `len(dismissals) == dispositions.dismiss`. Replaces the prose contract previously enforced by line 155's REQUIRED imperative.
- **Cross-field invariant**: any post-feature event whose `findings[]` contains at least one item with `origin: "alignment"` has `parent_epic_loaded: true`. Replaces the prose contract previously enforced by line 159's MUST imperative.

Implementation surface: a Python check that runs as a pre-commit hook or as part of a periodic events.log lint pass. The validator should fail loudly with a pointer to the violating event line.

### 2. Warning-template runtime validator

Validates that the orchestrator's user-facing warnings on the `missing` / `unreadable` parent-epic branches use one of the two allowlist templates from `skills/refine/references/clarify-critic.md` and do not echo raw filesystem error text or helper stderr output. Replaces the closed-allowlist enforcement previously expressed by line 26's MUST imperative.

Implementation surface: runtime check inside the orchestrator's warning-emission path, OR a static check that scans the orchestrator's emit-warning call sites for allowlist-template usage.

## Touch points

- `cortex_command/` — new validator module (location TBD by implementation)
- `hooks/` or `claude/hooks/` — pre-commit invocation if the validator runs at commit time
- `skills/refine/references/clarify-critic.md` — once the validator lands, append a one-line note that the prose contracts at lines 26, 155, 159 are now programmatically enforced

## Verification

- A post-feature event with `len(dismissals) != dispositions.dismiss` causes the validator to fail with a pointer to the line.
- A post-feature event with `findings[*].origin == "alignment"` and `parent_epic_loaded: false` causes the validator to fail.
- A warning emitted on the `missing` branch with raw filesystem error text causes the runtime validator to fail.
- All three above fail closed (non-zero exit) and emit a diagnostic message identifying the invariant violated.

## Risks

- The validator could be too eager and flag historical events that pre-date the invariant. Mitigation: gate on `schema_version` if events.log has versioned entries; otherwise scope the validator to events written after this ticket lands.
- The warning-template runtime validator may be hard to test without the actual missing/unreadable failure modes. Mitigation: exercise the templates via injected fault-test fixtures.
