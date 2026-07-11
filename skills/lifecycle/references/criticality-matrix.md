# Criticality Override and Behavior Matrix

## Criticality Override

The user can change criticality at any time by asking:

`cortex-lifecycle-event criticality-override --feature <name> --from <old> --to <new>`

An automated **Clarify reconciliation** (`cortex-refine reconcile-clarify --lifecycle-slug {slug}` at Spec-phase entry) carries `gate: "clarify_reconcile"` and is monotonic-up-only (never lowers a value). A later, ungated user `criticality_override` always supersedes it by recency.

## Criticality Behavior Matrix

Research is **always parallel** at every criticality, sized by the tier × criticality fan-out matrix owned by `/cortex-core:research`. Per-role model resolution is owned by `cortex-resolve-model` — run it at each dispatch site rather than reading a model from this table.

| Criticality | Review phase | Orchestrator review | Planning |
|-------------|-------------|--------------------|---------|
| low | tier-based (skip for simple) | skipped for simple, active for complex | single plan |
| medium | tier-based (skip for simple) | active at phase boundaries | single plan |
| high | forced regardless of tier | active at all phase boundaries | single plan |
| critical | forced regardless of tier | active at all phase boundaries | competing plans |

## Reading lifecycle state

Run `cortex-lifecycle-state --feature {feature}` (whole-state JSON) or with `--field <x>` (single-field JSON) for tier or criticality. It reduces the event log to current values, defaulting to `criticality=medium` / `tier=simple` when the key is absent or events.log is missing — the CLI prints `{}` or omits absent keys, so apply these defaults yourself.

- **Implement→{review|complete} routing**: owned by `cortex-lifecycle-implement-transition` (the implement-cluster verb reads tier/criticality through this reducer and applies the "Review when criticality ∈ {high, critical} OR tier = complex, else Complete" rule in its body) — not restated in prose here, to avoid a prose/code drift pair. implement.md §4 hands off to the verb and routes on its returned `state`.
- **`"corrupted": true`**: events.log is corrupted and tier/criticality are unknowable — treat the feature as requiring review (run the critical-review / orchestrator-review gate) rather than the skip rule and defaulting.
