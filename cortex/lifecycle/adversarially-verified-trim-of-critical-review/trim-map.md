# Trim Map: verification-gates.md

**File**: `skills/critical-review/references/verification-gates.md`
**Before (canonical bytes)**: 10565 (`git cat-file -s origin/main:…`)
**Method**: two-pass adversarial — a trim-auditor (opus) proposed cuts; a *separate, fresh* refuter (opus) independently assigned each verdict with a concrete breakage anchor. Per the spec, a near-zero applied result is a valid, passing outcome; cuts were NOT padded to force a reduction.

## Keep-rationale (file exclusion list — never proposed)
The two fenced flag-complete invocations (`check-artifact-stable` 5 flags, `check-synth-stable` 2 flags) and `prepare-dispatch`; the exit-0/2/3/4 reaction *markers* for both subcommands; the total-failure literal; the three Step designators (2a.5/2c.5/2d.5); console-script names; the Phase-2 envelope-extraction regex; the `N of M … (K excluded)` partial-coverage prefix + K=0 omission. All of these are now also statically pinned by `tests/test_critical_review_reference_pins.py` (Phase 1).

## Verdict summary
0 safe · 6 downgraded · 2 refuted. **Applied: 2** (the two pure-redundancy downgrades). **Skipped-with-reason: 4** (downgrades that reword untested behavioral routing/telemetry prose — deferred this round; the gate now makes a future verifiable application possible). **Refuted: 2.**

Every proposal carries a distinct `auditor_reason` (the case FOR the cut) and `verifier_reason` (the refuter's independent verdict) — the structural evidence that auditor and refuter were two separate passes.

---

## Proposals

### P1 — Step 2c.5 tempfile-guard paragraph (MANDATORY)
- **kind**: How-narration · **action**: condense · **est_savings_bytes**: ~360 · **risk**: med
- **excerpt**: "Sharing a path across invocations causes concurrent runs to corrupt each other's stdout (silent), and stale leftovers from prior sessions trip the Write tool's read-before-overwrite guard (noisy). Derive the path from `$LIFECYCLE_SESSION_ID` or `mktemp -d`."
- **auditor_reason**: How-narration spelling out the corruption modes and the derivation method; a capable model writing four parallel outputs uses per-invocation unique paths naturally.
- **verifier_reason** (downgraded): No pin/pointer/route depends on this prose, but the two named failure modes are non-obvious and asymmetric — the stale-leftover Write-guard trip is a harness-specific hazard a model would not infer from "unique path" alone, and its failure is silent. Keep the requirement + a compressed why (must retain the Write-guard mention).
- **verdict**: downgraded → **downgrade_to**: one sentence keeping the requirement + the Write-guard rationale clause.
- **disposition**: **skipped-with-reason** — rewords research-flagged behavioral prose (silent-failure steering) for ~marginal bytes; the passage stays present verbatim. Deferred; gate now protects it.

### P2 — Step 2c.5 Exit-4 benign-skip rationale (MANDATORY)
- **kind**: How-narration · **action**: condense · **est_savings_bytes**: ~330 · **risk**: med
- **excerpt**: "This is a benign skip, distinct from exit 3: no event was persisted, the reviewer is neither excluded-for-drift nor failed, and the stdout verdict line still reflects the genuine check result. Treat the reviewer as a normal pass — …"
- **auditor_reason**: Actionable contract is "Exit 4 = treat as normal pass"; the surrounding clauses are explanatory rationale.
- **verifier_reason** (downgraded): Carries the pinned `- **Exit 4**` marker (must survive). Three clauses are behavioral, NOT rationale: "proceed to Phase 2 for this reviewer" (a distinct transition vs exit-3 exclusion), "do not emit an exclusion warning", and "do not count it toward the all-reviewers-excluded total-failure path" (load-bearing against the line-59 total-failure trigger — a miscounted exit-4 could spuriously invalidate). Only the middle rationale is trimmable; no behavioral test guards this prose.
- **verdict**: downgraded → **downgrade_to**: keep the marker + the three behavioral instructions; trim only the "no event persisted / neither excluded nor failed / stdout verdict still reflects" rationale.
- **disposition**: **skipped-with-reason** — behavioral routing prose governing the total-failure tally, no behavioral test; deferred this round.

### P3 — Step 2d.5 Exit-4 benign-skip rationale (MANDATORY)
- **kind**: duplication · **action**: condense · **est_savings_bytes**: ~300 · **risk**: med
- **excerpt**: "This is a benign skip, distinct from exit 3: no event was persisted and the synthesizer's verdict is otherwise treated as a clean pass. Surface the synthesizer's prose output normally and proceed to Step 2e."
- **auditor_reason**: Counterpart restatement; the "proceed to Step 2e" action is echoed at line 88.
- **verifier_reason** (downgraded): Carries the pinned `- **Exit 4**` marker. The "proceed to Step 2e" tail IS redundant with line 88, but "Surface the synthesizer's prose output normally" is a distinct instruction with NO restatement in line 88 and is the explicit contrast to exit-3's "Do NOT surface the synthesizer's prose output" (line 85). Keep the marker + the surface-prose instruction.
- **verdict**: downgraded → **downgrade_to**: keep marker + "Surface the synthesizer's prose output normally"; the "proceed to Step 2e" tail + rationale may be trimmed (line 88 restates the Step 2e transition).
- **disposition**: **skipped-with-reason** — governs a distinct untested transition (whether Step 2e proceeds); deferred this round.

### P4 — Step 2d.5 `--feature`/exit-4 write-guard paragraph (dup of Step 2c.5)
- **kind**: duplicated-boilerplate · **action**: condense · **est_savings_bytes**: ~470 · **risk**: med
- **excerpt**: "the subcommand's write-guard now enforces this structurally: if you pass a `--feature` whose `cortex/lifecycle/{feature}/` directory does not exist, the subcommand suppresses the write and returns exit 4 … rather than creating a phantom directory."
- **auditor_reason**: Near-verbatim restatement of the line-49 write-guard contract for the second subcommand.
- **verifier_reason** (downgraded): The two copies govern DIFFERENT subcommands and DIFFERENT SKILL.md-pointed sections (SKILL.md:72→2c.5, :86→2d.5); a reader landing in 2d.5 must not have to cross-reference 2c.5, so the duplication can be compressed in place but NOT deleted. Both facts (missing-dir→exit-4-not-phantom; `<path>`-arg may skip) must survive in each section.
- **verdict**: downgraded → **downgrade_to**: compress both line-49 and line-80 copies to the same shorter wording, keeping both facts.
- **disposition**: **skipped-with-reason** — touches exit-4 telemetry semantics in two route sections with no behavioral test; the dedup edit surface (two sites) outweighs the marginal bytes this round.

### P5 — Step 2c.5 captured-SHA cross-reference restatement
- **kind**: duplication · **action**: remove(first sentence)/condense · **est_savings_bytes**: ~90 · **risk**: low
- **excerpt**: "The orchestrator captures the pre-dispatch SHA-256 of the artifact into orchestrator context before fan-out (see the `check-synth-stable` subcommand for the canonical computation path). That captured SHA is the expected value compared against each reviewer's sentinel here."
- **auditor_reason**: Restated cross-reference; Step 2a.5 already establishes the pinned SHA and line 48 binds `<hex>` to it.
- **verifier_reason** (downgraded): The capture-restatement sentence is genuinely redundant with Step 2a.5 + the line-48 binding and is removable; but keep a compressed pointer to `check-synth-stable` as the canonical-computation reference and the "expected value compared against each reviewer's sentinel" tie.
- **verdict**: downgraded → **downgrade_to**: drop the redundant capture sentence; keep a one-clause cross-reference retaining the `check-synth-stable` canonical-computation pointer and the sentinel-comparison semantics.
- **disposition**: **applied-per-downgrade** — pure redundancy, no behavioral routing content, refuter-certified, no pinned token touched.

### P6 — Step 2a.5 substitution-site enumeration
- **kind**: How-narration · **action**: condense · **est_savings_bytes**: ~120 · **risk**: low
- **excerpt**: "Substitute both into every dispatch site that follows: the per-angle reviewer template, the total-failure fallback reviewer template, and the synthesizer template."
- **auditor_reason**: How-narration enumerating the three substitution sites; a capable model substitutes wherever the templates reference the vars.
- **verifier_reason** (downgraded): No pin/pointer/route depends on it and SKILL.md:46 carries a compressed equivalent, but the conditionally-used total-failure fallback template is the non-obvious site — keep the catch-all plus that call-out so a fallback dispatch never runs against an unpinned artifact.
- **verdict**: downgraded → **downgrade_to**: "Substitute both into every dispatch site that follows — including the conditionally-used total-failure fallback reviewer template." (drop the obvious per-angle + synthesizer enumeration).
- **disposition**: **applied-per-downgrade** — narration with a retained non-obvious call-out; refuter-certified, no pinned token touched.

### P7 — Step 2c.5 Phase-2 "split at the last match" instruction
- **kind**: How-narration · **action**: condense · **est_savings_bytes**: ~140 · **risk**: high
- **excerpt**: "split at the last match (tolerates prose quoting the delimiter)."
- **auditor_reason**: Narration explaining why the last match; the regex literal is preserved.
- **verifier_reason** (refuted): NOT narration — it is the load-bearing selection instruction. The kept `re.findall(...)` returns ALL matches; "split at the last match" tells the orchestrator WHICH to use. It mirrors the Python emitter's deliberate last-real-sentinel precedence (`critical_review/__init__.py`) defending against a reviewer that quotes `<!--findings-json-->` in prose; first-match splitting would misroute that reviewer to the malformed-envelope exclusion path. No behavioral test guards this.
- **verdict**: **refuted** · **disposition**: refuted (not applied).

### P8 — Step 2c.5 Exit-3 record-exclusion double-emission guard
- **kind**: How-narration · **action**: condense · **est_savings_bytes**: ~180 · **risk**: high
- **excerpt**: "the orchestrator MUST NOT append to `events.log` inline and MUST NOT invoke `record-exclusion` separately (would cause double-emission)."
- **auditor_reason**: Restates a consequence inferable from "already appended"; the file header already states the no-inline-append rule.
- **verifier_reason** (refuted): The auditor's premise is half-true — the header covers the inline-append clause, but NOT the `record-exclusion`-double-emission guard, which is stated nowhere else. On exit 3 the subcommand has already appended `sentinel_absence`; a separate `record-exclusion` call (a real, separately-invokable subcommand) would append a second identical event. Removing this clause drops a distinct, untested-elsewhere foot-gun guard.
- **verdict**: **refuted** · **disposition**: refuted (not applied).

---

## Applied set (Task 3)
Only **P5** and **P6** are applied (per-downgrade). All others are skipped-with-reason or refuted, recorded above with the refuter's concrete anchors. The applied net byte change is small and positive-savings only; the tempfile-guard passage, both exit-4 rationales, the exit-2 reaction, and the full preserve-set remain present verbatim. This is the honest, verifier-bounded result — the file has very little genuinely-safe slack, as two independent adversarial passes (research + this one) both found.
