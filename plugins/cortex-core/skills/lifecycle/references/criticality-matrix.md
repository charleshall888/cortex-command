# Criticality Override and Behavior Matrix

## Criticality Override

The user can change criticality at any time by asking. On override, append:

`cortex-lifecycle-event criticality-override --feature <name> --from <old> --to <new>`

An automated **Clarify reconciliation** (from `cortex-refine reconcile-clarify --lifecycle-slug {slug}` at Spec-phase entry) carries `gate: "clarify_reconcile"` and is monotonic-up-only (never lowers a value). A later, ungated user `criticality_override` always supersedes it by recency — the user's setting is final.

## Criticality Behavior Matrix

Research is **always parallel** at every criticality, sized by the tier × criticality fan-out matrix owned by `/cortex-core:research`. Per-role model resolution is owned by the `cortex-resolve-model` verb — run it at each dispatch site rather than reading a model from this table.

| Criticality | Review phase | Orchestrator review | Planning |
|-------------|-------------|--------------------|---------|
| low | tier-based (skip for simple) | skipped for simple, active for complex | single plan |
| medium | tier-based (skip for simple) | active at phase boundaries | single plan |
| high | forced regardless of tier | active at all phase boundaries | single plan |
| critical | forced regardless of tier | active at all phase boundaries | competing plans |

## Reading lifecycle state

Run `cortex-lifecycle-state --feature {feature}` (whole-state JSON) or `cortex-lifecycle-state --feature {feature} --field <x>` (single-field JSON) to read tier or criticality. It reduces the event log to current values, **defaulting to `criticality=medium` / `tier=simple` when the key is absent or events.log is missing** — the CLI prints `{}` or omits absent keys, so apply these defaults yourself.

- **`"corrupted": true`**: if the output contains this field, events.log is corrupted and tier/criticality are unknowable — treat the feature as requiring review (run the critical-review / orchestrator-review gate) rather than applying the skip rule and defaulting.
