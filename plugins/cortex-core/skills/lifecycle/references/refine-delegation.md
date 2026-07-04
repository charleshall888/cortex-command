# Refine Delegation Steps

Follow when `cortex/lifecycle/{feature}/research.md` and/or `spec.md` is missing and lifecycle delegates to `/cortex-core:refine`.

1. **Read refine SKILL.md verbatim** (`<REFINE_SKILL_MD>`) so lifecycle stays in sync as `/cortex-core:refine` evolves.
2. **Epic context + starting point** — read `<DISCOVERY_BOOTSTRAP_MD>` (`discovery-bootstrap.md`) once: follow its Refine Starting-Point Rules (always), and — when `epic_research_path` was recorded in Discovery Bootstrap — its Epic Context Injection protocol.
3. **Event logging** — lifecycle owns `cortex/lifecycle/{feature}/events.log`. As `/cortex-core:refine` completes each phase:
   - After the full Clarify phase (including §3a critic review and Q&A), **before Research begins**, log `lifecycle_start` (tier/criticality from the post-critic, post-Q&A values in context): `cortex-lifecycle-event lifecycle-start --feature <name> --tier <simple|complex> --criticality <level>`
   - After each phase, log a `phase_transition` — one row per boundary (clarify→research, research→specify, specify→plan): `cortex-lifecycle-event phase-transition --feature <name> --from <from> --to <to>`
4. **Complexity escalation** — run the Research → Specify and Specify → Plan complexity-escalator gates per `<COMPLEXITY_ESCALATION_MD>`.
5. **Post-refine commit** — after the `phase_transition specify→plan` (or `lifecycle_cancelled`) row is logged and before auto-advancing to Plan, read `<POST_REFINE_COMMIT_MD>` and follow it. On commit failure, halt and do not auto-advance to Plan.
