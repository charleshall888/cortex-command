---
schema_version: "1"
uuid: f6d3637e-b27b-426b-9978-5ecfeb740238
title: "Reduce boot-context surface (CLAUDE.md + SKILL.md)"
type: feature
status: open
priority: high
parent: 187
blocked-by: []
tags: [boot-context, claude-md, skill-md, descriptions, skill-routing, workflow-trimming]
created: 2026-05-11
updated: 2026-05-11
discovery_source: research/lifecycle-discovery-token-audit/research.md
---

# Reduce boot-context surface (CLAUDE.md + SKILL.md)

## Problem

Every Claude Code session against this repo pays a fixed always-on context cost from `CLAUDE.md` and SKILL.md descriptions. Audit findings:

- **CLAUDE.md** at 67/100 lines per project policy. Of those, ~25% (~400 tok) is two policy entries (MUST-escalation + Tone/voice, lines 51-67). The tone section documents *why nothing ships* — history, not instruction.
- **13 enabled SKILL.md descriptions**, measured average ~136 words, range 31-218; sum ≈ 1,770 words ≈ ~2,300 tok always-loaded at every session start per Anthropic's Level 1 contract (`docs/overnight-operations.md:11`). Several descriptions embed trigger-phrase lists and structural prose (e.g., `lifecycle/SKILL.md` lists canonical source paths inside the description field).
- **SKILL.md bodies are Level 2** (loaded on trigger, not eagerly) per the same contract, but some bodies are large: `diagnose/SKILL.md` 489 lines, `overnight/SKILL.md` 403, `critical-review/SKILL.md` 369, `lifecycle/SKILL.md` 365. When multiple are triggered in one session, the trigger-conditional cost compounds.
- **Some skills may not earn their keep**. The project's "Workflow trimming" doctrine (per `requirements/project.md:23`) prefers hard-deletion over keeping unused surface. Audit didn't measure invocation frequency per skill — research would.

## Why it matters

- Always-on cost (~2,700 tok per session) is paid by *every* session against this repo, even sessions that never invoke any cortex skill.
- The CLAUDE.md tone block specifically documents a non-shipping decision; that content has the lowest actionability per token in the file.
- SKILL.md description content competes with itself: trigger phrases are the routing signal AND the bulk of the token cost. Compression has a routing-regression risk.
- Skill consolidation (deleting low-value skills) is the project's preferred response to surface bloat and has no routing-regression risk.

## Constraints

- **Skill routing must not regress**. The existing description-snapshot test (`tests/test_skill_descriptions.py` + `tests/fixtures/skill_trigger_phrases.yaml`) guards `description` field content for known trigger phrases. Any change that moves trigger phrases out of `description` must keep this test passing or replace it with an equivalent guardrail against the new surface.
- **Anthropic's Level 1/2/3 contract** (per `docs/overnight-operations.md:11`): Level 1 = name + description always in context; Level 2 = SKILL.md body on trigger; Level 3 = references on demand. **No evidence the loader routes against non-`description` frontmatter fields** — moving trigger phrases to a field the loader doesn't index is a silent regression with a green test suite.
- **CLAUDE.md's 100-line threshold rule** is itself in CLAUDE.md (lines 96-100). Extracting policies before the 100-line trip is defensible only if the rule itself is reframed (e.g., to a cost-based trigger).
- **`when_to_use:` field** already exists in 4 SKILL.md files (lifecycle, refine, discovery, critical-review). Loader tolerates the field; whether it routes against it is unverified.

## Out of scope

- Investigating whether Anthropic's plugin loader supports custom frontmatter routing (would require a controlled empirical test outside this repo).
- Renaming or restructuring the SKILL.md format beyond what existing tooling already accepts.
- Plugin-manifest changes beyond what's needed for the chosen approach.

## Acceptance signal

- Always-on boot context measurably smaller than today (target: meaningful reduction; specific number set during research after measurement).
- Skill auto-routing accuracy is at least equivalent to today's baseline (test gate stays green or is replaced with equivalent coverage).
- CLAUDE.md is below today's 67 lines AND the 100-line threshold rule is reframed or removed (if extraction happens), so future contributors aren't confused about when extraction is allowed.
- If any skill is deleted, it's documented in `CHANGELOG.md` with replacement entry points per the project's workflow-trimming doctrine.

## Research hooks

Several surface-reduction levers exist; research-phase should evaluate each:

- **Description compression** — strip structural prose (e.g., embedded canonical-path enumeration in `lifecycle/SKILL.md` description), keep trigger phrases. Safe; reversible; protected by existing test. Smaller win (~600-900 tok).
- **Trigger-phrase move to non-`description` frontmatter** (e.g., new `triggers:` array or extending `when_to_use:`). Larger nominal win (~2,300 tok) but contingent on Anthropic's loader actually indexing the moved field — currently unverified evidence-wise. If pursued, the cheapest verification is an empirical test (single SKILL.md with a uniquely-phrased trigger in the candidate field, observe routing).
- **Skill consolidation/deletion** — invocation-frequency audit; drop or merge low-value skills. Aligns with workflow-trimming doctrine. Removes both Level-1 description cost AND Level-2 body cost for deleted skills.
- **SKILL.md body trimming** for large bodies (`diagnose/SKILL.md` at 489 lines is the obvious first target). Level-2 cost, paid only on trigger, but compounds across multi-skill sessions.
- **CLAUDE.md policy extraction** to `docs/policies.md` — and reframing the 100-line rule itself to a cost-based trigger (e.g., "any policy entries totaling ≥400 tok"), so the extraction-now decision is principled rather than premature.

The audit's DR-4 area and the alternative-exploration outputs evaluate these and commit to recommendations. Treat those as inputs to your own evaluation; the loader-routing question in particular needs verification before any non-`description` move.
