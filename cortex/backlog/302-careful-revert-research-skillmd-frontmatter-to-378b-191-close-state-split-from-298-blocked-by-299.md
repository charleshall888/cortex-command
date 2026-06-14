---
schema_version: "1"
uuid: 0e8dcceb-26a5-432d-aec1-1137090e141a
title: 'Careful-revert research/SKILL.md frontmatter to ~378B #191 close-state (split from #298, blocked by #299)'
status: complete
priority: medium
type: chore
created: 2026-06-13
updated: 2026-06-13
blocked-by: 299
complexity: complex
criticality: high
spec: cortex/lifecycle/careful-revert-research-skillmd-frontmatter-to/spec.md
areas: ['skills']
---
## Why

`skills/research/SKILL.md`'s `description` regrew +124B post-#191 (378B at the #191 close → 502B today), re-adding the mechanism-narration ("Dispatches 3–10 parallel agents — sized by a tier×criticality matrix — … always-last adversarial pass") that #191 deliberately trimmed out: a description is routing metadata (what/when to use), and how-it-works internals belong in the on-trigger body, not the always-loaded L1 surface. Split from #298 (L1 cap policy), which sets the policy and trims the four uncapped skills but cannot carry this revert: #299 edits research's BODY and this edits the FRONTMATTER (byte-disjoint), so it must sequence after #299, and gating it inside #298 would make #298 un-completable in an overnight run. The "502 vs 200 cap" framing in #298's body was a #191 doc-classification error (review.md flagged it) — the real defect is the +124B regrowth. See cortex/lifecycle/l1-frontmatter-cap-policy-for-new/research.md and spec.md.

## Role

Careful-revert research's `description` from 502B toward the ~378B #191 close-state: remove the mechanism-narration regrowth while preserving the three test-enforced trigger phrases (`/cortex-core:research`, `research this topic`, `investigate this feature`) and a compact research.md-vs-conversation-output disambiguation tail. Lower research's ratchet budget (set in #298 at 502 as a cluster skill) to the new measured value.

## Integration

research is in the routing-pressure cluster (exempt from #298's ≤400 default), so this is a deliberate regrowth-revert, not a cap-forced trim. tests/test_skill_descriptions.py (trigger substrings vs `description` alone) and tests/test_skill_routing_disambiguation.py (cluster, concatenated desc+wtu) guard routing — both must pass. Lower the research budget in tests/test_l1_surface_ratchet.py (a budget reduction, so equal-or-lower passes — no lifecycle-id needed). Regenerate the cortex-core plugin mirror; commit canonical+mirror together.

## Edges

- blocked_by #299: #299 trims research's body; this trims the frontmatter — byte-disjoint, but same file + same mirror, so sequence after #299 to avoid churn and stale line numbers.
- Target is the ~378B #191 close-state, NOT the rejected 200B cap (a #191 doc-classification error). Do not over-trim toward 200.
- Keep all three trigger phrases in `description` (test_skill_descriptions checks `description` alone).

## Touch-points

- skills/research/SKILL.md frontmatter (description)
- tests/test_l1_surface_ratchet.py (research budget, lowered from 502)
- plugins/cortex-core/skills/research/SKILL.md (mirror, regenerated)
- cortex/lifecycle/l1-frontmatter-cap-policy-for-new/ (parent context: research.md, spec.md)