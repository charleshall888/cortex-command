# Research: non-prescriptive-tickets-and-refine

## Codebase Analysis

### Ticket Creation Paths

**`/discovery` → decompose phase** (`skills/discovery/references/decompose.md`):
- Decomposes research findings into backlog items using the standard `/backlog add` flow
- Already has explicit guidance: "No implementation planning: Don't specify HOW to build each item — that's `/lifecycle`'s plan phase"
- Uses `discovery_source` field to link back to research, enabling lifecycle to auto-load prior investigation
- **Gap**: Doesn't prevent prescriptive bodies — only prohibits formal implementation planning. Bodies can still contain "Proposed Fix" language.

**`/backlog add`** (`skills/backlog/SKILL.md`, `backlog/references/schema.md`):
- Generates YAML frontmatter, opens file for user/agent editing
- `schema.md` already contains anti-prescription guidance: *"When describing potential implementation approaches, frame them as suggestions to explore, not prescriptions. Use language like 'one approach might be...' — the lifecycle's research and planning phases exist to evaluate approaches critically."*
- **Gap**: This guidance is documented but not enforced. Current tickets (001, 002) do not follow it and contain "Proposed Fix" sections with exact implementation commands.

**`/morning-review`**:
- Creates investigation items when overnight features fail
- Not yet implemented — feature listed but no body generation logic exists

**`/lifecycle`, `/refine`**:
- Update existing tickets (status, complexity, criticality, spec fields) but do not create new ones

### How /refine Treats Ticket Suggestions

**Current flow** (`skills/refine/SKILL.md`):
- Step 1 resolves the backlog item and reads its frontmatter and body
- Step 3 (Clarify) delegates to `skills/lifecycle/references/clarify.md` §1–§7, which reads the body for intent/scope assessment
- Step 4 (Research) passes the "clarified intent" to `/research` — not the raw backlog body
- **Key gap**: No explicit instruction at any step that ticket implementation suggestions should be treated as hypotheses to evaluate, not directions to follow

**Language gaps in /refine**:
- "Resolve Input" positions the backlog item as the authoritative source — no caveat about treating its suggestions as provisional
- Research phase doesn't say "evaluate suggested approach alongside alternatives"
- No explicit framing of "ticket as context" vs "ticket as prescription"

**Existing holistic guidance that partially addresses this**:
- `skills/lifecycle/references/research.md` (final line in Constraints): *"Evaluate backlog suggestions critically: If the originating backlog item suggested an approach, treat it as one option to investigate — not a decision already made."*
- This exists but is in the research reference (not /refine itself), and may not surface during /refine execution

### Current Ticket Examples

**`001-fix-overnight-watchdog-to-kill-entire-process-group-on-stall.md`** — VERY PRESCRIPTIVE
- Includes exact bash commands (`setsid python3 -m ...`), specific kill signals
- Presents a single "Proposed Fix" with no alternatives
- An agent following this ticket would implement setsid directly

**`002-morning-report-surface-failure-root-cause-inline.md`** — MODERATE-TO-HIGH
- Specifies exact failure classification categories
- Names specific files and data flow paths
- Doesn't prescribe exact implementation mechanism, but narrows the solution space significantly

Both tickets were written before the schema anti-prescription guidance was documented (or before it was known to be insufficient).

### Existing Holistic Research Guidance

**What already exists**:
- `skills/lifecycle/references/research.md` Constraints section: "Evaluate backlog suggestions critically: treat as one option to investigate — not a decision already made"
- `skills/discovery/references/decompose.md`: "No implementation planning" rule
- `backlog/references/schema.md`: Anti-prescription framing guidance (present but unenforced)

**What is missing**:
- `/refine SKILL.md`: No mention of treating ticket suggestions as hypotheses
- `skills/lifecycle/references/clarify.md`: Reads ticket body but doesn't separate scope from implementation direction
- `skills/lifecycle/references/specify.md`: Doesn't mention reconsidering backlog suggestions
- Ticket creation skills (discovery/decompose): No explicit prohibition on "Proposed Fix" sections, only "no implementation planning"

### Files to Modify

| File | Reason |
|------|--------|
| `skills/refine/SKILL.md` | Add explicit guidance: treat ticket suggestions as context to evaluate, not path to follow; research should explore alternatives |
| `backlog/references/schema.md` | Strengthen anti-prescription guidance; add concrete examples distinguishing "research finding" from "prescription" |
| `skills/discovery/references/decompose.md` | Clarify that tickets should express findings/constraints from research, not prescribe solutions; prohibit "Proposed Fix" framing |
| `skills/lifecycle/references/clarify.md` | Add note that if backlog body contains implementation suggestions, these are hypotheses for research, not scope constraints |

**Possibly in scope** (depends on spec decisions):
- `skills/lifecycle/references/research.md` — guidance already exists; may want to make it more prominent
- `skills/lifecycle/references/specify.md` — could add guidance to revisit backlog suggestions when research diverges

## Open Questions

- Should decompose tickets include a "Research Findings" section summarizing key evidence (not prescriptions), or just link to `discovery_source`? Inline findings might help /refine's holistic research; a bare link forces reading the full discovery research. Deferred: design preference — resolve in Spec requirements interview.
- Should /refine explicitly recheck whether research explored alternatives if the backlog item contained implementation suggestions? (Currently the Sufficiency Check only checks scope match and file coverage) Deferred: design decision — resolve in Spec requirements interview.
- Should `schema.md` anti-prescription guidance move into the actual ticket creation flow (e.g., printed as a reminder when opening the file), rather than just being documentation? Deferred: design preference — resolve in Spec requirements interview.
- Is `skills/lifecycle/references/clarify.md` the right place for "treat suggestions as hypotheses" — or does it belong only in `/refine SKILL.md`? (Clarify is used by both /refine and /lifecycle directly) Deferred: architectural decision — resolve in Spec requirements interview.
