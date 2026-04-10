# Research: Add subagent output formats and apply imperative-intensity rewrites (#053)

## Epic Reference

Epic research: `research/agent-output-efficiency/research.md` — covers DR-1 through DR-6. DR-6 (stress-test gate) was answered NO by #052 (zero high-confidence removal candidates). This ticket delivers DR-1/DR-2: targeted constraints where they earn their place. The epic's research on subagent output format guidance, the layers problem, and the compression spectrum all apply.

---

## Codebase Analysis

### Axis B pattern inventory across all 9 skills

Grep pattern from ticket acceptance criteria: `CRITICAL:|You MUST|ALWAYS |NEVER |REQUIRED to|think about|think through|IMPORTANT:|make sure to|be sure to|remember to|!`

**Primary findings (ALL-CAPS patterns):**

| File | Line | Content | Category |
|------|------|---------|----------|
| `diagnose/SKILL.md` | 16 | `ALWAYS find root cause before attempting fixes. No fixes without completing Phase 1.` | Preservation item (core principle) |
| `diagnose/SKILL.md` | 22 | `**BEFORE attempting ANY fix:**` | Preservation item (same core principle) |
| `diagnose/SKILL.md` | 187 | `DO NOT attempt Fix #4 without completing the team investigation protocol` | Control flow gate (exclusion category 3) |
| `diagnose/SKILL.md` | 397 | `**Never fix just where the error appears.**` | **Unresolved — see Open Questions Q1** |
| `lifecycle/references/review.md` | 64 | `CRITICAL: The Verdict section MUST contain a JSON object with exactly these fields:` | Inside code fence (exclusion category 6); also output-channel directive (exclusion category 2) — **see Open Questions Q2** |
| `lifecycle/references/review.md` | 72 | `Your review.md MUST include a ## Requirements Drift section` | Inside code fence — same question |
| `lifecycle/references/review.md` | 78 | `The requirements_drift value in the verdict JSON MUST match` | Inside code fence — same question |
| `lifecycle/references/review.md` | 80 | `you MUST also include a ## Suggested Requirements Update` | Inside code fence — same question |
| `lifecycle/references/implement.md` | 155 | `Always use /commit for all commits — orchestrator checkpoints included. Never use raw git commands` | Constraints table prose — **see Open Questions Q3** |
| `lifecycle/references/plan.md` | 183 | `**Critical rule**` (bold, in prose) | Possible CRITICAL-family candidate — **see Open Questions Q3** |

**Analogues (softer imperative patterns):** Essentially absent across the 9-skill corpus. Zero occurrences of `IMPORTANT:`, `make sure to`, `be sure to`, `remember to` in standalone prose context (outside code fences). The 9 skills were already written in largely direct, softened style.

**Additional Axis B patterns from migration plugin Section 5 (thinking words):** `think about → consider`, `think through → evaluate`, `I think → I believe`, `think carefully → consider carefully`, `thinking → reasoning/considering`. These also appear to be absent in a quick scan but should be verified per-file during implementation.

**Net Axis B scope estimate:** 2–4 instances outside exclusion categories, pending resolution of open questions. Substantially smaller than the ticket's framing implied.

---

### Axis A gap inventory: subagent dispatch prompts

| Skill/File | Agent dispatched | Format spec present? | Gap |
|---|---|---|---|
| `research/SKILL.md` | Agents 1–5 | ✓ (structured `Output format:` sections) | None |
| `critical-review/SKILL.md` reviewer agents | 3–4 reviewer agents | ✓ (`## Findings: {angle}` template) | None |
| `critical-review/SKILL.md` Opus synthesis | Opus synthesis agent | ✗ | No structured output sections prescribed; narrative-only "single coherent challenge" instruction |
| `critical-review/SKILL.md` fallback single agent | Fallback agent (Step 2c) | ✗ | Same as synthesis |
| `lifecycle/references/research.md` researcher agents | Parallel researcher agents | ✓ (4-section template with named headers) | None |
| `lifecycle/references/plan.md` plan agents | Plan agents | ✓ (detailed plan format) | None |
| `lifecycle/references/implement.md` builder agents | Per-task builder agents | ✗ (partial) | File output specified; conversational reply format not specified ("Report what you did and any issues encountered") |
| `lifecycle/references/review.md` reviewer agent | Review subagent | ✓ (writes structured review.md) | None |
| `lifecycle/references/clarify-critic.md` critic agent | Clarify critic | ✗ (partial) | Prose-list instruction ("Return a list of objections only — one per finding, written as prose") but no labeled section structure or field names |
| `lifecycle/references/orchestrator-review.md` fix agents | Fix agents | ✗ (partial) | File rewrite specified; conversational reply format not specified |
| `pr-review/references/protocol.md` all agents | Haiku triage, 4 Sonnet reviewers, Opus synthesis | ✓ (explicit `## Output format` sections for all 6) | None |
| `discovery/references/research.md` | Main orchestrating agent (sequential phases) | N/A | Not a dispatch prompt — main agent protocol. **No Axis A work here.** |
| `discovery/references/orchestrator-review.md` fix agents | Fix agents | ✗ (partial) | Same gap as lifecycle/orchestrator-review |
| `diagnose/SKILL.md` competing-hypotheses teammates | Agent teams (gated by env var) | Partial (3-field description present, no format example) | Missing the actual format template/example for the 3-field output (root cause assertion, supporting evidence, rebuttal) |
| `overnight/SKILL.md` | Delegates to Python runner (`claude.overnight.*`) | N/A | Dispatch prompts are in Python code, not in SKILL.md. Adding format specs to SKILL.md would be the wrong layer. **No Axis A work here.** |
| `dev/SKILL.md` | Routes to other skills via delegation statements | N/A | No Agent tool calls in dev. **No Axis A work here.** |
| `backlog/SKILL.md` | No subagent dispatch | N/A | **No Axis A work here.** |

**Axis A real work summary:**
1. `critical-review/SKILL.md` — add structured output format to Opus synthesis agent and fallback single-agent prompts
2. `lifecycle/references/implement.md` — add conversational reply format spec for builder agents (alongside existing file-output spec)
3. `lifecycle/references/clarify-critic.md` — add labeled section structure or field names to critic return format
4. `lifecycle/references/orchestrator-review.md` and `discovery/references/orchestrator-review.md` — add reply format for fix agents (minor — file rewrite is primary, reply is secondary)
5. `diagnose/SKILL.md` — add format example for competing-hypotheses teammate output (low priority — gated by env var)

Skills with no Axis A gaps: `research`, reviewer in `critical-review`, `lifecycle/references/research.md`, `lifecycle/references/plan.md`, `lifecycle/references/review.md`, all `pr-review` agents.

---

### Synthesis compression candidates (Axis A — compress presentation)

Ticket requires: "Compress synthesis presentation in critical-review, research, pr-review — bullets not prose, skip empty/failed agent sections."

Current state:
- `critical-review/SKILL.md` Opus synthesis: "synthesize all reviewer findings into a single coherent narrative challenge" — prose presentation, not compressed. **Compression candidate.**
- `research/SKILL.md` Step 4 synthesis: structured output with section headers — already compressed. Minor cleanup of prose preamble possible.
- `pr-review` Opus synthesis: has structured `## Output format` section with labeled fields — already structured. Per-skill calibration confirms no further compression needed.

Net synthesis compression scope: `critical-review/SKILL.md` Opus synthesis prompt (change from narrative to structured/bullet format).

---

### dev/SKILL.md DV1 and DV2 current state

**DV1** (line 87): `"This is a conversational suggestion — lifecycle runs its own full assessment in Step 3."`
- Location: End of a sentence in `## Step 2: Criticality Pre-Assessment` prose.
- Analysis: Parenthetical that tells the orchestrator its output is advisory. Removing it leaves the sentence as a straight instruction without the hedge. **Surgical removal candidate** — does not affect downstream consumers, and the lifecycle skill already describes its own assessment process. Low risk.

**DV2** (lines 116-119): The full template:
```
> **Criticality suggestion: `<level>`** — `<one-sentence justification>`. Lifecycle will run its own full assessment; this is just a starting point.
```
- Location: Inside `## Step 2: Criticality Pre-Assessment` as the output template for the suggestion.
- Analysis: This is the format spec for the user-facing message itself. Removing it removes the output template — the skill would either produce no suggestion or an unformatted one. **This is NOT a removal candidate; it is the skill's output format spec for this step.** The "Lifecycle will run its own full assessment; this is just a starting point." is hedging prose within the template. **Narrower candidate: remove only the hedging clause from within the template**, leaving the template structure intact: `> **Criticality suggestion: \`<level>\`** — \`<one-sentence justification>\`.`

---

### Preservation decisions — current state

All 10 preservation items from the ticket confirmed present. Current line numbers:

| Item | File | Current line(s) |
|------|------|----------------|
| "Do not soften or editorialize" | `critical-review/SKILL.md` | 173 |
| Distinct-angle rule | `critical-review/SKILL.md` | 26, 65-66 |
| "⚠️ Agent N returned no findings" strings | `research/SKILL.md` | 181, 184 (and repeated) |
| Contradiction handling | `research/SKILL.md` | 186-188 |
| "root cause before fixes" core principle | `diagnose/SKILL.md` | 16 |
| Competing-hypotheses conditions | `diagnose/SKILL.md` | 72-92 |
| Epic-research path announcement | `lifecycle/SKILL.md` | 196 |
| Prerequisite-missing warn | `lifecycle/SKILL.md` | 280 |
| AskUserQuestion directives | `backlog/SKILL.md` | 40, 87, 91 |
| "summarize findings, and proceed" | `discovery/SKILL.md` | 63 |

**Unlisted preservation items identified during research** (not in ticket's list):
- `critical-review/SKILL.md` lines 103 and 129: "Do not be balanced. Do not reassure." — same section as "Do not soften or editorialize", same anti-warmth purpose. Must be preserved alongside the listed item.
- `diagnose/SKILL.md:397`: "**Never fix just where the error appears.**" — separate from the core-principle preservation at line 16 (see Open Questions Q1).

---

## Web Research

### Migration plugin status (2026-04-10)

Plugin confirmed unchanged since 2026-04-09. Core rewrite table (tool overtriggering, Section 1):

| Before | After |
|--------|-------|
| `CRITICAL: You MUST use this tool when...` | `Use this tool when...` |
| `ALWAYS call the search function before...` | `Call the search function before...` |
| `You are REQUIRED to...` | `You should...` |
| `NEVER skip this step` | `Don't skip this step` |

Additional patterns from Section 5 (thinking words — when extended thinking NOT enabled):

| Before | After |
|--------|-------|
| `think about` | `consider` |
| `think through` | `evaluate` |
| `I think` | `I believe` |
| `think carefully` | `consider carefully` |
| `thinking` | `reasoning` / `considering` |

**Sanctioned carve-outs** (aggressive language intentionally retained for severe failure modes):
- Code Exploration snippet (Section 3) — retains `ALWAYS/MUST` because speculation about unread code is severe
- Frontend Design Quality snippet (Section 4) — retains `it is critical that you think outside the box!`

These carve-outs are analogous to the ticket's exclusion categories: aggressive language is retained where the failure mode is severe enough to warrant it. Consistent with the ticket's approach.

### Canonical Axis A output format pattern

From Anthropic's subagent documentation, the canonical pattern is:
```
For each [item type], provide:
- [Field name 1]
- [Field name 2]
- [Field name 3]
```

This is preferred over word/token budgets. Per skill authoring best practices: "examples are pictures worth a thousand words" — provide input/output pairs to show expected format.

**Key constraint**: Subagent dispatch prompts receive ONLY their system prompt body — no parent Claude Code system prompt, no inherited CLAUDE.md. Every output format spec must be fully self-contained within the dispatch prompt.

### Skill authoring best practices (three audit questions)

Per paragraph in SKILL.md:
1. Does Claude really need this explanation?
2. Can I assume Claude knows this?
3. Does this paragraph justify its token cost?

These apply to Axis B candidates: if removing `IMPORTANT:` or `CRITICAL:` leaves a statement that Claude would follow anyway, the emphasis was unnecessary.

---

## Requirements & Constraints

### Applicable requirements (from `requirements/project.md`)

- "Complexity must earn its place" — Axis A additions must add measurable signal per-skill, not generic format specs.
- "Maintainability through simplicity" — Axis B simplification reduces prompt complexity.
- "Handoff readiness: the spec is the entire communication channel" — subagent prompts without format specs fail the handoff standard for overnight agents.
- "Context efficiency" quality attribute — targeted constraints in skills (layer 3) and dispatch prompts (layer 5) are the correct intervention layer.
- "ROI matters" — dry-run spot checks should be limited to highest-risk edits.

### Output floor fields (from `claude/reference/output-floors.md`)

Must remain in lifecycle and discovery phase transition and approval surface outputs:
- Phase Transition Floor: `Decisions`, `Scope delta`, `Blockers`, `Next`
- Approval Surface Floor: `Produced`, `Trade-offs`, `Veto surface`, `Scope boundaries`

These apply only to `lifecycle` and `discovery`. Other skills are not subject to these floors.

### DR-6 implications

Zero removal candidates confirmed from #052 adversarial review. The ticket's scope is:
- Axis A: additions only (new output format specs in dispatch prompts)
- Axis B: softening only (reduce aggressive emphasis; do not remove meaningful instructions)

**Important nuance (from adversarial agent)**: DR-6's "zero removal candidates" closes the removal question but does not directly confirm that softening aggressive imperatives is safe. The question "would softening `ALWAYS find root cause` change diagnostic behavior?" was not explicitly tested. This needs spec-phase resolution.

### Downstream consumer contracts (must not break)

- `events.log` event type and field names — consumed by `claude/overnight/report.py` and `claude/pipeline/metrics.py`
- Review verdict JSON schema: `verdict`, `cycle`, `issues`, `requirements_drift` — exact spelling
- Complexity escalation heuristics: bullet counts under `## Open Questions` and `## Open Decisions`
- `skills/backlog/references/schema.md` — consumed by utilities
- Criticality matrix and model selection tables in `lifecycle/SKILL.md`

---

## Tradeoffs & Alternatives

### Axis A: recommended approach

**A1 (canonical inline examples)** — recommended. Already used by `research/SKILL.md`, `pr-review/references/protocol.md`, and `critical-review/SKILL.md` reviewer agents. Consistent with Anthropic's guidance. Per-skill calibration applies: critical-review synthesis needs room for evidentiary chains; clarify-critic needs room for prose objections; builder agents need compact completion reports.

Avoid A3 (token budgets) — explicitly rejected by ticket. Avoid adding format specs to `overnight/SKILL.md`, `dev/SKILL.md`, `backlog/SKILL.md`, or `discovery/references/research.md` — wrong layer, wrong abstraction, or not a dispatch prompt.

### Axis B: recommended approach

**B1 (full core table + analogues)** — recommended. Analogues are essentially absent in the corpus anyway; B1 and B2 produce identical edits in practice. Confirm with per-file grep before acting.

**Commit strategy: pattern-bucketed** — recommended, with caveat. One commit per pattern family (e.g., "Soften CRITICAL: → bare statement", "Soften ALWAYS → direct imperative") gives per-pattern revert capability. Caveat: per-skill regression isolation requires re-applying the pattern to other skills after revert. For ~5 total instances, this overhead is manageable; pattern-bucketed is still the right choice at this scale.

### Verification strategy: recommended approach

**V2 + V4 with targeted V3**: 
- V4 (`just test`): always run; confirms frontmatter contracts intact
- V2 (grep-based preserved-content checks + manual diff review): confirm every exclusion-category item and preservation decision item is still present post-edit, by content-match not line number
- V3 (selective dry-runs): run `critical-review` on a short plan post-edit (high-risk: synthesis format change), and manually read `lifecycle/references/review.md` diff for CRITICAL/MUST handling. Limit to 2 dry-runs maximum.

### dev/SKILL.md treatment

DV1 (line 87 hedging parenthetical): surgical removal candidate — remove the sentence-ending caveat.
DV2 (lines 116-119): NOT a removal candidate. It is the output format spec for the criticality suggestion. **Narrower action**: remove only the trailing hedge phrase from within the template ("Lifecycle will run its own full assessment; this is just a starting point."), preserving the template structure.

---

## Adversarial Review

### Key challenges to the research findings

**Axis B candidate undercount**: Mixed-case patterns (`**Never fix...**` at diagnose:397, `Always use /commit` at implement:155, `**Critical rule**` at plan:183) were found but not resolved. These are not in the ALL-CAPS subset but ARE in the acceptance criteria grep pattern family if searched case-insensitively. Needs explicit policy decision.

**Injection-resistance copy count unverified**: The ticket says "five verbatim copies" of the injection-resistance instruction in `research/SKILL.md`. The actual copy count in the full 9-skill corpus was not verified. If any copy has drifted, Axis B prose edits near them could introduce inconsistency without triggering preserved-content checks.

**DV2 misclassified**: The moderate-confidence candidate at lines 116-119 (`dev/SKILL.md`) is an output format spec, not removable prose. Removing the full block silences the criticality suggestion output. Only the trailing hedge clause within the template is a removal candidate.

**critical-review preservation gap**: Lines 103 and 129 ("Do not be balanced. Do not reassure.") serve the same anti-warmth purpose as the listed "Do not soften or editorialize" but are not in the preservation list. These must be explicitly marked preserved before Axis B edits touch `critical-review/SKILL.md`.

**review.md code-fence contradiction**: `lifecycle/references/review.md:64-80` CRITICAL/MUST instances are inside a code fence (exclusion category 6) AND function as output-channel directives (exclusion category 2). Axis B policy is "code fences are out of scope entirely." But Axis A adds to the same reviewer prompt template. This creates a contradiction: if Axis A improves the dispatch template, the aggressive imperatives inside it remain, while surrounding additions are softened. Decision needed.

**DR-6 non-coverage of softening**: The #052 adversarial review tested removal, not softening. The "zero removal candidates" result does not directly confirm whether softening aggressive imperatives (e.g., ALWAYS → imperative form) would change model behavior. For the 2-4 real instances, this is low risk given how small the change is — but the gap exists.

---

## Open Questions

- **Q1**: `diagnose/SKILL.md:397` — "**Never fix just where the error appears.**" Is this a preservation item (same protection as line 16's core principle) or a softening candidate (soften `Never` to `Don't` or `Avoid`)? Not in the ticket's preservation list. Deferred to spec for explicit scoping.

- **Q2**: `lifecycle/references/review.md:64-80` — CRITICAL/MUST inside the reviewer prompt template code fence. Policy is "code fences are Axis B-excluded." These instances are also output-channel directives. Should they remain as-is (both exclusion categories apply), or does the Axis A work in this template create an obligation to also apply Axis B? Deferred to spec for explicit ruling.

- **Q3**: Mixed-case instances (`Always use /commit` in implement.md, `**Never fix...` at diagnose:397, `**Critical rule**` in plan.md) — are these in scope for Axis B? The grep pattern `ALWAYS ` (with space) would not catch `Always` (title case). The acceptance criteria says "strictly reduced" grep count for the pattern family. If mixed-case is included in scope, the candidate count grows; if excluded, these are out of scope. Deferred to spec for explicit ruling.

- **Q4**: Should `critical-review/SKILL.md` lines 103 and 129 ("Do not be balanced. Do not reassure.") be formally added to the preservation list before implementation begins? These serve the same anti-warmth purpose as the listed item but are not currently listed. Deferred to spec.

- **Q5**: For the injection-resistance instruction copies: should the implementation agent verify the copy count and content match (not just line number) before beginning Axis B edits? Recommend yes — add to acceptance criteria. Deferred to spec for inclusion.
