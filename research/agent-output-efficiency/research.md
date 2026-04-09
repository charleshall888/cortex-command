# Research: Agent Output Efficiency

## Research Questions

1. **What does caveman propose?** → **Answered.** Graduated intensity levels stripping linguistic fluff. The "auto-clarity" escape hatch (drop brevity for safety/confusion) is the most transferable concept. Blanket grammar-stripping fights Claude Code's built-in output instructions.

2. **What has IndyDevDan covered?** → **Partially answered.** Focus on hook-based agent observability, not output efficiency directly. Measuring what agents output is a prerequisite to optimizing it.

3. **Where does the current harness waste output?** → **Answered.** (a) Subagent prompts with no output format guidance, (b) synthesis skills reproducing all intermediate findings, (c) phase transition announcements on routine transitions.

4. **What's the subagent communication ROI?** → **Answered.** Parents see only the final message. Three return patterns: unstructured, structured JSON, file-based. The key lever is specifying output format in the dispatch prompt. Most harness skills do neither.

5. **What patterns could be trimmed?** → **Answered.** Only commit/pr have "no conversational text" constraints. All synthesis skills give subagents no output-length guidance. Phase transitions use open-ended "briefly summarize."

6. **What does the system prompt already say?** → **Answered.** "Go straight to the point. Be extra concise." Harness SKILL.md files often override these defaults with verbose output requirements. The two layers fight each other.

7. **What trade-offs exist between brevity and correctness?** → **Answered.** arXiv 2604.00025: brevity improved accuracy 26pp on verbosity-induced errors. Counter: LLMs reason through output. Resolution: brevity for communication/reporting, not internal reasoning.

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

From `skills/critical-review/SKILL.md` — reviewer agents receive full artifact content but no length constraint. From `skills/research/SKILL.md` — 3-5 agents dispatched with no brevity directive. From `claude/reference/parallel-agents.md` — "Expected output: Summary of what you found and fixed" but "summary" is undefined.

### Pattern: Synthesis Skills Reproduce All Intermediate Output

Critical-review, research, and pr-review: dispatch N subagents → receive all responses → synthesize → present full synthesis including per-agent sections. Even empty/failed agent findings trigger warning notes.

### Pattern: Phase Transitions as Status Updates

Lifecycle and discovery produce 5-6 transition announcements for complex features. Some are genuinely useful (escalation); most are routine.

### Pattern: Verification Output Volume

`verification-mindset.md` mandates "State claim WITH evidence" — load-bearing but verbose. The risk is in requirements verification, where agents reproduce the full checklist with per-item evidence.

## Web & Documentation Research

### Community Approaches

**Caveman** (github.com/JuliusBrussee/caveman): Transferable concepts: (1) auto-clarity escape hatch — drop brevity for safety/confusion, (2) pattern template `[thing] [action] [reason]. [next step]`, (3) boundaries — code/commits/PRs write normal. Non-transferable: grammar stripping fights system prompt.

**Claude-Token-Efficient** (github.com/drona23/claude-token-efficient): Eight behavioral rules targeting sycophancy, re-reading, whole-file rewrites. Simpler than caveman but still blanket.

**Anthropic Best Practices** (code.claude.com): "Keep CLAUDE.md under 200 lines." "Bloated CLAUDE.md files cause Claude to ignore your actual instructions!" "Ruthlessly prune."

**HN Discussion** (item 47581701): For brevity: output tokens cost 5-10x input. Against: LLMs reason through output; CLAUDE.md loads on every message so on low-output exchanges it's a net token increase. Pragmatic middle: brevity for communication, not reasoning.

**arXiv 2604.00025**: 31 models, 1,485 problems. Brevity improved accuracy 26pp on verbosity-induced errors. Caveat: applies to answer output, not chain-of-thought.

### Official Anthropic Sources

**Caveat on Anthropic sources**: These articles are published by the vendor whose revenue scales with API token consumption. Patterns promoting more subagents and more harness complexity also increase API usage. Findings are treated as authoritative for how Claude Code works (they built it) but not as independently validated engineering research. Independent sources (arXiv paper, HN discussion, community projects) provide external perspective where noted.

#### Context Engineering (anthropic.com/engineering/effective-context-engineering)

Core principle: **"Find the smallest set of high-signal tokens that maximize the likelihood of some desired outcome."**

Key patterns:
- Subagent returns should be "condensed, distilled summary of its work (often 1,000-2,000 tokens)" — **Note**: this guidance derives from web-search research subagents returning lists of companies. The harness's evidentiary subagents (code review, adversarial analysis, diagnosis) may have a structurally higher floor. Treat as a reference point from a different domain, not a universal anchor.
- "Clearing tool calls and results" is lightweight compaction — agents rarely need raw outputs after processing.
- Progressive disclosure / JIT loading preferred over pre-loading.
- System prompts need "the right altitude" — specific enough to guide, flexible enough for heuristics.
- **"For an LLM, examples are the 'pictures' worth a thousand words"** — format examples in dispatch prompts are more effective than length caps.

#### Multi-Agent Research System (anthropic.com/engineering/multi-agent-research-system)

- **"Each subagent needs an objective, an output format, guidance on tools, and clear task boundaries"** — every dispatch prompt needs an explicit output format.
- **Lightweight references**: Subagents "call tools to store work in external systems, then pass lightweight references back to the coordinator."
- **"Without detailed task descriptions, agents duplicate work, leave gaps, or fail to find necessary information."**
- **"The best prompts are not strict instructions, but frameworks for collaboration"** that define division of labor, problem-solving approaches, and effort budgets.
- **Performance-token correlation**: "80% of performance variance is explained by token usage alone" (vendor-measured on vendor models; directionally useful but not independently validated). Token efficiency predicts quality, not just cost.

#### Harness Design (anthropic.com/engineering/harness-design-long-running-apps)

- **"Every component in a harness encodes an assumption about what the model can't do on its own, and those assumptions are worth stress testing."** Context anxiety disappeared between Sonnet 4.5 and Opus 4.6, making context-reset scaffolding unnecessary.
- **Self-evaluation failure**: Agents "confidently praise work — even when quality is obviously mediocre." External evaluators are more tractable.
- **"Wording directly shapes output character"** — prompt language steers output style. Skill prompt wording directly determines output verbosity.
- **Sprint contracts**: Explicit success criteria upfront reduce irrelevant output.
- **File-based communication**: "One agent would write a file, another would read it." Lowest-context-cost communication pattern.

#### Managed Agents (anthropic.com/engineering/managed-agents)

- **"The session is not Claude's context window"** — the harness decides what enters context each turn from a durable event log. Events can be transformed before reaching Claude.

#### Claude Code Docs: Costs and Context

- **CLAUDE.md under 200 lines**; specialized instructions should move to skills (on-demand, not always-loaded).
- **Hook-based preprocessing**: Official pattern filters test output to failures only — `grep -A 5 -E '(FAIL|ERROR|error:)' | head -100`. Deterministic, zero model judgment.
- **Compaction**: Triggers at ~95% capacity, retains ~12% of original. Clears tool outputs first, then summarizes. Skill descriptions don't survive — only invoked skills preserved. Subagent transcripts unaffected.
- **Subagent economics**: System prompt 900 tokens (vs 4,200 main). File reads stay isolated. Returns enter parent context untruncated — "running many subagents that each return detailed results can consume significant context."

## Domain & Prior Art

### The Compression Spectrum

| Approach | Scope | Mechanism | Trade-off |
|----------|-------|-----------|-----------|
| Caveman | All output | Grammar transformation | Fights system prompt; adds input tokens |
| Per-skill constraints | Skill output | Targeted format specs | Requires per-skill tuning; surgical |
| Subagent output specs | Agent-to-agent | Format + examples | Most impactful for multi-agent workflows |
| Lightweight references | Agent-to-agent | Write to files, return pointers | Anthropic's own pattern; max context isolation |
| Hook-based preprocessing | Tool output | Filter before context entry | Zero prompt engineering; deterministic |
| System prompt defaults | All output | Built-in | Already present; harness skills override it |

### The Layers Problem

Claude Code's output efficiency operates in 6 layers, each potentially fighting the others:

1. **System prompt**: "Be extra concise. Lead with the answer."
2. **CLAUDE.md**: Can add or override instructions
3. **Skill layer**: SKILL.md instructions often mandate structured multi-section output
4. **Reference doc layer**: Conditional-loaded docs add context-specific instructions
5. **Subagent prompt layer**: Dispatch prompts can specify (or not) output expectations
6. **Compaction layer**: Operates retroactively — rewrites prior output when context fills. Redundancy in output is protective (gives summarizer multiple anchor points). Terse output gets one chance to survive. Overnight sessions are most likely to trigger compaction, so overnight output may need to be *less* aggressively compressed for compaction-resilience.

Skills (layer 3) and subagent dispatch (layer 5) override the system prompt's efficiency instructions. Interventions should target layers 3 and 5 while accounting for layer 6.

### Signal, Not Volume

- **User-facing output**: Convey decisions, findings, blockers. Skip routine status and redundant summaries.
- **Agent-to-agent output**: Convey actionable findings the parent can use immediately. Skip raw data and reasoning preamble.
- **Verification output**: Convey evidence compactly ("Tests: 34/34 pass"). Skip full output unless failures exist.

## Feasibility Assessment

**Critical prerequisite**: Approach H (stress-test) must run first. Its results gate whether approaches A-E are necessary. If removing verbose-by-default instructions produces acceptable output, A-E add unnecessary complexity.

| Phase | Approach | Effort | Risks |
|-------|----------|--------|-------|
| **Gate** | H. Stress-test skills by removing verbose instructions | S | Low — read-only audit |
| **Gate** | G. Hook-based preprocessing for high-volume tool output | S | Low — deterministic, pre-context |
| **If H shows gaps** | A. Add skill-specific subagent output format specs | M | Medium — per-skill calibration needed |
| **If H shows gaps** | B. Compress synthesis output (bullets, skip empty agents) | S | Medium — compaction interaction |
| **If H shows gaps** | C. Compress phase transitions to one line | S | Low — preserves signal |
| **If H shows gaps** | D. Add output guidance to parallel-agents.md | S | Low — advisory |
| **If H shows gaps** | E. Compress verification evidence format | S | Medium — must not weaken discipline |
| **Future** | I. Lightweight references (subagents write to files) | M | Medium — changes communication pattern |

## Decision Records

### DR-1: Targeted per-skill constraints vs. blanket brevity rules

- **Context**: The system prompt already says "be extra concise." Anthropic: "Keep CLAUDE.md under 200 lines" and "move specialized instructions to skills."
- **Recommendation**: No global brevity rules. Focus on targeted constraints in skill dispatch prompts — but **only after stress-testing (H) shows which skills actually need them**. Some skills may produce acceptable output once verbose-by-default instructions are removed.
- **Trade-offs**: Requires H to run first. Per-skill editing when needed. But avoids adding complexity before demonstrating the need.

### DR-2: Subagent output format — structured specifications per skill type

- **Context**: Subagents currently receive no output guidance. Their returns enter the parent's context untruncated. Subagent output is the parent's reasoning input — the parent cannot ask follow-ups.
- **Recommendation**: **Contingent on H.** For skills where stress-testing shows subagent output is excessive, define a return format appropriate to the skill's information needs. Use canonical examples (not length caps) to demonstrate expected output — "for an LLM, examples are the pictures worth a thousand words." Critical-review needs room for evidentiary chains; research needs room for citations; diagnose needs room for error traces. Anthropic's 1,000-2,000 token guidance for web-search subagents is a reference point from a different domain, not an anchor for evidentiary subagents.
- **Trade-offs**: Per-skill calibration work. Requires judgment about what each skill type needs.

### DR-3: Phase transition announcements — compress, don't suppress

- **Context**: Phase transitions are the only real-time signal that a boundary was crossed. TaskCreate/TaskUpdate are not wired into lifecycle. Statusline shows state, not transitions. Overnight agents are headless.
- **Recommendation**: Compress all transition announcements to one line (e.g., "Research complete — proceeding to specify"). Escalation announcements remain verbose.
- **Trade-offs**: Still produces per-phase output (~10 words vs. current multi-sentence summary).

### DR-4: Verification output — evidence vs. verbosity

- **Context**: verification-mindset.md is load-bearing (prevents false claims).
- **Recommendation**: Verification runs remain thorough internally. User-facing claims use compressed evidence format ("Tests: 34/34 pass").
- **Trade-offs**: None significant. Verification discipline is about agent behavior, not user-facing output.

### DR-5: Hook-based preprocessing — deterministic reduction

- **Context**: Anthropic's cost docs show a PreToolUse hook filtering test output to failures only. Deterministic, no model judgment, runs before tokens enter context.
- **Recommendation**: Hooks for deterministic filtering (test output, linter output, build logs). Prompt-based constraints for judgment-requiring formatting (research findings, review analysis). This separation means prompt constraints only cover hard cases.
- **Trade-offs**: Requires shell scripting and settings.json configuration.

### DR-6: Stress-test before adding constraints (PREREQUISITE)

- **Context**: "Every component in a harness encodes an assumption about what the model can't do on its own, and those assumptions are worth stress testing." Context anxiety disappeared between Sonnet 4.5 and Opus 4.6.
- **Recommendation**: **This gates DR-1 and DR-2.** Before adding output constraints, stress-test each skill by removing verbose-by-default instructions and measuring whether Opus 4.6 produces acceptable output on its own. Some skills may need subtraction (removing verbose instructions), not addition (adding brevity constraints).
- **Trade-offs**: Requires empirical testing. But the alternative — adding constraints without testing — risks growing harness complexity while solving phantom problems.

## Open Questions

- **Measurement**: How do we verify output changes improve experience vs. just reducing tokens? Lightweight proxies: re-ask rate, `/rewind` frequency, morning review follow-ups.
- **Overnight vs. interactive**: Overnight sessions are long-running, making compaction likely (12% retention). Overnight output may need compaction-resilience (structural markers, key-finding repetition) rather than maximum compression.
- **Skill-level calibration**: Each skill's output constraints should match its information needs. Critical-review needs evidentiary chains; research needs citations. Define per-skill budgets empirically from H's results, not from a web-search-derived anchor.
