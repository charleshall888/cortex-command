# Decomposition: backlog-optional-plugin

## Epic
- **Backlog ID**: 315
- **Title**: Optional backlog plugin + configurable backend

## Work Items
| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 316 | Extract backlog management skill into optional cortex-backlog plugin | high | M | — |
| 317 | Config-driven backlog backend: resolver, local/none routing, overnight safety | high | L | — |
| 318 | External-tracker best-effort backlog backend (GitHub Issues via gh) | medium | M | 317 |

## Suggested Implementation Order

316 and 317 are independent and can proceed in parallel; 318 follows 317 (it needs the config seam + backend branch). Within 317 the internal order is resolver → config scaffold → consumer routing → overnight guard / none-degrade, with the ADR landing early. 316's slash-rename sub-step (inside 317's consumer-rename work) assumes 316 is merged — an internal ordering note carried in 317's body, not a hard cross-ticket block.

## Grouping Notes

The research `### Pieces` set named ten analytical pieces (P1–P10). At the user's direction the gate consolidated them into three ticket units (a §4 packaging decision; the per-piece set in `research.md` is unchanged):

- **Ticket 316** ← pieces P1 (plugin extraction) + P2 (install-topology contract) + P3 (docs registration). One unit of work: the plugin cannot land without its build/parity/marketplace registration and the topology contract (keep `backlog-author` in core) co-landing in the same commit — the atomicity is forced by the classification guard, the plugin-list self-test, and the drift gate.
- **Ticket 317** ← pieces P4 (resolver) + P5 (config scaffold) + P6 (consumer routing + slash-rename) + P8 (overnight refusal guard) + P9 (none-backend + structural-consumer degrade) + P10 (ADR-0015). One coherent feature: everything that delivers a config-respecting, opt-out-able, overnight-safe backlog *without* needing any external tracker. Intra-group order P4 → P5 → P6 → {P8, P9}, ADR early; preserved as an internal phase boundary inside the ticket, not cross-ticket dependencies.
- **Ticket 318** ← piece P7 (external best-effort create + round-trip) plus the external arm of P6's backend branch. Kept separate from 317 because its `gh`-specific failure surface (fuzzy/eventually-consistent search, duplicate-on-retry, auth, fidelity loss) is the riskiest, most distinct behavioral chunk and earns its own review surface.

## Created Files
- `cortex/backlog/315-optional-backlog-plugin-configurable-backend.md` — Optional backlog plugin + configurable backend (epic)
- `cortex/backlog/316-extract-backlog-management-skill-into-optional-cortex-backlog-plugin.md` — Extract backlog management skill into optional cortex-backlog plugin
- `cortex/backlog/317-config-driven-backlog-backend-resolver-local-none-routing-overnight-safety.md` — Config-driven backlog backend: resolver, local/none routing, overnight safety
- `cortex/backlog/318-external-tracker-best-effort-backlog-backend-github-issues-via-gh.md` — External-tracker best-effort backlog backend (GitHub Issues via gh)
