# Research: L1 frontmatter cap policy for new skills + research-description overage (#298)

Dispatched at tier=complex, criticality=high → 8 agents (3 core + 4 chosen + adversarial). The adversarial pass materially reshaped the ticket's framing; read `## Adversarial Review` and `## Open Questions` first — several of the ticket body's own premises did not survive scrutiny.

## Codebase Analysis

**Primary change target — `tests/test_l1_surface_ratchet.py`:**
- `_BASELINES: dict[str, int]` (lines 33–52) holds frozen per-skill byte counts + a `"total": 8339` row. Target skills: `research: 502` (L50), `interview: 758` (L42), `requirements-gather: 498` (L48), `requirements-write: 685` (L49), `backlog-author: 427` (L35). Any trim must drop both the per-skill value and `total`.
- Assertion (lines 84–105): parametrized one-case-per-skill, `assert actual <= baseline` (L98). Equal-or-lower passes. **No exception mechanism exists here** (unlike `test_skill_size_budget.py`).
- **Misdirected ticket-295 pointer — 3 occurrences, all should repoint to 298**: module docstring (L9–12), `_BASELINES` comment (L31–32), assertion failure message (L103–104). Ticket 295 is the unrelated dependency-bump ticket; confirmed misdirection.

**Measurement utility — `bin/cortex-measure-l1-surface`:** measures **UTF-8 bytes** of **`description` + `when_to_use` combined** (absent field = empty string), via `yaml.safe_load` (all scalar forms normalize). Enumerates `cwd/skills/` only — **canonical, never plugin mirrors**. The ratchet runs it with `cwd=REPO_ROOT`. This confirms the ticket's Edge: the cap bounds the **SUM**, in bytes; no new measurement code needed.

**Target skills' frontmatter:** `research` 502B (folded `description:`, **no `when_to_use`**); `interview` 758B (desc 417 + wtu 341, largest); `requirements-write` 685B (desc 233 + wtu 452); `requirements-gather` 498B (desc 279 + wtu 219); `backlog-author` 427B (folded `description:`, **no `when_to_use`**).

**Routing-guard surface:** `tests/test_skill_descriptions.py` checks trigger-phrase substrings vs `description` **alone** (canonical only); `tests/test_skill_routing_disambiguation.py` checks phrases vs concatenated `description+when_to_use` for the fixed cluster `(dev, lifecycle, refine, research, discovery, critical-review)`. **Of the 5 targets, only `research` is guarded by either test** (3 phrases). The other four have no phrase floor.

**Prior-art cap-with-exception — `tests/test_skill_size_budget.py`:** authoring-time **line-count** cap (`CAP=500`) with `<!-- size-budget-exception: <reason≥30char>, lifecycle-id=<NNN>, date=<YYYY-MM-DD> -->` marker grammar. Note: a *different unit* (lines, whole body) than the L1 byte/frontmatter surface.

**Plugin mirror / parity:** all 5 target skills are byte-identical real files at `plugins/cortex-core/skills/<name>/SKILL.md`. Editing canonical `skills/` requires `just build-plugin` (rsync mirror regen); `.githooks/pre-commit` auto-runs it and fails on drift for staged `skills/` paths. Canonical + mirror must commit **together** (per `feedback_drift_hook_shared_checkout_coupling`).

## Web Research

**Anthropic's SKILL.md spec:** `description` hard cap **1024 chars**; metadata for *all* skills is always-loaded (~100 tokens/skill); body loads only on trigger. No published sub-1024 budget and no tiered guidance. Anthropic's own example descriptions run ~150–230 chars — well under the cap.

**Does description length improve routing? Largely no:**
- arXiv 2505.18135 ("Tool Preferences are Unreliable"): lengthening a tool's description **systematically increases its selection regardless of correctness** — a length-as-salience bias. Implies *uniform* lengths across competing skills are desirable to avoid biasing the router toward verbose ones.
- EASYTOOL (NAACL 2025): rewriting verbose tool docs to concise standardized form **cut tokens 70.4% while improving tool utilization** — most description length is waste.
- CallNavi: enhancing descriptions had negligible effect on overall correctness but positive effect on **complex multi-tool-chaining cases** — the one direct empirical support for a **tiered** budget (complex/orchestrator skills benefit from more trigger detail; simple skills don't).

**Patterns:** progressive disclosure dominates, but the headline MCP "accuracy up 49%→74%" numbers come from loading *fewer tools*, not shorter descriptions — a tool-count effect, distinct from per-item byte budgets. No off-the-shelf per-item description-length linter exists; a byte-budget ratchet is a modest novel contribution, not a re-implementation.

**Anti-patterns:** "longer = better routing" (false); uneven lengths across competing skills (router bias); over-trimming trigger phrases out of the always-loaded description (the only routing signal).

## Requirements & Constraints

- **`project.md:48` (the constraint #298 fulfills):** "Frontmatter bytes per skill are bounded by the baselines in `tests/test_l1_surface_ratchet.py` … A deferred cap-policy ticket governs the formal policy; the ratchet enforces the snapshot until that policy lands." #298 *is* that ticket. The line refers to "a deferred cap-policy ticket" **without a number** — so project.md is not a 295-misdirect, but it's the natural place to name 298 and reflect deliberate budgets when the policy lands.
- **`project.md:34` (precedent):** SKILL.md size cap (500 lines) + `<!-- size-budget-exception -->` marker — the structural model for "cap + documented exception."
- **`project.md:33` parity:** `bin/cortex-measure-l1-surface` is a `cortex-*` script that must stay referenced from an in-scope surface (justfile recipe + the test); changes must not orphan it.
- **Philosophy (`project.md:19,21,53` / `CLAUDE.md` Solution horizon):** "Complexity must earn its place; simpler wins." The ratchet was *explicitly shipped as a snapshot a known follow-up (this ticket) would replace* — so under Solution-horizon this is the **planned durable version, not a stop-gap**; the durable policy is warranted. But durability does not mean a new subsystem — simplicity pushes toward a lightweight policy in the existing test.
- **MUST-escalation policy / What-not-How:** re-trimmed frontmatter must not introduce new MUST/CRITICAL language without the evidence artifact; prefer soft positive-routing phrasing. State the budget (What) and routing intent (Why), not procedure.
- **No ADR governs the L1 surface, the ratchet, or token budgets** — governance lives only in project.md:48, the test docstring, and the backlog ticket. Whether the policy clears the three-criteria ADR bar is a judgment call (likely no — it's enforcement detail, not an irreversible architectural decision).

## Tradeoffs & Alternatives

**Decision 1 — Enforcement fork (the required alternative exploration): recommend Approach A (reuse the ratchet)** over B (new pre-commit authoring-time gate). The ratchet already runs in `pytest tests/` (CI-gated); the docstring + project.md:48 pre-declared this ticket as the policy that supersedes the snapshot; the Integration section says "update the ratchet baselines in the same change." Approach B duplicates an enforcement surface that exists, adds ~5 touch-points to a 666-line pre-commit harness, and forces a new in-scope reference (adding to the very L1 surface being shrunk) to pass parity. "At authoring time" describes *intent* (catch overage when a skill is written), which a test in the standard suite satisfies — it does not mandate a pre-commit script. **Caveat (from Adversarial): Approach A as a literal `_BASELINES` relabel prevents nothing — see Decision-3 / Open Questions.**

**Decision 2 — Policy shape: tiered, not flat; bound the SUM.** Live baselines span 4.5× (commit 208 vs discovery 932) — a flat cap is either no constraint on simple skills or an instant breach for routing-heavy ones. Tiering reuses the routing-pressure-cluster concept `test_skill_routing_disambiguation.py` already encodes. Bounding the SUM is mechanically forced (the utility measures the SUM; capping `description` alone leaves `when_to_use` as an uncapped escape valve).

**Decision 3 — Unmeetable-cap fallback: re-cap with rationale recorded in the policy doc + an inline baseline comment** (the prior spec's "minimum-achievable + rationale + gap" form), **not** a ported `size-budget-exception` marker. The marker grammar guards line-count in the *body*; the L1 budget is *frontmatter bytes*. A body-level marker can't gate the frontmatter quantity it would excuse (it sits where `cortex-measure-l1-surface` can't see it) — porting it imports Approach-B machinery through the back door.

## Routing-Headroom Empirics

**Structural finding:** both routing tests read the same `must_contain` arrays from `tests/fixtures/skill_trigger_phrases.yaml`. **Only `research`** (of the 5 targets) has any entries — 3 phrases: `/cortex-core:research`, `research this topic`, `investigate this feature` (bare ~74B; natural with disambiguation signal ~163B). The other four (interview, requirements-write, requirements-gather, backlog-author) have **zero test-enforced phrase floors**. The L1 ratchet is a **ceiling, not a floor**.

**Per-skill achievable floors** (SUM, all required phrases preserved): research ~150–200B; interview ~250–350B (largest headroom, ~400B prunable); requirements-write ~250–300B; requirements-gather ~200–250B; backlog-author ~200–250B.

**The research 200B "MISS":** prior `post-trim-measurement.md` recorded research at 378B vs a 200 cap. The 378B floor was *author judgment* (treated label + extra phrases + angle-list as all required), not a test floor — that trim predated the fixture. The 3 currently-enforced phrases fit in ~163B. **But see Adversarial + Prior-Art: ~150–200B has no routing justification; the honest target is a revert, not a compression stunt.**

**Risk:** because 4 of 5 skills have no fixture guard, the ratchet will let them be trimmed to almost nothing without failing — routing degradation invisible to CI. Durable fix: add the 4 skills' disambiguation phrases to the fixture *before* trimming, so a floor exists.

## Prior-Art Lineage

**Critical correction to the ticket's premise — the "research ≤200 cap" and "five-skill ≤300 exemption" are from a rejected doc, not the binding spec:**
- The **binding** #191 spec (`reduce-boot-context-surface-claudemd-skillmd/spec.md` R5/R6) used a **2-tier** scheme: routing-pressure cluster `(critical-review, lifecycle, discovery, refine, dev, research)` **≤1000 chars**; all others **≤400 chars**; plus `requirements` as a **≤200-char single-sentence stub**. `research` lived in the **≤1000 cluster** — it was **never capped at 200** in the spec.
- The 3-tier ≤200/≤300/≤400 scheme (and the "research MISS") appear only in `post-trim-measurement.md`, which #191's **own review phase rejected** as a doc-classification error: `review.md:47` — "applies non-spec caps (300/200) … mislabeling `research` as MISS"; `review.md:77` — "mis-cites the spec … falsely flags `research` as MISS when it is well within its R5 cap."
- **Therefore the ticket's headline ("research 502B overage vs the old 200 cap") cites a number the prior review overturned.** #298 should treat the ≤200/≤300 tiers as *one proposed option that was never binding*, not decided prior art.

**The real research regression:** research was **378B at #191 close, 502B today = +124B genuine post-#191 growth**, and the growth is exactly the mechanism-narration #191 ordered removed ("Dispatches 3–10 parallel agents — sized by a tier×criticality matrix … always-last adversarial pass"). This **falsifies the ticket body's own decomposition** ("the original 13 grew only ~194B (+3.4%) … NOT regrowth of trimmed skills") — `research` is in the original 13 and regrew +124B with the trimmed content class.

**What harness-token-efficiency-trim deferred to 298:** it froze the 8,339B snapshot (ratchet only, no text changes) and handed 298 the cap design + research overage + the F6 decomposition. The drift (378→502) happened **under** the ratchet with no enforcing floor.

**Lessons:** (a) achievable floors for routing-heavy skills are far above the aspirational 200/300 — anchor tiers to observed floors, not optimistic numbers; (b) tiers are proven necessary but the *specific* scheme is contested — #298 must consciously pick one; (c) "re-cap with rationale beats silent miss," and the fix must be *enforced* (a per-skill budget the ratchet binds), not a prose footnote that lets the next drift go unchecked.

## Adversarial Review

- **The central task is partly a phantom.** Verified: the binding spec put `research` at ≤1000, not 200; #191's review called the 200-cap a mislabel. The right research deliverable is a **revert to the ~378B #191 close-state** (removing the +124B mechanism-narration regrowth) — **not** a re-cap to 200 and **not** finding-#4's ~150–200B compression stunt (which has no routing basis and would breach the cluster cap's intent).
- **Approach A as a literal `_BASELINES` relabel prevents nothing.** A budget set at current size *is* the snapshot with a new label; the drift happened under the ratchet. Only a budget set **below** current size (forcing the research revert) or **paired with floors** (so over-trim is also caught) has regression-prevention value. The spec must state the anti-drift mechanism explicitly — a ceiling alone has none against intra-budget drift.
- **The four-skill re-trim is unfalsifiable today.** None of interview/requirements-write/requirements-gather/backlog-author appear in any routing fixture, so any trim passes CI. "Re-trim to what routing needs" requires *first* landing trigger-phrase fixtures (≥3 each, as a separate prior commit — #191's R2 discipline) — or descoping the four-skill trim. The middle path (trim blind) is the trap.
- **Exception-grammar port is incoherent** (body marker can't gate frontmatter bytes) — drop it; use prose re-cap.
- **298/299 collide.** Both are `status:backlog` and both edit `skills/research/SKILL.md` + its mirror (299 = body trim, 298 = frontmatter). Independent landing → mirror-regen conflict + stale line numbers. Sequence them (299 as predecessor, or fold research-frontmatter work into 299).
- **Correction to finding #4:** the "no floor" property is **specific to the 4 new skills**; the other 13 (including `research`) DO have `test_skill_descriptions.py` floors. Don't add phrases to skills that already have them.
- **`requirements` ≤200 stub carve-out** is needed in any tier scheme, else the policy flags it or invites it to grow to the tier ceiling.

## Open Questions

The Research-phase items below are split into resolved (inline answer) and deferred-to-Spec (consequential design/scope decisions for the requirements interview). The deferred items are the ones the user should weigh in on at Spec §4.

1. **Research deliverable framing — revert vs re-cap.** **Recommended resolution (lean strong):** reframe research's target as a **revert to the ~378B #191 close-state** by removing the post-#191 mechanism-narration regrowth, and explicitly retract the ticket's "502 vs 200 cap" headline (cite `review.md` mislabel). *Deferred to Spec:* needs user confirmation because it contradicts the ticket body's stated premise and decomposition. Do **not** adopt ~150–200B.

2. **Four-skill re-trim scope.** Two coherent options; **trim-blind is excluded**. (A) Land trigger-phrase fixtures (≥3 phrases each) for interview/requirements-write/requirements-gather/backlog-author as a *prior* commit, then trim against the new floor; or (B) descope the four-skill re-trim — ship policy + research-revert + pointer fix only. *Deferred to Spec:* genuine scope decision for the user (effort vs coverage). *Lean: (A) if the four-skill trim stays in scope, since it makes the trim verifiable and durable; (B) is a legitimate smaller-scope ship.*

3. **Anti-drift mechanism (the policy's actual teeth).** A budget == current size has zero regression value. Options: set tier budgets **below** current size (forces the research revert and real trims) and/or pair the ceiling with the new fixture floors from OQ2. *Deferred to Spec:* the spec must state the explicit mechanism that would have caught research's 378→502 drift.

4. **Tier scheme.** Adopt the binding 2-tier (≤1000 cluster / ≤400 others) re-anchored to compression-achievable values, with an explicit `requirements` ≤200 stub carve-out — vs a finer per-skill budget table. *Deferred to Spec.* *Lean: 2-tier + requirements carve-out, values re-derived from observed floors (not the rejected 200/300).*

5. **298/299 sequencing.** Declare 299 a hard predecessor, fold the research-frontmatter revert into 299's trim map, or sequence explicitly. *Deferred to Spec / execution-ordering decision.* *Lean: fold research-frontmatter into 299 OR declare 299 predecessor so one change touches the file + regenerates the mirror once.*

6. **Enforcement fork.** *Resolved:* **Approach A (reuse the ratchet)** — but only viable if budgets actually constrain (OQ3). Reject a literal snapshot-relabel.

7. **Exception mechanism.** *Resolved:* **drop the `size-budget-exception` port** (incoherent for frontmatter bytes); use re-cap-with-rationale recorded in the policy doc + inline baseline comment.

8. **Policy home + author discovery.** *Resolved:* rewrite the `project.md:48` constraint in place to name the deliberate budgets, the tiers, and the re-cap fallback; add one CLAUDE.md authoring line pointing skill authors at the budget. A pre-commit lint is feasible but unearned now (Approach A covers enforcement).

9. **Pointer + decomposition fixes.** *Resolved:* repoint the 3 ticket-295 references in `test_l1_surface_ratchet.py` to 298; name 298 in `project.md:48`; correct the ticket's "original 13 grew only +194B" decomposition (research regrew +124B).

10. **Contradiction logged:** Prior-Art's "research can't go below ~378B without routing loss" vs Routing-Headroom's "~150–200B achievable." *Resolved:* these measure different floors — Prior-Art's is the *author-judgment/routing-quality* floor (the right basis); Routing-Headroom's is the *test-enforced minimum* (3 phrases only). The revert target (~378B) follows the routing-quality basis, not the bare test minimum.
