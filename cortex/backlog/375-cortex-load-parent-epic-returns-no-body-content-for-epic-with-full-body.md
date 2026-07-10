---
schema_version: "1"
uuid: 991d9fc4-3c6d-4f76-87bf-7cda5186c6c5
title: cortex-load-parent-epic returns no body content for epic with full body
status: backlog
priority: medium
type: bug
created: 2026-07-10
updated: 2026-07-10
areas: ['backlog']
---
## Why

During item 373's clarify-critic dispatch (2026-07-10), `cortex-load-parent-epic 373-build-the-verb-completion-composition-wrapper-verbs-generated-pauses-shared-overnight-reducer` returned `{"status": "loaded", "parent_id": 371, "body": "(no body content)"}` while `cortex/backlog/371-cli-served-lifecycle-state-machine-phased-verb-completion-with-a-gated-loop.md` carries a full Why/Role/Integration/Edges body on disk. The critic's parent-epic alignment sub-rubric silently evaluated against an empty body — a genuinely divergent epic would have passed unchallenged.

## Role

The helper reports the epic body it actually loaded, or a distinguishable error state, so the alignment sub-rubric either gets real content or is explicitly skipped with a warning.

## Touch points

- `cortex_command` parent-epic loader consumed by `skills/refine/references/clarify-critic.md` (Parent Epic Loading section)
- Epic 371 file as the reproduction case