# Research: Ship Phase 2 of discovery-output-density

Scope: extend Phase 1's gate-brief generator framework (C) to lifecycle specify+plan approval surfaces, and wire `score-corpus` as a periodic warn-only check (G) via just-recipe + statusline + JSON state file. Both corpora (`cortex/research/`, `cortex/lifecycle/`). Justified by 100% of 56 lifecycle research.md files flagging ≥1 of 6 reader-study patterns.

**Headline finding**: The adversarial review produced empirical evidence that Phase 1's pattern detectors fire on **~50% of legitimate spec.md and plan.md prose** (case-insensitive `does not` regex, literal `DR-N`/`§N` forward-ref detection). The genre-transfer assumption underpinning the bundled Phase 2 design is falsified. The spec phase must resolve this before committing to ship.

## Codebase Analysis

### Phase 1 reuse surfaces (Candidate C)

- `cortex_command/discovery.py:267` — `GATE_BRIEF_WORD_CAP = 150` (derived from 90th-percentile of compressed Headline Finding lengths in research corpus).
- `cortex_command/discovery.py:275–324` — `GATE_BRIEF_RUBRIC` constant: three-anchor rubric ("decided / alternatives / tradeoff"); six reader-study pattern prohibitions.
- `cortex_command/discovery.py:522–570` — `validate_brief()`: hardcoded anchors (`decided`/`decide`, `alternative`/`options`, `tradeoff`/`cost`), word-cap tolerance `+ 25`.
- `cortex_command/discovery.py:657` — `_cmd_generate_brief()`: subcommand handler, dispatches fresh-context sub-agent with `GATE_BRIEF_RUBRIC` system prompt.
- `cortex_command/_brief_scoring.py` — six pattern scorers extracted as module-level helpers, importable.

What's discovery-specific (needs lifting): `--research-md` and `--persist-to` argument names; event emission targets `gate_brief_generated` (event needs new variants for spec/plan).

What's generic: rubric prose is domain-neutral; scorers are regex-based.

### Lifecycle gate call sites (Candidate C)

- `skills/lifecycle/references/specify.md` §4 (User Approval): approval surface fields = Produced / Value / Trade-offs / Proposed ADRs. **Injection point**: after orchestrator review §3a, before AskUserQuestion.
- `skills/lifecycle/references/plan.md` §4 (User Approval): approval surface fields = Produced / Trade-offs. **Injection point**: same pattern.

### Refine integration (Candidate C)

- `skills/refine/SKILL.md` Step 5 (Spec Phase): wraps specify.md via inheritance. Both refine and direct lifecycle converge at specify.md §4. Refine's complexity/value gate (its §4 adaptation) fires BEFORE brief generation; brief is produced AFTER complexity/value gate routes to "approve" rather than "drop / minimum viable."

### Brief persistence path (Candidate C)

- Phase 1 wrote `cortex/research/<topic>/brief.md`.
- Proposed for lifecycle: `cortex/lifecycle/<slug>/spec-brief.md` and `cortex/lifecycle/<slug>/plan-brief.md` (siblings to research.md, spec.md, plan.md). Not added to artifacts array (transient rendering asset per Phase 1 convention).
- Alternative considered: nested `cortex/lifecycle/<slug>/{spec,plan}/brief.md` to preserve score-corpus scanner's "one brief.md per topic dir" assumption. See Open Questions.

### score-corpus reusability (Candidate G)

- `cortex_command/discovery.py:820–905` — `_cmd_score_corpus`: takes `--root` + `--threshold`, walks topic dirs, picks `brief.md` first then falls back to `research.md`, scores via `_brief_scoring`. Output: `<path> patterns_reproducing=N/6 word_count=M [FLAGGED]`.
- Empirical: pointed at `cortex/lifecycle/` today scores all 56 research.md files; pointed at `cortex/research/` finds no brief.md (Phase 1 fresh-merge; no production briefs generated yet), falls back to research.md scan of 13 files.

### Just-recipe + statusline conventions (Candidate G)

- `justfile`: existing two-mode pattern via `check-events-registry-audit`, `check-parity-audit`, etc. Recipe naming convention: `<gate>-audit`.
- `claude/statusline.sh`: <500ms budget per `cortex/requirements/observability.md`. Scans lifecycle dirs already; adding score-corpus inline exceeds budget. Must pre-cache via background writer.

### Events registry

- Phase 1 event: `gate_brief_generated` with schema `{ts, event, feature, status, brief_word_count, patterns_detected_count}`.
- Phase 2 additions needed: `spec_brief_generated`, `plan_brief_generated` (same schema), `corpus_score_run` `{ts, event, root_path, total_items, flagged_count, threshold, duration_seconds}`.

### Module placement (skill-helper pattern, project.md L31)

Recommendation: extend `cortex_command/discovery.py` with new subcommands rather than spin up `cortex_command/lifecycle_brief.py`. Phase 1 already established the module as the brief-generation home; parallel-evolution risk is real if helpers fork.

### Tests

- `tests/test_discovery_gate_brief.py` — test pattern: three fixtures, score=0/6, decision-content anchors, word-cap tolerance.
- Phase 2 mirrors: `tests/test_lifecycle_spec_brief.py`, `tests/test_lifecycle_plan_brief.py`. Fixtures: `tests/fixtures/lifecycle-spec-brief/{simple,complex,critical}/spec.md` and analogous plan-brief fixtures.

## Web Research

### Industry validation of Phase 1's rubric (ADR template)

- ADR (Architecture Decision Record) template — Decision / Context / Consequences / Alternatives — converges on Phase 1's "decided / alternatives / tradeoff" framing. Used by Martin Fowler, AWS Prescriptive Guidance, GitHub adr-templates. The rubric direction is industry-validated.
- AWS Well-Architected "one-way vs two-way door" framing supports extending to higher-stakes spec/plan gates over the discovery research→decompose gate.

### LLM summarization failure modes (relevant to brief generator)

- Clinical-summarization study (Nature npj Digital Medicine 2025): 1.47% hallucination, 3.45% omission. **Omissions 2.3:1 are the more dangerous failure mode**.
- "From Single to Multi: How LLMs Hallucinate in Multi-Document Summarization" (NAACL 2025): cross-reference hallucination grows with input complexity.
- G-Eval (chain-of-thought rubric scoring): 0.51 → 0.66 Spearman ρ vs human judgment — modest improvement, not transformative.
- Implication for Phase 2: omission-bias self-check is more important than hallucination prevention. The brief generator should explicitly verify each Required anchor is present in the output before declaring success.

### Soft / warn-only signals — established industry posture

- CI/CD literature: "Start in warn mode for ~2 weeks, build trust, tune false positives, then promote to enforcement once baseline is clean."
- Critical threshold: **<15% FP rate or signals become wallpaper**. SonarCloud, GitHub Advanced Security cited as precedent.
- Alert fatigue cited in CHI 2026 (AI verification load): permanent always-visible signals collapse to noise without affordance to drill in.

### Density / readability metrics

- Flesch-Kincaid / Gunning Fog / SMOG inadequate for technical writing (surface-level only). Phase 1's invented six patterns are functionally similar to **Vale's custom-rule pattern** (used by Google, Microsoft, Datadog, GitLab, Elastic, RedHat) — Vale is the architectural analog for the corpus lint.
- Near-duplicate sentence detection has solid lineage (Stanford NLP IR Book; ACL 2022 "Deduplicating Training Data Makes Language Models Better").
- Hedge detection (arXiv 2024) is the academic analog to "author-process narration" detector.
- **False positives are the dominant failure mode** for pattern-based prose scoring.
- **Genre-transfer risk is the largest uncertainty** — pattern detectors calibrated on one genre should not be assumed to transfer to similar-but-distinct genres without re-validation. Small-N reader study replication is the field-standard answer.

### Word-cap discipline

- Naive truncation causes omission, hallucination — Phase 1's 90th-percentile-of-compressed-lengths derivation is defensible.
- Context-rot research (Chroma 2025): "200K window can degrade at 50K tokens." Input length matters, not just output cap.
- Implication: spec.md and plan.md may have different compression behavior than research.md. Re-derive cap per artifact type.

### Statusline / ambient signals

- Claude Code statusline doc is the canonical local precedent — JSON via stdin.
- Anti-pattern: ambient signals fail when users stop seeing them ("wallpaper"). Succeed when paired with drill-in affordance.
- IDE-quality indicators: closer to the writing moment = more behavior-shaping. Statusline = post-write surveillance, lower behavior-change potential than in-editor lint.

## Requirements & Constraints

### project.md (parent constraints)

- **Solution Horizon** (project.md:19–21): "Complexity must earn its place by solving a real problem now. When in doubt, simpler wins." "A scoped phase of a multi-phase lifecycle is not a stop-gap (stop-gap means unplanned-redo). Test: current knowledge, not prediction."
- **Skill-helper modules** (project.md:31): atomic `cortex_command/<skill>.py` subcommands fusing validation+mutation+telemetry.
- **SKILL.md size cap** (project.md:30): 500 lines. Exceptions via in-file `<!-- size-budget-exception: ... -->`. Default fix: extract to `references/`.
- **Dual-source mirror** (project.md:29): bin/cortex-* scripts require in-scope SKILL.md/requirements/docs/hooks/justfile/tests references.
- **In Scope**: AI workflow orchestration (skills, lifecycle); observability (statusline, notifications, metrics).
- **MUST-escalation policy** (CLAUDE.md): no new MUST language unless effort=high dispatch demonstrably fails on observed failure with artifact evidence. Phase 2 defaults to soft positive-routing.

### observability.md (statusline constraints)

- Statusline latency budget: <500ms per invocation.
- Statusline is read-only with respect to session state files.
- Failure is non-blocking (statusline failure doesn't affect Claude session).
- No DB; in-memory cache only.

### ADRs

- ADR-0001: File-based state, no database.
- ADR-0002: CLI wheel + plugin distribution.
- ADR-0003: Per-repo sandbox registration (`cortex/` umbrella sandbox-write-registered).

### Phase 1 spec carry-through (`cortex/lifecycle/discovery-output-density-investigate-author-centric/spec.md`)

- **Req 9** (post-merge corpus regression check): operator runs `score-corpus cortex/research/` at quarterly review; failure triggers replan, not silent breakage. **Phase 2's Candidate G operationalizes this.**
- **Req 15** (Phase 2 trigger arming): `phase2-trigger` tagged backlog ticket. Fired via #232 closure.
- **Non-Requirements**: Phase 1 explicitly out-of-scope: "Does NOT apply the fix cross-skill to lifecycle research / spec / plan artifacts (Candidate C). Named as Phase 2 trigger with operational arming."
- **Technical Constraint**: "The binding mechanism is hypothesized, not architecturally enforced. Markdown grammar is not load-bearing structural separation; the spec's binding claim rests on (a) fresh-context dispatch resetting the attention window, and (b) multi-fixture pre-merge tests."
- **Edge Cases preserved**: brief gen failure → fall back to dense; structurally malformed → degraded but non-empty preferred; no truncation; no caching.
- **Gate affordance** (CLAUDE.md): four user-blocking options (approve / revise / drop / promote-sub-topic) preserved in research→decompose gate. Phase 2 must preserve analogous affordances at spec and plan gates.

## Tradeoffs & Alternatives

### Fork 1 — Brief generator architecture (Candidate C)

- **Recommended**: Single shared generator with `--rubric=research|spec|plan` parameter; three rubric constants (`GATE_BRIEF_RUBRIC_RESEARCH`, `_SPEC`, `_PLAN`); `validate_brief()` rubric-keyed for anchor sets.
- **Why over alternatives**: Phase 1 already factored as thin shell around `GATE_BRIEF_RUBRIC` + `_run_brief_query`; adding switch extends the design idiom. Sibling subcommand approach (B) and new-module approach (C) duplicate code or fork modules unnecessarily. Single rubric (D) accepts genre mismatch.

### Fork 2 — Brief persistence path

- **Recommended**: Per-artifact briefs at `cortex/lifecycle/<slug>/spec-brief.md` and `<slug>/plan-brief.md`. Symmetric with `cortex/research/<topic>/brief.md`.
- **Why**: Auditability preserved per gate; score-corpus can score both as siblings.
- **Caveat surfaced**: score-corpus directory walker assumes `brief.md` per dir. Resolving requires scanner extension or rename to nested `<slug>/{spec,plan}/brief.md` — see Open Questions.

### Fork 3 — Candidate G execution model

- **Recommended**: just-recipe writes JSON to `cortex/state/corpus-score.json`; statusline reads on tick. Operator-driven periodic.
- **Why over alternatives**: Cron/launchd adds platform-specific setup (no project precedent). Overnight-runner integration couples to overnight cadence (defensible but expands scope). Combined-all (E) is principled extension if "periodic" means "scheduled."
- **Conflict surfaced**: clarified-intent's "periodic" is ambiguous. See Open Questions.

### Fork 4 — Threshold tuning

- **Recommended initial**: Preserve Phase 1's `--threshold 1` for both corpora. Plan revisits if lifecycle baseline noise is too high.
- **Why**: Calibration data doesn't exist yet; premature tuning risks under-flagging.

### Fork 5 — Statusline shape

- **Recommended**: Hidden-until-threshold; render count + color when visible. Preserves attention budget.
- **Caveat from adversarial review**: with measured FP rate ~50% (see Adversarial Review), threshold=1 means never hidden; raising threshold silences real signal. See Open Questions.

### Fork 6 — Bundle vs split (C and G)

- **Tradeoffs agent recommends SPLIT** (direct conflict with clarified-intent's bundle commitment).
- **Why**: G's complexity is concentrated in recipe + state-file + statusline (1–2 days). C is multi-day across three rubrics + generators + lifecycle skill edits. They don't share implementation surface.
- **Counter (adversarial finding)**: split rationale is reinforced by genre-transfer evidence — pattern calibration is a prerequisite phase that both C and G depend on. Bundle locks the user into shipping on a falsifiable premise. See Open Questions and Adversarial Review.

## Adversarial Review

The adversarial agent **empirically ran Phase 1's pattern detectors against real production spec.md and plan.md files** in `cortex/lifecycle/` and produced hard evidence of failure-mode realization.

### BLOCKING findings

**1. Genre-transfer empirically fails: pattern detectors flag ~50% of legitimate spec/plan prose.**

Measured pattern counts on real artifacts (six tested):

| Artifact | Total / 6 | Flagged patterns |
|---|---|---|
| `audit-auto-memory/spec.md` | 2 | forward_refs, negation_rebuttal |
| `audit-auto-memory/plan.md` | 0 | — |
| `close-plugin-cli-auto-update-gaps/spec.md` | 3 | forward_refs, negation_rebuttal, conditional_repeat |
| `improve-discovery-gate-presentation/spec.md` | 3 | forward_refs, negation_rebuttal, conditional_repeat |
| `discovery-output-density-investigate-author-centric/spec.md` | 3 | forward_refs, author_process, negation_rebuttal |
| `discovery-output-density-investigate-author-centric/plan.md` | 3 | forward_refs, author_process, negation_rebuttal |

Concrete failure mechanisms:
- `_NEGATION_REBUTTAL_RE` (`cortex_command/_brief_scoring.py:49`) is case-insensitive; fires on "does not partition further" / "does not duplicate" — standard Non-Requirements prose.
- `_FORWARD_REF_RE` (line 29) catches `DR-N` / `§N` literally; specs that *talk about* the discovery framework or use section refs always flag.
- `_AUTHOR_PROCESS_RE` (line 43) fires on "walked back" / "decomposition history" — terms common in retrospective Risks sections.

**Mitigation**: Plan must include a **pattern-calibration sub-task** that runs scorers against ≥10 real spec.md and ≥10 real plan.md production artifacts, computes FP rate on what should be clean prose, and re-derives the six (or different N) patterns for spec.md and plan.md specifically. Rubric-keyed pattern detectors required: `PATTERNS_BY_RUBRIC = {"research": [...], "spec": [...], "plan": [...]}`. The proposed single-generator architecture must extend to the scorer.

**2. `score-corpus --root cortex/lifecycle/` already misbehaves.**

- Scanner picks ONE file per dir (`brief.md` then falls back to `research.md`). Under the proposed `spec-brief.md` / `plan-brief.md` naming, the scanner finds `research.md` first and scores against the wrong rubric — `spec-brief.md` and `plan-brief.md` are never scored.
- 75 lifecycle dirs × measured FP rate flood the report with `[FLAGGED]` at threshold=1.
- Fallback `_extract_headline_and_architecture()` walks whole-file when section headers don't match (lifecycle research.md doesn't use `## Headline Finding` heading).

**Mitigation**: Replace single-file-per-dir logic with "score every recognized brief artifact in every recognized topic dir." Filename → rubric mapping explicit: `brief.md` → research, `spec-brief.md` → spec, `plan-brief.md` → plan. Require `--corpus research|lifecycle` discriminator. Whole-file fallback disabled for lifecycle (genre mismatch unrecoverable without re-calibrated patterns).

**3. Phase 1's binding hypothesis is unfalsified; Phase 2 builds at 3× scale on unvalidated premise.**

- Phase 1 spec line 82: "The binding mechanism is hypothesized, not architecturally enforced. The risk is that fixture coverage is incomplete relative to the production input distribution — mitigated by Req 9's post-merge corpus regression check."
- Req 9's quarterly cadence has not elapsed (merged 2026-05-17; Phase 2 invoked 2026-05-18).
- Production briefs in `cortex/research/*/brief.md`: zero (no Phase 1-produced briefs yet exist — no discovery runs have completed since merge).
- Precedent: prior fix (`improve-discovery-gate-presentation`, 2026-05-12) tightened directive prose without binding — "tests passed; production artifacts still drifted." Pattern: test-pinned binding does not guarantee production fidelity.

**Mitigation**: Spec must explicit-disposition this dependency. Two options: (a) defer Candidate C until Req 9 produces at least one quarter's worth of production briefs scoring clean; or (b) accept the risk in `## Technical Constraints` so the user is asked at spec time.

**4. Statusline + cache architecture has unfixable staleness/trust problem.**

- Operator-driven periodic = unbounded staleness. Operator runs once, forgets, statusline displays "8 flagged" for months.
- No inverse-truth path: cache says 0 but fresh artifact has 4 patterns.
- Measured FP rate ~50% means threshold=1 floods; raising threshold silences real signal until calibration completes.

**Mitigation**: Drop statusline from Phase 2 scope; ship score-corpus as recipe + retro check only. Statusline integration becomes a Phase 3 trigger contingent on FP rate stabilization <15%.

### IMPORTANT findings

**5. Rubric-anchor drift undetectable.** Co-locate rubric and validator anchors in a single dict per rubric; add parity test asserting every validator anchor appears as a token in the corresponding system prompt.

**6. Word-cap calibration cannot reuse 150.** Per-rubric word-cap derivation required: `GATE_BRIEF_WORD_CAP_RESEARCH`, `_SPEC`, `_PLAN`. Re-measure 90th-percentile-of-compressed for each corpus.

**7. Fixture authenticity:** real production specs contain `R1`/`Phase 2` references that legitimately trigger detectors. Either scrub fixtures (underfits production) or fix the detectors (the right answer). Acceptance threshold is `score=0/N` against re-calibrated spec/plan pattern set, not against Phase 1's six.

**8. Refine vs. lifecycle gate-call-site routing fires brief N times on revision.** Spec must define brief-cache semantics: regenerate only when `spec.md` content hash changes. Persist hash alongside `spec-brief.md`.

**9. MUST-escalation creep in two new rubrics.** Phase 1 rubric is grandfathered; Phase 2 rubrics are new MUST surface area. Spec must use soft positive-routing phrasing OR cite events.log evidence per CLAUDE.md policy.

**10. Scanner edge cases under suffixed-brief naming.** Filename → rubric mapping enumerated explicitly in spec.

### WATCH-ITEM findings

**11. Split vs bundle:** turns on the calibration finding, not on shared implementation surface. If calibration is a prerequisite phase, both C and G consume its output. Split rationale becomes: ship calibration first → ship G against research+lifecycle → ship C generators last.

**12. Hidden-until-threshold statusline collapses to wallpaper or invisibility** given measured FP rate. Drop statusline from Phase 2; defer to Phase 3 contingent on calibration.

## Open Questions

The adversarial review surfaced fundamental questions that the spec phase must resolve before committing to ship Phase 2 as bundled. These are listed by the decision they force on the user:

1. **Accept the genre-transfer empirical finding**: Phase 1's six patterns produce ~50% positive-rate on legitimate spec/plan prose. Does the user (a) accept this and require a pattern-calibration sub-phase before C/G ship, or (b) reject the empirical evidence as inconclusive and proceed with rubric-keyed scorers as a best guess, or (c) abandon Phase 2 entirely until Req 9 produces enough production briefs to falsify Phase 1's binding hypothesis?

2. **Bundle vs split**: the tradeoffs agent recommends split (G first, C after) on implementation-surface grounds; the adversarial agent reinforces split on calibration-prerequisite grounds. The user committed to bundle. Does the user (a) reverse to split with calibration first → G → C, or (b) bundle with calibration absorbed as Phase 2's first work, or (c) bundle without addressing calibration (high risk of shipping a falsified design)?

3. **Statusline scope**: the adversarial review recommends dropping statusline integration from Phase 2 entirely; the clarified-intent committed to it. Does the user accept the deferral (statusline becomes Phase 3 contingent on calibration), or insist on statusline in Phase 2 (accepting wallpaper/invisibility risk)?

4. **Phase 1 hypothesis dependency**: Req 9's post-merge corpus check has produced zero data points. Phase 2 builds at 3× scale on this unvalidated premise. Does the user (a) defer Phase 2 until Req 9 produces ≥3 production briefs scoring clean, or (b) accept the risk explicitly in spec's `## Technical Constraints`?

Each of these is the spec phase's job to resolve via user interview. The other "open scoping questions" from the original ticket (per-rubric word caps, brief persistence path, refine integration semantics, threshold tuning, statusline shape) are downstream of these four — the framework's load-bearing assumptions must resolve first.

The ticket body's open questions resolved by research:
- ~~Which gates does C cover?~~ → specify + plan committed (clarified-intent), but bundle/split decision may revise.
- ~~Single rubric or per-gate variation?~~ → per-gate rubric required (Fork 1 recommendation).
- ~~Brief persistence path?~~ → `cortex/lifecycle/<slug>/spec-brief.md` + `plan-brief.md` recommended (Fork 2).
- ~~Refine flow interaction?~~ → fires once after refine §4 complexity/value gate; cache via spec.md content-hash (Adversarial #8).
- ~~G threshold?~~ → preserve Phase 1 default=1 initially (Fork 4); revisit post-calibration.
- ~~G statusline shape?~~ → hidden-until-threshold IF statusline scope retained; otherwise dropped (Adversarial #12).
- ~~G corpus scope?~~ → both research and lifecycle, with filename → rubric mapping enumerated (Adversarial #10).
