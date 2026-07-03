---
schema_version: "1"
uuid: c75d97ba-dc70-4fcd-89b0-15150a6a801a
title: Evaluate observability.md s14 relocation to docs/internals/auto-update.md
status: complete
priority: low
type: chore
created: 2026-07-03
updated: 2026-07-03
resolution: Relocated the `## Install-mutation invocations` section from cortex/requirements/observability.md to docs/internals/auto-update.md; updated the artifact-format.md:45 exception note and marked master_candidates.json s14 verified_survives. No runtime citers; no test greps the heading.
parent: "357"
---
## Why

Deferred from #358 (provisional-tail sweep of `cortex/requirements` area files). Candidate **observability.md s14** is a `LAZY_REF` that would relocate the entire `## Install-mutation invocations` H2 section from `cortex/requirements/observability.md` to `docs/internals/auto-update.md`. This is a cross-file move outside #358's 5-file editorial scope, it targets a section the requirements angle flagged **must-keep** (a maintainer contract), and it requires updating the extra-H2 exception note in the `requirements-write` artifact-format guidance. #358 recorded it as `deferred: out-of-editorial-scope` (NOT refuted — the relocation may still be valid work) and left the section byte-identical.

## Scope

Evaluate the relocation as a real lifecycle change, not an editorial trim:
- Decide whether `docs/internals/auto-update.md` is the better home for the Install-mutation-invocations maintainer contract.
- If relocating: move the section, update the extra-H2 exception note, and refresh any citers of the moved section.
- The candidate is in `cortex/research/skill-value-scorecard/master_candidates.json` (`file=cortex/requirements/observability.md`, `id=s14`), currently left `status: unverified` pending this evaluation.

## Done when

Either the section is relocated (with citers + exception-note updated) via a lifecycle change, or `observability.md s14` is marked `verified_refuted` in `master_candidates.json` with rationale.

Source record: `cortex/lifecycle/sweep-provisional-tail-cortex-requirements-area/verify-outcomes.md` (observability s14 row).