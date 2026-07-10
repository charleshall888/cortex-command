# Post-Specify Checklist

Orchestrator-review `specify`-phase checklist (`spec.md`); rate each item **pass** or **flag**. Shared protocol and Binary-checkable rule: `orchestrator-review.md`.

| # | Item | Criteria |
|---|------|----------|
| S1 | Binary-checkable acceptance criteria | All criteria satisfy the Binary-checkable rule (shared protocol); prose like "confirm it works" fails. |
| S2 | Edge cases handled | Edge Cases covers failure modes, unexpected inputs, boundaries, and concurrency relevant to the feature. |
| S3 | MoSCoW justified | Must/should/won't reflect real priority, not "everything is must-have". |
| S4 | Non-requirements are concrete boundaries | Names concrete scope boundaries, not vague "not in scope for now". |
| S5 | Constraints grounded | Cite specific codebase patterns, ADRs, or architectural decisions — not generic best practices. |
| S6 | Behavioral changes documented | Modifying/removing/extending existing behavior gets a `## Changes to Existing Behavior` section (MODIFIED/REMOVED/ADDED); omit only for pure-greenfield work. |
| S7 | Spec phases present | `## Phases` with ≥1 phase; each requirement's `**Phase**` tag matches one. Skip on `criticality=low AND tier=simple`. |
