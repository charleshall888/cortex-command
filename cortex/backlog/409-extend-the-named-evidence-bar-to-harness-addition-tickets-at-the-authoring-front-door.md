---
schema_version: "1"
uuid: 7c7ae6da-4b1b-4a5c-97ff-01f37d3a147b
title: Extend the named-evidence bar to harness-addition tickets at the authoring front door
status: complete
priority: medium
type: feature
created: 2026-07-21
updated: 2026-07-21
tags: ['token-efficiency', 'backlog', 'governance']
areas: ['skills']
---
## Why

Efficiency-framed tickets keep landing as net additions: the 2026-07-16 four-agent audit found #382, #389, #390, and #392 all grew the harness while claiming to shrink it, and nothing at ticket-authoring time asks an author to name the evidence behind an addition or state its expected net effect. The evidence bar exists — the enforcement-gates constraint applies it to gates and Deletion bias applies it to keeps — but the front door where tickets are born carries no trace of it.

## Role

The canonical body template carries an Evidence rule in its Why section: a ticket adding harness machinery names specific evidence (measured cost or observed failure, not a hypothetical), and an efficiency-framed ticket states its expected net effect on the surface it claims to shrink. Deletion bias in the requirements carries the symmetric statement and the named anti-pattern, so the bar governs additions the same way it already governs keeps and gates.

## Integration

The rule rides the existing single choke point: skills/backlog-author/references/body-template.md is the uniform body shape read by backlog-author interview, backlog-author compose, and discovery decompose, so every structured authoring path inherits it without new machinery. The requirements Deletion bias clause anchors the rationale; the template sentence is the instruction at point of use.

## Edges

- This is authoring guidance, not a lint: cortex-create-backlog-item stays a dumb actor and no gate scans ticket prose — the retired prescriptive-prose scanner is not reborn here.
- The template growth trips the #408 reference-size ratchet by design; the pin takes an annotated raise, exercising the exception affordance for the first time.
- Hand-typed tickets bypass the template; the requirements clause is the only reach there, accepted.

## Touch points

- skills/backlog-author/references/body-template.md (Why section — the Evidence rule)
- cortex/requirements/project.md (Philosophy of Work, Deletion bias — symmetric bar + anti-pattern evidence)
- skills/backlog-author/references/size-pin.txt (annotated raise)