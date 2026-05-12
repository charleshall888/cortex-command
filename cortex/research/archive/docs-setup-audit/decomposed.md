# Decomposition: docs-setup-audit

Single ticket — no epic. The research surfaced one cohesive deliverable (restructure README + setup.md, document the per-repo flow, fix verifiable defects) that ships together or not at all. Splitting into multiple tickets would create artificial fragmentation: the codebase defects touch the same files as the IA restructure; the verification command lives inside the new quickstart; the per-repo flow content is the missing material the restructure exists to supply.

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 150 | Restructure README and setup.md for clearer onboarding | medium | M | — |

## Consolidation Decision

The research artifact's option evaluations (OE-1 through OE-6) plus the codebase-verified defects (plugin syntax conflict, plugin count drift, utility list incompleteness, broken cross-platform promise, auth duplication) and the per-repo flow gap were all considered as candidate work items. All consolidate into ticket 150 under §3 consolidation criteria:

- **(a) Same-file overlap**: every item modifies `README.md` or `docs/setup.md` (one diagram move touches `docs/agentic-layer.md` as a single insertion). Splitting would generate near-conflicting PRs against the same files.
- **(b) No-standalone-value prerequisite**: codebase defects are not independently shippable as separate tickets without the restructure context — fixing the plugin syntax conflict in isolation requires deciding which form is canonical, which is OE-6 in the same restructure work.

The cross-platform delivery (Open Question 5 in research) was evaluated as a candidate split-off ticket. Decision: include in 150. README L72 currently makes a promise setup.md doesn't deliver; that's a defect in scope of "fix the front door," not a separable feature.

## Suggested Implementation Order

Single ticket — recommended sequence within the lifecycle plan phase:

1. Verify plugin install command behavioral equivalence (OE-6 prerequisite for the canonicalization decision)
2. Restructure README per OE-1 (trim) and OE-4 (move pipeline diagram)
3. Reorder + expand `docs/setup.md` per OE-2 and OE-3 (per-repo flow content + lifecycle.config.md schema + worked first-invocation example)
4. Add OE-5 verification command at end of install section
5. Add cross-platform setup notes to setup.md
6. Sweep codebase-verified defects (plugin count consistency, utility list completeness, auth de-duplication once content has moved)

## Created Files

- `cortex/backlog/150-restructure-readme-and-setupmd-for-clearer-onboarding.md` — Restructure README and setup.md for clearer onboarding

## Next Step

Run `/cortex-interactive:lifecycle restructure-readme-and-setupmd-for-clearer-onboarding` (or any matching slug fragment) when ready to build. The lifecycle skill will auto-load `research/docs-setup-audit/research.md` as prior discovery context via the ticket's `discovery_source:` field.
