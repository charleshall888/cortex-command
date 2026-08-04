# Specification: nearly-all-work-is-rated-complex

## Problem Statement

Every mechanism that in practice moves a lifecycle's tier moves it up. `clarify-critic` carries a textually neutral licence to challenge a tier rating ("optionally complexity/criticality calibration if that rating looks poorly supported"), but it sits as an optional afterthought behind three mandatory dimensions, inside a prompt that says "Return objections only" and "One-sided: focus on what's wrong" — framing that makes understatement easy to evidence and overstatement a negative to prove. Whether that clause is dead or merely smothered is **unfalsifiable from the record**: `clarify_critic` events store counts only, never per-dimension detail, so no artifact anywhere shows it firing or failing to fire; `complexity_escalator` returns early when the tier is already `complex`, so it only ever suggests raising; `reconcile-clarify` appends only when the desired value outranks the current one. Nothing anywhere argues a tier *down*. `complexity-override` can lower one, but it is a verb an assessor must choose deliberately — nothing prompts or suggests it. The result is an assessment process with a ratchet and no release, which benefits nobody: work that deserves the short road cannot get onto it, and the tier stops being a judgment about the work.

The fix is not to make the adversarial reviewer balanced — it is correctly one-sided, and forcing symmetry on it invites filler findings. The fix is to stop asking it to opine on tier at all, and to make the orchestrator that *already owns* the tier decision reconcile it explicitly in both directions.

## Phases

- **Phase 1: Remove tier calibration from the critic** — take the judgment away from the one-sided reviewer. The capability is **relocated, not removed**: Phase 2 gives it to the agent that already owns the decision.
- **Phase 2: Make §5's tier decision an explicit two-directional reconciliation** — the orchestrator states whether its judgment moved after the critic, and which way.

## Requirements

1. **`clarify-critic` no longer solicits tier or criticality calibration.** Its remit narrows to the three confidence dimensions it is actually built for. The deleted clause ("optionally complexity/criticality calibration if that rating looks poorly supported") is directionally neutral and nominally licensed a downward challenge, so **Phase 1 must not ship without Phase 2** — alone it would remove the only such licence and invert this spec's goal. Acceptance: `grep -c 'complexity/criticality calibration' skills/refine/references/clarify-critic.md` returns `0`, and the file's Instructions section names only intent clarity, scope boundedness, and requirements alignment. **Phase**: Remove tier calibration from the critic

2. **The critic's rubric-dimension count stays within its soft cap.** Removing a dimension must not be offset by adding one elsewhere. Acceptance: `grep -c 'Soft cap of 5 rubric dimensions' skills/refine/references/clarify-critic.md` returns `1`, and the Instructions paragraph enumerates exactly the three names `intent clarity`, `scope boundedness`, `requirements alignment` and no fourth. **Phase**: Remove tier calibration from the critic

3. **`clarify.md` §5 requires the orchestrator to state, when recording a tier, whether it considered the next tier down and why it was rejected.** Deliberately **independent of critic findings** — it fires on every assessment, including when the critic returned nothing, failed, or (post-Phase-1) has no remit touching tier at all. This is what makes Phase 1's deletion safe: the downward consideration is created by the assessment step itself, not inherited from a reviewer signal. It also never reads the backlog value, so it holds on the 186 of 211 tickets carrying no complexity field. Acceptance: in `skills/refine/references/clarify.md`, the §5 Complexity item requires an explicit statement about the next-lower tier, verified by the item naming the lower-tier consideration and containing no conditional tying it to critic output — `grep -c 'critic' ` over the §5 Complexity item returns `0`. **Phase**: Make §5's tier decision an explicit two-directional reconciliation

4. **Neither direction is preferred.** The prose must not instruct the orchestrator to lower tiers, prefer lower tiers, or aim at any distribution. Acceptance: `grep -ciE 'quota|target (rate|distribution|share)|aim (for|at)' skills/refine/references/clarify.md skills/refine/references/clarify-critic.md` returns `0`, and `grep -c 'When torn, take the lower tier' skills/refine/references/clarify.md` returns `1` (unchanged). **Phase**: Make §5's tier decision an explicit two-directional reconciliation

5. **No new MUST/CRITICAL/REQUIRED escalation.** `docs/policies.md` gates these behind an evidence artifact plus a demonstrated `effort=high` failure, neither of which exists here. Acceptance: `git diff` of the two files adds no MUST, CRITICAL, or REQUIRED token. **Phase**: Make §5's tier decision an explicit two-directional reconciliation

6. **The change is byte-neutral or smaller across `skills/refine/references/`.** The directory has 5 bytes of headroom against its down-only pin. Acceptance: `uv run pytest tests/test_reference_size_ratchet.py` passes with no hand-raised `# raised:` exception added. **Phase**: Make §5's tier decision an explicit two-directional reconciliation

7. **The suite stays green.** Acceptance: `uv run pytest tests/ -q` reports no new failures against the pre-change baseline of 2473 passed. **Phase**: Make §5's tier decision an explicit two-directional reconciliation

## Non-Requirements

- **Re-cutting §5.2's tier definitions.** An independent audit agreed 8/8 with the assigned tiers on the full post-split population, and the "a precedent others follow" clause is not the driver (competing designs 10, blast radius 3, precedent 2, never sole). Re-cutting an endorsed rubric to move a distribution is quota-filling.
- **Rewriting the calibration clause instead of deleting it** — making it mandatory, or instructing the critic to hunt overstatement with effort matching understatement. Rejected on three grounds: it leaves tier judgment with an agent whose prompt is one-sided by construction; a mandatory finding invites a filler string, the documented reason `#448` made `--reason` optional; and it bets on wording against an evidentiary asymmetry that wording does not remove — proving nothing-worrying-applies is harder than naming one thing that does, whatever the clause says. Recorded because a reviewer argued for it and the argument is not weak: the clause is textually neutral, and the corpus **cannot** show whether it is dead or smothered, since `clarify_critic` events store counts only.
- **Making `complexity_escalator` bidirectional.** Research argues it would be actively worse: a low open-question count is weaker evidence of easiness than a high count is of hardness — equally consistent with thin research. Left one-way deliberately.
- **Observability for suppressed downgrades in `reconcile-clarify`.** Zero downgrade overrides exist across 211 lifecycles, and the suppression can only fire on a second reconcile, which has never occurred. Fails the Deletion-bias bar.
- **A filer-supplied complexity estimate.** Split to #453; this spec's mechanism deliberately does not depend on it.
- **Relief on the criticality axis.** Split to #452. Criticality pins 43–69% of the corpus, which caps what any tier-side change can deliver — including this one.
- **Any claim about the resulting tier rate.** The post-fix population is n=8 (Wilson CI 0.53–0.98). This change is justified by the structural asymmetry, not by a rate, and success is not measured by one.
- **Correcting the "1-3-file ceiling" misapplication** found in written justifications, where assessors cite a file count §5.2 explicitly disclaims. Real, but a separate and smaller edit.

## Edge Cases

- **The critic returns zero findings, fails, or times out.** §5's statement is unaffected — it is about the orchestrator's own tier reasoning, not about critic output, so it fires identically in all three cases.
- **Context B (no backlog item).** §5 already runs and skips write-backs. The statement is about critic influence, not about any recorded value, so it is unaffected by the absent ticket.
- **The orchestrator's judgment moves down.** It records `complexity-override` with `--reason`, exactly as it already would for an upward move. The verb already supports lowering; nothing new is needed.
- **A critic finding is dispositioned Ask and the user resolves it.** The reconciliation happens after §4's question round, so a user answer that simplifies scope can move the tier down before §5 writes.

## Changes to Existing Behavior

- **REMOVED**: `clarify-critic.md`'s optional complexity/criticality calibration clause, and any framing that invites it.
- **MODIFIED**: `clarify.md` §5's Complexity item — now requires a directional statement about whether critic findings moved the tier judgment.
- **UNCHANGED**: the rank-floor seed value, `§5.2`'s tier definitions, the escalator, `reconcile-clarify`'s monotonic guard, and the `when torn, take the lower tier` line.

## Technical Constraints

- **Phase ordering is a correctness constraint, not a convenience.** Shipping Phase 1 alone removes the one clause that nominally permitted a downward tier challenge, with nothing yet replacing it. Both phases land together or neither does.

- **Byte budget, measured — comfortable once phased, fatal if reversed.** The directory sits at 20583 against a 20588 pin. That 5-byte figure is only pre-edit slack, **not** the budget for R3: Phase 1's deletion frees **89 bytes**, so R3's sentence may be up to **94 bytes**, and a 73-byte conforming example ("State whether the next tier down was considered, and why it was rejected.") lands the directory at 20567 with ~21 bytes still spare. Do not over-trim R3's wording on a false impression of scarcity. Ordering is the real constraint: Phase 2 landing first would put the directory at 20654 and breach by 66. Re-run `just ratchet-refs` after both to lock in the lower floor.
- **Re-measure the budget immediately before Phase 2; do not trust the numbers above.** This directory is under concurrent churn — three commits touched it in the 36 hours before this spec was written. A sibling lifecycle committing to `specify.md`, `clarify-critic.md`, or `research-phase.md` between this ticket's two phases can consume the freed headroom and fail R6 at Phase 2 time, through no fault of this change. Treat the figures here as authoring-time observations, not a reservation.
- `plugins/cortex-core/skills/refine/references/*` are generated mirrors, rebuilt from staged blobs by the pre-commit hook. Edit canonical `skills/` only; expect the commit to contain mirror paths not named.
- `docs/policies.md` requires What/Why framing over procedural How, and the kept-pause taxonomy is untouched — no `<!-- pause: -->` marker is added or removed, so `kept-pauses-data.toml` needs no update.
- Editing `skills/` is lifecycle-gated per `CLAUDE.md`; this lifecycle satisfies that.

## Open Decisions

None. The mechanism was settled at spec interview: calibration leaves the critic entirely, and §5 requires a directional statement about critic influence on the tier. Two rejected alternatives, recorded so they are not re-proposed: comparing against the ticket's value (nothing to compare against in 88% of cases), and comparing against a pre-critic tier assessment (§2 rates confidence, not complexity — no such value exists).

## Proposed ADR

None considered. The change is a deletion plus a prose clarification within one skill and does not clear `cortex/adr/README.md`'s three-criteria gate.
