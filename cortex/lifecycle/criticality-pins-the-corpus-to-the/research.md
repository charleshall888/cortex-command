# Research: Ceremony relief on the criticality axis

**Clarified intent.** Decide whether ceremony relief can come from the criticality axis, evaluating all four candidate routes against the measured ceiling that caps the tier axis, so Spec can commit to exactly one route.

**Tier** complex · **Criticality** high · Ticket #452 · Backlog areas: `lifecycle`

> **Headline for Spec — the ticket's thesis is inverted.** The 48%/75.4% ceiling is real but answers a different question than the one the routes turn on. Measured **marginal** relief: dropping the criticality clause entirely frees **5.0%** (cortex-command) and **2.6%** (wild-light); dropping the tier clause frees **10.7%** and **33.1%**. On the representative corpus the tier axis is worth **12.7×** more than criticality. Every criticality-axis route buys ~2.6% where it counts. Supporting findings: the Plan-skip arm has **never fired** in ~650 lifecycles; the predicate has **five implementations with divergent defaults**; the two corpora fail for **opposite reasons**; and Review has a **measured 15.4% catch rate** it would be reducing.

---

## Codebase

### The executable predicate — five independent implementations

The OR predicate is reimplemented, not shared:

| # | Site | What it decides |
|---|---|---|
| 1 | `cortex_command/common.py:1084` — `requires_review(tier, criticality)` | Shared helper. Imported by exactly **one** module. |
| 2 | `cortex_command/lifecycle/spec_approve.py:153` | Spec-exit fork: Plan vs direct-to-implement |
| 3 | `cortex_command/lifecycle/implement_transition.py:175` | Implement-exit fork: Review vs complete |
| 4 | `cortex_command/lifecycle/next_verb.py:245` | Served-loop escalation |
| 5 | `cortex_command/overnight/advance_lifecycle.py:265` | Morning-review gate before machine-marking complete |

`advance_lifecycle.py:256-263` carries a comment admitting the duplication — *"Any future edit to either rule must change both"* — with nothing enforcing it. `common.requires_review` is consumed only by `overnight/outcome_router.py` (`:1084`, `:1405`), which fans out to the recovery and repair merge gates.

`dashboard/data.py:1519` and `overnight/report.py:800` also test `tier == "complex"`, but for analytics bucketing — not the predicate.

**Adjacent axis consumers no route may ignore:**
- `pipeline/dispatch.py:177-190` — `_EFFORT_MATRIX[(complexity, criticality)]`, a 3×4 grid setting agent reasoning effort.
- `skills/research/references/fanout.md:5-11` — the 3×4 research fan-out matrix (1–6 agents).
- `overnight/runner.py:3452` — circuit breaker pauses only `critical`.

The criticality vocabulary is **redeclared eight times** with no shared import (`refine.py:43,72`, `discovery.py:1000`, `lifecycle_event.py:255`, `pipeline/dispatch.py:203`, `transition_table.py:130`, `advance_lifecycle.py:111`; `common.CRITICALITY_VOCABULARY:836` is imported nowhere).

### `transition_table.py` guards are advisory

`transition_table.py:385,409,465,482` are prose strings inside `Guard(precondition=…)`. `describe.py:105,182,194` reads them as opaque display text — no parsing, no evaluation. `tests/test_transition_table_describe_parity.py` diffs the table against the *generated doc*, never against the executable code.

**Consequence:** a predicate change that leaves the guard prose stale passes CI silently, and the published transition doc becomes wrong with nothing to catch it.

### Test coverage is weaker than it looks

- `common.requires_review` has **zero direct unit tests** and is patched **38 times** in `overnight/tests/test_outcome_router.py`. That suite validates routing *given* a result, never the predicate's logic.
- `advance_lifecycle.py:265`'s inline copy has no direct test of its criticality branch.
- Predicate-pinning tests that do exist: `test_spec_approve.py:101,125`, `test_implement_transition.py:146,188`, `test_next_verb.py:119`.

### Ratchet headroom: zero everywhere a route would touch

| Directory | Pin | Measured | Headroom |
|---|---|---|---|
| `skills/refine/references/` | 20568 | 20568 | **0** |
| `skills/build/references/` | 57964 | 57964 | **0** |
| `skills/research/references/` | 1914 | 1914 | **0** |

`skills/build/references/size-pin.txt` already carries a `# raised:` exception from **lifecycle-id 449** — raised for this exact criticality/tier prose reconciliation.

### Mirror tax

All prose surfaces live under `skills/`, mirrored into `plugins/cortex-core/` by `.githooks/pre-commit` Phase 3 from staged blobs. Zero manual work; every commit carries doubled paths. `c6528012` is the precedent: a 4-file prose edit landed as a 10-file diff.

---

## Measurement & Evidence

Independent re-reduction over `cortex/lifecycle/**/events.log`, applying **both** `complexity_override` and `criticality_override` chronologically to obtain final values.

### A defect in the prior measurement

`criticality_override` is a **first-class event type**, not a rare schema variant: **92 rows in wild-light, 87 in cortex-command**, 88/89 using the ordinary `from`/`to` string schema (independently verified). The reduction behind `nearly-all-work-is-rated-complex/research.md` missed essentially all of them — which is why its "criticality alone" bucket read `1/211`. Many lifecycles it classified "tier alone" are actually "both" once criticality escalations are joined.

### Corrected numbers

| Corpus | tier alone | crit alone (strict) | both | neither | **Criticality determines the road** |
|---|---|---|---|---|---|
| wild-light (n=221) | 78 (35.3%) | 2 (0.9%) | 104 (47.1%) | 37 (16.7%) | **48.0%** (CI ≈ 41–55%) |
| cortex-command (n=171) | 25 (14.6%) | 7 (4.1%) | 122 (71.3%) | 17 (9.9%) | **75.4%** (CI ≈ 69–82%) |
| gaggimate (n=13) | 6 | 0 | 4 | 3 | 30.8% — n too small |
| Team-Builder-Bot (n=2) | — | — | — | — | too small |
| hall-dental | — | — | — | — | no lifecycle events |

**The ticket's label is wrong and its numbers were low.** "Criticality alone" in the strict sense (high/critical *with tier below complex*) is ~1–4%, never 43%. The 43%/69% figures are the **union** quantity — criticality is high/critical *independent of* tier — and corrected they are **48.0%/75.4%**. The ticket understated its own case.

### Marginal relief per axis — the quantity the routes actually turn on

**This supersedes the ceiling as the decision number.** The 48.0%/75.4% figure is `P(criticality ∈ {high, critical})` — the correct bound on **tier-axis** relief (what survives perfect re-tiering). It is the wrong number for choosing among criticality-axis routes, which deliver only the **criticality-only** cell: long road because of criticality *and not also* because of tier.

Reduced per lifecycle over every `events.log` including `archive/`, applying both override types (orchestrator-verified):

| Corpus | n | long road | both | **criticality-only** | tier-only |
|---|---|---|---|---|---|
| cortex-command | 337 | 282 (83.7%) | 229 | **17 (5.0%)** | 36 (10.7%) |
| wild-light | 311 | 234 (75.2%) | 123 | **8 (2.6%)** | 103 (33.1%) |

| Change | cortex-command | wild-light |
|---|---|---|
| Drop the criticality clause entirely | frees 17 (**5.0%**) | frees 8 (**2.6%**) |
| Drop the tier clause entirely | frees 36 (10.7%) | frees 103 (**33.1%**) |

**`tier == complex` is the dominant clause in both repos**, and on the representative corpus it is worth 12.7× criticality. The maximal criticality route — deleting the clause outright, which the ticket calls *"the only route that beats the ceiling"* — moves 17 and 8 lifecycles. It beats the ceiling only *conditionally on the tier axis also moving*, which is the dependency the ticket was written to escape.

### The Plan-skip arm has never executed

`phase_transition` pairs across both repos, all eras, including `archive/` (orchestrator-verified):

| Edge | cortex-command | wild-light |
|---|---|---|
| `specify → plan` | 184 | 131 |
| **`specify → implement`** (the short road) | **0** | **0** |
| `implement → review` | 258 | 211 |
| `implement → complete` (Review skip) | 21 | 42 |

The ticket treats "the short road (Plan + Review)" as one thing. **The two halves have entirely different realized behavior**: the Review-skip arm fires; the Plan-skip arm has fired zero times in ~650 lifecycle logs. Half the modelled benefit has never been delivered by the system as built.

### The success metric now has a baseline

The ticket mandates "which phases actually ran" but supplied `181/211 = 85.8%`, which is predicate *eligibility*. Measured from phase-completion events:

| Corpus | Plan actually ran | **Review actually ran** | Predicate eligibility |
|---|---|---|---|
| wild-light | 191/222 = 86.0% | **167/222 = 75.2%** | 83.3% |
| cortex-command | 158/171 = 92.4% | **149/171 = 87.1%** | 90.1% |

**Use 75.2% / 87.1% as the baseline.** Review runs below eligibility because some eligible lifecycles are abandoned or paused.

### `c6528012` is effectively unmeasured

Two days elapsed; **4 completed lifecycles**, all escalated to `high`.

- The **"Review is skipped at medium criticality"** branch has fired **n = 0 times**.
- The depth split fired correctly exactly **once** — `open-critical-review-agent-count` (moderate/high), Stage 2 skipped, single review cycle.

Route 1 cannot be harvested yet. There is nothing there to measure.

### Era-mixing does not affect the ceiling — confirmed, not assumed

The ceiling reads only `criticality ∈ {high, critical}`; it never consults the tier vocabulary, because it is computed under maximally-favorable re-tiering. Re-running restricted to post-split lifecycles gives the same qualitative split. `research.md:110`'s era-mixing objection lands on #451's tier claims, not on this bound.

### Criticality justification sample (n=27, stratified, `random.seed(452)`)

Sampling frame: all features with final criticality ∈ {high, critical} (wild-light 109, cortex-command 130); 15 and 12 drawn respectively.

| Bucket | cortex-command (n=12) | wild-light (n=15) |
|---|---|---|
| **A** — agentic-layer catch-all clause | **11 (91.7%)** CI 65–98% | 1 (6.7%) |
| **B** — hard to reverse | 0 | 0 |
| **C** — blast radius, reversible | 1 | 1 |
| **D** — **no justification recorded** | 0 | **13 (86.7%)** CI 62–96% |

**The two corpora fail for opposite reasons.** This is the single most decision-relevant finding in the research.

- **cortex-command**: `high` is a categorical default firing on file path alone. Representative: *"Skill/hook changes are shared-infrastructure (criticality default `high`)"*. A rubric reword would move real volume here.
- **wild-light**: 13 of 15 `high` calls have **no persisted reasoning anywhere** — not `research.md`, not `spec.md`, not the backlog `## Why`, not `events.log`. `clarify_critic` stores only counts, never finding text. Representative: `research.md`'s entire criticality content is the parenthetical *"(tier=complex, criticality=high)"*.
- **Bucket B never appeared once.** "Hard to reverse" is one of the rubric's two explicit `high` triggers and was never the stated reason in 27 sampled lifecycles.

**Implication:** in the representative corpus, criticality is *asserted, not reasoned*. A rubric reword there is unfalsifiable — there is no recorded judgment to compare against.

### Limits

- n = 12/15 on the justification sample; proportions, not precise counts.
- Whether wild-light's 13 D-cases would have sorted into B or C had they been recorded is **unknowable from the artifact trail**.
- The exact n reconciliation (222/171 here vs 211/164 in prior research) is unresolved; malformed-line count matches exactly (31), so file scope is identical — likely a differing run-dedup rule. Flagged rather than guessed.
- gaggimate and Team-Builder-Bot are too small to pool.

---

## Requirements & Constraints

### There is no written amendment procedure — only practice

`git log -p --follow cortex/requirements/project.md`: every change to an Architectural Constraints bullet rode inside a ticket-implementing commit. Two observed mechanisms:

1. **Review-phase auto-apply drift** (`skills/build/references/review.md:17-43`) — e.g. `e0fef8a2`, `e91fa492`.
2. **Direct edit inside the feature commit**, narrated in the body — e.g. `983c98ae`, `57efb93c` (#399), `e3aef4e5` (#407).

**`project.md:40` "The short road" carries no ADR back-pointer and no ticket number.** It was added in `983c98ae` justified only by commit narrative. Nothing in `cortex/adr/README.md` or `docs/policies.md` governs amending `project.md` (grep: zero hits).

**Route 4 should land the way every precedent bullet did** — inside #452's own build, not as a separate governance change.

### ADR-0024 makes route 4 a wheel release

The predicate is wheel Python, and changing it is **edge selection**, squarely inside ADR-0024's served-verb bound (`0024:23`: config *"can never introduce a state or edge"*). Per `0024:25`, *"a gate-matrix change requires a wheel release to take effect, and a skewed plugin↔wheel pair can disagree."*

`docs/rollforward-exit.md` covers the served-loop **mechanism**, not a predicate-**value** revert. Undoing a bad predicate needs another wheel release — ADR-0025 forfeited the cheap prose-side revert.

### No minimum review-coverage floor exists

`project.md:38` (critical-review at spec only), `:39` (agent bounds), `:40` (the short road). None sets a floor. The only floors are `spec_approve.py`'s hardcoded rule and `clarify.md:34`'s "appropriate default for most agentic-layer changes."

### The evidence bar

`project.md:41`'s named-evidence requirement is scoped to *pre-commit/CI gates* — its body is entirely about them. It does **not** reach lifecycle phases. `project.md:23`'s general deletion-bias bar does apply, and `project.md:21`'s presumption targets machinery that *"police[s] or observe[s] the harness itself"* while explicitly protecting *"state machine, events.log, fan-out dispatch"*. Plan/Review sit closer to the protected set than the presumed-deletable one — a genuine gap, resolving neither for nor against.

### Token-economy benefit, as stated

`project.md:37`: session carry is superlinear (37–61% of orchestrator spend); a fresh session re-caches for ~50k tokens (~0.7%). **So the saving from cutting a phase is not the avoided re-cache — it is the phase's own turns**, given `cache_read ∝ requests^1.68`. No per-phase turn count exists in `project.md`; `:114`'s known-bad-numbers note disqualifies reusing the #390/#391 figures.

### Consumer scope

`clarify.md` ships to every consumer repo on next plugin update. `ADR-0002` is a compatibility contract, not a behavior-change gate; release-type markers only drive semver. **No requirement gates a consumer-visible rubric change** — routes 2/3 get no extra procedural weight despite changing classification behavior everywhere.

### Area docs

Confirmed no area doc matches `[lifecycle, tiering, ceremony, criticality]`; only `project.md` + `glossary.md` load. `glossary.md` defines only *scene* and *cockpit* — **no entry for tier, criticality, short road, or ceremony.**

---

## Web & Prior Art

- **Cox (2008), *Risk Analysis*** (peer-reviewed): risk matrices correctly order **<10%** of hazard pairs; under negatively-correlated frequency/severity they can be *"worse than useless."*
- **DORA / Accelerate** (large-N survey): formal change-approval boards show **no** change-failure-rate benefit, and correlate with **2.6× likelihood of being a low performer**. Recommended fix: narrow what routes to heavy process; use peer review plus automation. Strongest empirical result found, and directly on point — the long road is CAB-shaped and triggered too broadly.
- **Severity-inflation / alarm-fatigue literature**: once a band holds a majority of items it has stopped discriminating. A band pinning 48–75% *is* that diagnostic signature.
- **Meta RADAR** (arXiv:2605.30208): separates *eligibility* from a continuous multi-signal risk score, so no single signal saturates the gate. Reported at scale: revert rate ⅓ of baseline, incidents 1/50, review time −35%. ⚠️ **The summary is an approximate paraphrase from an automated fetch, not verified quotes — verify before Spec relies on it.**
- **Reversibility as its own axis** (Bezos one-way/two-way doors; practitioner sources, opinion-level but near-unanimous): keep reversibility separate from consequence, because it changes the *shape* of the right mitigation, not just its weight.

**Convergent recommendation:** `high` OR-bundles three distinct things — *"significant"* (consequence), *"hard to reverse"* (reversibility), *"any change to shared skills / workflow infrastructure"* (exposure). Any one suffices, so the band's trigger surface is the union and dominates whatever the other axis does. Prior art says **unbundle**, don't re-tune.

⚠️ The loosening→harm direction surfaced **only anecdotal sources**; correctly not cited as evidence. Asymmetric evidence base — note when arguing either direction.

---

## Adversarial

The dispatched agent returned after two chases. Its findings are below; the orchestrator independently verified the three load-bearing ones (marginal-relief cells, the dead `specify → implement` arm, the catch-rate split).

### Strongest objection: the decision rested on the wrong quantity

See **Marginal relief per axis** above. Criticality-axis routes deliver 5.0%/2.6%, not 48%/75.4%. Independently reproduced.

### `b854bbf3` is `c6528012`'s revert, 30 minutes later — not an independent data point

- `c6528012` at 10:50:24 — body: *"critical-review **narrows** to complex plus high/critical."*
- `b854bbf3` at 11:20:57 — *"**Restore** critical-review at complex/medium; the narrowing was underfounded."*

The ticket's Edges present them as two separate lessons — one a harvest candidate, one a cautionary tale. They are one commit and its rollback. **Route 1 proposes harvesting a commit whose most aggressive clause was already reverted for resting on n=1.**

### Route 1's stated premise is false in code

*"Criticality decides whether Review runs; tier decides how deep"* is `skills/build/SKILL.md:80` — and it **contradicts its own gate table four lines above** (`:75-76`, low/medium → *"tier-based (skip below complex)"*) and the code (`implement_transition.py:175` routes `complex`+`medium` to Review). `c6528012` was authored to fix a prose/code disagreement and shipped the mirror-image one. **A live defect, worth filing regardless of #452's outcome.** What survives to harvest is only "Stage 2 is complex-only" — a depth reduction inside a phase that still runs.

### The real mechanism is an upward-only ratchet no route touches

| Corpus | `simple → complex` | `simple → moderate` | any downward |
|---|---|---|---|
| cortex-command (148) | 141 (95%) | 2 | 3 |
| wild-light (183) | 178 (97%) | 3 | **0** |

Seed is `simple`/`medium`; assessment jumps straight to `complex`/`high` and essentially never returns. Retuning bands or the predicate leaves this untouched — the same step re-escalates into whatever bands exist.

### Review earns its cost

| Corpus | APPROVED | CHANGES_REQUESTED | catch rate |
|---|---|---|---|
| cortex-command | 275 | 19 | **6.5%** |
| wild-light | 215 | 40 (+1 ERROR) | **15.7%** |

Corroborated by `review → implement-rework` (12/29) and the in-implement `orchestrator_review` gate (74/352 = 21.0% cortex-command). Orchestrator's own per-class reduction: `complex/high` 16.0% (17/106) vs `complex/medium` 12.8% (10/78) — **criticality does not predict catch rate.** Caveat: CHANGES_REQUESTED ≠ a defect that would have caused harm; sampling the 59 non-approve verdicts would price it.

**The DORA citation does not transfer** — it measured human approval boards external to the delivery team, not an inline automated reviewer with a 6–16% return rate.

### Five copies already disagree

Verified divergent defaults: `spec_approve.py:126` defaults tier to `"simple"`; `implement_transition.py:99` and `advance_lifecycle.py:254` to `"moderate"`. Benign today; latent the moment anyone adds a band or converts `== "complex"` to a rank test. Consolidation is safe **only because it is a provable no-op today** — all five reduce to the same boolean on the current vocabulary, so the refactor is diff-verifiable. That stops being true after any route lands, so it must ship as a standalone no-op, never bundled.

### Post-fork sample is 12 lifecycles

Phase-transition rows since the fork (`983c98ae`, 2026-07-18): 38 in cortex-command (~12 lifecycles) — 3 spec exits, all `→ plan`; 12 implement exits, all `→ review`. Wild-light: 42 implement exits, all `→ review`. **Combined post-fork short-road exits: 0 of 54.** Every confidence interval in this document describes a corpus where the middle tier did not exist.

### Route the agent would refuse to ship

**Route 4**, unconditionally on today's evidence: a wheel release inside an ADR-0024 bound, no revert path for a predicate value, five unsynchronized implementations with divergent defaults, no direct tests on the shared one, guard prose CI cannot check, zero ratchet headroom — to relieve 17 and 8 lifecycles.

### Where the repos actually diverge

On **tier**, not criticality: wild-light's tier-only cell is 33.1% vs cortex-command's 10.7%. Criticality behaves similarly in both. This argues for per-repo **tier** configuration (`cortex/lifecycle.config.md` already overrides complexity defaults) and against a global predicate edit.

### The Plan-skip claim, refuted

The measurement angle inferred *"Plan runs on both roads"* from an 86–92% run rate. **This is wrong.** `spec.approved-direct` has `to_state="implement"` (`transition_table.py:404`) and `_resolve_route` returns `"implement"` (`spec_approve.py:155`). The short road genuinely skips Plan. The 86–92% figure sits within noise of long-road eligibility (83.3%/90.1%) — exactly what you expect if Plan runs *only* on the long road. **The ticket's benefit model stands.**

### Review earns its cost — the strongest objection to the ticket

Measured directly from wild-light `events.log`:

| Signal | Count | Rate |
|---|---|---|
| `review_verdict: CHANGES_REQUESTED` | 30 / 194 | **15.5%** |
| `review_verdict: APPROVED` | 163 / 194 | 84.0% |
| Rework cycles actually run (cycle ≥ 2) | 29 | — |
| `requirements_drift: detected` | 77 / 185 | **41.6%** |

Every other number in this research measures *how much* ceremony runs. This measures **what it catches**. A phase returning CHANGES_REQUESTED 15.5% of the time and detecting requirements drift 41.6% of the time is not an idle control.

**This is precisely the argument `b854bbf3` lacked.** That commit cut gate eligibility for 35% of the corpus on n=1 and was reverted 30 minutes later. Any route reducing Review coverage must argue against the 15.5% catch rate — and must say what happens to the defects currently caught.

### Revert risk, ranked

1. **Route 2 (widen `medium`)** — highest. It moves work out of Review wholesale, was already rejected in `c6528012`'s own commit body, and is the closest structural analog to `b854bbf3`. Trigger: the first defect that ships through newly-admitted-medium work.
2. **Route 4 (decouple)** — high blast radius, but reverting costs a wheel release rather than a prose revert, so it fails *slowly and expensively* rather than fast.
3. **Route 3 (unbundle)** — moderate. Adds a band rather than widening one, so coverage loss is bounded by the new band's population.
4. **Route 1 (harvest)** — cannot be reverted because it changes nothing. It also cannot be executed yet (n=0).

### The self-referential trap

This ticket is `complex`/`high` and takes the long road. Its own `high` is bucket A — it edits shared skill prose. It is therefore a live instance of the phenomenon it describes: the catch-all clause, not a risk judgment, set its criticality.

### Unresolved adversarial surface

Not covered, because the agent did not return: whether "consolidate the five predicate copies first" adds more blast radius than it removes; whether one rubric can serve two repos that differ 48% vs 75.4%; independent verification of the numbers above.

---

## Open Questions

0. **Should this ticket ship a criticality-axis change at all?** *Resolved — no, on the evidence.* Marginal relief is 5.0%/2.6%; the tier clause is worth 12.7× more on the representative corpus; the Plan-skip half of the benefit has never fired; and Review has a 6.5–15.7% catch rate the change would reduce. The ticket's Role asked whether relief should come from the criticality axis. **The answer the research produces is no.** What remains buildable is named in OQ8.

1. **Can one rubric serve both corpora, given they fail for opposite reasons?** cortex-command is 92% bucket-A (catch-all clause); wild-light is 87% bucket-D (nothing recorded). *Resolved as moot by OQ0* — but note the repos diverge on **tier**, not criticality, which points at per-repo tier configuration rather than a global rubric edit.

2. **Should criticality reasoning be persisted before any rubric change?** 13/15 wild-light `high` calls record no justification. Without it, no rubric change can be evaluated in the corpus that matters. *Open — this may be the true prerequisite, and it is not one of the ticket's four routes.*

3. **Must the five predicate copies be consolidated before the predicate is changed?** Routes 3 and 4 otherwise require five synchronized edits with no test that fails on a missed one (`requires_review` is patched 38×; `advance_lifecycle.py:265`'s copy is untested). *Open — a fifth route the ticket does not list.* Adversarial review of it did not return.

4. **What is the defensible floor for Review coverage?** No requirement sets one, and Review has a measured 15.5% catch rate. *Open — Spec must state the floor it is willing to defend before choosing any coverage-reducing route.*

5. **Is `c6528012` harvestable at all on this timescale?** n=4, and its key branch has fired zero times. *Deferred — re-measure when the post-split population reaches n≥30, per the same reasoning `research.md:118` applied to its own n=8. No action is justifiable on n=4 either way.*

6. **Does the un-complexity-selected complex rate still gate this work?** `nearly-all-work-is-rated-complex/research.md:117` OQ1 says it "should gate any further tier work." *Resolved — does not gate.* That question governs the **tier** axis; this ticket's thesis is that the tier axis is capped and asks about criticality. The 48%/75.4% ceiling is computed under maximally-favorable re-tiering, so it holds regardless of the true complex rate.

7. **Does Meta RADAR say what the web angle reports?** The summary is a flagged automated paraphrase, not verified quotes. *Open — verify before Spec cites it. Low cost: one fetch.*

---

## Epic Reference

None — `cortex-load-parent-epic 452` returned `no_parent`.
