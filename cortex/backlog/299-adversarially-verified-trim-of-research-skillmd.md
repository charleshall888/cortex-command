---
schema_version: "1"
uuid: 6a8e28ef-dbe3-4b51-911b-3d84d1ce3b40
title: Adversarially-verified trim of research/SKILL.md
status: backlog
priority: medium
type: chore
created: 2026-06-10
updated: 2026-06-10
---
## Why

skills/research/SKILL.md (15,018 bytes) loads on every research delegation from lifecycle, refine, AND discovery — hot-path in exactly the sessions the harness-token-efficiency-trim feature optimized — but was excluded from that feature's 12-file trim because no adversarially-verified trim map existed for it. Building the map mid-lifecycle would have inflated the feature (per its critical-review pass). The 12 mapped files averaged ~28% verified-safe reduction; a comparable map here plausibly yields 3-4KB.

## Role

Produce a per-section trim map for research/SKILL.md (classify: load-bearing gates vs maintainer rationale vs How-narration vs duplication), adversarially verify each proposal (the harness-token-efficiency-trim feature's evidence.json → trims_verified entries show the proposal/verdict schema that worked), then apply the verified-safe subset.

## Integration

Known constraint anchors (from the prior feature's research — verify before editing): tests/test_research_fanout_matrix.py and tests/test_discovery_research_sizing.py pin the fan-out count matrix references; the per-angle prompt blocks at roughly lines 80-185 are dispatched-verbatim to research sub-agents and are largely UNTRIMMABLE (sub-agents cannot follow pointers); fanout.md is the canonical count-matrix home per the do-not-re-inline citation in the SKILL body — do not duplicate it back. The file is consumed via ${CLAUDE_SKILL_DIR}/../lifecycle/references/ propagation from refine and discovery — cortex-check-skill-path lints any propagation edits.

## Edges

- The adversarial pass on the synthesizer/adversarial-wave instructions: the always-last adversarial dispatch ordering is load-bearing (error-amplification control) — narration around it can trim, the ordering rule cannot.
- Section designators may be cited from docs/ — run a citation grep before renumbering.

## Touch-points

- skills/research/SKILL.md (canonical) + plugins/cortex-core mirror
- skills/lifecycle/references/fanout.md (canonical matrix — pointer target, not duplicate)
- tests/test_research_fanout_matrix.py, tests/test_discovery_research_sizing.py
