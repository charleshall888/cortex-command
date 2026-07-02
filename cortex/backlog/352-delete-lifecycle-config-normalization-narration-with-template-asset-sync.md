---
schema_version: "1"
uuid: 0604375c-04bf-4ea3-914d-e4a01676f732
title: Delete lifecycle config normalization narration with template-asset sync
status: backlog
priority: low
type: chore
tags: ['skill-value-scorecard']
areas: [skills, lifecycle]
discovery_source: cortex/research/skill-value-scorecard/report.html
created: 2026-07-02
updated: 2026-07-02
parent: "347"
---
## Why
The normalization-rules section of the lifecycle config file narrates parser mechanics — case handling, whitespace stripping, duplicate-key last-wins, invalid-value fall-through — that the config parser module enforces and its tests cover individually, with typos degrading fail-safe to the picker plus a stderr warning. The audit verified the deletion through all three lenses: no consumer needs the prose to act correctly and no test pins the file body. It scored value 1 at 920 weighted tokens, the single worst value-per-token section in the corpus.

## Role
Delete the section from the scaffolded config and keep the three copies of this content in sync: the repo instance, the init template, and the skill asset — the 335 reconcile work added parity gates between them, so a one-sided edit will trip the gate rather than drift silently.

## Integration
Verify which of the three copies is canonical for the parity gate and edit in the direction the gate reconciles (asset from init-template per 335). The section birth commit predates the parser landing; the prose was written as a spec for code that now exists and is tested.

## Edges
- Frontmatter byte-slice parity gate from 335 must stay green.
- Fresh cortex-init scaffolds must produce the trimmed file, not resurrect the section.

## Touch points
- cortex/lifecycle.config.md (repo instance)
- the cortex-init template and skills/lifecycle/assets/lifecycle.config.md
- plugins/cortex-core mirror (same commit)
- cortex/research/skill-value-scorecard/master_candidates.json (verdict source)