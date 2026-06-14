# Decomposition: cortex-core-tooling-gaps

## Epic
- **Backlog ID**: 303
- **Title**: cortex-core tooling gaps (verified subset)

## Work Items
| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 304 | Add report-only ADR citation auditor | high | S | — |
| 305 | Hyperlink the spec column in the generated backlog index | low | S | — |
| 306 | Generate a cross-lifecycle phase index wired to morning-review | medium | M | — |

## Suggested Implementation Order

All three are independent (no blocked-by edges). Recommended sequence by value-per-effort:

1. **305** (spec-column hyperlink) — a true one-render fix; ship anytime as a quick win.
2. **304** (ADR citation auditor) — highest value, small effort; the strongest piece, motivated by a real consumer-repo breakage (dozens of dangling ADR references + a duplicate number).
3. **306** (cross-lifecycle phase index) — largest of the three; do last, and confirm the morning-report wiring is in scope before building so it does not ship as an orphan generator.

## Dropped Items

Seven of the ten verified candidates were dropped or deferred during the value triage at the research→decompose gate (the user elected to file only the three strongest). Recorded here for audit; the full reasoning lives in `research.md` Decision Records and Open Questions.

| Candidate | Disposition | Rationale |
|-----------|-------------|-----------|
| A2 — ADR `area:` frontmatter backfill | Folded into 304 | The area field has no consumer; the honest fix is deleting the README's never-honored defer-note, which is now a scope item inside the ADR auditor — not a standalone backfill ticket. |
| A1.iii — next-free-ADR-number helper | Dropped | ADRs are contiguous 0001–0010 with no gaps/collisions; zero current defect. Speculative against Solution-horizon. The auditor flags gaps/collisions if they ever appear. |
| B1 — requirements file→section index generator | Deferred | Generalize-from-N=1 (one consumer hand-built it); carries the same consumer-governance ownership smell as B3. Revisit when a second consumer needs it. |
| B3 — consumer always-loaded budget ratchet | Deferred (maintainer-confirm) | Regrowth is real, but the delivery mechanism is unresolved: ADR-0008 bars cortex from writing consumer root docs. Needs a maintainer ownership call (template under `cortex/` vs read-only measurement mode). |
| B4 — opt-in lifecycle archive verb | Dropped | Overrides the deliberate "preserve complete dirs as history" design to solve a navigation problem that 306's index already solves without moving anything. Redundant. |
| B5a/B5b — research-doc status convention + stale-status detector | Deferred | Scaffolding for a deferred, semantically hard feature: external prior art shows status-vs-reality drift is not done deterministically, and the detector cannot exist until a status convention is established and backfilled across dozens of docs. |
| C1 — overnight per-run `--exclude` flag | Deferred | Friction evidence weakened on verification (the brief's cited workaround does not exist in the docs; the real park is `status: abandoned`). File if an operator actually hits "skip this item tonight." |

## Created Files
- `cortex/backlog/303-cortex-core-tooling-gaps-verified-subset.md` — cortex-core tooling gaps (verified subset) [epic]
- `cortex/backlog/304-add-report-only-adr-citation-auditor.md` — Add report-only ADR citation auditor
- `cortex/backlog/305-hyperlink-the-spec-column-in-the-generated-backlog-index.md` — Hyperlink the spec column in the generated backlog index
- `cortex/backlog/306-generate-a-cross-lifecycle-phase-index-wired-to-morning-review.md` — Generate a cross-lifecycle phase index wired to morning-review
