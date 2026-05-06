---
schema_version: "1"
uuid: eb7cf492-c35d-4d70-835c-2d7b1b58f844
title: "Lifecycle adopts cortex-resolve-backlog-item, delete refine/references/clarify.md"
type: feature
status: complete
priority: high
parent: 172
blocked-by: []
tags: [lifecycle, refine, dual-source, deduplication, backlog-resolution, vertical-planning]
created: 2026-05-06
updated: 2026-05-06
discovery_source: research/vertical-planning/research.md
complexity: complex
criticality: high
spec: lifecycle/lifecycle-adopts-cortex-resolve-backlog-item-delete-refine-references-clarifymd/spec.md
areas: [skills]
session_id: null
---

# Lifecycle adopts cortex-resolve-backlog-item, delete refine/references/clarify.md

Switch lifecycle's `clarify.md §1` from ad-hoc Python scanning to the `cortex-resolve-backlog-item` CLI that refine already uses, then delete refine's near-identical `clarify.md` (130 lines). Distinct from ticket 174's byte-identical collapses because lifecycle and refine clarify.md differ only in §1 (Resolve Input) but the predicates are not identical — adopting refine's flow changes which backlog items resolve unambiguously vs as ambiguous.

## Context from discovery

The audit's pressure-test pass verified that `skills/lifecycle/references/clarify.md` (124 lines) and `skills/refine/references/clarify.md` (130 lines) are byte-identical except for §1 Resolve Input (10 added lines for refine's `cortex-resolve-backlog-item` exit-code handling).

Lifecycle's current §1 does ad-hoc Python scanning: numeric input ID + kebab input slug + title fuzzy match. Refine's helper has its own predicate: set-theoretic union of raw substring AND slugified substring. **These match different sets** — particularly for inputs with uppercase or punctuation.

Audit § *"Pressure-test corrections — Falsified or weakened — `clarify.md` adoption of `cortex-resolve-backlog-item` is a no-op → NOT NO-OP."*

## What to land

### Phase 1: Predicate equivalence test

Before any deletion, write a contract test that exercises both predicates against a curated set of backlog-item resolution inputs:
- Numeric IDs (exact match, padded with zeros, etc.)
- Kebab-case slugs
- Title fuzzy matches
- Inputs with uppercase
- Inputs with punctuation
- Inputs that match multiple items (ambiguity handling)
- Inputs that match no items

Document any divergence between the two predicates. If divergences are found, decide per-case whether refine's helper produces correct behavior or whether the helper needs an enhancement to preserve lifecycle's match semantics.

### Phase 2: Lifecycle adoption

Update `skills/lifecycle/references/clarify.md §1` to invoke `cortex-resolve-backlog-item` with the documented exit-code handling pattern from refine's clarify.md.

### Phase 3: Deletion

After lifecycle adoption is verified to handle the test inputs from Phase 1 correctly:
- Delete `skills/refine/references/clarify.md` (canonical)
- Update `skills/refine/SKILL.md` Step 3 to read from `skills/lifecycle/references/clarify.md` (now containing the helper-based §1)
- Run `just build-plugin` to prune mirror

## Touch points

- `bin/cortex-resolve-backlog-item` (verify; no changes expected)
- `skills/lifecycle/references/clarify.md` (update §1 to use helper)
- `skills/refine/references/clarify.md` (delete)
- `skills/refine/SKILL.md` (update reference path)
- `tests/test_resolve_backlog_item.py` or similar (new contract test)
- `plugins/cortex-core/skills/refine/references/clarify.md` (auto-pruned by build-plugin)

## Verification

- New contract test passes for all curated input cases
- `test ! -f skills/refine/references/clarify.md` (exit 0)
- A fresh refine invocation on a test backlog item resolves correctly via the helper-based flow
- A fresh lifecycle invocation on a test backlog item resolves correctly via the helper-based flow (now reading the same clarify.md as refine)
- `pytest tests/test_dual_source_reference_parity.py` passes (collected pairs drop by 1)
