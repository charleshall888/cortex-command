# Specification: skill-suite-dedup

## Problem Statement

The core skill constellation (lifecycle, refine, critical-review, research, discovery) carries AI-authored verbosity and two latent path-resolution bugs. Per the leanification campaign, reduce token bloat and fix the bugs while **preserving lifecycle behavior** and not breaching the test-pinned surfaces. Full findings in `research.md`.

## Phases

A single implementation, ordered risk-first then fat-first. Each phase ends with `just build-plugin` (regenerate mirrors) + `just test` (guard the pinned surfaces) before the next begins.

1. **Bugs** — Bug 1 (refine standalone resolution), Bug 2 (discovery `research.md:104`).
2. **Fat cuts** — research roster (R4), `decompose.md` LEX-1 (R5), `refine §4` gate (R6). (`implement.md §1a` dropped — see R3.)
3. **Leading words + dedup** — tier ratchet, fresh-eyes, adversarial triads; 4 single-source targets.
4. **Description trims** — fixture-aware.

## Requirements

**MoSCoW:** R1–R2 (bugs) and R10 (the no-regression invariant) are **Must**. R4–R9 (leanification) are **Must for this feature** — each is independently droppable without breaking the others, but all are in-scope here. **R3 was dropped** on §3b evidence (negligible yield, real risk — see below). Nothing is Should/Could. The **Won't** set is the Non-Requirements section.

Every requirement's acceptance is anchored by the **global gate (R10): `just build-plugin` clean + `just test` green + no lifecycle behavior change**, plus the requirement-specific binary check named below.

- **R1 (Bug 1) — Phase 1:** refine SKILL.md's Step 5 adaptation block resolves `orchestrator-review.md` and `critical-review-gate.md` itself as body-resolved `${CLAUDE_SKILL_DIR}/../lifecycle/references/…` paths (mirroring `:146`); `specify.md:149/153/164` reworded to "the propagated `<target>` path" without naming lifecycle's manifest. *Acceptance:* grep of refine SKILL.md shows both targets resolved in-body; `test_critical_review_gate_nonlocal_failsafe` + `cortex-check-skill-path` green.
- **R2 (Bug 2) — Phase 1:** `discovery/references/research.md:104` uses the propagated orchestrator-review target consistent with discovery SKILL.md's sibling-path-propagation section (or is documented as intentionally bare with rationale). *Acceptance:* no bare-relative `references/…` path remains at `:104`, or a one-line rationale comment is present; `cortex-check-skill-path` green.
- **R3 — DROPPED from scope (moved to Non-Requirements):** the `implement.md §1a` prune. §3b review proved recoverable fat is ~zero — its bytes *are* the test-pinned Step v token-order and diagnostic literals — while any relocation is an **unconditional** `test_lifecycle_step_v_ordering.py` failure. Negligible yield against real breakage risk in the most test-pinned section of the repo; not worth the minefield.
- **R4 — Phase 2:** `research/SKILL.md:73-178` — disclose the conditional Adversarial/Tradeoffs templates to a reference; keep the always-fired core inline. *Acceptance:* the two conditional templates no longer inline in SKILL.md; core templates + placeholder markers intact — **extend `test_dispatch_template_placeholders.py` to cover research/SKILL.md's `{topic}` / `{INJECTION_RESISTANCE_INSTRUCTION}` / `{research_considerations_bullets}` markers** (it currently does not); `just test` green.
- **R5 — Phase 2:** `decompose.md:95-114` — keep the LEX-1 rule + 1-2 examples inline; delete the tool-maintainer regex detail (or disclose to a scanner-spec reference). *Acceptance:* regex-level detail absent from decompose.md; the LEX-1 rule statement + ≥1 example present; `test` covering the prescriptive-prose scanner green.
- **R6 — Phase 2 (corrected by §3b review):** `refine/SKILL.md:147` §4 gate — prune procedural narration **in place** (no relocation). **PRESERVE the user-visible AskUserQuestion format strings**: the `(Recommended)` suffix and its preceding rationale clue are pinned by `test_refine_skill.py` (within 35 lines of the gate anchor) and are output contract, *not* prunable How. *Acceptance:* the gate remains in refine SKILL.md; fire-conditions + default-recommendation logic + the AskUserQuestion decision + the `(Recommended)` format string still present; `test_refine_skill.py` + `test_lifecycle_kept_pauses_parity` green.
- **R7 — Phase 3:** Coin **tier ratchet** (seed→reconcile→gate) and **fresh-eyes** (critical-review no-anchoring), collapsing their restatements onto the token; collapse the adversarial triads onto **adversarial**. Define each once. *Acceptance:* each term defined exactly once and referenced by token thereafter; the `:99` "Anchor-checks" (opposite sense) preserved distinctly; `just test` green.
- **R8 — Phase 3 (acceptance corrected by §3b review):** Single-source `corrupted:true` (→ criticality-matrix canonical); dispatch-protocol *narration* (→ fanout.md) **while keeping each entry point's runnable `model=$(cortex-resolve-model …)` + `model:` bind in place per `fanout.md:37`**; backend write-back routing shape (→ one source, fields supplied per site — **preserve site-specific quirks like `:171`'s empty-`--areas` clearing**). Preserve the **three** distinct model-resolution contracts (criticality-keyed+halt / synthesizer no-criticality+halt / searcher degrade-loud). *Acceptance:* **no existing test covers this — add a static wiring test** pinning each call site's `--role`/`--criticality`-presence/halt-vs-degrade shape and each rule's single-source-plus-citation structure; `just test` green. **Manual invariant** (not test-caught, per the `test_*_wired` pattern's own disclaimer that runtime under-trigger is unassertable): the per-site runnable bind must survive the narration collapse.
- **R9 — Phase 4:** Trim description synonyms to one-trigger-per-branch across the five skills. Respect `skill_trigger_phrases.yaml` pins; keep the lifecycle mirror-regen note unless relocated. *Acceptance:* `test_l1_surface_ratchet` (equal-or-lower passes) + the routing fixture green.
- **R10 (invariant) — all phases:** No intended change to lifecycle control flow or gate behavior. *Acceptance:* every phase ends with `just build-plugin` clean + `just test` fully green; the wrapped lifecycle→refine path is byte-reduced at behavior parity.

## Non-Requirements

- Relocating the §4 gate; delta-refactoring the two `clarify.md` files; renaming `criticality`/`complexity` fields+CLI; changing "materially weak". (All dropped on scrutiny — see research.md.)
- **`implement.md §1a` pruning (R3)** — dropped: ~zero recoverable fat (bytes are pinned Step v tokens) vs. unconditional test-failure risk. Do not touch §1a in this lifecycle.
- The `cortex-check-skill-path` lint blind-spot fix — separate follow-up ticket, not this lifecycle.
- Re-doing the four fixes already applied inline before this lifecycle (stale phase name at `discovery/references/research.md:112`; softened angle count at `critical-review/SKILL.md:46`; `(sonnet)` removal at `research/SKILL.md:190` + `discovery/references/research.md:43`) — done, mirrors regenerated, tests green.

## Edge Cases

- **Fixture-pinned phrases** — `skill_trigger_phrases.yaml` mandates several lifecycle description phrases; R9 trims only the free ones.
- **fresh-eyes / Anchor-checks collision** — `critical-review/SKILL.md:99` "Anchor-checks" means the good/evidence sense; the leading word must not overwrite it.
- **Three model-resolution contracts** — collapsing (ii) synthesizer into (i) criticality-keyed would break standalone critical-review (no lifecycle state to read).
- **Dual-source mirror** — canonical edits under `skills/` require `just build-plugin`; a missed regen fails `test_dual_source_reference_parity` / `test_plugin_mirror_parity`.
- **kept-pauses parity** — large insertions/deletions in `specify.md` or `refine/SKILL.md` can breach the ±35-line tolerance; keep edits local.

## Changes to Existing Behavior

None intended for the wrapped (lifecycle→refine) path. The **only** deliberate behavior change is Bug 1: standalone `/cortex-core:refine` in an off-repo consumer goes from broken (skipped/hallucinated gates) to working. Everything else is byte reduction and single-sourcing at behavior parity.

## Technical Constraints

- **ADR-0009** — reference paths resolve in the SKILL.md body and propagate; no bare-relative or `../` paths in reference files. Bug fixes must honor this.
- Test-pinning surface — `just test` every phase. §3b review surfaced pinned tests the research Risk map missed: `test_lifecycle_step_v_ordering.py`, `test_lifecycle_enterworktree_callsites.py`, `test_implement_worktree_interactive_contract.py` (all pin `implement.md §1a` — R3); `test_refine_skill.py` (pins the `(Recommended)` format string — R6); `test_dispatch_template_placeholders.py` (R4, needs extension). Two **new** tests are in scope: R8's model-resolution/single-source wiring test, and R4's research/SKILL.md placeholder coverage.
- **L1 surface ratchet** (`test_l1_surface_ratchet.py`) — description trims must not regrow budget; critical-review sits at its 795B cluster ceiling.

## Open Decisions

- **Batching (resolved, recommend):** one plan, tasks ordered R1→R2 then R4→R9 (R3 dropped), each its own `just test` gate. Rejected: splitting bugs into a separate lifecycle (heavier ceremony, same files).
- **How-pruning minimums (resolved, recommend):** preserve *What decision + when it fires + option set*; cut *step-by-step method, exact label/format strings, tool-internal diagnostics*. This is the concrete reading of "prescribe What/Why, not How" for R6 (and the delete-not-prune boundary for R5). Note the R6 carve-out: user-visible output strings like `(Recommended)` are contract, not How — do not cut them.

## Proposed ADR

None. This applies existing principles (ADR-0009 path resolution, "prescribe What/Why not How", single-source-of-truth) rather than introducing a new architectural decision. The coined leading words (`tier ratchet`, `fresh-eyes`) become canonical vocabulary but do not warrant an ADR.
