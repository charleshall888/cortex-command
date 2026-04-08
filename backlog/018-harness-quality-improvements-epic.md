---
schema_version: "1"
uuid: b1c2d3e4-f5a6-7890-bcde-f01234567890
id: "018"
title: "Improve overnight execution quality through spec improvements and harness maintainability"
type: epic
status: complete
priority: high
blocked-by: []
tags: [overnight, specs, harness, quality]
created: 2026-04-03
updated: 2026-04-08
discovery_source: research/harness-design-long-running-apps/research.md
---

# Improve overnight execution quality through spec improvements and harness maintainability

Discovery research on Anthropic's harness design article identified three gaps in cortex-command's overnight execution quality.

## Context from discovery

The primary finding was validation: context resets are already correctly implemented. The gaps are upstream of execution — in how specs and plans are authored, and in the absence of any practice for reviewing whether harness components are still earning their complexity.

The full research is at `research/harness-design-long-running-apps/research.md`.

## Child tickets

- 019 — Tighten lifecycle spec template and plan.md verification requirements
- 020 — Add harness component pruning checklist
- 021 — Define evaluator rubric for software features (spike)
- 022 — Fix non-atomic state writes in overnight runner
- 023 — Replace spec dump with JIT loading in implement prompt
- 024 — Reconcile judgment.md with batch-brain.md
- 025 — Prevent agents from writing their own completion evidence
