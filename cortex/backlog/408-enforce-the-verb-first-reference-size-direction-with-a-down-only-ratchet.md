---
schema_version: "1"
uuid: ea055171-a605-44a2-8b1e-b37826464d99
title: Enforce the verb-first reference-size direction with a down-only ratchet
status: backlog
priority: medium
type: feature
created: 2026-07-21
updated: 2026-07-21
tags: ['token-efficiency', 'skills', 'tests']
areas: ['skills']
---
## Why

The requirements state reference prose follows verb-first — behavior moves into CLI verbs, prose keeps only control flow — targeting roughly a tenfold reduction of the skills reference corpus. Nothing enforces that direction: the corpus sits at 58 files / ~241KB, recent reference commits are net additions (picker-protocol fix, trunk-cost copy), and no test can see reference-file growth — SKILL.md bodies have a 500-line budget test while references have nothing. Meanwhile trim passes are triple-closed (leanification campaign, wave 2, epic #340's premise ruling), so the direction needs a structural mechanism, not another sweep.

## Role

Add a down-only size ratchet for skills reference directories, mirroring the SKILL.md size-budget test's pattern: pins start at current sizes, growth fails with a pointer to the verb-first rule, and lowering a pin is always allowed and expected. The tenfold target is then approached opportunistically — any lifecycle already touching a skill applies verb-first and lowers that skill's pin — rather than via a dedicated rewrite campaign.

## Integration

Ruling recorded 2026-07-21, resolving the fork the requirements clause left open: opportunistic-plus-ratchet over a dedicated drastic rewrite campaign. The campaign's own empirics say verb extraction is where trim work breeds correctness bugs and the payoff is qualitative (attention-dilution, harness size), not measured token spend — cost scales with turns and context and cache sits near 98 percent. The ratchet adds the determinism the direction lacked; a dedicated campaign remains available if convergence proves too slow, and commissioning it is a separate decision.

## Edges

- The ratchet is a size gate, not a prose-scanner: it carries named evidence (unchecked growth against a stated requirements direction) and sits in the same survivor class as the SKILL.md budget test under the named-evidence rule — it must not morph into content linting, and #407's disposition pass should treat it accordingly.
- Exception affordance mirrors the SKILL.md cap's in-file exception comment: growth needed for a correctness fix takes the exception, states why, and re-ratchets afterward.
- New skills need a seeding rule — the first commit of a references directory sets its pin.
- Pins must live where a lifecycle naturally updates them; a stale central pin file that blocks unrelated commits would recreate the friction #407 exists to remove.

## Touch points

- tests/test_skill_size_budget.py (the pattern to mirror)
- skills/*/references/ (the ratcheted surface, 58 files at creation)
- cortex/requirements/project.md (Architectural Constraints — the verb-first size-direction clause)
- docs/policies.md (authoring policy alignment)
- Related: #407 (named-evidence disposition), #340 (closed trim epic whose premise ruling this respects)