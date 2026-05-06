---
schema_version: "1"
uuid: 6da37238-e1c0-4e2d-8f11-24b9cb57d101
title: "Skill-design test infrastructure (description snapshots + cross-skill handoff + ref-file path resolution + skill-size budget)"
type: chore
status: in_progress
priority: medium
parent: 172
blocked-by: []
tags: [tests, skill-design, lifecycle, refine, critical-review, discovery, vertical-planning]
created: 2026-05-06
updated: 2026-05-06
discovery_source: research/vertical-planning/research.md
complexity: complex
criticality: high
spec: lifecycle/skill-design-test-infrastructure-description-snapshots-cross-skill-handoff-ref-file-path-resolution-skill-size-budget/spec.md
areas: [tests]
session_id: 363d73f9-d244-4d69-aa6a-c5be1781336d
lifecycle_phase: plan
---

# Skill-design test infrastructure (description snapshots + cross-skill handoff + ref-file path resolution + skill-size budget)

Four new test classes that catch regressions the prior cortex test suite doesn't catch. Bundled because each is a small focused test class and they share a CI-time / test-design concern.

## Context from discovery

The skill-creator-lens audit identified gaps in cortex's existing test surface specific to skill design. Audit § *"Test/verification gaps (new class)"*. Each test class catches a different regression mode that has at least one historical near-miss in cortex.

## What to add

### 1. Description-trigger snapshot test (`tests/test_skill_descriptions.py`)

The SKILL.md `description` field is the primary trigger mechanism. A casual edit dropping "prepare for overnight" from refine's description silently breaks routing for users who say that phrase.

Test asserts each of the four SKILL.md descriptions contains a curated set of trigger phrases:
- lifecycle: ["start a lifecycle", "lifecycle research/specify/plan/implement/review/complete", ...]
- refine: ["refine backlog item", "prepare for overnight", "spec this out", ...]
- critical-review: ["critical review", "pressure test", "stress test", ...]
- discovery: ["discover this", "research and ticket", "decompose into backlog", ...]

Build the trigger phrase corpus from ticket 178's description fixes (this ticket lands after 178 if it lands; both can be done in parallel by reading the post-178 descriptions or the audit's recommended phrasings).

**Failure mode caught**: silent description edit removes a trigger phrase, regressing routing.

### 2. Cross-skill handoff integration test

lifecycle→refine, refine→lifecycle, lifecycle→critical-review handoffs aren't currently exercised end-to-end. `tests/test_skill_callgraph.py` validates that the call exists in markdown but does not exercise it.

Test creates a fixture lifecycle session and walks through:
1. discovery → produces backlog ticket with `discovery_source` field
2. refine on that ticket → produces lifecycle/{slug}/research.md + spec.md
3. lifecycle on the same slug → reads research.md + spec.md, produces plan.md
4. critical-review auto-trigger on critical-tier plan

**Failure mode caught**: refactor renames `discovery_source` → `research_source` (or any other handoff field rename) breaks the chain silently.

### 3. Reference-file path resolution test

Skill files cite paths with line numbers like `plan.md:107` references `plugins/cortex-core/skills/critical-review/SKILL.md:176-182`. Line numbers are extremely brittle — any insertion above line 176 breaks the citation.

Test scans every `<file>:<line>` reference in `skills/**/*.md` and asserts:
- The file exists at the cited path
- The file has at least the cited line count

Optionally: assert the cited line range still matches a stable section anchor (catches drift even when line counts hold).

**Failure mode caught**: stale line-number pointers across skill files.

### 4. Skill-size budget test

Skill-creator framework recommends SKILL.md ≤500 lines. cortex's lifecycle (380) and critical-review (365) are close to the cap; the next significant addition will breach it without a CI signal.

Test asserts each SKILL.md is ≤500 lines (configurable cap per skill if needed). Failure surfaces as a clear "skill X exceeds budget; consider extracting to references/" error.

**Failure mode caught**: organic SKILL.md growth without conscious extraction decision.

## Touch points

- `tests/test_skill_descriptions.py` (NEW)
- `tests/test_skill_handoff.py` (NEW; or extend existing test_skill_callgraph.py if cleaner)
- `tests/test_skill_reference_paths.py` (NEW)
- `tests/test_skill_size_budget.py` (NEW; or fold into a multi-test file)
- `justfile` may need a recipe for running the new test class

## Verification

- All four new tests pass against the current state of skills/ (with any phrasing-drift from ticket 178 absorbed)
- All four tests are wired into `just test` or equivalent CI surface
- Each test produces a clear, actionable error message on failure (not just an assertion failure)
- A deliberate regression (drop a trigger phrase from one description) causes test_skill_descriptions.py to fail with a useful message
- A deliberate regression (rename a referenced file) causes test_skill_reference_paths.py to fail with the file path
