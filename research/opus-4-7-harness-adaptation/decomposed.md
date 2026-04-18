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
| 88 | Collect 4.7 baseline rounds and snapshot aggregated data | medium | S | 87 |
| 89 | Measure xhigh vs high effort cost delta on representative task | low | S | 87 |
| 90 | Adopt xhigh effort default for overnight lifecycle implement | low | M | 89, 92 |
| 91 | Decide and document post-4.7 policy settings (MUST-escalation, tone regression) | low | S | 85 |
| 92 | Remove progress-update scaffolding from long-running prompts (DR-3 Wave 1) | medium | S | 88 |

## Suggested Implementation Order

1. **Wave 0 — spikes** (parallel): #83, #84 — pre-audit exploration. #87 (instrumentation) can also start here since it's independent.
2. **Wave 1 — audit + codification**: #85 (after spikes return), #86 (parallel with #85, different files).
3. **Wave 2a — baseline**: #88 (requires #87). Collects 2–3 overnight rounds and commits the baseline snapshot.
4. **Wave 2b — prompt changes + measurement** (can run in parallel after Wave 2a): #92 (scaffolding removal, requires #88's baseline), #89 (xhigh cost delta, requires #87).
5. **Wave 3 — effort adoption**: #90 (requires #89 and #92).
6. **Wave 4 — policy**: #91 (after #85 provides concrete calibration evidence for OQ3). OQ6 (tone) needs no evidence and could ship anytime but stays consolidated in #91.

## Key Design Decisions

- **Consolidation**: OQ3 (MUST-escalation norm) and OQ6 (tone regression) merged into a single chore ticket (#91) per Decompose rule (a) same-file overlap — both likely edit CLAUDE.md or `claude/reference/` files.
- **Separation preserved**: W1 (#83) and W2 (#84) kept as separate spikes despite both being small — each produces an independent deliverable (migration diff vs loading-semantics verdict). Neither has no-standalone-value per Decompose rule (b).
- **Ask-2 fold-in**: `consider`-softening audit was folded into #85's scope as pattern P7 (per user decision 2026-04-18 — recommended option). No separate DR-5 ticket; the three-category classification (conditional-requirement / optional / polite-imperative) is included in #85's body.
- **DR-6 scope-narrowing applied**: #86 extends `output-floors.md` rather than creating a new `subagent-disposition.md` file, codifies M1 only (not M2/M3), and matches DR-2's dispatch-skill scope.

## Dependency graph — known enforcement limits (from 2026-04-18 critical review)

- **`blocked-by` enforces status-terminality only**, not data-ordering or evidence-feedback. `claude/overnight/backlog.py:505-508` checks only whether the blocker reached a terminal status; no artifact-existence check, no field referencing the blocker's output. The previous claim here that "#87 → #88 enforces DR-4's 'baseline before Wave-1 prompt changes' requirement via blocked-by" was mechanically false — the edge only enforces "#87 reaches `complete` before #88 starts," which is satisfiable by flipping a status field without running aggregation.
- **#88 was a composite ticket — resolved by splitting into #88 (baseline only) + #92 (scaffolding removal) with a cross-ticket `blocked-by` edge.** User decision 2026-04-18 per Ask-A. The split gives DR-4's step-2 → step-3 gate mechanical enforcement via status-terminality: #92 cannot start until #88 reaches `complete`, which requires the baseline snapshot artifact to be committed.
- **#85 retained as a single composite with three methodologies enumerated.** User decision 2026-04-18 per Ask-B. Trade-off accepted: one ticket, one lifecycle run, Plan phase picks approach per-Pass. #85's body now explicitly enumerates Pass 1 (grep-amenable P1–P6), Pass 2 (reference-file negation-only), Pass 3 (P7 with git-blame + three-category classification), adds a size-acknowledgment note (M is provisional, likely complex), and re-attaches #053's 10+ specific preservation anchors.
- **Spike → audit is a gate, not a feedback channel.** #83/#84 → #85 carries no mechanism for spike outputs to update #85's scope. #85 now includes a "pre-lifecycle scope re-derivation" step in its body to make the manual handoff explicit.
- **#91 blocker list corrected.** Was `[83, 84, 85]`; reduced to `[85]` after critical review identified #83 and #84 as evidence-mismatched blockers (they produce no OQ3-relevant evidence and zero OQ6-relevant evidence).
- **Plan phase does not decompose tickets.** Plan picks approach; it does not re-split tickets that arrive with composite scope. Sizing and methodology acknowledgments were added to #85's body to surface the aggregation risk before lifecycle starts.

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
- `backlog/092-remove-progress-update-scaffolding-from-long-running-prompts-dr-3-wave-1.md` — split out of original #88 during 2026-04-18 critical-review
