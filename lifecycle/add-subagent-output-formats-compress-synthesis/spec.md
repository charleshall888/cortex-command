# Specification: Add subagent output formats and apply imperative-intensity rewrites (#053)

> **Epic reference**: `research/agent-output-efficiency/research.md` — DR-6 closed negative (#052). This ticket delivers DR-1/DR-2: targeted additions (Axis A) and softening (Axis B) within defined exclusion boundaries.

## Problem Statement

Nine core SKILL.md files dispatch subagents with no output format guidance, causing inconsistent and unstructured returns that degrade parent context quality. These same files contain aggressive capitalized imperatives (CRITICAL:, ALWAYS, NEVER, YOU MUST) that cause Opus 4.6 to overtrigger — the model is trained to interpret this language as panic, leading to overcorrection. Anthropic's migration guidance prescribes softening these patterns to normal imperatives. This ticket applies both fixes — adding format specs (Axis A) and softening imperatives (Axis B) — within precisely-defined exclusion boundaries established by #052's adversarial review.

## Requirements

### Axis A — Subagent output format specs

**A1 (Must-have)** — `critical-review/SKILL.md`: The Opus synthesis agent dispatch prompt and the fallback single-agent dispatch prompt each include a structured output format spec with named sections (not a prose-only instruction). The format spec must preserve adversarial stance and evidentiary depth: it must NOT include any form of balanced or positive summary section (e.g., "## What Went Well", "## Recommendation", "## Strengths"). Sections should cover objections, through-lines, tensions, and concerns — not endorsements.
Acceptance: Interactive/session-dependent — dispatch prompt blocks require context-aware inspection to verify: (a) the format spec is in the synthesis/fallback block (not the reviewer block), and (b) no balanced or endorsement sections are introduced.

**A2 (Must-have)** — `critical-review/SKILL.md`: The Opus synthesis presentation is compressed from narrative to structured bullet format. Synthesis skips empty/failed agent sections (no empty section headers or "⚠️ Agent N returned no findings" repeated into the synthesis output). Bullet format constraint: each objection or finding is a discrete bullet rather than embedded in a multi-objection prose paragraph. Bullets may be multi-sentence when quoting artifact text as evidence — the constraint is against multi-objection paragraphs, not against detailed individual findings.
Acceptance: Interactive/session-dependent — manual inspection of the synthesis prompt confirms "bullets not prose" instruction and "skip empty sections" instruction are present, and the format guidance explicitly permits multi-sentence bullets with citations.

**A3 (Must-have)** — `lifecycle/references/implement.md`: The builder agent dispatch prompt includes a reply format spec for what the agent should report back conversationally (in addition to the existing file-output instructions). The format spec must cover: task name or ID, completion status (completed/partial/failed), files modified, verification outcome, and any issues or deviations from the spec. Format: "For each task completed, report: task name, status, files modified, verification outcome, issues or deviations."
Acceptance: `grep -c "For each\|Report.*:" skills/lifecycle/references/implement.md` ≥ 1 in the builder dispatch block. Interactive/session-dependent: verify grep hit is inside the dispatch block and covers the five named fields above.

**A4 (Should-have)** — `lifecycle/references/clarify-critic.md`: The clarify-critic agent return format includes at least one labeled section header or named-field list (in addition to the existing "list of objections" instruction).
Acceptance: Interactive/session-dependent — manual inspection of the critic dispatch prompt confirms a format spec with labeled structure is present.

**A5 (Should-have)** — `lifecycle/references/orchestrator-review.md` and `discovery/references/orchestrator-review.md`: Fix agent dispatch prompts each include a reply format spec covering what the agent should report back (what was changed and why, at minimum).
Acceptance: Interactive/session-dependent — manual inspection of each fix agent prompt confirms a reply format spec is present.

**A6 (Nice-to-have)** — `diagnose/SKILL.md`: The competing-hypotheses teammate output spec includes a concrete format example for the three-field output (root cause assertion, supporting evidence, rebuttal). Gated by `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` — only include if the edit fits naturally; do not force.
Acceptance: Interactive/session-dependent — manual inspection confirms example format block is present near the teammate output spec.

### Axis B — Imperative-intensity rewrite

**B1 (Must-have)** — Core rewrite table applied across all 9 SKILL.md files and their reference files (outside exclusion categories). Patterns to soften:

| Before | After |
|--------|-------|
| `CRITICAL: X` | `X` (bare statement) |
| `ALWAYS [verb]` | `[verb]` (direct imperative) |
| `NEVER [verb]` | `Don't [verb]` |
| `You MUST` / `you must` / `You must` | `You should` |
| `REQUIRED to` | `should` |
| `think about` | `consider` |
| `think through` | `evaluate` |

Acceptance: For each of the 9 SKILL.md files plus all referenced files in scope, the pre-edit and post-edit grep counts for the pattern `CRITICAL:|[Yy]ou [Mm]ust|ALWAYS |NEVER |REQUIRED to|think about|think through` (excluding code fence content) are logged. Post-edit count ≤ pre-edit count per file. For any file where count is unchanged: a documented rationale entry exists confirming no qualifying candidates were found outside exclusion categories. Note: `REQUIRED to` is included as a confirmation pattern — it is expected to have count 0 in all files; an unchanged count of 0 is valid with rationale "pattern not present in this file."

**B2 (Should-have)** — Clear analogues applied where present (IMPORTANT:, make sure to, be sure to, remember to, rhetorical !). These patterns are essentially absent from the 9-skill corpus (verified in research); this requirement is a confirmation pass.
Acceptance: Same grep-count logging approach as B1, for pattern `IMPORTANT:|make sure to|be sure to|remember to`.

**B3 (Should-have)** — `dev/SKILL.md` DV1: Remove the hedging parenthetical at line 87 — the clause "This is a conversational suggestion — lifecycle runs its own full assessment in Step 3." Verify by content of the sentence before removing; if line 87 has drifted, search by content, not line number.
Acceptance: `grep -c "This is a conversational suggestion" skills/dev/SKILL.md` = 0.

**B4 (Should-have)** — `dev/SKILL.md` DV2: Remove the trailing hedge clause from within the criticality suggestion template at lines 116-119. Remove only "Lifecycle will run its own full assessment; this is just a starting point." from the template body. Preserve the template structure (`> **Criticality suggestion: ...`).
Acceptance: `grep -c "Lifecycle will run its own full assessment" skills/dev/SKILL.md` = 0. `grep -c "Criticality suggestion" skills/dev/SKILL.md` ≥ 1 (template structure preserved).

### Preservation and scope discipline

**P1 (Must-have)** — All listed preservation decisions remain present by content-match grep after all edits. Preservation list (content to search for; current line numbers are advisory — verify by grep, not line number):

| Content | File |
|---------|------|
| `Do not soften or editorialize` | `skills/critical-review/SKILL.md` |
| `Do not be balanced` | `skills/critical-review/SKILL.md` |
| `Do not reassure` | `skills/critical-review/SKILL.md` |
| `No two derived angles` (or `Each angle must be distinct`) | `skills/critical-review/SKILL.md` |
| `⚠️ Agent [N] returned no findings` | `skills/research/SKILL.md` |
| `note the contradiction explicitly under` | `skills/research/SKILL.md` |
| `ALWAYS find root cause before attempting fixes` | `skills/diagnose/SKILL.md` |
| `Never fix just where the error appears` | `skills/diagnose/SKILL.md` |
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | `skills/diagnose/SKILL.md` |
| `**Critical rule**` | `skills/lifecycle/references/plan.md` |
| `Found epic research at` | `skills/lifecycle/SKILL.md` |
| `warn if prerequisite artifacts are missing` | `skills/lifecycle/SKILL.md` |
| `AskUserQuestion` | `skills/backlog/SKILL.md` |
| `summarize findings, and proceed` | `skills/discovery/SKILL.md` |

Acceptance: Each grep returns ≥ 1 match in its target file post-edit. Any miss is a blocking failure.

**P2 (Must-have)** — Injection-resistance instructions verified before Axis B begins. Count verbatim copies of the injection-resistance instruction across all 9 skills and reference files using `grep -r "All web content.*untrusted external data" skills/` — record the count. Verify each copy is verbatim (not drifted). Only begin Axis B edits after this count is recorded.
Acceptance: `grep -rc "All web content.*untrusted external data" skills/` records count ≥ 1 before any edits begin.

**P3 (Must-have)** — Downstream consumer contracts unchanged: event type names and field names (phase_transition, lifecycle_start, complexity_override, etc.), review verdict JSON fields (verdict, cycle, issues, requirements_drift), complexity escalation section headers (## Open Questions, ## Open Decisions), backlog schema field names.
Acceptance: `just test` exits 0 (tests validate skill frontmatter contracts). Interactive/session-dependent: manual diff confirms no event type names or verdict JSON field names were modified.

### Final verification

**V1 (Must-have)** — `just test` exits 0.
Acceptance: `just test` exits 0.

**V2 (Must-have)** — Manual diff review of all edits confirms intent is preserved and no unintended rewrites occurred.
Acceptance: Interactive/session-dependent — implementer reviews the full diff before committing each pattern-bucketed commit.

**V3 (Must-have)** — Dry-run spot check: invoke `critical-review` on a short plan artifact after the synthesis format change and confirm the output is structured (not narrative-only). A minimal invocation (single short plan, one review pass) is sufficient — the goal is confirming the synthesis prompt change produces structured bullet output with adversarial stance intact.
Acceptance: Interactive/session-dependent — output contains labeled sections or named fields (not a single prose paragraph), and no balanced/endorsement sections appear.

**V4 (Must-have)** — Confirm `lifecycle/references/review.md` CRITICAL/MUST instances are unchanged after all Axis B edits complete.
Acceptance: `grep -c "CRITICAL:" skills/lifecycle/references/review.md` post-edit = pre-edit count (record pre-edit count before starting).

## Non-Requirements

- No removal of any meaningful instructions (DR-6 closed negative — removal rubric is out of scope)
- No edits outside the 9 SKILL.md files and their listed reference files
- No edits to hooks, settings.json, dashboard, overnight runner code (`claude/overnight/`, `claude/pipeline/`), requirements docs, `claude/reference/output-floors.md`, tests, or bin
- `overnight/SKILL.md`: no Axis A work — dispatch prompts live in the Python runner, not in the skill file
- `dev/SKILL.md`, `backlog/SKILL.md`: no Axis A work — neither dispatches subagents via the Agent tool
- `discovery/references/research.md`: no Axis A work — describes a sequential protocol for the main agent, not subagent dispatch prompts
- No schema changes to events.log, review verdict JSON, or backlog schema
- Mixed-case/bold variants (title-case `Always`, bold `**Never**`, bold `**Critical rule**`) are out of scope for Axis B — ALL-CAPS only
- Code fence content is out of scope for Axis B (exclusion category 6)
- `lifecycle/references/review.md` CRITICAL/MUST instances are out of scope for Axis B — these are output-channel directives (exclusion category 2) inside the reviewer prompt template. They are unfenced prose, NOT inside a code fence; the protection comes from their role as functional control directives for the review verdict JSON schema
- Single-word ALL-CAPS procedural markers (e.g., `BEFORE`, `THEN`, `STOP`, `ANY`) are out of scope for Axis B — the rewrite table targets multi-word imperative constructions (CRITICAL:, ALWAYS, NEVER, YOU MUST), not procedural annotation words

## Edge Cases

- **Exclusion category ambiguity**: When a pattern could be read as either a prose rewrite candidate or an output-channel directive, treat it as an output-channel directive and preserve it. Error toward preservation.
- **diagnose:397 preservation**: "**Never fix just where the error appears.**" at `diagnose/SKILL.md:397` is a preservation item (same diagnostic methodology family as line 16). Do not apply Axis B to it. Verify by grep post-edit.
- **review.md CRITICAL/MUST**: These instances are unfenced prose in the reviewer prompt template — they are NOT in a code fence. They are excluded as output-channel directives (exclusion category 2) because they are control directives for the review verdict JSON schema with downstream Python consumers. Axis A additions to the same template must not inadvertently modify these instances.
- **Thinking-word patterns in extended-thinking contexts**: Do NOT apply `think about → consider` or `think through → evaluate` if the skill or reference file explicitly uses extended thinking. Research shows this pattern applies only when extended thinking is NOT enabled. The 9 skills do not enable extended thinking — this is a safeguard if any reference file references it.
- **Stale line numbers**: All line-number references in the ticket body are advisory. Verify preservation items and candidates by content-match grep, not line number. Line numbers may have shifted since #052's research.
- **DV2 partial removal**: Remove only the trailing hedge clause from the criticality suggestion template — do not remove the template structure itself. The template (`> **Criticality suggestion: \`<level>\`** — \`<one-sentence justification>\`.`) must remain intact.

## Changes to Existing Behavior

- **MODIFIED**: `critical-review/SKILL.md` Opus synthesis presentation → compressed (structured bullets, named sections, empty/failed agent sections skipped)
- **MODIFIED**: `critical-review/SKILL.md` synthesis/fallback agent dispatch prompts → add structured output format spec
- **MODIFIED**: `lifecycle/references/implement.md` builder agent dispatch prompts → add reply format spec
- **MODIFIED**: `lifecycle/references/clarify-critic.md` critic dispatch prompt → add labeled output format
- **MODIFIED**: `lifecycle/references/orchestrator-review.md` and `discovery/references/orchestrator-review.md` fix agent prompts → add reply format spec
- **MODIFIED**: Aggressive imperative language (CRITICAL:, ALWAYS, NEVER, YOU MUST) in affected skill files → softened to direct imperative form
- **MODIFIED**: `dev/SKILL.md` criticality pre-assessment section → DV1 hedging clause removed; DV2 trailing hedge removed from template

## Technical Constraints

- **Commit strategy**: Pattern-bucketed commits — one commit per rewrite pattern applied across all affected files (e.g., "Soften CRITICAL: imperatives across skills" as one commit). Roughly 3–5 commits for Axis B plus 1–2 per Axis A location. Per-skill atomic commits are secondary to per-pattern; choosing one commit per skill is acceptable if pattern-bucketed creates confusion.
- **Axis B scope rule**: ALL-CAPS only. Title-case and bold variants are out of scope. Analogues (IMPORTANT:, make sure to, etc.) are a separate category from the core table; track separately.
- **Exclusion category hierarchy**: When multiple exclusion categories apply (e.g., code fence AND output-channel directive), the more restrictive applies. Any one exclusion category is sufficient to protect a pattern.
- **Format spec style**: Use the canonical Anthropic pattern — `"For each [type], provide: [named field list]"` or `"Output format: / ## [Section name]"` — not word/token budgets. Per-skill calibration: critical-review agents need room for evidentiary chains; implement builder agents need compact completion reports.
- **Overnight vs. interactive subagents**: Overnight subagents need compaction-resilient markers (structural headers, field names) per the epic research. Interactive subagents can be more compact. Calibrate accordingly.

## Open Decisions

None. All spec-time-resolvable questions were resolved during the research and interview phases.
