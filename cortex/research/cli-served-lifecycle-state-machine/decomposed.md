# Decomposition: cli-served-lifecycle-state-machine

## Epic
- **Backlog ID**: 371
- **Title**: CLI-served lifecycle state machine: phased verb-completion with a gated loop

## Work Items
| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 370 | cortex-lifecycle-resolve mis-resolves numeric backlog ID to state:new when a slug-keyed lifecycle already exists (adopted pre-existing ticket) | high | S | — |
| 372 | Land lifecycle writer-discipline and config-transparency point fixes | high | S–M | — |
| 373 | Build the verb-completion composition: wrapper verbs, generated pauses, shared overnight reducer | high | L | 370 |
| 374 | Phase-C gate: decide the served next/advance loop on post-composition evidence | medium | M | 373 |

## Suggested Implementation Order

370 and 372 land first, in any order (both standalone). 373 follows 370 (the wrapper verbs sit on the fixed identity resolver). 374 runs only after living with 373 — it is a decision spike, not queued build work; its go path spawns the loop build as its own lifecycle, and the loop's later stages (pause runtime tooth, overnight core-sharing, entry-point configs) decompose only after a go verdict.

## Grouping Notes
- **Ticket 372** ← pieces "writer-discipline point fixes" and "dormant-config audit" (Phase A of research Feasibility). One hygiene cluster; no intra-group ordering.
- **Ticket 373** ← pieces "advance verb (transition-executor bodies)", "pause-spec registry (repo-data substrate)", "overnight policy layer (shared-reducer floor)", and verification-harness arms d/f (Phase B). One integration cluster — the strict prefix of the machine; intra-group note: the wrapper verbs and the pause work are independent, the overnight reducer swap can land any time.
- **Ticket 374** ← pieces "transition table", "next verb", "advance verb (loop composition)", "protocol handshake", "interactive policy layer", "fragment corpus (flavor decision)", "describe verb", "escape hatches", remaining harness arms (Phase C). Packaged as a single gate spike because the pieces fund together or not at all, per the research's phased funding decision.
- **Ticket 370** ← piece "identity resolver". Pre-existing ticket adopted under the epic (parent set) instead of duplicating.

## Consolidation Notes
- Pieces 2+3 of the first-presented batch (writer discipline; dormant-config audit) merged into surviving piece 2 (ticket 372) — both machine-independent Phase A hygiene; user-directed consolidation for large-work-unit execution.
- Pieces 4+5+6 of the first-presented batch (wrapper verbs; marker-generated pauses; overnight reducer) merged into surviving piece 3 (ticket 373) — one Phase B integration cluster; user-directed consolidation for large-work-unit execution.

## Created Files
- `cortex/backlog/371-cli-served-lifecycle-state-machine-phased-verb-completion-with-a-gated-loop.md` — epic
- `cortex/backlog/372-land-lifecycle-writer-discipline-and-config-transparency-point-fixes.md` — Phase A
- `cortex/backlog/373-build-the-verb-completion-composition-wrapper-verbs-generated-pauses-shared-overnight-reducer.md` — Phase B
- `cortex/backlog/374-phase-c-gate-decide-the-served-next-advance-loop-on-post-composition-evidence.md` — Phase C gate
- (updated) `cortex/backlog/370-…-slug-keyed-lifecycle-already-exists.md` — adopted: `parent: 371`
