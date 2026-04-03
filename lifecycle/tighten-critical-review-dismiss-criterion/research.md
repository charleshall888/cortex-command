# Research: Tighten /critical-review Dismiss criterion

## Codebase Analysis

- **File**: `skills/critical-review/SKILL.md` — Step 4 Apply Feedback, Dismiss definition (line ~183)
- **Current Dismiss definition**: "the objection is already addressed in the artifact, misreads the stated constraints, or would expand scope in a direction clearly outside the requirements."
- **No other files reference the Dismiss definition** — it is self-contained in CR's Step 4. `clarify-critic.md` has its own parallel Apply/Dismiss/Ask framework (inlined in the same session), so changes to CR's definition do not cascade there.
- **CR is invoked by**: `lifecycle/SKILL.md` (specify + plan phases, complex tier), `lifecycle/references/specify.md`, `lifecycle/references/plan.md`, `discovery/references/research.md` (unconditional). Any behavioral change to Step 4 affects all these call sites.

## Problem Statement (from session analysis)

The `/critical-review` skill dispatches a fresh agent to reduce anchoring bias in critique generation. However, the Apply/Dismiss/Ask disposition loop (Step 4) runs in the orchestrator's main conversation context — the same anchored context where the artifact was produced.

Two distinct failure modes exist when dismissing a fresh-agent objection:

**(a) Context-informed dismissal** — The orchestrator dismisses because they have accurate information the fresh agent lacks (e.g., user stated a constraint in conversation). This is **correct** behavior — the disposition loop working as designed.

**(b) Investment-driven dismissal** — The orchestrator dismisses because they remember their own prior reasoning and are protecting a decision. This **is** anchoring bias — the Dismiss is not grounded in the artifact, only in the orchestrator's memory.

These look identical from the outside, and often from the inside too. The current Dismiss definition does not distinguish between them, which means investment-driven dismissals pass silently.

## Key Finding

A distinguishing criterion exists: **if the dismissal justification cannot be pointed to in the artifact text and lives only in conversation memory, it is anchoring, not a legitimate dismissal.** Legitimate dismissals are always groundable in artifact text (the artifact addresses the objection, the artifact's constraints exclude the concern, the artifact's scope statement rules it out). Investment-driven dismissals require reaching back into conversation history.

## Open Questions

None — the fix is unambiguous given the above.
