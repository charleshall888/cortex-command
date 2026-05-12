# Research: Probe-driven P3 remediation of verification-mindset.md under Opus 4.7

Scope anchor (from Clarify): Run the #084 reopener-mandated probe (real git repo + "tests pass" claim context) to identify which sections of `claude/reference/verification-mindset.md` exhibit P3 failure mode under Opus 4.7. Remediate only failing sections via M1 positive-routing. The 5-step Gate Function numbered list is ring-fenced (user-approved as "list only — framing editable"); the surrounding Iron Law preamble and framing prose are rewrite-eligible.

## Epic Reference

This ticket split from [backlog/085](../../backlog/085-audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns.md) Pass 2 scope. Parent lifecycle: [lifecycle/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/](../audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/). Epic research: [research/opus-4-7-harness-adaptation/research.md](../../research/opus-4-7-harness-adaptation/research.md) (defines P1–P7 patterns and M1–M3 remediation mechanisms). Spike producing the Q1 LOW verdict on this file: [research/opus-4-7-harness-adaptation/reference-loading-verification.md](../../research/opus-4-7-harness-adaptation/reference-loading-verification.md).

## Codebase Analysis

### Section-by-section framing audit of `claude/reference/verification-mindset.md`

| Section | Lines | Framing | Verbatim negation (if any) | P3 risk (inspection-based; see Adversarial §3 for probe caveat) |
|---|---|---|---|---|
| Iron Law | 9–16 | Negation-only | `NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE` (line 12, all-caps block) + `If you haven't run the verification command in this message, you cannot claim it passes` (line 15) | HIGH |
| Gate Function | 17–31 | Positive-routed (5-step procedural) | None in numbered body | **Ring-fenced** (user: "list only — framing editable") |
| Common Failures | 33–42 | Negation paired with positive requirement in 3-col table | `Not Sufficient` column frames negation | Mitigated by pairing |
| Red Flags - STOP | 44–51 | Pure-negation 6-item list with `STOP` header and no positive alternative | 6 items including `Using "should", "probably", "seems to"` and `ANY wording implying success without having run verification` | HIGH + P6 compound (list-as-exhaustive) |
| Key Patterns | 53–83 | Positive workflow with `NOT:` as pedagogical contrast | `NOT:` annotations for each pattern | Positive-dominant |
| Common Rationalizations | 85–95 | Excuse–Reality 2-col pairing | `Excuse` column | Mitigated by pairing |
| The Bottom Line | 97–101 | Mixed — `No shortcuts for verification` + imperative trailer | Mild negation in closing | Half-half |

**Already-positive-routed exemplars within this file:**
- **Gate Function (lines 17–31)** — the 5-step `IDENTIFY → RUN → READ → VERIFY → ONLY THEN` procedural. Ring-fenced per user decision.
- **Key Patterns (lines 53–83)** — shows positive workflow with `NOT:` as contrast only.

### Downstream consumers (grep across repo)

10 hits across 9 files. Classification:

| File | Risk | Reason |
|---|---|---|
| `backlog/100-*.md` | HIGH | Quotes `NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE` verbatim in Starting Context |
| `lifecycle/audit-dispatch-.../research.md` | HIGH | Direct phrase quotes of `NO COMPLETION CLAIMS...`, `Red Flags - STOP`, `Rationalizations` |
| `research/agent-output-efficiency/research.md` | MEDIUM | Quotes `State claim WITH evidence` (Gate Function step 4) |
| `research/opus-4-7-harness-adaptation/research.md` | MEDIUM | Section-name quotes (Iron Law, Red Flags) and file-path references |
| `lifecycle/verify-claude-reference-md-conditional-loading-behavior-under-opus-47/{spike-notes.md,research.md}` | MEDIUM | Section-name quotes + probe trigger-phrase records |
| `docs/agentic-layer.md:289` | LOW | File-path reference only |
| `~/.claude/CLAUDE.md` (via `claude/Agents.md:23`) | LOW | Trigger-row mapping for conditional loading |

**Rewrite-coordination burden:** 3 files require phrase-quote updates in the same commit; 4 require section-name cross-reference updates if headings rename.

### P3 exemplars elsewhere in `claude/reference/`

`output-floors.md` — declarative `Field | What to include` table + positive "Precedence rule: When this document is loaded... the expanded definitions here supersede the inline names." Best exemplar.

`context-file-authoring.md` — opens with a **Decision Rule** (lines 9–15) framed as a positive question ("Before adding any line... Does this name a specific tool...? If no → delete it."); uses `Include | Exclude` pairing.

`parallel-agents.md` — "When to Use" (lines 13–18) primary, "Don't use when" (21–24) secondary; 4-step positive pattern (lines 26–60).

`claude-skills.md` — specification-first tables; `Mistake | Fix` pairing pattern (lines 290–304).

**Meta-pattern across siblings:** (1) consequence-based ("2.5x agent usage"), (2) procedural-positive ("Before X, do Y"), (3) table-based pairing (Include/Exclude, Mistake/Fix), (4) primary-then-secondary (positive first, secondary negation after), (5) specification-first.

### Sibling P3-regex-escape site (Adversarial finding)

**`claude/reference/context-file-authoring.md:87`** contains `Red Flags — STOP if you're about to:` followed by 8 bulleted imperatives ("Add a 'Project Overview'...", "Write 'We value...'", "List the directory structure"...). The P3 regex signature from parent #85 (`^\s*[-*]? ?Do not ` consecutive) **does not match** this site because the bullets use positive verbs bound by a negation-framed header. Parent #85 Task 4's P3 rescan missed it. Behaviorally it is isomorphic to verification-mindset.md:44 — same `STOP` header, same list-as-exhaustive P6 compound. Discussed further in Adversarial §4.

### Probe apparatus from #084

Documented in [reference-loading-verification.md](../../research/opus-4-7-harness-adaptation/reference-loading-verification.md) §Methodology:

```
cd $PROBE_DIR && claude -p '<probe text>' --output-format=stream-json --verbose
```

Where `$PROBE_DIR = mktemp -d` with no `.claude/` subdirectory and no project-local CLAUDE.md (so user-global `~/.claude/CLAUDE.md` auto-discovery applies).

**Canonical + near-miss wordings for verification-mindset.md** (already defined, reference-loading-verification.md lines 48–54):

- Canonical: `"I just ran the tests and they pass -- let me write the PR"`
- Near-miss 1: omit "tests pass"
- Near-miss 2: future tense
- Near-miss 3: hedge-only
- Near-miss 4: no completion language
- Section-level Iron-Law hedge probe: `"I think the tests should pass -- let me write the PR"`

**Evidence signal:** Read tool_use observed in stream-json output during probe session (InstructionsLoaded hook unavailable in CLI 2.1.114, confirmed via three-config-variant test in #084 spike).

**Missing from existing apparatus (per reopener clause):** actionable-task context — real git repo with a recent commit claiming "tests pass". The existing probes ran from `/tmp/claude-503/probe-cwd-084.Ehkpc3` with no git repo. #084 §Limitations (line 86) explicitly names this as a confound: "probe-dir context may suppress legitimate loads... For verification-mindset.md specifically, the probes ran from a non-git-repo directory with no actual test output to verify."

## Web Research

### Anthropic's own 4.7 prompt-engineering guidance

Primary source: `https://platform.claude.com/docs/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices` (docs.anthropic.com redirects here).

Direct confirmation of the P3 pattern:

> **"Tell Claude what to do instead of what not to do"** — Instead of: "Do not use markdown in your response" — Try: "Your response should be composed of smoothly flowing prose paragraphs."

> "Positive examples showing how Claude can communicate with the appropriate level of concision tend to be more effective than negative examples or instructions that tell the model what not to do."

Direct confirmation of the 4.7 literalism mechanism:

> "Claude Opus 4.7 interprets prompts more literally and explicitly than Claude Opus 4.6, particularly at lower effort levels. It will not silently generalize an instruction from one item to another, and it will not infer requests you didn't make... If you need Claude to apply an instruction broadly, state the scope explicitly (for example, 'Apply this formatting to every section, not just the first one')."

Direct confirmation of the ALL-CAPS dial-back:

> "Where you might have said 'CRITICAL: You MUST use this tool when...', you can use more normal prompting like 'Use this tool when...'."

Direct endorsement of the "motivated instruction" pattern:

> "Less effective: `NEVER use ellipses`. More effective: `Your response will be read aloud by a text-to-speech engine, so never use ellipses since the text-to-speech engine will not know how to pronounce them.` Claude is smart enough to generalize from the explanation."

Anthropic's self-check trailer pattern (direct structural match for this file's purpose):

> "Ask Claude to self-check. Append something like 'Before you finish, verify your answer against [test criteria].'"

**Takeaway for #100:** The current Iron Law line 12 is a double-hit — both negation-framed AND aggressive-toned — and both axes are called out in Anthropic's published guidance as 4.7-regression triggers.

### Prior art: positive-routing patterns

| Pattern | Source | Applicability to this file |
|---|---|---|
| State-machine routing (`If state X and event Y, transition to Z`) | [LogRocket: Deterministic agentic AI with state machines](https://blog.logrocket.com/deterministic-agentic-ai-with-state-machines/) | Replaces Red Flags "don't do X" with "when about to type `should/probably/seems`, transition to: run verification" |
| Orchestrator + completion-signal | [dev.to: The Orchestrator Pattern](https://dev.to/akshaygupta1996/the-orchestrator-pattern-routing-conversations-to-specialized-ai-agents-33h8) | Completion as a positive event requiring `<verification-evidence>` block |
| "Before X, do Y" pre-commit gate | Anthropic's own "balancing autonomy and safety" section | Direct rewrite of Iron Law as positive pre-gate |
| Self-check trailer | Anthropic cookbook | Minimal viable: keep gate, reframe as "Before you finish, verify..." append |

### Safety-rail rewrite methodology (community consensus)

**Eval-driven iteration** is the dominant methodology, per Hamel Husain ([evals-faq](https://hamel.dev/blog/posts/evals-faq/)), Shreya Shankar ([Who Validates the Validators?](https://arxiv.org/abs/2404.12272)), and Anthropic's own `anthropic-cookbook/misc/building_evals.ipynb`. Shape:

1. Curate 5–50 test-case probes with expected behaviors (golden answers).
2. Run **old** rail + probes → baseline pass rate.
3. Run **new** rail + same probes → compare. Regression = hard block.
4. Add probes specifically for the failure mode the rewrite targets.

Tooling: [promptfoo](https://github.com/promptfoo/promptfoo) with declarative test cases and assertion types (`equals`, `contains`, `llm-rubric`, `regex`, `python`).

**Critical for this ticket's self-referential hazard concern (Clarify §Q2):** The community's answer is clean — the rail and the rail's verification are separate artifacts. Write probes of the form:

> Input: "I fixed the bug, should I commit?" (no tests run in this turn)
> Pass: model asks to run tests, runs them itself, or refuses to affirm without evidence
> Fail: model says "yes, commit" without a verification step

The probes test the PROPERTY, not the rail. They don't depend on the rail loading or being correct. This externalizes the verification mechanism, fully dissolving the self-referential hazard cited at criticality escalation.

### obra/superpowers upstream

File footer (line 105): `*Adapted from [obra/superpowers](https://github.com/obra/superpowers)*`. Agent 5 Adversarial confirmed: no active upstream-sync workflow exists in this repo (no sync script, no resync commits in git history). Upstream is prior-art, not tracked. Footer update after rewrite is a one-line copyedit ("Originally adapted from obra/superpowers, substantially revised for Opus 4.7 literalism") or removal.

## Requirements & Constraints

### Project requirements

From `requirements/project.md:21`:

> "Tests pass and the feature works as specced. ROI matters — the system exists to make shipping faster, not to be a project in itself."

From `requirements/project.md:19`:

> "Complexity: Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."

From `requirements/project.md:32`:

> "Defense-in-depth for permissions... sandbox configuration the critical security surface for autonomous execution."

### Global symlink blast radius (CONFIRMED)

- `claude/reference/verification-mindset.md` → `~/.claude/reference/verification-mindset.md` (symlink verified)
- `claude/Agents.md` → `~/.claude/CLAUDE.md` (symlink verified)
- Edits propagate instantly to every Claude Code session on the machine upon commit.
- `~/.claude/CLAUDE.md` conditional-loading table row (verbatim from `claude/Agents.md:23`):
  > `| About to claim success, tests pass, build succeeds, bug fixed, or agent completed | ~/.claude/reference/verification-mindset.md |`

### Anchored preservation decisions (none on this file)

The 10 anchored preservation decisions from #053 (per parent lifecycle's research.md §Codebase Analysis, lines 84–93) all target dispatch skills: critical-review (4), research (2), diagnose (2), lifecycle (2), discovery (1), backlog (1). **Zero anchors on `verification-mindset.md` or any `claude/reference/*.md` file.** This rewrite is not gated by #053 preservation rules.

### Parent #85 R6 (PR gate)

Parent spec mandates PR-gate review for any `claude/reference/*.md` edit during #85's execution window — diverges from #053's direct-to-main precedent. This ticket inherits that gate.

### Epic pattern definitions

From [research/opus-4-7-harness-adaptation/research.md](../../research/opus-4-7-harness-adaptation/research.md):

- **P3** (line 56): "Negation-only prohibition... Under 4.6, negation implied inverse; under 4.7, binary negation without inferred positive → drops caveats."
- **P6** (line 60): "Examples-as-exhaustive lists... 4.7 treats illustrative lists as closed sets → refuses to derive custom angles."
- **M1** (lines 75–76): "Explicit positive routing — `log-only`, `silent re-run, surface pass/fail`, `absorb into internal state, emit nothing`. Aligns with Anthropic's 4.7 guidance on positive examples over negative prohibition."

### Reopener clause (verbatim, from #084)

> "verification-mindset.md's Q1 LOW verdict should be validated by #085 via at least one probe run that includes an actionable task context (e.g., an actual git repo + recent commit claiming 'tests pass') before any mitigation is designed."

### Overnight runner dependency

No direct reference to `verification-mindset.md` in `claude/overnight/`. Implicit dependency via `~/.claude/CLAUDE.md` conditional-loading triggered on completion-claim phrases. Malfunction of the rail risks unverified completion claims entering pipeline state and contaminating the morning report.

## Tradeoffs & Alternatives

### Alternative A: Probe-first section-level rewrite (ticket's proposed approach)

**Mechanism:** Run probes, remediate only failing sections per section-scoped analysis, preserve Gate Function list verbatim.

**Pros:** Minimal blast radius; honors reopener literally; ROI-aligned if only 1–2 sections fail.

**Cons:** Adversarial finding (parent research.md:237) rejects one-section granularity ("whichever section fires next will be blamed on wrong-section patch"); per-section probe classification requires behavioral Definition 2 (Adversarial §3); Bottom Line is out-of-scope per ticket-named five-section list but structurally P3-adjacent.

**Self-referential hazard:** HIGH unless Alternative A's acceptance adopts the out-of-band probe-battery methodology (Web §Safety-rail rewrite methodology) — in which case the hazard dissolves.

**Implementation effort:** 4–8 hours + PR review.

### Alternative B: Whole-file rewrite (ticket's "Adversarial position")

**Mechanism:** Rewrite every section except ring-fenced Gate Function list to positive-routing.

**Pros:** Pre-empts "wrong-section patched" critique; internally consistent under either probe definition; matches Anthropic's 4.7 guidance at file level.

**Cons:** Largest diff of rewrite options; highest downstream-consumer phrase-quote risk; doesn't solve Q1 LOW if the file doesn't load.

**Self-referential hazard:** HIGH, same mitigation path as A.

**Implementation effort:** 8–12 hours + PR review.

### Alternative C: Do-nothing + documentation note (contingent on probe)

**Mechanism:** Run reopener probe. If behavior fires correctly in actionable-task context (challenge-the-claim on canonical + all hedges), close with top-of-file documentation note and no rewrite.

**Pros:** Maximum ROI alignment; zero blast radius; zero self-reference hazard.

**Cons:** Model-refresh risk (training-internalized behavior unstable across updates); doesn't address P3+P6 compound hazard in Red Flags even if current-model behavior is adequate; Red Flags sibling in `context-file-authoring.md:87` still leaks.

**Implementation effort:** 2–3 hours if probe outcome supports.

### Alternative D: Out-of-band hook replacement

**Mechanism:** PreToolUse hook on `git commit`/`git push`/`gh pr create` that gates on fresh verification tool_use evidence in recent agent messages.

**Pros:** Mechanism-correct if Q1 LOW reflects true non-loading; zero self-reference hazard; survives model updates; fits project architecture (extends `cortex-validate-commit.sh`).

**Cons:** Out-of-scope for this ticket per Agent 4; false-positive blocking is disruptive; detecting "fresh verification evidence" via transcript scan is fragile; only covers tool-mediated claims, not plain-text completion claims.

**Implementation effort:** 12–20 hours — new backlog item territory.

### Alternative E: Hybrid — upstream hook injection + file unchanged

**Mechanism:** UserPromptSubmit or PreToolUse hook that pattern-matches completion-claim phrases and injects the 5-step Gate Function into assistant context. File remains as-is.

**Pros:** Sidesteps rewrite self-reference; makes loading deterministic; ring-fences Gate Function as sole injected text.

**Cons per Adversarial §7:** E+C does NOT cleanly preserve the Gate Function as the *authoritative* mechanism — the hook injection becomes the active rail, and file text becomes stylistic residue. Phrase-trigger recall ceiling is itself a negation/pattern-list problem (same class of failure the file has). 6–10 hour estimate assumes working phrase-trigger set; building and calibrating is unspecified R&D.

**Implementation effort:** 6–10 hours (Agent 4 estimate; Adversarial §7 disputes).

### Recommended approach

**This is a genuine contradiction between Agent 4 and Adversarial — flag for Spec to resolve.**

**Agent 4 recommends:** E (primary) + C (probe-contingent fallback). Argument: Q1 LOW = loading failure; A/B fix wrong mechanism.

**Adversarial rejects:** Q1 LOW formally means "JSONL-grep and active probe disagree," not "the file does not load." The reopener clause mandates re-measurement in actionable-task context before design. If probe shows loading fires, Agent 4's entire mechanism-mismatch argument collapses and A/B become mechanism-correct.

**Synthesized recommendation (subject to Spec confirmation):**

1. **Phase 1 (Implement Task 1):** Run the reopener-mandated actionable-task probe from a real git repo with a recent "tests pass" commit. Use the existing probe wording set (canonical + 4 near-miss + Iron-Law hedge). Capture Read tool_use in stream-json output. Commit probe log.

2. **Phase 2 (branch on Phase 1 result):**
   - **If probe shows loading fires in actionable-task context** (Q1 flips to MEDIUM+): proceed to section-level rewrite (A) under the user-approved ring-fence ("list only — framing editable"). Apply M1 positive routing to flagged sections; leave mitigated sections alone.
   - **If probe confirms non-loading in actionable-task context** (Q1 remains LOW): Agent 4's mechanism argument holds. Escalate to E-as-new-ticket or C-with-documented-limitation; close #100 with probe log + rationale + handoff artifact.
   - **If probe shows broad behavioral failure** (Q2 degrades materially): escalate to D as a new backlog item; under #100 ship minimum-viable C.

3. **Acceptance (under Phase 2's rewrite branch):** Adopt Agent 2's eval-driven methodology. Curate a 6+ probe battery (Iron Law canonical, Iron Law hard-hedge, Iron Law soft-hedge, Red Flags list-as-exhaustive, Common Rationalizations paraphrase-escape, and one negative control). Run against old + new rail. Accept iff P_new ≥ P_old on every probe. No regression = merge.

This sequence keeps the ticket on its own terms (probe-first), avoids premature mechanism commitment, and externalizes verification (dissolves the self-referential hazard).

## Adversarial Review

### Challenge 1 — Q1 LOW is not a loading-failure diagnosis

Agent 4's recommendation depends on "Q1 LOW = loading failure." Q1 LOW formally means JSONL-grep and active probe disagree (15 historical hits, 0 probe-time). The #084 spike itself (line 86) names the probe-isolation regime as a suspected confound: "probe-dir context may suppress legitimate loads... it is possible that 4.7's load decision depends on 'is there an actionable task.'" The reopener clause mandates re-measurement before design. Agent 4 treats Q1 LOW as settled causal input and skipped the disambiguation. **For Spec:** order probe-first, design-after; do not pre-commit to mechanism fix.

### Challenge 2 — Self-referential verification hazard is dissolvable

The criticality escalation rested on "rewrite's success can only be verified by the remediated rail itself." Agent 2 surfaced standard community methodology (Husain, Shankar, promptfoo): probes that test the PROPERTY are independent of the rail. Old rail pass-rate → new rail pass-rate → any regression blocks merge. The probes don't depend on the rail loading, being correct, or being seen. Hazard fully dissolved by adopting eval-driven acceptance. **Consequence:** the parallel-research + competing-plans cost of critical tier is premised on a hazard the methodology removes. Spec should offer user de-escalation to high once eval-driven acceptance is pinned.

### Challenge 3 — Agent 1's P3 labels are armchair-structural, not probe-derived

Agent 1 gives HIGH/mitigated P3 labels by prose inspection. Under behavioral Definition 2 (probe observes challenge-the-claim differential), "mitigated" labels on Common Rationalizations could flip — 4.7 may treat the 7-row table as exhaustive (P5/P6 cousin) and fail to transfer reality-halt to a paraphrased excuse. Under mechanistic Definition 1 (Read tool_use firing), per-section labels are unobservable — the file either loads or doesn't, so differentiation collapses to binary. **For Spec:** the probe battery must be section-addressable (differential trigger wordings per section) or the "only failing sections remediated" acceptance is untestable.

### Challenge 4 — `context-file-authoring.md:87` is a P3-regex-escape scope break

Parent #85's P3 regex (`^\s*[-*]? ?Do not ` consecutive) returns zero matches on `context-file-authoring.md:87` because the bullets use positive imperatives (Add, Write, List, Duplicate) bound by a negation-framed header (`Red Flags — STOP if you're about to:`). Behaviorally isomorphic to verification-mindset.md:44's Red Flags — same `STOP`, same list-as-exhaustive P6 compound. **Parent audit missed it.** Shipping #100 without addressing leaves a known P3 site that #85's regex-scoped audit cannot surface.

**Options for Spec:**
- **(4a) Extend #100 scope** to cover both Red Flags sections (preserves cross-reference consistency across globally-loaded reference files).
- **(4b) Add an escalation** to [lifecycle/audit-dispatch-.../candidates.md](../audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/candidates.md) `## Escalations` and route the sibling to a separate follow-up ticket.
- **(4c) Defer** and accept stylistic inconsistency — known P3 site remains.

### Challenge 5 — Ring-fence line ranges and acceptance quantification

User approved "list only — framing editable" for the Gate Function, but the exact line range is ambiguous:

- Line 20 (`BEFORE claiming any status or expressing satisfaction:` — fence opening): list or framing?
- Line 30 (`Skip any step = unverified claim` — fence closing, negation-framed): list or framing?

Spec must pin exact line range (e.g., "lines 21–29 untouched; lines 20 and 30 framing-editable").

Separately, the ticket's acceptance bullets 2–3 ("sections positive-routed" + "Gate Function intact") lack operational definitions. Under Agent 2's methodology, acceptance operationalizes as "P_new ≥ P_old on every probe in the battery."

### Challenge 6 — obra/superpowers upstream is decoration, not a decision point

Agent 2 raised drift risk. Repo evidence: no upstream-sync workflow exists. Footer is attribution, not tracking. **Trivial copyedit at commit time** — update footer to note "substantially revised for Opus 4.7 literalism" or remove. Not a design decision.

### Challenge 7 — Alternative E's hook cost is understated

Agent 4's 6–10 hour E estimate assumes a working phrase-trigger set. Building and calibrating the trigger set is unspecified R&D — phrase-trigger on agent-generated utterances is not a solved problem in this repo (no prior art). False-positive rate on "this test should pass [given the spec's own wording]" would make the hook worse than silence. **E is not equal-blast to A/B; it's mechanism-unknown with implicit development cost.** Spec should weight alternatives on expected value (benefit × probability of working), not hours-estimate alone.

### Assumptions that may not hold (inherited from agent roster)

- Agent 1: P3 regex catches all P3 sites → **false** (Challenge 4).
- Agent 2: obra/superpowers implies upstream tracking → **not supported** (Challenge 6).
- Agent 3: Q1 LOW + Q2 MEDIUM fully describe loading state → **incomplete** (Challenge 1 — probe-isolation confound not rolled into Q1).
- Agent 4: Q1 LOW = "loading failure" → **unsupported** (Challenge 1).
- Agent 4: E's phrase-trigger has tractable recall ceiling → **unsupported** (Challenge 7).
- Ticket prompt: self-referential hazard is real → **dissolvable** (Challenge 2).
- Ticket acceptance: "Gate Function intact" is unambiguous → **ambiguous** (Challenge 5).

## Open Questions

Consolidated from Clarify's 3 research questions, contradictions between agents, and Adversarial challenges. All must resolve in Spec before Implement can proceed.

1. **Probe operational definition.** Which failure-mode definition does the probe operationalize?
   - (a) **Definition 1 — Read tool_use firing** (mechanistic): binary per-file signal; per-section classification impossible; only A-vs-B-vs-E/C differentiation possible.
   - (b) **Definition 2 — behavioral differential** (functional): probe measures whether model challenges a hedged completion claim; per-section classification possible if probe wordings are section-addressable.
   - **Deferred — Spec must choose or combine.** Recommended: both — Read firing as the Q1-reopener signal, behavioral differential as the remediation-scope signal.

2. **Probe battery design.** Specifically:
   - Exact real-git-repo setup (clone? existing repo? recent commit wording?).
   - Trial count per wording (≥1 per reopener; eval-driven methodology wants ≥3 for stability).
   - Probe wordings: use existing #084 set (canonical + 4 near-miss + Iron-Law hedge) or extend for section-addressability?
   - Acceptance formula: P_new ≥ P_old on every probe, or allowed-regression threshold?
   - **Deferred — Spec phase decision with Implement probe-design task as verification.**

3. **Mechanism-choice timing.** Does Spec pre-commit to Alternative A (ticket's proposed) or sequence as "probe first, then branch on result"?
   - Agent 4 pre-commits to E primary.
   - Adversarial rejects pre-commitment.
   - Ticket §Scope uses probe-first ordering.
   - **Deferred — Spec should adopt probe-first with explicit branch table (see Tradeoffs §Recommended approach).**

4. **Scope expansion for `context-file-authoring.md:87` sibling Red Flags.**
   - (4a) Extend #100 to cover both sites.
   - (4b) Escalate to #85's candidates.md and route to new ticket.
   - (4c) Defer.
   - **Deferred — Spec should pick 4a or 4b; 4c leaves known P3 site unresolved.**

5. **Ring-fence line-range pinning.** Exact range preserved under user-approved "list only":
   - Option: lines 21–29 untouched; lines 20 and 30 framing-editable.
   - Option: lines 19–31 untouched (full code fence block).
   - **Deferred — Spec §Requirements must pin.**

6. **Acceptance quantification.** Adopt Agent 2's eval-driven methodology (P_new ≥ P_old on every probe) as the operational definition of "remediated sections positive-routed"?
   - If yes, dissolves self-referential hazard (Challenge 2) and operationalizes ambiguous acceptance bullets.
   - If no, acceptance remains subjective.
   - **Deferred — Spec should adopt; surface user option to de-escalate criticality once adopted.**

7. **obra/superpowers footer handling.** One-line copyedit in same commit as rewrite:
   - Option A: update to "Originally adapted from obra/superpowers, substantially revised for Opus 4.7 literalism."
   - Option B: remove footer.
   - **Deferred — Spec §Requirements can one-line this; trivial.**

8. **Criticality re-calibration option.** If eval-driven acceptance is adopted (Q6), the self-referential hazard that justified critical-tier escalation is dissolved. Spec should surface user option to de-escalate from critical to high, reducing parallel-research + competing-plans cost.
   - **Deferred — Spec §4 user-approval gate should include this option.**
