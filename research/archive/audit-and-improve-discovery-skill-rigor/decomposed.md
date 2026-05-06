# Decomposition: audit-and-improve-discovery-skill-rigor

## Epic
- **Backlog ID**: 137
- **Title**: Harden /discovery citation grounding and external-endorsement value gating

## Work Items
| ID  | Title                                                                 | Priority | Size | Depends On |
|-----|-----------------------------------------------------------------------|----------|------|------------|
| 138 | Codify citation norm and premise-as-verification in /discovery research phase | medium   | S    | —          |
| 139 | Add vendor-endorsement value gating to /discovery decompose phase     | medium   | S    | 138        |

## Suggested Implementation Order

1. **#138 first.** It introduces the `premise-unverified` signal into `research.md` and resolves the Prerequisites-framing drift. It is a single-file rule edit with no dependencies.
2. **#139 second.** It references #138's `premise-unverified` signal when gating external-endorsement value cases in `decompose.md`.

Both are S-effort rule edits to adjacent files in `skills/discovery/references/`. They could realistically ship in the same session, though they are tracked as separate tickets because they address different phase layers (synthesis-time citation grounding vs. decomposition-time value gating).

## Key design decisions

- **Recommendation revised from A+B to A+C after critical review.** The original research artifact proposed A (citation rule) + B (post-hoc orchestrator-review checklist item). Critical review surfaced (a) an internal contradiction between Q3 and DR-1 on whether `decompose.md:29` is a gate, (b) misdiagnosis of #092's proximate cause (value-case capture, not locator-grounding), and (c) empirical evidence from `research/opus-4-7-harness-adaptation/events.log` that all existing post-hoc human checks ran and passed while the premise was wrong. A+C targets the correct failure layers; B was dropped because post-hoc human checklists were empirically insufficient.
- **Approach F (automated mechanical grounding check) deferred.** Surfaced via external-literature scan on execution-grounded verification. Would have caught #092 deterministically, but crosses from rule-edit into tooling. Held as the documented escalation path if A+C prove insufficient on future web-heavy topics.
- **Approach D (closure feedback loop) deferred.** Base rate (1–2/111) does not justify new infrastructure at this time.
- **No epic-for-an-epic.** Two work items → one epic + two children per `decompose.md:47-57`, even though both children are S-effort same-surface-class. Consolidation rules at `decompose.md:33-37` do not fire (different files, both have standalone value).
- **IDs renumbered from 134/135/136 to 137/138/139.** Initial assignment collided with bug tickets filed by a concurrent session (now #134 and #135). The concurrent session's tickets landed first and have stronger claim; mine were renumbered forward.

## Created Files

- `backlog/137-harden-discovery-citation-grounding-and-external-endorsement-gating.md` — Epic
- `backlog/138-codify-citation-norm-and-premise-as-verification-in-discovery-research.md` — Ticket A
- `backlog/139-add-vendor-endorsement-value-gating-to-discovery-decompose.md` — Ticket C
