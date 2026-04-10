# Review: Define output floors for interactive approval and overnight compaction

## Stage 1: Spec Compliance

### R1: Create `claude/reference/output-floors.md`
**Rating**: PASS

- File exists at `claude/reference/output-floors.md`
- Contains `audience: agent` frontmatter (count = 1)
- Follows the existing reference doc pattern: frontmatter, action-oriented content, no motivational preamble
- At 74 lines, it falls below the ~100-150 line target stated in the spec description and Technical Constraints. However, the acceptance criteria gate only on file existence and frontmatter, and the existing reference docs range from 96-314 lines (context-file-authoring.md is 96 lines). The `~` prefix indicates approximate, and the doc covers all required sections without padding. This is acceptable.

### R2: Phase transition floor
**Rating**: PASS

- `grep -c 'Decisions\|Scope delta\|Blockers\|Next'` = 4 (meets >= 4 threshold)
- All four fields are present as a table-format checklist with descriptions
- "None" convention for empty fields is documented
- No prose examples (checklist format per spec)

### R3: Approval surface floor
**Rating**: PASS

- `grep -c 'Produced\|Trade-offs\|Veto surface\|Scope boundaries'` = 4 (meets >= 4 threshold)
- All four fields present with descriptions matching the spec's definitions
- Table format consistent with the phase transition floor section

### R4: Overnight file-based addendum
**Rating**: PASS

- `grep -c 'rationale'` = 4 (meets >= 1 threshold)
- Lists the five file-based artifacts that bypass compaction
- Documents the `rationale` field convention for events.log entries
- Correctly scopes to escalation resolutions and non-obvious feature selection decisions
- States enforcement is a downstream concern (not this doc's job)
- Routine decisions explicitly excluded from requiring rationale

### R5: Replace lifecycle SKILL.md phase transition instruction
**Rating**: PASS

- `grep -c 'output-floors' skills/lifecycle/SKILL.md` = 1 (meets >= 1)
- `grep -c 'briefly summarize what was accomplished' skills/lifecycle/SKILL.md` = 0 (old instruction removed)
- Cross-reference preserves auto-proceed behavior ("announce the transition and proceed to the next phase automatically")
- Four inline field names present as fallback (Decisions, Scope delta, Blockers, Next)
- Precedence rule stated: "when loaded, the reference doc supersedes these inline names"

### R6: Inline approval surface fields in phase reference files
**Rating**: PASS

- `grep -c 'Produced\|Trade-offs\|Veto surface\|Scope boundaries' skills/lifecycle/references/specify.md` = 4 (meets >= 4)
- `grep -c 'Produced\|Trade-offs\|Veto surface\|Scope boundaries' skills/lifecycle/references/plan.md` = 4 (meets >= 4)
- specify.md: Fields inserted in section 4 (User Approval) with parenthetical definitions and cross-reference to output-floors.md
- plan.md: Fields inserted in section 4 (User Approval) with same format, supplementing the existing "overview + task list" presentation
- Both files note the reference doc provides expanded definitions when loaded

### R7: Add conditional loading trigger to Agents.md
**Rating**: PASS

- `grep -c 'output-floors' claude/Agents.md` = 1 (meets >= 1)
- Trigger text matches spec exactly: "Writing phase transition summaries, approval surfaces, or editing skill output instructions"
- Target is `~/.claude/reference/output-floors.md`
- Row added after the existing `parallel-agents.md` entry, consistent with table format

### R8: Downstream consumption note
**Rating**: PASS

- `grep -c '#052\|#053'` = 3 (references both tickets)
- Downstream Consumption section explains the relationship: this doc is the constraint source, those tickets use the floors as their rubric
- Both #052 and #053 are referenced by number with brief descriptions of what each assesses

## Stage 2: Code Quality

### Naming Conventions
Consistent with project patterns. The file name `output-floors.md` follows the kebab-case pattern used by other reference docs (`verification-mindset.md`, `parallel-agents.md`, `context-file-authoring.md`). Section headings use Title Case matching existing reference docs.

### Error Handling
Not applicable -- this is a reference document and configuration change, not executable code. The graceful degradation approach (inline fallback fields + conditional loading) is well-designed: if the reference doc fails to load, both SKILL.md and the phase reference files contain the field names inline.

### Test Coverage
All 8 acceptance criteria verified programmatically:
- R1: file exists, frontmatter count = 1
- R2: phase transition field count = 4
- R3: approval surface field count = 4
- R4: rationale count = 4
- R5: output-floors reference in SKILL.md = 1, old instruction removed = 0
- R6: approval fields in specify.md = 4, plan.md = 4
- R7: output-floors in Agents.md = 1
- R8: ticket references = 3

### Pattern Consistency
- Reference doc follows `audience: agent` frontmatter pattern
- Justfile entries added to all three required locations (setup-force, deploy-reference, check-symlinks), placed after the `claude-skills.md` entry in each
- Agents.md conditional loading table row follows the existing column format
- Inline field format in specify.md and plan.md uses bold + parenthetical consistent with how both files already structure their content

### Observations
- The reference doc is 74 lines vs the ~100-150 target. This is compact but complete -- all required sections are present without filler. The existing `context-file-authoring.md` is 96 lines, so 74 is not dramatically outside the range. The spec framed this as approximate ("~100-150"), and the acceptance criteria do not gate on line count.
- The Applicability section mentions discovery with a note about per-skill calibration via #052, correctly handling the Non-Requirements exclusion of discovery SKILL.md modification while acknowledging discovery does have phase transitions.
- The edge case for "skills without phase transitions" is handled via a negative-scope statement in the Applicability section (listing commit, pr, backlog, dev as excluded). The spec edge case says "The reference doc should not reference these skills" -- the implementation references them only to exclude them. This is consistent with spec intent, though a strict reading could flag it.

## Requirements Drift
**State**: detected
**Findings**:
- The output floors reference document introduces a new "rationale" field convention for orchestrator events.log entries. This convention (orchestrator decision rationale captured in a `rationale` field on events.log entries when resolving escalations or making non-obvious feature selection decisions) is not reflected in `requirements/pipeline.md`, which defines the pipeline event log format and orchestrator behavior. The pipeline requirements doc's "Session Orchestration" section describes outputs including `pipeline-events.log` and the "Deferral System" section covers escalation handling, but neither mentions the rationale field convention.
**Update needed**: requirements/pipeline.md

## Suggested Requirements Update
Add a bullet to the "Session Orchestration" section's acceptance criteria or the "Non-Functional Requirements" section of `requirements/pipeline.md`:

> **Orchestrator rationale convention**: When the orchestrator resolves an escalation or makes a non-obvious feature selection decision (e.g., skipping a feature, reordering rounds), the relevant events.log entry should include a `rationale` field explaining the reasoning. Routine forward-progress decisions do not require this field. (Convention defined in `claude/reference/output-floors.md`; enforcement requires orchestrator prompt changes.)

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "detected"
}
```
