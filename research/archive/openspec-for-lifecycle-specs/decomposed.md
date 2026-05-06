# Decomposition: openspec-for-lifecycle-specs

## Outcome: Direct Implementation (No Tickets)

After critical review and devil's advocate analysis, the four potential work items were triaged as follows:

### Implemented Directly

| Item | What | Rationale |
|------|------|-----------|
| Spec structural validation | `just validate-spec` recipe + `bin/validate-spec` script | S-sized chore, too small for lifecycle. Catches structural issues (missing headings, absent MoSCoW markers, prose-only criteria) before orchestrator review. |
| "Changes to Existing Behavior" section | Added to spec template in `specify.md` + S6 orchestrator review check | S-sized chore, too small for lifecycle. Forces spec authors to document MODIFIED/REMOVED/ADDED behavioral changes. |

### Deferred (No Tickets Created)

| Item | Why Deferred |
|------|-------------|
| Behavioral baseline enforcement mechanism (spike) | Research artifact already documents the three enforcement options (lifecycle hook, review gate, automated merge) and the key constraint ("do not adopt without enforcement"). Revisit when "agents researching from scratch" becomes a measured bottleneck. |
| Orchestrator review skip-rule calibration (spike) | The 78% pass rate is an ambiguous data point — only resolvable by experiment, not further research. The 22% catch rate IS catching real issues. Documented as an open question in research.md. |

## Key Design Decisions

- **No epic created**: The two actionable items were small enough for direct implementation. The two investigative items don't warrant tickets because the research artifact already contains the analysis.
- **Devil's advocate informed routing**: The DA correctly identified that ticketing S-sized chores through lifecycle is the exact over-engineering the research diagnosed. Direct implementation avoids this.

## Created/Modified Files

- `bin/validate-spec` — spec structural validation script
- `justfile` — added `validate-spec` recipe
- `skills/lifecycle/references/specify.md` — added "Changes to Existing Behavior" section to template
- `skills/lifecycle/references/orchestrator-review.md` — added S6 check for behavioral change documentation
