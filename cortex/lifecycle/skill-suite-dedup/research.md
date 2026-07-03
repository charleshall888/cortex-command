# Research: skill-suite-dedup

## Problem Statement

The lifecycle skill constellation (lifecycle, refine, critical-review, research, discovery) carries verbosity/bloat from AI authorship, plus two latent path-resolution bugs. This is part of the active skill-leanification campaign: make the core skills lean while preserving behavior. Evaluate edits by **fat cut**, not "does behavior change."

## Method

Produced by a multi-analyst study through Matt Pocock's `writing-great-skills` framework (leading words, progressive disclosure, single-source-of-truth, sediment, sprawl, no-ops, completion criteria), followed by deterministic grep/read verification of every falsifiable claim, then an independent Fable second-review that corrected the bucketing and surfaced the test-pinning risk map. Findings below are the *verified* survivors; over-reach was cut on scrutiny (see Dropped).

## Findings

### Bugs (correctness — fix first, risk-bearing)

- **Bug 1 — refine standalone path-resolution gap (off-repo breakage).** `specify.md:149/153/164` tell the agent to resolve `orchestrator-review.md` and `critical-review-gate.md` via *"lifecycle SKILL.md's Reference-path propagation manifest"*, but refine's own `SKILL.md` never resolves those two targets — only lifecycle's body does (`SKILL.md:139-156`). Wrapped by lifecycle it works; **standalone refine breaks off-repo** (CWD-relative), skipping or hallucinating the orchestrator-review and critical-review skip-gates. `criticality-matrix` is saved only by refine `SKILL.md:146`'s direct resolution; the other two have no rescue. Verified by grep: refine SKILL.md has zero mentions of those two targets. This is the exact failure ADR-0009 exists to prevent.
  - **Fix:** add both targets to refine SKILL.md's Step 5 adaptation block as body-resolved `${CLAUDE_SKILL_DIR}/../lifecycle/references/{orchestrator-review,critical-review-gate}.md` paths (mirror the `:146` pattern), and reword `specify.md:149/153/164` to "the propagated `<target>` path" without naming lifecycle's manifest — so both callers satisfy it.

- **Bug 2 — discovery `research.md:104` bare-relative path.** `references/orchestrator-review.md` is a bare-relative path pointing at discovery's *own* orchestrator-review delta file (not the lifecycle canonical). Determine whether it's a genuine bare-path smell (should be body-resolved + propagated via discovery SKILL.md's sibling-path-propagation section) or intentional, and fix consistently. Smaller blast radius than Bug 1, same failure class.

(Two other bug fixes — the stale "proceed to Specify" phase name at discovery `research.md:112`, and the softened angle count at critical-review `SKILL.md:46` — plus removal of hardcoded `(sonnet)` model annotations at `research/SKILL.md:190` and `discovery/references/research.md:43` were **already applied inline** before this lifecycle, mirrors regenerated, tests green. Do not redo.)

### Fat cuts (prescribe What/Why not How — the largest AI-bloat, measured bytes)

Ranked by size: `implement.md §1a` interactive worktree-entry How (~6571B — prune the How, relocate the branch-only remainder behind the worktree pointer); `research/SKILL.md:73-178` angle-prompt roster (~3949B — disclose the *conditional* Adversarial/Tradeoffs templates, keep the always-fired core inline); `decompose.md:95-114` LEX-1 regex spec (~2353B — keep the rule + 1-2 examples, delete the tool-maintainer regex detail); `refine/SKILL.md:147` §4 complexity/value gate (~1493B procedural How — **prune in place, do NOT relocate**: sole consumer is refine, solution-horizon says leave the home).

### Leading words (recruit strong PRETRAINED words to collapse restatement)

Endorsed by `GLOSSARY.md:134` ("reach for an existing word first"); the sin is *invention* (e.g. `corner-anchored`), not reuse. Candidates: **tier ratchet** for the seed→reconcile→gate invariant (restated at `refine/SKILL.md:58,135-138`, `specify.md:162`, `seed-reconcile-gate-ordering.md`; "ratchet" already appears); **fresh-eyes** for critical-review's no-anchoring concept (`SKILL.md:18,36,99` — WATCH the collision: `:99` "Anchor-checks" means the *opposite/good* sense); collapse the "don't be balanced" adversarial triads (`clarify-critic.md:46,82,95`; reviewer/fallback/synthesizer prompts) onto the already-established **adversarial** token.

### Single-source dedup (delete the copies, keep the binds)

- `corrupted:true` rule — 4 sites (`critical-review-gate.md:7`, `criticality-matrix.md:30`, `orchestrator-review.md:9`, `refine/SKILL.md:146`) → make `criticality-matrix` canonical, others cite it.
- Dispatch-protocol narration — `research/SKILL.md:180-192` + `discovery/references/research.md:37-45` re-narrate `fanout.md` → point to it, keep only the runnable bind each entry point must carry per `fanout.md:37`.
- Backend-gated write-back 3-arm routing — `refine/SKILL.md:71-79` and `:161-173` (`clarify.md:87` already names Step 3 "the canonical copy") → extract the routing shape, call sites supply their fields.
- Model-resolution — **THREE distinct contracts must be preserved**: (i) criticality-keyed + halt (`implement.md:165`, `review.md:22`, `orchestrator-review.md:45`, `competing-plans.md:16`); (ii) synthesizer no-criticality + halt (`competing-plans.md:61`, `critical-review/SKILL.md:70`); (iii) searcher degrade-loud, never halts (`research/fanout.md:32`). Do NOT collapse (ii) into (i) — breaks standalone critical-review.

### Description synonym trims (one-trigger-per-branch)

lifecycle, refine, critical-review, research, discovery descriptions carry 6-11 synonyms for one branch. **Fixture-constrained** — `tests/fixtures/skill_trigger_phrases.yaml` pins several lifecycle phrases; trim only the free ones. The lifecycle description's mirror-regen maintenance note is trimmable only if relocated (it is governance-load-bearing ambient context).

## Dropped on scrutiny (do NOT do)

- Relocating the §4 gate — behavior-neutral, sole consumer; solution-horizon says leave the home (prune in place instead).
- Delta-refactoring the two `clarify.md` files — they legitimately diverge (share only 6 lines).
- Renaming `criticality`/`complexity` fields+CLI — ripples into backlog frontmatter on every item + CLI flags; cost ≫ benefit. A prose-only disambiguation note in `criticality-matrix.md` is the cheap alternative if wanted.
- Changing "materially weak" at `orchestrator-review.md:21` — reviewer judgment, consistent with prescribe-What-not-How; leave unless an observed failure shows miscalibration.

## Risk map (test-pinning surface — the real hazard)

`test_lifecycle_kept_pauses_parity` (±35-line tolerance, sweeps `skills/refine/` too), `test_critical_review_gate_nonlocal_failsafe` (pins `specify.md §3b` heading + backend-read ordering), `test_competing_plans_wired`, `test_refine_reconcile_wiring`, `test_dual_source_reference_parity` + `test_plugin_mirror_parity` (run `just build-plugin` after canonical edits), `test_l1_surface_ratchet`, the routing fixture. **Every edit batch ends with `just test`.**

## Follow-up (separate ticket, not this lifecycle)

`cortex-check-skill-path` lint blind spot — it does not catch "consult the manifest" phrasing naming a manifest the invoking skill does not have (Bug 1's root enabler).

## Open Questions (for Spec)

- Batching/sequencing: one plan with risk-first → fat-first task ordering, or split bug-fixes from the leanification refactor into separate approval surfaces?
- How aggressive on the How-pruning of `implement.md §1a` and the §4 gate — what is the minimum What/Why that must survive each cut?
- Leading-word rollout: coin `tier ratchet` and `fresh-eyes` in this lifecycle, or gate them behind a lighter-touch dedup-only pass first?
