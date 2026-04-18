# Decomposition: opus-4-7-harness-adaptation

## Epic

- **Backlog ID**: 82
- **Title**: Adapt harness to Opus 4.7 (prompt delta + capability adoption)

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 83 | Run /claude-api migrate to opus-4-7 on throwaway branch and report diff | high | S | — |
| 84 | Verify claude/reference/*.md conditional-loading behavior under Opus 4.7 | high | XS | — |
| 85 | Audit dispatch-skill prompts and reference docs for 4.7 at-risk patterns | high | M | 83, 84 |
| 86 | Extend output-floors.md with M1 Subagent Disposition section | medium | S | — |
| 87 | Instrument events.log aggregation for turns and cost per tier | medium | M | — |
| 88 | Collect 4.7 baseline rounds then remove progress-update scaffolding | medium | S | 87 |
| 89 | Measure xhigh vs high effort cost delta on representative task | low | S | 87 |
| 90 | Adopt xhigh effort default for overnight lifecycle implement | low | M | 88, 89 |
| 91 | Decide and document post-4.7 policy settings (MUST-escalation, tone regression) | low | S | 83, 84, 85 |

## Suggested Implementation Order

1. **Wave 0 — spikes** (parallel): #83, #84 — pre-audit exploration. #87 (instrumentation) can also start here since it's independent.
2. **Wave 1 — audit + codification**: #85 (after spikes return), #86 (parallel with #85, different files).
3. **Wave 2 — baseline + capability adoption**: #88 (requires #87), #89 (requires #87). These capture the DR-4 baseline window.
4. **Wave 3 — effort adoption**: #90 (requires #88 and #89).
5. **Wave 4 — policy**: #91 (after #83/#84/#85 provide concrete calibration evidence).

## Key Design Decisions

- **Consolidation**: OQ3 (MUST-escalation norm) and OQ6 (tone regression) merged into a single chore ticket (#91) per Decompose rule (a) same-file overlap — both likely edit CLAUDE.md or `claude/reference/` files.
- **Separation preserved**: W1 (#83) and W2 (#84) kept as separate spikes despite both being small — each produces an independent deliverable (migration diff vs loading-semantics verdict). Neither has no-standalone-value per Decompose rule (b).
- **Ordering discipline encoded in dependencies**: #87 → #88 enforces DR-4's "baseline before Wave-1 prompt changes" requirement via `blocked-by`. Without this encoding, a future implementer could ship #88 out of order and contaminate the measurement.
- **Ask-2 fold-in**: `consider`-softening audit was folded into #85's scope as pattern P7 (per user decision 2026-04-18 — recommended option). No separate DR-5 ticket; the three-category classification (conditional-requirement / optional / polite-imperative) is included in #85's body.
- **DR-6 scope-narrowing applied**: #86 extends `output-floors.md` rather than creating a new `subagent-disposition.md` file, codifies M1 only (not M2/M3), and matches DR-2's dispatch-skill scope.

## Created Files

- `backlog/082-adapt-harness-to-opus-47-prompt-delta-capability-adoption.md` — epic
- `backlog/083-run-claude-api-migrate-to-opus-4-7-on-throwaway-branch-and-report-diff.md`
- `backlog/084-verify-claude-reference-md-conditional-loading-behavior-under-opus-47.md`
- `backlog/085-audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns.md`
- `backlog/086-extend-output-floorsmd-with-m1-subagent-disposition-section.md`
- `backlog/087-instrument-eventslog-aggregation-for-turns-and-cost-per-tier.md`
- `backlog/088-collect-47-baseline-rounds-then-remove-progress-update-scaffolding.md`
- `backlog/089-measure-xhigh-vs-high-effort-cost-delta-on-representative-task.md`
- `backlog/090-adopt-xhigh-effort-default-for-overnight-lifecycle-implement.md`
- `backlog/091-decide-and-document-post-47-policy-settings-must-escalation-tone-regression.md`
