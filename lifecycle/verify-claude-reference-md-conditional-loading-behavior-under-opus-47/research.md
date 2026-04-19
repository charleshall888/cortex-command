# Research: Verify claude/reference/*.md conditional-loading behavior under Opus 4.7

> Generated: 2026-04-18. Ticket: #084 (spike, high criticality, complex tier). Parent epic: #82. Deliverable: `research/opus-4-7-harness-adaptation/reference-loading-verification.md` (consumed by #085).

## Epic Reference

This ticket is decomposed from epic #82 (Opus 4.7 harness adaptation) — epic research at [research/opus-4-7-harness-adaptation/research.md](../../research/opus-4-7-harness-adaptation/research.md). This research addresses **Open Question 5** from that epic: whether 4.7's stricter instruction-following breaks the natural-language conditional-loading table in `~/.claude/CLAUDE.md`. The epic's DR-1 scope contraction (prompt-delta audit, not harness re-think) is *provisional on OQ5*; this ticket resolves that provisional — if reference files no longer load reliably, DR-1 must expand.

## Codebase Analysis

### Files that will change

- **Primary ticket-mandated deliverable**: `research/opus-4-7-harness-adaptation/reference-loading-verification.md` — exact path, consumed by #085.
- **Lifecycle working artifact**: this file (`lifecycle/verify-claude-reference-md-conditional-loading-behavior-under-opus-47/research.md`), plus eventual `spec.md` and `events.log` appends.
- **No reference-file or CLAUDE.md edits** — ticket scope is explicitly exploratory.

### Reference-file structural characterization

The conditional-loading table lives at `~/.claude/CLAUDE.md` lines 18–25 (symlinked to `claude/Agents.md` in-repo). Four rows map to five files:

| # | File | Trigger phrase in CLAUDE.md | 4.7-risky internal patterns |
|---|------|-----------------------------|-----------------------------|
| 1 | `claude/reference/context-file-authoring.md` | "Modifying SKILL.md files, Agents.md, CLAUDE.md, or reference docs" (shared row with #2) | "Red Flags — STOP if you're about to" 8-item negation list (lines 89–96) — P3 pattern. Conditional-bypass phrasing "Don't confuse human docs with agent docs" at line 77. |
| 2 | `claude/reference/claude-skills.md` | Same row as #1 | "Common Mistakes" table (lines 290–304) in negation form. "Don't split when:" list (lines 269–272) mirrors `parallel-agents.md`'s P3 pattern. |
| 3 | `claude/reference/verification-mindset.md` | "About to claim success, tests pass, build succeeds, bug fixed, or agent completed" | **Epic-flagged**. "Red Flags — STOP" section (line 44) with pure-negation list (lines 47–51). "The Iron Law" all-caps ASCII block `NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE`. "Common Rationalizations" all-negation table. Risk: binary halt-on-hedge under 4.7. |
| 4 | `claude/reference/parallel-agents.md` | "Deciding whether to dispatch agents in parallel" | **Epic-flagged**. "Don't use when" (lines 22–25) + "When NOT to Use" (lines 98–103) — all-or-nothing refusal risk. "Common Mistakes" list (lines 90–94). |
| 5 | `claude/reference/output-floors.md` | "Writing phase transition summaries, approval surfaces, or editing skill output instructions" | **Epic-flagged (low risk)**. "Precedence rule" (line 9) — P2 conditional-bypass. "Applicability" all-negation list (lines 70–76). DR-6 plans to extend this file, so correctness is load-bearing. |

All five files carry `audience: agent` frontmatter and are symlinked `~/.claude/reference/*.md` → `claude/reference/*.md`.

### Where passive evidence lives

- **Session transcripts**: `~/.claude/projects/-Users-charlie-hall-Workspaces-cortex-command/*.jsonl` — 210 JSONL files. Cross-file grep for the five reference filenames yields **118 occurrences across 15 files** — the corpus confirms recent loading events exist but is not date-bucketed against the Opus 4.7 cutover.
- **Lifecycle `events.log`**: 36 files reference these patterns; shows whether references were *applied* (e.g., `output-floors.md` appears as a spec requirement in recent lifecycles).
- **Retros** (`retros/2026-04-*`): 6 recent retros mention reference-file concepts; none document a "failed to fire" regression — weak negative evidence (absence, not disproof).
- **Epic F-table** (research.md lines 62–79): five catalogued 4.7-era failures (F1–F5) all resolve to SKILL.md-body instruction ambiguity; none attributed to reference-file non-loading — indirect positive evidence, but also consistent with no one having noticed yet.

### Existing tooling

- `justfile` recipes (`deploy-reference`, `check-symlinks`) manage symlink state but do not probe loading.
- `scripts/validate-callgraph.py` references `claude-skills.md` documentationally only.
- `bin/count-tokens`, `bin/audit-doc` — SDK-based token/audit tools; repurposable for structured probes.
- **`hooks/` SessionStart hook** injects `additional_context` — a potential probe-scaffolding point (but see Adversarial failure-mode 7 re: leakage risk).
- **No existing probe harness for reference-file loading exists**. The spike must design one (or pick one of the alternatives below).

### Conventions

- Deliverable format follows precedent of `research/opus-4-7-harness-adaptation/research.md` — but condensed per ticket's "one-page report" framing. Recommended minimum sections: Research Question (OQ5 restated), Methodology, Per-file verdict table, Remediation impact on #085, Open follow-ups, Limitations.
- Events logged to `lifecycle/{slug}/events.log` in NDJSON/YAML-block format already in use.
- Commits via `/commit` skill.

## Web & Documentation Research

### Core finding: the CLAUDE.md table uses a non-Anthropic-standard conditional-loading pattern

Anthropic's three documented conditional-loading primitives are:

| Primitive | Trigger mechanism | Loading |
|-----------|-------------------|---------|
| **Skills** | YAML `name` + `description` metadata match against current task | Lazy (metadata preloaded, SKILL.md on-demand) |
| **`.claude/rules/*.md` with `paths:` frontmatter** | Glob match on files Claude reads | Lazy, deterministic |
| **`@path` imports in CLAUDE.md** | File reference in CLAUDE.md body | **Eager** — loaded at launch, not conditional |

The user's `~/.claude/CLAUDE.md` table is a **natural-language "Read X when Y"** table — a fourth pattern not in the documented set. Per Claude Code memory docs: *"CLAUDE.md content is delivered as a user message after the system prompt, not as part of the system prompt itself. Claude reads it and tries to follow it, but there's no guarantee of strict compliance, especially for vague or conflicting instructions."*

This has two load-bearing implications:
1. Loading relies **entirely on the model's instruction-following**, not any Claude Code feature. There is no `@`-style auto-expansion or path-glob trigger.
2. "Reliability under 4.7" is undefined without a measured baseline — there is no published reliability number for 4.6 to compare against.

### Opus 4.7 behavioral shifts directly relevant

Quoted from `platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-7` and the migration guide:

- *"More literal instruction following, particularly at lower effort levels. The model will not silently generalize an instruction from one item to another, and will not infer requests you didn't make."*
- *"Claude Opus 4.7 respects effort levels strictly, especially at the low end. At `low` and `medium`, the model scopes its work to what was asked rather than going above and beyond."*
- *"Fewer tool calls by default, using reasoning more. Raising effort increases tool usage."*
- *"Fewer subagents spawned by default. Steerable through prompting."*
- *"Positive examples showing how Claude can communicate with the appropriate level of concision tend to be more effective than negative examples or instructions that tell the model what not to do."*

Direct implications for this table:
- Natural-language triggers that rely on model extrapolation ("Modifying SKILL.md files" → "writing agent prompts") are more likely to **under-fire** under 4.7.
- "Fewer tool calls by default" makes spontaneous "let me read that reference" behavior less likely — the cost of a reference-file read must be implicit in 4.7's effort budget.
- STOP-header and negation-only patterns inside the reference files are unaddressed by 4.7-specific docs — gap.

### Verification primitives Anthropic documents

- **`InstructionsLoaded` hook** (from `code.claude.com/docs/en/memory`): *"Use the `InstructionsLoaded` hook to log exactly which instruction files are loaded, when they load, and why."* This is the most authoritative primitive for the loading question (Q1). Limits: tells you whether a file was loaded, not whether its content was *applied*.
- **`/memory` command**: *"Run `/memory` to verify your CLAUDE.md and CLAUDE.local.md files are being loaded."* Complementary sanity check.
- **Evaluation-driven development for Skills** (best-practices doc): Establish baseline without the skill, create scenarios that test gaps, iterate. Generalizes to reference-file probing.
- **"Claude A / Claude B" testing pattern**: one Claude iterates the reference doc; another Claude tests it on real tasks.
- **Observable signals to watch**: *"Missed connections: Does Claude fail to follow references to important files? Your links might need to be more explicit or prominent."*

### Community methodology

Scott Spence's sandboxed-evals approach (Daytona-isolated `claude -p` runs, parse JSONL for `Read` tool_use events, pair trigger-matching with non-matching prompts, measure false negatives and false positives, replicate for consistency) — validated on Sonnet 4.5 / Haiku but not Opus 4.7. MLflow evaluation patterns (Anthropic-co-authored) record skill invocation during traces and LLM-judge outputs — directly generalizable to reference-file loading.

### Documentation gaps

1. No Anthropic guidance on CLAUDE.md natural-language conditional tables as a pattern.
2. No 4.7-specific guidance on STOP headers, negation-only lists, or all-or-nothing prohibition patterns.
3. No published A/B methodology for verifying a specific referenced-file load under 4.7.
4. No data on 4.7's extrapolation radius for similar-but-not-listed triggers — precisely the question that matters here.

## Requirements & Constraints

### Relevant requirements

- **`requirements/project.md` line 46**: "Global agent configuration (settings, hooks, reference docs)" is explicitly **in-scope** for this project. The reference files under test are not out-of-scope infrastructure.
- **`requirements/project.md` lines 60–65**: The project.md file *itself* uses the same natural-language conditional-loading pattern — which means the mechanism's reliability has a second-order effect on whether requirements docs route correctly. A mechanism-wide regression would affect more than the five files named in the ticket.
- **`requirements/pipeline.md` line 127**: Treats `output-floors.md` as authoritative for a runtime convention ("Orchestrator rationale convention"). At least one of the five reference files is load-bearing for spec-stated behavior, not just author-guidance.
- **`requirements/project.md` line 13** (Handoff readiness): *"A feature isn't ready for overnight until the spec has no open questions, success criteria are verifiable by an agent with zero prior context, and all lifecycle artifacts are fully self-contained."* Translated to this spike → #085 handoff: the one-page report is the entire communication channel to #085; it must be self-contained and zero-context verifiable.
- **`requirements/project.md` line 17**: *"Research before asking. Don't fill unknowns with assumptions — jumping to solutions before understanding the problem produces wasted work."* Closest directive for methodology: investigate empirically, do not infer.

### Architectural constraints

- File-based state convention — reference files are plain markdown at known paths.
- Sandbox / permission rules apply to any probe tooling.
- `requirements/project.md` line 33 (Context efficiency): project values **deterministic, non-model-judgment** mechanisms for context shaping. The conditional-loading table is, by contrast, model-judgment-driven — structural tension to surface (not resolve here).

### Notable absences

- **No methodology rigor bar for spikes or verification work** anywhere in requirements. No sample-size requirements, no reproducibility expectations.
- **No constraints on modifying `~/.claude/CLAUDE.md` during a spike** — the read-only scope is self-imposed.
- **No service-level expectation for conditional loading reliability** — requirements never state "reference docs must load X% of the time." The spike must infer its own evidence bar.
- **No reference methodology for verifying Claude Code's own behavior** — multi-agent.md covers spawning and dispatch, not model-behavior verification.

## Tradeoffs & Alternatives

### Alternative A: Interactive probe-pair sessions

Hand-craft prompts matching each trigger in a fresh 4.7 session; observe behavior.
- Pros: matches real usage, zero new code, ticket-suggested.
- Cons: n=1 per probe, subjective grading, cannot separate "file fired" from "model would have done it anyway under 4.7," contamination risk from trigger phrasing.
- Time: 2–4h. Confidence: LOW–MEDIUM.

### Alternative B: Scripted batch probing via Claude Agent SDK

Use `claude/pipeline/dispatch.py` scaffolding, n≥20 invocations per file × 2 conditions (probe + control).
- Pros: statistical confidence, separates trigger-fired from natural base-rate, reusable for 4.8.
- Cons: 1–3 days of implementation, probe operationalization is the hard problem, over-engineered for a one-page report.
- Time: 1–3 days. Confidence: HIGH if probe set well-designed; LOW otherwise.

### Alternative C: Passive evidence mining from existing 4.7 transcripts

Grep the 210 JSONLs, lifecycle events.log files, and retros for Read tool calls against reference paths; match against expected behavioral patterns.
- Pros: zero contamination, n=hundreds of sessions, cheap (1–2h), methodology already proven in epic research (Agent B's F-table).
- Cons: answers "did it fire in past sessions" — weak for over-firing questions (passive logs show what happened, not what was suppressed or nearly fired).
- Time: 1–2h. Confidence: HIGH for binary broken/not-broken; LOW for nuanced over-firing.

### Alternative D: CLAUDE.md A/B variation in a worktree

Remove one row, probe, compare to baseline.
- Pros: establishes causation; only method that separates "reference caused behavior" from "baseline model behavior."
- Cons: symlink resolution means naive worktree approach fails (global `~/.claude/CLAUDE.md` symlink still resolves to original — see Adversarial failure-mode 7). Mutating the live file risks mid-session contamination of the probing agent itself.
- Time: 4–6h plus isolation design. Confidence: HIGH per row tested, but only for the load-bearing question.

### Alternative E: Direct introspection

Ask the model whether a reference file is loaded.
- Pros: trivially cheap.
- Cons: VERY LOW confidence — models confabulate context-window membership. Sanity-check only, never primary evidence.

### Alternative F (proposed by Tradeoffs agent): Hybrid — passive mining first, targeted active probes as fallback

- Passive mining for all 5 files → classify as "confirmed loading" (≥2 positive firings) or "needs active probe."
- Active probes only for files with insufficient passive signal.
- A/B variation as a last-resort fallback for ambiguous probe results.
- Time: 2–6h depending on fallback depth. Confidence: MEDIUM–HIGH overall, varies by file.

### Alternative G (proposed by Adversarial agent): Decomposed methodology per deliverable question

The ticket has three deliverable questions with fundamentally different evidence regimes. The report should decompose them rather than using one methodology for all three:

- **Q1 (do they load when triggers fire)**: `InstructionsLoaded` hook (Anthropic-documented primitive — deterministic, Read-event-level signal). Fallback: JSONL grep. Acceptable as HIGH confidence.
- **Q2 (does 4.7's stricter instruction-following change behavior — STOP over-firing, all-or-nothing refusal)**: **paired probes** per file — one canonical-trigger prompt that should fire, one near-miss prompt that should *not* fire. n≥5 paraphrase probes per file to cover trigger-phrasing robustness. State explicit confidence level; do not assert reliability.
- **Q3 (which files need P3 remediation)**: depends on Q2; compute from Q2 verdicts + explicit section-level pattern probes (Iron Law on hedges, "Don't use when" on boundary cases, Precedence rule on conflicting inline fields).

### Recommended approach

**Alternative G (decomposed per-question methodology) with Alternative F as the underlying investigator.** The tradeoff analysis on its own pointed at F, but the adversarial review correctly observed that F's strongest evidence is for Q1 and weakest for Q2 — the ticket's hard half. G addresses this by pairing F's passive mining / `InstructionsLoaded` hook for Q1 with explicit active probes (paired trigger + near-miss; section-level pattern probes) for Q2.

**Concrete protocol** (to be refined in spec):
1. Q1 baseline — extract `InstructionsLoaded` hook data (if installed) or grep 210 JSONLs with date-bucketing against the Opus 4.7 cutover, for each of the 5 reference files.
2. Q1 verdict — per-file loading rate, flagged by confidence tier (sample size, date-bucketing hygiene).
3. Q2 active probes — per file: 2 canonical-trigger probes + 3 near-miss / paraphrase probes. For files with epic-flagged internal patterns (`verification-mindset.md`, `parallel-agents.md`, `output-floors.md`): add section-level pattern probes (Iron Law on hedges; "Don't use when" on boundary dispatch cases; Precedence rule on conflicting inline fields).
4. Q3 synthesis — per-file remediation recommendation based on Q1 + Q2 verdicts.
5. Limitations section — explicit on sample size, baseline gap, contamination risks, and the fact that the 5-file verdict is a proxy for mechanism-wide behavior.

## Adversarial Review

The adversarial agent surfaced 8 failure modes and 2 shaky assumptions. These fed directly into the recommended approach (Alternative G) above. Key points:

1. **Evidence-type mismatch**: Passive logs answer Q1 (loading) well and Q2 (over/under-firing) poorly. The original hybrid recommendation used passive mining as primary for both — backwards for the harder half of the ticket.
2. **`InstructionsLoaded` hook limits**: deterministic for "did it load," silent on "did the agent apply it." Cannot replace behavioral probes for Q2.
3. **Unverified 4.6 baseline**: the ticket's "changed under 4.7" framing presumes a 4.6 reliability number that doesn't exist. Any claim must either include a 4.6 cohort measurement or reframe to absolute ("current 4.7 loading rate is X%") without a delta claim.
4. **Load-vs-apply conflation**: 4.7's literal-interpretation regime means a file can load correctly and still behave differently. None of A/C/F on their own distinguish these — G's section-level probes are necessary.
5. **JSONL cohort hygiene**: 210 transcripts span Opus 4.6 and 4.7 eras without date-bucketing, CLAUDE.md revision tracking, or task-mix normalization. Naive before/after comparisons confound with content changes, Claude Code client updates, task-mix drift.
6. **Low-rigor report shape risk**: a one-page report with n≈10 probes will default to "appears reliable"; #085 will crystallize against a verdict the evidence doesn't support. The clarify-critic already escalated to high-criticality on this reasoning; the methodology must reflect the escalation.
7. **Isolation gaps in Alternative D**: `~/.claude/CLAUDE.md` is symlinked; a worktree variation doesn't take effect without repointing the global symlink, which contaminates the probing agent and any concurrent sessions.
8. **Three conflated mechanisms**: the ticket scope combines (a) mechanism reliability, (b) trigger-phrasing robustness, (c) intra-file pattern integrity under 4.7. The report must decompose these or risk answering only one.
9. **Scope assumption**: the 5-file verdict is a proxy for mechanism-wide behavior — `requirements/project.md` uses the same pattern. #085 decisions will implicitly extend. Needs a Limitations-section flag.
10. **Artifact-shape assumption**: a one-page spike report may be underpowered for a high-criticality gate. Either raise rigor or include an explicit reopener clause so #085 can expand scope on later contradicting evidence.

## Open Questions

- **OQ-A (methodology — to be resolved in Spec)**: Does the spec commit to Alternative G (decomposed per-question methodology) as proposed, or accept a lighter protocol (e.g., F alone) on rigor-vs-cost grounds? **Deferred**: will be resolved in the Spec phase by confirming the methodology choice with the user; the Research phase has surfaced the tradeoff but the final call is a value-vs-cost decision that belongs in the approval surface.
- **OQ-B (baseline strategy — to be resolved in Spec)**: Does the spec include a 4.6 baseline cohort (date-bucketed JSONL split around the Opus 4.7 cutover), or does the report explicitly disclaim any "changed under 4.7" delta claim and reframe to absolute current-state? **Deferred**: will be resolved in the Spec phase by picking one of the two framings based on what the downstream #085 decision actually needs.
- **OQ-C (InstructionsLoaded hook availability — to be verified during Implement)**: Is the `InstructionsLoaded` hook available in the installed Claude Code version on this machine? **Deferred**: verification requires a CLI check at implement time; if the hook is unavailable, the spec must fall back to JSONL grep with explicit caveats. Does not block Spec.
- **OQ-D (scope boundary — to be decided in Spec)**: Does the deliverable report acknowledge that the same natural-language conditional-loading pattern is used in `requirements/project.md`, and therefore the 5-file verdict is a proxy for mechanism-wide behavior? Or is the report scoped strictly to the five named files with that implication elided? **Deferred**: will be resolved in the Spec phase — this is a scope-framing decision that belongs on the approval surface.
- **OQ-E (report structure — to be resolved in Spec)**: Is the one-page constraint binding, or can the report expand if Alternative G's per-question decomposition requires more space? **Deferred**: will be resolved in the Spec phase — the constraint came from the ticket body but the clarify-critic escalated criticality in a way that may justify expansion.
- **OQ-F (reopener clause — to be resolved in Spec)**: Should the report include an explicit reopener clause stating "if #085 execution surfaces evidence contradicting this report, #085 must expand scope rather than defer to this verdict"? **Deferred**: will be resolved in the Spec phase — this is a policy decision about how much confidence the report's verdict should carry into #085.

All six open questions are explicitly deferred to the Spec phase with rationale. No bare unannotated questions remain.
