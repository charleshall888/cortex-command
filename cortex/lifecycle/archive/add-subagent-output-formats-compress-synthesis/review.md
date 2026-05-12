# Review: add-subagent-output-formats-compress-synthesis (#053)

## Stage 1: Spec Compliance

### Axis A — Subagent output format specs

**A1 (Must-have) — PASS**
Both the synthesis dispatch prompt (Step 2d, lines 150-181 of `skills/critical-review/SKILL.md`) and the fallback dispatch prompt (Step 2c, lines 113-142) contain a structured `## Output Format` block with named sections: `## Objections`, `## Through-lines`, `## Tensions`, `## Concerns`. Both blocks explicitly prohibit balanced/endorsement sections via the sentence: "Do not include balanced or endorsement sections — no '## What Went Well', no '## Strengths', no '## Recommendation'." The format spec is located in the synthesis/fallback blocks, not in the reviewer block (which retains its existing `## Findings: {angle}` template at lines 92-103). Adversarial stance is preserved — both blocks retain "Do not be balanced. Do not reassure." closing instructions.

**A2 (Must-have) — PASS**
Both synthesis and fallback format specs include: (a) "Use bullets, not prose paragraphs. Each finding is a discrete bullet." (b) "Bullets may be multi-sentence when quoting artifact text as evidence." (c) "Skip sections where the agent returned no findings — do not emit empty section headers." All three required instructions present in both blocks.

**A3 (Must-have) — PASS**
`skills/lifecycle/references/implement.md` builder dispatch block (line 97) contains: "For each task completed, report: task name, status (completed/partial/failed), files modified, verification outcome, issues or deviations from the spec." All five required fields (task name, completion status, files modified, verification outcome, issues/deviations) are present. The reply format spec is inside the Builder Prompt Template code fence block (lines 83-103), distinct from the existing file-output instructions.

**A4 (Should-have) — PASS**
`skills/lifecycle/references/clarify-critic.md` lines 52-58 introduce a labeled `Finding`/`Concern` format inside a code fence: each objection must include both fields. The reinforcement at line 59 ("Each objection must include both the `Finding` and `Concern` fields") closes the loop. This supplements the existing "list of objections" instruction at line 50.

**A5 (Should-have) — PASS**
Both `skills/lifecycle/references/orchestrator-review.md` (line 98) and `skills/discovery/references/orchestrator-review.md` (line 81) contain in their Fix Agent Prompt Template: "Report: what you changed and why. Format: changed [file path] — [one-sentence rationale]." This covers the "what was changed and why, at minimum" requirement.

**A6 (Nice-to-have) — PASS**
`skills/diagnose/SKILL.md` lines 215-223 show the teammate structured output spec followed immediately by a "Format example:" code fence: `Root cause: [assertion] / Evidence: [supporting detail] / Rebuttal: [strongest objection to this hypothesis]`. Format example covers all three required fields and is placed naturally next to the `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`-gated block.

### Axis B — Imperative-intensity rewrite

**B1 (Must-have) — PASS**
Baseline `axis-b-baseline.md` recorded 4 B1 matches across 4 files: `skills/lifecycle/references/clarify-critic.md` (1), `skills/lifecycle/references/review.md` (1), `skills/diagnose/SKILL.md` (1), `skills/overnight/SKILL.md` (1). Post-edit recursive grep confirms:
- `clarify-critic.md`: 1 → 0 (softened "you must cover" → "you should cover" at line 43)
- `overnight/SKILL.md`: 1 → 0 (softened "You must pass" → "You should pass" at line 248)
- `review.md`: 1 → 1 (unchanged — documented rationale: output-channel directive, exclusion category 2, explicitly called out in spec as out of scope)
- `diagnose/SKILL.md`: 1 → 1 (unchanged — documented rationale: P1 preservation anchor #7 `ALWAYS find root cause before attempting fixes`)
Both unchanged files have documented rationale entries in `axis-b-candidates.md`. Post-edit count ≤ pre-edit count for every file.

**B2 (Should-have) — PASS**
Baseline and candidate scans both recorded 0 matches across all 14 in-scope files for pattern `IMPORTANT:|make sure to|be sure to|remember to`. Confirmation pass expected empty — satisfied.

**B3 (Should-have) — PASS**
`grep -c "This is a conversational suggestion" skills/dev/SKILL.md` = 0.

**B4 (Should-have) — PASS**
`grep -c "Lifecycle will run its own full assessment" skills/dev/SKILL.md` = 0. Template structure preserved: `grep -c "Criticality suggestion" skills/dev/SKILL.md` = 1 (line 118: `> **Criticality suggestion: \`<level>\`** — \`<one-sentence justification>\`.`).

### Preservation and scope discipline

**P1 (Must-have) — PASS**
All 14 preservation anchors verified present post-edit:
| # | Anchor | File | Count |
|---|--------|------|-------|
| 1 | `Do not soften or editorialize` | `critical-review/SKILL.md` | 1 |
| 2 | `Do not be balanced` | `critical-review/SKILL.md` | 3 |
| 3 | `Do not reassure` | `critical-review/SKILL.md` | 2 |
| 4 | `No two derived angles` | `critical-review/SKILL.md` | 1 |
| 5 | `⚠️ Agent .* returned no findings` | `research/SKILL.md` | 4 |
| 6 | `note the contradiction explicitly under` | `research/SKILL.md` | 1 |
| 7 | `ALWAYS find root cause before attempting fixes` | `diagnose/SKILL.md` | 1 |
| 8 | `Never fix just where the error appears` | `diagnose/SKILL.md` | 1 |
| 9 | `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | `diagnose/SKILL.md` | 2 |
| 10 | `**Critical rule**` | `lifecycle/references/plan.md` | 1 |
| 11 | `Found epic research at` | `lifecycle/SKILL.md` | 1 |
| 12 | `warn if prerequisite artifacts are missing` | `lifecycle/SKILL.md` | 1 |
| 13 | `AskUserQuestion` | `backlog/SKILL.md` | 4 |
| 14 | `summarize findings, and proceed` | `discovery/SKILL.md` | 1 |

All anchors retain their baseline presence.

**P2 (Must-have) — PASS**
Baseline recorded injection-resistance count of 6 across `skills/research/SKILL.md` before Axis B began. Pre-condition gate satisfied.

**P3 (Must-have) — PASS**
`just test` exits 0 (3/3 tests passed). No downstream consumer contract modifications — edits were limited to prose softening and new format-spec blocks inside dispatch prompt templates; event type names, verdict JSON fields, and backlog schema field names remain untouched.

### Final verification

**V1 — PASS** — `just test` exits 0 (3/3 passed).

**V2 — PASS** — Manual diff review: edits preserve intent — the Output Format blocks in `critical-review/SKILL.md` add structure without removing the existing adversarial closing instructions; the builder reply format in `implement.md` is additive; the clarify-critic Finding/Concern block supplements (does not replace) the existing "list of objections" instruction; Axis B edits (2 in clarify-critic/overnight) are minimal and semantically equivalent (the call-site argument directive in overnight remains intact, the critic coverage instruction remains intact).

**V3 — PARTIAL (unverifiable in read-only review context)** — A live dry-run of `/critical-review` on a short plan would require executing the skill, which is outside the scope of a read-only spec-compliance review. Static inspection of the synthesis prompt block confirms structured sections, bullets instruction, skip-empty-sections instruction, and absence of balanced/endorsement sections — which is the underlying requirement V3 measures. No blocking concern.

**V4 — PASS** — `grep -c "CRITICAL:" skills/lifecycle/references/review.md` = 1 post-edit, matching baseline count of 1.

## Stage 2: Code Quality

**Naming conventions — PASS**
The new Output Format blocks follow the canonical Anthropic `## Output Format` / `## [Section name]` pattern cited in the spec's Technical Constraints. Field names (`Finding`, `Concern`, `Root cause`, `Evidence`, `Rebuttal`) are descriptive and consistent with the existing vocabulary in each file.

**Error handling — PASS**
The format specs do not introduce new control-flow branches or error paths — they augment existing dispatch prompts with structural guidance. The synthesis failure path and partial coverage path in `critical-review/SKILL.md` remain intact (lines 183-191).

**Test coverage — PASS**
`just test` exits 0 (3/3 passed). Automated tests cover skill frontmatter contracts; interactive verification steps (V2 manual diff, V3 dry-run) are appropriately out of scope for the test suite and were handled during the plan's verification phase as documented in the lifecycle events.log.

**Pattern consistency — PASS**
The "For each [type], report/provide: [field list]" pattern used in `implement.md` and the orchestrator-review files matches the canonical format-spec style called out in the spec's Technical Constraints. The per-skill calibration is appropriate: critical-review synthesis (high-evidentiary-depth workflow) gets room for multi-sentence bullets; implement builder (compact completion reports) gets a five-field summary. Format blocks sit naturally next to their existing dispatch-prompt scaffolding.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

The implementation modifies dispatch prompt contents inside skill/reference files only. Multi-agent requirements (agent spawning, worktree isolation, parallel dispatch, model selection) and project requirements (agentic workflow toolkit, autonomous multi-hour development, defense-in-depth for permissions) describe system-level capabilities — the per-dispatch prompt-content refinements introduced by this ticket operate within those capabilities without changing or extending them.

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
