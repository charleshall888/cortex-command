---
audience: agent
---

# Output Floors

Minimum content requirements for phase transition summaries and approval surfaces. These floors define what information must be present — not how verbose or terse the output should be.

**Precedence rule**: When this document is loaded alongside inline field names in SKILL.md or phase reference files, the expanded definitions here supersede the inline names.

## Phase Transition Floor

Every phase transition summary must include these four fields. Use "None" when a field has nothing to report — fields are always present even when empty.

| Field | What to include |
|-------|-----------------|
| **Decisions** | Key decisions made during this phase. "None" if the phase was mechanical (e.g., a trivial rename or config change with no judgment calls). |
| **Scope delta** | Changes to scope, approach, or plan since the last phase. Includes additions, removals, and trade-off shifts. "None" if scope is unchanged. |
| **Blockers** | Active blockers, escalations, or deferred questions. Anything that could prevent the next phase from succeeding. "None" if the path is clear. |
| **Next** | Next phase name and what it will do. One sentence. |

These fields are the minimum. Additional context is welcome when it aids the user's understanding — the floor is a lower bound, not a ceiling.

## Approval Surface Floor

When presenting an artifact for user approval (spec approval, plan approval), the summary must include these four fields. This structures what the user sees at the approval gate — the moment they decide to proceed or veto.

| Field | What to include |
|-------|-----------------|
| **Produced** | One-line summary of the artifact and its purpose. |
| **Trade-offs** | Alternatives considered and rationale for the chosen approach. If no alternatives were evaluated, state why (e.g., "single obvious approach, no alternatives"). |
| **Veto surface** | Items the user might disagree with or want to change. Design choices, scope boundaries, or priority calls that reflect judgment rather than necessity. If nothing is controversial, state "No veto-worthy items identified." |
| **Scope boundaries** | What is explicitly excluded. Maps to the spec's Non-Requirements section. |

The approval surface floor supplements — not replaces — any existing presentation format (e.g., plan.md's "overview + task list").

## Overnight File-Based Addendum

### Compaction and File Artifacts

File-based lifecycle artifacts bypass compaction entirely:
- `lifecycle/{feature}/research.md`
- `lifecycle/{feature}/spec.md`
- `lifecycle/{feature}/plan.md`
- `lifecycle/{feature}/review.md`
- `lifecycle/{feature}/events.log`

These files survive regardless of context window management. No additional conversational compaction resilience is needed for information that is written to these artifacts.

### Orchestrator Rationale Convention

One gap exists: orchestrator decision rationale (why features were selected, how escalations were resolved) lives only in conversation and can be lost to compaction during long overnight sessions.

**Convention**: When the orchestrator resolves an escalation or makes a non-obvious feature selection decision (e.g., skipping a feature, reordering rounds), it should include a `rationale` field in the relevant events.log entry explaining the reasoning.

This convention is defined here. Enforcement via orchestrator prompt changes is a downstream concern — this document defines the pattern; the orchestrator prompts must be updated separately to implement it.

Routine forward-progress decisions (dispatching the next round, marking a feature complete after tests pass) do not require a rationale field.

## Downstream Consumption

This document serves as the constraint source for:
- **#052 (skill prompt audit)**: Assesses whether each skill's phase transition output meets the phase transition floor.
- **#053 (subagent output formats)**: Assesses whether subagent dispatch prompts specify output format expectations that align with these floors.

These downstream tickets use the floors defined above as their rubric for evaluating compliance.

## Applicability

Output floors apply to skills that produce phase transitions or approval surfaces:
- `lifecycle` (phase transitions + approval surfaces)
- `discovery` (phase transitions — per-skill calibration via #052)

Skills without phase transitions (commit, pr, backlog, dev) are not subject to these floors.
