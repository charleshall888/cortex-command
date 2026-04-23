# Research: Remove progress-update scaffolding from long-running prompts (DR-3 Wave 1)

## Epic Reference

Parent epic research: [research/opus-4-7-harness-adaptation/research.md](../../research/opus-4-7-harness-adaptation/research.md). This lifecycle executes DR-3 Wave 1 from that epic under a pivoted scope (2026-04-22): no baseline comparison, no measurement — remove scaffolding on trust of Anthropic's 4.7 guidance, accept unattributable regressions, revert via git if a loud failure surfaces. Sibling epic ticket #088 (baseline collection) was closed wontfix 2026-04-21.

**The research below materially changes the shape of this ticket.** See the Adversarial Review and Open Questions sections — the classification-rule decision is pre-Spec and load-bearing.

## Codebase Analysis

### Deletion candidates under a strict classification rule

**Zero clear candidates found.** Comprehensive search across `skills/**/*.md`, `claude/reference/**/*.md`, `claude/overnight/prompts/*.md`, `claude/pipeline/prompts/*.md`, hooks, and dynamic-prompt composition code returned no literal progress-update directives aimed at the model ("summarize after every N tool calls", "every M turns provide a status update", "checkpoint every X iterations", etc.). The canonical target from the Anthropic migration guide — "After every 3 tool calls, summarize progress" — does not exist in this codebase. Either it was never added, or prior cleanup removed it.

### Ambiguous (single site)

- `skills/lifecycle/references/implement.md:178-181` — daytime-dispatch polling loop's "Progress tail" step: `tail -n 5 lifecycle/{feature}/events.log` and surface a brief summary of the 5 most recent events to the user, every 120s for up to 120 iterations (~4 hours).
  - **Under strict rule**: not scaffolding — it's an orchestrator session monitoring a detached background subprocess, not model self-narration of ongoing agentic work. The 5-event cap is an explicit context-hygiene choice.
  - **Under broader rule** (see Adversarial Review §5): the orchestrator *is* generating user-facing narration on a 120s cadence, structurally similar to "every N tool calls, summarize" — only the trigger type differs (wall-clock vs tool-count). Keeping it under 4.7 forces cadence that 4.7's native updates might otherwise self-calibrate.

### Legitimate turn-structure guidance (not candidates under either rule)

For contrast — these are explicitly excluded:

- `claude/reference/output-floors.md:11-22` — phase-transition minimum-output floor. **Structural event: phase boundary.** See Adversarial Review §6 — this is borderline under the broader rule.
- `claude/reference/output-floors.md:24-36` — approval-surface floor (triggered by artifact hitting approval gate).
- `claude/overnight/orchestrator.py:269,282` — 5-minute heartbeat background task (runtime watchdog, not model prompt).
- `claude/overnight/runner.sh:800` — "Overnight session abandoned" notification string (string literal, not directive).
- `lifecycle/{feature}/learnings/progress.txt` — file-based retry learnings artifact. **Explicitly out of scope** per Anthropic's Nov 2025 engineering post (see Web Research) and requirements/multi-agent.md Context hygiene NFR.

### Proposed strict classification rule

> An instruction is progress-update scaffolding iff it directs the model to emit a summary, update, or checkpoint keyed to elapsed time, tool-call count, turn count, or iteration count — with no structural event (phase transition, batch completion, artifact write, approval gate, parallel-dispatch rejoin, external subprocess exit) as its trigger.

**Edge cases the rule covers well**: the canonical "every 3 tool calls" pattern; time-keyed status emission; iteration-keyed checkpoints.

**Edge cases the rule covers poorly** (elaborated in Adversarial Review §6): structural-event-triggered narration that would be redundant under 4.7's native updates (phase transition floor, announce-at-completion patterns across refine/research/discovery/lifecycle); orchestrator narration between dispatch waves in multi-agent skills; poll-loop summaries of external subprocess state.

### Pattern-match noise check

An earlier tradeoffs-agent pass claimed "checkpoint-flavored language at `implement.md:74, 183, 268, 274, 361, 363`" were likely Wave-1 candidates. Adversarial review read each verbatim and **confirmed zero are scaffolding**. All six use "checkpoint" to reference: (a) the §2d verification procedure, (b) sequencing relationships to that procedure, or (c) file-based durable writes to `plan.md`. Crude keyword grep without context inspection produces false positives — the classification rule must be applied with file-content inspection, not regex alone.

### Dynamic prompt composition

Prompt composition via `_render_template` (feature_executor.py) and `fill_prompt` (runner.sh) operate against **static template files** already inspected — no runtime-constructed scaffolding.

## Web Research

### Primary Anthropic sources

**Load-bearing citation — Opus 4.7 Migration Guide, item 4** (`platform.claude.com/docs/en/about-claude/models/migration-guide`, published 2026-04-16):

> "4. **Built-in progress updates in agentic traces:** Claude Opus 4.7 provides more regular, higher-quality updates to the user throughout long agentic traces. If you've added scaffolding to force interim status messages ('After every 3 tool calls, summarize progress'), try removing it. If you find that the length or contents of Claude Opus 4.7's user-facing updates are not well-calibrated to your use case, explicitly describe what these updates should look like in the prompt and provide examples."

**Secondary** — What's New in Opus 4.7 behavior-changes bullet list — says the same thing more briefly.

### Critical nuance: the guidance is three-step, not "delete everything"

Anthropic's recommendation is explicitly: **(1) try removing**, **(2) observe calibration**, **(3) if mis-calibrated, add shaped examples to the prompt**. The pivoted #092 contract ("remove only + revert via git on loud failure") drops step 3. See Adversarial Review §2.

### Related but out-of-scope guidance

Anthropic's Nov 2025 engineering post ["Effective harnesses for long-running agents"](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) **still recommends** durable progress artifacts (progress files, commit messages, cross-session scratchpads). That guidance is orthogonal to 4.7's new behavior — do NOT sweep away `learnings/progress.txt`, `events.log`, `plan.md` `[x]` updates, or commit messages under the #092 banner.

### Counter-evidence: 4.7 long-context regressions

HN discussion of the 4.7 model card documents long-context retrieval regressions vs 4.6 (e.g., ~30-point drops at large context sizes; collapse at 524k–1024k). The regime where progress-update scaffolding mattered most (long autonomous traces spanning large context) is precisely where 4.7 may regress relative to 4.6. Anthropic's "native updates are higher-quality" claim is strongest in interactive short-horizon settings and weakest in the long overnight regime where this project uses the model. See Adversarial Review §3.

### Prior art

No other agent framework has published analogous "remove progress scaffolding" recommendations. This is Anthropic-model-specific guidance, not industry consensus.

### No post-mortems found

The model is ~6 days old at time of research (launch 2026-04-16); absence-of-public-regret-reports is weak signal.

## Requirements & Constraints

### In scope
- In-prompt progress-update scaffolding in dispatch-skill SKILL.md files, their reference docs, and `claude/reference/*.md`.
- Dispatch-skill surface per DR-2: `critical-review`, `research`, `pr-review`, `discovery`, `lifecycle`, `diagnose`, `overnight`.

### Explicitly out of scope (all confirmed by requirements docs)
- `lifecycle/{feature}/learnings/progress.txt` — file-based retry learnings (multi-agent.md Context hygiene NFR).
- Agent stderr capture/capping (multi-agent.md infrastructure).
- `pipeline-events.log`, `events.log`, `overnight-state.json`, `escalations.jsonl` — structured audit trails (pipeline.md).
- Orchestrator structured `rationale` field at escalation junctures — defined in `output-floors.md`, distinct from progress narration (pipeline.md NFR).
- Deferral file schemas (pipeline.md).
- Substring output-filter hooks / `output-filters.conf` (project.md Context efficiency NFR).
- Remote-access prompt behavior (no relevant constraints).
- Model selection matrix recalibration — DR-4 shelved via #088 wontfix.
- Measurement/baseline/comparison apparatus — explicitly dropped by 2026-04-22 pivot.

### Architectural constraints
- **Symlink architecture**: `skills/*` → `~/.claude/skills/*`; `claude/reference/*` → `~/.claude/reference/*`. Edits propagate globally on next invocation. **No staged rollout available.**
- **Overnight runner** bypasses permissions (`--dangerously-skip-permissions`) — prompt changes affect autonomous execution without permission gating.
- **Fail-forward model**: one feature's regression doesn't cascade; multiple concurrent dispatches act as implicit comparison.
- **`output-floors.md` is load-bearing** for orchestrator rationale convention (pipeline.md NFR) and DR-6 M1 codification — edits must preserve those sections.

### Sibling lifecycle overlap
- **#067, #068, #069** (M1 positive-routing rewrites in clarify-critic, critical-review, specify) — in clarify/specify phase. Touch `skills/critical-review/SKILL.md`, `skills/lifecycle/references/clarify-critic.md`, `skills/lifecycle/references/specify.md`. **Potential intent collision** with #092 opportunistic cleanup — see Adversarial Review §4.
- **Audit lifecycle** (`audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns`, #85) — active, same epic, P1–P7 remediation commits already landed. Format precedent (`candidates.md` table) is reusable; pattern catalog does NOT transfer (P1–P7 are static anti-patterns, not progress-update scaffolding).

### #088 closure note (verbatim)

> "Closed as wontfix. At n<30 per bucket this baseline is directional only — not conclusive enough to attribute prompt-change regressions to the prompt rather than variance. The 2–3 rounds of operator attention plus prompt-freeze discipline is not justified unless we plan to execute #092 and #090 with rigorous before/after comparison, which we're not currently prioritizing."

Relevant to classification rule decision: #088's wontfix premise was "no rigorous before/after for #092" — if #092 also becomes a no-op (empty corpus under strict rule), closing #092 wontfix maintains that internal consistency.

## Tradeoffs & Alternatives

Recommendations from tradeoffs analysis, **conditional on the classification-rule decision** (see Open Questions):

### Sequencing
- **Two waves** (clear candidates first, ambiguous second) — mirrors sibling audit lifecycle. Falls back to single-wave if clear candidates are ≤3.

### Classification rule application
- **Per-site `candidates.md` table** with semantic-test judgment per row — regex-only would over- or under-catch. Same format as audit lifecycle's candidates.md. Each row: `file:line`, verbatim quote, context, classification (`qualifying | preservation-excluded | not-a-failure-mode`), rationale.

### Batch size and blast radius
- **`claude/reference/*.md` + `claude/Agents.md` edits via PR** (high blast radius — all projects on machine). `skills/*/SKILL.md` and `skills/*/references/*.md` direct-to-main. Mirrors audit lifecycle spec R6.

### Adjacent-cleanup scope
- **Permissive** per 2026-04-22 decision — adjacency cleanups allowed, recorded per-site in `candidates.md` with rationale so the diff is self-explaining. NOT Alt C (separate follow-up ticket) — that would re-introduce the scope bound the user dropped.

### Rollback
- **`git revert`** against single-commit-per-wave — already specified in backlog and precedent.

### Merge-order recommendation
- **#092 lands AFTER #067/#068/#069**, not before. The three M1 siblings actively rewrite content in overlapping files; #092 landing first could silently invalidate their rewrite targets. Adversarial Review §4 constructs the scenario.

## Adversarial Review

### Is the corpus actually empty?

Ground-truthed all 6 pattern-matched `implement.md` lines that a prior analysis flagged. **Zero of six are scaffolding.** All use "checkpoint" in non-scaffolding senses (procedure name, sequencing reference, durable file writes). Agent 1's strict classification holds. **Under the strict rule, the corpus is empty** — #092 is a no-op and closing wontfix matches #088's precedent.

### The pivot exceeds what Anthropic's guidance endorses

Anthropic's step 3 ("add shaped examples if mis-calibrated") is dropped by the current pivot contract. Subtle narration-quality regressions are accepted as unattributable — a weaker contract than "follow Anthropic's guidance." This matters most for large interventions like `output-floors.md` edits; less for small single-line deletions.

### 4.7 long-context regressions weaken the "trust 4.7" assumption

Overnight runs live in the long-context regime where 4.7 regresses vs 4.6. The assumption that 4.7's native updates are higher-quality than scaffolding is strongest in short interactive settings and weakest in this repo's primary use case. Mitigation: the broader-rule path should preserve Anthropic's step-3 branch (shaped examples) so regressions are recoverable without full revert.

### Sibling-lifecycle collision scenarios

- **Scenario A — #092 before #067/#068/#069**: #092's "remove only" could delete content that M1 siblings were planning to rewrite to positive routing — making M1 siblings silent no-ops. **Riskier.**
- **Scenario B — #092 after #067/#068/#069**: #092 operates on post-rewrite content and can make targeted decisions. **Preferred order.**

### `implement.md:180` safe to leave?

Three stress tests suggest *not* under the broader rule:
1. The orchestrator IS narrating (via the "surface a brief summary of the 5 most recent events to the user" clause) — just sourced from a file. Anthropic's "scaffolding to force interim status messages" language arguably covers this.
2. 4.7's native updates would plausibly self-emit over the same 2-hour polling window without 120s-cadence forcing.
3. The comment "capped at 5 (not 20) to limit context accumulation over long runs" admits the scaffolding has a cost.

Counter: it also serves an audit function (surfacing events the user might miss). Under Anthropic's 3-step guidance, the correct treatment is "try removing, re-baseline, add shaped example if mis-calibrated" — precisely the path the pivot drops.

### Is the strict classification rule too strict?

**Yes, likely.** Gaps:
1. "Structural event" is generous — phase-completion-triggered narration is arguably exactly what 4.7 now emits natively.
2. The rule ignores "announce to user after completing X" framing — pervasive across skills.
3. The rule ignores multi-level nesting — `output-floors.md` is meta-scaffolding that mandates narration across lifecycle/discovery.

Broader rule candidate: **"Any directive that forces model-generated user-facing narration at a fixed structural cadence where 4.7's native updates would plausibly cover the same surface area."**

Sites the broader rule catches:
- `claude/reference/output-floors.md:11-22` — phase-transition floor (4 mandatory fields per transition)
- `claude/reference/output-floors.md:24-36` — approval-surface floor
- `skills/lifecycle/SKILL.md:317` — inline reference to the floor
- `skills/lifecycle/references/implement.md:180` — poll-loop summary
- `skills/lifecycle/references/implement.md:278` — `**f. Report**: Summarize what the batch accomplished and any issues before dispatching the next batch.`
- `skills/refine/SKILL.md:170` — "Announce that /refine is complete. Summarize:"
- `skills/research/SKILL.md:226` — "Announce: 'Research complete. Written to...'"
- `skills/research/SKILL.md:170` — "Summarize each agent's findings into a brief paragraph. Then dispatch agent 5."
- `skills/discovery/SKILL.md:63` — "After completing a phase artifact, ... summarize findings ..."

### Does the empty-corpus finding invalidate the pivot's premise?

**Under the strict rule**: yes. The pivot was engineered as a cost-reduction vs #088's baseline-first plan — it assumes removal work exists. Empty corpus → no work → pivot is moot → **close #092 wontfix**.

**Under the broader rule**: no, but the pivot contract is under-specified for interventions at `output-floors.md` scale. The broader rule affects ~5–7 sites concentrated in meta-scaffolding — deleting the Phase Transition Floor is a substantially larger intervention than deleting a single "summarize every 3 tool calls" line. These sites deserve Anthropic's full 3-step treatment (step 3 = add shaped examples on mis-calibration).

### Orchestrator-narration scaffolding in multi-agent dispatch

Structurally identical to "every N tool calls" scaffolding but keyed to multi-agent graph boundaries instead of tool-count:
- `skills/research/SKILL.md:170` — summarize-between-waves directive.
- `skills/lifecycle/references/implement.md:278` — summarize-per-batch directive.
- `skills/critical-review/SKILL.md` synthesis sections — synthesis-of-reviewer-outputs directive.

None of these are in the audit lifecycle's P1–P7 catalog — the audit's pattern catalog does not transfer to #092. "Mirror the sibling lifecycle" is correct process-wise but not scope-wise.

### Recommended mitigations (for Spec if we proceed)

1. **Decide the classification rule explicitly in Spec** — strict (→ wontfix) or broader (→ ~5–7 sites). Don't let it emerge implicitly.
2. **If broader rule chosen: restore Anthropic's step-3 branch** to the pivot. "Remove only + revert" is too coarse for `output-floors.md`-scale interventions.
3. **Sequence #092 AFTER #067/#068/#069.**
4. **Re-scope `implement.md:180` explicitly** — pick: (a) keep with 4.7-re-baselining deferred note, (b) delete + accept audit-surface loss, (c) replace with shaped example per Anthropic step 3.
5. **Explicit exclusion in Spec**: durable file-based artifacts (events.log, plan.md `[x]`, commit messages, learnings/progress.txt) are out of scope per Anthropic's Nov 2025 engineering guidance.

## Open Questions

All items below require user decision before Spec can proceed. None are resolvable by further investigation.

- **Classification rule**: strict (file-inspection finding: empty corpus → close #092 wontfix, mirroring #088) or broader (~5–7 sites centered on `output-floors.md` phase transitions and announce-at-completion patterns in refine/research/discovery/lifecycle)? **Deferred — requires user decision in Research Exit Gate; drives whether this lifecycle proceeds at all.**
- **If broader rule**: should the pivot contract include Anthropic's step-3 branch (permission to add shaped examples in prompts if post-merge observation shows mis-calibration), or stay at "remove + revert only"? **Deferred — requires user decision before Spec.**
- **Sequencing vs #067/#068/#069**: should #092 wait for those three in-flight M1 sibling tickets to land first? **Deferred — requires user decision before Spec.**
- **`implement.md:180` "Progress tail"**: under broader rule — keep as-is (with note), delete, or replace with shaped example? **Deferred to Spec if we proceed.**
