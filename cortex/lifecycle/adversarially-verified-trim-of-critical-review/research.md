# Research: Adversarially-verified trim of critical-review reference files

**Clarified intent (scope anchor):** Produce adversarially-verified trim maps for the four in-scope critical-review reference files (`verification-gates.md`, `a-to-b-downgrade-rubric.md`, `residue-write.md`, `angle-menu.md`) and apply the safe subset, shrinking the orchestrator's per-run token cost without breaking critical-review's load-bearing contracts (exit-code routes, verbatim-dispatch prompts, the inlined A→B rubric, E101-enforced flags, registered event shapes).

**Tier/criticality:** complex / high. **Mode:** lifecycle (refine).

> **Headline correction the research confirmed:** the ticket's premise is overstated. The four in-scope files total **19,762B (~19.3KB)**, not "~45KB" (the 45KB figure swept in the ~11KB of hard-excluded verbatim-dispatch prompts). Loads are **on-demand and conditional**, not eager. The realized leverage is heavily concentrated, and the conservative safe-trim (~1,700–2,700B) is a small fraction of the prior feature's value bar. See **Open Questions** — these are decisions for Spec, not settled facts.

---

## Codebase Analysis

### Files that change (canonical + mirror — dual-source)

Every edit touches a **canonical** source under `skills/critical-review/references/` AND its **auto-generated mirror** under `plugins/cortex-core/skills/critical-review/references/`. Confirmed byte-identical today (`diff -q`).

| File | Canonical (B) | Mirror |
|---|---|---|
| verification-gates.md | 10,565 | plugins/cortex-core/skills/critical-review/references/verification-gates.md |
| a-to-b-downgrade-rubric.md | 5,307 | (mirror) |
| residue-write.md | 2,276 | (mirror) |
| angle-menu.md | 1,614 | (mirror) |

Also touched: `skills/critical-review/SKILL.md` (pointer integrity only — 114 lines, far under the 500-line cap). `bin/.events-registry.md` (event shapes — see Contract-Preservation; no markdown change required there).

### Per-file load sites (all in `skills/critical-review/SKILL.md`, form `${CLAUDE_SKILL_DIR}/references/<file>.md`)

- **verification-gates.md** — pointed-to at **4** distinct steps, each "consult for contract" (not a whole-file inline): SKILL.md:48 (Step 2a.5 invocation contract + exit routing), :64 (Step 2c partial-failure coverage rule), :72 (Step 2c.5 route table + record-exclusion contract + Phase-2 schema), :86 (Step 2d.5 invocation contract + resolution).
- **a-to-b-downgrade-rubric.md** — Step 2d (SKILL.md:76): a literal `Read` **and** full substitution into `{a_to_b_rubric}` inside the dispatched Opus synthesizer prompt (`synthesizer-prompt.md:35-37`). **Double cost per run** (orchestrator context + dispatched prompt). Structurally in the SAME category as the three excluded prompt files: **cannot be pointer-replaced** — the fresh Opus agent cannot resolve a skill-dir path.
- **residue-write.md** — Step 2e (SKILL.md:92), conditional on reaching residue write.
- **angle-menu.md** — Step 2b (SKILL.md:54), on-demand pointer; Step 2b already states the angle-count rule and distinctness criteria inline.

### Mirror mechanism & commit coupling

`just build-plugin` (justfile:585) does `rsync -a --delete "skills/$s/" "plugins/cortex-core/skills/$s/"` (critical-review is in the manifest). `.githooks/pre-commit` (enabled by `just setup-githooks`): editing any `skills/` path sets `BUILD_NEEDED=1`, runs `just build-plugin`, then `git diff --quiet -- plugins/cortex-core/` — **commit fails with "dual-source drift detected" if the mirror isn't regenerated and staged**. Per MEMORY `feedback_drift_hook_shared_checkout_coupling`: on `main`, run build-plugin with the canonical-edit commit and stage canonical+mirror together.

### Lifecycle auto-trigger path

`skills/lifecycle/references/critical-review-gate.md` is the **skip-decision** file (consulted at Specify §3b and Plan §3b). **Run** when `tier=complex` AND `criticality ∈ {medium,high,critical}` → the full critical-review skill runs at **both** phases (`specify.md:169`, `plan.md:267`). Simple → skip-silent; complex+low → log+skip (`lifecycle_critical_review_skipped`). So references load across **2 runs per qualifying lifecycle**.

### Conventions to follow
Keep all reference pointers as `${CLAUDE_SKILL_DIR}/references/<file>.md` resolved in the SKILL.md body; never push a `${CLAUDE_SKILL_DIR}` token or a `see other.md` pointer into a dispatched prompt body. Preserve named sections the four SKILL.md pointers promise. `plan.md:83-87` externally cites the Phase-2 envelope-extraction wording (by mirror path) — don't invalidate it.

---

## Web Research

**No off-the-shelf framework exists** for "adversarially-verified text-level trimming of an agent skill's instruction files while preserving load-bearing contract text." The approach is grounded by *composition* of four adjacent bodies:

1. **Context engineering** — Anthropic, *Effective context engineering for AI agents*: strive for "the minimal set of information that fully outlines your expected behavior" ("minimal does not necessarily mean short"); curate "diverse, canonical examples," avoid "a laundry list of edge cases." No numeric example count.
2. **Prompt regression / eval-driven iteration (strongest transferable evidence)** — *When "Better" Prompts Hurt* (arXiv 2601.22025): prompt edits are **non-monotonic** — a generic wrapper improved instruction-following +13% while degrading extraction −10% and RAG compliance −13% on Llama 3 8B; "degradation comes from generic rules conflicting with task-specific constraints." Practice: version-controlled golden set, automated assertions for format/required-fields/prohibited-content + semantic/judge checks; "iterate within the evaluation loop, not by intuition." Reinforced by testRigor (prompt drift), Braintrust (golden sets with adversarial inputs), Evidently/eugeneyan (LLM-as-judge for behavioral diff, ~85% pairwise alignment).
3. **Prompt compression** — gist tokens (arXiv 2304.08467), Behavior-Equivalent Token (2511.23271), LongLLMLingua: behavioral-equivalence *framing* transfers; the *methods* are model-internal/learned-embedding, not human-readable file editing.
4. **Intent engineering ("What/Why not How")** — productcompass / pathmode echo the principle ("define the goal and criteria for success… the model has more latitude") but are practitioner blogs, **not empirical**. Few-shot saturation: soft consensus plateau ~5–7 examples, but saturation is task-dependent (harder structured-extraction tasks saturate at 20–30) — "8 can be cut to 4" is defensible for simple demonstrations but **must be verified per-skill, not assumed**.

**Load-bearing caveat:** the two claims most central to this work — (a) procedural "How" narration is safely trimmable for capable models, and (b) the specific text being cut is redundant rather than load-bearing — are **not externally validated**. Prior art justifies the *method*; it does not pre-certify any individual trim. The non-monotonicity result is the strongest argument for keeping the adversarial verification step and for testing behaviors the trim did *not* target.

---

## Requirements & Constraints

**Iterative trimming is sanctioned:** `project.md:53` "Maintainability through simplicity: Complexity is managed by iteratively trimming skills/workflows"; `project.md:96` "Workflow trimming… Retirements in CHANGELOG.md" (note: *wholesale retirement* is the CHANGELOG-logged action; trimming reference content within a kept skill is lighter and doesn't trigger that ceremony).

**Authoring principles that govern the trim:**
- **What/Why-not-How** (CLAUDE.md): procedural How-narration is the prime trim target; **decision criteria and intent are load-bearing and must survive**.
- **Skill/phase authoring** (CLAUDE.md): before classifying a boundary as ceremonial and removing it, identify the affordance it protects; if internals already enforce it, document that reasoning explicitly. Prefer structural over prose-only enforcement.
- **MUST-escalation policy** (#91 / epic #82 / audit #85): do **not** add new MUST/CRITICAL/REQUIRED without an evidence artifact + effort=high(/xhigh) dispatch record; pre-existing MUSTs grandfathered; default to soft positive-routing if rewriting imperative phrasing.
- **Solution horizon**: a scoped phase of a multi-phase lifecycle is not a stop-gap; durable-vs-simple per current knowledge.

**Architectural constraints / enforcement gates (with exact pins):**
- **L1 surface ratchet** (`tests/test_l1_surface_ratchet.py`, `bin/cortex-measure-l1-surface`): measures **frontmatter only** (`description`+`when_to_use`). critical-review baseline = **795B, current = 795B — zero headroom**. Trimming reference *bodies* does nothing for the ratchet; the trim must **not add a single frontmatter byte**. (Reference files are entirely out of ratchet scope.)
- **SKILL.md size cap** 500 lines (`test_skill_size_budget.py`) — not binding (SKILL.md is 114 lines).
- **Dual-source parity** (`tests/test_dual_source_reference_parity.py`): byte-identical canonical↔mirror, one case per reference file; failure → "run `just build-plugin`."
- **E101/E102/E103 contract lint** (`cortex_command/lint/contract.py`, pre-commit Phase 1.55): the **only live, non-trivial static pin** on the in-scope files. In `verification-gates.md` the fenced invocations must keep all required flags: `check-artifact-stable --feature --reviewer-angle --expected-sha --model-tier --input-file` (5) and `check-synth-stable --feature --expected-sha` (2). `prepare-dispatch` has no required flags. Placeholders `<...>`/`{...}` are exempt. E102 = unknown flag (don't rename/mistype). Suppress illustrative invocations with `<!-- contract-lint:ignore-next -->`.
- **Skill-path lint SP001/SP002** (ADR-0009): the four non-prompt files only trigger D1 inside explicit `<!-- BEGIN/END SUBAGENT PROMPT -->` fences; D2 fires on bare-relative `references/…`/`../…`/`skills/…` in Read/bash context unless `${CLAUDE_SKILL_DIR}/`-prefixed. **Verified: none of the four files currently contain `${CLAUDE_SKILL_DIR}` tokens or bare-relative Read paths** — a trim won't trip SP001/SP002 unless it introduces one.
- **Bare-python lint (L201)**: none of the four files contain `python3 -c/-m cortex_command` — no risk.
- **Events `sentinel_absence`/`synthesizer_drift`** (`bin/.events-registry.md:113-114`, `scan_coverage: manual`): emitted from **Python** (`cortex_command/critical_review/__init__.py`), not markdown. The events-registry static gate scans `skills/**/*.md` for `"event": "<name>"` JSON literals only — **none exist in these files** (the mentions are prose). No orphaning risk; but don't sever the SKILL.md gate-flow steps (2a.5/2c.5/2d.5/2e) that drive the Python emitters.

---

## Prior-Feature Methodology Recovery

Prior feature: **`harness-token-efficiency-trim`** (PR #19, merged 2026-06-10, v2.25.x). Durable artifacts at `cortex/lifecycle/harness-token-efficiency-trim/` — **`evidence.json` is the machine-readable source of truth** (the /tmp workflow outputs did not survive). Ticket 300 is its **R8(c) deferral** (research F8: critical-review references "have no trim maps; building them mid-lifecycle would inflate this feature"). Siblings: 298 (L1 cap policy), 299 (research/SKILL.md trim + R2-PARTIAL canonicalizations), 301 (Option-C metrics reducer).

**Recovered trim-map artifact shape** (`evidence.json → trims_verified`, a list of per-file objects):
```
{ "file", "keep_rationale" (the file's exclusion list),
  "safe_proposals":[…], "downgraded_proposals":[…], "refuted_proposals":[…],
  "safe_savings_bytes" }
```
Each **proposal**: `section` (heading + line range), `kind` (`duplicated-boilerplate | redundant-example | maintainer-rationale | adr-recap | How-narration | duplication`), `action` (`remove | condense | move-to-adr-or-doc`), `est_savings_bytes`, `risk` (low/med/high), `excerpt` (text to cut), `notes` (co-edit warnings), `verifier_reason` (adversary's verdict with concrete anchors), `downgrade_to` (safer substitute, downgraded only).

**Verification procedure (two-pass adversarial):**
1. Per-file **trim auditor** → immediately followed by a dedicated **"refute every cut" verifier** sub-agent.
2. A proposal is **safe** only if the verifier **cannot cite a concrete breakage anchor** (test substring pin w/ file:line, parity-line math, grep proving no consumer, dispatched-verbatim zone, recorded decision). Three verdicts: **safe** (apply verbatim) / **downgraded** (apply the narrower `downgrade_to`, usually condense-not-remove) / **refuted** (skip). A `refuted` with `verifier_reason:"no verdict returned"` = null/timeout, conservatively skipped (`skipped:no-verdict`). Prior realized: 48,934B proposed → 36,539B approved safe, 36 downgraded, 2 refuted.

**Byte-accounting:** before = `git cat-file -s origin/main:<path>` (returns 0 for new files); after = `wc -c`. **Canonical `skills/` only; mirrors excluded** (mechanically regenerated → would double-count). `safe_savings_bytes` treated as a **floor, not a two-sided bound**. Disposition ledger labels every proposal (`applied | applied-per-downgrade | skipped:no-verdict | skipped-with-reason | moved:<dest>`); close-out asserted **zero undispositioned proposals**. Mandatory **citation sweep** (R6f), later mechanized as `tests/test_skill_section_citations.py`.

**Prior accept floor: ≥30,000B net** (realized 40,169B / 19.2%). ← critical for the value question below.

**Gaps that must be decided fresh:** (1) no critical-review trim map exists — build from scratch using the recovered schema; (2) the auditor/verifier sub-agent prompt text was **not preserved** (lived in workflow runs) — re-compose, or use `/cortex-core:critical-review` itself as the in-repo adversarial analogue; (3) the critical-review-specific anchors must be **re-inventoried with fresh line numbers**; (4) no analogue for the "loaded twice + rubric-inlining" weighting — decide whether to report raw bytes (prior convention) or dispatch-weighted savings.

---

## Realized Per-File Leverage

Assumptions: tokens ≈ bytes/4; qualifying lifecycle runs critical-review 2× (Specify+Plan); 1 synthesizer/run; a-to-b inlining = read(1)+dispatch(1) = 2× when synthesis fires.

| File | tok/load | realized cost/qualifying lifecycle | leverage (tok saved / 10% trim) |
|---|---|---|---|
| **verification-gates.md** | 2,641 | ~10,564 (band 5.3k–15.8k) | **~1,056 — CLEAR TOP** |
| **a-to-b-downgrade-rubric.md** | 1,326 | ~5,304 (2× inline × 2 runs = 4× effective) | **~530 — strong #2** |
| residue-write.md | 569 | ~1,024 | ~102 — minor |
| angle-menu.md | 403 | ~322 (often skipped) | ~32 — negligible |

**verification-gates.md + a-to-b together ≈ 92% of realized savings; the bottom two combined <8%.** a-to-b is the one file whose realized rank far exceeds its byte rank (the inlining double-cost).

**Conditional loads effectively always fire:** synthesis (→ a-to-b) runs on ~100% of runs (only total-dispatch-failure skips it); residue-write fires ~90%+ (empirical: 83 `critical-review-residue.json` files on disk; every findings-bearing event records B-class ≥2). So conditionality doesn't meaningfully discount realized cost — but it does mean these are *pointer reads that only cost when critical-review actually runs*, unlike the prior feature's lifecycle files which load far more often.

---

## Within-File Trim-Candidate Mapping

> Read alongside the **Adversarial Review** below, which refutes/downgrades several of these candidates. Net safe-trim after adversarial pass is **lower** than the raw estimates here.

### verification-gates.md (~1,100–1,500B raw candidate pool — the safest, largest pool)
- Step 2c.5 **tempfile-handling paragraph** (~500B) — *flagged How-narration* → **the adversary refutes this; see below.**
- **Duplicated exit-4 benign-skip rationale** across Step 2c.5 / 2d.5 (~500B) — *candidate dedupe* → **adversary downgrades: keep both (different transitions).**
- `--feature` resolver restatement in Step 2a.5 (~150B) — *candidate* → **adversary: it's a cross-reference, lean refuted.**
- **Keep verbatim:** exit 0/3/4 route tables, the 5-flag/2-flag fenced invocations, total-failure string, Phase-2 schema, `N of M … (K excluded)` partial-coverage prefix + K=0 omission.

### a-to-b-downgrade-rubric.md (inlined into every synthesizer run — highest risk)
- **Keep verbatim:** intro/ratify condition, the 4 trigger definitions (absent/restates/adjacent/vague), straddle-exemption-takes-precedence rule, reclassification-note format `Synthesizer re-classified finding N from A→B: <rationale>`.
- 8 worked examples (~3,500B): **do NOT mechanically cut to 4.** The ratify/downgrade contrast pair per trigger is disambiguating; the **adjacent pair (ex 5/6) is the only demonstration of the straddle-exemption interaction** — load-bearing. Conservative: **prose-tighten within examples (~500–900B)** keeping full coverage; 8→6 (drop only absent-ratify + vague-ratify) is the *maximum* and **must be gated on a behavioral eval.**

### residue-write.md (~100–150B only — almost all contract)
- Keep: skip-on-zero rule, resolver dispositions + exact `Note:` strings, R4 payload field names (`class, finding, reviewer_angle, evidence_quote` + envelope), failure→`synthesis_status:"failed"`. Only safe trim: de-dup the zero-B-class skip rule stated 3×.

### angle-menu.md (~0–150B — leave as-is)
- Already at floor. Keep the "representative not exhaustive / invent new" license, angle-count rule, distinctness + artifact-specificity criteria + the single disambiguating "retry logic" example.

**Total conservative safe-trim (pre-adversarial): ~1,700–2,700B (~13–21% of 19,762B).** The durable low-risk win is verification-gates.md How-narration.

---

## Contract-Preservation & Blast-Radius

**Live static pin (the only one):** E101 contract lint on the two fenced `verification-gates.md` invocations (flag sets above). `bin/.contract-lint-exceptions.md` exempts only `SKILL.md`, **not** the reference files — they pass on their own merit (verified 0 violations today).

**Runtime/behavioral contracts with NO static gate (the dangerous zone):**
- **a-to-b rubric** inlined into the Opus synthesizer (`SKILL.md:76-78` → `synthesizer-prompt.md:35-37`): trigger defs + straddle rule + reclassification-note format. A bad trim degrades A↔B classification silently. **No lint, no test.**
- **Exit-code route tables** (verification-gates.md): the orchestrator's reaction rules for exit 0/3/4 on both subcommands (esp. exit-3 do-not-surface, exit-4 benign-skip). Python (`critical_review/__init__.py`) owns the *codes*; the *reaction prose* is markdown-only and **untested**.
- **Total-failure string** (`All reviewers excluded — drift or Read failure detected; critical-review pass invalidated. Re-run after resolving concurrent write source.`): **markdown-only, no Python fallback, no test** — must survive verbatim.

**The hard PRESERVE-SET (verbatim across the four files):** (1) the two fenced flag-complete invocations; (2) exit-0/3/4 reaction rules for both subcommands; (3) the total-failure string; (4) a-to-b's 4 triggers + straddle rule + reclassification-note format; (5) console-script names `cortex-critical-review`, `cortex-critical-review-resolve-feature`, `cortex-critical-review-write-residue`; (6) residue R4 field names.

**Pre-commit gates on `skills/*` edits (in order):** parity → contract(E101) → events-registry → prescriptive-prose → bare-python(L201) → skill-path(SP001/SP002) → build-plugin mirror+drift. Only **E101** has a live non-trivial pin; the rest are satisfied-by-construction if the trim keeps flags, doesn't rename console scripts, adds no `"event":` literal / `${CLAUDE_SKILL_DIR}` token / bare-python callsite, and commits canonical+mirror together.

**Consumers that do NOT pin content (safe):** events-registry checker (no JSON literal in these files), grep-targets test (backlog only), L1 ratchet (frontmatter only), skill-path lint (no tokens present today), `record-exclusion` (bare inline-code, no flags → not pinned).

---

## Adversarial Review

The adversary challenged the trim map and found the verification approach **structurally blind on exactly the high-value targets**. Key conclusions (grounded in file reads):

1. **"Safe to trim How-narration" conflates two claims.** The What/Why-not-How principle governs *what authors write*, not *what is safe to remove from shipped instructions a live model executes*. Concretely: the verification-gates.md:37 **tempfile paragraph is a Why disguised as How** — it names two failure modes ("concurrent runs corrupt each other's stdout (silent)"; "stale leftovers trip the Write tool's read-before-overwrite guard (noisy)"). Removing it removes the only thing steering the orchestrator toward a fresh path; the failure is **silent** in the concurrent-run case. **This is the single most dangerous proposed cut — refute it or only condense while keeping both named consequences.** Likewise the exit-4 rationale in 2c.5 vs 2d.5 is *not* a pure duplicate — the two govern **different downstream transitions** (reviewer-tally/total-failure vs whether Step 2e proceeds) with **zero behavioral test coverage**; do not dedupe.

2. **The verification method is blind to the regressions that matter most.** It verifies cuts against static anchors (tests/lints/grep/parity) — but the top-two targets (inlined rubric, route semantics, tempfile guard, total-failure string) have **no static gate**. "No anchor breaks" then means *the anchor doesn't exist*, not *the cut is safe* — the safety signal **inverts** on precisely the high-value prose. **Verified: `tests/test_skill_section_citations.py` covers only `skills/lifecycle/references/{plan,complete,review}.md` — ZERO critical-review coverage.** The recovered "citation sweep verifies cross-references survive" does **not** protect these files. A real check needs an A/B synthesizer/orchestrator eval over fixtures exercising the four triggers + straddle, all exit-3/4 branches, and a stale-tempfile scenario — feasible (a `baseline_critical_review.py` fixture harness exists) but **not committed to by the lifecycle as scoped.**

3. **Value bar.** Conservative safe-trim 1,700–2,700B = **6–9% of the prior feature's ≥30,000B accept floor**, from lower-frequency on-demand files, with the highest-value cuts unverifiable. **Measured on bytes, this feature fails the prior precedent.** It is only defensible if reframed — value = *de-risking a hand-trim* and/or *establishing the methodology + static anchors for the critical-review family* — with an honest, much lower byte target. The spec MUST NOT claim "verified-safe" for the top-two files when no behavioral verification runs.

4. **The 8→6 example cut is unverifiable without an A/B eval.** The rubric is the *only* thing separating A-class (blocks artifact) from B-class (residue). A blurred Trigger 3 / weakened straddle contrast can **silently downgrade a real A→B** (defect ships) or **ratify B→A** (false blocks). Both surface only as degraded review quality over many runs. **Default rubric edits to refuted absent an eval; never cut the ex-5/ex-6 straddle pair.**

5. **Missed by the core wave:** (a) the **total-failure string has no Python source-of-truth** (unlike the synth-drift string at `critical_review/__init__.py:684,696`) — paraphrasing it breaks nothing detectably yet corrupts a user-facing total-failure message; treat as a frozen literal. (b) **Route-table↔Python drift the trim could introduce:** condensing exit-code prose risks making it say something subtly different from the Python exit constants, with no test cross-checking — **hand-diff every condensed exit-code prose against `critical_review/__init__.py`.** (c) the `--feature` "restatement" is actually a cross-reference (orphan risk, low value → lean refuted).

**Recommended mitigations the spec should weigh:** refute the tempfile cut; keep both exit-4 rationales; gate every rubric edit behind a behavioral eval (else ship zero rubric changes); **consider adding a static anchor first** (extend `test_skill_section_citations.py` to cover these files + pin the total-failure literal) so cuts become verifiable — the adversary argues this is the feature's real value; hand-diff condensed exit-code prose vs Python; commit canonical+mirror together; surface "leave 2 of 4 as-is" + the honest byte target to the user.

---

## Open Questions

These are decisions for the **Spec phase / user** — surfaced, not silently resolved. Each is annotated as resolved, deferred-to-spec, or a contradiction.

1. **Does the feature pass its own value bar? (Deferred to Spec — primary scope/value decision.)** Conservative safe-trim ~1,700–2,700B is 6–9% of the prior feature's ≥30,000B accept floor, from on-demand files. The Spec §4 complexity/value gate must decide: (a) reframe value away from raw bytes (de-risking the hand-trim / establishing methodology + static anchors for the critical-review family) and state an honest low byte target; (b) descope to a minimal high-leverage trim of verification-gates.md How-narration only; or (c) reconsider. **Recommendation to carry into Spec: option (a) — the durable value is the methodology + the static anchor, not the byte count.**

2. **Is "leave residue-write.md + angle-menu.md ~as-is" an approved scope cut? (Deferred to Spec/user.)** 92% of realized savings are in the top two files; the ticket scoped all four. This is a genuine scope decision, not a research finding — the user should approve descoping two files to near-zero.

3. **Will this lifecycle run a behavioral (A/B) eval to certify the high-value cuts? (Deferred to Spec — determines what "adversarially-verified" means here.)** The rubric and route semantics have no static gate; without an eval, "verified-safe" is a misnomer for the top-two files. Options: (a) build/run an A/B synthesizer eval over the four triggers + straddle + exit branches (a `baseline_critical_review.py` harness exists); (b) ship only static-anchor-protected cuts and default unverifiable cuts to refuted. **This is the central definition-of-done question.**

4. **Should the feature ADD a static anchor before trimming? (Deferred to Spec — the adversary's reframe.)** Extending `tests/test_skill_section_citations.py` to cover the critical-review reference files and pinning the total-failure literal would convert today's unverifiable cuts into verifiable ones. This may be the feature's highest-value deliverable — Spec should decide whether it's in scope.

5. **Report raw bytes or dispatch-weighted savings? (Resolved — report both.)** Prior convention is raw canonical bytes (`git cat-file -s origin/main` vs `wc -c`, mirrors excluded). The a-to-b inlining + 2-runs-per-lifecycle weighting means realized token savings exceed raw byte deltas; report raw bytes as the ledger figure (per precedent) AND the realized-leverage estimate as context. No further user input needed.

6. **Re-compose the adversarial auditor/verifier prompts, or use `/cortex-core:critical-review`? (Resolved — Spec/Plan author chooses.)** The prior feature's sub-agent prompt text wasn't preserved; the in-repo `/cortex-core:critical-review` skill is the available adversarial analogue. Not a user question — a method choice for Plan.
