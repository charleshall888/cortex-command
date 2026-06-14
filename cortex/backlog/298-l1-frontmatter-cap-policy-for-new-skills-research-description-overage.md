---
schema_version: "1"
uuid: e80d67ca-d383-4942-baab-6a452b4271f9
title: L1 frontmatter cap policy for new skills + research-description overage
status: complete
priority: medium
type: chore
created: 2026-06-10
updated: 2026-06-13
complexity: complex
criticality: high
spec: cortex/lifecycle/l1-frontmatter-cap-policy-for-new/spec.md
areas: ['skills']
---
## Why

The L1 frontmatter surface (skill `description`/`when_to_use`, loaded into EVERY session's system prompt in every project with the plugin) measures 8,339 bytes vs 5,777 at lifecycle #191's post-trim snapshot. Decomposition (measured 2026-06-10, evidence preserved in cortex/lifecycle/harness-token-efficiency-trim/evidence.json → l1_surface_baseline): the four skills added since #191 contribute 2,368B uncapped (interview 758, requirements-write 685, requirements-gather 498, backlog-author 427); the original 13 grew only ~194B (+3.4%). So this is NOT regrowth of trimmed skills — it is absence of cap policy for new skills. Also: the prior trim's spec caps as-written FAILED at its close (research measured 378 vs its 200 cap, a documented MISS in the post-trim measurement doc; research is 502 today).

## Role

Define a cap policy for new-skill frontmatter (per-skill byte budget at authoring time), resolve the research-skill overage (502B vs the old 200 cap — either trim or re-cap with rationale), and re-trim the four uncapped skills where their descriptions exceed what routing accuracy needs.

## Integration

tests/test_l1_surface_ratchet.py (added by harness-token-efficiency-trim) freezes today's per-skill baselines — equal-or-lower passes. The cap policy replaces the ratchet's frozen snapshot with deliberate budgets; update the ratchet baselines in the same change. Trimming descriptions is constrained by tests/test_skill_descriptions.py (case-sensitive trigger-phrase substrings from tests/fixtures/skill_trigger_phrases.yaml, checked against description alone) and tests/test_skill_routing_disambiguation.py (cluster phrases against concatenated description+when_to_use) — routing-accuracy regressions are the failure mode to guard.

## Edges

- A description trim that drops a trigger phrase breaks routing fixtures — run both routing test files per edit.
- The #191 spec caps were aspirational in one case (research MISS); the new policy should state what happens when a cap cannot be met (re-cap with rationale beats silent miss).
- when_to_use is concatenated to description for routing — caps should bound the SUM.

## Touch-points

- skills/*/SKILL.md frontmatter (description, when_to_use)
- tests/test_l1_surface_ratchet.py (baselines)
- tests/fixtures/skill_trigger_phrases.yaml, tests/test_skill_descriptions.py, tests/test_skill_routing_disambiguation.py
- cortex/lifecycle/reduce-boot-context-surface-claudemd-skillmd/ (prior art: spec R6 caps, post-trim-measurement.md)
