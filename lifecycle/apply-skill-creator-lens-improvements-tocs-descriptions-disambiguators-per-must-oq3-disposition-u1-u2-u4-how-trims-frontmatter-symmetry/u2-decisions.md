---
wholesale_remove: [skills/lifecycle/references/specify.md]
---

# U2 named-consumer decisions

Per-row KEEP/DROP decisions across the 12 corpus files for the U2 trim. Rule: a row stays if Reality column references a specific identifier (function name, file path, schema key, or named test/validator/contract). Generic prose without a named consumer → DROP.

`skills/discovery/references/decompose.md` is listed in the corpus but its `## Constraints` section is a bullet list, not a Thought/Reality table — the named-consumer rule applies vacuously (zero table rows). No edit to that file.

## skills/discovery/references/clarify.md

- [skills/discovery/references/clarify.md:62] | KEEP | `/cortex-core:refine`, `/cortex-core:lifecycle`
- [skills/discovery/references/clarify.md:63] | KEEP | `§3` (backlog coverage check section)
- [skills/discovery/references/clarify.md:64] | DROP | reality_text="High confidence on all four dimensions = proceed without questions. A well-stated topic should flow through Clarify quickly."
- [skills/discovery/references/clarify.md:64] | KEEP | `aim, domain, novelty, alignment` (named rubric dimensions)

## skills/discovery/references/auto-scan.md

- [skills/discovery/references/auto-scan.md:83] | DROP | reality_text="No state is written until a topic is selected and the normal discovery flow begins. Auto-scan is purely read-only."
- [skills/discovery/references/auto-scan.md:84] | DROP | reality_text="The user picks one. Parallel discovery on multiple gaps is not supported by this mode."
- [skills/discovery/references/auto-scan.md:85] | KEEP | `requirements/*.md`
- [skills/discovery/references/auto-scan.md:84] | KEEP | `research.md`, `plan.md`
- [skills/discovery/references/auto-scan.md:85] | KEEP | `/cortex-core:discovery`

## skills/lifecycle/references/clarify.md

- [skills/lifecycle/references/clarify.md:127] | KEEP | `§6` (criteria definition section)
- [skills/lifecycle/references/clarify.md:128] | KEEP | `≤5 targeted questions`, `Specify`, `Research` (named phases and contract)
- [skills/lifecycle/references/clarify.md:129] | KEEP | `intent, scope, requirements alignment` (named rubric dimensions)
- [skills/lifecycle/references/clarify.md:129] | DROP | reality_text="High confidence on all three dimensions = proceed without questions. Do not manufacture uncertainty."

## skills/lifecycle/references/clarify-critic.md

- [skills/lifecycle/references/clarify-critic.md:161] | DROP | reality_text="Always runs — the critic's job is to challenge whether those High ratings are deserved, not to rubber-stamp them."
- [skills/lifecycle/references/clarify-critic.md:162] | KEEP | `disposition framework`
- [skills/lifecycle/references/clarify-critic.md:163] | KEEP | `§4` Q&A
- [skills/lifecycle/references/clarify-critic.md:164] | KEEP | named two-input contract: `confidence assessment` and `source material`
- [skills/lifecycle/references/clarify-critic.md:165] | KEEP | `clarify_critic` event (schema key)
- [skills/lifecycle/references/clarify-critic.md:166] | KEEP | `applied_fixes` (schema key)
- [skills/lifecycle/references/clarify-critic.md:166] | KEEP | `dismissals` array, `events.log`, `§4`

## skills/lifecycle/references/specify.md

- [skills/lifecycle/references/specify.md:177] | DROP | reality_text="Obvious requirements still have hidden edge cases. The interview surfaces what you assume you already know."
- [skills/lifecycle/references/specify.md:177] | DROP | reality_text="Knowing what to build is not the same as having agreed requirements. The spec is the contract."
- [skills/lifecycle/references/specify.md:177] | DROP | reality_text="Even simple features have assumptions worth validating. The interview adapts — if everything is clear, it finishes quickly."
- [skills/lifecycle/references/specify.md:177] | DROP | reality_text="Not sure = ask the user. The user is present during spec; implementation may run overnight without them. Defer only when implementation-level context is genuinely required and unavailable at spec time."

(All 4 rows DROP — file is in `wholesale_remove` list. Task 9 removes the entire Thought/Reality table; the `## Hard Gate` heading and intro paragraph remain.)

## skills/lifecycle/references/plan.md

- [skills/lifecycle/references/plan.md:305] | DROP | reality_text="Clear requirements still need a task breakdown. Planning is about HOW to decompose the work, not WHAT to build."
- [skills/lifecycle/references/plan.md:306] | DROP | reality_text="Figuring it out while coding means re-doing work when early assumptions prove wrong. Plan once, implement once."
- [skills/lifecycle/references/plan.md:307] | KEEP | `code budget`, `function bodies` (named contract from §3)
- [skills/lifecycle/references/plan.md:308] | KEEP | `research/spec artifacts` (named contract for backlog item validation)
- [skills/lifecycle/references/plan.md:309] | KEEP | `self-sealing` (named anti-pattern), `test commands, pre-existing state, prior-task outputs` (named alternatives)

## skills/lifecycle/references/implement.md

- [skills/lifecycle/references/implement.md:296] | DROP | reality_text="Each task is self-contained by design. The plan already decomposed the work so each task has everything it needs. Reading other tasks risks scope creep."
- [skills/lifecycle/references/implement.md:297] | DROP | reality_text="Combined tasks are harder to verify, harder to revert, and harder to review. One task, one commit, one concern."
- [skills/lifecycle/references/implement.md:298] | DROP | reality_text="Small tasks with clear scope succeed reliably. Large tasks with vague scope fail unpredictably. Trust the plan's sizing."
- [skills/lifecycle/references/implement.md:299] | KEEP | `batch model`, `checkpoint writes` (named contract)
- [skills/lifecycle/references/implement.md:300] | DROP | reality_text="Deviating from spec paths breaks traceability between phases. If the spec path is wrong, flag it — don't fix it silently."
- [skills/lifecycle/references/implement.md:301] | KEEP | `/cortex-core:commit`, `Skill tool` (named tool/command contract)

## skills/lifecycle/references/review.md

- [skills/lifecycle/references/review.md:214] | DROP | reality_text="Review each requirement against the spec individually. Gestalt impressions miss specific gaps."
- [skills/lifecycle/references/review.md:215] | DROP | reality_text="The reviewer does not modify files. Flagging issues preserves separation of concerns and creates a paper trail."
- [skills/lifecycle/references/review.md:216] | KEEP | `PARTIAL` (schema key — review status)
- [skills/lifecycle/references/review.md:217] | KEEP | `verdict` field, `APPROVED`, `CHANGES_REQUESTED`, `REJECTED` (schema keys/values)
- [skills/lifecycle/references/review.md:216] | KEEP | `§1`, `detected` (schema key for drift logging)
- [skills/lifecycle/references/review.md:217] | KEEP | `verdict`, `APPROVED`, `requirements` docs

## skills/lifecycle/references/orchestrator-review.md

- [skills/lifecycle/references/orchestrator-review.md:180] | DROP | reality_text="Evaluate every checklist item individually. Gestalt impressions miss specific gaps. A single unflagged issue becomes the user's problem."
- [skills/lifecycle/references/orchestrator-review.md:181] | DROP | reality_text="The orchestrator does not edit phase artifacts directly. Dispatching fixes preserves separation of concerns and creates an audit trail via event logging."
- [skills/lifecycle/references/orchestrator-review.md:181] | DROP | reality_text="Flag it. The fix agent may resolve it quickly. Letting minor issues pass compounds across phases — a vague spec item becomes a broken plan task becomes a failed implementation."
- [skills/lifecycle/references/orchestrator-review.md:180] | KEEP | `2-cycle cap` (named contract)
- [skills/lifecycle/references/orchestrator-review.md:181] | KEEP | `low criticality, simple complexity` (named matrix dimensions)

## skills/lifecycle/references/complete.md

- [skills/lifecycle/references/complete.md:100] | DROP | reality_text="The review checked spec compliance and code quality, not test execution. Run the tests."
- [skills/lifecycle/references/complete.md:100] | DROP | reality_text="Failing tests mean the feature is not verified. Fix them now while context is fresh."
- [skills/lifecycle/references/complete.md:100] | KEEP | `lifecycle directory` (named directory reference)

## skills/refine/references/clarify-critic.md

- [skills/refine/references/clarify-critic.md:209] | DROP | reality_text="Always runs — the critic's job is to challenge whether those High ratings are deserved, not to rubber-stamp them."
- [skills/refine/references/clarify-critic.md:210] | KEEP | `disposition framework`
- [skills/refine/references/clarify-critic.md:211] | KEEP | `§4` Q&A
- [skills/refine/references/clarify-critic.md:212] | KEEP | `bin/cortex-load-parent-epic`, `## Parent Epic Alignment`, `<parent_epic_body>` markers
- [skills/refine/references/clarify-critic.md:213] | KEEP | `clarify_critic` event (schema key)
- [skills/refine/references/clarify-critic.md:214] | KEEP | `applied_fixes` (schema key)
- [skills/refine/references/clarify-critic.md:214] | KEEP | `dismissals` array, `events.log`, `§4`

## Summary

| File | KEEP | DROP | Wholesale-remove |
|------|------|------|------------------|
| discovery/clarify.md | 3 | 1 | no |
| discovery/auto-scan.md | 3 | 2 | no |
| discovery/decompose.md | n/a | n/a | n/a (no table) |
| lifecycle/clarify.md | 3 | 1 | no |
| lifecycle/clarify-critic.md | 6 | 1 | no |
| lifecycle/specify.md | 0 | 4 | **yes** |
| lifecycle/plan.md | 3 | 2 | no |
| lifecycle/implement.md | 2 | 4 | no |
| lifecycle/review.md | 4 | 2 | no |
| lifecycle/orchestrator-review.md | 2 | 3 | no |
| lifecycle/complete.md | 1 | 2 | no |
| refine/clarify-critic.md | 6 | 1 | no |
| **Total** | **33** | **23** | 1 file |

<!-- u2-decisions:complete -->
