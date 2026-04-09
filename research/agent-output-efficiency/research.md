# Research: Agent Output Efficiency

## Research Questions

1. **What does caveman propose?** What specific patterns does it use for brevity, and which translate to a structured harness vs. freeform prompting?
   → **Answered.** Caveman uses graduated intensity levels (lite/full/ultra) that progressively strip articles, filler, hedging, and grammar. It claims 65-75% token reduction. The "auto-clarity" escape hatch (drop brevity for safety warnings, irreversible actions, confusion) is the most transferable concept. The blanket grammar-stripping is less applicable — it fights Claude Code's built-in output efficiency instructions and adds input tokens on every message.

2. **What has IndyDevDan covered?** What recent content addresses agent output efficiency or communication patterns?
   → **Partially answered.** IndyDevDan's public work focuses on hook-based agent observability (real-time monitoring via event tracking), not output efficiency per se. The observability angle is relevant: measuring what agents actually output is a prerequisite to optimizing it. No specific recent video on brevity/communication patterns found.

3. **Where does the current harness waste output?** Which SKILL.md files, reference docs, and prompts generate the most low-signal output in interactive sessions?
   → **Answered.** Five categories identified (see Codebase Analysis). The biggest waste: (a) subagent prompts with no brevity constraints, (b) synthesis skills reproducing all intermediate findings, (c) phase transition announcements on routine transitions with no surprises.

4. **What's the subagent communication ROI?** How much of a subagent's returned context does the parent actually act on? What report format maximizes utility?
   → **Answered.** Parents see only the subagent's final message — all intermediate tool calls and reasoning stay isolated. Three patterns: unstructured (open-ended research), structured JSON (programmatic orchestration), file-based (chaining). The key lever is specifying output format and length in the dispatch prompt. Most harness skills do neither.

5. **What patterns in current prompts could be trimmed?** Are there redundant instructions, over-specified formats, or verbose templates?
   → **Answered.** Only commit/pr skills have explicit "no conversational text" constraints. All synthesis skills (critical-review, research, pr-review) give subagents full artifact content with no output-length guidance. parallel-agents.md says "Expected output: Summary of what you found and fixed" but doesn't enforce brevity. Phase transition instructions use open-ended "briefly summarize" without defining what brief means.

6. **What does Claude Code's system prompt already say about output efficiency?** How does the harness layer interact with built-in output instructions?
   → **Answered.** The system prompt includes: "Go straight to the point. Try the simplest approach first. Be extra concise." and "Keep your text output brief and direct. Lead with the answer or action, not the reasoning." Anthropic employees get numeric limits (25 words between tool calls, 100 words final response). The harness's SKILL.md files often override these defaults by mandating structured multi-section output, synthesis presentations, and phase transition summaries. The two layers can fight each other.

7. **What trade-offs exist between brevity and correctness?** When does terser output cause information loss that leads to rework?
   → **Answered.** A March 2026 paper (arXiv 2604.00025, 31 models, 1,485 problems) found brevity constraints improved large model accuracy by 26pp on verbosity-induced errors — forcing commitment to correct answers rather than rambling into mistakes. Counter-argument from HN discussion: LLMs are autoregressive, so forcing premature answers can hurt reasoning on genuinely complex problems. The resolution: brevity helps for communication/reporting output but should not constrain internal reasoning (chain-of-thought).

## Codebase Analysis

### Current Output Constraint Landscape

| Skill | Output constraint | Subagent brevity | Phase announcements |
|-------|------------------|-----------------|-------------------|
| commit | "No conversational text — only tool calls" | N/A | N/A |
| pr | "No conversational text — only tool calls" | N/A | N/A |
| lifecycle | "briefly summarize what was accomplished" | None | Yes — per phase |
| discovery | "summarize findings" | None | Yes — per phase |
| critical-review | None | None | N/A |
| research | None | None | Agent batch summary |
| pr-review | None | None | N/A |
| overnight | Specific error messages | N/A | Session plan summary |
| dev | None | None | N/A |
| backlog | None | N/A | N/A |
| diagnose | None | None | Phase findings |

### Pattern: Subagent Prompts Without Output Guidance

From `skills/critical-review/SKILL.md` — reviewer agents receive full artifact content and detailed instructions, but no length constraint:
```
Return findings in this exact format:
[structured sections listed]
[NO LENGTH CONSTRAINT]
```

From `skills/research/SKILL.md` — 3-5 agents dispatched, each receives focused scope but no brevity directive. Agent 5 (Adversarial) receives summarized findings from agents 1-4 with no response-length guidance.

From `claude/reference/parallel-agents.md`:
```
Expected output: Summary of what you found and fixed.
```
This is the closest the harness gets to output guidance — but "summary" is undefined.

### Pattern: Synthesis Skills Reproduce All Intermediate Output

Critical-review, research, and pr-review all follow the same pattern:
1. Dispatch N parallel subagents
2. Receive all N responses
3. Synthesize into structured output
4. Present full synthesis to user (including per-agent sections)

Even empty/failed agent findings trigger warning notes. The synthesis step adds value, but presenting both per-agent findings and synthesis creates redundancy.

### Pattern: Phase Transitions as Status Updates

Lifecycle: "announce the transition and proceed to the next phase automatically. Between phases, briefly summarize what was accomplished and what comes next."

Discovery: "summarize findings, and proceed to the next phase automatically."

These produce 5-6 transition announcements for a complex lifecycle feature. Some are genuinely useful (escalation to Complex tier); most are routine.

### Pattern: Verification Output Volume

`verification-mindset.md` mandates "State claim WITH evidence" — this is load-bearing (prevents false completion claims) but encourages more output, not less. The pattern "Run test command → See: 34/34 pass → All tests pass" is already compressed. The risk is in verification of requirements, where agents sometimes reproduce the full checklist with per-item evidence.

### Pattern: Agents.md Is Already Lean

At 27 lines, the global `Agents.md` is not a source of waste. The conditional-loading table (3 entries) gates additional context behind triggers. This is well-designed — context loads only when relevant.

## Web & Documentation Research

### Caveman Project (github.com/JuliusBrussee/caveman)

Core approach: graduated compression levels that strip linguistic fluff while preserving technical accuracy. Three transferable concepts:

1. **Auto-clarity escape hatch**: Drop brevity for safety warnings, irreversible actions, user confusion. Resume after. This principle applies directly — certain output MUST be verbose (destructive operation confirmations, error diagnostics, ambiguous situations).

2. **Pattern template**: `[thing] [action] [reason]. [next step].` — A structural rule that compresses communication without losing information. More useful as a subagent reporting format than as a user-facing style.

3. **Boundaries**: "Code/commits/PRs: write normal." — Recognizes that code output and formal artifacts should not be compressed. Brevity applies to communication, not artifacts.

Non-transferable: grammar stripping (articles, fragments) fights the system prompt's own efficiency instructions and can make output harder to parse. The wenyan modes are novelty.

### Claude-Token-Efficient (github.com/drona23/claude-token-efficient)

Eight-rule CLAUDE.md that targets: sycophantic framing, file re-reading, whole-file rewrites, unnecessary pleasantries. Claims ~63% output reduction. Simpler than caveman — focuses on behaviors rather than grammar transformation. The "answer first, reasoning after" rule has research backing (arXiv paper) but can hurt complex reasoning.

### Anthropic Best Practices (code.claude.com/docs/en/best-practices)

Key guidance relevant to this topic:

- "Keep CLAUDE.md concise. For each line, ask: 'Would removing this cause Claude to make mistakes?' If not, cut it."
- "Bloated CLAUDE.md files cause Claude to ignore your actual instructions!"
- "Context window is the most important resource to manage."
- Subagents recommended specifically for investigation to avoid context pollution
- "If Claude keeps doing something you don't want despite having a rule against it, the file is probably too long and the rule is getting lost."
- "Ruthlessly prune."

### Hacker News Discussion (item 47581701)

Key arguments:
- **For brevity**: Output tokens cost 5-10x input tokens. Reducing output has direct cost and speed benefits.
- **Against blanket brevity**: LLMs are autoregressive — "thinking is inextricably tied to output." Forcing premature answers causes premature commitment. A CLAUDE.md file loads on every message, so on low-output exchanges it's a net token increase.
- **Pragmatic middle**: Let Claude's defaults stand for reasoning/implementation. Apply brevity constraints only to communication/reporting output.

### Research Paper (arXiv 2604.00025)

31 models, 1,485 problems. Brevity constraints improved large model accuracy by 26 percentage points on problems where verbosity induced errors. Mechanism: forces models to commit to the correct approach rather than rambling through multiple approaches and settling on a wrong one. Important caveat: this applies to answer output, not chain-of-thought reasoning.

### Subagent Communication Patterns (morphllm.com, Claude Code docs)

Three return formats:
1. **Unstructured** — Natural language. Best for research/exploration. Parent interprets.
2. **Structured JSON** — SDK `outputFormat` option. Best for programmatic orchestration.
3. **File-based** — Subagent writes to file, downstream agents read. Best for chaining.

Key insight: "By delegating to a subagent, verbose output stays in the subagent's context window. Only the summary returns to the parent." This isolation is the primary value of subagents for context management.

Practical pattern for brevity: "instruct test runners to 'report only failures' with focused error details rather than full logs."

## Domain & Prior Art

### The Compression Spectrum

| Approach | Scope | Mechanism | Trade-off |
|----------|-------|-----------|-----------|
| Caveman | All output | Grammar transformation | Fights system prompt; adds input tokens |
| Claude-Token-Efficient | All output | Behavioral rules | Simpler but still blanket; can hurt reasoning |
| Per-skill constraints | Skill output | Targeted format/length specs | Requires per-skill tuning; surgical |
| Subagent output specs | Agent-to-agent | Prompt-specified format | Most impactful for multi-agent workflows |
| System prompt defaults | All output | Built-in | Already present; harness skills override it |

### The "Layers" Problem

Claude Code's output efficiency operates in layers, each potentially fighting the others:

1. **System prompt layer**: "Be extra concise. Lead with the answer."
2. **CLAUDE.md layer**: Can add or override instructions
3. **Skill layer**: SKILL.md instructions often mandate structured multi-section output
4. **Reference doc layer**: Conditional-loaded docs add context-specific instructions
5. **Subagent prompt layer**: Dispatch prompts can specify (or not) output expectations
6. **Compaction layer**: Claude Code automatically summarizes prior context when approaching context limits. This is the only layer that operates *retroactively* — it rewrites prior output after the fact. Compaction interacts with brevity in a non-obvious way: redundancy in output is protective, giving the summarizer multiple anchor points to preserve a finding. Terse output that states something exactly once gives compaction a single chance to keep it or drop it. Overnight sessions are far more likely to trigger compaction (longer running), so brevity constraints may need to be *less* aggressive for overnight agents to ensure compaction-resilience.

The harness currently has tight constraints at layers 1 and 2, but skills (layer 3) and subagent dispatch (layer 5) override them with verbose output requirements. The most impactful intervention targets layers 3 and 5 — but any intervention must account for layer 6's retroactive effect, especially for overnight sessions where compaction is most likely.

### The "Signal, Not Volume" Principle

Communication quality is not about saying less — it's about conveying the important information and ensuring the receiver understood. Applied to agent output:

- **User-facing output**: Should convey decisions, findings, and blockers. Should NOT convey routine status, empty-result notices, or redundant summaries.
- **Agent-to-agent output**: Should convey actionable findings in a format the parent can use immediately. Should NOT reproduce raw data, include reasoning preamble, or leave findings unstructured.
- **Verification output**: Should convey evidence compactly (e.g., "Tests: 34/34 pass"). Should NOT reproduce full test output unless failures exist.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| A. Add skill-specific subagent output formats | M | Medium — requires per-skill calibration; too-tight constraints lose reasoning input that parent cannot recover | Audit each skill's dispatch prompts; define output budget per skill type |
| B. Compress synthesis output (bullets not prose, skip empty agents) | S | Medium — compaction (layer 6) may further compress already-terse output, especially in overnight sessions | Modify synthesis instructions in 3 skills; consider compaction resilience |
| C. Compress phase transition announcements to one line | S | Low — preserves transition signal while reducing volume | Edit lifecycle and discovery SKILL.md files |
| D. Add default output guidance to parallel-agents.md | S | Low — advisory, not enforced | Edit one reference doc |
| E. Compress verification evidence format | S | Medium — must not weaken verification discipline; compaction may drop compressed evidence | Define compressed-but-sufficient evidence format |
| F. Blanket brevity CLAUDE.md rules (caveman-style) | S | High — fights system prompt, adds per-message overhead, may degrade reasoning | None, but may cause more problems than it solves |

## Decision Records

### DR-1: Targeted per-skill constraints vs. blanket brevity rules

- **Context**: The harness needs to reduce output waste without degrading reasoning quality or fighting the system prompt.
- **Options considered**:
  - (a) Blanket brevity rules in CLAUDE.md/Agents.md (caveman-style)
  - (b) Targeted output constraints per skill and per subagent dispatch prompt
  - (c) Hybrid: light global guidance + targeted skill-level constraints
- **Recommendation**: Option (c). A single line in Agents.md establishing the principle ("Prefer concise output — lead with findings, skip preamble, compress routine status"), plus targeted constraints in each skill's dispatch prompts and synthesis instructions. This lets the system prompt's existing efficiency instructions work by default while adding precision where the harness overrides them.
- **Trade-offs**: Requires per-skill editing (more work than one CLAUDE.md line), but avoids the blanket-brevity risks (fighting system prompt, degrading reasoning, net-negative token cost on simple exchanges).

### DR-2: Subagent output format — structured specifications per skill type

- **Context**: Subagents currently receive no output-length guidance. Their responses can be arbitrarily long, all of which enters the parent's context. Subagent output is the parent's *reasoning input*, not a user-facing report — the parent cannot ask follow-up questions, so whatever is omitted is permanently lost.
- **Options considered**:
  - (a) Word/token caps ("Keep findings under 150 words")
  - (b) Format specifications ("Return as: ## Findings\n- [bullet]\n## Recommendation\n[one sentence]")
  - (c) Combined: format spec with length guidance
  - (d) Skill-specific format specs that allocate space proportional to the skill's purpose
- **Recommendation**: Option (d). Each skill that dispatches subagents should define a return format appropriate to that skill's information needs. Critical-review subagents need room for evidentiary chains; research subagents need room for citations and context; diagnose subagents need room for error traces. A generic "3-5 bullets, max 20 words" would be adequate for some skills and catastrophically insufficient for others. The principle is: specify format and approximate length in every dispatch prompt, but calibrate per skill, not globally.
- **Trade-offs**: More per-skill editing work than a single template. Requires judgment about what each skill type needs. But avoids the self-defeating pattern of constraining subagent output length while relying on those same subagents to judge what's "critical" enough to escape the constraint.

### DR-3: Phase transition announcements — compress, don't suppress

- **Context**: Lifecycle and discovery announce every phase transition with a summary. Most are routine.
- **Options considered**:
  - (a) Remove all transition announcements
  - (b) Announce only on escalation, unexpected findings, or user-blocking decisions
  - (c) Keep all but compress to one line
- **Recommendation**: Option (c). Compress all transition announcements to a single line (e.g., "Research complete — proceeding to specify") rather than suppressing routine ones. The monitoring infrastructure cannot replace text announcements: TaskCreate/TaskUpdate are not wired into lifecycle skills, the statusline shows current state (not transitions), overnight agents are headless with no statusline or task rendering, and events.log phase_transition records have no real-time consumer. The text announcement is currently the *only* real-time signal that a phase boundary was crossed — suppressing it would make stuck features indistinguishable from progressing ones, especially in overnight contexts.
- **Trade-offs**: Still produces per-phase output, but at ~10 words per transition vs. the current multi-sentence summary. Escalation announcements should remain verbose (explaining why the escalation happened).

### DR-4: Verification output — evidence vs. verbosity

- **Context**: verification-mindset.md is load-bearing but encourages verbose evidence output.
- **Options considered**:
  - (a) Leave as-is (correctness over efficiency)
  - (b) Define compressed evidence format ("Tests: 34/34 pass" not full output; "Build: exit 0" not full log)
  - (c) Evidence in verification, compressed in user-facing report
- **Recommendation**: Option (c). Verification runs remain thorough (full output read by the agent). User-facing claims use compressed evidence format. The agent verifies fully but reports compactly.
- **Trade-offs**: None significant. The verification discipline is about the agent's behavior, not the user-facing output. The user sees "Tests: 34/34 pass" and trusts the agent verified properly.

## Open Questions

- **Measurement**: How do we measure whether output changes actually improve the user experience vs. just reducing tokens? Token count alone doesn't capture whether the user had to re-ask or missed important information. This is a prerequisite for validating any specific numeric constraint — without measurement, any word/bullet limit is a guess. Consider lightweight proxies: user re-ask rate, `/rewind` frequency, morning review "what happened?" follow-ups.
- **Overnight vs. interactive**: Overnight agents should almost certainly have *different* output constraints than interactive agents — and possibly *less* aggressive compression. Overnight sessions are long-running, making compaction likely. Compaction is a second lossy summarization step; if output is already compressed, compaction may drop findings entirely. Overnight output is also consumed differently (morning review, not real-time). The right question is: should overnight output be compaction-resilient (slightly redundant, key findings structurally marked) rather than maximally compressed?
- **Skill-level calibration**: Rather than a binary "verbose by design" opt-out, each skill's output constraints should be calibrated to its information needs. Critical-review exists to surface subtle problems — aggressive brevity defeats its purpose. Research exists to explore — citations and context require space. The decomposition phase should define per-skill output budgets based on what each skill actually needs to convey, not a global standard.
