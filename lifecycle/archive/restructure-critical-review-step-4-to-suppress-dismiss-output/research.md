# Research: restructure-critical-review-step-4-to-suppress-dismiss-output

## Epic Reference

Background context: [`research/audit-interactive-phase-output-for-decision-signal/research.md`](../../research/audit-interactive-phase-output-for-decision-signal/research.md). This ticket implements one of the DR-2 recommendations from that epic (restructure critical-review Step 4 to drop Dismiss reporting and restrict Apply to a bullet list). The epic's other recommendations live in sibling tickets and are out of scope here.

## Codebase Analysis

### Target file and target block

- **File**: `skills/critical-review/SKILL.md`.
- **Step 4 block**: lines 197–218.
- **Line 215** (the canonical compact-summary instruction, verbatim):
  > "Present a compact summary: what was changed (one line per fix), what was dismissed and why, and — only if any remain — ask about 'Ask' items in a single consolidated message."
- **Line 205** (Dismiss description + Anchor check, verbatim):
  > "**Dismiss** — the objection is already addressed in the artifact, misreads the stated constraints, or would expand scope in a direction clearly outside the requirements. State the dismissal reason briefly. **Anchor check**: if your dismissal reason cannot be pointed to in the artifact text and lives only in your memory of the conversation, treat it as Ask instead — that is anchoring, not a legitimate dismissal."

### Call sites of `/critical-review`

Three confirmed invocation sites, all within skill reference files:

1. `skills/lifecycle/references/specify.md:150` — §3b, runs when `tier=complex`. Presents Step 3 synthesis + Step 4 compact summary as the user-facing approval surface **immediately before** the AskUserQuestion for spec approval.
2. `skills/lifecycle/references/plan.md:243` — §3b, runs when `tier=complex`. Same consumption pattern as specify: synthesis + compact summary before plan approval.
3. `skills/discovery/references/research.md:128` — §6b, invocation is **looser**: "Run `/critical-review` on `research/{topic}/research.md`. Address any significant challenges raised before proceeding." No AskUserQuestion approval gate. Dismiss listings are not flow-blocking.

The specify and plan sites consume Step 4 output *directly* as part of the approval surface. Discovery is the outlier — no approval gate.

### Anchor check and intra-Step-4 interaction

Line 205's Anchor check enforces a "pointer-to-artifact-text" rule on Dismiss decisions. The codebase search found no other intra-Step-4 conflict with the proposed restructure, but the adversarial review (below) contests the claim that the anchor check is "orthogonal to output format." The current compact summary is the only external audit surface for the anchor check; removing it shifts the check from live-verified to self-graded-internal.

### clarify-critic as reference precedent

`skills/lifecycle/references/clarify-critic.md` uses the same Apply/Dismiss/Ask disposition framework (documented as "reproduced to avoid silent drift"). Its events.log schema:

```yaml
- ts: <ISO 8601>
  event: clarify_critic
  feature: <slug>
  findings: <array of prose strings — one per objection>
  dispositions:
    apply: <count>
    dismiss: <count>
    ask: <count>
  applied_fixes: <array of descriptions>
  status: "ok"
```

Key traits: findings array is prose objections (not categorized by disposition), dispositions are counts only, applied_fixes is an array of change descriptions, **no dismiss-reasons array**. This pattern is what Tradeoffs agent proposed extending — but the adversarial review contests whether it is actually "extension" or "belated normalization" of an existing inconsistent practice.

### Existing `critical_review` events.log entries

Two incompatible formats coexist in the repo:

- **JSONL** (single-line): `{"ts": ..., "event": "critical_review", "phase": "...", "applied": [...], "dismissed": [], "asked": [...]}` — e.g. `lifecycle/archive/add-characterization-tests-for-batch-runner-pre-extraction/events.log:13`.
- **YAML multi-line block**: seen in `lifecycle/archive/extract-optional-skills-to-plugin/events.log:63–131` — includes `dispositions: {apply:, dismiss:, ask:, defer:}` and `applied_fixes:` list, and in some variants a `dismissed:` or `deferred:` list with prose.

**Schema inconsistency is real**: Dismiss rationale is sometimes captured (YAML variant) and sometimes omitted (JSONL variant). Alt C (Tradeoffs agent's recommendation) is better described as *formalizing* this into one shape rather than *adding* a new field.

### Downstream event consumers

A grep of `claude/overnight/report.py` and `claude/pipeline/metrics.py` for `critical_review`, `applied_fixes`, `dismissed`, `dispositions` returned **zero matches**. `parse_events` uses `json.loads` per line, which silently drops YAML multi-line entries as malformed. **No consumer reads `critical_review` events today**; the log is write-only in practice. This is a load-bearing finding: it disconfirms the claim that the events.log schema has meaningful "downstream impact," and it weakens the Alt C argument that post-hoc audit substitutes for live oversight.

### Bullet conventions from existing skills

- `commit`: imperative verb + scope, concise, no restatement of the bug that triggered the fix.
- `pr`: "bullet per logical change — keep high-level, not a changelog."
- Existing `critical_review` `applied_fixes` entries use the verb + scope pattern: "R10 side_effect changed to feature-name-keyed callable", "R1: removed 'must use namespaced form' claim; bare name is correct per plugin-dev reference", "R10: promoted [SHOULD] → [MUST] with 1500-token abort threshold."

These are decision-oriented (strengthened, narrowed, clarified, added, removed), not location-oriented (updated R10). The adversarial review identifies the difference as load-bearing for whether the fix produces useful output.

### Test/fixture coverage

No test fixtures for `/critical-review` Step 4 output format. `tests/test_skill_contracts.py` validates SKILL.md frontmatter and structure only. No assertions need updating.

## Web Research

### Opus 4.7 instruction literalism

Anthropic's [Claude 4 best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-4-best-practices) establishes that Opus 4.7 follows instructions more literally than prior models. Direct quotes relevant to this restructure:

- "Claude Opus 4.7 interprets prompts more literally and explicitly than Claude Opus 4.6, particularly at lower effort levels. It will not silently generalize an instruction from one item to another, and it will not infer requests you didn't make."
- Applied to code review: "When a review prompt says things like 'only report high-severity issues,' 'be conservative,' or 'don't nitpick,' Claude Opus 4.7 may follow that instruction more faithfully than earlier models did — it may investigate the code just as thoroughly, identify the bugs, and then not report findings it judges to be below your stated bar."
- On format framing: "Tell Claude what to do instead of what not to do... Positive examples showing how Claude can communicate with the appropriate level of concision tend to be more effective than negative examples or instructions that tell the model what not to do."
- On removing stale scaffolding: "If you've added scaffolding to force interim status messages ('After every 3 tool calls, summarize progress'), try removing it."

### Implications for the fix

Two directional takeaways, **in tension**:

1. **Pro-fix**: "Remove-requirement" framing (drop "what was dismissed and why" from the instruction) is the reliable lever, not "be briefer." This matches DR-4 from the epic.
2. **Anti-fix**: Opus 4.7 literalism also means the *new* instruction ("bullet list of what changed in the artifact") may be interpreted in its most literal reading — file-level diffs rather than decision-oriented summaries. The fix's format spec needs an example to avoid this failure mode.

### Review/rework reporting conventions

- [Conventional Comments](https://conventionalcomments.org/): "non-blocking" label is the closest analog to Dismiss; bookkeeping lives with comments, not in the compact merge summary. Ask-analog (unresolved) is the only surface in the compact view.
- [Keep a Changelog](https://quackback.io/blog/keep-a-changelog): user-facing entries describe what changed in the artifact, not what was raised and decided during review.
- GitHub PR model: resolved conversations disappear from the compact view; only unresolved items remain surfaced. Dismissal has its own audit record, separate from the merge summary.
- Gerrit/Phabricator: comments "are nonbinding... have no formal effect on the code review" — detailed audit lives behind the scenes; decision surface is compact.

### Dismissal audit prior art

The ["Rejection Log" / COVENANT.md pattern](https://dev.to/thebenlamm/your-ai-agent-has-a-rejection-log-heres-why-it-matters-1dkn) is explicit precedent for recording dismissals to a separate file (for later audit) while suppressing them from the conversation. Structural format:

```
## Withheld
- [Issue description]
  REASON: [Rule citation]
  CONFIDENCE: [Assessment level]
```

Caveat ([Audit Trail Paradox](https://dev.to/arkforge-ceo/the-audit-trail-paradox-why-your-llm-logs-arent-proof-1c21)): "regulators read 'audit trail' as proof of execution, not merely records of what participants claimed happened." A log of dismissals has audit value only when it can be spot-checked against the artifact text; write-only logs provide no oversight.

## Requirements & Constraints

### Output-floors

`claude/reference/output-floors.md` prescribes minimum content for **phase transitions and approval surfaces** ("Decisions / Scope delta / Blockers / Next"). Step 4 of `/critical-review` is **not** a phase transition — it is an in-phase post-synthesis action inside a skill. No output-floor rule governs the Step 4 compact summary, so the restructure is not floor-constrained.

### Project philosophy

`requirements/project.md` supports the direction:

- "Context efficiency" quality attribute: addresses preprocessing of tool output, not skill narration — directionally supportive but not load-bearing.
- "Handoff readiness" philosophy: applies to overnight handoff; `/critical-review` Step 4 is interactive-only and never handed off.
- "Complexity must earn its place" and "In doubt, the simpler solution is correct."
- **Interactive human oversight is a design principle**: clarify and specify phases always run interactively (user is present). Step 4 sits inside this interactive loop and is not a handoff artifact.

### Multi-agent and observability

- `requirements/multi-agent.md`: no uniform-output requirement across invocations of `/critical-review`. Per-caller customization is acceptable.
- `requirements/observability.md`: no mandate to log dispositions to events.log for `/critical-review`. clarify-critic is the only disposition framework with an explicit logging requirement; `/critical-review` has precedent (existing entries) but no written contract.

### Preservation anchors

Ticket #052's preservation anchors for anti-warmth ("Do not be balanced. Do not reassure. Find the problems.") are in the reviewer and synthesis prompts — not Step 4. Changing Step 4 output format does not touch #052 preservation anchors.

### Scope boundaries

Changing `/critical-review` behavior is in-scope per project.md ("AI workflow orchestration (skills, lifecycle, pipeline, discovery, backlog)"). No requirements file blocks the change.

## Tradeoffs & Alternatives

Five alternatives were considered. All presume the fix's core move (drop Dismiss from Step 4's user-visible compact summary) but differ on what remains visible and what is captured elsewhere.

### Alt A — Pure removal (no Apply output either)

Drop both Dismiss and Apply reporting. Only surface Ask items when present; otherwise emit nothing. Artifact is the record.

- **Pros**: maximally aligned with DR-1 ("only user decision points surface"). Strongest DR-4 compliance (no output surface = no narration).
- **Cons**: user has no evidence that a review happened. If an Apply fix is substantive (semantic inversion, MUST→SHOULD promotion, new acceptance criterion), the user approves a changed artifact with no signal that anything changed.
- **Crosses the trust threshold**: yes.

### Alt B — Ticket-as-written

Drop Dismiss reporting; keep Apply as "bullet list of what changed" (one line per fix, naming the change not the objection); keep Ask items consolidated.

- **Pros**: minimal implementation (one phrase removal). Directly implements DR-2. Preserves visibility of Apply work.
- **Cons**: the Apply format is under-specified. Under Opus 4.7 literalism, bullets can be location-oriented ("R10 updated") or decision-oriented ("R10 strengthened from SHOULD to MUST"). DR-2 explicitly favors decision-oriented phrasing, but the instruction as written doesn't encode this.
- **Crosses the trust threshold**: on the threshold — depends on bullet quality.

### Alt C — Dismiss-to-events.log (Tradeoffs agent's original recommendation)

Alt B plus writing Dismiss rationale + findings + dispositions to `lifecycle/{feature}/events.log` for post-hoc audit.

- **Pros**: extends an existing-but-inconsistent practice (some `critical_review` entries already include `dismissed:` lists). Apparent symmetry with clarify-critic.
- **Cons**: **no consumer reads `critical_review` events today** (verified via grep of `claude/**/*.py`). Two incompatible schemas (JSONL vs YAML multi-line) coexist and the JSONL parser silently drops YAML entries. The audit is write-only in practice — "trust-threshold crossing dressed as audit."
- **Crosses the trust threshold**: yes, without real mitigation.

### Alt D — Structured sub-agent for Step 4

Dispatch a sub-agent that returns a JSON schema (`{applied, dismissed, ask}`); orchestrator renders only the user-visible fields.

- **Pros**: structural DR-4 compliance (sub-agents constrained by output format spec, which is highly reliable per Anthropic guidance).
- **Cons**: significantly higher implementation complexity. Moves classification error from orchestrator to sub-agent. Extra dispatch latency. Overkill for a one-file output restructure.
- **Crosses the trust threshold**: no, but cost is disproportionate.

### Alt E — No output when no Ask items

Alt B plus: when zero Ask items exist, emit nothing (not even Apply bullets).

- **Pros**: maximizes silence when nothing needs user attention.
- **Cons**: asymmetric — user sees narration only when there's a question, never when there's a silent Apply. Applies crosses the trust threshold most aggressively.
- **Crosses the trust threshold**: yes (strongest version of the silent-change failure mode).

### Mitigation-augmented variant — Alt B + count-only Dismiss line + worked-example format

Proposed by the adversarial review. Core changes:

1. Drop "what was dismissed and why" from the user-visible summary.
2. Replace with a one-line count: "Dismiss: N objections (reasons in working notes)" — preserves anchor-check incentive because the count is visible and the user can ask for details if suspicious.
3. Specify the Apply bullet format explicitly with a worked example: "Apply bullets describe the direction of the change (strengthened, narrowed, clarified, added, removed), not the location. Example: 'R10 strengthened from SHOULD to MUST'; counter-example: 'R10 updated.'"
4. Tighten the anchor check: "Before finalizing a Dismiss, quote the exact artifact line that grounds the dismissal into your working notes. If no quote is possible, treat as Ask." Preserves teeth without requiring live user audit.
5. Drop events.log capture (Alt C) unless a consumer is landed in the same change. Honesty beats ceremony.

This variant preserves the core "remove-requirement" lever (no verbose Dismiss walkthrough) while addressing the anchor-check-weakening and decision-legibility failure modes surfaced by the adversarial review. **This is the recommended path forward for the spec to refine.**

## Adversarial Review

The adversarial agent surfaced eight failure modes and three additional concerns. Summarized below (full agent output retained in conversation context — refer to it during spec).

### Eight primary failure modes

1. **Anchor check weakening is real, not orthogonal**. The live user-visible dismissal is the current external enforcement for the anchor check. Removing it converts the anchor check from cross-verifiable to self-graded-internal. A retro (`retros/2026-04-15-1121-extract-optional-skills-to-plugin.md:17`) documents a real instance of mis-disposition (under-escalation as Ask that should have been escalated harder); a silent-Dismiss design would have hidden this entirely.
2. **Opus 4.7 literalism cuts both ways**. "Ask items remain as the only user-directed output when present" can cause substantive Apply fixes to be emitted as skeletal bullets ("R10 updated") when the decision is consequential (semantic inversion, MUST→SHOULD promotion, new acceptance criterion).
3. **Nested invocation risk is significant**. Specify §3b and plan §3b present Step 4 output as the approval surface. "Clarified scope" vs. "narrowed scope" are visually identical bullets but materially different decisions. Verification cost shifts from "read rationale" to "re-read the full artifact" — in practice users skip this.
4. **events.log schema risk is under-stated but in the opposite direction**. The codebase agent claimed downstream consumers exist; verification (grep) shows zero consumers. Alt C's audit capture is write-only — no oversight value without a reader.
5. **Retro evidence is disconfirming**. The sole retro mentioning Dismiss documents **under-escalation** (opposite failure mode from the ticket's framing). The claim "Dismiss requirement causes verbose disposition walkthroughs" is a hypothesis, not evidence — may be a speculative problem.
6. **DR-4 counter-reading**. "Bullet list of what changed in the artifact" under Opus 4.7 literalism produces file-level diffs ("updated R3"), which DR-2 explicitly contrasts with the interpretive framing the ticket wants. Format spec may actively prescribe the less-useful bullet style.
7. **Alt C's "follows clarify-critic precedent" is contested**. Dismiss capture is inconsistently present in existing `critical_review` events; Alt C is better described as "normalize an existing inconsistent practice" than "extend precedent." And no consumer reads the log.
8. **Silent-change / trust threshold**. Alt A, C, and E all cross a trust threshold where the user loses oversight without compensating live signal. Alt C is "trust-threshold crossing dressed as audit."

### Three additional concerns

- **F9 (in-place artifact write + silent Apply = no undo path)**: Step 4 writes the updated artifact before the user sees the compact summary. Under a misleading bullet, the user approves; `/commit` stages the change before the user notices the actual edit.
- **F10 (non-uniform call-site compliance)**: discovery §6b lacks the AskUserQuestion gate that specify/plan have. The Apply-bullet-only signal there is weaker — user may proceed without re-reading the research artifact at all.
- **F11 (epic-wide silence scope-creep)**: paired with sibling ticket #068 (which suppresses Dismiss at clarify-critic), the combined effect is epic-wide Dismiss silence. User inference-tracking across phases ("why did the agent come back to this in specify after it was dismissed in clarify?") becomes unrecoverable.

### Disconfirmed assumptions

- "Step 3 already showed all objections" — true at Step 3 emission, but objections scroll off-screen during Step 4's artifact rewrite before approval.
- "Users don't need Dismiss rationale" — true in the median case, false in the edge case where the orchestrator dismisses incorrectly. Fix optimizes for median at cost of edge.
- "events.log capture is audit-equivalent to live surfacing" — false. Log is write-only.

### Recommended mitigations (from adversarial review)

1. **Keep a one-line count-only Dismiss surface**: "Dismiss: N objections" preserves anchor-check incentive while eliminating prose walkthrough.
2. **Make Apply bullets decision-oriented with a worked example in SKILL.md**: "R10 strengthened from SHOULD to MUST" not "R10 updated."
3. **Consider retaining current Dismiss output at discovery §6b** only — the weaker call site, where users have less re-read pressure. Uniformity across call sites is not required per `multi-agent.md`.
4. **Tighten the anchor check** to require quoting artifact text into working notes before finalizing a Dismiss.
5. **Drop events.log capture unless a consumer is landed in the same ticket**. Otherwise the audit is ceremonial.
6. **Consider sequencing**: land sibling ticket #068 (suppress-dismiss-rationale-leak in clarify-critic) first; monitor for under-escalation regressions; only then apply to `/critical-review`.

## Open Questions

These are design and scope questions for the Spec phase to resolve. Each has competing evidence — none are self-resolvable from the research alone.

**All items below are deferred to Spec.** Rationale: each requires a design decision with user preference input (not further investigation), and the Spec phase's structured interview is the right gate for resolving them. The Research Exit Gate is satisfied by this explicit deferral.

1. **Count-only Dismiss surface vs. full removal**: Should Step 4 retain a one-line "Dismiss: N objections" surface (adversarial mitigation) to preserve anchor-check pressure, or go fully silent (ticket-as-written + DR-2)? Tradeoff: full removal is DR-2 purist but loses live audit pressure; count-only breaks the "silent on Dismiss" rule but preserves anchor-check teeth and adds minimal noise.

2. **Apply bullet format specification**: Should the restructured Step 4 include a worked example that prescribes decision-oriented bullets ("R10 strengthened from SHOULD to MUST") and forbids location-only bullets ("R10 updated")? The web research says Opus 4.7 literalism rewards positive format specification over negative prohibitions — suggests yes. Ticket body does not specify. Decision affects the entire usefulness of the fix.

3. **Uniform vs. per-call-site application**: Should the fix apply uniformly to all three call sites (specify §3b, plan §3b, discovery §6b), or differ at discovery §6b (where the consumption is looser)? Adversarial review recommends considering discovery as an exception. `multi-agent.md` does not require uniformity. Ticket body implies uniformity.

4. **Anchor-check tightening**: Should the anchor-check instruction at line 205 be tightened to require quoting the grounding artifact text into working notes before finalizing a Dismiss (compensating for the lost live audit)? Or is the current anchor-check wording sufficient even without user visibility?

5. **events.log capture (Alt C) without a consumer**: Should Dismiss rationale be captured to events.log even though no consumer reads `critical_review` events today? Options: (a) skip capture (honesty); (b) capture and land a consumer in `claude/pipeline/metrics.py` as part of this ticket (scope expansion); (c) capture without a consumer and accept it as write-only (rejected by adversarial).

6. **Sequencing with sibling ticket #068**: Should this ticket wait until #068 (clarify-critic Dismiss suppression) ships and has been monitored for under-escalation regressions? Both are in epic #066 and carry the same failure mode risk. The research does not block sequencing, but it is a risk-reduction measure worth considering.

7. **Handling of the Apply-as-silent-change edge case**: If an Apply fix performs a semantic inversion (e.g., changes a MUST to a SHOULD based on an objection), does the one-line Apply bullet suffice, or should there be a trigger for fuller description (e.g., MUST/SHOULD promotion, scope narrowing)? The ticket body doesn't address this; the adversarial review identifies it as a core failure mode.

8. **Scope of Step 4 rewrite**: Does the restructure touch only line 215 (the compact-summary instruction), or does it also need to revise line 205 (the Dismiss description + Anchor check)? The adversarial review argues line 205 needs tightening; the ticket body implies line 215 is the sole target.
