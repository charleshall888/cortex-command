---
id: 52
title: Audit skill prompts and remove verbose instructions above the floor
status: refined
priority: medium
type: chore
parent: 49
blocked-by: []
tags: [output-efficiency, skills]
created: 2026-04-09
updated: 2026-04-10
discovery_source: research/agent-output-efficiency/research.md
session_id: 1a6d6f64-1fba-44d2-889c-07a6bf0d8bc6
lifecycle_phase: plan
lifecycle_slug: audit-skill-prompts-and-remove-verbose-instructions-above-the-floor
complexity: complex
criticality: high
spec: lifecycle/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/spec.md
areas: [skills]
---

# Audit skill prompts and remove verbose instructions above the floor

## Context from discovery

Only commit and pr skills have explicit output constraints ("no conversational text — only tool calls"). All other skills give open-ended output instructions. Anthropic's harness design principle: "every component encodes an assumption about model capabilities — stress test those assumptions." Some verbose-by-default instructions may be unnecessary with Opus 4.6.

**Rubric** (from ticket #050's output floors): An instruction is removable if it generates output above the interactive and overnight floors defined in #050 AND is not consumed by a downstream skill or approval gate. Instructions that serve overnight observability or approval surfaces are not candidates for removal.

Skills to audit: lifecycle, discovery, critical-review, research, pr-review, overnight, dev, backlog, diagnose. Uncertain cases get a flagged note in the audit output for later resolution — not silently deferred.
