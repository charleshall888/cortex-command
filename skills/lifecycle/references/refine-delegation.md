# Refine Delegation Steps

Follow these steps when `cortex/lifecycle/{feature}/research.md` and/or `spec.md` is missing and lifecycle delegates to `/cortex-core:refine`.

1. **Read refine SKILL.md verbatim** (body-resolved path: `<REFINE_SKILL_MD>`) so lifecycle stays in sync as `/cortex-core:refine` evolves.

2. **Epic context + starting point** (read `<DISCOVERY_BOOTSTRAP_MD>` (`discovery-bootstrap.md`) once): follow its Refine Starting-Point Rules (always), and — when `epic_research_path` was recorded in Discovery Bootstrap — its Epic Context Injection protocol.

3. **Event logging during delegation**: lifecycle owns `cortex/lifecycle/{feature}/events.log`. Log these events as `/cortex-core:refine` completes each phase:

   - After the full Clarify phase completes (including §3a critic review and any Q&A) — **before Research begins** — log `lifecycle_start` (tier and criticality come from the post-critic, post-Q&A values in context):
     ```bash
     cortex-lifecycle-event log --event lifecycle_start --feature <name> --set tier=<simple|complex> --set criticality=<level>
     ```
   - After each phase completes, log a `phase_transition` event:
     ```bash
     cortex-lifecycle-event log --event phase_transition --feature <name> --set from=<from> --set to=<to>
     ```
     Log a `phase_transition` row per boundary: clarify→research, research→specify, specify→plan.

4. **Complexity escalation gates**: run the Research → Specify and Specify → Plan complexity-escalator gates per `<COMPLEXITY_ESCALATION_MD>`.

5. **Post-refine commit** (`post-refine-commit`): after the `phase_transition specify→plan` row or the `lifecycle_cancelled` row is logged — and before auto-advancing to Plan — read `<POST_REFINE_COMMIT_MD>` and follow it. On commit failure, halt and do not auto-advance to Plan.
