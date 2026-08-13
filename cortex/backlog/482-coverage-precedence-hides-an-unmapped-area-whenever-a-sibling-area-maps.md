---
schema_version: "1"
uuid: cfc7195a-1f0f-4583-bf31-fa15658f1b3d
title: Coverage precedence hides an unmapped area whenever a sibling area maps
status: wontfix
priority: low
type: chore
created: 2026-08-12
updated: 2026-08-12
tags: ['lifecycle', 'requirements', 'loader']
areas: ['lifecycle']
---
Split out of wild-light #495 (`the audio tag routes to no requirements doc`) during its refine, 2026-08-12. Filed here because the change is to this repo's loader and to accepted ADR-0037, not to any consumer.

## Why

`load_requirements_cli.py` computes coverage with an explicit precedence: a doc that actually loaded outranks every partial failure. The source comment states the rationale — "a feature with one good area doc and one unmapped area is `loaded` — the drift check has something to run against."

The consequence is that a lifecycle declaring `areas: [audio, 2-5d]`, where `2-5d` maps and `audio` does not, emits `COVERAGE:loaded` and **no note at all**. Nothing tells the operator that `audio` routed nowhere. The `unmapped` state — the one ADR-0037 built the marker to surface — never fires, because it is reached only when *zero* areas hit.

That is in tension with ADR-0037's own stated purpose. Its *Consequences for authors* says: "silently unmatched is no longer possible, but silently *unmapped* is the new failure mode the marker exists to surface." In the mixed case the marker does not surface it.

## Why this is not simply a re-litigation of ADR-0037

ADR-0037 explicitly rejected a per-area tally, and it did so on measured grounds: "`unmapped` is the expected steady state for 61 lifecycles (`skills` alone 45), not a defect ... a per-area tally here is the recurring noise that would retrain operators to ignore the marker."

Read carefully, that argument is scoped to the **`unmapped` state's report** — the population of lifecycles where nothing matched. It does not measure, and does not rule on, the **partial** population: lifecycles reporting `loaded` that carry at least one unmapped area. The recorded state distribution (`loaded` 86, `unmapped` 61, `no-area` 44, `doc-missing` 0) does not break `loaded` down that way, so the noise cost of a partial-case note is unmeasured rather than measured-and-rejected.

**Measure that population first.** If partials are rare, a note costs almost nothing and ADR-0037's noise argument does not reach it. If they are common, ADR-0037's reasoning extends and this ticket should close as answered. In wild-light the count was **0 of 6** lifecycles carrying `areas:` at the time of filing — a repo where the failure mode is currently unreachable. This repo has the far larger corpus and is the one that matters.

## Edges

- Whatever shape is chosen, ADR-0037 is `accepted` and its *Measured outcome* section speaks to this area. A change needs an amendment or a superseding record, not a silent code edit.
- `cortex/requirements/lifecycle.md` line ~106 pins the loader contract ("Every run of the loader emits one `COVERAGE:(loaded|doc-missing|unmapped|no-area)` line on stderr, which the Review phase reads. → #472, ADR-0037"). Adding a fifth state breaks that enumeration; adding a *note* under the existing `loaded` state does not.
- Its `## Open Questions` already carries an adjacent deferral: "Whether the review phase's no-area-doc warning should also fire when a listed requirements path is reported absent, not only when nothing matched. Deferred: it changes the review skill's warning contract." Same contract surface — decide both together or state why not.
- A note-without-state-change is the cheap shape: keep `COVERAGE:loaded`, add one stderr line naming only the unmapped areas. It leaves every machine reader working.

## Touch-points

- `cortex_command/lifecycle/load_requirements_cli.py` — the coverage-precedence block and `UNMAPPED_NOTE_TEMPLATE`
- `cortex/adr/0037-area-to-doc-map-as-the-requirements-vocabulary.md` — amend or supersede
- `cortex/requirements/lifecycle.md` — the pinned contract line and the adjacent open question

## Resolution (2026-08-12) — closed by its own measurement gate

The ticket pre-registered the rule: *"If partials are rare, a note costs almost nothing... If they are
common, ADR-0037's reasoning extends and this ticket should close as answered."* Measured over this repo's
205 active lifecycles — the larger corpus the ticket said was the one that matters:

- state distribution `loaded` 89, `unmapped` 62, `no-area` 54, `doc-missing` 0
- **23 of the 89 `loaded` (25.8%)** carry at least one unmapped area — common, not rare
- their unmapped areas: `skills` 12, `tests` 3, `install` 2, `hooks` 2, `report` 2, `cli` 1, `docs` 1,
  `requirements` 1 — all areas with no doc planned, and `skills` (the largest) was declined outright in #476

So a note under `loaded` fires on one run in four and names areas that are unmapped by construction: the map
*is* the vocabulary, and 7 map rows cover a much larger declared-area space. That is exactly the recurring
noise ADR-0037 rejected, and it does reach the partial case. **No note added; no code change.**

The gap the ticket identified was real — ADR-0037 measured the `unmapped` state's report and never broke
`loaded` down this way — so the measurement is recorded in that ADR under *Amendment 2026-08-12*, with the
re-open trigger: a corpus whose partials are dominated by areas that *do* have docs, or a `doc-missing`
count that stops being 0. **0** `loaded` lifecycles currently mask a `doc-missing` hit, and all 7 mapped docs
exist on disk; a masked `doc-missing` is a genuine defect rather than an expected state, so it is deferred as
unreachable-today rather than decided against.

The adjacent open question in `cortex/requirements/lifecycle.md` (whether the review phase's warning should
fire on an *absent listed path*) is the `doc-missing` half and stays open on the same grounds — it is
unmeasurable while the count is 0, which is a different reason from this ticket's.

The consumer-side ticket (wild-light #495) is unaffected: `audio` routing nowhere there is answered by adding
a map row in that repo, not by changing this loader.
