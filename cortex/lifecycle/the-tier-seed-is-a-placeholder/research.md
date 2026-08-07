# Research: Give a filer a place to record a complexity estimate structurally distinct from Clarify's assessed complexity

Backlog item: `cortex/backlog/453-the-tier-seed-is-a-placeholder-so-a-filer-view-never-reaches-it.md`
Tier: complex · Criticality: high · Fan-out: 5 angles (4 core + adversarial)

**Clarified intent.** Give a filer a place to record a complexity *estimate* that is structurally distinct from Clarify's assessed `complexity`, so the lifecycle seed carries filer signal instead of the rank floor. Whether anything routes on that estimate was the open fork this research was asked to settle.

**Headline.** The ticket's two Why-section claims did not survive re-measurement, and the strongest surviving objection is that the value the ticket wants to improve is behaviorally inert at every fork that reads it. Research recommends **close wontfix**, with two real defects to file separately. The operator decides; the case is laid out in full below, including what would change the recommendation.

---

## Codebase

### The seed path, end to end

`cortex_command/refine.py:_read_backlog_frontmatter` (`refine.py:75-161`) returns `(tier, criticality, seeded)`. `seeded` is a `frozenset[str]` ⊆ `{"tier", "criticality"}` naming which fields fell back to a default rather than reading an assessed value.

- Absent backlog or absent `backlog_slug` → rank-floor defaults `("simple", "medium")`, `seeded = {"tier", "criticality"}` (`refine.py:113-118`). Deliberately **not** the reader default of `"moderate"` — the seed must be inert for the monotonic-up ratchet (`refine.py:88-97`).
- When the file exists: reads `complexity:`/`criticality:` via `update_item._get_frontmatter_value` (imported at `refine.py:21`), validates against `_ALLOWED_CRITICALITY`/`_ALLOWED_COMPLEXITY` (`refine.py:43-44`), coerces legacy values via `_LEGACY_COMPLEXITY_MAP` (`refine.py:57-60`), exits 64 on an invalid value.

Feeds `_cmd_emit_lifecycle_start` (`refine.py:430-523`), which writes the `lifecycle_start` row with `tier`, `criticality`, and — only when non-empty — a `seeded` key (`refine.py:454-468`). Idempotent via `_lifecycle_start_present` (`refine.py:194-213`).

`_cmd_reconcile_clarify` (`refine.py:288-427`) later ratchets toward Clarify's assessed values: reads `_seeded_fields_at_start` (`refine.py:232-258`) and `_fields_already_overridden` (`refine.py:261-285`), then stamps `from_seeded: true` on the resulting override row (`refine.py:336-337, 354, 369`) when the field is still at its pre-override seeded value.

**Who reads `seeded`/`from_seeded`: only `refine.py` itself.** `_seeded_fields_at_start` and `_fields_already_overridden` are the sole readers. No dashboard, transition table, or `common.py` path consumes either key. `common.py:reduce_lifecycle_state` (`common.py:984-1038`) reduces to `{tier, criticality}` scalars only; `read_tier`/`read_criticality` (`common.py:718-826`) and `lifecycle/state_cli.py` delegate to that one reducer and never look at the markers.

### Every writer of a tier into backlog frontmatter

- **`create_item.py` — no complexity flag exists.** Confirmed against the full file: `create_item()` (`create_item.py:164-175`) and the argparse surface (`create_item.py:242-258`) carry `title/status/type/priority/rework-of/parent/tags/areas/body` only. `--body` is appended verbatim *after* the frontmatter block (`create_item.py:210-220`) — it cannot set frontmatter keys.
- **`update_item.py` — the only writer.** `_SCALAR_FLAGS` registers `("--complexity", None)` / `("--criticality", None)` at `update_item.py:625-626`; `_DEST_TO_FRONTMATTER_KEY` maps them 1:1 at `:643-644`; `_SCALAR_DESTS` at `:661-662`. The write itself is generic (`update_item.py:499-551`) — **no schema or allowlist inside `update_item()`**; the CLI-layer tuples are the only gate.
- Skill-prose callsites: `skills/dev/SKILL.md:17` (rule 4) and `skills/refine/SKILL.md:47` (Clarify write-back), both mirrored into `plugins/cortex-core/`.

**Correction to the ticket's Why.** "It is the only reachable value" is false. A filer can reach `complexity:` today via `cortex-update-item` or by hand-editing the file. The accurate, narrower claim is that the **creation** verb has no such flag.

### Adding a new frontmatter key

No enforced schema exists anywhere. Checklist:

1. `update_item.py` `_SCALAR_FLAGS` / `_DEST_TO_FRONTMATTER_KEY` / `_SCALAR_DESTS` (`:620-670`) if settable post-creation. If settable at creation, `create_item.py` needs entirely new machinery — none exists.
2. `frontmatter_quote.STRING_INTENDED_KEYS` (`frontmatter_quote.py:36-38`) — only if the value could mis-resolve as non-string YAML. An enum needs no entry; `complexity`/`criticality` are themselves **not** in the allowlist — direct precedent for a same-shape field. Contract: ADR-0027.
3. Backlog index builder (`generate_index.py`) — zero hits for `complexity`/`criticality`; no change needed.
4. Validator — **none exists**. No test pins the frontmatter key set.
5. `skills/backlog/references/schema.md` (26 lines) is the documented schema and **omits `complexity` and `criticality` entirely** despite both being load-bearing. Pre-existing drift a new field would compound.
6. Dashboard/report readers (`dashboard/data.py:1438,1830-1831`, `poller.py:266,297`) read these from `pipeline-events.log`, not backlog frontmatter. A new backlog field would not surface there.

Existing items lacking the key break nothing — `_get_frontmatter_value` returns `None` and every reader has an explicit absent-case default.

### `skills/dev/SKILL.md` — actual structure

44 lines: **Step 1: Route** (5 first-match-wins rules, `:12-20`), **Step 2: Criticality Pre-Assessment** (`:22-26`), **Step 3: Backlog triage** (`:28-43`). No heading named "Step 1.4" exists, but the shorthand is established in-repo — `skills/refine/SKILL.md:53` says "hand back to direct implementation (dev Step 1.4)" meaning rule 4. The ticket is reusing an existing informal name, not inventing one.

**Step 2 is the closest live analogue and it writes nothing** — no frontmatter, no event, no file. It suggests a criticality level, carried forward as conversational prose into refine (`dev/SKILL.md:18`), where Clarify independently reassesses and overwrites via `cortex-update-item` (`refine/SKILL.md:47`). Nothing routes on the suggestion. It leaves no durable trace.

### The short-road fork machinery

`common.py:requires_review` (`common.py:1084`): `return tier == "complex" or criticality in ("high", "critical")`, called from `overnight/outcome_router.py:1084,1405`.

The phase-fork guards are separate:
- `spec_approve.py:_resolve_spec_route` (`:127-154`) — reads reduced `events.log` state, routes `plan` when `criticality in _LONG_ROAD_CRITICALITIES or tier == "complex"`, else `implement`.
- `implement_transition.py:_resolve_route` (`:155-177`) — same predicate, `review` vs `complete`.

The transition table is `cortex_command/lifecycle/transition_table.py` — wheel-owned Python code+data (frozen dataclasses, `TRANSITIONS` at `:291-511`), explicitly closed: "config selects parameters only — it can never introduce a state or edge" (`:12-23`). Relevant rows carry `Guard(precondition=..., reads=("criticality","tier"))`. Import-time invariant checks at `:570-609`, completeness test in `tests/test_transition_table.py`.

Docstrings in `spec_approve.py`/`implement_transition.py` cite a `criticality-matrix.md` that **does not exist** in the repo — apparently retired when routing moved into wheel-owned code under ADR-0024.

### Prior art and requirements matching

Two in-repo instances of "filer estimate later superseded": the `seeded`/`from_seeded` markers (same-field overwrite plus a boolean), and dev Step 2 (never persisted at all). **No existing pattern of two structurally separate, simultaneously-live fields** anywhere in frontmatter, events vocabulary, or the transition table.

`cortex-load-requirements` (`load_requirements_cli.py:200-266`) matches on the lifecycle `index.md` **`tags:`** field (`_read_tags`, `:133-150`) — it never reads the backlog item's `areas:` field. Direction is `tag.lower() in trigger_lower` (`:225-228`): the tag must be a *substring of* the trigger. `project.md:100`'s trigger is `"backlog/ticketing/issue tracker/backlog backend"`; this ticket's tags are `[lifecycle, tiering, backlog-verbs]`, and `"backlog-verbs"` is not a substring of it. Not a code bug — but a real gap for compound tags, and the field a human would expect to drive this (`areas: ['backlog']`) is never consulted.

---

## Prior Art & External Patterns

### Estimate-vs-actual as two fields

Every mature tracker with a two-field model keeps the creation-time number **frozen and non-authoritative** — its whole value is as a comparison baseline against a later, separately-owned number. None let the filer's estimate directly drive routing.

- **Jira** — Original Estimate (set once, frozen baseline), Remaining Estimate (live), Story Points (separate relative sizing). Original Estimate drives reporting/velocity math, never routing. [Atlassian docs](https://support.atlassian.com/jira-software-cloud/docs/estimate-an-issue/)
- **Azure DevOps** — Original Estimate / Remaining Work / Completed Work; Original set once, never mutated. [Microsoft Learn](https://learn.microsoft.com/en-us/azure/devops/boards/queries/query-numeric?view=azure-devops)
- **Linear** — team-level opt-in Estimate; **Triage** is a structurally separate inbox where non-member issues are reviewed before entering a team's workflow. The filer's input is one signal among several, and the routing *rule* is team-authored. Closest existing analogue to "filer estimate gated by a separate assessment". [Estimates](https://linear.app/docs/estimates), [Triage](https://linear.app/docs/triage)
- **GitHub Issues** — no built-in estimate field; teams bolt on Projects v2 custom fields. Open community demand for filer-populated estimates at creation. [Discussion 4416](https://github.com/orgs/community/discussions/4416)
- **Pivotal / Shortcut** — stories sit **unestimated** indefinitely and are *excluded* from velocity math rather than defaulting to a placeholder. Mature trackers make "no estimate yet" a first-class visibly-excluded state rather than a floor. [Pivotal](https://www.pivotaltracker.com/help/articles/estimating_stories/)

### Calibration literature

The evidence does **not** support treating a filer's creation-time estimate as reliable signal.

- **Cone of Uncertainty** — at initial-concept time, estimate error runs 4x high to 4x low, a **16x range**. Filing time is at or before that point, i.e. the worst position on the cone. [McConnell PDF](https://athena.ecs.csus.edu/~buckley/CSc231_files/McConell_ConeofUncertainty.pdf)
- **Reference-class forecasting** (Flyvbjerg/Kahneman) — the approach with real empirical backing works by substituting *a distribution over comparable past items* for a single guess. It is explicitly a critique of ad hoc single-point human estimates, which is exactly what a filer's number is.
- **Planning poker** — the one technique with controlled-study support (up to 40% accuracy improvement, *Journal of Systems and Software*), but its mechanism is **group** discussion, the opposite of a solo filer number; it also increased error in extreme cases. [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0164121208000885)
- **Jørgensen's reviews** — cost models land within 30% only ~57% of the time with *more* information than a filer has. One COCOMO study found **no positive correlation** between stated product complexity and actual effort, sometimes negative. [Review](https://www.researchgate.net/publication/222537419_Jorgensen_M_A_Review_of_Studies_on_Expert_Estimation_of_Software_Development_Effort_Journal_of_Systems_and_Software_70_37-60), [COCOMO study](https://arxiv.org/pdf/1509.08418)
- **#NoEstimates** — contested, thin evidence on both sides; strongest cited claim is anecdote-level.
- No study found measuring *filer-stage* (pre-triage) estimate accuracy specifically — the literature clusters on expert/team estimation. This is the biggest evidence gap relative to the actual design question.

### Anti-patterns

- **Anchoring is empirically demonstrated in software estimation specifically.** Jørgensen et al., 381 professionals across three experiments plus company-setting studies with 410 developers: numerical anchors measurably bias subsequent estimates; **the effect persists in developers trained to recognize it**; more credible or more precise anchors do not increase resistance. The only mitigation shown to work is explicitly listing arguments *against* the anchor before estimating. [Numerical anchors](https://www.sciencedirect.com/science/article/abs/pii/S0164121215000618), [First impressions](https://www.researchgate.net/publication/261450122_First_impressions_in_software_development_effort_estimation_Easy_to_create_and_difficult_to_neutralize)
- **Placeholder defaults are recognized as worse than empty fields** — Pivotal/Shortcut's "unestimated" design exists because a placeholder can be silently read downstream as real data while an explicit empty state cannot.
- **Gaming a known routing threshold** — plausible but **no documented case study found**; flagged as folklore, not evidence. The nearest documented analogue is severity inflation (below), a different mechanism.

### Routing on self-reported severity

The best-evidenced section for the fork.

- **Bug/QA practice separates ownership**: reporter owns severity (technical evidence), triager owns priority (business context). Where not enforced, motivated reporters inflate and "everything becomes P1", burying real criticals. [Severity vs Priority](https://bugreel.io/blog/severity-vs-priority-guide)
- **Support triage**: customer-set urgency is treated as *context for an agent's decision*, never the decision. Teams monitor degradation (e.g. high-priority volume >20% means criteria are too loose). [Triage practices](https://www.issuelinker.com/blog/support-ticket-triage)
- **Security disclosure**: HackerOne reporters self-select severity; only weak correlation with actual bounty (Spearman ρ = 0.34); triage teams routinely revise reporter severity **in both directions**. [HackerOne](https://docs.hackerone.com/en/articles/8495674-severity), [CVSS-bounty study](https://www.researchgate.net/publication/309614063_Vulnerability_severity_scoring_and_bounties_why_the_disconnect)

**Strong cross-domain precedent for advisory-only-with-confirmation; effectively zero for routing on a raw self-report. No precedent found anywhere for "may raise but never lower"** — it is a novel proposal, not an industry-tested pattern. Real systems use symmetric triager override.

### Required vs optional at creation

Each additional *required* field costs roughly 10–15% completion; HubSpot's 4→3 field test saw a 50% conversion lift. Baymard finds ambiguous optionality causes 32% of users to hit validation errors. Required risks garbage-in from filers with no basis to answer — precisely the population the Cone of Uncertainty says is least equipped. [Baymard](https://baymard.com/blog/required-optional-form-fields), [Form stats](https://www.feathery.io/blog/online-form-statistics)

---

## Requirements & Constraints

### Front-door evidence bar — `project.md:23`

> "a ticket adding harness machinery names its specific evidence in its Why, and an efficiency-framed ticket states its expected net effect on the surface it claims to shrink"

Option (a) was covered by the ticket's cited evidence *as filed* — but see Evidence Re-derivation, which removes that footing. Options (b)/(c) are efficiency-framed ("may raise ceremony", "cheapest triage") and carry **no stated net effect**; they fail the bar as written. The ticket's own Edges concede this: "any triage saving depends entirely on the routing decision above."

Separately, the stated net effect for (a) — "the share of lifecycles whose seed is a placeholder, currently 186/211 = 88%" — is a **prevalence figure, not an effect**. It says how often the situation occurs, not what shrinks. The efficiency prong is unmet even for (a).

Also binding: *"A surface with no consumer that fails on its removal carries the presumption of removal; discharge requires either a consumer that turns a build or gate red when the surface is removed — not a report-only or manually-invoked script — or a filed bug recording observed failure."*

### Triage is verb-owned — `backlog.md:102`

> "Triage recommendations are computed by the `cortex-backlog-triage` verb from readiness (`spec:` presence), never from ticket `type`… the verb-not-prose boundary is #343"

Direct precedent against putting (c)'s routing logic in `dev/SKILL.md` prose. Any routing must extend a **verb**.

### The short road — `project.md:40`

The single predicate `criticality ∈ {high, critical} OR tier == complex` applies **inside** the lifecycle, at spec exit and implement exit, via the served transition table. #453's routing question is **upstream** — whether to enter the lifecycle at all. So (c) may never touch the transition table; (b) touches it only if "raise ceremony" maps onto the phase-fork guards, in which case `project.md:40`'s "one predicate" wording needs updating and the change lands in wheel-owned code with a release-cadence cost (ADR-0024: "a gate-matrix change requires a wheel release to take effect").

### ADR-0024 — closed transition table

> "config selects parameters only — it can never introduce a state or edge" (`0024:23`)

(a) never touches it. (b)/(c) require a wheel code change if implemented via new guards/edges — permitted, but not a config toggle.

### ADR-0027 — frontmatter-scalar write contract

Applies to all three. An enum (`simple|moderate|complex`-shaped) needs no `STRING_INTENDED_KEYS` entry — `complexity`/`criticality` themselves have none. Numeric story-point-style values **must** be allowlisted or they reproduce the exact type-leak ADR-0027 exists to close. Needs an explicit spec line either way.

### Backend model — `backlog.md:30,88,94,97`

> "Backend routing lives at the skill/consumer layer; the `cortex-*` CLI tools remain cortex-backlog-only"

On an external backend there is no frontmatter file — the ticket is a GitHub/Jira issue driven by LLM best-effort. The field is **inert** there, which matches the zero-per-tool-maintenance NFR. But note the sharper reading: `cortex-create-backlog-item` is not the filing path on an external backend at all, so the flag is *unreachable*, and (b)/(c) would make control flow differ per backend — a divergence, not mere inertness. Consumer skills already branch on resolved backend (`backlog.md:48`), so gating on `backend == cortex-backlog` is an established pattern.

**Backward compatibility** (`backlog.md:88`, "no behavior change for existing local-backlog repos"): any routing change must fire **only** when a filer explicitly set an estimate, never on its absence.

### Vocabulary — `glossary.md`

7 lines, defines only `scene` and `cockpit`. No entries for `tier`, `complexity`, `criticality`, or `estimate`. No glossary-level collision.

### #450 (wontfix) — binding on all three options

> "Do not simply add `--complexity`/`--criticality` flags to the filing verb. That would legitimise the bypass rather than close it — the whole point is that the tier is Clarify's output, not the filer's input." (`450:35`)
> "Presence of a tier at `backlog` status is therefore **not** the detector; absence of a corresponding event is." (`450:36`)

Forces a structurally distinct key. A data-shape constraint, not a routing one — it applies identically to (a)/(b)/(c).

### #447 (wontfix) and #451 (complete)

#447 died because its instrument needed a denominator it could not observe — any efficiency claim for (c) needs its own real denominator and cannot borrow #447's approach. #451 is the split parent, **status complete**: its subject is the upward-only tiering asymmetry.

### Lifecycle-gating (CLAUDE.md)

- **(a)** — wheel-internal Python only (`create_item.py`, possibly `frontmatter_quote.py`), plus a doc line in `backlog-author/SKILL.md`. Minimal shipped-surface touch.
- **(b)** — adds `refine.py` / `clarify.md` / `refine/SKILL.md`, possibly the ADR-0024 table.
- **(c)** — everything in (b) plus `dev/SKILL.md` and a new or extended triage verb.

### Option/constraint matrix

| Constraint | (a) Advisory | (b) Downward-safe | (c) Full routing |
|---|---|---|---|
| Front-door evidence bar (`project.md:23`) | **Fails** — net effect is a prevalence figure; no-consumer presumption applies | **Fails** — no stated net effect | **Fails** — no stated net effect |
| Complexity / "simpler wins" (`project.md:19`) | Satisfied | Needs justification | Needs justification |
| Short road (`project.md:40`) | Untouched | **Conditional** — violated only if implemented via the phase-fork predicate | Satisfied — targets a different, upstream fork |
| Triage is verb-owned (`backlog.md:102`) | N/A | Applies | **Requires** verb implementation, not SKILL.md prose |
| ADR-0027 | Satisfied if enum; allowlist if numeric | Same | Same |
| ADR-0024 closed table | Untouched | **Conditional** — wheel change + release cost | Likely untouched |
| Backward compat (`backlog.md:88`) | Satisfied | Requires explicit absent-estimate guarantee | Same, stronger |
| External backend (`backlog.md:94,97`) | Inert | Control flow diverges per backend | Same |
| #450 field-distinctness | Satisfied by design | Same | Same |

---

## Evidence Re-derivation

**Verdict: net weakens #453 as written.** Both cited numbers are unreproducible as stated. A correctly-conditioned re-measurement finds a smaller version of the same real phenomenon, on a cohort too small to size it.

### Q1 — assessed complexity on a non-complexity-selected denominator

Denominator: every backlog ticket with a `complexity:` key holding a valid value. Missing-key tickets reported separately, never folded into `simple`.

| Repo | assessed n | simple | moderate | complex | complex % | MISSING | OTHER |
|---|---|---|---|---|---|---|---|
| wild-light | 295 | 66 | 9 | 220 | 74.6% | 165 | 7 |
| cortex-command | 303 | 44 | 2 | 257 | 84.8% | 146 | 1 |
| pixel-art-generator | 25 | 6 | 0 | 19 | 76.0% | 8 | 6 |
| gaggimate-barista | 11 | 1 | 0 | 10 | 90.9% | 14 | 0 |
| Team-Builder-Bot | 0 | – | – | – | – | 0 | 0 |
| **Pooled** | **634** | **117** | **11** | **506** | **79.8%** | **333** | **13** |

This answers research OQ1 from `nearly-all-work-is-rated-complex`: on a population not complexity-selected by construction, complex share is **79.8%**, close to that research's own 75% wild-light estimate — not the ~89–95% lifecycle-denominator figures.

**Could not reproduce the selection-effect gap.** The prior research reported wild-light never-entered 64% complex vs entered 89%. Three operationalizations of "entered a lifecycle" (frontmatter `lifecycle_slug`; filename-slug matching a lifecycle or archive dir; the OR) all show **no meaningful gap** — wild-light 73–75% either way, cortex-command 82–86% either way. Unresolved: the prior matching method is unknown. The Q1 headline does not depend on it.

### Q2 — era control

The three-tier vocabulary landed at `e3ee3b4c` ("Split the complexity tier into simple/moderate/complex"), **2026-08-03 — three days ago**. Restricting to tickets created on or after that date:

| Repo | post-era n | assessed | simple | moderate | complex |
|---|---|---|---|---|---|
| wild-light | 47 | 28 | 11 | 6 | 11 |
| cortex-command | 32 | 11 | 3 | 1 | 7 |
| **Pooled** | **79** | **39** | **14 (35.9%)** | **7 (17.9%)** | **18 (46.2%)** |

`moderate` is used substantially post-era (17.9% vs 1.7% all-time). **The all-time near-absence of `moderate` is almost entirely an era artifact**, exactly as the prior research warned. The cohort where "zero `moderate → complex`" could mean anything is 39 tickets over 3 days.

### Q3 — is the seed actually a placeholder?

1. **Naive** (any `lifecycle_start` carrying a `seeded` key, all-time): 16/654 = 2.4%. **Meaningless** — the `seeded` key was added at `3a64142b`, **2026-08-04 10:34**; 638 of 654 rows predate the instrumentation, where "no key" means *can't tell*.
2. **Corrected** (rows at or after the instrumentation boundary): **n=21**. **16/21 = 76.2%** seeded from the placeholder default for both fields; 5/21 carried real assessed values.

**Directionally confirms the claim, but the number is 76% on n=21 over two days, not 88% on n=211.** Real effect, unknown size.

An independent count over this repo's 302 lifecycles with a start row (including `archive/`) puts the placeholder-seed rate at **56%**, and adds the corrective figure the ticket never measures:

| | count | share |
|---|---|---|
| lifecycles with a start row | 302 | — |
| started at the `simple` floor | 169 | 56% |
| …subsequently overridden | 132 | **78% of floor seeds** |
| …never overridden | 37 | 22% |
| …never overridden **and** criticality low/medium | **25** | **8.3% of all lifecycles** |

The escalator already corrects **78% of floor seeds**. The residual is 25 lifecycles, and for each of those, `simple` + low/medium criticality + short road is the intended cheap path. No lifecycle is named where the seed produced a wrong outcome.

### Q4 — do first-assessments and escalations already look different?

Pooled `complexity_override` + `criticality_override` events, n=509:

| | count | % |
|---|---|---|
| carries a `gate` field | 421 | **82.7%** |
| carries `from_seeded: true` | 7 | 1.4% (instrumentation 2 days old) |

Gate breakdown: `clarify_reconcile` 282 (55%), `research_open_questions` 129 (25%), no-gate/legacy 88 (17%), `specify_open_decisions` 4, `clarify`/`clarify_assessment` 5, other 1.

**The distinguishing information is already present for 83% of overrides via the `gate` field alone.** Corroborated by timing: `research_open_questions` overrides **never fire before** the clarify→research transition (0/77) — genuine downstream escalations — while `clarify_reconcile` fires at the boundary, i.e. first-assessment backfill. The remaining 17% are pre-instrumentation legacy rows, a closed historical gap.

**This refutes the ticket's claim that "every first assessment is indistinguishable in shape from an escalation."** It holds only for the 17% predating the `gate` field.

Note a correction to the prior research: its 91% "preceded by `clarify_critic`" discriminator is a **false lead** — it fires for ~98% of *both* classes, because Clarify runs early in essentially every lifecycle regardless of when the override lands.

### Q5 — would a filer estimate have helped?

Post-era cohort, n=39:

| tier | n | mean body chars | mean tags | type mix | priority mix |
|---|---|---|---|---|---|
| simple | 14 | 4,366 | 2.7 | 9 chore / 3 bug / 1 feature / 1 spike | 0 high / 9 med / 5 low |
| moderate | 7 | 6,509 | 4.1 | 5 bug / 2 chore | 3 high / 3 med / 1 low |
| complex | 18 | 6,227 | 4.3 | 11 bug / 4 feature / 2 chore / 1 spike | 9 high / 8 med / 1 low |

`type=chore` and `priority ≤ medium` are strong markers for eventual `simple` — **0 of 14 simple tickets were filed `high` priority**. Body length and tag count both scale with tier. n=39 is too small for a regression, but four independent, filer-visible, zero-cost signals all move together: a plausible existence proof that filer-stage signal is recoverable.

### Corpus integrity

- **78 lifecycle event logs** (14 wild-light / 61 cortex-command / 3 gaggimate) are in a **legacy YAML format unparseable by the JSONL reader** every analysis here uses. Excluded from every count. Nobody has measured what is in them.
- **154 of 303** cortex-command tickets carrying a `complexity:` have **no `lifecycle_slug`** (131 complex, 21 simple, 2 moderate) — no assessment event can be located for them.
- `lifecycle_slug` is set on **153 of 449 tickets (34%)**; **200 of 353 lifecycle dirs have no ticket pointing at them**. The reverse join is impossible: `lifecycle_start` rows carry no backlog key. Estimate-vs-assessment is computable for at most a third of tickets, non-randomly selected.
- No name overlap between `cortex/lifecycle/*` and `archive/*` in any repo checked — dedup by name union is safe.

Analysis script: `/private/tmp/claude-501/-Users-charliehall-Workspaces-cortex-command/520b86e5-805e-4b9d-bf5f-36ff6a91fcc3/scratchpad/analyze.py` (Q1–Q3; Q4/Q5 refinements were inline one-offs not folded into the file).

---

## Adversarial Review

### The `moderate` value is behaviorally inert at every fork that reads the seed

Grant the ticket's numbers entirely and the harm still isn't established, because **nothing forks differently at `moderate` than at `simple`.** The predicate governing every phase fork is `tier == "complex" or criticality in ("high", "critical")` — `common.py:1084`, duplicated at `spec_approve.py:152` and `implement_transition.py:172`. `simple` and `moderate` take the identical branch everywhere. The only tier-keyed consumer that distinguishes them is the research fan-out matrix (`fanout.md:8-11`), which the same file declares is "**an upper bound on breadth, not a quota**" — an advisory ceiling, not a route.

So seeding `moderate` instead of `simple` changes a string in an events row and one soft upper bound.

**Verified precision fix (orchestrator).** `moderate` is not *globally* inert: `pipeline/dispatch.py:153-157` gives it 200 turns / \$25 against `simple`'s 150 / \$5, and `dispatch.py:181-185` lifts `(moderate, low)` and `(moderate, medium)` to `"high"` effort where `simple` gets `"low"`. But that reads a **different** complexity value — the per-task field parsed from the plan document (`parser.py:396`, defaulting to `"simple"`), which the backlog/lifecycle seed never reaches. The inertness claim holds for the value #453 is about. See Open Questions for the separate placeholder-floor problem this exposes.

**And the legibility half already shipped.** `refine.py:354,369` stamp `from_seeded: True` onto the override row, and the comment at `refine.py:327-333` states the ticket's own rationale verbatim: *"an override row reads `simple -> complex` identically whether `moderate` was weighed and rejected or never considered at all — and the override row is what every corpus count reads."* That is Why-paragraph-3, fixed, in the tree, three days ago. The ticket's Edges call this "complementary, not a substitute" — but the thing it says the markers lack ("here is what the filer thought") is a different, unevidenced want, not the measured harm.

Also: `clarify.md:33` defines `simple` as "handle directly, **no lifecycle**." The floor value, read as an assessment, means *this should not be in a lifecycle at all* — which is why it is inert, and why the lifecycle denominator excludes real `simple` by construction. The ticket's 88% measures a population defined to exclude the value it counts.

### 2. Anchoring destroys the calibration by construction

The estimate would live in backlog frontmatter. Clarify reads backlog frontmatter (`refine.py:75-161`), and the assessing agent reads the ticket file wholesale. Jørgensen's result says the assessment then regresses toward the estimate. The "free" divergence data becomes a measurement of how well the anchor propagated.

Worse: the anchored assessment is the value the whole lifecycle forks on. The mechanism producing the calibration byproduct **corrupts the tier signal**, and the corruption is invisible because both numbers agreeing *reads as good calibration*.

For calibration to work, the estimate must not appear in any text the assessing agent reads before committing its assessment. Two designs survive:
- **Sidecar** — estimate stored outside the ticket, revealed after Clarify writes back. More machinery than a field; the ticket's Edges forbid built machinery.
- **Blind-then-reveal** — a verb that refuses to surface the estimate until `complexity_override` has landed. The only cheap anchoring-proof shape, and **incompatible with (b) and (c) by construction** — you cannot route on a value the router may not see.

"Calibration comes free" and "the estimate seeds the lifecycle" are mutually exclusive. The ticket asks for both.

### 3. Q5 cuts both ways — and "infer the seed" is a worse trap

If `type`, `priority`, tag count and body length already predict the tier, a verb could compute the seed at creation from fields filers already fill: zero filer cost, no new key, no *new* anchor (those inputs are already visible to Clarify), no #450 surface. Strictly dominant over (a) on every axis the ticket cares about.

Reject it anyway: it is a **classifier fitted to a contaminated corpus** whose predictions then feed the corpus it was fitted to — self-fulfilling and silently drifting. n=39 over a three-day-old vocabulary is an anecdote with percentages. And it inherits the headline: the output would be a `moderate` that no fork reads. A model in the harness is worse than a field.

The honest residue of Q5 is the web angle's Pivotal/Shortcut finding, which no core angle carried into a recommendation: **make "unestimated" a first-class excluded state rather than picking a floor.** That is what `seeded`/`from_seeded` already do. The industry's answer is shipped.

### 4. The measurement infrastructure cannot support any tier conclusion right now

Beyond the corpus-integrity findings above, one defect is new and consequential:

**The contamination has a known direction, and the harness instructs it.** `skills/dev/SKILL.md:17` (rule 4) tells the agent, for any simple change: implement it here, then `cortex-update-item {slug} --status complete --complexity simple`. That writes a complexity with **no lifecycle, no `lifecycle_start`, and no `complexity_override`** — exactly #450's shape, sanctioned in shipped prose. #450 was closed wontfix having concluded the values "arrived through a path neither of those owns — most likely hand-authored frontmatter in the `--body` payload." **That channel hypothesis is wrong; the channel is dev rule 4.** Consequences: #450's wontfix rests on a false diagnosis; the "#450 detector" that #453's Edges say the new field must not trip currently fires on the harness's own documented happy path; and the corpus is biased toward `simple` in a way that both inflates any "we under-assess simple" argument and deflates the ticket's own 88%.

### 5. Per-option failure modes

**(a) Advisory only — fails the repo's own deletion bar on day one.** `project.md:23` requires a consumer that turns a build or gate red on removal, or a filed bug recording observed failure. Advisory-only means *by definition* there is no such consumer. (a) is born presumed-deletable and can only be discharged by becoming (b)/(c) or by building the report the ticket forbids. Decay path: filers (mostly agents) stop populating it; existing values go stale against a vocabulary that already changed once in three days; the key becomes frontmatter nobody reads. Who notices: nobody. When: the next trim audit — the exact "net additions dressed as efficiency" anti-pattern named at `project.md:23`.

**(b) Downward-safe — no external precedent, and it worsens the disease #451 diagnosed.** "May raise, never lower" is the monotonic-up reconcile that already exists (`refine.py:344`, `_TIER_RANK`). #451 — *"Tier assessment has three upward forces and no downward path"*, status **complete** — is the sibling this was split from. (b) adds a **fourth upward force and still no downward path** to a system whose completed sibling names that asymmetry as the defect.

**(c) Full routing — not "skip Clarify" but "skip the lifecycle", and it buys nothing.** Per `clarify.md:33`, `simple` means "handle directly, no lifecycle": a filer writing `simple` removes the ticket from the assessment path entirely, silently, leaving no record — which is why #447 was closed wontfix. Self-reported severity drifts toward whatever minimizes friction, and here that direction erases the evidence of its own error. Second kill: **dev rule 4 already does this, better** — `dev/SKILL.md:17` routes simple work to direct implementation on the *triage agent's* judgment, made with ticket and repo in hand. (c) moves the identical decision from the best-informed moment to the worst (filing time, top of the cone) and freezes it. A strict downgrade of a live capability, and under `backlog.md:102` it has nowhere legal to live in the surface the ticket names as its locus.

### 6. Assumptions that won't hold

**"A filer will fill an optional field."** In this corpus the filer is usually Claude. `skills/backlog-author/SKILL.md:9` disclaims frontmatter outright, and `backlog.md:96` records that discovery and morning-review compose bodies through backlog-author. So the estimate would be supplied by the calling skill — an LLM — and later assessed by Clarify — the same model family reading the same ticket. **The estimate/assessment distinction the entire design rests on collapses into one model grading its own earlier guess.** The calibration comparison would measure self-consistency, not filer-vs-assessor divergence. No core angle raised this.

**"A filer's estimate means the same thing as Clarify's tier."** It cannot, and the ticket half-admits it — then proposes routing options that read it exactly that way. If the vocabularies genuinely differ, the calibration comparison is a category error; if they are the same, #450's objection lands at the data layer too.

**"The corpus will stay stable enough for the comparison to mean something."** The vocabulary is three days old; the `seeded` instrumentation two. A calibration series spanning a vocabulary change measures the change.

**"This won't become a reason to build a report."** It will. Estimate-vs-assessment stored and never compared *is* (a), which fails the no-consumer bar. The only discharge is building the comparison — the one thing the ticket forbids.

**"Adding a frontmatter key is free."** Nearly, but `skills/backlog/references/schema.md:5-21` is a documented table; adding a key without a row is drift.

### 7. What the core angles got wrong or missed

- **None asked whether `moderate` does anything.** The load-bearing omission; `common.py:1084` was cited as the fork location without anyone noticing it never mentions `moderate`.
- **Codebase angle** named dev Step 2 as the closest live analogue. The closer analogue is **dev Step 1 rule 4** (`dev/SKILL.md:17`), which *does* write, writes `complexity`, and does so with no assessment event. It also missed `lifecycle_slug` (`schema.md:14`), the join key the calibration promise depends on.
- **Codebase angle** correctly found `seeded`/`from_seeded` are read only by `refine.py` — then didn't draw the conclusion: under `project.md:23` that makes them presumed-deletable, so the ticket's Edges lean on a surface that is itself deletion-bias-exposed.
- **Evidence angle**: `seeded` appears on 6 of 185 `lifecycle_start` rows in this repo; its n=21 cohort size should be read against that. Core corrections stand.
- **Requirements angle**: "inert on external backends" understates it — the filing verb isn't the path there at all, so the flag is unreachable and (b)/(c) make control flow differ per backend.
- **Web angle**: its best finding — Pivotal/Shortcut's first-class "unestimated" excluded state — is the actual answer, and no angle connected it to the already-shipped `seeded` markers that implement exactly that.
- **Foreclosed by the ticket's framing**: it assumes the seed is the problem. The alternative it never entertains is that **the tier vocabulary has three values and two behaviors**, so the middle value is decoration. Collapsing tier to the binary the code already uses would delete a vocabulary, a fan-out row, and this ticket.

### Recommendation: close wontfix

The measured harm is a string in a log row that no fork reads; the legibility remedy shipped two days ago; the escalator already corrects 78% of floor seeds; the residual is 8.3% of lifecycles with no demonstrated bad outcome; the headline 88% does not reproduce (56% here); calibration is unobtainable without anchoring; (a) fails the no-consumer bar on day one; (b) adds a fourth upward force to the asymmetry #451 was filed about; (c) is a worse-informed duplicate of dev rule 4 with nowhere legal to live.

**What would change it:**
1. A fork, gate, or transition-table row that reads `moderate` and behaves differently from `simple` — a route, not an advisory upper bound. Without this the harm is cosmetic and nothing else matters.
2. A named lifecycle among the 25 that ran end-to-end on an unexamined floor seed where the outcome was **wrong** — under-planned, under-reviewed, reworked. One instance turns 8.3% from a bound into evidence.
3. Evidence that a material share of tickets are filed by a **human** rather than by discovery/morning-review through backlog-author. If "filer" means a person, the estimate is genuinely independent signal and the collapse argument dissolves.
4. A blind-then-reveal design costed at less than the field it replaces — the only anchoring-proof shape, and it forecloses (b) and (c).

**Caveat:** the adversarial measurements are this repo only (including `archive/`). The ticket's 186/211 is from an unnamed consumer corpus that could not be located. Treat these as a reproducible second data point, not a refutation of a number nobody can find.

---

## Open Questions

1. **Does the operator accept the close-wontfix recommendation?** — *Deferred to spec approval.* Research cannot close a ticket. The full case is above, including the four falsifiers. This is the decision the Spec phase exists to record either way.

2. **The routing fork (a)/(b)/(c) — resolved conditionally, not chosen.** Every option fails the front-door evidence bar as currently stated: (a) on the no-consumer presumption, (b)/(c) on the absent net-effect statement. If the ticket proceeds despite the recommendation, **(a) with a blind-then-reveal verb** is the only shape that is both anchoring-proof and precedent-backed; (b) has no precedent found in any tracker or disclosure program and adds a fourth upward force to #451's diagnosed asymmetry; (c) is dominated by dev rule 4 and illegal under `backlog.md:102` in the surface the ticket names.

3. **`dev/SKILL.md:17` rule 4 writes `complexity` with no assessment event** — the live #450 shape in shipped prose, contaminating 154 of 303 assessed tickets in this repo. #450's wontfix rests on a false channel hypothesis ("hand-authored frontmatter in the `--body` payload"). *Out of scope here; should be filed separately.* Note this is also the strongest argument that #450 should be reopened rather than left wontfix.

4. **Ticket↔lifecycle joins are not sound enough for any calibration analysis.** `lifecycle_slug` is set on 34% of tickets; 200 of 353 lifecycle dirs have no ticket pointing at them; `lifecycle_start` rows carry no backlog key; 78 event logs are in an unparseable legacy YAML format. *Out of scope; file separately.* Any future tier work depends on this being repaired first.

5. **The per-task complexity floor in the overnight path is a separate, possibly larger instance of this ticket's own thesis.** `parser.py:396` defaults a task's complexity to `"simple"` when the plan omits it, and unlike the lifecycle seed that value **does** drive behavior: `dispatch.py:153-157` (150 turns/\$5 vs 200/\$25) and `dispatch.py:181-185` (`"low"` vs `"high"` effort). A placeholder there under-resources a dispatched agent. Nobody has measured how often the plan omits it. *Deferred — not #453's surface, but it is where the ticket's argument would actually have teeth.*

6. **Is the tier vocabulary's middle value decoration?** Three values, two behaviors at every seed-reading fork. Collapsing `tier` to the binary the code already uses would delete a vocabulary, a fan-out row, and this ticket. *Deferred — a larger deletion-biased question than #453 and it should not be settled inside it.*

7. **`project.md:59` cites "→ ADR-0029" for "Lifecycle identity is the canonical slug", but ADR-0029 is "Per-pattern side ruling for sync-allowlist conflicts"** and no ADR carries that content (verified against `cortex/adr/`). Docstrings in `spec_approve.py`/`implement_transition.py` similarly cite a non-existent `criticality-matrix.md`. The repo's report-only ADR citation audit (`project.md:41`) evidently does not cover `cortex/requirements/` or docstrings. *Out of scope; file separately.*

8. **`cortex-load-requirements` never consults a ticket's `areas:` field** and matches tags only as substrings of a trigger phrase (`load_requirements_cli.py:225-228`), so `backlog-verbs` silently failed to load `cortex/requirements/backlog.md` for this very ticket. Not a code bug, but a real gap for compound tags. *Out of scope; file separately.*

9. **The prior research's selection-effect gap could not be reproduced** (64% vs 89% on wild-light) under three operationalizations of "entered a lifecycle". *Deferred* — the Q1 headline does not depend on it, but it means one more figure in `nearly-all-work-is-rated-complex/research.md` is unconfirmed.
