---
schema_version: "1"
uuid: d54e86bc-93ec-4cbb-a68e-d98ff705cb00
title: 'Config-driven backlog backend: resolver, local/none routing, overnight safety'
status: complete
priority: high
type: feature
created: 2026-06-23
updated: 2026-06-24
parent: "315"
tags: ['backlog-optional-plugin']
discovery_source: cortex/research/backlog-optional-plugin/research.md
lifecycle_phase: research
lifecycle_slug: config-driven-backlog-backend-resolver-local
complexity: complex
criticality: high
spec: cortex/lifecycle/config-driven-backlog-backend-resolver-local/spec.md
areas: ['backlog']
---
## Why

Even with the management skill made optional, every consumer still hard-codes the local backlog, and the cortex init config offers no way to say "this repo uses a different tracker" or "do not manage tickets here." A user on an external tracker has no switch to flip.

## Role

Introduce the configurable-backend seam and wire the consumers that work without any external tracker. Add a config-resolution helper that answers "which backlog backend is active" from the cortex init config (defaulting to the local backend), a config block where the user declares the backend and free-form driving instructions, and the backend branch in each interactive consumer for the local and none arms. Install the overnight safety guard, and record the architectural decision. After this lands, a user can set the backend to none to stop cortex touching any tracker, the local backend keeps working by default, and overnight refuses to run against a non-local backend.

## Integration

Consumers read the active backend through a new console-script binstub, mirroring how they already read the commit-artifacts and branch-mode config flags from prose. The resolver lives alongside the existing config readers and reuses the shared frontmatter extractor; overnight calls the same helper rather than growing a third config parser. The config block is added to the init scaffold template, which is hash-tracked. The decision is recorded in a new ADR that the consumers and the requirements doc back-point to.

## Edges

- Backend resolution is config-authoritative and must not introspect installed plugins; an absent config block resolves to the local backend so existing repos are unchanged.
- Backend branching lives in the skill and consumer layer; the backlog console-script tools stay local-only and must not grow backend awareness.
- Routing prose must use soft positive-routing phrasing, not MUST or REQUIRED escalation, per the harness escalation policy.
- The overnight guard is a structural first-check on the unattended path and must never allow an external-tracker write; its resolved-backend variable must not collide with the existing launchd scheduler-backend name.
- The slash-rename of the moved management command must touch only live files and must not rewrite historical lifecycle or research artifacts. The rename sub-step assumes the plugin extraction is already merged — an internal ordering note, not a separate cross-ticket dependency.
- Structural consumers that read the local index directly (dev's epic map, refine's parent-epic alignment) degrade to a clear advisory under external or none rather than silently producing wrong guidance.

## Touch points

- cortex_command/lifecycle_config.py:29-46 (shared frontmatter extractor), cortex_command/lifecycle_config.py:49-140 (existing reader pattern to mirror)
- cortex_command/lifecycle/branch_mode_cli.py (CLI-module pattern for the new cortex-read-backlog-backend binstub)
- cortex_command/init/templates/cortex/lifecycle.config.md (new backlog: block), cortex_command/init/scaffold.py:69 (bump the init-artifacts hash input)
- skills/lifecycle/references/backlog-writeback.md:45-62, skills/discovery/references/decompose.md:138, skills/refine/SKILL.md:79, cortex_command/refine.py:35-85, skills/dev/SKILL.md:137-166, skills/morning-review/references/walkthrough.md:538
- cortex_command/overnight/cli_handler.py:2005 and :2078 (refusal-guard insertion in handle_prepare/handle_launch), cortex_command/overnight/cli_handler.py:74-114 (read_synthesizer_gate precedent)
- cortex/adr/ (new ADR-0015: configurable backlog backend + LLM-as-adapter)