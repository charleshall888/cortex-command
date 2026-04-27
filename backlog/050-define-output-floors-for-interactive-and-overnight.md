---
id: 50
title: Define output floors for interactive approval and overnight compaction
status: complete
priority: high
type: feature
parent: 49
tags: [output-efficiency, context-management, overnight]
created: 2026-04-09
updated: 2026-04-09
discovery_source: research/agent-output-efficiency/research.md
session_id: null
lifecycle_phase: implement
lifecycle_slug: define-output-floors-for-interactive-approval-and-overnight-compaction
complexity: complex
criticality: high
spec: lifecycle/archive/define-output-floors-for-interactive-approval-and-overnight-compaction/spec.md
areas: [skills,lifecycle]
---

# Define output floors for interactive approval and overnight compaction

## Context from discovery

Phase transitions, approval surfaces, and synthesis output serve multiple consumers: interactive users approving specs/plans, overnight agents whose output must survive compaction (12% retention), and morning review which reads event logs and session artifacts. The lifecycle SKILL.md's "briefly summarize what was accomplished and what comes next" instruction is simultaneously the transition announcement, the approval surface, and the only intra-feature progress signal in overnight context.

Before any output can be compressed, two floors must be defined:

**Interactive floor**: What must a phase summary include for a user to make an informed approval decision without reading the full artifact? Key decisions made, trade-offs chosen, scope boundaries, anything the user might veto.

**Overnight floor**: What must survive compaction and remain actionable in morning review? Structural markers, key findings, phase progress signals. Overnight sessions routinely hit the 95% compaction threshold — the surviving 12% must be self-sufficient.

These floors gate all downstream compression work (tickets #052 and #053). Phase transition format (one-line vs. multi-sentence) is an output of this ticket, not a separate decision — the floor determines the format.
