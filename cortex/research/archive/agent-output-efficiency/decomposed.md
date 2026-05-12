# Decomposition: agent-output-efficiency

## Epic
- **Backlog ID**: 049
- **Title**: Improve agent output signal-to-noise ratio

## Work Items
| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 050 | Define output floors for interactive approval and overnight compaction | high | M | -- |
| 051 | Add hook-based preprocessing for test/build output | high | S | -- |
| 052 | Audit skill prompts and remove verbose instructions above the floor | medium | S | 050 |
| 053 | Add subagent output format specs and compress synthesis | medium | M | 050, 052 |

## Suggested Implementation Order
1. **050 and 051 in parallel** — 050 defines the constraints everything else respects; 051 is independent (deterministic hooks, no model judgment)
2. **052 after 050** — audit uses 050's output floors as its rubric
3. **053 after 052** — format specs and synthesis compression only for skills where the audit showed gaps

## Key Design Decisions

**Merged phase transitions and phase summary requirements into one ticket (050).** Originally split as "compress transitions to one line" and "define minimum info requirements" — critical review revealed these target the same instruction in the SKILL.md and could produce contradictory formats if executed independently.

**Defined audit rubric by reference to output floors.** Originally "remove high-confidence verbose instructions" with no criteria. Now: removable if above the floor AND not consumed by downstream skill or approval gate.

**Scoped all tickets to both interactive and overnight contexts.** Originally implicit interactive-only. Critical review identified that shared skills (lifecycle) run in both contexts, compaction at 12% retention means overnight needs different (possibly less aggressive) compression, and interactive stress-testing doesn't validate overnight behavior.

## Created Files
- `cortex/backlog/049-improve-agent-output-signal-to-noise-ratio.md` — Epic
- `cortex/backlog/050-define-output-floors-for-interactive-and-overnight.md` — Output floor definitions
- `cortex/backlog/051-add-hook-based-preprocessing-for-tool-output.md` — Hook-based preprocessing
- `cortex/backlog/052-audit-skill-prompts-remove-verbose-instructions.md` — Skill prompt audit
- `cortex/backlog/053-add-subagent-output-formats-compress-synthesis.md` — Subagent format specs + synthesis
