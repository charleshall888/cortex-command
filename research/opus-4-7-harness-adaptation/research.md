# Research: opus-4-7-harness-adaptation

> Generated: 2026-04-17. Topic: adapting this agentic-workflow harness to Claude Opus 4.7. Prior art: backlog #053 (4.5/4.6 imperative softening, complete).

## Scope framing note

The topic was presented as "harness adaptation." All five research agents converged on the same conclusion, though the framing differs by agent:
- **Agent A** (codebase audit) found every at-risk pattern in prompt files (SKILL.md + references), none in Python/bash infrastructure.
- **Agent B** (observed-failure mining) found all five observed failures (F1–F5) in prompt-level instruction ambiguity, zero in hooks/dashboard/pipeline code.
- **Agent C** (web docs) documented Anthropic's 4.7 guidance as targeting prompts, effort levels, and SDK params — not model-agnostic infrastructure.
- **Agent D** (matrix/numeric constraints) found no matrix-data-structure change warranted by 4.7.
- **Agent E** (adversarial) explicitly named the "harness re-think" framing as scope creep and proposed contraction.

This artifact therefore treats the effort as a **prompt-delta audit plus targeted capability adoption** — skill prompts, reference docs, CLAUDE.md surfaces, and dispatch templates — not a ground-up harness rewrite. DR-1 records this framing decision.

**Provisional**: Q3 surfaced that `claude/reference/*.md` files carry more weight than initially assumed (they're globally loaded via `~/.claude/CLAUDE.md` conditional-loading table), which *expands* the prompt surface. Open Question 5 further notes that if 4.7 changes conditional-loading semantics, the audit target could shift. The contraction framing is therefore valid *subject to OQ5 resolution*; the scope is "prompts and prompt-adjacent surfaces," not "skills only."

## Research Questions

1. **Q1 — Prompt delta audit.** What instruction patterns in our prompts are still at risk of 4.7 literal-interpretation misfires given #053 already covered aggressive imperatives?
   → **Answered.** Six distinct at-risk patterns identified, none covered by #053. Highest-signal: double-negation suppression, ambiguous conditional bypass logic, negation without positive alternative, examples-as-exhaustive lists. New finding not in scope of #053: "Consider" softenings from #053 may now under-trigger under 4.7 where the underlying action is actually required (not optional).

2. **Q2 — Observed 4.7 failures in our artifacts.** What do accumulated 4.7-era lifecycle artifacts reveal about concrete misbehaviors?
   → **Answered.** Five observed failures catalogued, currently being remediated by tickets #067, #068, #069. Recurring mechanism: 4.7 does not infer target audience, silence, or brevity that 4.6 inferred from context. Fix pattern: explicit positive routing ("log-only", "silent-and-re-run", "emit only X") rather than "do not narrate" negative directives.

3. **Q3 — Hook & reference surface.** Do hooks and reference docs contain instructions 4.7 would over-follow?
   → **Partially answered.** Current hooks are data-only injection (notification counts, status) — low 4.7 exposure. Reference docs flagged: `verification-mindset.md` Red Flags section (`STOP` header + negation-only list — risk of halt-on-hedge), `parallel-agents.md` "Don't use when" list (risk of all-or-nothing refusal), `output-floors.md` precedence rule (low risk). `claude/reference/` files carry more weight than initially assumed because they're globally loaded via `~/.claude/CLAUDE.md` conditional-loading table.

4. **Q4 — Model selection matrix recalibration.** Does 4.7's capability step-up change haiku/sonnet/opus routing?
   → **Answered: no immediate change.** The matrix is already conservative (sonnet dominant, opus reserved for complex+high/critical). 4.7's instruction-following consistency improves all tiers equally and does not widen or narrow the capability gap. The `model-selection.md` rationale ("Sonnet 4.6 gap with Opus is <2% on coding tasks") is unchanged by 4.7. Sonnet-default for interactive subagents (#046) remains correct — its justification was cost/rate-limit, not capability.

5. **Q5 — Tuned numeric constraints.** Do 4.7's changes require retuning turn limits, budget caps, concurrency?
   → **Partially answered with instrumentation gap flagged.** Turn limits (15/20/30) and budget caps ($5/$25/$50) live in `claude/pipeline/dispatch.py` code-only with no cited rationale. We lack empirical data to validate or adjust them. Concurrency limits are subscription-tier-bound, not model-bound — no change. 4.7 pricing is confirmed parity with 4.6 per release announcement (same $5 / $25 per Mtok). **Instrumentation gap**: we cannot currently answer "did this feature actually need opus, or would sonnet have worked?" from `events.log` — see Open Question 4.

6. **Q6 — Interactive default.** Is `"model": "opus[1m]"` still right?
   → **Answered: stay, update the model ID.** 1M context remains strategic for daytime work. Opus 4.7 retains 200K max output + 1M context at standard pricing (no long-context premium). When Claude Code ships 4.7 as `opus-4-7[1m]` or a resolved alias, update the settings.json line. Tone regression (less conciliatory, fewer emoji) is a user-preference issue, not a correctness one.

7. **Q7 — New capability opportunities.** What 4.7 features should we adopt, not just defend against?
   → **Answered.** Eight concrete opportunities. Highest-value: `xhigh` effort level (new, calibrated for coding/agentic), adaptive thinking as the new default, built-in progress updates (allows removing "summarize after N tool calls" scaffolding), self-verification before reporting (simplifies our verification loops), and the Anthropic-published `/claude-api migrate this project to claude-opus-4-7` automation command. Task budgets beta (`task-budgets-2026-03-13` header) is interesting but needs design work.

## Codebase Analysis

### Existing patterns and constraints

- **Prior softening (#053)** across 9 skills covers `CRITICAL:|You MUST|ALWAYS|NEVER|REQUIRED to|IMPORTANT:|make sure to|be sure to|remember to|think about|think through`. Validated as still correct by Anthropic's 4.7 best-practices doc.
- **Preservation rules from #053** (security strings, output-channel directives, control-flow gates, output-floor field names, quoted source, example code blocks, section headers) carry forward. Anthropic's 4.7 best-practices doc endorses positive routing over negative prohibition, which aligns with (not contradicts) the preservation rules. Adversarial hypothesis (Agent E Angle 5): 4.7's literal interpretation should make control-flow gates fire more deterministically than under 4.6. This hypothesis is untested — re-audit is deferred, not dismissed. If Q3's reference-doc concerns surface reference-file regressions under 4.7 (see OQ5), preservation rules may need selective re-examination then.
- **Model selection matrix** in both spec (`requirements/multi-agent.md:51-62`) and code (`claude/pipeline/dispatch.py:134-147`) — zero divergence detected.
- **Escalation ladder** hard-coded haiku → sonnet → opus with no downgrade; correct under 4.7.
- **Interactive default** `"model": "opus[1m]"` in `claude/settings.json:221`.

### Six at-risk patterns not covered by #053

| # | Pattern | Example site | 4.7 hypothesis | Freq | Confidence |
|---|---------|-------------|----------------|------|------------|
| P1 | Double-negation suppression (`omit X entirely — do not emit empty header`) | `critical-review/SKILL.md:22, 138`; `morning-review/references/walkthrough.md:106` | Over-strict compliance with both branches → gappy synthesis output | 3 skills | HIGH |
| P2 | Ambiguous conditional bypass (`Only X satisfies this check ... If Y, always run Z`) | `refine/SKILL.md:83`; `lifecycle/SKILL.md:112` | Model conflates skip-condition scope with subsequent unrelated instructions | 4 skills | MED-HIGH |
| P3 | Negation-only prohibition (`Do not be balanced. Do not cover other angles.`) | `critical-review/SKILL.md:103`; `verification-mindset.md:44-51` | Under 4.6, negation implied inverse; under 4.7, binary negation without inferred positive → drops caveats | 6+ sites | MED |
| P4 | Multi-condition gate with implicit short-circuit | `lifecycle/SKILL.md:152`; `refine/SKILL.md:69-87` | 4.7 fails to infer implicit control flow when bypass detection is natural-language-stated | 3+ skills | MED-HIGH |
| P5 | Procedural order dependency (`do not omit, reorder, or paraphrase`) | `pr/SKILL.md:38-46`; `skills/lifecycle/references/implement.md:189` | 4.7 treats "do not reorder" literally → refuses semantically-equivalent reordering | 4+ skills | MED |
| P6 | Examples-as-exhaustive lists (`Select from this menu`, `such as`) | `critical-review/SKILL.md:32-49` Angle Menu; `skills/lifecycle/references/review.md:59` | 4.7 treats illustrative lists as closed sets → refuses to derive custom angles | 3+ skills | MED |

### Five observed-failure patterns (already being remediated in flight)

All five cluster in **lifecycle clarify/specify/critical-review phases** — specifically, subagent→orchestrator return paths. They resolve to **three distinct root-cause mechanisms**, not one:

| # | Failure | Ticket | Mechanism family | Root mechanism |
|---|---------|--------|------------------|----------------|
| F1 | Dismiss-rationale leak in clarify-critic | #068 | M1: Missing audience/routing spec | "State X briefly" without audience → 4.7 defaults to user-visible |
| F4 | Clean-pass silence ambiguity | #069 | M1: Missing audience/routing spec | "No event is logged" ≠ "say nothing to user" under 4.7 |
| F5 | Fix-agent report absorption ambiguity | #069 | M1: Missing audience/routing spec | Subagent "Report:" without disposition → orchestrator relays verbatim |
| F2 | Apply/Dismiss/Ask walkthrough bloat in critical-review Step 4 | #067 | M2: Length-calibration regression | "Compact summary" meta-instruction not inferred as brevity requirement (this matches 4.7's new length-calibration-to-task-complexity behavior) |
| F3 | Internal narration of pre-write checks in specify | #069 | M3: Missing output-gate on internal verification | Verification steps without explicit output-gate → 4.7 narrates work by default |

**Remediation patterns differ by mechanism**:
- **M1 fixes** (3 of 5 failures): explicit positive routing — `log-only`, `silent re-run, surface pass/fail`, `absorb into internal state, emit nothing`. This is the pattern that aligns with Anthropic's 4.7 guidance on positive examples over negative prohibition.
- **M2 fixes** (1 of 5): replace meta-instructions (`compact`, `brief`) with explicit format specs (bullet limit, word cap, worked example). Meta-instructions rely on inference that 4.7 no longer makes.
- **M3 fixes** (1 of 5): add explicit output-gate to internal verification steps — "if verification fails, surface; otherwise silent." Distinct from M1 because it concerns steps that are internal-by-design, not steps whose audience happens to be ambiguous.

These mechanisms share a common theme (4.7 doesn't infer context 4.6 inferred) but converge on different concrete fixes. DR-6 below treats M1 as the dominant mechanism for codification because M1 accounts for 60% of observed failures and has the clearest structural fix; M2 and M3 are handled ticket-by-ticket.

### "Consider"-softening review (new concern — scope corrected)

Under 4.7, hedge-style language (`consider`, `try to`, `if possible`, `you might want to`) now genuinely weakens instructions rather than being charitably interpreted (per Anthropic best-practices §4.7).

**Scope correction** (critical-review Reviewer 2): #053's rewrite table contains exactly one `consider`-related row: `think about → consider` (when extended thinking NOT enabled). #053 did **not** use `consider` as a general softener for `CRITICAL:|MUST|ALWAYS|NEVER|IMPORTANT:` etc. Grep across `skills/` returns only ~9 `\b[Cc]onsider\b` occurrences in 8 files; `claude/reference/` returns 0. The original "30–40 sites" estimate was wrong by ~4×.

**Three site categories** across actual `consider` occurrences:
1. **Conditional requirement** (dominant): `"if count ≥ 10, append to the response: '... consider running /evolve'"` (retro SKILL.md:116), `"if the epic has no children ... consider running /discovery"` (dev SKILL.md:191, 195). Action is *required given the condition*. Binary optional-vs-required test collapses this category whichever way the auditor picks.
2. **Genuinely optional**: suggestions emitted by a skill to the user, where the user is the decision-maker (e.g., `dev/SKILL.md:195` is this class when read as user-facing output). Keep as `consider`.
3. **Polite imperative** (rare — the original motivating class): action is required but phrased politely. `pr/SKILL.md:34` (`"Consider the type of change..."` — required to classify PR type) is a candidate. This is the only class where direct-imperative restoration is defensible.

**Scope, corrected**: at most ~9 sites. Subset that #053 actually introduced (i.e., where git blame shows #053 commits replaced `think about` with `consider`) is likely smaller — possibly zero. Needs git blame before any rewrite.

**Revised DR-5** below reflects this corrected scope. A previous draft example (`skills/diagnose/SKILL.md:25` "Don't skip past errors or warnings") was incorrectly placed here; that site is a P3 negation, not a `consider` hedge. The actual `consider` in `diagnose` is at line 74 (`"consider spawning a competing-hypotheses"`).

## Web & Documentation Research

### Authoritative sources

| Source | URL | Fetched | Signal |
|--------|-----|---------|--------|
| Release announcement | anthropic.com/news/claude-opus-4-7 | yes | Headline behavior changes, capability additions |
| Migration guide | platform.claude.com/docs/en/about-claude/models/migration-guide | yes | Prose guidance + checklist, no rewrite table |
| Prompting best practices | platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices | yes | Dedicated "Prompting Claude Opus 4.7" section — highest density |
| Skills best practices | platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices | yes | Unchanged fundamentals; still endorses `MUST` escalation on observed failure |
| 4.7 migration plugin | github.com/anthropics/claude-code/plugins/claude-opus-4-7-migration | **404** | Does not exist as of 2026-04-17; 4.5 plugin is the tabular baseline |

### 4.7 behavior changes (verbatim high-signal)

- *"Claude Opus 4.7 interprets prompts more literally and explicitly than Claude Opus 4.6, particularly at lower effort levels. It will not silently generalize an instruction from one item to another, and it will not infer requests you didn't make. ... If you need Claude to apply an instruction broadly, state the scope explicitly."* [best-practices §4.7]
- *"Positive examples showing how Claude can communicate with the appropriate level of concision tend to be more effective than negative examples or instructions that tell the model what not to do."*
- Length now calibrates to perceived task complexity (remove length-control prompts, then re-tune).
- Fewer subagents spawned by default.
- Fewer tool calls by default.
- Built-in regular progress updates in long agentic traces (remove summarize-every-N scaffolding).
- Stricter effort respect at `low`/`medium` — under-thinks; fix by raising effort.
- Self-verification before reporting.
- Tone: less conciliatory, fewer emoji (voice regression vs. 4.6).

### Delta vs. 4.6

**Continuation** (#053 validated): softening `CRITICAL:|MUST|ALWAYS|NEVER|IMPORTANT:` remains correct.

**New concerns** (specific to 4.7, not in #053):
1. Scope-explicit instructions (no silent generalization).
2. Hedges now genuinely weaken (`try to`, `if possible`, `consider`).
3. Negative filter directives in review harnesses suppress output meaningfully — push filtering downstream.
4. Progress-update scaffolding is now counterproductive.
5. Length-control prompts should be removed and re-tuned.

**Partial tension with skill-authoring doc**: Skills best-practices still endorses escalating to `MUST filter` when Claude forgets a rule in iteration. Reconciliation: default soft, escalate on observed failure. This is an *inference* on my part, not a source-stated reconciliation — tracked in Open Questions.

### New capabilities to adopt (Q7)

| Capability | What it enables | Harness opportunity |
|-----------|-----------------|---------------------|
| `xhigh` effort level (new) | "Best setting for most coding and agentic use cases" per migration guide | Overnight runner lifecycle implement phase default → `xhigh` with `max_tokens ≥ 64k` |
| Adaptive thinking as default | `thinking: {type: "adaptive"}` + effort; `enabled`+`budget_tokens` returns 400 | Breaking change — must update any SDK calls that explicitly set thinking budget |
| Task budgets beta (`task-budgets-2026-03-13` header) | Model-visible running countdown across full agentic loop (min 20k) | Overnight rounds could expose visible budget for graceful wind-down |
| Built-in progress updates | Native regular updates in long traces | Remove "After every 3 tool calls, summarize progress" scaffolding from lifecycle/implement prompts |
| Self-verification before reporting | Pre-emit sanity check in 4.7 | Simplify our explicit verification loops |
| High-res image + 1:1 pixel coords | 2576px / 3.75MP / ~4784 tok/img | Dashboard screenshot workflows could accept larger images |
| 1M context + 128k output at standard pricing | No long-context premium | Interactive default can confidently stay on `opus[1m]` |
| `/claude-api migrate this project to claude-opus-4-7` | Claude Code built-in automation | May or may not apply to SKILL.md prompts — needs verification (see Open Q3) |

### Breaking changes to check

- `temperature` / `top_p` / `top_k` → 400 error (must omit).
- `thinking: {type: "enabled", budget_tokens: N}` → 400 (must use adaptive).
- `interleaved-thinking-2025-05-14` beta header unnecessary under adaptive.
- Prefill semantics (carried from 4.6): use structured outputs / `output_config.format`.
- Cybersecurity refusals newly active (not expected to affect our harness).

## Domain & Prior Art

### #053 (complete, 2026-04-10)

Softened 9 skills + references against 4.6 overtriggering. Scope, preservation rules, and downstream-consumer invariants documented in `backlog/053-add-subagent-output-formats-compress-synthesis.md`. Validated as still-correct direction by 4.7 guidance — do not reverse bulk; audit `Consider`-sites surgically per the new finding above.

### In-flight tickets #067, #068, #069

Already address F1–F5 above. The remediation pattern they converge on (positive routing / structured envelopes for subagent returns) is exactly the pattern the 4.7 best-practices doc endorses. These tickets are not redundant with this discovery — they are the *first wave*; this discovery produces the *second wave* covering patterns not yet observed.

### Anthropic migration plugin precedent (4.5)

The 4.5→4.6 migration plugin shipped a tabular rewrite reference at `github.com/anthropics/claude-code/plugins/claude-opus-4-5-migration/`. The 4.7 equivalent does not exist yet. The 4.5 table remains a load-bearing sub-reference.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| A. Audit 6 new at-risk patterns across subagent-dispatching skills only | M | Low — matches #053 methodology; preservation rules already established | None |
| B. `Consider`-softening surgical audit — git blame to find #053-introduced sites (subset of ~9 total), per-site optional / conditional-required / polite-imperative classification | XS | Low — per-site judgment call, no architectural change; may be zero sites after git-blame filter | `git blame` against #053 commit hashes; understanding of three-category classification (not binary) |
| C. Adopt `xhigh` effort default in overnight lifecycle implement | S | Medium — needs SDK wiring verification and cost-per-turn reality check | SDK path in `claude/pipeline/dispatch.py` supports effort param |
| D. Remove progress-update scaffolding from long-running prompts | S | Low — directly endorsed by Anthropic guidance | Identify which prompts have "summarize every N" scaffolding |
| E. Migrate to adaptive thinking (SDK breaking change) | S | Medium — breaks if any explicit `budget_tokens` set; grep required | Grep for `budget_tokens` in pipeline/overnight code |
| F. Instrument turn usage and cost to validate 15/20/30 and $5/$25/$50 limits | M | Low — data gathering only | events.log schema already carries `num_turns`, `cost_usd` |
| G. Try `/claude-api migrate this project to claude-opus-4-7` built-in command | S (exploration) | Medium — unknown whether it touches SKILL.md prompts or only SDK/API code | Ability to run Claude Code `/claude-api` locally |
| H. Full `claude/reference/*.md` audit for negation-only patterns | S | Low | None |
| I. Remove length-control prompts globally then re-tune (best-practices guidance) | M-L | Medium — length-control is load-bearing in some places (output floors) | Scope distinction between output-floor field names (preserved) and length-control prose (audit) |

**Deferred** (not in this discovery's scope):
- Full re-benchmark of model-selection matrix using production data (requires the Approach F instrumentation first).
- Task-budgets beta adoption (requires design work on graceful wind-down semantics).
- Interactive-default change (requires Claude Code to ship 4.7 as a selectable model).

## Decision Records

### DR-1: Scope framing — prompt-delta audit, not harness re-think (provisional on OQ5)

- **Context**: Topic was framed as "how the agent harness should adapt." Four agents' findings independently point at prompts as the only 4.7-sensitive surface: Agent A (all at-risk patterns live in SKILL.md + reference files, none in Python/bash infrastructure), Agent B (all 5 observed failures are prompt-level instruction ambiguity), Agent C (Anthropic's published 4.7 guidance targets prompts + effort + SDK params), Agent D (no model-matrix change warranted). Agent E then framed this convergence as "harness re-think is scope creep."
- **Options**: (a) Full harness re-think per original topic framing, (b) Prompt-delta audit + capability adoption only, (c) Wait-and-see — let observed failures surface then fix reactively.
- **Recommendation**: **(b) Prompt-delta audit + capability adoption.** (a) is scope creep; (c) is defensible (user's "Prefer minimal fixes" preference) but 3 in-flight tickets responding to observed 4.7 failures (#067, #068, #069) already indicate a small proactive sweep pays for itself.
- **Provisional on OQ5**: Q3 found that `claude/reference/*.md` files are globally loaded and carry more weight than initially assumed. OQ5 flags that 4.7 may change conditional-loading semantics for these files. If OQ5 resolves unfavorably, "prompts" scope expands to include conditional-loading mechanics and reference-file surface, not just SKILL.md files. Keep DR-1 firm for SKILL.md + reference-file audit; revisit if OQ5 shifts the target.
- **Trade-offs**: We may miss non-prompt regressions (e.g., if 4.7's rate-limit signature differs from 4.6 and our adaptive throttler mis-classifies). Mitigation: monitor `api_rate_limit` event rates in `pipeline-events.log` post-migration for one week.

### DR-2: Skills to audit

- **Context**: 9 skills in #053's scope + 17 skills outside it + reference docs + CLAUDE.md surfaces. Two convergent 4.7-specific signals point at subagent-dispatch paths: Anthropic's own migration guide (Agent C) documents "fewer subagents by default" and "fewer tool calls" as concrete regressions; Agent B's observed-failure catalog (F1–F5) all lie in subagent→orchestrator return paths. Agent E synthesized this as the primary audit target.
- **Options**: (a) All ~30 skills, (b) 9 #053 skills only, (c) Subagent-dispatching skills (~7) + reference docs Claude reads globally (claude/reference/*.md, CLAUDE.md), (d) Only skills with confirmed observed-failure evidence.
- **Recommendation**: **(c).** Audit subagent-dispatching skills (`critical-review`, `research`, `pr-review`, `discovery`, `lifecycle`, `diagnose`, `overnight`) + `claude/reference/*.md` for the 6 at-risk patterns from Agent A (P1–P6). Skip skills like `backlog`, `commit`, `retro` that don't dispatch and haven't shown observed failures.
- **Trade-offs**: Non-dispatch skills could still have P3/P6 issues; deferring them is a calculated bet grounded in both published guidance (dispatch paths named as regression surface) and our own observed-failure distribution (100% dispatch-path). If a non-dispatch skill surfaces an observed 4.7 failure, expand scope at that point.

### DR-3: New capability adoption priority (revised for measurement discipline)

- **Context**: 8 new capabilities identified. Effort-budget matters. Critical-review Reviewer 3 surfaced a sequencing problem: DR-4 depends on clean 4.7 measurement baseline, and any Wave-1 prompt change before the baseline window contaminates the data.
- **Options**: Adopt all now, adopt top-N, defer all, or gate Wave 1 on DR-4 baseline collection.
- **Recommendation**: **Tier into 3 waves with explicit ordering.**
  - **Wave 0 (already resolved, no work)**: Adaptive thinking migration. Grep across `claude/**/*.py` returned zero matches for `budget_tokens|thinking.*enabled|interleaved-thinking`. We already comply by default. (Previously listed as Wave 1; struck after finding the grep was null.)
  - **Wave 1 (gate on DR-4 baseline)**: Remove progress-update scaffolding from long-running prompts (Approach D). **Must not ship until DR-4 has collected 2–3 overnight rounds of clean 4.7 baseline data.** Rationale: this change will shift `num_turns` and `cost_usd` distributions, so shipping it before the baseline contaminates the matrix-validation data DR-4 exists to gather. Alternative acceptable approach: ship Wave 1 first and collect the baseline with the scaffolding already removed — but then we lose the ability to measure the scaffolding's own impact.
  - **Wave 2 (ticket separately, after Wave 1 settles)**: Adopt `xhigh` effort default for overnight implement (C) — needs SDK wiring check and cost impact measurement. Also follow-up: remove length-control prompts and re-tune per best-practices.
  - **Wave 3 (defer indefinitely)**: Task budgets beta, high-res image support, interactive default model ID update (blocked on Claude Code shipping 4.7).
- **User decision (2026-04-18)**: Gate on DR-4 baseline. The 2–3 baseline rounds run first; scaffolding removal ships after. Preserves matrix-validation signal.
- **Trade-offs**: Ordering discipline costs 1–2 weeks. Buys: uncontaminated DR-4 baseline + ability to attribute any regression to a specific change.

### DR-4: Model matrix — no recalibration without data; baseline precedes Wave 1

- **Context**: Q4 + Q5 results show no clear capability-driven reason to shift tiers, but instrumentation gap prevents empirical validation.
- **Options**: (a) Preemptive shift of complex+high from opus → sonnet, (b) No shift, (c) No shift + add instrumentation to validate later.
- **Recommendation**: **(c).** Keep matrix as-is. Add a backlog item to instrument turn usage and cost per tier from `events.log`; revisit after 2–3 overnight rounds on 4.7.
- **Ordering requirement (added post critical-review)**: the 2–3 baseline rounds **must execute before** any Wave-1 prompt change from DR-3. Otherwise the `num_turns` and `cost_usd` data will reflect 4.7 + prompt changes simultaneously, and the matrix-validation signal will be lost. Explicit ordering: (1) ship 4.7 with existing prompts → (2) collect 2–3 rounds of baseline data → (3) only then ship Wave-1 prompt changes → (4) revisit matrix recalibration decision.
- **Trade-offs**: Pays opus rates for work sonnet may now handle during the baseline window; cost of one week of data gathering is <$50 at current volumes.

### DR-5: "Consider"-softening audit (scope corrected, may fold into DR-2)

- **Context**: Under 4.7, hedges (`consider`, `try to`, `if possible`) now genuinely weaken instructions. #053's rewrite table contained exactly one `consider` row: `think about → consider` (extended thinking NOT enabled). Critical-review Reviewer 2 corrected the initial scope estimate (30–40 sites → ~9 actual `\b[Cc]onsider\b` occurrences in `skills/`, 0 in `claude/reference/`). A further git-blame filter to identify specifically #053-introduced sites may reduce the candidate set to near-zero.
- **Options**: (a) Drop DR-5 entirely — treat `Consider` as one more at-risk pattern to catch during DR-2's P1–P6 audit pass, (b) Git-blame to find #053-introduced sites only (likely very small set), then apply three-category classification, (c) Audit all ~9 `consider` sites regardless of #053 origin using three-category classification (conditional-requirement / genuinely-optional / polite-imperative).
- **User decision (2026-04-18)**: **(a) — fold into DR-2.** Rationale: the three-category classification is itself a P2-family check (`Ambiguous conditional bypass`), and the actual sites are few enough that treating them as an extra scan-target during DR-2's audit pass is lower-overhead than a separate DR. Eliminating DR-5 also avoids the partial-reversal risk the critical-review flagged (undoing a 2-cycle-reviewed #053 decision with a single-pass judgment).
- **Follow-through**: DR-2's audit target list expands to include `consider` / `try to` / `if possible` hedge patterns alongside P1–P6. Applies only to the ~9 sites grep returns inside DR-2's scope (dispatch skills + `claude/reference/*.md`); sites outside DR-2's scope are not audited.
- **Trade-offs**: Loses the explicit "this is a new concern from 4.7" framing at the DR-level — but preserves the concern as a pattern within DR-2.

### DR-6: Observed-failure M1 pattern — codify via `output-floors.md` extension, dispatch-skill scope only

- **Context**: Critical-review Reviewer 4 corrected two premises: (1) F1–F5 resolve to three distinct mechanisms (M1 missing routing, M2 length-calibration, M3 missing output-gate), not one; (2) all 5 failures cluster in `lifecycle` clarify/specify/critical-review phases — the same phases `output-floors.md`'s Applicability section already scopes itself to. M1 (audience/routing) accounts for 3 of 5 failures and is the mechanism with the clearest structural fix.
- **Options**: (a) New reference doc `claude/reference/subagent-disposition.md` covering all dispatch-skill subagent-return patterns, (b) Extend `claude/reference/output-floors.md` with an Applicability-scoped Subagent Disposition section (lifecycle/discovery only — matches F1–F5 distribution), (c) Defer codification — let future lifecycles surface the pattern organically, accept ad-hoc fixes for now.
- **Recommendation**: **(b).** Extend `output-floors.md` with a new section scoped via the same Applicability pattern already in use. This matches the `claude/reference/` extend-not-add precedent, does not add conditional-loading weight (Q3/OQ5 concern), matches DR-2's dispatch-skill scope (no tension), and codifies only M1 — leaving M2 and M3 to per-ticket fixes since they don't share the same structural remediation.
- **Scope bound**: Codifies M1 only (the 60% dominant mechanism with a clean structural fix). Does not claim harness-wide applicability.
- **Trade-offs**: Narrower scope than originally proposed. Loses ability to fix M2/M3 via the same reference. Accepts that M2 (length-calibration in `critical-review`) and M3 (output-gating in `specify`) will be handled by #067/#069's per-ticket fixes without being promoted to a general pattern yet.
- **Deferred**: if M2 or M3 recurs in a second skill, revisit promoting those mechanisms to the reference.

### DR-7: Try the official automation command before hand-editing

- **Context**: Anthropic ships `/claude-api migrate this project to claude-opus-4-7` as an automated migration command in Claude Code.
- **Recommendation**: Before manually editing anything, run the built-in migration command on a throwaway branch and inspect what it changes. If it only touches SDK/API Python code (not SKILL.md prompts), that's fine — it still validates our SDK-side parameter migration. If it touches prompts, use its output as a starting point.
- **Trade-offs**: ~30-minute exploration cost; high information value regardless of outcome.

## Open Questions

1. **Does `/claude-api migrate this project to claude-opus-4-7` operate on SKILL.md prompts or only on Anthropic SDK/API Python code?** Answering requires running the command on a throwaway branch and diffing. This determines whether DR-7 absorbs most of DR-2+DR-5 or is narrower.

2. **Should overnight's effort default be `high` or `xhigh`?** Anthropic says `xhigh` is "the best setting for most coding and agentic use cases" and requires `max_tokens ≥ 64k`. Our current SDK calls in `claude/pipeline/dispatch.py` may not set effort explicitly. Needs: (a) confirm SDK wiring supports effort passing, (b) measure actual cost delta between effort tiers on a representative task. Answer determines the design of Wave-2 adoption.

3. **Does Anthropic's "use stronger language on observed failure" (skills best-practices) reconcile cleanly with "dial back aggressive imperatives" (migration guide)?** My current reconciliation (default soft, escalate on observed failure) is inference-level, not source-stated. A user-level decision is needed: when we encounter a `MUST`-style escalation post-migration, do we keep it, or normalize it back to soft and re-observe?

4. **What instrumentation do we need to empirically validate turn/budget limits?** Current `events.log` schema carries `num_turns` and `cost_usd` per dispatch, but we lack an aggregation pipeline that answers "for complex+high tasks in the past month, what's the 95th percentile turn usage?" A small script or dashboard widget would resolve this. Scope: does this get its own ticket, or live inside DR-4?

5. **Are `claude/reference/*.md` files globally loaded (via `~/.claude/CLAUDE.md` conditional table) reliably under 4.7, or does 4.7's stricter instruction-following change the conditional loading semantics?** Agent A flagged risk around `verification-mindset.md`'s `STOP` header and `parallel-agents.md`'s `Don't use when` list. Need a quick 4.7 invocation to confirm the reference files still load and fire correctly — otherwise the audit target shifts.

6. **Tone regression: is the voice change (less conciliatory, fewer emoji) a user-experience issue worth addressing at the CLAUDE.md or global-settings level?** This is a policy question, not a research question — flagging for the user to decide during Decompose.

---

### Resolved during research (not open)

- **Adaptive-thinking SDK breaking change**: grep across `claude/**/*.py` for `budget_tokens|thinking.*enabled|interleaved-thinking` returns zero matches. We do not set these anywhere in pipeline code. The SDK breaking change (`thinking: {type: "enabled", budget_tokens: N}` → 400) does not affect us. **No action required.** (Previously Wave-1 in DR-3; reclassified as Wave 0 / null work.)
- **"Consider"-audit scope estimate (30–40 sites)**: corrected to ~9 actual occurrences via grep. Framing that #053 introduced `consider` as a general softener was also wrong — #053's rewrite table contains exactly one `consider` row (`think about → consider`). See revised DR-5.
- **F-table root-mechanism conflation**: the five observed failures were initially listed under a single "common remediation pattern." Revised analysis identifies three distinct mechanisms (M1 audience/routing, M2 length-calibration, M3 output-gate). DR-6 now codifies M1 only.

---

## Critical-review cycle summary (2026-04-18)

The research artifact went through one `/critical-review` cycle with four parallel reviewers + Opus synthesis. Four major objections were surfaced:

1. **DR-1 single-source evidentiary weakness** — cited Agent E alone, with "~95% model-agnostic" uncited. **Applied**: broadened the scope framing to cite all five agents' convergent findings; made DR-1 provisional on OQ5.
2. **DR-5 empirical wrongness** — site count 30–40 was actually ~9, one cited example (`diagnose:25`) didn't contain `consider` at all, #053's `consider` usage was a narrow `think about` replacement, not a general softener. **Applied**: scope corrected, DR-5 recommends folding into DR-2 rather than running as a separate audit.
3. **DR-3 contaminates DR-4 baseline** — Wave 1 prompt changes shipping "with the audit" corrupt the measurement window DR-4 depends on; adaptive-thinking migration was null work per grep. **Applied**: reclassified adaptive thinking as Wave 0 / no-op; gated remaining Wave 1 item (progress-update scaffolding removal) on DR-4 baseline completion; added explicit ordering requirement to DR-4.
4. **DR-6 over-generalization + DR-2 tension** — F1–F5 resolve to 3 distinct mechanisms, all cluster in lifecycle phases; DR-6 proposed new-file reference doc despite `output-floors.md` extend-not-add precedent. **Applied**: F-table split into M1/M2/M3; DR-6 narrowed to dispatch-skill scope (matches DR-2), recommendation changed to extend `output-floors.md` Applicability-scoped section, codifies M1 only.

### Ask items — resolved 2026-04-18

Both Asks resolved to the research's recommendation:

- **Ask-1 (DR-3 Wave 1)**: Gate on DR-4 baseline. Scaffolding removal ships after 2–3 baseline rounds complete; attribution stays clean.
- **Ask-2 (DR-5)**: Fold into DR-2. `consider` / hedge patterns added to DR-2's audit scope for the ~9 in-scope sites; no separate audit DR.

All four critical-review objections are now resolved (Applied directly or Asked-and-answered). The artifact is ready for Decompose.
