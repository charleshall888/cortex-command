# Research: trim-plan-approval-chat-output

## Summary

The lifecycle plan and spec phase approval summaries (chat output) include five fields: Produced, Value, Trade-offs, Veto surface, and Scope boundaries. The user finds Veto surface and Scope boundaries excessive in chat — they just want what's needed to approve or decide to read the artifact. Both fields should be removed from the chat approval surface and moved into the plan artifact file (where they don't currently exist as named sections).

## Codebase Analysis

### Active instruction files with "Veto surface" / "Scope boundaries" in approval context

Three files define or carry the approval surface fields:

1. **`claude/reference/output-floors.md`** (lines 30–34): The canonical approval surface floor definition. Lists all five fields as required in chat at approval gates. The precedence rule: "when this document is loaded alongside inline field names in SKILL.md or phase reference files, the expanded definitions here supersede the inline names." This is the authoritative source — changing it changes behavior for all approval surfaces that load it.

2. **`skills/lifecycle/references/plan.md`** §4 (lines 243–249): Inline bullet list of approval surface fields in the user approval section. Lists Produced, Trade-offs, Veto surface, Scope boundaries (Value absent from inline list despite being in output-floors.md — pre-dates the Value addition). With the precedence rule, output-floors.md supersedes these when loaded.

3. **`skills/lifecycle/references/specify.md`** §4 (lines 156–162): Same inline bullet list as plan.md for the spec phase approval. Lists Produced, Value, Trade-offs, Veto surface, Scope boundaries.

### No other active callers

A grep across all `.md` files in the repo found no other active skill instruction files referencing "Veto surface" or "Scope boundaries" in approval context. All other occurrences are:
- Historical lifecycle artifacts (immutable records from past features)
- Backlog item bodies (not executed as instructions)
- Research and spec documents from the define-output-floors feature (historical)
- The `orchestrator-review.md` mention of "scope boundaries" refers to spec quality (S4 checklist: Non-Requirements completeness), not to the approval surface chat field

### Plan artifact: no equivalent sections exist

The current `plan.md` artifact template (§3) produces: Overview, Tasks, Verification Strategy. It has no Trade-offs, Veto Surface, or Scope Boundaries sections. These concepts only appear in the chat approval output (§4). If removed from chat without being added to the artifact, they are lost entirely.

### Spec artifact: equivalent sections already exist

The `spec.md` template already has:
- `## Non-Requirements` — equivalent to Scope Boundaries
- `## Open Decisions` — partially equivalent to Veto Surface (captures judgment calls unresolved at spec time)

For the spec phase: no new artifact sections needed. The user can read spec.md and find Non-Requirements for scope and Open Decisions for unresolved judgment calls.

### Value field note

`output-floors.md` includes "Value" in the Approval Surface Floor, but `plan.md` §4's inline bullet list predates this addition and doesn't include it. The user's example output didn't show a Value field — which suggests Value either isn't being shown in practice (the inline list is being followed over the floor) or is intermittently included. Value should remain in the floor definition; it's there intentionally per prior feedback.

## Open Questions

_(None — all research questions resolved.)_
