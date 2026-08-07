# Specification: criticality-pins-the-corpus-to-the

> **Epic reference:** none — `cortex-load-parent-epic 452` returned `no_parent`.
> Research: `cortex/lifecycle/criticality-pins-the-corpus-to-the/research.md`.

## Problem Statement

Ticket #452 asked whether lifecycle ceremony relief should come from the criticality axis, on the premise that the tier axis is capped; research answered no, and the people who benefit are everyone running lifecycles here and in consumer repos, who would otherwise have absorbed a consumer-wide rubric change that buys almost nothing. Measured marginal relief from dropping the criticality clause entirely is **5.0%** (cortex-command, 17/337) and **2.6%** (wild-light, 8/311), while dropping the tier clause frees 10.7% and **33.1%** — so on the representative corpus the axis this ticket dismissed is worth 12.7× the one it proposed; the Plan-skip half of the modelled benefit has never executed (`specify → implement` is 0 across ~650 lifecycle logs); and Review, which the relief would reduce, returns CHANGES_REQUESTED at 6.5–15.7% with criticality failing to predict it (`complex/high` 16.0% vs `complex/medium` 12.8%). The decision is therefore negative and worth recording so it is not re-litigated a third time after #449 and this ticket, and one durable gap remains behind it: **87% of `high` calls in the representative corpus carry no recorded justification anywhere** — not in `research.md`, `spec.md`, the backlog `## Why`, or `events.log` — so the axis cannot be audited by anyone who revisits it.

## Phases

- **Phase 1: Record the decision** — capture the negative answer and its evidence where the next person to ask will find it.
- **Phase 2: Persist the criticality reason** — carry Clarify's already-computed justification into the reconcile gate that writes most overrides, tagged by clause, so the axis becomes auditable.

## Requirements

1. **An ADR records the decision and its evidence.** `cortex/adr/0035-ceremony-relief-is-not-taken-on-the-criticality-axis.md` states that ceremony relief will not be taken on the criticality axis, with the marginal-relief measurement as its evidence. Acceptance: that file exists and contains the strings `5.0%`, `2.6%`, `33.1%`, `24.7%`, and `9.4%`; **and** `bin/cortex-adr-citation-audit | python3 -c "import json,sys; assert not [f for f in json.load(sys.stdin)['findings'] if f['kind']=='duplicate_number']"` exits zero. The bare audit is **report-only and exits 0 on every path** (`justfile:470`), so "the audit passes" is not a check — the `duplicate_number` assertion is. It is also the only finding kind that *can* fire here: `unresolved` cannot (R1 creates the file) and `slug_mismatch` cannot (R2 cites the bare `ADR-NNNN` prefix, which carries no slug). **0035 is free as of 2026-08-06** — 0030 through 0034 are taken — but the number is a race against any concurrent lifecycle, which is why the assertion beats the note. **Phase**: Record the decision

2. **The short-road constraint gains the ADR back-pointer it never had.** `cortex/requirements/project.md:40` ("The short road") currently carries no ADR reference and no ticket number. Acceptance: `grep -c 'ADR-0035' cortex/requirements/project.md` returns ≥1, and the matching line also contains `The short road`. A bare `grep 'ADR-00'` is **not** a valid check — it already returns 8 matches on the unmodified file (`→ ADR-0001` at `:35`, `→ ADR-0003` at `:36`, among others), so it would pass without the edit. **Phase**: Record the decision

3. **The ticket records the negative answer rather than closing silently.** Acceptance: `cortex/backlog/452-*.md` contains a section stating the decision and linking `cortex/lifecycle/criticality-pins-the-corpus-to-the/research.md`. **Phase**: Record the decision

4. **`reconcile-clarify` accepts and persists an override reason.** `cortex-refine reconcile-clarify` gains optional `--criticality-reason` and `--tier-reason`; when supplied, the emitted `criticality_override` / `complexity_override` rows carry a `reason` key. Acceptance: run `cortex-refine reconcile-clarify` on a fixture lifecycle with `--criticality-reason "exposure: shared skill prose"`; the appended `criticality_override` row in `events.log` contains `"reason": "exposure: shared skill prose"`. Grounding: `cortex_command/refine.py:357-371` (emission site), `cortex_command/lifecycle_event.py:310-325` (the existing `--reason` contract to match). **Phase**: Persist the criticality reason

5. **The flags are optional and omission is byte-identical to today.** Acceptance: `cortex-refine reconcile-clarify` invoked without either flag emits rows containing no `reason` key, and the existing reconcile tests pass unmodified. Rationale is already ruled on at `cortex_command/lifecycle_event.py:307-309` — *"a mandatory flag invites a filler string, which is worse than an absent one because it reads as evidence."* **Phase**: Persist the criticality reason

6. **A clause tag from a closed set is validated when present.** The reason may be prefixed `reversibility:`, `exposure:`, `consequence:`, or `other:`. Supplying a prefix outside that set exits non-zero with the offending value on stderr and appends no row; supplying no prefix is accepted and recorded verbatim. Acceptance: `--criticality-reason "bogus: x"` exits non-zero and leaves `events.log` unchanged; `--criticality-reason "plain text"` succeeds. **Phase**: Persist the criticality reason

7. **The refine skill supplies the reason from Clarify's §5.3 output.** `skills/refine/SKILL.md` Step 4's `reconcile-clarify` invocation passes the criticality reasoning Clarify already states, tagged per R6. No new assessment work — the reasoning exists in-session and is currently discarded at the write. Acceptance: `Interactive/session-dependent: the reason is model-generated per lifecycle and cannot be pinned by a fixture.` Grounding: `skills/refine/references/clarify.md:34` (§5.3 already requires "brief reasoning"). **Phase**: Persist the criticality reason

8. **The clause distribution is greppable without new tooling.** Acceptance: the following returns per-clause counts for `criticality_override` rows only, across the whole corpus:

    ```
    find cortex/lifecycle -name events.log -exec cat {} + | python3 -c "import sys,json,collections; c=collections.Counter(); [c.update([r['reason'].split(':')[0]]) for l in sys.stdin for r in [json.loads(l)] if r.get('event')=='criticality_override' and r.get('reason')]; print(c)" 2>/dev/null
    ```

    A bare `grep … cortex/lifecycle/*/events.log` is **not** valid on two counts: the glob matches 188 of 353 `events.log` files, missing all of `archive/` — while the research's own reduction covered `archive/` — and `reason` already appears on **16 event types** (92 rows on `sentinel_absence`), with R4's `--tier-reason` writing the same key onto `complexity_override`, so an unscoped tally merges both axes. No measurement script, module, or CLI verb is added — `cortex/requirements/project.md:23` requires verifying with existing tools first. **Phase**: Persist the criticality reason

9. **Glossary entries exist for the terms this work turns on.** `cortex/requirements/glossary.md` gains entries for *tier*, *criticality*, and *short road*. Acceptance: each of the three appears as an entry in `cortex/requirements/glossary.md`. The glossary currently defines only *scene* and *cockpit*, so these concepts have no canonical definition anywhere. Filed under Phase 1 because it is definitional documentation alongside the ADR, with no dependency on the reason-persistence work — Phase 2 is what the ADR defers a future rubric change behind, and unrelated docs there would blur what "Phase 2 shipped" licenses. **Phase**: Record the decision

## Non-Requirements

- **No rubric change.** `skills/refine/references/clarify.md` §5.3 is not edited. Unbundling `high` into consequence / reversibility / exposure remains the structurally correct move per the prior art, but it delivers 2.6% on the representative corpus and would reduce a control with a 6.5–15.7% catch rate. It becomes arguable again only when Phase 2's data shows which clause fires — deliberately left for a successor ticket.
- **No predicate change** (the ticket's route 4). A wheel release inside ADR-0024's bound, with no revert path for a predicate value, to relieve 17 and 8 lifecycles.
- **Not harvesting `c6528012`** (route 1). Its premise is false in code — `skills/build/SKILL.md:80` contradicts its own table and `implement_transition.py:175` — and `b854bbf3` is its 30-minute revert, not an independent data point. Only 4 lifecycles have completed since; the key branch has fired zero times.
- **Not fixing `skills/build/SKILL.md:80`.** A live prose/code contradiction, found here but independent of this decision. **Filed as #462.**
- **Not consolidating the five predicate implementations.** They carry divergent tier defaults (`spec_approve.py:126` → `"simple"`; `implement_transition.py:99`, `advance_lifecycle.py:254` → `"moderate"`), and `common.requires_review` has no direct test while being patched 38× in the only suite exercising it. Safe to consolidate **only** as a standalone provable no-op, never bundled with a behavior change. **Filed as #463.**
- **Not investigating the dead `specify → implement` arm.** Zero firings across ~650 logs is a finding, not a defect this ticket fixes.
- **Not backfilling reasons onto existing rows.** The 92 wild-light and 87 cortex-command existing `criticality_override` rows stay as they are.
- **Not building measurement tooling** (R8).
- **No reliance on Meta RADAR.** Research flagged its summary as an unverified automated paraphrase; nothing here rests on it, so no verification is owed.
- **Not adding a criticality band value.** The vocabulary is redeclared at eight sites with no shared import (`refine.py:43,72`, `discovery.py:1000`, `lifecycle_event.py:255`, `pipeline/dispatch.py:203`, `transition_table.py:130`, `advance_lifecycle.py:111`); a new value needs all eight edited with nothing to catch a miss. No requirement here adds one.

## Edge Cases

- **A ticket already carrying `criticality: high` is seeded high, so the ratchet never fires and there is no row to attach a reason to.** `reconcile-clarify` appends only when the desired rank exceeds the current one, so a lifecycle whose backlog frontmatter already says `high` produces no override row at all — and that `high` call stays unexplained, which is precisely the condition Phase 2 exists to close. **Measured bound: 10.5% (cortex-command, 4/38) and 16.7% (wild-light, 10/60) of modern-era (`lifecycle_start` ≥ 2026-07-01) final-`high` lifecycles are unreachable this way.** Expected: silent, matching today's suppression behavior. Accepted as a known blind spot rather than fixed here — closing it means recording a reason at `lifecycle_start`, a wider change than this ticket carries. A successor reading the clause distribution must subtract this population, not assume it absent.
- **Both axes ratchet in one call**: each row carries its own reason; passing one flag records that one and leaves the other row without a `reason` key.
- **A reason whose body contains a colon** (`exposure: consumed by overnight/: runner`): the tag is the prefix before the *first* colon; the remainder is recorded verbatim.
- **Pre-existing rows without `reason`**: readers tolerate their absence permanently, consistent with the events-log compatibility rule that readers tolerate every prior shape forever.
- **A consumer repo on an older wheel** receives updated skill prose (R7) but not the verb flags (R4). Expected: the unknown flag is rejected and the reconcile fails loudly rather than silently dropping the reason — a version-skew error surfaced to the operator, consistent with ADR-0024's accepted plugin↔wheel coupling cost.
- **The clause tag is supplied but wrong** (an author tags `exposure:` where the real driver was reversibility): undetectable by construction. Accepted — the tag improves auditability over nothing, and R5's optionality keeps it from becoming compulsory filler.
- **Partial fill is the expected outcome, not a failure.** Measured on the existing manual-override path, where `--reason` already exists, reasons appear on **22–63%** of rows (cortex-command 6/21 criticality, wild-light 10/16); on the `clarify_reconcile` path, where no flag exists, **0 of 149** rows carry one. So R4 supplies a destination that is currently absent, and success is a non-zero clause distribution — not complete coverage. A successor ticket reading this data must treat it as a sample, not a census.

## Changes to Existing Behavior

- **ADDED** — an ADR under `cortex/adr/` (R1).
- **MODIFIED** — `cortex/requirements/project.md:40` gains an ADR back-pointer (R2).
- **MODIFIED** — `cortex/backlog/452-*.md` records the negative answer (R3).
- **MODIFIED** — `cortex_command/refine.py` `reconcile-clarify`: two optional flags; emitted rows gain an optional `reason` key. Additive; omission byte-identical (R5).
- **MODIFIED** — `skills/refine/SKILL.md` Step 4 carries the reason. Mirrored into `plugins/cortex-core/` by `.githooks/pre-commit` Phase 3.
- **ADDED** — three `cortex/requirements/glossary.md` entries (R9).

## Technical Constraints

- `--reason` already exists on the manual override verbs (`lifecycle_event.py:313,323`); R4 matches that contract rather than inventing a second shape.
- The reason must stay optional (`lifecycle_event.py:307-309`).
- `skills/refine/references/` sits at exactly zero ratchet headroom (20568/20568); any prose growth needs an annotated `# raised:` exception carrying this lifecycle's id. R7 edits `SKILL.md`, which is not reference-dir-pinned, but any spillover into `references/` is pinned.
- `project.md` has no written amendment procedure; every historical amendment rode inside the implementing ticket's commit, which is how R2 should land.
- `transition_table.py:385,409,465,482` are advisory prose that nothing parses; tests check table↔doc parity only, never table↔code. No requirement here changes the predicate, so no guard prose needs updating.
- `clarify_critic` events record counts only, never finding text — so the critic path is not an alternative home for the reason.
- **Input limitation:** the research's adversarial angle returned only after two chases, and its three highest-value questions were independently verified by the orchestrator. Two adversarial questions went uncovered — whether consolidating the five predicate copies adds more blast radius than it removes, and whether one rubric can serve two corpora differing 10.7% vs 33.1% on the tier cell. Both fall in Non-Requirements here.

## Open Decisions

None.

## Proposed ADR

### Proposed ADR: 0035-ceremony-relief-is-not-taken-on-the-criticality-axis

**Context.** The short-road predicate is `criticality ∈ {high, critical} OR tier == complex` (`project.md:40`, which carries no ADR back-pointer and no ticket number). #449 and #452 both asked whether relief should come from the criticality axis. Measured marginal relief from dropping the criticality clause is 5.0% (cortex-command, 17/337) and 2.6% (wild-light, 8/311); dropping the tier clause frees 10.7% and 33.1%. The Plan-skip arm has never executed in ~650 lifecycle logs. Review returns CHANGES_REQUESTED at 6.5–15.7%, and criticality does not predict it (16.0% vs 12.8%). A prior narrowing on this axis was reverted 30 minutes after shipping.

**Decision.** Ceremony relief is not taken on the criticality axis **while `tier == complex` remains the dominant clause**. A future rubric or predicate change on that axis requires recorded per-clause justification data plus a measured CHANGES_REQUESTED rate for the affected class, stated against the corpus baseline. Classification outcomes are recorded with the clause that produced them so the axis stays auditable.

**Scope and re-open trigger.** This decision is conditional on the measured tier distribution, not permanent. The 5.0%/2.6% marginal figures hold the tier distribution fixed at today's values, where the large majority of lifecycles are `tier == complex`. Among lifecycles that are *not* `tier == complex`, criticality still pins **24.7%** (cortex-command) and **9.4%** (wild-light). **So if the tier axis is ever corrected — the change worth 33.1% on the representative corpus — criticality becomes the binding clause and this decision must be revisited.** Re-open when the `tier == complex` share falls materially, or when the criticality-only cell exceeds 10% of lifecycles in the representative corpus.

**Trade-off.** This forecloses relief on argument alone and defers it by at least one ticket. It is accepted because the axis has produced one same-day revert already, because a reduction in Review coverage is not observable after the fact — the counterfactual defect is never seen — and because 87% of `high` calls in the representative corpus currently carry no recorded reasoning, making any rubric change there unfalsifiable. The cost is that the structural defect the prior art identifies (that `high` OR-bundles consequence, reversibility, and exposure) stays unfixed until the data exists to fix it against — and, per the scope clause, that this decision must be actively re-checked rather than treated as settled.
