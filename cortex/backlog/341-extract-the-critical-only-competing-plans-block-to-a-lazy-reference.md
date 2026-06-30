---
schema_version: "1"
uuid: 562ec957-4c0e-44f1-b408-a9316932d37e
title: Extract the critical-only competing-plans block to a lazy reference
status: backlog
priority: high
type: chore
created: 2026-06-30
updated: 2026-06-30
parent: "340"
tags: ['skill-efficiency-remaining-work']
discovery_source: cortex/research/skill-efficiency-remaining-work/research.md
---
## Why
The plan-phase reference carries a large "Competing Plans" block that runs only when a feature's criticality is critical, yet it loads on every plan because the phase reads the whole reference top-to-bottom. Measured across 257 features, critical is about 2% of plans (the rest high/medium/low), so this block is dead weight on roughly 98% of plan reads — and it is the single largest resident-byte reduction available on the hottest interactive path, at low risk. It is also the no-architectural-risk form of the resident-prose reduction the phase-isolation probe recommended over a context rewrite.

## Role
Move the critical-only competing-plans flow — the multi-plan dispatch, the plan-agent prompt template, the synthesizer step, and the comparison-event schema — out of the plan reference into a sibling reference that the criticality branch reads only when criticality is critical. Leave a real heading stub plus a one-line pointer in the plan reference, so the non-critical path skips the body entirely while the heading other consumers cite stays in place. The win requires physical extraction to a separately-read file; reordering within the plan reference saves nothing, because the whole file enters context on read regardless of internal section order.

## Integration
The criticality branch already routes critical features to the competing-plans block and everyone else straight to the single-plan flow, so the relocation rides the existing branch — the stub points the critical arm at the new reference. The overnight orchestrator only cites the competing-plans heading as a documentation anchor; it carries its own inline reimplementation and does not read the plan reference at runtime, so the citation survives as long as the heading stub remains. The section-citation test that pins the heading and the prior consolidation epic's guardrail that preserves it verbatim are both satisfied by keeping the stub heading.

## Edges
- Breaks the overnight documentation anchor if the competing-plans heading is removed rather than stubbed — the heading must remain as a real pointer.
- Breaks the section-citation test if the pinned heading text changes.
- The critical arm gains one extra reference read on the about-2% critical path — acceptable, since that content was going to load on exactly those runs anyway.

## Touch points
- skills/lifecycle/references/plan.md §1b (the block to extract; leave `### 1b. Competing Plans (Critical Only)` heading + pointer)
- skills/lifecycle/references/plan.md:18-19 (the §1a criticality branch that gates the read)
- new skills/lifecycle/references/competing-plans.md (extraction target)
- cortex_command/overnight/prompts/orchestrator-round.md:302 (citation referent to update)
- tests/test_skill_section_citations.py:64 (heading pin — repoint to the stub or the new file)
- plugins/cortex-core/skills/lifecycle/references/ (auto-generated mirror)