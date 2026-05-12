# Research: Audit dispatch-skill prompts and reference docs for 4.7 at-risk patterns

## Epic Reference

This ticket scopes from [research/opus-4-7-harness-adaptation/research.md](../../research/opus-4-7-harness-adaptation/research.md) — the epic defined 7 at-risk prompt patterns (P1–P7) and a 3-mechanism remediation taxonomy (M1–M3); #85 implements the audit that epic §"Six at-risk patterns not covered by #053" identifies as the concrete deliverable.

Spike inputs that feed this research:
- [#083 claude-api migrate results](../../research/opus-4-7-harness-adaptation/claude-api-migrate-results.md) — `/claude-api migrate` is non-destructive to the audit surface; handles model-ID swap + API parameters only, does NOT auto-rewrite prompts.
- [#084 reference-loading verification](../../research/opus-4-7-harness-adaptation/reference-loading-verification.md) — 4/5 reference files load reliably under 4.7; `verification-mindset.md` is Q1 LOW and requires validation probe before any rewrite.

## Codebase Analysis

### Surface reconciliation (CRITICAL — ticket scope is stale)

The ticket body names "7 dispatch skills" and "5 reference files." Reality differs:

| Ticket claim | Reality | Correction |
|--------------|---------|------------|
| `skills/critical-review/` | ✓ exists, dispatches via Agent tool | keep in scope |
| `skills/research/` | ✓ exists, dispatches 3–5 parallel agents | keep in scope |
| `skills/pr-review/` | ✗ **EXTRACTED to a separate plugin repo** (see `lifecycle/extract-optional-skills-to-plugin/plan.md:76-84` Task 7; removed in commit `9ae4a85`) | **DROP from scope** — file does not exist |
| `skills/discovery/` | ✓ exists | keep in scope |
| `skills/lifecycle/` | ✓ exists | keep in scope |
| `skills/diagnose/` | ✓ exists | keep in scope |
| `skills/overnight/` | ✓ exists BUT **does not dispatch subagents** — `SKILL.md` has zero `Agent(` / `Task(` calls; orchestrates via the bash runner, which is a separate shell process | **DROP from scope** — not a dispatch skill per DR-2's definition |
| `skills/refine/` | Not in ticket scope — BUT actually dispatches `/research` (SKILL.md:94) AND is flagged HIGH-RISK P2 in epic research.md:56 (path-guard at lines 49–51, 83) | **ADD to scope** |
| `claude/Agents.md` (→ `~/.claude/CLAUDE.md`) | Not in ticket scope — BUT loaded at **every session start globally across all projects**, larger blast radius than any conditional-load reference file | **ADD to scope** |

**Revised audit surface: 6 dispatch skills + 6 reference/global files = 12 surfaces** (net-flat count, different composition).

### Per-site P1–P7 enumeration

**Grep baseline (corrected — Agent 4's count was 3× undercount)**:
- `do not` / `Do not` occurrences across 6 dispatch skills + their references + 5 reference files: **~124 total** (critical-review=12, lifecycle+references=81, research=11, diagnose=3, overnight=8, discovery+references=8, pr=1)
- `\b[Cc]onsider\b` occurrences in `skills/`: **9 total**
- `do not omit, reorder, or paraphrase` occurrences (P5 archetype): **3 sites in lifecycle/references/ (`research.md:57`, `plan.md:27`, `implement.md:189`)** — Agent 1 initially reported "P5: zero true positives"; adversarial challenge surfaced these missed sites

After per-site judgment and preservation-rule filtering (see exclusions below), realistic remediation surface: **30–50 sites** (not Agent 4's 15–30, not ticket's 84). Spec phase must re-run grep baselines against the corrected scope.

**High-confidence true-positive sites** (evidence for Plan; Spec should re-validate per-site under 4.7 literalism):

| Pattern | Site | Quoted text | Risk | Preservation status |
|---------|------|-------------|------|---------------------|
| P1 | `critical-review/SKILL.md:22` | "omit the `## Project Context` section entirely — do not inject an empty placeholder" | HIGH — double condition + dual negation | Output-channel directive (#053 PR2); excluded from behavioral remediation, but format may be rewritable |
| P1 | `critical-review/SKILL.md:138` | "Skip sections where the agent returned no findings — do not emit empty section headers" | HIGH — dash-separated dual negation | Output-channel directive (#053 PR2); same status |
| P1 | `lifecycle/SKILL.md:180` | "If no matching backlog item was found, omit the heading and body line entirely" | MED — explicit condition + dual omit | Output-channel directive |
| P1 | `lifecycle/references/review.md:90` | "When drift is NOT detected, omit the Suggested Requirements Update section entirely" | MED — explicit conditional + omit | Output-channel directive |
| **P2** | `refine/SKILL.md:49-51` | "Only lifecycle/{lifecycle-slug}/research.md satisfies this check. Any file … does NOT satisfy this check regardless of path." | **HIGH** — flagged in epic research.md:56 | Control-flow gate (#053 PR3) — but gate scope is itself ambiguous |
| **P2** | `refine/SKILL.md:83` | Path guard with triple-condition scoping ("Only X satisfies … does NOT count … does NOT satisfy … If X does not exist, always run Research") | **HIGH** — gate-scope mis-parsing risk | Control-flow gate; load-bearing |
| P3 | `critical-review/SKILL.md:103` | "Do not cover other angles. Do not be balanced." | MED — two negations, no positive alternative | **Anchored preservation** (#053 line 83) — distinct-angle rule; but see Adversarial concern re 4.7 re-validation |
| P3 | `critical-review/SKILL.md:140` | "Do not be balanced. Do not reassure. Find the problems." | LOW — mitigated by positive frame | Anchored preservation (#053) — "Do not soften or editorialize" |
| P3 | `critical-review/SKILL.md:179` | "Do not be balanced. Do not reassure. Find the through-lines and make the strongest case." | LOW — strong positive frame | Anchored preservation; **Adversarial flag: highest-consequence P3** — synthesizer's sole output constraint; 4.7 may drop all hedging/uncertainty markers |
| P3 | `lifecycle/references/clarify-critic.md:50` | "Return a list of objections only … Do not classify or categorize them. Do not recommend fixes. Do not reassure." | MED — 3 negations, implicit positive | Phase-transition floor (#053 PR4) |
| P3 | `lifecycle/references/clarify-critic.md:63` | "Do not be balanced. Do not summarize what the assessment got right." | MED — 2 negations, no positive | Phase-transition floor |
| P3 | `claude/reference/verification-mindset.md:44-51` | 6-item "Red Flags - STOP" negation-only list | HIGH — globally loaded; **Adversarial flag: compound P3+P6 hazard** (list-as-exhaustive framing) | **Pass 2 target** — probe required first |
| P4 | `lifecycle/SKILL.md:57-73` | Worktree-Aware Phase Detection block: ~16 lines of natural-language conditional/short-circuit logic | MED — implicit sequential dependency | Load-bearing control flow |
| P4 | `lifecycle/SKILL.md:152` | "Guard: If `lifecycle/{slug}/index.md` already exists, skip this entire block — do not overwrite" | LOW — explicit guard | Control-flow gate |
| **P5** | `lifecycle/references/research.md:57` | "substitute the variables but do not omit, reorder, or paraphrase any instructions" | MED — canonical P5 archetype per epic research.md:59 | Not preservation-ringed; live audit target |
| **P5** | `lifecycle/references/plan.md:27` | Same phrase | MED | Live audit target |
| **P5** | `lifecycle/references/implement.md:189` | Same phrase (within task-scope constraints) | MED | Live audit target |
| P6 | `critical-review/SKILL.md:28-56` | "Select angles from the following menu" + categorized example list | MED — "menu" framing risks closed-set interpretation | Angle-menu rule is anchored preservation; framing may be rewritable |
| **P7 variant** | `claude/reference/context-file-authoring.md:87` (second "Red Flags - STOP") | Found during adversarial scan; parallel structure to verification-mindset.md | MED | — |

### Pass 3 `[Cc]onsider` git-blame result (null for #053-origin)

All 9 `consider` sites in `skills/` predate #053's completion SHA. **Zero sites introduced by #053's `think about → consider` rewrite row.** Pass 3 as originally scoped ("#053-specific sites") has zero work cells. However, 5 of 9 sites are classified as **(a) conditional-requirement** — "consider" softens actions that are required given the preceding condition:

- `skills/diagnose/SKILL.md:74` — "consider spawning a competing-hypotheses team" (action required when root-cause unclear + 2+ theories)
- `skills/pr/SKILL.md:34` — "Consider the type of change" (required analysis for PR body)
- `skills/morning-review/references/walkthrough.md:142` — "Consider each configured entry's label and command" (required step-2 of demo selection)
- `skills/lifecycle/references/clarify-critic.md:77` — "consider alternatives" (part of self-resolution)
- `skills/lifecycle/references/plan.md:277` — "evaluate it critically and consider alternatives" (required unless validated)

Adversarial framing: **Pass 3 as scoped is null**. Spec must decide: (a) drop Pass 3 entirely, or (b) broaden Pass 3 to "audit all `consider` sites regardless of origin" (which changes the methodology and revives DR-5 option c that epic research rejected).

### verification-mindset.md structural inventory (for Pass 2)

106 lines total. Structural at-risk content:

- **Lines 9–31 (Iron Law + Gate Function)**: Opens with "NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE" (negation-only framing) followed by a 5-step positive gate. Under 4.7 literalism, the opening negation may block before the positive gate is reached.
- **Lines 34–42 (Common Failures table)**: negations paired with positive requirements ("Tests pass | requires Test command output: 0 failures") — mitigated.
- **Lines 44–51 (Red Flags - STOP)**: 6-item negation-only list with no positive alternative. **Adversarial flag: compound P3+P6 hazard** (list presented as exhaustive).
- **Lines 85–95 (Common Rationalizations table)**: 2-column excuse/reality format, mitigated.

**Adversarial position**: the entire file is negative-framing. A one-section patch to Red Flags leaves the other four sections unpatched; whichever fires next under 4.7 will be blamed on "patched the wrong section." Consider whole-file rewrite (Iron Law → "Before claiming: positive checklist"; Gate Function → retain with positive framing; Red Flags → "Verification checklist before completion claim"; Rationalizations → delete or convert to "instead of X, do Y").

### Integration points and dependencies

1. **Global symlink blast radius**: `claude/reference/*` → `~/.claude/reference/*`; `claude/Agents.md` → `~/.claude/CLAUDE.md`. Edits propagate to all local projects on commit. A rewrite of `verification-mindset.md` affects every agent's verification gate. `Agents.md` loads at every session start globally.
2. **Preservation-rule dependency ring**: 5 P3 candidate sites are preservation-ringed under #053's anchored decisions. `critical-review/SKILL.md:179` (distinct-angle) and `critical-review/SKILL.md:140` ("Do not soften or editorialize") are load-bearing for the critical-review differentiator from `/devils-advocate`; any rewrite risks silent regression in adversarial review quality.
3. **P2 gate scope in `refine/SKILL.md`**: affects whether every lifecycle feature re-runs `/research` on path-guard mis-match. Misparse under 4.7 could cause redundant research runs (extra spend) or skipped research (broken handoff to Spec).

### Conventions to follow (from #053 rewrites)

- Pattern-bucketed commits (one commit per pattern across all files), matching #053 Task 8
- Candidate-enumeration file (`axis-b-candidates.md` equivalent) inside `lifecycle/{slug}/` for per-site exclusion decisions
- Grep-baseline before and after (`\bdo not\b`, `\b[Cc]onsider\b`, etc.) with explicit diff reporting
- Spot-check two high-risk skills (`critical-review` on a complex plan, `lifecycle` on resuming a phase) in a throwaway session after remediation
- Preservation-anchor grep post-edit (confirm all 10 anchored strings still present)

## Web Research

### Anthropic 4.7 prompt-engineering guidance (direct confirmation of pattern taxonomy)

Key verbatim sources:

- **[docs.claude.com whats-new-claude-4-7](https://platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-7)** — "More literal instruction following, particularly at lower effort levels. The model will not silently generalize an instruction from one item to another, and will not infer requests you didn't make."
- **[claude-prompting-best-practices — Prompting Claude Opus 4.7 section](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)** — "Positive examples showing how Claude can communicate with the appropriate level of concision tend to be more effective than negative examples or instructions that tell the model what not to do." + "If you need Claude to apply an instruction broadly, state the scope explicitly (for example, 'Apply this formatting to every section, not just the first one')."
- **[Opus 4.7 migration guide](https://platform.claude.com/docs/en/docs/about-claude/models/migrating-to-claude-4)** — "A prompt and harness review may be especially helpful for migration to Claude Opus 4.7" + "Re-baseline response length with existing length-control prompts removed, then tune explicitly."

### Pattern taxonomy verification

| Ticket pattern | Publicly confirmed by Anthropic? | Evidence |
|---|---|---|
| P1 Double-negation | Inferred, not independently named | Consistent with literalism + "positive examples beat negative rules" |
| P2 Ambiguous conditional bypass | Inferred | Consistent with "state scope explicitly" |
| P3 Negation-only prohibition | **Directly confirmed** | Best-practices doc explicitly; migration guide behavior #1–#2 |
| P4 Multi-condition gate w/ implicit short-circuit | Inferred | Consistent with literalism mechanism |
| P5 Procedural order dependency | Inferred | Consistent with literalism |
| P6 Examples-as-exhaustive | **Directly confirmed** | "Will not silently generalize an instruction from one item to another"; best-practices example diversity guidance |
| P7 `consider`/hedges | **Directly confirmed** | Best-practices doc: "only report high-severity," "be conservative," "don't nitpick" called out by name as now-faithfully-followed softeners |

**5 of 7 patterns directly confirmed by Anthropic; 2 (P1, P4) are mechanism-consistent but not independently named.** Epic taxonomy is well-anchored, not over-fit.

### Three additional remediation mechanisms (Anthropic-backed)

Beyond the epic's M1/M2/M3:

- **M4 context + rationale pattern**: Anthropic explicitly recommends explaining *why* an instruction matters when negation is unavoidable (e.g., "Your response will be read aloud by TTS, so never use ellipses"). Preserves negation when rationale is load-bearing. A softer variant of M1 for sites where clean inversion isn't possible.
- **M5 downstream-filter framing**: Code-review example from Anthropic — "report everything, filtering happens elsewhere." Lightweight output-gate variant for quality/severity thresholds.
- **M6 effort-level as remediation lever**: 4.7 respects effort strictly. Some literalism issues resolve better by raising effort (`high` → `xhigh`) than by prompt rewrite. Not a prompt remediation, but a triage dimension.

### New pattern candidate from Web (not in epic taxonomy)

**P8 candidate — severity-gate framing**: "only report important," "skip minor issues," "don't surface nits" specifically called out by Anthropic as 4.7 recall killers. Remediation: M5 downstream-filter framing. Spec phase should decide whether to add P8 explicitly.

### Other findings

- `/claude-api migrate` scope confirmed narrow: only model IDs, breaking API params, prefill replacement, effort calibration. Does NOT auto-rewrite prompts.
- **Fewer subagents by default** and **fewer tool calls by default** are structural behavior changes, not just prompt patterns. Dispatch skills assuming fan-out may silently become serial under 4.7 without explicit "spawn multiple subagents in the same turn" instruction.
- **Effort-level interaction with literalism**: worst at low/medium effort, partially suppressed at high/xhigh. Different dispatch skills run at different effort levels — pattern severity varies across call sites. **Audit dimension missing from original scoping.**
- **HN discussion of the 4.6→4.7 system-prompt diff** (simonwillison.net): the new `<acting_vs_clarifying>` section actively breaks workflows that want upfront clarification — relevant for dispatch skills relying on Claude-inferred clarification phases.

## Requirements & Constraints

### Hard constraints that gate remediation

- **Symlink architecture (CLAUDE.md:20-31)**: `skills/*` → `~/.claude/skills/*`, `claude/reference/*` → `~/.claude/reference/*`, `claude/Agents.md` → `~/.claude/CLAUDE.md`. Edits propagate globally to all local projects. Rollout safety depends on testing in context before symlink refresh.
- **Global conditional-loading table in Agents.md** routes reference files by trigger phrase. Vague/generic SKILL.md descriptions break auto-loading. Preserve exact trigger phrasings.
- **Description budget (claude-skills.md:59-65)**: 2% of context window (~16,000 chars) shared across ALL skills (global + project). Dispatch skill descriptions must be concise.
- **Output floor field names** (Decisions/Scope delta/Blockers/Next and Produced/Trade-offs/Veto surface/Scope boundaries) are load-bearing for statusline, dashboard, and morning report. Already under #053 preservation rule 4; keep preserving.
- **File-based lifecycle artifacts bypass compaction** (output-floors.md:63-75): research.md, spec.md, plan.md, review.md, events.log. Orchestrator rationale only in conversation is compaction-vulnerable; dispatch skills must append rationale to events.log.
- **Forward-only phase transitions** (pipeline.md:18-25): dispatch skills writing state must follow atomic-write patterns. Status values `pending | running | merged | paused | deferred | failed` — prompt rewrites must not alter these.
- **2-cycle rework loop cap** (pipeline.md:59-65): review dispatch skills must respect APPROVED/CHANGES_REQUESTED/REJECTED verdicts and the 2-cycle cap.
- **No direct `git commit`** (Agents.md:7-10): dispatch skills writing to git must delegate to `/commit` skill.

### Tests scaffolding available

- `tests/test_skill_contracts.py` — validates SKILL.md frontmatter via `scripts/validate-skill.py`
- `tests/test_skill_callgraph.py` — validates skill calling relationships
- `tests/test_hook_commit.sh` — precedent for lint-style hook tests (can extend for pattern-grep regression guards)
- `tests/test_skill_behavior.sh` — behavioral test scaffolding
- `tests/test_events_contract.py` — events.log schema validation

### Preservation ring-fence requires re-validation under 4.7

**Adversarial finding (from Agent 5)**: #053's 10 anchored preservation decisions were calibrated against 4.5/4.6 behavior. Under 4.7 literalism, ring-fenced instructions like `critical-review/SKILL.md:179` ("Do not be balanced. Do not reassure. Find the through-lines") may themselves exhibit the P3 failure mode — 4.7 synthesizers may drop ALL caveats/hedging under this exact wording, producing false-certainty adversarial reviews.

**Recommendation for Spec**: don't pre-accept the ring-fence. Spike one ring-fenced site through a real Opus 4.7 synthesis (e.g., critical-review on a real artifact) and inspect output for dropped caveats. If the preservation rule is failing under 4.7, flip the exclusion. Otherwise honor it.

## Tradeoffs & Alternatives

### Axis A — Commit strategy

| Option | Pros | Cons | Recommended |
|--------|------|------|-------------|
| A1 Pattern-bucketed (one commit per P1–P8 across all files) | Matches #053's validated practice; per-pattern revert; grep-baseline rationale per commit | Can degenerate to 1–2-file commits if patterns collapse | **PRIMARY** |
| A2 Per-skill-file | Smallest blast radius per commit; clean `git blame` | Loses pattern narrative; inflates commit count; fights Pass 3 traceback | Backup for whole-file rewrites (verification-mindset.md) |
| A3 Single mega-commit | Atomic | Unrevertable at pattern level; obscures methodology | Rejected |
| A4 Audit-report-then-PR | Durable audit artifact; decouples discovery/fix | Duplicates `axis-b-candidates.md` pattern #053 already has; low marginal value | Rejected (subsumed by A1 + candidates.md) |

**Recommended: A1 primary, A2 for whole-file rewrites (e.g., verification-mindset.md if rewrite chosen).**

### Axis B — Decomposition

| Option | Description | Recommended |
|--------|-------------|-------------|
| B1 Single-ticket | Execute all passes under #85 | Default, with caveats |
| B2 Per-pass | Split to Pass 1 / Pass 2 / Pass 3 child tickets | **Pass 2 MUST split out per Adversarial recommendation 2** |
| B3 Per-pattern | One ticket per P1–P8 | Rejected — over-decomposed for realistic site density |

**Recommended (adversarial-adjusted): split Pass 2 into child ticket NOW** (not conditionally), because the probe-dir hypothesis is Q1-only resolvable and Q2 has no behavioral test. Complete Pass 1 + (possibly Pass 3) under #85. Drop Pass 3 or re-scope if Spec broadens beyond #053-origin.

### Axis C — verification-mindset.md probe design (ONLY RELEVANT IF PASS 2 STAYS UNDER #85)

| Option | Compliance with #084 reopener | Sufficiency |
|--------|-------------------------------|-------------|
| C1 Manual interactive | Compliant | Resolves Q1 only; Q2 unresolved per Adversarial finding 5 |
| C2 Scripted `claude -p` with actionable-task preamble | Compliant | Same Q1/Q2 limitation |
| C3 JSONL scrape | Non-compliant (not a probe) | Background evidence only |
| C4 Skip+rewrite | Non-compliant | Veto'd by reopener |

**Recommended (revised per Adversarial)**: Accept that neither C1 nor C2 resolves Q2. Pass 2 remediation decision should be based on a **structural analysis of verification-mindset.md under 4.7 literalism** (the whole file is negation-framed per §Codebase Analysis), not on probe results alone. Whole-file rewrite to positive-routing structure is the default; C1/C2 probes are corroborating evidence, not sole decision input.

### Axis D — Remediation verification

- **D1 Human review per-commit** (matches #053): required
- **D2 Scoped grep-regression CI check**: add for P7 sites (cheap, high-value) and P1/P3 signature patterns (`omit.*entirely|do not emit`, `Do not be balanced. Do not reassure`). Not for P4/P6 (signatures too fuzzy).
- **D3 Probe-based behavioral test**: no existing harness; build cost not justified for one-shot audit. Skip.

### Axis E (NEW — adversarial-surfaced) — PR gate vs direct-to-main

#053 landed direct-to-main. But: `claude/reference/*` and `claude/Agents.md` edits propagate via symlink to ALL local projects immediately. `verification-mindset.md` is the harness's primary verification gate. A misjudged rewrite directly on main has no fast rollback.

**Recommended**: **introduce PR gate for #85**, breaking #053's precedent. Require PR review for any edit to `claude/reference/*.md`, `claude/Agents.md`, and the 6 dispatch skills' SKILL.md files. Non-SKILL.md edits in `skills/*/references/` can follow #053's direct-to-main precedent.

### Cross-axis recommended combination (adversarial-adjusted)

**A1 (pattern-bucketed) + A2 (per-file for verification-mindset.md) + B2-partial (Pass 2 split out today) + D1+D2(scoped) + E PR-gate for high-blast-radius files**

Pass 3 treatment: default to "drop" unless Spec explicitly broadens scope.

## Adversarial Review

### Findings that alter scope (critical)

1. **`overnight` is NOT a dispatch skill.** `skills/overnight/SKILL.md` contains zero `Agent()` / `Task()` invocations. Orchestrates via bash runner — a separate shell process. Including it in the audit inflates scope by ~14% and anchors Pass 1 on a false premise. **Drop.**
2. **`pr-review` was extracted to a plugin repo.** Confirmed via `lifecycle/extract-optional-skills-to-plugin/plan.md:76-84` and commit `9ae4a85`. The current repo's `skills/pr/` is an unrelated PR-creation skill. Ticket scopes a dead file. **Drop.**
3. **`refine` is missing from audit scope** despite epic research.md:56 explicitly citing it as HIGH-risk P2. Refine dispatches `/research` (SKILL.md:94) and its path-guard logic affects every lifecycle feature. **Add.**
4. **`claude/Agents.md` is missing from audit scope.** Loaded at every session start globally. Larger blast radius than any conditional-load reference file. No P1–P7 audit has been performed on it. **Add.**

### Assumptions that may not hold

- **Preservation rules are still load-bearing under 4.7**: #053 calibrated against 4.6. The ring-fenced sites may themselves exhibit P3 failure (see `critical-review:179` synthesizer prompt). Ring-fence is circular: "this is a #053 rule, so we don't audit it for the 4.7 regression that would invalidate it."
- **84 work cells is oversized**: Agent 4's "15–30 realistic" was grep-undercount; corrected baseline (124 `do not`) projects to ~30–50. Ticket's original "complex + high" sizing was likely right.
- **Line numbers in anchored preservation decisions are current**: #053's anchors cite line numbers from research time. Drift is possible; Spec should re-verify anchor positions before honoring exclusions.
- **One-section patch is sufficient for verification-mindset.md**: Entire file is negation-framed. Iron Law, Gate Function, Red Flags, Common Rationalizations are all P3-adjacent. Whichever section fires next under 4.7 will be blamed on wrong-section patch. Whole-file rewrite is the correct granularity.

### Missed patterns (pattern taxonomy gaps)

- **P8 severity-gating** (new): "only report important," "skip minor issues" — Anthropic-named 4.7 recall killer. Not in P1–P7. Spec should decide whether to add.
- **P5 sites were missed**: Agent 1 initially reported "P5: zero true positives" but `lifecycle/references/research.md:57`, `plan.md:27`, `implement.md:189` all contain "do not omit, reorder, or paraphrase" (the canonical P5 archetype per epic research.md:59).
- **Second "Red Flags - STOP"** instance at `claude/reference/context-file-authoring.md:87` — parallel structure to verification-mindset.md, unflagged by Agents 1–4.

### Missed audit dimensions

- **Effort-level triage**: 4.7 literalism is worst at low/medium effort. Skills run at varying effort levels. Per-site severity weighting should account for the effort level each skill runs at. No agent enumerated this.
- **Subagent-default regression**: 4.7 ships "fewer subagents by default." Dispatch skills that assume fan-out (`research` dispatching 3–5 agents, `critical-review` dispatching parallel angles) need explicit "spawn multiple subagents in the same turn" language. Audit should check that each fan-out site has this.

### Security / blast-radius concerns

- **Global symlink + direct-to-main = uncontrolled rollout.** `claude/reference/*` → `~/.claude/reference/*` means edits propagate to all local projects instantly. `verification-mindset.md` is the universal verification gate — a misjudged rewrite silently suppresses the harness's primary safety rail.
- **Preservation-rule over-application is a security regression vector.** `diagnose/SKILL.md` env var gate and `lifecycle/SKILL.md` prerequisite-missing warn are ring-fenced but are themselves safety-critical — if they fail under 4.7, the preservation rule IS the vulnerability.
- **`critical-review/SKILL.md:179`** is the adversarial synthesizer's sole output constraint. Under 4.7, 4.7 Opus may drop all caveats/hedging — producing false-certainty reviews that users weight too heavily. **Highest-consequence P3 in the audit.**

### Veto surface — conditions under which the ticket should be restructured

- **VETO if scope keeps `overnight` and `pr-review`.** Two of seven surfaces are the wrong files. Fix before Spec or reject.
- **VETO if Pass 2 stays bundled with Passes 1+3.** The probe-dir Q2 problem has no behavioral test. Bundling forces either blocking wait or rushed rewrite. Split Pass 2 to child ticket now.
- **VETO if preservation rules remain unconditionally ring-fenced.** Require per-rule 4.7 re-validation spike before honoring exclusion, or reject the ticket.
- **VETO direct-to-main execution on reference files.** Global symlink + no PR + verification-mindset centrality = uncontrolled change. Introduce PR gate for high-blast-radius files.
- **VETO if Agents.md stays out of scope.** Larger blast radius than any reference file; must be audited within #85 or as immediate child ticket.

## Open Questions — Resolved at Research Exit Gate (2026-04-20)

The following were surfaced during Research and resolved by the user before entering Spec. Spec formalizes these as requirements.

1. **Scope reconciliation** — *Resolved: update scope.* Drop `overnight` (zero Agent/Task calls — adversarial confirmed) and `pr-review` (extracted to plugin repo, commit `9ae4a85`). Add `refine` (dispatches `/research`, HIGH-risk P2 flagged in epic research.md:56) and `Agents.md` (global blast radius via symlink to `~/.claude/CLAUDE.md`). Revised audit surface: **6 dispatch skills + 6 reference/global files = 12 surfaces** (net-flat count, different composition).

2. **Pass 2 decomposition** — *Resolved: split to child ticket now.* `verification-mindset.md` whole-file rewrite goes to a new child ticket under epic #82, created as the first Plan task. Rationale: probe-vs-Q2 asymmetry (probes answer Q1 loading, not Q2 behavior), whole-file rewrite granularity, and different verification methodology (behavioral) from Pass 1/3 (grep-and-judge). #85 completes Pass 1 + Pass 3 only.

3. **Pass 3 treatment** — *Resolved: broaden scope.* git-blame finds zero #053-introduced `consider` sites; original scoping premise is empirically false. Broaden to all 9 `[Cc]onsider` occurrences in `skills/` (5 classified as conditional-requirement, 4 as polite imperatives). Three-category classification methodology (a/b/c) still applies. Revives DR-5 option c that the epic had rejected on premise-grounds.

4. **Preservation-rule re-validation** — *Resolved: accept #088's quantitative coverage; skip qualitative spike-test.* #088's baseline snapshot gives automatic cost/turn drift detection against post-#85 sessions. Qualitative spike-test (e.g., running `critical-review` on a known artifact and inspecting output quality) is deferred. Fallback: if #088's post-change comparison detects drift specifically on ring-fenced dispatches, run the qualitative spike as a remediation step in a follow-up ticket.

5. **PR gate for high-blast-radius files** — *Resolved: introduce PR gate.* Any edit to `claude/reference/*.md` or `claude/Agents.md` under #85 requires PR review (breaking #053's direct-to-main precedent for these files only). Non-SKILL.md edits in `skills/*/references/` may still follow #053's direct-to-main pattern. Rationale: global symlink propagation to `~/.claude/reference/*` and `~/.claude/CLAUDE.md` makes rollback-via-revert too slow for a misjudged edit to the universal verification gate or global agent instructions.

6. **New pattern P8 (severity-gating)** — *Resolved: defer.* Scope already grows from OQ1 (new surfaces) and OQ3 (broader Pass 3). Adding P8 scan across 12 surfaces compounds scope. #090's xhigh outcome may change severity-gating calculus (higher effort partially suppresses 4.7 literalism). Open a follow-up ticket under epic #82 if any of the 12 audited surfaces contains severity-gate framing that surfaces during Pass 1 grep work.

7. **Scheduling against #088's freeze** — *Resolved: Spec + Plan now, implement waits.* #85's Spec and Plan phases do not touch prompt-surface files, so they proceed now in parallel with #088's measurement window. #85's implement phase blocks until #088's baseline snapshot commits at `research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md`. Spec documents this as an explicit dependency in the spec's blocked-by/scheduling section.
