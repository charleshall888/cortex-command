# Specification: careful-revert-research-skillmd-frontmatter-to

## Problem Statement

`skills/research/SKILL.md`'s `description` regrew +124B after #191 closed (378B → 502B), re-adding the elaborated mechanism-narration ("sized by a tier×criticality matrix … always-last adversarial pass for high/critical") that #191 deliberately trimmed. A `description` is always-loaded L1 routing metadata (what the skill is + when to use it); how-it-works internals belong in the on-trigger body — a principle confirmed by Anthropic's own skill-authoring guidance ("describe the outcome and when to invoke it, not how it works internally"). The regrowth pays a per-turn token cost across every session and competes for routing attention against sibling cluster skills, with no routing benefit. This revert restores research's description to the #191 close-state with one deliberate correction (the stale agent count `3–5`→`3–10`), landing at **379B** — the #191 close-state (378B) plus 1 byte for the corrected count, a net **−123B** — and lowers its ratchet budget so the drift cannot silently recur. Note: the revert removes the *elaborated* mechanism clause but keeps the light one-line mechanism summary that #191's own close-state retained (a fuller mechanism-free trim is Option C, explicitly out of scope — see Non-Requirements). Split from #298 (which set the cap policy but could not carry this revert without becoming un-completable overnight); unblocked now that #299 (research body trim) is complete.

## Phases
- **Phase 1: Description revert** — rewrite research's `description` to the #191 close-state with the agent count corrected, and regenerate + stage the plugin mirror.
- **Phase 2: Ratchet & docstring** — lower the `research` and `total` budget rows to the tool-measured values, update the ratchet docstring, and verify all gates pass.

## Requirements

1. **Revert research's `description` to the #191 close-state with the agent count corrected.** Construct it deterministically: take `git show 500e8464:skills/research/SKILL.md`'s `description` block and apply only the single-token correction `3–5` → `3–10` (the dispatcher is now 3–10 per the fan-out matrix; a byte-identical revert would re-state a stale count). This removes the +124B elaborated-mechanism regrowth (`sized by a tier×criticality matrix … always-last adversarial pass for high/critical`) while preserving: the three **test-enforced** trigger phrases (`/cortex-core:research`, `research this topic`, `investigate this feature` — guarded by R2's routing tests) and, **preserved-by-construction with no test backstop**, `gather research for`, the refine-delegation phrase (`when /cortex-core:refine delegates its research phase`), and the `research.md or conversation output` disambiguation tail. Do NOT hand-author the text (hand counts drift from the tool's folded-scalar handling). **Acceptance**: `bin/cortex-measure-l1-surface` (run from repo root) reports `research 379` (this gate stands alone — it does not depend on the Phase-2 baseline edit), AND the resulting `description` is byte-equal to `git show 500e8464:skills/research/SKILL.md`'s description with `3–5`→`3–10` applied (`diff` of the two folded strings is empty). **Phase**: Description revert

2. **Both routing guard tests pass with the reverted description.** **Acceptance**: `python3 -m pytest tests/test_skill_descriptions.py tests/test_skill_routing_disambiguation.py -q` exits 0 (the three trigger phrases remain present in `description`, which has no `when_to_use`, so both tests see the same surface). **Phase**: Description revert

3. **Regenerate the cortex-core plugin mirror and stage it together with the canonical edit.** `just build-plugin` regenerates `plugins/cortex-core/skills/research/SKILL.md` from canonical — this *creates* a working-tree mirror delta that must be explicitly staged; the fail-closed pre-commit drift hook runs `build-plugin` then `git diff --quiet -- plugins/…` and aborts the commit (exit 1) if the regenerated mirror is unstaged, so canonical + mirror must land in the **same commit**. **Acceptance**: after `just build-plugin`, the rebuilt mirror's frontmatter is byte-equal to canonical (`diff <(git show :skills/research/SKILL.md) …` once both staged), and at commit time the pre-commit hook's `git diff --quiet -- plugins/cortex-core/skills/research/SKILL.md` exits 0 (no unstaged mirror delta). Pass if both `skills/research/SKILL.md` and `plugins/cortex-core/skills/research/SKILL.md` appear in `git diff --cached --name-only` for the landing commit. **Phase**: Description revert

4. **Lower the `research` and `total` ratchet budgets to the tool-measured values.** In `tests/test_l1_surface_ratchet.py`, set `_BASELINES["research"]` from `502` to the value `bin/cortex-measure-l1-surface` reports (expected `379`), and `_BASELINES["total"]` from `7320` to `6818 + research` (expected `7197`). Copy the tool-emitted numbers verbatim; do not hand-compute. Note: the ratchet test asserts `actual <= baseline` (a one-sided direction check), so pytest passing confirms only `measured <= budget` — the exact budget==measured equality (the anti-drift property) is pinned by the literal-value grep below, not by pytest. **Acceptance**: `grep -c '"research": 379' tests/test_l1_surface_ratchet.py` = 1 AND `grep -c '"total": 7197' tests/test_l1_surface_ratchet.py` = 1 (substituting the actual tool values if they differ) AND `python3 -m pytest tests/test_l1_surface_ratchet.py -q` exits 0. **Phase**: Ratchet & docstring

5. **Update the ratchet docstring to reflect the landed revert.** The module-docstring provenance block (lines ~22–26, *above* the `_BASELINES` dict) currently states research "stays at its deliberate cluster budget of 502 until the follow-on revert (ticket 302) lands." Rewrite it to state research is at its post-revert budget (379) and that #302 has landed. **Acceptance**: `grep -c 'until the follow-on revert (ticket 302) lands' tests/test_l1_surface_ratchet.py` = 0 AND the **docstring region** references the new value: `sed -n '1,50p' tests/test_l1_surface_ratchet.py | grep -c '379'` ≥ 1 (scoped to the header/docstring above the `_BASELINES` dict so it is not satisfied as a side-effect of R4's dict edit). **Phase**: Ratchet & docstring

6. **The pre-commit gate set and full suite pass for the edited files.** Staging `skills/research/SKILL.md` and `tests/test_l1_surface_ratchet.py` fires these `--staged`-scoped pre-commit gates (all exit 0 for this change): **parity** (`check-parity --staged`; no `cortex-*` bin reference added), **contract** (`check-contract --staged`), **events-registry** (`check-events-registry`; no event name added), **prescriptive-prose** (triggers on `skills/*` but scans only ticket-body sections, so it is a no-op on frontmatter), **bare-python-lint**, and **skill-path**. `just test` exits 0. **Acceptance**: the landing commit's pre-commit hook exits 0; `just test` exits 0. Note: repo-wide `--audit` runs are already non-zero today (a pre-existing `E104` at `docs/overnight-operations.md:693`, plus non-zero parity/events-registry audits) — that is the baseline, not a regression from this change; gate only on the `--staged` scope of the edited files. **Phase**: Ratchet & docstring

## Non-Requirements

- Does NOT touch research's SKILL.md **body** — that was #299's byte-disjoint territory (now complete). Edits are confined to the `description` frontmatter.
- Does NOT pursue the mechanism-free ~265B form (Option C). The operator selected Option B (~378B target); dropping the light mechanism one-liner entirely is a scope reinterpretation that over-trims past the ticket's "do not over-trim toward 200" boundary, and is explicitly out of scope.
- Does NOT trim toward the ~163–200B test-enforced minimum (a rejected "compression stunt" with no routing justification).
- Does NOT change any other skill's `description` or budget row; only `research` and `total` move. (Caveat: research's surviving `research.md or conversation output` tail is a cross-skill coupling — see Technical Constraints.)
- Does NOT raise any budget (only lowers) — so no re-cap rationale or lifecycle-id is required.
- Does NOT introduce new MUST/CRITICAL/REQUIRED language (the removed "always-last … for high/critical" wording is mechanism, not escalation).
- Does NOT add a minimum-byte floor test (none exists; introducing one is separate work).

## Edge Cases

- **Folded `>` scalar trailing newline**: the YAML folded scalar clip-chomps exactly one trailing `\n` that `cortex-measure-l1-surface` counts, so hand counts drift by ~1 byte. Mitigation: R1/R4 gate on the tool output and the deterministic git-derived construction, never on a hand count.
- **Forgotten `total` update passes green**: the `total` row is a ratchet case with `actual <= baseline` direction, so leaving it at a stale-high 7320 (measured 7197) still *passes* — silently re-opening the budget-above-measured drift channel that let research grow 378→502. R4 makes lowering `total` a hard requirement and pins the exact value via grep (pytest alone cannot catch a too-high budget).
- **Mirror-staging stall (overnight)**: because `just build-plugin` creates an *unstaged* mirror delta and the drift hook fails closed, an autonomous commit that stages canonical-only aborts at the hook rather than landing a bad commit. R3 requires staging canonical + regenerated mirror in the same commit to avoid the stall.
- **Intermediate state is safe**: after the Phase-1 description edit but before R4, the ratchet still passes (`379 <= 502`). No broken intermediate budget state; the only Phase-1 commit hazard is the mirror-staging stall above.
- **No min-byte floor test**: an accidental over-trim would pass all tests green; only review and R1's deterministic git-derived construction guard against it.
- **Re-running on a dirty/edited base**: if the on-disk description is no longer 502B at implementation time (e.g., another skill's budget drifted, perturbing the `total` arithmetic, or research's frontmatter was touched), re-derive the description from `git show 500e8464` and re-read both `research` and `total` from a fresh `cortex-measure-l1-surface` run rather than trusting the cached 379/7197.

## Changes to Existing Behavior

- **MODIFIED**: research's always-loaded L1 `description` surface shrinks 502B → 379B (removes the *elaborated* mechanism-narration regrowth — the tier×criticality / always-last-adversarial clause — while keeping the light one-line mechanism summary, the trigger phrases, the refine-delegation hook, and the research.md-vs-conversation disambiguation tail).
- **MODIFIED**: `tests/test_l1_surface_ratchet.py` — `_BASELINES["research"]` 502→379, `_BASELINES["total"]` 7320→7197, and the provenance docstring updated to reflect #302 landed.
- **MODIFIED**: `plugins/cortex-core/skills/research/SKILL.md` mirror regenerated to match canonical.
- No change to research's runtime dispatch behavior (the SKILL.md body is untouched).

## Technical Constraints

- Editing canonical `skills/` is lifecycle-gated. Staging `skills/research/SKILL.md` + `tests/test_l1_surface_ratchet.py` fires these `--staged` pre-commit gates, all expected to exit 0 for this change: parity (SKILL.md↔bin), contract, events-registry, prescriptive-prose (no-op on frontmatter), bare-python-lint, skill-path. Run them per edit.
- Mirror regen is `just build-plugin`; it *creates* a working-tree delta in `plugins/cortex-core/skills/research/SKILL.md` that must be staged so canonical + mirror commit together (drift-hook + shared-checkout coupling). `test_plugin_mirror_parity.py` does NOT cover the research mirror — the fail-closed pre-commit drift hook is the only mirror guard, so do not skip `just setup-githooks`.
- **Cross-skill coupling**: research's surviving `research.md or conversation output` tail is depended on by `skills/discovery/SKILL.md`'s by-name cross-reference ("Different from /cortex-core:research — research produces a research.md and stops"). This revert preserves the tail, so the coupling holds; but any *future* trim of that tail must update discovery's description in lockstep — there is no test tripwire for this asymmetric, sibling-hosted dependency.
- Budget == measured, no headroom (the #298 anti-drift pattern; headroom is what permitted the 378→502 drift). This equality is enforced by R4's literal-value grep, not by the `<=` ratchet assertion.
- Deterministic construction is mandatory: `git show 500e8464:skills/research/SKILL.md` description + only the `3–5`→`3–10` swap; baselines copied verbatim from a fresh `bin/cortex-measure-l1-surface` run.
- Sequence after #299 (complete) — already satisfied; #299 edited the body only and left the frontmatter (still 502B) untouched.

## Open Decisions

None. The one open decision from research (target shape: Option B at ~378B vs Option C at ~265B) was resolved by the operator at spec time — Option B.

## Proposed ADR

None considered.
