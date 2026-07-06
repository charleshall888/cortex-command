# Orchestrator Phase Review (Discovery)

Discovery has no applicability skip rule — orchestrator review always runs for every discovery topic regardless of complexity or criticality.

## Protocol

Read the canonical orchestrator-review protocol from the lifecycle sibling — the body-resolved path propagated via discovery SKILL.md as **orchestrator-review** → `skills/lifecycle/references/orchestrator-review.md`. Its sections (Execute Review, Handle Verdict, Fix Dispatch, Escalation) apply as written, with two discovery-specific substitutions:

1. **Fix Agent path and persona**: in the fix-agent prompt template (body-resolved **fix-agent-prompt-template** path, discovery SKILL.md propagation), replace `{feature}` with `{topic} discovery topic` and `cortex/lifecycle/{feature}/{artifact}` with `cortex/research/{topic}/{artifact}`. The return envelope is plain prose (`changed [path] — [rationale]`), not lifecycle's YAML envelope.
2. **Checklist**: use the Post-Research Checklist below instead of the lifecycle Post-Specify / Post-Plan checklists.

## Checklists

### Post-Research Checklist

Evaluate against `cortex/research/{topic}/research.md`:

| # | Item | Criteria |
|---|------|----------|
| R1 | Research questions answered concretely | Each question in the Codebase Analysis and Web Research sections has a specific finding, not a hand-wavy generalization |
| R2 | Feasibility grounded in evidence | Feasibility assessment cites specific codebase patterns, API capabilities, or documented behavior — not just "this should be possible" |
| R3 | Critical unknowns addressed | No critical unknowns are left unacknowledged; if unresolvable, they appear in Open Questions with explanation of why they could not be resolved |
| R4 | Open questions are genuine | Items in Open Questions represent true unknowns that require user input for decomposition choices, or questions that could not be resolved through research (with an explanation of why). Research feeds directly into Decompose — questions that could have been answered through more investigation are not acceptable deferrals. |
| R5 | Dependency verification complete | If external dependencies exist, the Web & Documentation Research section confirms specific capabilities (endpoints, methods, flags) are present and not deprecated |

## Constraints

| Thought | Reality |
|---------|---------|
| "The artifact looks mostly fine, I'll pass it through" | Evaluate every checklist item individually. Gestalt impressions miss specific gaps. A single unflagged issue becomes the user's problem. |
| "I can fix this issue myself instead of dispatching" | The orchestrator does not edit phase artifacts directly. Dispatching fixes preserves separation of concerns and creates an audit trail via event logging. |
| "This issue is minor, not worth a fix cycle" | Flag it. The fix agent may resolve it quickly. Letting minor issues pass compounds across phases — a weak research finding becomes a poorly-prioritized backlog ticket becomes a failed implementation. |
| "The fix made things worse, I should try a third cycle" | The 2-cycle cap is firm. Escalate to the user. More iteration rounds decrease quality, not increase it. |
