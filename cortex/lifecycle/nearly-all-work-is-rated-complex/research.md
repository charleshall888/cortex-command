# Research: Establish whether the ~95% complex tier rate reflects the work or the clarify.md §5.2 rubric

**Headline: the ticket's evidence does not survive, and its conclusion does — for a different reason than it gives.**

`#451` argued that nearly all work is rated `complex`, so the tier axis cannot relieve ceremony, and proposed re-cutting §5.2. Research finds the supporting numbers invalid on three independent counts, the proposed remedy unsupported, and the underlying conclusion **true anyway** — because criticality, not tier, pins the corpus to the long road. The correct response is to reframe onto the criticality axis, not to re-cut the rubric and not to terminate.

## Codebase

The tier travels: decided at `skills/refine/references/clarify.md` §5.2 → written to backlog frontmatter by `cortex-update-item` → seeded into `lifecycle_start` by `cortex_command/refine.py:_read_backlog_frontmatter` → mutated by `complexity_override` or `cortex-refine reconcile-clarify` → read by `common.py:_read_tier_inner` and `requires_review()` (`common.py:1039-1055`), which is the literal short-road predicate.

**Two upward asymmetries, only one of them structural:**

- `cortex_command/lifecycle/complexity_escalator.py` — advisory. It **writes nothing** (`sys.stdout.write` only) and returns early when the tier is already `complex` (line ~302), so its advice can only ever point up. Threshold is 8 unresolved bullets.
- `cortex-refine reconcile-clarify` (`refine.py:276-300`) — **structural**. Appends only when `_TIER_RANK[desired] > _TIER_RANK[current]`; a downward desired value is silently suppressed, and both suppression and no-op print bare `{"state":"noop"}`.

**Consumers.** Four sites branch on tier, and none reads it alone:

| Site | Predicate |
|---|---|
| `transition_table.py:385,409` (`spec.approved` vs `-direct`) | `criticality ∈ {high,critical} OR tier == complex` |
| `transition_table.py:465,482` (`implement.review` vs `.complete`) | same OR |
| `specify.md:88` (critical-review trigger) | `tier == complex` **AND** `criticality ∈ {medium,high,critical}` |
| `research/references/fanout.md` | tier × criticality matrix — the only *graduated* consumer |

The AND/OR mismatch matters: moving mass out of `complex` buys short-road eligibility only in the low/medium-criticality cell, while removing critical-review eligibility at **every** criticality. A tier re-cut is simultaneously a review-coverage cut.

**Change surface.** `clarify.md` is canonical; `plugins/cortex-core/**` is a generated mirror (never hand-edit). **No test pins the §5.2 prose.** The only mechanical gate is the down-only reference-size ratchet: `skills/refine/references/size-pin.txt` = 20588, directory = 20583 — **5 bytes of headroom**. Net-additive rubric text needs a hand-raised annotated exception.

## Corpus Evidence

211 wild-light lifecycles with a `lifecycle_start`; 31 malformed lines skipped.

**Method warning:** filtering overrides with `isinstance(to, str)` silently drops 5 real events. Three schemas exist — plain `to`, a top-level `criticality` key (4 rows), and dict-valued `from`/`to` carrying both axes (1 row).

**Long-road baseline** (`criticality ∈ {high,critical} OR tier == complex`) — the surface the success metric must move:

| Month | Long road | Total | Share |
|---|---|---|---|
| 2026-05 | 30 | 43 | 70% |
| 2026-06 | 80 | 91 | 88% |
| 2026-07 | 53 | 54 | 98% |
| 2026-08 | 14 | 14 | 100% (partial) |

**Overall 181/211 = 85.8%.**

**Which clause forces the long road:**

| | Count | Share |
|---|---|---|
| Tier alone (`complex`, criticality below high) | 86/211 | 40.8% |
| **Criticality alone** (high/critical, tier below complex) | **1/211** | **0.5%** |
| Both | 94/211 | 44.5% |
| Neither — short road | 30/211 | 14.2% |

**Override direction:** 166/167 complexity overrides move up. 165 are `simple → complex`; **zero are `moderate → complex`**, because nothing ever sits at `moderate` to escalate from.

**Gate attribution:** of 166 overrides landing on `complex` — `clarify_reconcile` 86 (52%), `research_open_questions` 60 (36%), legacy/absent 19, `specify_open_decisions` 1. The `clarify_reconcile` rows are preceded by `clarify_critic` 91% of the time: they are **not escalations**, they are the placeholder floor being backfilled with Clarify's first assessment.

## Tier-Call Audit

Date-stratified sample of 16 pre-split lifecycles plus **all 8** post-split (the entire population under the current rubric); 23 read in total.

**Post-split: 8/8 agreement**, including one genuine `moderate` whose `research.md` states the reasoning explicitly — *"No design fork survives — the operator decided. The risk is entirely blast radius. Tier `moderate`, criticality `high`."*

**The precedent-clause hypothesis is falsified.** Across 15 endorsed `complex` calls the primary justifying clause was: competing designs 10, blast radius 3, precedent 2 — and precedent as *sole* justification appears once in 23 lifecycles, in a call the auditor scores as wrong. Corroborating corpus-wide: **152 of 180** complex lifecycles carry an explicit Options/Alternatives/Tradeoffs section.

**Independent corroboration from 16 operator-written justifications** (hand-written via the `log` escape hatch, since the typed verb took no `--reason` until `3a64142b`): the same distribution, plus a distinct misapplication — at least 3 justify `complex` on **file counts** ("push past simple's 1-3-file ceiling", "4+ files", "5+ files") when §5.2 says in bold that *size is not the test* and states no file ceiling anywhere.

## Web

Two well-documented analogues: **severity inflation** (SEV1 creep) and **priority inflation** ("everything is P0"), both independently reported across practitioner sources with converging diagnoses — vague or unenforced definitions let every reporter find a route to the top label. The formal statistical account is **range compression** in risk matrices (Cox 2008).

**MECE** (mutually exclusive, collectively exhaustive) indicts OR-ed category definitions where one disjunct is far broader than the others: the broadest disjunct silently sets the category's real boundary.

**Does not transfer:** reference-class forecasting and story-point anchoring describe *continuous* estimates biased *downward*; this is a *discrete* category collapsing *upward* — opposite shape of error.

**Strongest warning, and it constrains the success metric:** forced distributions. GE abandoned the vitality curve; Ford's fixed 10/80/10 ranking produced an age-discrimination class action settled at **$10.5M**. The documented failure is target substitution — the distribution becomes the optimized thing while judgment quality degrades. Evidenced alternative: anchor examples, calibration against borderline cases, periodic re-calibration, MECE redesign — **never a quota**.

No literature names the "one broad OR-clause absorbs the category" pattern; the closest formal term is *over-inclusive classification* from constitutional-law doctrine. Treat as internal hypothesis, not externally confirmed — and it was in fact falsified above.

## Requirements & Constraints

- **`project.md:40` "The short road"** — the ratified single predicate. Rubric *content* is prose-layer and free to change; the fork *structure* is wheel-owned (ADR-0024) and would need the transition table.
- **`project.md:23` Deletion bias** — two prongs. `#451` is efficiency-framed, so the applicable prong requires a stated **expected net effect on the surface it claims to shrink**. Resolved at Clarify: share of lifecycles taking the long road, measured by the existing `events.log` reduction, explicitly *not* a tier quota.
- **No ADR binds §5.2.** No ratified target distribution exists anywhere in `requirements/` or `adr/`. `#447`'s wontfix concerned *instrumentation for the simple bucket*, and does not foreclose a rubric change — but leaves no number to aim at.
- **`docs/policies.md`** — new MUST language requires an evidence artifact plus a demonstrated effort=high failure. "Tell the assessor more firmly" is gated; "when torn, take the lower tier" already sits there as the soft form that coexisted with a 97% complex rate.

## Adversarial

**The instrument-artifact explanation does not survive.** The claim was that the ~95% rate was produced by the escalator, which until 2026-08-03 wrote `complexity_override` itself at ≥2 open-question bullets, and that the rubric's own output was 11%.

- **The 11% figure is a placeholder count, not an assessment rate.** It is 22 of 211 `lifecycle_start` rows carrying `complex`; the other 186 carry the rank floor from `refine.py:118`. Proof the floor dominates: **all 8 post-split lifecycles start at `simple` and all 8 ran the full lifecycle** — but post-split, an assessed `simple` is routed *out* before a lifecycle exists. The value cannot be an assessment. Both commits anchoring the explanation (`14008792`, `d2e5394b`) rest on this number. **Do not cite it.**
- **The fix worked and the rate did not move.** Zero `research_open_questions` overrides post-fix (60 before). All 8 post-fix overrides are `clarify_reconcile`. Complex rate **7/8 = 87.5%** — indistinguishable from the 93% it was meant to explain.
- **Cause vs symptom is decided by the counterfactual.** Replaying with every escalator override stripped: actual 85.3% (180/211) vs **60.7%** (128/211). Only 52/211 (24.6%) owe `complex` solely to the escalator. It inflated every month and explained none. It was **ratifying a default-up, not creating one**.

**The population is complexity-selected by construction.** wild-light backlog tickets that *never entered a lifecycle*: 41 `simple` vs 72 `complex`. Those that did: 18 `simple` vs 142 `complex`. Simple work is routed out *by design*, so "89% of lifecycles are complex" substantially measures the routing rule. Across all assessed backlog tickets the complex share is **75%**. Neither `#451` nor the research controlled for this.

**n=8 cannot support the audit.** 7/8 complex → Wilson 95% CI **0.53–0.98**; likelihood ratio only 8.9:1 against a 60%-complex world. 8/8 auditor agreement has P = 0.168 if the rubric is 80% accurate. It rules out a catastrophic rubric and nothing more. It also rated a different proposition: all 8 final tiers equal the backlog value exactly, so it judged whether one-shot calls were defensible, not whether the axis is degenerate.

**Withdrawn:** the "under-tiering is invisible" finding. `multiplayerspawner-state-recovery-across-host-migration` is a pre-split lifecycle with an untouched rank-floor placeholder and no override — "no assessment recorded", not under-tiering.

**The ceiling, corrected and sharpened:** pinned by criticality alone — wild-light 43%, cortex-command 69%. And **7 of 8 post-split lifecycles are `criticality: high`**; tier is load-bearing in exactly 1 of 8.

## Synthesis

**The single most decisive fact:** the one correct `moderate` call in 375 lifecycles across two repos was made at `criticality: high`, so it took the long road regardless. It saved research fan-out (8 agents → 3) and critical-review, and nothing else. The middle tier was used exactly as designed and could not relieve ceremony — which is `#451`'s thesis, proven by the case that was supposed to refute it.

- `#451`'s **evidence** is invalid: era-mixed (`moderate` did not exist for 203/211 lifecycles), placeholder-contaminated, and drawn from a complexity-selected population.
- `#451`'s **remedy** is wrong: the audit endorses the calls, the falsified precedent-clause hypothesis removes the mechanism, and a re-cut would cut review coverage on the same stroke.
- `#451`'s **conclusion** is correct: the tier axis cannot relieve ceremony — because criticality pins 43–69% of the corpus and 7 of 8 of the post-fix sample.

## Open Questions

1. **What is the assessed complex rate on a population that is not complexity-selected?** All measurement so far counts lifecycles, which exclude routed-out `simple` work by construction. The backlog-ticket denominator gives 75%. *Deferred:* answerable by an existing-tools reduction over backlog frontmatter, and it should gate any further tier work rather than block this ticket.
2. **Does the post-fix rate hold at n≥30?** Current post-split population is 8. *Deferred:* re-measure in several weeks; no action can be justified on n=8 either way.
3. **Should `#448`'s `seeded` marker propagate past `lifecycle_start`?** It is discarded at `refine.py:263` (`_seeded`), so an override row still cannot be read without joining back to the seed. `3a64142b` is also untagged, so the marker is dormant in every consumer. *Resolved as a defect to fix:* propagation is a two-line change; release is a separate concern.
4. **Should `reconcile-clarify`'s suppressed downgrades be made observable?** *Resolved — no.* Across 211 lifecycles: 168 have exactly one `complexity_override`, 50 have zero, none has two, and **zero downgrades have ever been recorded**. The suppression can only fire on a second reconcile against a lower value, which has never occurred. Per Deletion bias this is harness machinery for a zero-instance event.
5. **Is the file-count misapplication worth correcting?** At least 3 of 16 written justifications cite a "1-3-file ceiling" that §5.2 explicitly disclaims. *Open:* a same-size-or-smaller clarification is nearly free against the 5-byte budget, but it is prose-only enforcement of a judgment.
6. **Does relief on the criticality axis reopen a settled question?** `#449` and `c6528012` both considered and explicitly rejected widening `medium` criticality to admit production code — "the highest-leverage single change and also lowers the review bar for exactly the work most likely to need review." *Open, and it is the central design question for any successor ticket.*
