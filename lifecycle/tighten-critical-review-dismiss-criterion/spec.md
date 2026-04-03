# Specification: Tighten /critical-review Dismiss criterion

## Problem Statement

The `/critical-review` Step 4 Dismiss definition allows the orchestrator to dismiss fresh-agent objections using justifications that live only in conversation memory — not in the artifact under review. This is indistinguishable from anchoring bias (protecting prior decisions) and silently erodes the benefit of dispatching a fresh, unanchored reviewer. A tighter criterion prevents this: Dismiss is only valid when the reason is traceable to the artifact text itself.

## Requirements

1. **[M] Anchor check added to Dismiss definition**: The Dismiss definition in `skills/critical-review/SKILL.md` Step 4 must include a criterion that flags conversation-memory-only justifications as candidates for Ask.
   - AC: The Dismiss definition contains an "Anchor check" or equivalent that states: if the dismissal reason cannot be pointed to in the artifact text and lives only in conversation memory, treat it as Ask instead.
   - AC: The anchor check explicitly labels this pattern as anchoring, not a legitimate dismissal.
   - AC: The existing Dismiss conditions (already addressed in artifact, misreads constraints, expands scope) are preserved unchanged.

## Non-Requirements

- This spec does NOT change the Apply or Ask definitions.
- This spec does NOT change the fresh-agent dispatch prompt (Steps 2a–2d).
- This spec does NOT add a mechanism to detect or log when the anchor check is triggered.

## Edge Cases

- **Dismissal grounded in project requirements loaded at session start**: If the orchestrator dismisses based on `requirements/project.md` content (loaded into context, not in the artifact), this is a legitimate dismissal — requirements are authoritative context, not conversation memory. The anchor check should not flag this. The key distinction is whether the context is *durable and external* (requirements files, spec, plan) vs. *ephemeral conversation memory* (things said earlier in the session that aren't in any artifact).

## Technical Constraints

- The Dismiss definition is a single paragraph in Step 4. The anchor check should be appended as a sentence to that paragraph, not a separate bullet or subsection.
- `clarify-critic.md` has its own inlined Apply/Dismiss/Ask framework — it should receive the same anchor check in a separate change (not this spec).
