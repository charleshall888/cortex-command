---
schema_version: "1"
uuid: 39d5d66b-3ac3-4459-a07d-601417b9f613
id: 013
title: "Wire requirements drift check into lifecycle review"
type: chore
status: backlog
priority: medium
parent: 009
blocked-by: [011]
tags: [requirements, lifecycle, process]
created: 2026-04-03
updated: 2026-04-03
discovery_source: research/requirements-audit/research.md
---

# Wire requirements drift check into lifecycle review

## Context from discovery

Requirements drift is universal in AI-assisted development, and no reviewed tool has automated detection — it's a workflow discipline problem. The practical fix is to make requirements accuracy a required output of the lifecycle review phase, not an afterthought.

Currently, lifecycle review completes without any requirements check. The four major omissions in project.md (dashboard, conflict pipeline, deferral system, model selection) accumulated before project.md existed, but the forward risk is that new features built through lifecycle will drift in the same way.

Research finding: "Asking 'did anything drift?' is insufficient — the review phase must either update requirements or explicitly log 'no drift detected.'" An advisory prompt repeats the same soft enforcement that allows drift to accumulate.

## Scope

Add a `requirements_drift` field to the lifecycle review artifact. The review phase must produce one of:
- `requirements_drift: none` — explicit statement that implementation matched requirements
- `requirements_drift: [list of changes]` — describes what drifted, with a pointer to the updated requirements file or a note that a requirements update is needed

The check should:
- Load the relevant project and area requirements docs during review
- Compare implementation against stated requirements
- Produce the `requirements_drift` field as a required section of the review artifact
- In overnight/autonomous contexts: write drift findings to the morning report rather than stalling
