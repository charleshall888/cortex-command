# Research: Broaden discovery brief gate's substring anchors to accept natural English paraphrases

Backlog item 256. Tier=complex, criticality=high. Lifecycle slug `fix-validate-brief-substring-anchors-that`. Parent epic #251.

## Codebase Analysis

### Files that will change

- `cortex_command/discovery.py`
  - `:285-322` — `GATE_BRIEF_RUBRIC` constant. The rubric instructs the sub-agent to "Use ordinary words" and offers `settled on` as its own example verb; both fail the current validator. **Additional latent bug (not in the ticket):** line 305 in the rubric body reads `Word target: write no more than GATE_BRIEF_WORD_CAP words.` — the string is a triple-quoted literal, not an f-string, so the literal token `GATE_BRIEF_WORD_CAP` is what the sub-agent sees rather than the numeric `250`. Empirically verified: `'GATE_BRIEF_WORD_CAP' in GATE_BRIEF_RUBRIC` is `True`; `'250' in GATE_BRIEF_RUBRIC` is `False`. This is a more parsimonious explanation for the one observed paraphrase-rejection brief (439 words, 75% over cap) than "Sonnet weakly enforces word counts." See Adversarial Review §2 and Open Questions Q1.
  - `:532-580` — `validate_brief()`. Three substring-anchor checks (case-insensitive `in` on lowercased brief): decision (`"decided"|"decide"`), alternatives (`"alternative"|"options"`), tradeoff (`"tradeoff"|"cost"`). Plus a word-cap tolerance check (`GATE_BRIEF_WORD_CAP + 25`).
  - `:775-820` (and surrounding `_cmd_generate_brief` body) — retry-feedback prose. Lines 783-810 currently say verbatim: *"The brief must contain all three decision-content anchors: the literal word 'decided' or 'decide', the word 'alternative' or 'options', and the word 'tradeoff' or 'cost'."* Full prose rewrite required if the anchor set broadens — this is a verbatim enumeration, not a "soft" reference.
  - `:777` and `:818` — the two production call-sites of `validate_brief` (first attempt + retry).
  - `_run_brief_query` at `:615-683` — unchanged in behavior, but reads `GATE_BRIEF_RUBRIC` as its system prompt; any rubric edits affect every dispatch.
- `tests/test_discovery_gate_brief.py` (~400 lines, 3 acceptance contracts):
  - Lines 109-170: `test_brief_passes_all_fixtures` — **auth-gated (`_REQUIRES_AUTH`), skipped in CI**. Generates briefs from fixtures and validates them.
  - Lines 178-244: `test_brief_failure_falls_back_to_architecture` — auth-gated.
  - Lines 310-402: `test_gate_renders_brief_not_architecture` — no-auth. Hand-writes a brief at lines 330-335 using literal `decided`/`alternatives`/`tradeoff`/`cost` tokens, so it would not regress on anchor changes either. **CI coverage gap for anchor behavior — new tests must run without auth.**
  - Three fixtures live at `tests/fixtures/discovery-brief/{simple,complex,diagnostic}-topic/research.md`. Used by `test_brief_passes_all_fixtures`.
- `cortex_command/_brief_scoring.py` — pattern-scoring helper for the reader-study six-pattern detector. Not affected by anchor changes.

### Relevant existing patterns

- Anchor validation pattern is intentionally cheap: `.lower()` once, then three `in` checks. Pattern is grep-discoverable. Avoid regex unless required for word-boundary matching.
- Rubric structure is prose-only (no markdown lists / headings) and structured around three questions: decision / alternatives / tradeoff. Each question's example verb is the strongest signal the sub-agent gets about what to produce; rubric/validator agreement at the example-verb level is the load-bearing invariant.
- Retry feedback at `:783-810` is the recovery surface; one retry, with verbatim instruction on which tokens the validator expects.
- Event emission goes through `_emit_event` in `_cmd_generate_brief`. The `gate_brief_generated` event captures `status` and `brief_word_count` but **does not capture the brief text on failure** — every subsequent corpus analysis is blind to which anchor actually drove a given rejection.

### Integration points and dependencies

- `bin/.events-registry.md:121` registers `gate_brief_generated` with `scan_coverage: gate-enforced`. No anchor-vocabulary references. No registry changes needed.
- No `cortex-check-parity` references to `validate_brief` anchors. No hook changes needed.
- `skills/discovery/SKILL.md` and `skills/discovery/references/decompose.md` reference the brief generation subcommand but do not hardcode the anchor list. Skill prose is transparent to anchor changes.
- Skill-helper module pattern (project.md): `cortex_command/discovery.py` already fits — atomic subcommand fusing validation+mutation+telemetry. No promotion needed.

### Empirical corpus (the "0/7 pass-through")

The seven failing `gate_brief_generated` events:
- `cortex/research/harness-friction-triage/events.log` — one event: 2026-05-20T13:12:59Z, 439 words, `status: validation_failed`. **The only event with a non-zero brief.** The brief text itself is not preserved on failure, but this is the one confirmed paraphrase-rejection case.
- `cortex/lifecycle/discovery-output-density-investigate-author-centric/events.log` — six events, all with `brief_word_count: 0`. These are sub-agent generation failures (empty output / SDK returns), not anchor failures. Five of the six are clustered into two narrow timestamp bursts, suggesting they may come from a single debug session rather than six distinct production failures.

Implication: the corpus empirically supports a paraphrase-rejection rate of 1 sample, not 7. The framing "0/7 pass-through" is correct but overstates the breadth of empirical motivation for anchor broadening specifically. See Adversarial Review §1 and Open Questions Q2.

## Web Research

### Substring/keyword gates in LLM pipelines — when they work, when they break

- Where they work: shape checks (type, range, regex on enums) — Instructor's first rung. The gate's job is value-shape validation.
- Where they break: content-presence checks ("does this brief state a decision?") — Instructor explicitly names this limit. The discovery-brief gate is a content-presence check disguised as a value-shape check.
- Lexical-brittleness mechanism (arxiv 2602.17316, "Same Meaning, Different Scores"): "LLMs rely on surface lexical cues over abstract syntactic structure"; meaning-preserving paraphrases silently fail substring anchors.
- Published empirical regime: TinyV (arxiv 2505.14625) measured ~38% false-negative rate for verifier-style keyword checks; the discovery brief's 0/7 (or 1/1 paraphrase-rejection) sits inside this regime.
- Instructor's published escalation ladder: type → rule-based/keyword (where they make sense) → semantic (LLM-judge) for complex/subjective criteria. **A 0/7 pass-through means rule-based has failed the "where it makes sense" test** — either broaden or escalate to semantic, but DO NOT tighten the rubric to match a brittle anchor.

### Paraphrase-tolerance approaches

- Curated synonym lists (lemmatization, regex stems): cheap, deterministic, hand-maintained, well-suited to small stable vocabulary spaces.
- Lemmatization (spaCy / NLTK / stem-strip): collapses inflectional variation (`decide`/`decides`/`decided`/`deciding`/`decision`) into a single anchor.
- Embedding similarity / LLM-as-judge: handles unbounded paraphrase but adds latency, cost, and calibration burden.
- Hybrid (keyword + semantic fallback): the recommended pattern in search-relevance literature.

### ADR/MADR canonical vocabulary (vocabulary corpus for the three moves)

- Decision-section heading: "Decision Outcome"; canonical lead-in: "Chosen option: …".
- Alternatives-section heading: "Considered Options" or "Alternatives Considered".
- Tradeoffs-section heading: "Consequences" or "Pros and Cons of the Options"; rows formatted "Good, because…" / "Bad, because…".
- Verb cluster (decision): chose/choose/chosen, decided/decide, selected/select, picked/pick, settled on, opted for, went with, agreed on, resolved to, concluded.
- Noun/phrase cluster (alternatives): alternatives, options, considered, candidates, contenders, rejected, evaluated.
- Noun/phrase cluster (tradeoff): tradeoff(s), trade-off, consequence(s), cost(s), pros and cons, downside(s), drawback(s), risk(s), compromise(s), giving up X to get Y.

### Rubric-design literature: rubric/validator agreement is load-bearing

- Masood / ACL 2024 "LLM-Rubric": rubrics must be stable; the rubric's own example MUST pass its own validator. The current `settled on` ↔ literal-`decided` mismatch is the precise instability Masood flags.
- Retry feedback: there is a published-style argument that retry feedback should describe move INTENT, not enumerate lexical anchors verbatim (rubric-leak / lock-in concerns). **Counter-argument (Adversarial Review §7): retry is recovery, not teaching — verbatim "use one of these tokens" maximizes the next dispatch's chance of passing the validator. The published-style argument applies cleanly to first-attempt rubric prose, less cleanly to retry feedback.**

### Key URLs (for spec/plan reference)

- Instructor on semantic validation: https://python.useinstructor.com/blog/2025/05/20/understanding-semantic-validation-with-structured-outputs/
- arxiv 2602.17316 — lexical brittleness mechanism: https://arxiv.org/abs/2602.17316
- arxiv 2506.13023 — practical-guide warning on keyword-selection brittleness: https://arxiv.org/html/2506.13023v1
- arxiv 2505.14625 — TinyV verifier false-negative rate: https://arxiv.org/pdf/2505.14625
- MADR template: https://github.com/adr/madr/blob/develop/template/adr-template.md
- Promptfoo `llm-rubric` (canonical semantic-fallback drop-in): https://www.promptfoo.dev/docs/configuration/expected-outputs/model-graded/llm-rubric/

## Requirements & Constraints

### From `cortex/requirements/project.md`

- **Design principle — prescribe What and Why, not How.** The What/Why: the brief must reference each of the three decision moves (decision, alternatives, tradeoff). The How (literal substring list vs. regex stems vs. semantic gate) is implementation detail; choose the durable How that captures the What.
- **Structural separation over prose-only enforcement.** The validator is structural enforcement; the rubric is prose. Aligning them is structural maintenance, not prose-only patching. Rubric-validator agreement should ideally be enforced by a test (Adversarial Review §6), not by convention.
- **Solution horizon.** If the next-failure pattern is nameable, propose the durable version. Here the pattern is nameable: more natural-English paraphrase verbs (`landed on`, `went with`, `opted for`, `picked`) will eventually arrive. A narrow corpus-tightest fix is a stop-gap.
- **MUST-escalation policy does NOT apply.** No MUST/CRITICAL/REQUIRED escalation needed for this work.
- **Three-criteria ADR gate** — likely no ADR needed: the change is reversible (anchor sets can be tightened later), follows existing pattern (cheap structural check), no architectural alternative is being rejected (the semantic-gate alternative is being deferred to #255, not rejected).
- **Skill-helper module pattern.** `cortex_command/discovery.py` is already a skill-helper module; no promotion needed.

### From `cortex/research/harness-friction-triage/research.md`

- §62-70: explicitly classifies the brief-gen validator as "same anti-pattern (hygiene check dressed as semantic gate) as critical-review's `verify-reviewer-output`." Sibling ticket #255 owns the structural-anti-pattern taxonomy work. **Remedy differs from `verify-reviewer-output`:** the decision-content property here IS enforceable — the sub-agent IS producing the prose; the validator measures the wrong proxy. So broaden + align, do not abandon.
- §131 (decomposition Piece): explicitly scoped as "Single-file fix" with effort=S. Recommends broadening the three anchor sets.

### From sibling ticket #255 (gate-policy taxonomy + critical-review gate fixes)

- Owns the cross-cutting structural anti-pattern (hygiene-as-semantic-gate) across `critical_review.py`. Ships independently of #256.
- A semantic-gate replacement for `validate_brief` would land under #255's umbrella, not as #256 scope creep.

### From `skills/discovery/SKILL.md`

- Gate emits four options: `approve | revise | drop | promote-sub-topic` (line 396 in tests). These must remain verbatim.
- Discovery render path falls back to dense `## Architecture` section if brief generation fails or validation fails — this is the current production behavior (the brief.md path is dead by default per the empirical corpus).

## Tradeoffs & Alternatives

Six alternatives were weighed.

### Alternative A — Ticket's proposed approach (literal substring families)

Broaden the three anchor sets to the enumerated families: decision (`decide|decided|decision|decisions|chose|chosen|concluded|settled|selected`), alternatives (`alternative|alternatives|option|options|considered|weighed`), tradeoff (`tradeoff|trade-off|cost|drawback|downside|sacrifice`). Update rubric + retry-feedback + tests.

- Complexity: very low. ~40 LOC net. Touch surface is exactly the three sites the ticket names.
- Maintainability: medium. Hand-maintained lists grow per inflection; future paraphrases tail-fail (e.g., `landed on`, `went with`).
- Performance: identical to today (three lowercase `in` checks).
- Alignment: good. Pure structural fix; resolves the internal contradiction; honors "structural separation over prose-only enforcement."
- Pros: cheapest possible fix; zero new infrastructure; the broadened set is derived from observed paraphrase pools.
- Cons: hand-maintained list calcifies; one paraphrase wide for the next-failure pattern; doesn't address the deeper "hygiene dressed as semantic gate" anti-pattern (deferred to #255).

### Alternative B — Empirically-tightest set (narrow to one corpus sample)

Broaden only the anchors that drove failures in the corpus, using only paraphrase tokens that actually appeared.

- **Rejected.** Corpus has effectively one usable lexical sample (439-word brief); narrowing to it overfits to noise. Solution-horizon principle in project.md explicitly rejects narrow fixes when the next-failure pattern is nameable (it is).

### Alternative C — Lemmatized regex word-stems

Replace literal lists with regex stems: `\b(decid|chose|chosen|conclud|settl|select)\w*`, `\b(alternat|option|consider|weigh|choic)\w*`, `\b(tradeoff|trade-off|cost|drawback|downside|sacrific|compromis)\w*`.

- Complexity: low (~15 LOC).
- Maintainability: nominally better than A (stems absorb inflections).
- **Adversarial finding (§3):** the `\w*` suffix has severe false-positive risk. Empirically tested by Agent 5: stems match `commit` → `committee`, `pick` → `pickup`/`pickiness`, `option` → `optional`, `select` → `selecting` (UI sense), `cost` → `cost-of-living` etc. Pure-noise prose with no decision content passes (e.g., "Pick up the trash. The alternative was unclear. The downside is obvious.").
- **Modified Alt-C**: replace `\w*` with explicit accepted suffixes per stem (e.g., `decid(e|ed|es|ing|ion|ions)?` with `\b` word-boundary anchors). This recovers durability while bounding false positives.
- Recommendation: **Modified Alt-C with explicit suffixes** captures the durability benefit without the FP regression — see Recommended Approach.

### Alternative D — Semantic / LLM-as-judge gate

A fresh-context sub-agent classifies whether the brief contains the three decision-content moves.

- **Deferred to ticket #255.** Right answer to the broader category question; out of scope for #256's empirical urgency. The deferred ticket should reference #256's post-merge corpus to determine whether the broadened anchors achieve adequate pass-through; if 6+/7 next-corpus passes, semantic-gate work is not justified.

### Alternative E — Soften the gate (warn-only / retry-only, no hard fail)

- **Rejected.** The six empty-brief failures are real sub-agent failures the gate SHOULD catch. Softening turns the gate into a vestigial logger without resolving the structural mismatch.

### Alternative F — Drop the gate entirely

- **Rejected.** The brief.md path was designed deliberately to compress dense Architecture sections for human gate-readers; dropping the feature on a fixable validator bug is throwing out a working compressor because the gauge is broken.

### Recommended approach

**Alternative A (literal substring families) augmented with word-boundary regex matching to bound false positives, plus the rubric-substitution bug fix as a precursor.**

Rationale:
- The empirical case for "broaden anchors" is narrower than the ticket frames (1 confirmed paraphrase rejection, not 7), so an aggressive lemma-stem broadening (Alt-C) over-corrects. Adversarial Review §3 demonstrated concrete FP cases that pass pure-noise prose.
- Alternative A's literal substring families with `\b` word-boundaries on each token (e.g., `\bdecide\b|\bdecided\b|\bdecision\b|...`) keeps the cheap-discoverable pattern, captures the ticket's enumerated families, and rules out `optional`/`pickup`/`committee`-style FPs.
- Include MADR canonical vocabulary: `chose`, `chosen`, `selected`, `settled on`, `opted`, `picked` (decision); `considered`, `weighed`, `evaluated`, `rejected` (alternatives); `consequence`, `drawback`, `downside`, `compromise`, `risk` (tradeoff). The rubric's own example verb `settled on` must be in the set.
- Fix the `GATE_BRIEF_RUBRIC` f-string bug first (line 305: `GATE_BRIEF_WORD_CAP` token never substitutes). This may be the more parsimonious explanation for the 439-word over-cap brief and could reduce future paraphrase-rejection rate independently. Whether this fix lands inside #256 or as a precursor commit is Open Question Q1.

Belongs to follow-up:
- Semantic-gate replacement: deferred to #255 with explicit post-merge corpus reference.
- Structural rubric-validator parity test: should land in #256 per Adversarial §6 (see Open Question Q3).

## Adversarial Review

### Failure modes and edge cases

1. **The empirical case for anchor broadening is weaker than presented.** Only 1 of 7 corpus events is a confirmed paraphrase rejection (the 439-word brief). The other 6 events have `brief_word_count: 0` (sub-agent generation failures, not anchor failures), and 5 of those 6 are clustered into two narrow timestamp bursts in a single lifecycle directory — likely a single debug session rather than 6 distinct production failures. "0/7 pass-through" inflates the empirical breadth.

2. **The rubric is not an f-string — `GATE_BRIEF_WORD_CAP` is literally sent to the sub-agent.** Line 305 reads `Word target: write no more than GATE_BRIEF_WORD_CAP words.`; `GATE_BRIEF_RUBRIC` is a plain triple-quoted string, not an f-string. Empirically verified: `'GATE_BRIEF_WORD_CAP' in GATE_BRIEF_RUBRIC` is `True`; `'250' in GATE_BRIEF_RUBRIC` is `False`. None of the codebase/web/requirements/tradeoffs agents caught this. The "Sonnet weakly enforces word counts" theory in `_GATE_BRIEF_WORD_CAP_RATIONALE` is plausibly explained more simply: the model never sees a numeric target. This bug likely explains the 439-word brief (75% over cap). **Recommendation: fix as precursor or as part of #256 scope (see Open Question Q1).**

3. **Alt-C lemma stems have severe false-positive risk.** Empirically tested: 14 crafted briefs. Pure-noise prose with no decision content passes (`Pick up the trash. The alternative was unclear. The downside is obvious.`). `commit` matches `committee`; `pick` matches `pickup`/`pickiness`; `option` matches `optional`. **Modified Alt-C with explicit suffixes is the recovery path; bare Alt-C with `\w*` is not viable.**

4. **CI coverage gap.** `test_brief_passes_all_fixtures` (lines 109-170) is auth-gated (`_REQUIRES_AUTH`) and skipped in CI. `test_gate_renders_brief_not_architecture` (lines 310-402) hand-writes a brief using literal `decided`/`alternatives`/`tradeoff`/`cost` and would not catch anchor regressions either. New tests for paraphrase variants must run without auth — recommend parametrized unit tests of `validate_brief()` against ~20 hand-written paraphrase + false-positive cases.

5. **The proposed broadened set is still one paraphrase wide.** A genuine paraphrase brief — *"We landed on the GitHub-native badge. Shields.io was on the table. The downside is no coverage percentage."* — fails any of the proposed sets (no anchor matches `landed`, `went with`, `on the table`, `accepted`). The fix moves the FN boundary but does not eliminate it; that boundary's permanent durability requires Alternative D (semantic gate, deferred to #255).

6. **Rubric/validator parity has no structural enforcement, only convention.** Without a test that extracts example verbs from `GATE_BRIEF_RUBRIC` and asserts each appears in `validate_brief()`'s accepted set, the next rubric edit re-introduces the drift this ticket is fixing. The proposed plan relies on code-review discipline, which is prose-only enforcement — the anti-pattern project.md explicitly flags. **Recommend: include a structural parity test as a required acceptance contract.** See Open Question Q3.

7. **Removing "use these exact words" from retry feedback may worsen retry success.** Agent 2 cited Masood: retry feedback should describe move intent, not enumerate lexical anchors. **Counter-argument:** retry is a recovery operation, not a teaching operation; verbatim "use one of: decided, chose, settled on, concluded" maximizes the dispatch's chance of passing the validator. Masood's argument applies cleanly to first-attempt rubric prose, less cleanly to retry feedback. **Recommendation: keep retry's verbatim lexical instruction, with the expanded vocabulary; this is recovery, not rubric leak.**

### Security concerns or anti-patterns

8. `_run_brief_query` at line 663 sets `permission_mode="bypassPermissions"` with `max_turns=3`. The brief generator is supposed to produce text, but the SDK options give the sub-agent tool access without confirmation. Unrelated to this ticket but a latent surface — a research.md crafted with prompt injection could direct the sub-agent. The six empty-brief failures are equally consistent with a sub-agent that completed in tool-call turns without emitting text. **Out of scope for #256, but worth noting for a follow-up.**

9. **The "hygiene dressed as semantic gate" anti-pattern is being cemented.** Doing #256 without #255 means the lexical check remains the gate's contract; future authors will assume the lexical check IS the semantic check. The right structural answer is Alternative D in #255. #256's right framing: "narrow the failure boundary while the semantic-gate question is resolved upstream."

### Assumptions that may not hold

- "Lemma stems are durable against the next paraphrase" — refuted by FN-constructable cases (`landed on`, `went with`, `on the table`).
- "6/7 corpus failures are SDK / sub-agent issues" — partially correct, but the rubric-substitution bug (Adversarial §2) is a more parsimonious root-cause hypothesis for the one paraphrase-rejection case than "Sonnet weakly enforces word counts."
- "The gate is justified at all" — with 1 confirmed paraphrase rejection across the entire corpus, the prior for "this gate has any pass-through cases worth optimizing" is weak. A reasonable alternative posture: instrument first (preserve brief text on failure), re-collect data, then legislate anchors. See Open Question Q4.

### Recommended mitigations (rolled into #256 scope and Open Questions)

1. Fix the rubric-substitution bug as precursor or in-scope. See Q1.
2. Preserve brief text in `gate_brief_generated` events on failure (observability fix). See Q2.
3. Prefer Alternative A (literal substrings with `\b` word-boundaries) over bare Alt-C (lemma stems with `\w*`). Modified Alt-C with explicit suffixes is the durability-recovery path.
4. Add structural rubric-validator parity test. See Q3.
5. New paraphrase unit tests must run without auth (no `_REQUIRES_AUTH` gating).
6. Keep retry feedback's verbatim lexical instruction (recovery, not teaching).

## Open Questions

**All four open questions below are deferred to the Spec phase Q&A** (confirmed by user 2026-05-20 at Research Exit Gate). Each will be resolved during the specify.md structured interview alongside other spec decisions.

### Q1 — Scope: rubric-substitution bug

Should the `GATE_BRIEF_WORD_CAP` literal-token bug in `GATE_BRIEF_RUBRIC` (line 305) be fixed as part of #256, or shipped as a separate precursor commit / new backlog ticket?

- **Pro in-scope:** Same module, same author surface, structurally connected (the rubric's word-cap instruction is part of the rubric/validator-agreement story this ticket is fixing). One coherent diff. Likely root-cause for the 439-word over-cap brief, so fixing it makes the empirical "broaden anchors" case cleaner.
- **Pro precursor:** Cleaner scope for #256; the bug fix is one line; new ticket would be trivially small. Keeps the anchor-broadening change isolated.
- **Recommendation to surface to user in spec phase.**

### Q2 — Observability: preserve brief text on failure

Should `gate_brief_generated` events preserve the brief text (e.g., `brief_excerpt: brief[:200]` or full text on failure) so future corpus analysis is not blind?

- **Pro in-scope:** Required for empirical validation of any future anchor change. Cheap to add. Without it, the next anchor-broadening ticket faces the same one-sample empirical poverty.
- **Pro deferred:** Slight schema change; might want to coordinate with events-registry / dashboard consumers.
- **Recommendation to surface to user in spec phase.**

### Q3 — Structural rubric-validator parity test

Should the spec include a structural parity test that extracts example verbs from `GATE_BRIEF_RUBRIC` programmatically and asserts each passes `validate_brief()` (or is in the accepted set)?

- **Pro:** Prevents recurrence of the exact bug this ticket is fixing. Honors "structural separation over prose-only enforcement" from project.md.
- **Implementation:** New unit test in `tests/test_discovery_gate_brief.py`; extracts example verbs by regex (e.g., backticked verbs in rubric body) and asserts validation passes for a minimal brief containing only that verb plus the other two anchor moves.
- **Recommendation:** include in spec as a required acceptance contract.

### Q4 — Posture: instrument-first or legislate-now?

Given that 1/7 confirmed paraphrase failures (rest are upstream sub-agent issues), should #256 proceed as scoped (broaden anchors now), or pause to:
1. Land the observability fix (Q2) and rubric-substitution fix (Q1) as precursors;
2. Re-collect 2-4 weeks of corpus data;
3. Then legislate anchor breadth from a richer empirical base?

- **Pro legislate-now:** The empirical case is narrow but the structural contradiction (rubric example verb fails own validator) is independently real; fixing it does not require more data. The anchor broadening is reversible.
- **Pro instrument-first:** The "0/7" framing is partly an artifact of an unrelated bug (rubric substitution) + a debug-session cluster. Better data prevents over-correction.
- **Recommendation to surface to user in spec phase.** Default position: proceed as scoped, with Q1 and Q2 folded in.

## Considerations Addressed

- *Research must validate which paraphrase tokens actually appear in the 0/7-failing corpus before locking the anchor token set, rather than adopting the ticket's enumerated families verbatim.* — Addressed: empirical analysis revealed only 1 of 7 events has non-zero brief text (439-word brief in `cortex/research/harness-friction-triage/events.log`); the other 6 are `brief_word_count: 0` upstream failures. Brief text itself is not preserved on failure, so per-anchor failure mode for that one sample is recoverable only by re-running generate-brief manually. **The empirical breadth supports anchor broadening as a structural fix (rubric/validator agreement) but not as a paraphrase-distribution-driven calibration.** Recommended set is the ticket's families plus MADR canonical vocabulary (`settled on`, `selected`, `chose`, `picked`, `consequence`, `compromise`, etc.) — not corpus-derived.
- *Research must identify which anchor(s) actually drive the 0/7 corpus failures, since the tradeoff anchor already accepts the literal word cost (the rubric's own instructed word at line 301) and the broaden-all-three framing may be partly unsupported.* — Addressed: the tradeoff anchor already accepting `cost` is empirically correct (rubric line 301 instructs "Name the concrete cost or constraint"). Without preserved brief text we cannot reconstruct per-anchor failure mode for the one paraphrase-rejection sample, but the rubric/validator contradiction is independently structural (rubric's `settled on` example fails the decision anchor). **The broaden-all-three framing is partly redundant on the tradeoff side but justified by rubric/validator agreement on the decision side.** Open Question Q2 (observability) is the durable fix for future per-anchor analysis.
- *The retry-feedback prose at cortex_command/discovery.py lines 783-810 enumerates literal anchor words verbatim and is a full prose rewrite, and existing tests in tests/test_discovery_gate_brief.py likely contain assertions that paraphrase variants fail which will need to flip rather than merely extend.* — Addressed: confirmed full prose rewrite required at lines 783-810 (the prose enumerates anchors verbatim — `the literal word 'decided' or 'decide', the word 'alternative' or 'options', and the word 'tradeoff' or 'cost'`). On the test side, the situation is different from expected: no existing tests assert paraphrase variants fail — the auth-gated tests use real fixtures with whatever the sub-agent produces, and the no-auth test hand-writes a brief using only the literal anchor tokens. **The test-side burden is "add new paraphrase unit tests" (additive), not "flip existing assertions" (revisionary).** However, the broader CI gap (auth-gated fixture tests skipped in CI) is independently a concern (Adversarial §4).
