# Specification: Define output floors for interactive approval and overnight compaction

## Problem Statement

Phase transition summaries and approval surfaces across the lifecycle skill have no minimum content requirements — the sole instruction is "briefly summarize what was accomplished and what comes next." This leaves output quality to the model's judgment, which produces inconsistent results: sometimes omitting key decisions, sometimes over-summarizing. Interactive users need enough information in these summaries to make informed approval decisions without reading full artifacts. The overnight pipeline's file-based architecture already handles compaction survival for critical information, but orchestrator decision rationale is a gap — it lives only in conversation and can be lost to compaction. This ticket defines the minimum content requirements as a reference document that downstream tickets #052 and #053 consume as their rubric.

## Requirements

1. **Create `claude/reference/output-floors.md`**: A reference document following the existing pattern (`audience: agent` frontmatter, ~100-150 lines). Contains three sections: a phase transition floor, an approval surface floor, and an overnight file-based addendum.
   - Acceptance criteria: `test -f claude/reference/output-floors.md`, pass if file exists. `grep -c 'audience: agent' claude/reference/output-floors.md` = 1.

2. **Phase transition floor**: Define a required-fields checklist (no prose examples) specifying the minimum fields every phase transition summary must include:
   - **Decisions**: Key decisions made during this phase (or "None" if the phase was mechanical)
   - **Scope delta**: Changes to scope, approach, or plan since last phase (or "None")
   - **Blockers**: Active blockers, escalations, or deferred questions (or "None")
   - **Next**: Next phase name and what it will do
   - Acceptance criteria: `grep -c 'Decisions\|Scope delta\|Blockers\|Next' claude/reference/output-floors.md` >= 4.

3. **Approval surface floor**: Define a required-fields checklist for output presented to the user for approval (spec approval, plan approval):
   - **Produced**: One-line summary of the artifact
   - **Trade-offs**: Alternatives considered and rationale for chosen approach
   - **Veto surface**: Items the user might disagree with or want to change
   - **Scope boundaries**: What is explicitly excluded
   - Acceptance criteria: `grep -c 'Produced\|Trade-offs\|Veto surface\|Scope boundaries' claude/reference/output-floors.md` >= 4.

4. **Overnight file-based addendum**: A section stating that file-based artifacts (research.md, spec.md, plan.md, review.md, events.log) bypass compaction and require no additional conversational compaction resilience. Defines the rationale field convention: orchestrator decision rationale should be captured in a `rationale` field on events.log entries when the orchestrator resolves escalations or makes non-obvious feature selection decisions. This ticket defines and documents the convention; enforcement requires a follow-up ticket to modify orchestrator prompts.
   - Acceptance criteria: `grep -c 'rationale' claude/reference/output-floors.md` >= 1.

5. **Replace lifecycle SKILL.md phase transition instruction**: Replace the instruction at line 273 ("After completing a phase artifact, announce the transition and proceed to the next phase automatically. Between phases, briefly summarize what was accomplished and what comes next.") with a cross-reference to `output-floors.md` that preserves the auto-proceed behavior while specifying the minimum content fields. The cross-reference must include the phase transition field names inline (Decisions, Scope delta, Blockers, Next) as a minimum-viable fallback when the reference doc is not loaded. When both the inline fields and the reference doc are present, the reference doc's expanded definitions supersede the inline names.
   - Acceptance criteria: `grep -c 'output-floors' skills/lifecycle/SKILL.md` >= 1. `grep -c 'briefly summarize what was accomplished' skills/lifecycle/SKILL.md` = 0.

6. **Inline approval surface fields in phase reference files**: Add the approval surface field names (Produced, Trade-offs, Veto surface, Scope boundaries) to the approval sections of `skills/lifecycle/references/specify.md` (§4 User Approval) and the plan phase reference file's approval section. These phase references are already loaded when approval happens, providing a minimum-viable fallback for the approval surface floor without depending on conditional loading.
   - Acceptance criteria: `grep -c 'Produced\|Trade-offs\|Veto surface\|Scope boundaries' skills/lifecycle/references/specify.md` >= 4.

7. **Add conditional loading trigger to Agents.md**: Add a row to the conditional loading table at `claude/Agents.md` lines 20-24 with trigger "Writing phase transition summaries, approval surfaces, or editing skill output instructions" and target `~/.claude/reference/output-floors.md`.
   - Acceptance criteria: `grep -c 'output-floors' claude/Agents.md` >= 1.

8. **Downstream consumption note**: The document must include a brief section noting that this document serves as the constraint source for #052 (skill prompt audit) and #053 (subagent output formats), enabling those tickets to assess whether each skill's output meets the defined floors.
   - Acceptance criteria: Interactive/session-dependent: the note references tickets #052 and #053 by number.

## Non-Requirements

- Per-skill calibration of output floors — that is #052's responsibility after this floor is defined
- Subagent output format specifications — that is #053's responsibility
- Discovery SKILL.md phase transition replacement — discovery's "summarize findings" instruction is epistemological ("what did we learn"), not progress-oriented ("what did we decide"); the lifecycle-native checklist fields would routinely produce "None" for 2-3 of 4 fields, a quality regression. Per-skill calibration for discovery is #052's job.
- Compaction instruction customization (custom `## Compact Instructions` in CLAUDE.md)
- Conversational compaction-resilience markers for overnight — the file-based architecture already handles this
- Category-based skill classification system (evidentiary, synthesis, orchestration, utility) — abandoned per adversarial review finding that categories rot without tooling enforcement
- Changes to the compaction algorithm or compaction thresholds
- Programmatic enforcement of the rationale field convention — this ticket defines the convention; enforcement requires orchestrator prompt changes tracked separately

## Edge Cases

- **Skills without phase transitions** (commit, pr, backlog, dev): Output floors do not apply. The reference doc should not reference these skills.
- **Phase transitions with nothing to report for a field**: The checklist uses "None" — fields are always present even when empty, providing structural consistency.
- **Conditional loading failure (phase transitions)**: The SKILL.md cross-reference includes the phase transition field names inline (Decisions, Scope delta, Blockers, Next) as a minimum-viable fallback. This is not the full specification — the reference doc's expanded definitions supersede the inline names when both are loaded.
- **Conditional loading failure (approval surfaces)**: The approval surface field names (Produced, Trade-offs, Veto surface, Scope boundaries) are inlined in the phase reference files (specify.md, plan.md) which are already loaded when approval happens. This provides degraded-floor protection for the higher-stakes approval interaction.
- **Orchestrator rationale for routine decisions**: Not every orchestrator decision needs rationale. The convention applies only to escalation resolutions and non-obvious feature selection decisions (e.g., skipping a feature, reordering rounds). Routine forward-progress decisions do not require it.

## Changes to Existing Behavior

- MODIFIED: `skills/lifecycle/SKILL.md` line 273 — "briefly summarize what was accomplished and what comes next" replaced with cross-reference to output-floors.md including inline phase transition field names and precedence rule
- MODIFIED: `skills/lifecycle/references/specify.md` §4 — approval section updated with inline approval surface field names
- MODIFIED: Plan phase reference file approval section — updated with inline approval surface field names
- ADDED: `claude/reference/output-floors.md` — new reference document defining phase transition floor, approval surface floor, and overnight addendum
- ADDED: Conditional loading trigger row in `claude/Agents.md` for output-floors.md
- ADDED: Rationale field convention for events.log orchestrator entries (defined in reference doc; enforcement via orchestrator prompt changes is a separate concern)

## Technical Constraints

- Reference doc follows existing architecture: `audience: agent` frontmatter, symlinked from `claude/reference/` to `~/.claude/reference/` via `just setup`
- The SKILL.md cross-reference must include phase transition field names inline as a minimum-viable fallback, with an explicit precedence rule: the reference doc supersedes the inline names when loaded
- Approval surface field names are inlined in phase reference files (specify.md, plan.md) — these files are already loaded for the phases where approval happens, so no conditional loading dependency
- The reference doc should target ~100-150 lines to stay within the reference doc size budget (existing docs are 50-120 lines)
- The rationale field convention is defined and documented but not enforced programmatically — enforcement requires orchestrator prompt changes in a follow-up ticket

## Open Decisions

- None. The SKILL.md replacement approach, checklist format, rationale scope, discovery exclusion, and overnight strategy were all resolved during the interview and critical review.
