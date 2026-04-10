# DR-6 Stress-Test Gate: Answer

## Question

From `research/agent-output-efficiency/research.md` DR-6 (near line 189):

> Before adding output constraints, stress-test each skill by removing verbose-by-default instructions and measuring whether Opus 4.6 produces acceptable output on its own. Some skills may need subtraction (removing verbose instructions), not addition (adding brevity constraints).

## Empirical Answer

This audit applied #052's original rubric against 9 skills (lifecycle, discovery, critical-review, research, pr-review, overnight, dev, backlog, diagnose) across codebase analysis, web research, requirements review, tradeoffs exploration, and a dedicated adversarial review pass. The result is **zero high-confidence removal candidates**. Every initial "remove" verdict produced by the codebase-phase grep-and-read pass was overturned by the adversarial pass, which identified load-bearing value the grep-based analysis missed: defense-in-depth disclosures against frontmatter poisoning, output-channel directives (`AskUserQuestion`) dressed as prose, control flow gates (env-var checks, confirmation prompts, autonomous-run skips) dressed as conditional sentences, sub-agent prompts targeting Sonnet/Haiku rather than Opus 4.6, counter-weights against Opus 4.6's trained warmth in critical-review, and human-facing consumers of the events.log narrative fields via `skills/morning-review/references/walkthrough.md`.

## Pointer to Rationale

The authoritative per-candidate rationale lives in `lifecycle/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/research.md`. This DR-6 note is a pointer, not a duplicate — do not re-litigate the rubric here; trace the specific counter-argument to its research.md section.

Per-skill candidate sections in research.md covering every initial removal verdict and its counter-argument: lifecycle L1 (resume phase reporting), L2 (epic-research path announcement defense-in-depth), L3 (phase transition floor fields), L4 (phase-jump prerequisite warning safety rail); discovery D1 (per-skill-calibrated floor); critical-review CR1 (distinct-angle contract) and CR2 (anti-warmth counter-weight); research R1 (injection-resistance, explicitly out of scope), R2 (empty-agent fallback format), R3 (contradictions feeding lifecycle complexity escalation); pr-review PR1 (prior-outputs context retention); overnight O1 and O2 (rationale preambles that prevent helpful-optimization-away); dev DV1 and DV2 (conversational criticality suggestion caveats); backlog B1 and B2 (`AskUserQuestion` output-channel directives); diagnose DG1 (root-cause principle), DG2 (stderr completeness targeted at Sonnet/Haiku retry sub-agent), DG3 (competing-hypotheses control-flow gates).

The final aggregate verdict is stated in research.md under "High-confidence removal candidates": *None with high confidence.* The "Adversarial Review" section enumerates the structural categories (control flow misidentified as prose, security-adjacent disclosure, load-bearing detection gaps, critical-review warmth interaction, rubric unfalsifiability for non-Opus sub-agent destinations) that collectively overturn the grep-based remove verdicts.

## Deferred Candidates

Two moderate-confidence candidates survived the adversarial review as "flag for spec phase" rather than explicit keeps: `dev` DV1 (research.md lines 89-90 — the parenthetical "This is a conversational suggestion — lifecycle runs its own full assessment in Step 3") and `dev` DV2 (research.md lines 116-118 — the conversational template for the criticality suggestion). Neither has a confirmed downstream consumer, but both sit close enough to the criticality heuristic table that a naive delete risks clipping load-bearing adjacent text. Both DV1 and DV2 are deferred to the new imperative-intensity rewrite ticket as bonus candidates: the rewrite pass will naturally revisit the same prose region under a different rubric (intensity reduction per Anthropic's migration plugin), giving those two a second look without reopening #052's removal scope.

## Implication for Epic

This closes the DR-6 gate with a negative result: **removing verbose-by-default instructions alone is not sufficient to control Opus 4.6 skill prompt output.** The audit corpus (~2185 lines across 9 SKILL.md files) yielded no safely removable sentences under the original rubric — the verbosity that reads as redundant under grep is, on close reading, load-bearing for behaviors that grep cannot see. Downstream tickets in the epic therefore remain necessary: #053 (subagent output formats) and #054+ (compression and synthesis) are not made redundant by this stress-test. The epic intervention roadmap should proceed with those tickets as planned.

## Follow-Up Ticket

The one bright spot from the audit is an orthogonal axis Anthropic's own Opus 4.5 migration plugin ships as a rewrite table (`CRITICAL:` → plain, `ALWAYS` → plain, `NEVER` → `Don't`, `think about` → `consider`, etc.). That axis is tracked as a new backlog ticket: [[059-apply-anthropic-migration-rewrite-table-to-skill-prompts]] (file: `059-apply-anthropic-migration-rewrite-table-to-skill-prompts.md`). It is an orthogonal rewrite axis — imperative intensity reduction per Anthropic's published migration guidance — not a continuation of #052's removal rubric. The deferred `dev` DV1 and DV2 candidates ride along as bonus targets for the same pass.
