---
schema_version: "1"
uuid: 5e36f351-6787-4ab8-910f-3d6c3dad3325
title: "Extract /dev epic-map parse into bin/build-epic-map"
status: backlog
priority: medium
type: feature
parent: "101"
blocked-by: ["102", "103"]
tags: [harness, scripts, dev]
created: 2026-04-21
updated: 2026-04-21
discovery_source: research/extract-scripts-from-agent-tool-sequences/research.md
---

# Extract /dev epic-map parse into bin/build-epic-map (C4)

## Context from discovery

`/dev` Step 3a/3b (`skills/dev/SKILL.md:135-166`) normalizes the parent field (quote strip, UUID skip, integer match) across `backlog/index.json` entries and builds an epic→children map. Parent-field normalization is purely mechanical; the downstream Step 3c decision tree (children's `status`/`spec`/`in_progress`/`review`/`blocked` flags → workflow recommendation) stays inline.

## Research context

- C4 in `research/extract-scripts-from-agent-tool-sequences/research.md`.
- Determinism: MECHANICAL-PARSE, judgment downstream.
- Heat: warm.
- Net SKILL.md line count may not shrink meaningfully; Step 3c's decision tree remains inline.

## Scope

- New `bin/build-epic-map` emitting `{epic_id: {children: [...], status, refined}}` JSON.
- Deploy via `just deploy-bin`.
- Update `skills/dev/SKILL.md` Steps 3a/3b to invoke the script; remove inline normalization logic.

## Out of scope

- Step 3c decision tree (remains agent-driven).
