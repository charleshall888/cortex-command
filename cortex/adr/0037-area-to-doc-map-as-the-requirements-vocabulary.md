---
status: accepted
---

# 0037 — Area→doc map as the requirements vocabulary

_Decision date: 2026-08-07 (#472 — requirements-loader-matches-index-tags-against)._

## Context

Requirements selection has matched lifecycle `index.md` `tags:` as case-folded substrings against free-text
trigger phrases since #333 replaced a hand-executed prose algorithm. Measured across 190 lifecycles, 8.9%
load a real area doc. Two independent causes: the selected field (`tags:`, an epic/topic slug vocabulary) is
not the field carrying the area concept (`areas:`), and substring matching both false-negatives on
hyphenation (`'overnight-runner' in 'pipeline/overnight runner/…'` is False) and false-positives on
accidental containment (`pipe` selects `pipeline.md`).

## Decision

`## Conditional Loading` becomes an explicit many-to-one area→doc map whose keys are the declared area
vocabulary, matched by exact kebab-normalized key lookup against the backlog item's `areas:`, propagated to
the loader through `index.md`. The map *is* the vocabulary — there is no separate validator over `areas:`,
and an unknown area is reported rather than rejected.

Every run of the loader emits exactly one `COVERAGE:(loaded|doc-missing|unmapped|no-area)` line on stderr.
stdout keeps #333's paths-only contract unchanged, which is why the marker is stderr-only.

## Trade-off

A strict map keyed on area name alone is a **regression** — measured at 14 lifecycles (7.4%) versus 17 (8.9%)
today. The gain depends entirely on preserving many-to-one synonyms (`overnight-runner` → `pipeline.md` alone
accounts for 26 of 41). So this trades substring matching's accidental reach for an explicit synonym list
that must be maintained by hand as areas are added — a real recurring cost, accepted because the alternative
silently mis-selects and because the synonym sets already exist in `project.md`'s trigger text and are
recovered mechanically rather than invented.

Rejected: keying the loader off the backlog item directly (ADR-0019 backend-awareness boundary); keying off a
normalized substring match (retains accidental containment); a validated closed vocabulary over `areas:`
(schema change across 466 items whose payoff depends on area docs that do not yet exist).

## Measured outcome

Confirmed at review by two disjoint derivations — the shipped loader over `index.md` `areas:`, and a route
reading each index's parent backlog item directly without consulting `index.md` at all. Both give the same
figures, with **zero per-lifecycle disagreement**, which is the evidence that the index-copy path loses
nothing the items carry:

| | value |
|---|---|
| lifecycles loading ≥1 area doc present on disk | **86** (was 17 at HEAD) |
| same, excluding `lifecycle.md`-only matches | **41** — the ceiling computed from backlog-item `areas:` |
| state distribution | `loaded` 86, `unmapped` 61, `no-area` 44, `doc-missing` 0 |

`unmapped` is the expected steady state for 61 lifecycles (`skills` alone 45), not a defect — no doc is
planned for those areas. Its report is deliberately one terse line: a per-area tally here is the recurring
noise that would retrain operators to ignore the marker, which is the exact failure this decision exists to
fix.

Five lifecycles lost the area doc they resolved at HEAD. Three matched `remote-access.md` only because the
tag `ux` is a substring of `tmux` — losing those is the decision working as specified. Two are genuine
losses whose tickets declare no `areas:` at all and now report `no-area`; that is this trade-off's accepted
cost, and the loss is now *reported* rather than silent.

### Amendment 2026-08-12 — the *partial* population, measured (#482)

The table above breaks the corpus down by state and says nothing about the population *inside* `loaded`
that carries an unmapped area anyway. Coverage precedence makes any present doc outrank every partial
failure, so a lifecycle declaring `areas: [audio, 2-5d]` where only `2-5d` maps reports `loaded` with **no
note at all** — the `unmapped` state is reached only when *zero* areas hit. #482 asked whether the noise
argument above, which was measured on the `unmapped` state's report, actually reaches that case.

Measured over the 205 active lifecycles: `loaded` 89, `unmapped` 62, `no-area` 54, `doc-missing` 0. Of the
89 `loaded`, **23 (25.8%)** carry at least one unmapped area. Their unmapped areas are `skills` 12, `tests`
3, `install` 2, `hooks` 2, `report` 2, `cli` 1, `docs` 1, `requirements` 1 — every one an area with no doc
planned, `skills` most of all (#476 declined to add one). All 7 map rows resolve to files that exist, and
**0** `loaded` lifecycles mask a `doc-missing` hit, so the masked case is entirely the expected-unmapped one.

A note under `loaded` would therefore fire on one run in four and name areas that are permanently unmapped
by construction — the map *is* the vocabulary. That is the same recurring noise this section already
rejects, so the argument does reach the partial case and **no note is added**. The distinction #482 drew is
real and the measurement was missing; the conclusion is unchanged. Re-open only on a corpus where the
partial population is dominated by areas that *do* have docs, or where `doc-missing` stops being 0 — the
masked `doc-missing` case is a genuine defect (a map row pointing at a file that is not there) rather than
an expected state, and it is unmeasured only because it has never occurred.

## Consequences for authors

- Adding a new area requires adding a row to `## Conditional Loading`. Until then the area reports
  `unmapped` — silently unmatched is no longer possible, but silently *unmapped* is the new failure mode the
  marker exists to surface.
- `index.md` `tags:` is retained and **inert**. It selects nothing; do not extend it expecting reach.
- A row's path is the first whitespace-delimited token after the U+2192 separator. Trailing prose on a row
  would otherwise be absorbed into the path — the live defect this ticket removed.

## Cross-references

- Spec: `cortex/lifecycle/requirements-loader-matches-index-tags-against/spec.md` — Requirements 5, 6, 7, 9,
  10; Proposed ADR 0037.
- Research: `cortex/lifecycle/requirements-loader-matches-index-tags-against/research.md`.
- Review: `cortex/lifecycle/requirements-loader-matches-index-tags-against/review.md` — the two-route
  coverage derivation and the five-lifecycle regression check.
- Ticket: #472. Prior art: #333 (the substring mechanism this replaces).
- Glossary: `cortex/requirements/glossary.md` — *area*.
- Area requirements: `cortex/requirements/lifecycle.md` — Architectural Constraints.
