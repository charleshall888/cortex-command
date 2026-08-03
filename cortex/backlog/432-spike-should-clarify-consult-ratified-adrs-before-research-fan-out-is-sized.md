---
schema_version: "1"
uuid: 40b01bd6-a4a4-4950-9925-04533957160e
title: 'Spike: should Clarify consult ratified ADRs before research fan-out is sized?'
status: wontfix
priority: medium
type: spike
created: 2026-08-03
updated: 2026-08-03
tags: ['refine', 'clarify', 'adr', 'token-efficiency', 'skills']
areas: ['skills', 'lifecycle']
complexity: complex
criticality: high
---
## Outcome (2026-08-03) — answered, no-go on both counts

Full measurement in `cortex/lifecycle/spike-should-clarify-consult-ratified-adrs/research.md`.

1. **Don't build the ADR-consult mechanism.** 0 DECLINES in 26 stratified samples across the only two
   repos with ADR corpora (upper bound ≤~11%); 19 BOUNDS + 5 TOUCHES means **24 of 26 firings would be
   false alarms** by this ticket's own "only the declining case pays" standard. The corpus is largely a
   *byproduct* of the work that cites it, not a body of prior constraints.
2. **The Why below is wrong four ways.** ADR-0036 retains the census fields and declines a *threshold*,
   so #404 is BOUNDS not DECLINES; the quoted ruling was committed **103 minutes after** the ticket was
   filed; **no critical-review ran** (a research angle caught it — this ticket charges the detector's cost
   to the thing it detected); and the escalator did fire (`simple→complex`, `medium→high`), falsifying
   "a simple/low ticket has no check at all".
3. **The real cause was already fixed.** The constraint #404 missed lived in the *requirements* corpus
   Clarify already rates against, unreachable because `cortex-load-requirements` read tags from a
   lifecycle `index.md` that could not exist at a fresh refine. `1553a379` (2026-08-03 10:42 EDT) made
   `cortex-refine start` seed the index from the backlog item — **3.5 hours after #404's lifecycle_start**.
   Verified: the loader now returns `engineering-rendering-perf.md` and `render-2-5d.md` for that feature.

Left undone deliberately: cortex-command's `## Conditional Loading` table has 6 triggers to wild-light's 73
(21% vs 75% of backlog items routing to an area doc). That is a content gap, not a mechanism gap.

## Why

Clarify rates **requirements alignment** but never reads the repo's *ratified decisions*. So a ticket
proposing work a governing ADR has already declined passes Clarify clean, gets sized for research fan-out on
tier × criticality, and is researched, specced, and reviewed before anything notices. The saving from *not
building* is the largest saving a refine can produce, and it is currently discovered last — if at all.

**Measured instance (wild-light #404, 2026-08-03).** The ticket proposed adding a `Camera3D` to the perf
probe to produce a 3D draw-cost number. `ADR-0036` had already adjudicated exactly that number: it "moves
with terrain material-key work and **is not a threshold**", and the successor yardstick is "the human
GO/NO-GO in a windowed session — **not a re-derived scalar**". The ADR even demonstrates its own point: the
figure it recorded moved 524→514 because of an unrelated *material-key rename*.

Nothing surfaced this until a **critical-review reviewer** pointed at it — i.e. after Clarify, after a
6-angle research fan-out, after the spec was written. By then the session had spent one research angle
deriving camera pose / FOV / frozen-calibration plumbing / frustum-cull arithmetic, one reviewer angle, a
drafted ADR, and a spec phase — all subsequently deleted. Roughly a third of that session's agent spend went
to a phase that should not have survived Clarify.

The existing safety net is real but late and conditional: `specify.md` §3b runs critical-review only at
`tier = complex AND criticality ∈ {medium, high, critical}`. A simple/low ticket proposing ADR-forbidden work
has no check at all.

**This is a spike, and "don't do it" is a legitimate outcome.** The obvious objection is that this taxes
*every* Clarify to save on the minority of tickets where a ratified decision already applies. Nobody has
sized that trade. Sizing it is the deliverable.

## Role

Determine whether Clarify should consult ratified decisions before research fan-out is sized, and if so, by
what mechanism and at what cost. Produce a recommendation with numbers, not a design.

## Integration

Candidate homes, to be weighed rather than assumed:

- **`clarify.md` §2, dimension 3 (requirements alignment).** The strongest conceptual fit: "does this conflict
  with a recorded decision?" *is* an alignment question, and dimension 3 already asks a weaker version of it
  against `cortex/requirements/`. Note the tension with clarify.md's own closing scope line — "Clarify checks
  intent, scope, and alignment only … technical feasibility to Research" — which the spike must reconcile:
  an ADR that *declines* the work is alignment, not feasibility.
- **`clarify-critic.md`'s rubric.** Cheapest intervention: add a challenge dimension asking whether the
  alignment rating accounted for ratified decisions. Direct precedent in **#161**, which added the
  parent-epic alignment check to this same critic. Costs one rubric line, no new verb, no new read — but only
  challenges the rating, it does not supply the ADR text.
- **A load step alongside `cortex-load-requirements`.** Most thorough, most expensive, and needs a selection
  mechanism (below).
- **`fanout.md` / `research-phase.md`.** Wrong home — by then the tier is already sized and the cost is
  already committed. Recorded here only to rule it out explicitly.

**The selection problem is the crux.** wild-light carries **62 ADRs**; reading the corpus at every Clarify is
a non-starter. Options to evaluate: tag routing (note `cortex-load-requirements` sources tags from
`cortex/lifecycle/<slug>/index.md`, which does not exist at a fresh refine — do not inherit that trap);
keyword grep from the ticket's own Touch-points; an ADR front-matter index; reuse of whatever
`cortex-adr-citation-audit` already builds over the corpus.

## Edges

- **Do not read the whole ADR corpus.** Any design whose cost scales with corpus size fails on the repos that
  most need it.
- **Do not make it blocking, and do not warn on absence.** Consumer repos need not have `cortex/adr/` at all;
  an absent corpus is a silent no-op, not a finding. Compare `cortex-load-requirements`, which correctly
  proceeds when `cortex/requirements/` is missing.
- **Do not let a "no relevant ADR" result read the same as "not checked".** That is the exact failure mode of
  `cortex-load-requirements` returning a bare `project.md` — indistinguishable from genuine absence.
- **Do not assume critical-review backstops it.** The gate is conditional on tier and criticality, so the
  cheapest tickets have the least cover.
- **Do not produce a new standing obligation.** A step that emits "consider these 9 ADRs" on every ticket,
  which readers learn to skip, is worse than nothing — it manufactures the ignorable-ceremony pattern the
  harness elsewhere works to retire.
- **An ADR that *bounds* work is not the same as one that *declines* it**, and neither is one that merely
  *touches the same subsystem*. Only the declining case pays for itself; a mechanism that cannot distinguish
  the three will mostly generate noise.
- **The ~1/3 figure above is one observation, not a rate.** #404 was an unusually rotten ticket (week-old
  diagnosis falsified by a cutover the next day, half of it already built). Do not generalise from it without
  sampling further closed lifecycles.

## Touch-points

`skills/refine/references/clarify.md` (§2 dimension 3, §5 handoff package, and the closing scope statement);
`skills/refine/references/clarify-critic.md` (rubric, and its documented 5-dimension soft cap — a sixth
"requires replacing one or extracting a separate critic"); `skills/refine/references/research-phase.md` and
`skills/research/references/fanout.md` (where the cost is committed, i.e. what a Clarify-side check protects);
`cortex_command/load_requirements_cli.py` (the closest existing mechanism, and its index-dependency trap);
`cortex_command/adr_citation_audit.py` (already walks the ADR corpus — check whether its index is reusable);
`cortex/adr/` in consumer repos. Prior art: **#161** (check added to clarify-critic), **#187**
(lifecycle/discovery token-waste cuts).

**Suggested deliverable:** a recommendation naming (a) the home, (b) the selection mechanism and its measured
per-Clarify cost, (c) the hit rate over a sample of closed lifecycles — how many would a ratified ADR have
redirected — and (d) an explicit no-go if (b) exceeds (c).
