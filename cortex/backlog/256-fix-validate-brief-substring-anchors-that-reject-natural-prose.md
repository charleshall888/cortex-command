---
schema_version: "1"
uuid: ef4e8d85-4723-442d-8009-5e99090381f3
title: "Fix validate_brief substring anchors that reject natural prose"
status: complete
priority: high
type: chore
created: 2026-05-20
updated: 2026-05-20
parent: "251"
tags: [discovery, validator-bug, gate-policy]
discovery_source: cortex/research/harness-friction-triage/research.md
complexity: complex
criticality: high
spec: cortex/lifecycle/fix-validate-brief-substring-anchors-that/spec.md
areas: [skills]
session_id: null
---

## Role

Broaden the three substring anchor sets in the discovery brief validator so it accepts natural English paraphrases instead of demanding narrow morphological tokens. The decision anchor accepts the family `decide|decided|decision|decisions|chose|chosen|concluded|settled|selected`; the alternatives anchor accepts `alternative|alternatives|option|options|considered|weighed`; the tradeoff anchor accepts `tradeoff|trade-off|cost|drawback|downside|sacrifice`. Resolves the structural contradiction between the rubric prose (which instructs the sub-agent to "Use ordinary words" and uses `settled on` as its own example verb) and the validator (which demands literal `decided` / `decide` tokens).

## Integration

Same gate slot in the discovery research-to-decompose flow; the validator's role and exit-code contract do not change. Only the substring sets and the rubric prose change. Downstream consumers of the gate's pass/fail signal see no contract change.

## Edges

- Breaks if a future revision narrows the anchor set without adding regression tests for paraphrase variants — the broadened set must be defended by tests.
- Empirical motivation: zero successful pass-throughs across the seven observed `gate_brief_generated` events in the discovery and lifecycle corpora; the dense-Architecture fallback is the production behavior today, which means the brief.md path is dead by default.
- Structural sibling of the gate-policy taxonomy child (same hygiene-dressed-as-semantic-gate anti-pattern, different module); ships independently of that ticket.

## Touch points

- `cortex_command/discovery.py:532-580` — `validate_brief` substring anchor sets to broaden.
- `cortex_command/discovery.py:285-322` — `GATE_BRIEF_RUBRIC` prose; resolve the rubric-vs-validator contradiction (the rubric's own example verb `settled on` currently fails the validator).
- `cortex_command/discovery.py:783-810` — retry-feedback prose; align with the broadened anchor set.
- `tests/test_discovery_gate_brief.py` — extend with unit tests covering paraphrase variants (`decision`, `chose`, `concluded`, `selected`, `settled on`, `weighed`, `trade-off`).
- `cortex/research/harness-friction-triage/events.log` — replay surface; this discovery's brief should pass post-fix.
