---
status: proposed
---

# Lifecycle event emission contract

## Context

Epic #336 routes deterministic lifecycle event emission through `cortex-lifecycle-event`, but supplies no explicit field-ordering/typing/serialization contract — so #330 (its foundation ticket) sets the de-facto one that #331/#332/#329 inherit.

## Decision

The verb emits a uniform `{ts, event, feature, <ordered --set/--set-json fields>}` row in canonical form (spaced `json.dumps` defaults, `%Y-%m-%dT%H:%M:%SZ` timestamps, append via flock + `O_APPEND`); `schema_version`/`worktree_path` are ordinary optional fields, not privileged keys; events whose canonical shape places `schema_version` *before* `feature` (the nested judgment events `plan_comparison`, `clarify_critic`, and #331's `pr_opened`) are exempt and stay hand-written rather than forcing positionable base-key machinery into the verb. The events-registry scanner recognizes `--event <name>` so gate coverage and typo-catching survive the migration.

## Trade-off / rejected alternatives

A uniform, low-machinery verb (no per-event schema registry) at the cost of a documented hand-written exception for schema_version-first/nested events, and a canonical-format definition that is byte-faithful to a *newly-defined* canonical (not to the already-format-mixed on-disk corpus). Chosen over a fully-general positionable verb (higher complexity, marginal offload for the exempt events). Hard to reverse (siblings build on the contract), surprising without context (why some events stay inline), and a real trade-off (uniformity vs. completeness) — meeting the three-criteria ADR gate.
