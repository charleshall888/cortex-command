---
schema_version: "1"
uuid: 8f1fdd95-b748-4b10-bbf8-6f54b17e75a1
title: "Lifecycle and hook hygiene one-offs"
type: chore
status: open
priority: medium
parent: 187
blocked-by: []
tags: [lifecycle, hooks, hygiene, scan-script, auto-scan]
created: 2026-05-11
updated: 2026-05-11
discovery_source: research/lifecycle-discovery-token-audit/research.md
---

# Lifecycle and hook hygiene one-offs

## Problem

Four unrelated hygiene gaps surfaced by the audit, bundled here because each is small and they don't share mechanism:

- **Lifecycle SKILL.md Step 2 re-globs the backlog 4×** for the same feature slug. `skills/lifecycle/SKILL.md:95, 129, 164, 191` each runs `backlog/[0-9]*-*{feature}*.md` independently. `bin/cortex-resolve-backlog-item` (already invoked elsewhere in the flow) returns the resolved filename; the four globs ignore it.
- **`hooks/cortex-scan-lifecycle.sh` unconditionally regenerates metrics on every SessionStart**. `:244-256` shells `python3` once for phase detection; `:417` shells `python3` again to regenerate `metrics.json`; `:446` appends the metrics summary to the injected SessionStart context. The metrics regeneration runs even when no pipeline is active.
- **Discovery auto-scan may be dead code**. `skills/discovery/references/auto-scan.md:31` walks all `backlog/[0-9]*-*.md` frontmatter (183+ files) when `/cortex-core:discovery` is invoked with no topic argument. Audit found zero evidence the no-topic invocation has ever been used (no historical lifecycle dirs derive from it; git log shows no traces). If it's never invoked, optimization is gold-plating; deletion is the right move.
- **`hooks/cortex-skill-edit-advisor.sh:43` runs full `just test-skills`** (4 sub-suites per `justfile:439-460`) on every `Edit`/`Write` to any SKILL.md, and pipes up to 20 lines of test output back into the agent context. For a session iterating on a skill, this fires often.

## Why it matters

- The 4× glob is pure plumbing waste; the resolver already has the answer.
- The unconditional metrics regen is wall-clock cost per session + ~150 B of context injection that's unactionable when no pipeline is running.
- Optimizing dead code (auto-scan) wastes effort; deleting it removes a surface that doesn't earn its keep.
- The full `just test-skills` on every SKILL.md edit creates latency and noise while iterating, exactly when fast feedback matters most.

## Constraints

- **Lifecycle SKILL.md Step 2** uses the backlog glob to discover the feature file when resolving against various predicates (existing index.md vs not, ready-status check, etc.). Don't conflate Step 2's separate concerns into one call; do reuse the *resolved filename* across them.
- **`cortex-scan-lifecycle.sh`** SessionStart output is consumed by Claude — a missing or malformed payload could break session-context injection. Gating must preserve the well-formed path for the active-pipeline case.
- **Auto-scan deletion** must follow the project's "Workflow trimming" doctrine (per `requirements/project.md:23`): hard-delete with `CHANGELOG.md` entry naming the replacement entry point. If auto-scan is genuinely useful but only used rarely, optimization-via-`index.json` is acceptable.
- **`cortex-skill-edit-advisor.sh`**: the existing skill-test suite is the project's regression gate; whatever the scoped replacement looks like, it must still catch SKILL.md changes that break tests.

## Out of scope

- Replacing the scan-lifecycle hook architecture wholesale.
- Adding new tests; this is a hygiene-cuts ticket.
- Restructuring `cortex-resolve-backlog-item` itself.
- Removing the SessionStart context injection (the active-pipeline case is load-bearing).

## Acceptance signal

- Lifecycle SKILL.md Step 2 globs the backlog at most once per entry; subsequent steps reuse the resolved filename.
- `cortex-scan-lifecycle.sh` SessionStart metrics regen and append only fire when there's an active pipeline (or research-phase chooses a different predicate with documented rationale).
- Discovery auto-scan either: (a) is deleted entirely with the no-topic branch removed from SKILL.md and a CHANGELOG entry, or (b) reads `backlog/index.json` rather than walking individual files. The choice depends on the usage audit.
- `cortex-skill-edit-advisor.sh` runs a scoped check on SKILL.md edits — research-phase decides whether that's "test the changed skill only," "lint-only fast pass," or something else.

## Research hooks

- For auto-scan: gather actual usage signal (git history, hook telemetry if any, user query for whether anyone has invoked it). Decide delete vs. optimize.
- For scan-lifecycle metrics: what's the active-pipeline detection predicate? Existing partial gate at `:416` suggests the check is straightforward but worth verifying.
- For skill-edit-advisor: which sub-suite of `just test-skills` actually catches SKILL.md regressions? If only one of the four sub-suites is load-bearing here, scope to that. Or use the fast lint path that already exists.
- For Step 2's resolver reuse: confirm the resolver's `filename` field carries through the rest of Step 2's logic without ambiguity.

The audit's Tier 3 findings and the alternative-exploration outputs touch each of these. Treat their specifics as evidence, not as pre-decided answers.
