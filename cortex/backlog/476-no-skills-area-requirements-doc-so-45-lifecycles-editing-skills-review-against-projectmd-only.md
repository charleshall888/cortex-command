---
schema_version: "1"
uuid: fd9f2faa-8218-4e07-b16f-29be03ace64a
title: No skills area requirements doc, so 45 lifecycles editing skills review against project.md only
status: backlog
priority: medium
type: feature
created: 2026-08-07
updated: 2026-08-08
tags: ['requirements', 'skills', 'process']
areas: ['skills', 'requirements']
complexity: complex
criticality: high
---
# No skills area requirements doc, so 45 lifecycles editing skills review against project.md only

## Why

Measured on the live tree after #472's backfill, through the shipped loader:

```
declare areas: [skills]                          57
  already covered by another declared area       12
  would newly gain coverage from a skills.md     45
```

`skills` is the largest unmapped area by a wide margin — the full unmapped tail is `skills` 57, `hooks` 9, `tests` 7, `docs` 4, then singles. It has neither a `cortex/requirements/skills.md` nor a `## Conditional Loading` row, so a lifecycle editing a skill loads `project.md` + Global Context and nothing area-level.

This is the same gap #469 closed for `lifecycle` (44 lifecycles), one area larger.

**Observed cost, not hypothetical.** In #472's own implement phase, Task 5 edited `skills/build/references/review.md`. Its plan Context had to hand-carry, in the task text, every constraint that governs that edit:

- `skills/build/references/` sits at **zero headroom** against its `size-pin.txt`, so any net growth fails `just ratchet-refs`
- the ratchet/mirror sequence is `just ratchet-refs` → `just build-plugin` → `just ratchet-refs`
- `build-plugin` does not carry `size-pin.txt`, making the mirror pin the one path to stage by hand
- every other `plugins/cortex-core/` path is rebuilt from staged blobs and must never be staged manually
- per `docs/policies.md`, no test may assert skill prose exists or reads a certain way

None of that loaded. It was carried by hand because the plan author happened to know it. The recurrence is independently attested: this exact sequence is a standing operator note precisely because it keeps being rediscovered rather than read. A builder dispatched without that paragraph would have grown a zero-headroom directory and staged the wrong mirror path.

## Role

Give the skill surface area-level requirements, so a lifecycle touching `skills/` is planned and reviewed against the constraints that actually govern it rather than against `project.md` alone — and so requirements-drift detection has somewhere to land for the repo's most-edited area.

## Integration

Some content relocates rather than being written new: `project.md`'s `## Architectural Constraints` carries the SKILL.md 500-line size cap (186 bytes, purely skills) and, inside the Enforcement gates bullet, the verb-first reference-prose direction with its down-only size ratchet. Both currently load for all 191 lifecycles but govern only the 45.

Be honest about the size of that win: it is roughly 1KB out of `project.md`'s 27KB. **This ticket is not efficiency-framed** — the relocation is a tidy side effect, not the justification. The justification is the governance gap above.

`docs/policies.md` keeps the authoring *how-to* (kept-pauses affordances, What/Why-not-How, L1 surface budgets, MUST-escalation). The area doc carries scope, boundaries, and architectural constraints, and points at policies.md rather than restating it — the existing area docs are the format model, and `CLAUDE.md` already names `cortex/requirements/` as a sanctioned home for harness-work direction.

Constraints worth capturing: the dual-source canonical/mirror rule, `${CLAUDE_SKILL_DIR}` resolution (ADR-0009), the reference-size ratchet and per-directory pins, the no-tests-pinning-skill-prose rule, and the shipped-surfaces-carry-no-repo-governance boundary.

## Edges

- **The map row and the doc must land together.** Adding `skills → cortex/requirements/skills.md` without writing the doc moves 45 lifecycles from `unmapped` to `doc-missing` — strictly louder, no better. Either both, or neither.
- **`skills` may be too broad to be one area.** It spans commit, pr, backlog, research, and the lifecycle phase skills, whose concerns differ. The area→doc map is many-to-one, so a later split is cheap — but if the doc turns into a grab-bag with no shared scope, that is the signal to split rather than to keep appending.
- Decide whether `hooks` (9) routes here or stays unmapped. The two surfaces share the dual-source mirror rule and little else.
- This doc loads for 45 lifecycles, so it is subject to the same conditional-loading discipline as the others. `project.md:7` explicitly does not treat resident prose as the token lever, but that is not a licence for a doc without a scope boundary.
- The boundary against `lifecycle.md` needs stating: the build/refine phase *skills* are authored under this doc; the state machine they drive is specified by `lifecycle.md`. The same surface must not be specified twice.

## Touch-points

New `cortex/requirements/skills.md`; `cortex/requirements/project.md` (a `## Conditional Loading` row, plus whatever Architectural Constraints bullets relocate); `cortex/requirements/glossary.md` if the area needs a term. Verify with the coverage measurement in `cortex/adr/0037-area-to-doc-map-as-the-requirements-vocabulary.md` — expect the `loaded` count to rise by ~45 and `unmapped` to fall from 61 to ~16.
