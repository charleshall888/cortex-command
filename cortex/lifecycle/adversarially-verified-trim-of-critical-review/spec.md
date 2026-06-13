# Specification: adversarially-verified-trim-of-critical-review

## Problem Statement

The critical-review skill's reference files carry load-bearing contract text — the A→B rubric inlined into every Opus synthesizer dispatch, the exit-code route reactions the orchestrator follows, and a total-failure user-facing string with no Python source-of-truth — yet **no static gate protects any of it**: `tests/test_skill_section_citations.py` covers only the lifecycle references, and a careless edit to these files breaks nothing detectably while silently degrading review quality. The byte-trim the ticket asked for is real but small (~19.8KB surface, on-demand loads, conservative safe-trim well under 1.5KB — below the prior trim feature's ≥30KB value bar).

So this feature's value is **a regression-detection gate plus a worked, recorded trim pass over the highest-risk file** — not the byte count. Three honest scope limits, stated up front because critical-review flagged earlier drafts for overclaiming them:

- **The gate is narrow.** It pins the enumerated literals/designators in `verification-gates.md` and the SKILL.md total-failure string. It does **not** cover `a-to-b-downgrade-rubric.md` (the file the research ranks as *most* dangerous to edit — left unpinned and untrimmed this round), `residue-write.md`, or `angle-menu.md`.
- **The gate detects string-regression, not behavioral equivalence.** A green pin proves the pinned literals/designators are still present (catches deletion, rename, paraphrase of *pinned* strings). It does **not** prove the orchestrator still reacts identically to exit 3/4 — that residual risk is handled by a one-time hand-diff (R8), not the static gate.
- **The methodology is recovered, not invented.** The trim-map schema and the adversarial-verifier pattern come from the prior `harness-token-efficiency-trim` feature; this feature *applies and extends* them to the critical-review family. "Adversarial" here means "challenged by a fresh adversarial pass," not "certified by a fully independent verifier" (the verifier is the same agent-class, or `/cortex-core:critical-review` itself).

The operator chose this reframe explicitly over a bytes-first trim, a full behavioral-eval build, and dropping the ticket.

## Phases

- **Phase 1: Anchor** — add a regression-detection test pinning the load-bearing literals/designators in `verification-gates.md` + the SKILL.md total-failure string, so edits that delete/rename/paraphrase them fail loudly. Independently shippable; the primary deliverable.
- **Phase 2: Verified trim** — run a recorded adversarial trim pass over `verification-gates.md` and apply only the verifier-certified-safe subset (possibly empty), under the Phase-1 gate and all existing gates.

## Requirements

1. **Pin the total-failure literal.** A test asserts the exact string `All reviewers excluded — drift or Read failure detected; critical-review pass invalidated. Re-run after resolving concurrent write source.` appears verbatim in BOTH `skills/critical-review/SKILL.md` and `skills/critical-review/references/verification-gates.md`. Acceptance: `grep -Fc "All reviewers excluded — drift or Read failure detected; critical-review pass invalidated. Re-run after resolving concurrent write source." skills/critical-review/SKILL.md` = 1 AND same for `…/references/verification-gates.md` = 1; the test fails if the literal is removed/paraphrased from either file (verify by a scratch edit, then revert). **Phase**: Anchor

2. **Pin the verification-gates.md preserve-set designators.** The same test (or sibling) asserts presence of the route-reaction preserve-set in `verification-gates.md`: the exit-0/exit-3/exit-4 reaction markers for both `check-artifact-stable` and `check-synth-stable`, and the section designators (`Step 2a.5`, `Step 2c.5`, `Step 2d.5`) the four `skills/critical-review/SKILL.md` pointers depend on. Acceptance: test asserts each designator/marker string is present; renumbering or deleting any one fails the test. **Known limitation (state in the test docstring):** this guards token *presence*, not the surrounding reaction *prose* — a paraphrase of an unpinned reaction sentence can still pass; R8 covers that residual behavioral risk. The exact pinned-string set is enumerated from research.md's PRESERVE-SET (Plan finalizes the list). **Phase**: Anchor

3. **Wire the pin test into the suite, green on the pre-trim tree.** Acceptance: `just test` exits 0 with the new/extended test discovered and passing, *before* any Phase-2 trim is applied (proves the pinned literals/designators are present in the current content — not that the file is behaviorally frozen). **Phase**: Anchor

4. **Run and record an adversarial trim pass over `verification-gates.md`.** Use the recovered methodology (research.md §Prior-Feature Methodology Recovery): a per-proposal record with `section` (heading+line range), `kind`, `action` (remove/condense/move), `est_savings_bytes`, `risk`, `excerpt`, `verifier_reason`, and `verdict ∈ {safe, downgraded, refuted}`. The verifier (a re-composed auditor/refuter pass, or `/cortex-core:critical-review` as the in-repo adversarial analogue) **independently assigns every verdict** with a concrete `verifier_reason`. Commit a lightweight artifact at `cortex/lifecycle/adversarially-verified-trim-of-critical-review/trim-map.md`. Acceptance: file exists, non-empty; every proposal carries a verdict + non-empty `verifier_reason`; the tempfile-guard paragraph (the "concurrent runs corrupt each other's stdout" / "stale leftovers trip the Write tool's guard" passage) and both exit-4 benign-skip rationales (Step 2c.5 and Step 2d.5) each appear as evaluated proposals (not silently dropped). The research-derived prior expects these to land `refuted`/`downgraded`, but R4 does **not** mandate the verdict value — safety for them is enforced structurally by R5+R6, not by pre-writing the answer. **Phase**: Verified trim

5. **Apply only the verifier-certified safe + downgraded-per-downgrade proposals.** Refuted proposals are NOT applied. Acceptance: after the trim, `grep -c` confirms the tempfile-guard passage (both named failure modes) and both exit-4 rationales remain present in `verification-gates.md`; net byte change is `≥ 0` and equals exactly the certified safe+downgraded subset applied. **A zero-byte result is a valid, passing outcome** (the gate + recorded trim map are the deliverable) — the applied set MUST NOT be padded to force a reduction. **Phase**: Verified trim

6. **Preserve-set survives verbatim; out-of-scope files untouched.** Acceptance: (a) E101 contract lint passes on the edited files (`cortex-check-contract --staged` / the `just` contract recipe exits 0) — the two fenced invocations keep all required flags (`check-artifact-stable` 5 flags, `check-synth-stable --feature --expected-sha`); (b) `git diff --stat` shows `a-to-b-downgrade-rubric.md`, `residue-write.md`, `angle-menu.md` with 0 changed lines (canonical and mirror); (c) Phase-1 pin test (R1–R2) exits 0 post-trim. **Phase**: Verified trim

7. **Commit canonical + regenerated mirror together; dual-source parity green.** Acceptance: after `just build-plugin`, `git status` shows the `plugins/cortex-core/skills/critical-review/references/verification-gates.md` mirror staged alongside the canonical edit; `python -m pytest tests/test_dual_source_reference_parity.py` exits 0; the pre-commit drift hook passes (no "dual-source drift detected"). **Phase**: Verified trim

8. **No route-table↔Python drift introduced (one-time hand-diff).** Any condensed exit-code prose is hand-diffed against `cortex_command/critical_review/__init__.py` exit constants (0/2/3/4 semantics). Acceptance: an `implementation-notes.md` entry records the hand-diff result; the prose route reactions for exit 3/4 still match the Python emitter behavior (exit 3 = excluded/do-not-surface; exit 4 = benign-skip/no-event). **Acknowledged limitation:** this is a one-time author check scoped to *this* change, not a re-runnable gate; a durable prose↔Python route-consistency test is a noted follow-up (Non-Requirements), not built here. **Phase**: Verified trim

9. **No new MUST escalations; frontmatter byte-count unchanged.** Acceptance: `python -m pytest tests/test_l1_surface_ratchet.py` exits 0 (critical-review frontmatter stays 795B); the diff introduces no new `MUST`/`CRITICAL`/`REQUIRED` token (`git diff` review), or if one is unavoidable it carries the #91-policy evidence artifact in the commit body. **Phase**: Verified trim

10. **Full suite green.** Acceptance: `just test` exits 0 on the final tree. **Phase**: Verified trim

## Non-Requirements

- **No trim to `a-to-b-downgrade-rubric.md` (rubric untouched this round).** Its cuts require an A/B behavioral eval the operator declined to build now; the inlined rubric is left byte-for-byte unchanged AND is not covered by the Phase-1 gate.
- **No trim to `residue-write.md` or `angle-menu.md`, and no gate coverage for them.** Combined <8% of realized leverage; left as-is and unpinned.
- **No A/B behavioral synthesizer eval built or run.** Verification this round = the Phase-1 static (string-presence) gate + the adversarial trim-map verifier pass over `verification-gates.md` + the R8 one-time hand-diff.
- **The tempfile-guard paragraph and both exit-4 rationales are NOT removed** (the adversarial research pass refuted these cuts — load-bearing Why, distinct untested transitions; the Phase-2 verifier re-confirms independently).
- **No fixed/aggressive byte target; a zero-byte applied trim is acceptable.** The applied trim equals exactly what the verifier certifies safe.
- **No durable prose↔Python route-consistency gate** built this round (R8 is a one-time hand-diff) — noted as a sensible follow-up.
- **Not hoisting the total-failure string into a Python constant.** Follow-up; the Phase-1 pin mitigates the immediate fragility.
- **No `skills/critical-review/SKILL.md` content changes** beyond pointer integrity if a `verification-gates.md` heading is renumbered.

## Edge Cases

- **A trim renumbers/renames a `verification-gates.md` Step heading a SKILL.md pointer relies on** → Phase-1 pin test (R2) fails; update the citing pointer in the same change before the trim lands.
- **A trim paraphrases an unpinned exit-3/4 reaction sentence** → the static pin does NOT catch this (known limitation, R2); the R8 hand-diff is the backstop. If the paraphrase changes meaning, R8 reverts it.
- **Mirror not regenerated before commit** → pre-commit drift hook blocks ("dual-source drift detected"); run `just build-plugin` and stage canonical+mirror together (per MEMORY drift-hook coupling).
- **Verifier certifies a near-zero or zero safe pool** → Phase 2 ships the trim-map artifact documenting "nothing further safe to cut"; net change may be zero (R5 allows it). The feature still delivers Phase 1. Honest reporting required — do not manufacture cuts.
- **E101 false-trip on an illustrative invocation introduced during a rewrite** → wrap with `<!-- contract-lint:ignore-next -->` or keep templated `<…>` placeholders.

## Changes to Existing Behavior

- **ADDED**: a string-regression test guarding `skills/critical-review/references/verification-gates.md` + the SKILL.md total-failure literal — new test surface in `tests/`, extending the `test_skill_section_citations.py` precedent to (part of) the critical-review family.
- **MODIFIED**: `skills/critical-review/references/verification-gates.md` (+ its `plugins/cortex-core` mirror) shrinks by the certified-safe How-narration subset (possibly empty); orchestrator-observable behavior unchanged (preserve-set intact, R8 confirms route prose).
- **No behavioral change** to the critical-review skill's runtime contract, the inlined rubric, residue-write, or angle-menu.

## Technical Constraints

- **Dual-source mirror**: edit canonical only; `just build-plugin` regenerates `plugins/cortex-core/skills/critical-review/references/`; commit canonical+mirror together (drift hook + `test_dual_source_reference_parity.py`).
- **E101/E102 contract lint** (`cortex_command/lint/contract.py`, pre-commit Phase 1.55): keep required flags in the two fenced invocations; don't rename console scripts (`cortex-critical-review`, `cortex-critical-review-resolve-feature`, `cortex-critical-review-write-residue`).
- **L1 ratchet** (`test_l1_surface_ratchet.py`): frontmatter-only, critical-review at 795B zero-headroom — do not touch frontmatter.
- **Skill-path lint SP001/SP002**: introduce no `${CLAUDE_SKILL_DIR}` token or bare-relative Read path into the reference files (none present today).
- **Byte-accounting**: canonical `skills/` paths only (mirrors excluded — mechanically regenerated); before = `git cat-file -s origin/main:<path>`, after = `wc -c`.
- **Pre-commit gate order on `skills/*` edits**: parity → contract(E101) → events-registry → prescriptive-prose → bare-python(L201) → skill-path(SP001/SP002) → build-plugin mirror+drift. Only E101 carries a live non-trivial pin on these files.
- **The total-failure literal has no Python fallback** — it is the canonical user-facing string for the all-excluded case; treat as frozen (R1 enforces this). The synth-drift string, by contrast, IS Python-anchored (`critical_review/__init__.py`).

## Open Decisions

- **Pin-test mechanism and exact pinned-string set** (R2): whether to generalize `test_skill_section_citations.py`'s hardcoded `REFERENCES_DIR` to cover both dirs or add a sibling `tests/test_critical_review_reference_pins.py`, and the precise minimal preserve-set list to pin. Deferred to Plan — *reason*: the choice depends on reading the test's current extensibility and selecting the smallest pin set that still catches a renumber/paraphrase, which is best decided while editing the test. The total-failure-literal pin (R1) is a must-have regardless of mechanism.

## Proposed ADR

None considered.
