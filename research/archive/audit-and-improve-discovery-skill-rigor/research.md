# Research: audit-and-improve-discovery-skill-rigor

## Topic

Investigate whether the `/discovery` skill's protocol produces value-validated, evidence-grounded backlog tickets, or whether it tends to produce over-eager epics whose premises haven't been verified against the actual codebase.

## Triggering incident

Backlog #092 closed wontfix on 2026-04-22 after its lifecycle research phase found an empty corpus. The canonical Anthropic target ("After every 3 tool calls, summarize progress" scaffolding) did not exist anywhere in the codebase. The ticket's generating research artifact (`research/opus-4-7-harness-adaptation/research.md`) projected the locator "from lifecycle/implement prompts" by inference, not by grep. #088 was a dependent ticket that closed the following day because, without #092 as a justification, its baseline collection was not worth the effort.

Critical data point from `research/opus-4-7-harness-adaptation/events.log`: the generating artifact passed its orchestrator-review on cycle 1 with zero issues, passed its critical-review with all objections applied, and went through a user gate that approved the decomposition. **Every existing post-hoc check ran, and each passed, while the premise was silently wrong.** This observation is load-bearing for H3's revised verdict below.

## Scope of this discovery

This is a meta-audit: `/discovery` running on itself. Per the prompt's meta-instruction, all protocol claims below are anchored by file:line citations in `skills/discovery/**` files. Web research was performed for the alternatives-discovery portion (Approach F below). Domain & Prior Art was skipped — it would not have altered the verdict set, and the audit target is internal.

An earlier draft of this artifact used "skipping web/domain" as evidence for H3; that was circular (the author's override in one run is not data about the protocol). Dropped.

## Research Questions

1. **Rate of waste (Q1)** → **Low observed rate, with a material denominator caveat.** Among 111 discovery-sourced tickets (grep `discovery_source:` in `backlog/[0-9]*.md`), 6 closed `wontfix`/`abandoned`. The closed-ticket classification:
   - **Hard premise-failure** (codebase assumption didn't hold): **1 ticket**, #092. Closure quote: "Empty-corpus finding … The canonical Anthropic target … does not exist in this codebase." (`backlog/092-...md`)
   - **Consequential premise-entanglement**: **1 ticket**, #088 (baseline for #092). Closed because #092's premise-failure invalidated #088's utility, not because #088 itself failed.
   - **External fact change** (file deleted upstream): 2 tickets, #061 and #062 (both targeted `hooks/cortex-notify-remote.sh`, removed in 373ca30). Different failure mode.
   - **Priority-shift**: 1 ticket, #128 (deferred in favor of upstream fix via #127).
   - **Unclear**: 1 ticket, #089.

   **Closed-ticket rigor-concern rate = 1–2/111 = 0.9–1.8%.**

   **Denominator caveat (added after critical review)**: The 68 tickets counted as "complete" in the status breakdown have NOT been audited for silent value-failure — tickets that merged but whose research premise was weaker than stated. Spot-checks of 3 complete tickets surface this mode:
   - **#083**: deliverable states "the research.md DR-7 prediction was directionally correct … but specifically wrong about the target file (`claude/pipeline/dispatch.py` does not import `anthropic` directly and was not touched)." Research premise named the wrong file; because the deliverable was a report (not a code change), no wontfix triggered.
   - **#084**: deliverable self-reports "Probe-dir context may suppress legitimate loads … it is possible that 4.7's load decision depends on 'is there an actionable task' rather than 'is the trigger phrase present'. This is one hypothesis for the Q1 LOW verdict." The spike flags that its own regime may have invalidated four of five verdicts — counted "complete."
   - **#020**: deliverable exists at `.claude/skills/harness-review/SKILL.md` but outside the repo's symlink architecture (CLAUDE.md: "Files in this repo are symlinked to system locations"). Silent value-failure at the integration layer.

   **Revised reading**: the 1-2/111 figure measures "premise failures severe enough to trigger abandonment," not "research premise weaker than stated." The true rigor-concern rate is plausibly higher but cannot be measured without a ticket-by-ticket value-delivery audit (out of scope for this discovery). Base-rate arguments should be weighted accordingly in DR-1.

2. **Evidence grounding — where can codebase-pointing recs enter without citations (Q2)?** → **Three specific entry points in `research.md`:**
   - **`research.md:35-42` (§2 Codebase Analysis)**: No requirement that findings carry file:line citations; no requirement that search-negative results be reported explicitly.
   - **`research.md:44-53` (§3 Web & Documentation Research)**: No crosscheck requirement against codebase findings.
   - **`research.md:66-73` (§5 Feasibility Assessment)**: "For each viable approach surfaced during research" allows any agent's approach into the table. The "Prerequisites" column (`research.md:107` template) is where "Identify X in the codebase" typically lands — framed as implementation sequencing, not as premise verification (novel finding, below).

   **Where the failure compounded in #092**: The web agent correctly quoted Anthropic. In synthesis the quote was rewritten as "Remove 'After every 3 tool calls, summarize progress' scaffolding from lifecycle/implement prompts" — locator added by inference. `orchestrator-review.md:112` (R2: "Feasibility grounded in evidence") is a post-hoc check. Per the events.log evidence, R2 ran and passed despite the projected locator. R2 as worded asks "cites specific codebase patterns" — which the artifact technically did (the prompt directory names) without actually verifying the pattern occurs in those files.

3. **Value validation — is the Value field gating (Q3)?** → **Revised after critical review: the gate exists structurally; its failure mode is upstream.** `decompose.md:29` ("Present the proposed work items to the user for review before creating tickets") IS a mandatory user-approval checkpoint before ticket creation. Combined with `decompose.md:23` (flag weak value), it forms a flag-then-user-approve gate. But the gate can only catch issues the agent surfaces for review. In #092's chain, "endorsed by Anthropic's 4.7 migration guide" was synthesized as sufficient value without a weakness flag — the gate had nothing to gate on.

   **The failure is upstream of the gate, in what gets flagged at decompose.md:23 and how value-from-external-endorsement is classified**. A rule that specifically identifies vendor-endorsement-without-codebase-grounding as requiring explicit user approval would make the existing gate catch this case.

4. **Epic bias (Q4)** → **None detected.** `decompose.md:47-57` (§4 Determine Grouping) is cardinality-driven: "If the research produces exactly one work item, create a single backlog ticket. If the spec produces 2+ work items [create] Epic + children." No weighting.

5. **Closure accounting (Q5)** → **No mechanism exists.** Grep across `skills/discovery/**` for `wontfix`, `invalidate`, `update research`, `closure`: zero hits. When #092 closed wontfix, `research/opus-4-7-harness-adaptation/research.md` was not updated. **However**: the empirical base rate (1-2/111) makes this low-urgency infrastructure. Treating Q5 "ABSENT" as a protocol gap without also noting low urgency smuggles in severity.

6. **Pattern scan across artifacts (Q6)** → **Citation density statistic is lexical, not epistemic.** Across 7 sampled research artifacts, codebase-pointing recommendations carry file:line or backtick-wrapped path citations at 85–95%. **Caveat**: this counts whether a file-path string appears, not whether it was verified. An inferred locator (like #092's "from lifecycle/implement prompts") counts as a citation for grep purposes. The #092 generating artifact (opus-4-7-harness-adaptation) sat at ~83% — the FLOOR of the sampled range, not safely above a threshold. The statistic's bottom quartile is where rigor breaks; it is not a safety margin.

## Codebase Analysis

**Protocol files audited (exhaustively):**

- `skills/discovery/SKILL.md` — 3-step orchestration.
- `skills/discovery/references/clarify.md:1-66` — pre-research ideation gate.
- `skills/discovery/references/research.md:1-139` — multi-dimensional investigation.
- `skills/discovery/references/decompose.md:1-118` — break research into tickets.
- `skills/discovery/references/orchestrator-review.md:1-134` — post-artifact quality gate (R1–R5 at lines 111–115).
- `skills/discovery/references/auto-scan.md` — self-directed topic surfacing.

**Revised gradient verdicts** (after critical review):

| Hypothesis | Verdict | Notes | Anchor |
|-----------|---------|-------|--------|
| H1: Codebase agent contract weak on citations / empty-corpus reporting | **WEAK CONTRACT, STRONG NORM (85-95%)** | Protocol does not require citations, but artifacts achieve 85-95% compliance via synthesizer discipline. Approach A codifies existing behavior; doesn't close a "gap" so much as harden a norm. | `research.md:35-42` vs. empirical 85-95% density |
| H2: Web agents can add codebase-pointing actions without crosscheck | **CONFIRMED** | Real synthesis-layer gap. Web→artifact path has no codebase-verification step. This was the literal #092 mechanism. | `research.md:44-53` → `research.md:75-120` |
| H3: Existing post-hoc checks cannot catch projected-locator errors | **CONFIRMED EMPIRICALLY** | `events.log` for opus-4-7-harness-adaptation shows orchestrator-review passed cycle 1 with zero issues, critical-review passed with 4 objections all applied, user gated on DR-4 — and the premise was still wrong. R2 ("cites specific codebase patterns") is satisfied by a pattern string appearing, not by the pattern actually occurring. | events.log + `orchestrator-review.md:112` |
| H4: Value field is descriptive, not gating | **REVISED — gate exists, upstream input fails** | `decompose.md:29` IS a user-approval gate. It cannot catch weaknesses the agent does not surface at `decompose.md:23`. Vendor-endorsement-as-value enters un-flagged. Fix target: add a specific rule recognizing external-endorsement-without-codebase-premise as requiring explicit flagging. | `decompose.md:23` + `decompose.md:29` |
| Q4: Epic bias | **NONE** | Cardinality-driven. | `decompose.md:47-57` |
| Q5: Closure feedback loop | **ABSENT, LOW URGENCY** | Zero grep hits, but 1-2/111 base rate makes new infrastructure hard to justify. | Zero grep hits across `skills/discovery/**` |
| Novel: Prerequisites framed as implementation, not verification | **CONFIRMED** | Feasibility template's Prerequisites column accepts "Identify X in codebase" as implementation sequencing. Not currently revisited after the #092 incident. | `research.md:67-73` + template at `research.md:104-107` |

**Empirical patterns:**

- Discovery-sourced tickets: 111 total. Status breakdown: 68 complete, 29 backlog, 3 refined, 3 in-progress, 4 wontfix, 2 abandoned, 2 blocked.
- Hard premise-failure among closed: 1 (#092) + 1 entangled (#088), both from `research/opus-4-7-harness-adaptation/research.md`.
- Silent premise-weakness among "complete": at least 3 of 3 spot-checked tickets from the same web-heavy source show partial premise weakness (see Q1 caveat).
- Citation density 85–95% is lexical; opus-4-7 at ~83% is the sample floor.

## Web & Documentation Research (limited scope)

Targeted only at alternatives discovery — specifically whether external literature surfaces approaches not in the original feasibility table.

- **Context drift** in multi-agent systems is a well-named failure mode: agents operate on incomplete signals and confidently report contradictory information without grounded reference points. #092 is a textbook instance.
- **Execution-grounded verification** appears in external multi-agent frameworks (AgentForge, CrewAI production deployments): run automated probes against generated artifacts to surface hallucinations before acceptance. For `/discovery`, the analog is an automated grep/AST probe against every codebase-pointing claim in a finished research.md. **This surfaced Approach F below** — a mechanical alternative not in the original ladder.
- **Redundant independent verification** (codebase and web agents independently verifying shared claims before synthesis) is another common pattern in orchestration literature; a less-intensive variant of the original Approach B.

External literature did not surface hypotheses missing from H1–H4 — the failure taxonomy is well-covered.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **A. Codify citation norm + premise-as-verification in `research.md`** — Rule: codebase-pointing claims require a codebase-agent file:line citation OR an explicit `premise-unverified` mark. Empty-corpus searches reported as `NOT_FOUND`. Feasibility template's Prerequisites column retargeted: prerequisites describing codebase-state verification must be resolved during research, not deferred as implementation work (addresses the "Novel" finding). | S | Codifies existing 85-95% norm rather than closing a gap — the improvement is ensuring the bottom quartile doesn't slip. Risk of ritualism (citations added for show). | None. Pure edit to `research.md`. |
| **B. Add R6 to `orchestrator-review.md`** (original proposal) — "Codebase claims have citations or are marked premise-unverified." | S | Post-hoc human checks demonstrably did not catch #092 (see events.log). R6 improves documentation but not mechanical reliability. **De-prioritized after critical review**. | None. |
| **C. Value-case gating for external-endorsement premises in `decompose.md`** — When a work item's Value rests on vendor guidance / external endorsement without a grounded codebase premise, require the agent to flag it explicitly at `decompose.md:23`, and the user-approval step at `decompose.md:29` must pause on such items. This targets the literal #092 mechanism. | S | False positives: legitimate vendor-guided work exists. The trigger is narrow — "external endorsement + unverified codebase prerequisite," not "external endorsement alone." | Approach A's `premise-unverified` tag ideally ships first so decompose can read it. |
| **D. Closure feedback loop** — Append a note to generating research artifact when a derived ticket closes wontfix with premise-failure. | M | 1-2/111 base rate may not justify new infrastructure. No `/wontfix` skill exists; requires a hook or skill-level nudge. Low urgency. | New touchpoint at ticket closure. |
| **F. Automated mechanical grounding check** (new, from web research) — Before the research artifact is accepted, run automated grep/AST probes against every codebase-pointing claim. Unverified claims must be marked `premise-unverified` or resolved before the artifact passes. | M | Requires a small piece of tooling (parse research.md for codebase-pointing claims; run greps). Would have caught #092 deterministically. **Addresses the empirical weakness that post-hoc human checks don't actually cross-check.** Defer if rule-edits (A+C) are judged sufficient. | Tooling infrastructure; non-trivial vs. rule edits. |
| **E. No change** — Skill is close to correct behavior; base rate is low. | — | Leaves the vendor-endorsement-as-value mechanism open; #092-style recurrence remains plausible in web-heavy topics. | — |

## Decision Records

### DR-1: How far to go — revised after critical review

- **Context**: Critical review surfaced (a) internal contradiction in the original "A+B" recommendation (it relied on decompose.md:29 being a gate while Q3 said it wasn't), (b) misdiagnosis of #092's proximate cause (value-case capture, not locator-grounding), and (c) empirical evidence (events.log) that post-hoc human checks did not catch the failure.
- **Options considered**:
  - **(a) Zero tickets** — Protocol is mostly fine (85-95% norm, 1-2/111 base rate). #092 was concentrated in one web-heavy artifact.
  - **(b) A only** — Codify the citation norm and fix prerequisites framing. Cheapest, most evidence-grounded; does not target the #092 value-capture mechanism.
  - **(c) A + C** — Codify citation + gate external-endorsement value cases. Two S-effort rule edits, both at the correct layer of the #092 failure mode.
  - **(d) A + C + F** — Add mechanical grounding check. Strongest coverage; requires tooling.
  - **(e) Epic / full restructuring** — Disproportionate.

- **Recommendation**: **(c) A + C.** This is two paired rule edits, S-effort each, at the actual failure layers: A hardens the synthesis-time citation norm; C targets the decomposition-time value-case mechanism that let #092's vendor-quote-as-value through the user gate. The original A+B was wrong — B is a post-hoc human checklist, and events.log shows post-hoc human checks did not catch #092 in practice.

- **Trade-offs**:
  - A+C preserves the "small edit" discipline while actually targeting the diagnosed mechanism.
  - F would be mechanically stronger but crosses into tooling; deferred because rule edits should close the specific path that failed.
  - The "revisit on recurrence" fallback remains weak without D's closure feedback — a future premise-failure may not be visible without manual audit. This is accepted as the cost of keeping the intervention small.
  - A+C does not address silent value-failure in the 68 "complete" tickets. That is out of scope for this discovery and would require a separate ticket-audit effort.

### DR-2: Dispatch structure — keep parallel, with targeted rule edits

- **Context**: H3 confirmed empirically (all existing post-hoc checks ran and passed during #092's chain). Options: reorder dispatch, gate synthesis, or add mechanical verification.
- **Recommendation**: **Gate synthesis via Approach A's rule edit.** Keep parallel dispatch; add the specific rule that codebase-pointing claims must be anchored by codebase-agent citations or marked unverified. This codifies the 85-95% norm and fixes the bottom quartile.
- **Trade-offs**: If A+C proves insufficient on future web-heavy topics, Approach F (mechanical grounding check) becomes the escalation — it is the only approach in the feasibility table that doesn't rely on human discipline, and empirical evidence from #092 shows human discipline is insufficient when the artifact is web-heavy.

## Open Questions

One scope question for the user (see "Ask" below).

## Summary for decomposition

Two work items expected under the DR-1(c) recommendation:

1. **Codify citation norm + premise-verification in `research.md`** — §2 Codebase Analysis requires file:line citations or `premise-unverified` marks; §5/§6 Feasibility template's Prerequisites column retargeted so codebase-state verification is research work, not implementation work. Empty-corpus searches must be reported as `NOT_FOUND`.
2. **Value-case gating in `decompose.md`** — When Value rests on external endorsement without a grounded codebase premise, require explicit flagging at `decompose.md:23` and pause the user-approval step at `decompose.md:29`.

Both are S-sized rule edits to the `/discovery` skill, at the same protocol surface. Per `decompose.md:33-37` consolidation rule, they could be combined into one ticket (both touch skill files; both are same-neighborhood), but the files are distinct and the mechanisms are at different phase layers, so the Decompose step will likely judge them as two separate tickets.

## Ask for user

The critical review substantially revised the diagnosis. Three scope options remain reasonable; the decision is a user call:

1. **A + C** (recommended) — Two S-effort rule edits targeting the diagnosed failure layers. Keeps intervention small; does not rely on human discipline.
2. **Zero tickets** — The skill is close to correct; base rate is low; #092 is isolated. Accept that web-heavy topics will occasionally produce premise-failures and rely on ambient recurrence detection.
3. **A + C + F** — Adds the mechanical grounding check. Strongest coverage; empirical evidence from #092 supports it (human checks demonstrably didn't catch the failure). Trades "minimal rule edits" for "small piece of tooling."

The recommended default is #1; #2 and #3 are defensible alternatives. **Please confirm which scope to proceed with in decomposition.**
