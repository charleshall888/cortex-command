# Specification: lead-refine-4-complexity-value-gate

## Problem Statement

The `/cortex-core:refine` skill's §4 complexity-value gate (`skills/refine/SKILL.md`:162) currently presents value case + complexity cost + 2–3 alternatives as a neutral menu and waits for the user to pick. The user almost always defaults to full scope, so the neutral menu wastes operator time and signals agent uncertainty when the analysis usually supports full scope. This spec amends §4 so the gate (a) always announces a per-feature recommendation with a one-sentence rationale, and (b) only renders the multi-option `AskUserQuestion` when the recommendation is not full scope or when confidence is low. When the recommendation is confidently full scope, the rationale is announced and the flow falls through to the existing approval surface (Approve / Request changes / Cancel) without an intervening pick-menu.

## Phases

- **Phase 1: §4 rewrite + structural coupling** — amend `skills/refine/SKILL.md` §4 prose; add the kept-pauses inventory line in `skills/lifecycle/SKILL.md`; add `tests/test_refine_skill.py` with prose-shape assertions; verify plugin mirror regenerates.

## Requirements

1. **§4 bullet rewritten** in `skills/refine/SKILL.md` (single logical bullet at the existing `Complexity/value gate` anchor): the rewrite (a) keeps the gate-fire trigger conditions identical to the current prose (3+ distinct new state surfaces / new persistent data format / subsystem with ongoing per-feature upkeep), (b) introduces a per-feature recommendation step before any user-facing question, (c) instructs the orchestrator to announce the recommendation with a one-sentence rationale citing the specific spec surface(s) driving the choice, and (d) instructs the orchestrator to call `AskUserQuestion` only when the recommendation is not full scope OR when the orchestrator is uncertain — otherwise fall through to the existing approval surface. **Phase**: Phase 1. **Acceptance**: `grep -c "Complexity/value gate" skills/refine/SKILL.md` = 1 (anchor preserved) AND `grep -c "I recommend\|recommend " skills/refine/SKILL.md` ≥ 1 AND `grep -c "AskUserQuestion" skills/refine/SKILL.md` ≥ 1.

2. **`(Recommended)` capital-R label suffix** specified in §4 prose: the rewrite states that when the `AskUserQuestion` is rendered, the lead option's `label` ends with the literal suffix ` (Recommended)` (single leading space, capital R). **Phase**: Phase 1. **Acceptance**: `grep -c "(Recommended)" skills/refine/SKILL.md` ≥ 1, located within the §4 bullet (verified by the regex assertion in Req 6).

3. **Conditional fire encoded in prose**: §4 prose states that `AskUserQuestion` fires only when the orchestrator's recommendation is not full scope OR when confidence is low; otherwise, the announcement is folded into the regular approval surface. **Phase**: Phase 1. **Acceptance**: `grep -E "only when|unless|when the recommendation" skills/refine/SKILL.md` returns a match inside the §4 bullet, confirming a conditional-fire clause is present.

4. **Downsize-option labels carried through**: §4 prose continues to enumerate `drop entirely`, `bugs-only`, and `minimum viable` as the canonical downsize candidates (already present at line 162), and adds `Confirm current scope` as the lead option when the `AskUserQuestion` is rendered. **Phase**: Phase 1. **Acceptance**: `grep -c "drop entirely" skills/refine/SKILL.md` ≥ 1 AND `grep -c "bugs-only" skills/refine/SKILL.md` ≥ 1 AND `grep -c "minimum viable" skills/refine/SKILL.md` ≥ 1 AND `grep -c "Confirm current scope" skills/refine/SKILL.md` ≥ 1.

5. **Kept-user-pauses inventory updated** in `skills/lifecycle/SKILL.md`: a new bullet is added under the `### Kept user pauses` section pointing to the line in `skills/refine/SKILL.md` where the new `AskUserQuestion` call site appears, formatted as `- \`skills/refine/SKILL.md:<line>\` — <one-line rationale>`. The rationale notes the conditional nature (fires only when recommendation diverges from full scope or confidence is low). **Phase**: Phase 1. **Acceptance**: `pytest tests/test_lifecycle_kept_pauses_parity.py` exits 0.

6. **New test file** at `tests/test_refine_skill.py` containing four regex assertions against `skills/refine/SKILL.md`: (a) `\(Recommended\)` appears within 35 lines after the `Complexity/value gate` anchor, (b) `I recommend` (or `recommend `) appears inside the §4 bullet block, (c) one of `rationale` or `because` appears between the `Complexity/value gate` anchor and the `(Recommended)` literal (proves rationale-first ordering), (d) the substring `MUST decide` does NOT appear inside the §4 bullet (negative assertion guarding against MUST-escalation regression). **Phase**: Phase 1. **Acceptance**: `pytest tests/test_refine_skill.py` exits 0 AND `grep -c "def test_" tests/test_refine_skill.py` ≥ 4.

7. **No new MUST/REQUIRED/CRITICAL in §4 amendment**: the amendment text uses soft positive-routing phrasing per `CLAUDE.md`:72–84 — declarative verbs ("Decide", "Announce", "Call") rather than `MUST decide` / `MUST announce`. **Phase**: Phase 1. **Acceptance**: covered by the negative regex assertion in Req 6(d) (no `MUST decide` inside the §4 bullet).

8. **Plugin mirror regenerates**: `plugins/cortex-core/skills/refine/SKILL.md` is overwritten by `just build-plugin` so its §4 prose matches `skills/refine/SKILL.md`. **Phase**: Phase 1. **Acceptance**: `diff <(sed -n '/Complexity\/value gate/,/Hard Gate/p' skills/refine/SKILL.md) <(sed -n '/Complexity\/value gate/,/Hard Gate/p' plugins/cortex-core/skills/refine/SKILL.md)` exits 0 after `just build-plugin`.

## Non-Requirements

- Touching the orchestrator-review §4 surface (different skill, different gate) — out of scope per ticket #209.
- Touching the lifecycle's `drop entirely / minimum viable / hardened` presentation in `/cortex-core:lifecycle` — out of scope per ticket #209 (separate change set if user wants it propagated).
- Auto-skipping the entire gate when triggers fire — the rationale is always announced; only the multi-option pick-menu is conditional. The announcement (value case / complexity cost / rationale) still fires whenever the gate's three trigger conditions match.
- Reworking the kept-user-pauses parity test itself — only the inventory entry and the call-site line are added.
- Modifying the §4 trigger conditions (3+ state surfaces / new persistent data format / ongoing upkeep) — those remain identical.
- Adding telemetry or events.log entries for gate-fire vs gate-skip — out of scope.

## Edge Cases

- **No natural downsize alternatives**: §4 already states "If an alternative doesn't naturally apply, say so." The rewrite preserves this. If the orchestrator finds no meaningful downsize, the announcement says so and falls through to the regular approval surface (`AskUserQuestion` is not rendered).
- **Recommendation is "drop entirely"**: the recommendation is not full scope, so `AskUserQuestion` fires with `Drop entirely (Recommended)` as the lead option, followed by `Confirm current scope` and other downsize alternatives.
- **Orchestrator is uncertain which option to recommend**: confidence is low, so `AskUserQuestion` fires. The lead option is still the orchestrator's best guess marked `(Recommended)`; the question body acknowledges the uncertainty in the rationale.
- **Gate fires but the spec is genuinely tiny and full scope is obviously correct**: announcement renders the rationale (e.g., "I recommend Confirm current scope — the only added persistence cost is one config line and the value case is X."), then the flow falls through to the regular approval surface with no intervening pick-menu.
- **Author of an unrelated future PR moves the §4 bullet**: the parity test in `tests/test_lifecycle_kept_pauses_parity.py` (±35-line tolerance) and the `Complexity/value gate` anchor regex in `tests/test_refine_skill.py` will both surface the drift on `just test`.

## Changes to Existing Behavior

- **MODIFIED**: `skills/refine/SKILL.md` §4 complexity-value gate adaptation under Step 5 — the gate now leads with a per-feature recommendation + rationale; the multi-option `AskUserQuestion` is rendered conditionally.
- **MODIFIED**: `skills/lifecycle/SKILL.md` "Kept user pauses" inventory — adds a new bullet pointing at the new `AskUserQuestion` call site in `skills/refine/SKILL.md`.
- **ADDED**: `tests/test_refine_skill.py` — new test file with §4 prose-shape assertions.
- **ADDED (mirror)**: `plugins/cortex-core/skills/refine/SKILL.md` is regenerated by `just build-plugin` to match the canonical source.

## Technical Constraints

- **SKILL.md size cap**: `skills/refine/SKILL.md` is 212/500 lines; an inline worked example of ~12–20 lines stays well within budget (`tests/test_skill_size_budget.py` enforces).
- **Soft-form phrasing**: the amendment uses declarative verbs (not MUST/REQUIRED/CRITICAL) per `CLAUDE.md`:72–84 MUST-escalation policy. The ticket-body wording `MUST decide` is interpretive and is not reproduced verbatim.
- **Kept-pauses parity tolerance**: `LINE_TOLERANCE = 35` at `tests/test_lifecycle_kept_pauses_parity.py`:27 — the inventory entry's rough-line anchor must point within ±35 lines of the actual `AskUserQuestion` mention in `skills/refine/SKILL.md`.
- **Anchor preservation**: `skills/refine/SKILL.md`:164 cross-references the heading "Complexity/value gate" — the rewrite must preserve that anchor text so the cross-reference does not stale.
- **Plugin mirror drift gate**: `.githooks/pre-commit` enforces `plugins/$p/` parity with the source tree via `just build-plugin`. The pre-commit hook fails the commit if the mirror is stale, so the implementer must run `just build-plugin` (or rely on the hook to do it) before pushing.
- **No new orchestrator persistence**: the conditional-fire decision is computed in-context each time the gate evaluates; no new state file or config flag is introduced.

## Open Decisions

None. The three decisions deferred from `research.md` (`(Recommended)` capital-R standardization, literal `AskUserQuestion` + inventory line with conditional-fire semantics, and carrying through the `drop entirely / bugs-only / minimum viable` downsize labels) were all resolved with the user during the Spec interview and are encoded in the Requirements and Technical Constraints sections above.
