---
schema_version: "1"
uuid: 417cdff6-c766-42da-9936-3d9e01c69ac0
title: "Make cortex-update-item accept --flag value syntax for consistency with sibling CLIs"
status: complete
priority: low
type: chore
created: 2026-05-20
updated: 2026-05-25
tags: [harness, cli, skill-authoring]
discovery_source: cortex/research/harness-friction-triage/research.md
session_id: 4e0f0814-7d4c-4551-b965-7a5306917c41
lifecycle_phase: research
lifecycle_slug: make-cortex-update-item-accept-flag
complexity: complex
criticality: high
spec: cortex/lifecycle/make-cortex-update-item-accept-flag/spec.md
areas: [skills]
---
## Why

`cortex-update-item <slug> key=value [key=value ...]` uses key=value positional arguments, while every other `cortex-*` CLI in the project (`cortex-create-backlog-item`, `cortex-resolve-backlog-item`, `cortex-discovery`, `cortex-critical-review`, etc.) uses the `--flag value` argparse convention. Skill prose and operator muscle memory default to the `--flag value` form, which fails with `Invalid argument (expected key=value): --status`. Hit live during the harness-friction-triage discovery session when resetting #209 status (needed two attempts; first used `--status refined`).

## Role

Reshape `cortex-update-item` to accept the `--flag value` syntax (potentially keeping `key=value` as a deprecated form during a transition window, or replacing outright if no consumers depend on it).

## Integration

The argparse signature change is local; consumers are skill prose that references the CLI by example and operators invoking it interactively. `cortex-check-parity` and a future skill-prose contract lint (ticket 253) would catch any consumer that still uses the old form.

## Edges

- Breaks if any in-repo caller pipes structured input expecting the key=value parsing.
- Behavior change observed by humans muscle-memoried on the old syntax; transition period worth considering.
- Symptom of the broader pattern (skill-prose-vs-CLI-surface drift) the harness-friction-triage discovery surfaced; ships independently of that work.

## Touch points

- `cortex_command/backlog/update_item.py` (argparse setup)
- Skill prose referencing `cortex-update-item` calls (grep before changing the CLI to flag any callers needing migration)
- `cortex/research/harness-friction-triage/research.md` (discovery context — friction surfaced during cleanup)