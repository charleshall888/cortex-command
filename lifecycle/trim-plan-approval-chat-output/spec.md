# Specification: trim-plan-approval-chat-output

## Problem Statement

The plan phase approval summary shown in chat includes five fields — Produced, Value, Trade-offs, Veto surface, and Scope boundaries — making it longer than it needs to be for the triage decision (approve vs. read deeper). Veto surface and Scope boundaries are detail-level content; users who care about them should read the plan artifact. The fix is to remove those two fields from the chat approval surface and add them as named sections in the plan.md artifact template, so they're preserved but accessible on demand. The spec phase has the same problem with the same two fields; it is also fixed here.

## Requirements

1. `output-floors.md` Approval Surface Floor table must contain exactly three rows: Produced, Value, Trade-offs. The Veto surface and Scope boundaries rows are removed. A prose note is added after the table stating that those fields belong in the plan artifact, not the chat approval summary.
   - Acceptance criteria: `grep -c '| \*\*Veto surface\*\* \|| | \*\*Scope boundaries\*\* |' claude/reference/output-floors.md` = 0 (matches only bold-formatted table row labels, not prose mentions).

2. `plan.md` §4 (User Approval) inline bullet list must list only Produced and Trade-offs. The Veto surface and Scope boundaries bullets are removed.
   - Acceptance criteria: `grep -c '- \*\*Veto surface\*\*\|- \*\*Scope boundaries\*\*' skills/lifecycle/references/plan.md` = 0 (matches only bullet-list entries, not section headers like `## Scope Boundaries`).

3. `plan.md` §3 (Write Plan Artifact) artifact template must include `## Veto Surface` and `## Scope Boundaries` as named sections after `## Verification Strategy`.
   - Acceptance criteria: `grep -c '## Veto Surface\|## Scope Boundaries' skills/lifecycle/references/plan.md` = 2.

4. `specify.md` §4 (User Approval) inline bullet list must list only Produced, Value, and Trade-offs. The Veto surface and Scope boundaries bullets are removed.
   - Acceptance criteria: `grep -c 'Veto surface\|Scope boundaries' skills/lifecycle/references/specify.md` in the §4 section = 0.

## Non-Requirements

- The spec artifact template (`specify.md` §3) is not changed. `## Non-Requirements` and `## Open Decisions` already provide equivalent coverage.
- Trade-offs is not moved into the plan artifact — it stays in chat output only.
- The phase transition floor in `output-floors.md` is not changed.
- `orchestrator-review.md` is not changed.
- Historical lifecycle artifacts with grep verification checks referencing "Veto surface" are not touched — they are immutable records.
- The pre-existing discrepancy (Value is in `output-floors.md` but absent from `plan.md` §4 inline list) is out of scope. Value stays in the floor definition; the inline list inconsistency is left as-is.

## Edge Cases

- **The precedence rule in output-floors.md**: The floor supersedes inline field names when both are loaded. After this change, the floor will list 3 fields (Produced, Value, Trade-offs) and the inline list in plan.md §4 will also list 2 (Produced, Trade-offs). The Value discrepancy in plan.md §4 is pre-existing and out of scope. The important thing is that Veto surface and Scope boundaries are removed from both, so neither the floor nor the inline list can bring them back into the chat.

- **Overnight plan agents**: Plan agents produce artifacts; they don't generate approval summaries. The plan.md artifact template changes (Req 3) apply only to what's written to disk. Overnight sessions are not affected by approval surface chat format (which is interactive-only).

## Changes to Existing Behavior

- REMOVED: Veto surface and Scope boundaries from plan phase chat approval summary
- REMOVED: Veto surface and Scope boundaries from spec phase chat approval summary
- ADDED: `## Veto Surface` and `## Scope Boundaries` sections to `plan.md` artifact template — these sections now appear in plan files written to disk

## Technical Constraints

- output-floors.md's precedence rule means changes to the floor automatically affect all approval surfaces that load it. Belt-and-suspenders: also update the inline bullet lists in plan.md and specify.md so that neither source can restore the removed fields.
- Plan.md §3 artifact template changes affect all future plan artifacts; they do not retroactively modify existing plan.md files already on disk.

## Open Decisions

_(None — all decisions resolved at spec time.)_
