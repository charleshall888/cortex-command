# Specification: open-critical-review-agent-count

## Problem Statement

`/cortex-core:critical-review` dispatches far more agents than its own
documentation claims. Across 82 dated `critical-review-residue.json` files,
`reviewers.dispatched` was 4 in 89% of runs and 3 in 11% — **never the documented
2**. Both runs postdating the "Default 2" prose (`3feec553`, 2026-07-27) dispatched
4 and 3. With the synthesizer, every invocation costs 4–5 agents. The gate fires on
every `complex` + `medium`/`high`/`critical` spec, so this is the harness's widest
routine fan-out, and `project.md`'s token-economy constraint names fan-out width as
one of three cost levers. This change cuts the routine run to 2–3 agents by
narrowing reviewer width to 1–2 and removing the escalation clause that made the
documented default unreachable.

## Phases

- **Phase 1: Narrow reviewer width** — one coherent prose change across the skill,
  its two documentation consumers, and the ratified requirements clause.

## Requirements

1. **Reviewer width is 1–2 angles with no escalation tier.** `skills/critical-review/SKILL.md`
   Step 2 states a 1–2 range chosen by the orchestrator, and contains no clause
   permitting 3 or more. **Acceptance**: `sed -n '/## Step 2:/,/## Step 3:/p'
   skills/critical-review/SKILL.md | grep -n "3–4\|3-4"` returns no output; the width
   sentence names 1 and 2 only. **Phase**: Narrow reviewer width

2. **Criticality weighting survives as a single clause, not a matrix.** The width
   sentence carries a weighting toward 2 at `high`/`critical`, honoring
   `docs/internals/sdk.md:144`'s retained ruling ("reviewer count … is what
   criticality buys") without a lookup table. **Acceptance**: Step 2 contains one
   sentence mentioning `high`/`critical` in connection with preferring 2; no table,
   no per-cell mapping, and `docs/internals/sdk.md` is unmodified. **Phase**: Narrow reviewer width

3. **Over-subscription has a stated rule.** Step 2 says what to do when the artifact
   presents more genuinely distinct weaknesses than slots: take the highest-severity
   ones and do not widen. This closes the pressure Step 2's own distinctness rule
   creates (research, Adversarial §4). **Acceptance**: in `skills/critical-review/SKILL.md`,
   the Step 2 section (`## Step 2:` heading through the next `##` heading) contains
   both a severity-priority instruction (matching `highest-severity` or `highest
   severity`) and an explicit widen-prohibition (matching `not widen`, `don't widen`,
   or `does not widen`); expected: both patterns present. **Phase**: Narrow reviewer width

4. **The total-failure fallback is reconciled to the new range.** `SKILL.md:34`'s
   all-reviewers-failed branch currently derives "3–4 angles"; it must not state a
   breadth wider than the primary path. **Acceptance**: the fallback sentence names
   the same 1–2 range; `grep -c "3–4" skills/critical-review/SKILL.md` returns 0. **Phase**: Narrow reviewer width

5. **Width-1 does not leave unreachable prose.** At width 1 the partial-coverage
   branch ("Some reviewers failing → synthesize from the rest … N of M") is
   unreachable, since 0 completed is indistinguishable from total failure. Step 4's
   failure handling must read coherently at both width 1 and width 2. **Acceptance**:
   Interactive/session-dependent: whether the reworded Step 4 partial-coverage
   sentence makes a true statement at width 1 (versus describing a state that cannot
   occur) is a semantic reachability judgment, not a string pattern a command can
   check. **Phase**: Narrow reviewer width

6. **L1 surface stays truthful about parallelism.** `description` and `when_to_use`
   must not assert parallel dispatch unconditionally, since width 1 is a normal case.
   All four `must_contain` trigger phrases survive. **Acceptance**:
   `uv run pytest tests/test_skill_routing_disambiguation.py tests/test_l1_surface_ratchet.py`
   passes, and the L1 byte sum stays ≤795 (currently 652). **Phase**: Narrow reviewer width

7. **`docs/skills-reference.md:110` matches the shipped rule.** It currently reads
   "default 2, escalating to 3-4 on high/critical criticality or novel claims".
   **Acceptance**: that line states the 1–2 range and carries no "3-4"; its
   description of the synthesis agent is left intact. **Phase**: Narrow reviewer width

8. **`cortex/requirements/project.md:38` is amended.** The width half becomes 1–2
   with the criticality weighting; the dead "routed to Sonnet with an Opus
   synthesizer" clause is dropped, as ADR-0032 (accepted) superseded model selection
   and `cortex/adr/README.md:51-55` forbids restating a superseded decision body.
   The "gates at spec only" half and "Supersedes #383" are preserved.
   **Acceptance**: line contains "1–2", contains neither "Sonnet" nor "Opus", and
   still contains "Supersedes #383". **Phase**: Narrow reviewer width

9. **The change is net-negative on prose bytes.** The escalation clause is deleted
   and nothing longer replaces it. **Acceptance**: `wc -c skills/critical-review/SKILL.md`
   is lower than at HEAD before the change. **Phase**: Narrow reviewer width

10. **Mirror and ratchet hygiene.** The `plugins/cortex-core/` mirror is regenerated
    by the pre-commit hook from staged blobs rather than hand-edited.
    **Acceptance**: `uv run pytest tests/test_dual_source_reference_parity.py tests/test_reference_size_ratchet.py tests/test_skill_size_budget.py`
    passes and the commit contains the regenerated mirror paths. **Phase**: Narrow reviewer width

## Non-Requirements

Descoped by the 2026-08-04 decisions to keep the synthesizer and honor the
criticality ruling. Each was researched; none is an oversight:

- **Deleting the synthesizer subagent / Step 5.** The 2026-04-25 upstream-only pivot
  (`cortex/lifecycle/archive/critical-review-orchestrator-pushback-on-findings/research.md:205`,
  `spec.md:41`) stands. `references/synthesizer-prompt.md` is untouched, so the
  size-pin stays 4702 and no step is renumbered.
- **`project.md:39`** — its synthesizer example remains accurate; no re-derivation.
- **`skills/refine/references/clarify-critic.md:61`** — its "keep the two in sync"
  citation of Step 7 holds, since no step is deleted.
- **`skills/refine/references/specify.md:88`** — synthesis is still presented before
  approval; unchanged.
- **`synthesis_status` and the residue schema** — unchanged. The pre-existing misfire
  (9 of 91 residues lack the field and render a false `⚠ degraded: synthesis failed`
  via `report.py:1375-1384`, pinned by `tests/test_report.py::test_missing_required_fields_default_unknown`)
  is real but independent of this change; it is not fixed here.
- **`docs/internals/sdk.md:144`** — honored, not amended.
- **Structural enforcement of the width.** Explicitly rejected by the user in favor
  of prose. See Technical Constraints for the risk this carries.
- **Any new CLI verb, matrix, config key, or test asserting a dispatch count.**

## Edge Cases

- **Width 1 and a malformed envelope**: the single reviewer's envelope fails to
  parse → zero findings survive. Behaves as total reviewer failure and takes the
  existing fallback branch; must not report "0 of 1 completed" as partial coverage.
- **Width 1 and a clean run**: no through-lines and no tensions exist to find. The
  synthesizer's `## Through-lines` / `## Tensions` sections are already
  skip-if-empty, so no change is needed — but the run must not read as degraded.
- **More than two distinct weaknesses**: covered by R3 — highest-severity wins, no
  widening, no bundling several concerns into one over-stuffed angle description.
- **`criticality` is `high` or `critical`** (the common case, since the gate only
  fires at `medium`+): weighting prefers 2, but 2 is the ceiling — this must not
  reintroduce an escalation path.
- **Residue accounting at width 1**: `reviewers: {completed: 1, dispatched: 1}` must
  still be written; the morning report's partial-coverage annotation must not fire.

## Changes to Existing Behavior

- **MODIFIED** — `skills/critical-review/SKILL.md` Step 2: width `default 2, escalate
  3–4` → `1–2`, escalation clause removed, weighting and over-subscription clauses added.
- **MODIFIED** — `SKILL.md` Step 4: fallback breadth 3–4 → 1–2; partial-coverage
  branch made width-1-coherent.
- **MODIFIED** — `SKILL.md` frontmatter: parallelism no longer asserted unconditionally.
- **MODIFIED** — `docs/skills-reference.md:110`, `cortex/requirements/project.md:38`.
- **REMOVED** — the criticality/novel-claims escalation clause, and `project.md:38`'s
  superseded model-routing clause.
- **Runtime effect**: routine invocations go from 4–5 agents to 2–3.

## Technical Constraints

- **Prose-only, by explicit user decision.** No verb, matrix, or test may assert a
  dispatch count. The known risk, stated plainly: width prose has a **0-for-82**
  compliance record on this exact skill, and its most recent revision was ignored by
  both subsequent runs. The mitigation is structural-in-spirit rather than in
  mechanism — the previous prose carried an escape hatch that fired on nearly every
  artifact, and a flat range has nothing to escalate through. This is a hypothesis,
  not a guarantee, and `reviewers.dispatched` in future residue files is the way to
  falsify it.
- `cortex/adr/README.md`'s three-criteria gate is not met (trivially reversible), so
  no ADR. Both predecessor decisions on this same clause (#383's supersession, #403)
  landed as plain `project.md` edits.
- Editing `skills/` is lifecycle-gated; edit canonical sources only and let the
  pre-commit hook fold in the `plugins/cortex-core/` mirror.
- `tests/test_l1_surface_ratchet.py:57` budgets this skill at 795 bytes (currently
  652). A reduction needs no re-cap or lifecycle-id.
- `references/` is untouched, so the `just ratchet-refs` → `just build-plugin` →
  `just ratchet-refs` sequence is not required and `size-pin.txt` stays at 4702.

## Open Decisions

None. Research OQ5 (fallback breadth) and OQ6 (over-subscription pressure) are
resolved into R4 and R3 respectively rather than deferred.

## Proposed ADR

An ADR was considered and rejected: `cortex/adr/README.md`'s three-criteria gate is
not met because criterion 1 (hard to reverse) fails — this change is two prose-file
edits, trivially reversible.
