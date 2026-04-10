# Research: Define output floors for interactive approval and overnight compaction

## Epic Reference

Epic research at `research/agent-output-efficiency/research.md` covers the broader output efficiency initiative. This ticket (#050) defines the two output floors that gate downstream compression work (#052, #053).

## Codebase Analysis

### Current Phase Transition Instructions

The sole instruction governing all phase transition output across the codebase:

> "After completing a phase artifact, announce the transition and proceed to the next phase automatically. Between phases, briefly summarize what was accomplished and what comes next." — `skills/lifecycle/SKILL.md`

Discovery uses the same pattern: "summarize findings and proceed to the next phase automatically." No structure, no minimum fields, no format.

### Existing De Facto Floors

| Surface | Location | What it requires |
|---------|----------|-----------------|
| Complete phase summary | `complete.md` lines 88-92 | Feature name, tasks completed, key files changed, open items |
| Orchestrator review pass | `orchestrator-review.md` lines 49-55 | One-line assessment: "Research solid: all 4 questions answered..." |
| Deferral files | `requirements/pipeline.md` lines 90-91 | Severity, context, question, options, action attempted, default choice |
| Exit report | `implement.md` | JSON schema with action, summary, files_changed, issues |
| Morning report | `morning-review/references/walkthrough.md` | Executive summary, per-feature metadata, verification commands |

The orchestrator review's one-line assessment pattern is the closest existing model for what output floors should define.

### Subagent Output Format Spectrum

- **Fully structured**: batch-brain.md (JSON schema with types and examples)
- **Structured headers**: research SKILL.md, critical-review SKILL.md (named sections with bullet placeholders)
- **Template-based**: pr-review protocol.md (exact structure with example output)
- **No guidance**: parallel-agents.md ("Summary of what you found and fixed"), lifecycle builder prompts ("Report what you did")

### Approval Surface Patterns

- **Spec approval** (`specify.md`): "Present the specification summary" — no definition of what the summary includes
- **Plan approval** (`plan.md`): "Present the plan summary (overview + task list)" — slightly more specific
- **Overnight batch review**: Full artifact display with [A]pprove/[R]emove/[Q]uit controls

### File Architecture

The new reference doc would be `claude/reference/output-floors.md`, symlinked to `~/.claude/reference/output-floors.md`. Existing reference docs follow a consistent pattern: `audience: agent` frontmatter, 50-120 lines, conditionally loaded via the Agents.md table. A new trigger row would be added for loading at phase transitions and skill editing.

### Skills Affected by Output Floors

Only 4-6 skills produce phase transitions or subagent dispatch with output format implications: lifecycle, discovery, critical-review, research, pr-review, diagnose. Skills like commit, pr, backlog, dev have no phase announcements and no subagent output — floors have no cross-cutting effect on them.

## Web Research

### What Survives Compaction (Empirical)

Anthropic compaction probes: high-level facts central to the task survive 3/3 times. Obscure specifics (file paths, precise numerical values) survive 0/3 times. Factory.ai evaluation: file/artifact tracking scores 2.19-2.45/5.0 across ALL compression methods — the weakest preservation point. When artifact awareness drops below ~2.5/5.0, agents waste tokens re-fetching.

### Anthropic's Session Memory Compaction Template

Six mandatory sections with priority hierarchy:
1. User corrections & negative feedback (verbatim)
2. Error messages & failures
3. Active work in progress
4. Completed work details
5. Pending tasks
6. Older content (compress or drop)

"Must preserve" elements: exact identifiers, error messages verbatim, user corrections, specific values/configurations, technical constraints discovered.

### Approval Gate Best Practices

AgentC2 pattern: approval surfaces must present "a clear summary of what the agent did, what it wants to do next, the data it is operating on, and the potential impact of approval." Decision-makers should not need to examine raw logs.

### File-Based Bypass

Anthropic's harness-design article: three artifacts must survive context boundaries — feature list (JSON), progress log, version control state. "The model is less likely to inappropriately change or overwrite JSON files." Compaction alone "doesn't always pass perfectly clear instructions to the next agent."

Community pattern: Claude Code users add `## Compact Instructions` sections to CLAUDE.md. Custom instructions replace (not supplement) the default compaction prompt.

### Key Insight

Manus (production agent system) uses schema-defined summary fields when compaction reaches diminishing returns. Sub-agents use constrained output schemas via a "submit results" tool. The planner defines output structure BEFORE task assignment — prior art for pre-defining what shape output must take.

## Requirements & Constraints

### Output-Side Requirements (from project.md)

- "Morning is strategic review — not debugging sessions" — morning review output must be high-signal
- "Surface all failures in the morning report" — failures must be visible
- "Complexity must earn its place" — floor definitions must not add unnecessary complexity
- "ROI matters — the system exists to make shipping faster"

### Overnight Pipeline Design (from pipeline.md, multi-agent.md)

- **Thin orchestrator**: "Read state files and status codes only. Do NOT accumulate implementation details." The orchestrator intentionally avoids consuming detailed conversational output.
- **Morning report reads files**: events.log, review.md, plan.md, deferral files — not compacted conversation history
- **Events.log is the audit trail**: Metrics computed from `feature_complete` events. Structured NDJSON is the durable signal.
- **Hard caps**: Agent stderr capped at 100 lines; learnings truncated to 2000 chars

### Existing Architectural Patterns

- File-based state: "All lifecycle artifacts, backlog items, pipeline state, and session tracking use plain files" (project.md)
- Compaction triggers at ~95% capacity, retains ~12%. Clears tool outputs first, then summarizes. Skill descriptions don't survive.
- The 6-layer output problem (system prompt → CLAUDE.md → skill → reference → subagent → compaction) identified by epic research

### Criticality Matrix Implications

At high/critical criticality: orchestrator review is active at all phase boundaries, review phase is forced, model selection is Sonnet explore / Opus build/review. Output floors interact with the orchestrator review checklists (R1-R5, S1-S6, P1-P7) — these are per-phase quality gates that already define what "good" looks like for each artifact.

## Tradeoffs & Alternatives

### Dimension 1: Single Floor vs. Dual-Track

| Approach | Pros | Cons |
|----------|------|------|
| **Single floor + overnight file addendum** | Avoids context-detection problem; recognizes critical overnight info already lives in files | Must audit for gaps where info lives only in conversation |
| **Dual-track (interactive/overnight)** | Precise calibration per context | No reliable `$IS_OVERNIGHT` signal; doubles maintenance |
| **Universal floor set to highest need** | Simplest | Interactive users see unnecessarily verbose output |

**Recommended**: Single conversational floor + overnight file-based addendum. The interactive/overnight tension is largely resolved by the existing file-based architecture — critical overnight info survives in research.md, spec.md, plan.md, events.log. The addendum identifies any gaps.

### Dimension 2: Format Approach

| Approach | Pros | Cons |
|----------|------|------|
| **Prescriptive templates** | Maximum consistency; machine-parseable | Rigid; fights adaptive output; per-skill awkwardness |
| **Rubric (required categories)** | Flexible per skill type; composable | Less consistent; room for interpretation |
| **Rubric + canonical examples** | Best of both; matches existing ref doc patterns | Examples tend to become de facto templates |

**Recommended**: Rubric with canonical examples, acknowledging the adversarial finding that examples tend to ossify into templates. Design examples as minimum-viable output (not aspirational) so that template-anchoring still produces acceptable results.

### Dimension 3: Skill Calibration

| Approach | Pros | Cons |
|----------|------|------|
| **Universal minimums** | Simplest; one rubric everywhere | Different skills have structurally different needs |
| **Per-skill floor table** | Precise | Maintenance scales with skill count (~20+) |
| **Skill-type category overrides** | Balanced precision/maintenance (4 categories) | Classification tax; lifecycle spans multiple categories |

**Recommended**: Universal minimums as the baseline. If specific skills need higher floors, they specify those in their own SKILL.md or phase reference files — not in the centralized doc. This avoids the category classification tax.

### Dimension 4: Compaction Strategy

| Approach | Pros | Cons |
|----------|------|------|
| **Structural markers in conversation** | Low cost; natural summary boundaries | Still competes with 12% retention budget |
| **File-based capture for critical info** | Completely solves compaction; morning report already reads files | Adds file I/O to transitions |
| **Hybrid** | Defense in depth | Dual maintenance |

**Recommended**: Focus on file-based capture for anything the morning report needs. The overnight pipeline was designed to read files, not compacted conversation. The one gap is orchestrator decision rationale — solve by adding a rationale field to events.log entries.

### Dimension 5: Loading Strategy

| Approach | Pros | Cons |
|----------|------|------|
| **Always-loaded** | Always available | Wastes context on non-output operations |
| **Conditional loading** | Consistent with existing architecture | Output quality is continuous, not exceptional — trigger may not fire |
| **Embedded in phase reference files** | Zero loading risk; co-located with consumption | Duplicates universal baseline; no single source of truth |

**Recommended**: Standalone reference doc with conditional loading, with the acknowledgment that the conditional trigger must be carefully worded. The doc serves as the authoritative source for #052 and #053; phase reference files can cross-reference it.

## Adversarial Review

### Failure Modes

1. **Orchestrator rationale gap**: The "false dilemma" (single floor works for both contexts) is partially wrong. Overnight orchestrator decision rationale (why features were selected, how escalations were resolved) lives only in conversation. This is the one genuine overnight gap — solve by adding a `rationale` field to events.log entries, not by making conversational output more verbose.

2. **Examples ossify into templates**: Every flexible rubric in this codebase has tightened into a rigid template within 1-2 iterations (P4 checklist, exit report schema, review verdict JSON). The rubric-with-examples approach will produce template-like behavior regardless of intent. Mitigation: design the examples as minimum-viable output so that anchoring still produces acceptable results.

3. **Category system will rot**: The proposed 4-category override system (evidentiary, synthesis, orchestration, utility) has no tooling enforcement — `/skill-creator` doesn't know about categories. Skills span categories (lifecycle is orchestration AND synthesis AND evidence). Mitigation: abandon categories; use a single universal floor with per-skill overrides embedded in their own reference files.

4. **Conditional loading is for exceptional decisions, not continuous requirements**: Existing triggers work because they fire at recognizable decision points ("about to claim success"). "About to write a phase transition summary" is baseline behavior, not exceptional. If the doc fails to load, the fallback is the status quo. Mitigation: make the trigger explicit and tied to events.log writes; accept that some invocations will miss.

5. **Layer 7 problem**: The output-floors reference doc adds a new layer to the 6-layer output control problem. The SKILL.md says "briefly summarize" (layer 3) while the floor says "must include decisions, scope changes, blockers" (layer 4). These are in tension. Mitigation: update the SKILL.md Phase Transition section to replace "briefly summarize" with a cross-reference to the output-floors doc, making layers 3 and 4 consistent rather than competing.

6. **Central reference doc vs. phase reference files**: Phase reference files already define output format for their phase. A centralized doc creates dual source of truth. When plan.md's required fields change, output-floors.md must also update. Mitigation: output-floors.md defines the universal baseline and principles; phase-specific details stay in phase reference files.

### Assumptions That May Not Hold

- "Conditional loading will fire reliably for continuous output quality requirements" — evidence suggests it works for exceptional triggers, not continuous ones
- "Rubric flexibility will be preserved" — codebase pattern shows examples become templates
- "A single conversational floor works for all contexts" — orchestrator rationale is a genuine gap

## Open Questions

- Should the SKILL.md's "briefly summarize what was accomplished and what comes next" be replaced with a cross-reference to the output-floors doc, or should the floor requirements be inlined there to avoid layer conflicts?
- How should the output-floors doc handle the orchestrator rationale gap — recommend a `rationale` field in events.log, or defer to a separate ticket?
