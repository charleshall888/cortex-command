# Criticality Override and Behavior Matrix

## Criticality Override

The user can change criticality at any time by requesting it explicitly. When overriding, append a `criticality_override` event:

```bash
cortex-lifecycle-event log --event criticality_override --feature <name> --set from=<old> --set to=<new>
```

An automated **Clarify reconciliation** (emitted by `cortex-refine reconcile-clarify --lifecycle-slug {slug}` at Spec-phase entry) carries an optional `gate: "clarify_reconcile"` field and is monotonic-up-only (never lowers a value). The user's criticality setting is always final: a later, ungated user `criticality_override` always supersedes the reconciliation by recency.

## Criticality Behavior Matrix

| Criticality | Review phase (023) | Orchestrator review (024) | Scaled behaviors (025) |
|-------------|-------------------|--------------------------|----------------------|
| low | Tier-based (skip for simple) | Skipped for simple; active for complex | Parallel research (sized by fan-out matrix), single plan |
| medium | Tier-based (skip for simple) | Active at phase boundaries | Parallel research (sized by fan-out matrix), single plan |
| high | Forced regardless of tier | Active at all phase boundaries | Parallel research (sized by fan-out matrix), single plan |
| critical | Forced regardless of tier | Active at all phase boundaries | Parallel research (sized by fan-out matrix), competing plans |

Per-role model resolution (which model each dispatch role uses at a given criticality) is owned by the `cortex-resolve-model` verb — run it at each dispatch site rather than reading a model from this table.

Research is **always parallel** at every criticality, sized by the tier × criticality fan-out matrix owned by the `/cortex-core:research` skill.

## Reading lifecycle state

Run `cortex-lifecycle-state --feature {feature}` (whole-state JSON) or `cortex-lifecycle-state --feature {feature} --field <x>` (single-field JSON) to read tier or criticality. It reduces the event log to the current values, **defaulting to `criticality=medium` / `tier=simple` when the key is absent or events.log is missing** — the CLI prints `{}` / omits absent keys, so apply these defaults yourself.

- **`"corrupted": true`**: if the output contains this field, events.log is corrupted and tier/criticality are unknowable — treat the feature as requiring review (run the critical-review / orchestrator-review gate) rather than applying the skip rule and defaulting.
