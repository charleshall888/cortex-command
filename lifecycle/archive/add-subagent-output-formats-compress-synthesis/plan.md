# Plan: add-subagent-output-formats-compress-synthesis

## Overview

Two-axis targeted edit across 9 SKILL.md files and in-scope reference files: Axis A adds structured output format specs to 5 subagent dispatch locations with confirmed gaps; Axis B softens ALL-CAPS imperative patterns (2–4 actual instances outside exclusion categories, most of the corpus already softened). Executed sequentially — Axis A first, then Axis B — with a full baseline safety scan before any edits, pattern-bucketed commits for Axis B, and explicit preservation-anchor verification post-edit.

## Tasks

### Task 1: Baseline safety scans
- **Files**: `lifecycle/archive/add-subagent-output-formats-compress-synthesis/axis-b-baseline.md` (created by this task)
- **What**: Record all pre-edit safety baselines before any file is touched. Covers P2 injection-resistance count, all 14 P1 preservation anchors, V4 pre-edit CRITICAL count in review.md, and B1/B2 pattern counts per file. Write all counts to a persistent file so Tasks 8 and 10 can read them from a known location.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - P2 injection-resistance: `grep -rc "All web content.*untrusted external data" skills/` — record count (must be ≥ 1)
  - V4 pre-edit: `grep -c "CRITICAL:" skills/lifecycle/references/review.md` — record exact count
  - P1 anchors (14 items from spec §P1 — grep each by content, not line number):
    - `Do not soften or editorialize` → `skills/critical-review/SKILL.md`
    - `Do not be balanced` → `skills/critical-review/SKILL.md`
    - `Do not reassure` → `skills/critical-review/SKILL.md`
    - `No two derived angles` or `Each angle must be distinct` → `skills/critical-review/SKILL.md`
    - `⚠️ Agent` (for "returned no findings" string) → `skills/research/SKILL.md`
    - `note the contradiction explicitly under` → `skills/research/SKILL.md`
    - `ALWAYS find root cause before attempting fixes` → `skills/diagnose/SKILL.md`
    - `Never fix just where the error appears` → `skills/diagnose/SKILL.md`
    - `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` → `skills/diagnose/SKILL.md`
    - `**Critical rule**` → `skills/lifecycle/references/plan.md`
    - `Found epic research at` → `skills/lifecycle/SKILL.md`
    - `warn if prerequisite artifacts are missing` → `skills/lifecycle/SKILL.md`
    - `AskUserQuestion` → `skills/backlog/SKILL.md`
    - `summarize findings, and proceed` → `skills/discovery/SKILL.md`
  - B1 baseline: `grep -rc "CRITICAL:\|[Yy]ou [Mm]ust\|ALWAYS \|NEVER \|REQUIRED to\|think about\|think through" skills/` — per-file counts
  - B2 baseline: `grep -rc "IMPORTANT:\|make sure to\|be sure to\|remember to" skills/` — per-file counts
  - Write all counts to `lifecycle/archive/add-subagent-output-formats-compress-synthesis/axis-b-baseline.md` in this format:
    ```
    ## Baseline Counts
    - V4 CRITICAL count (skills/lifecycle/references/review.md): N
    - B1 per-file counts: {file}: N, {file}: N, ...
    - B2 per-file counts: {file}: N, ...
    ```
  - This file is the permanent record — Tasks 8 and 10 read from it
- **Verification**:
  - `ls lifecycle/archive/add-subagent-output-formats-compress-synthesis/axis-b-baseline.md` — file exists
  - Interactive/session-dependent: confirm all 14 P1 anchors returned ≥ 1 match each before proceeding to edit tasks.
- **Status**: [x] complete

### Task 2: Axis A — critical-review synthesis format and compression (A1 + A2)
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Add a structured output format spec to the Opus synthesis agent dispatch prompt (Step 2d) and the fallback single-agent dispatch prompt (Step 2c). Compress the synthesis presentation from narrative to structured bullets: add "bullets not prose" and "skip empty/failed agent sections" instructions. The reviewer agent blocks (which already have format specs) are not modified.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - Synthesis block target (Step 2d): the instruction currently reads "synthesize all reviewer findings into a single coherent narrative challenge" — this is the prose-only block to modify
  - Fallback block anchor (Step 2c): the instruction currently reads "Synthesize into one coherent challenge — not a per-angle dump" — this is the equivalent prose in the fallback block; it requires the same format spec addition
  - Both blocks are distinct dispatch prompts in the same file; both must receive the format spec — do not address only one
  - Format spec to add: named sections covering objections, through-lines, tensions, and concerns. Explicitly prohibit balanced or endorsement sections (no "## What Went Well", "## Strengths", "## Recommendation")
  - Canonical format pattern: `"## Objections / ## Through-lines / ## Tensions / ## Concerns"` or `"For each finding, provide: / - Objection / - Evidence / - Through-line (if any)"`
  - Compression instructions to add: "Use bullets, not prose paragraphs. Each finding is a discrete bullet. Bullets may be multi-sentence when quoting artifact text as evidence. Skip sections where the agent returned no findings — do not emit empty section headers."
  - Preservation anchors in this file (verify by grep after edit; do NOT touch these lines):
    - `Do not soften or editorialize` (~line 173)
    - `Do not be balanced` (~line 103)
    - `Do not reassure` (~line 129)
    - `No two derived angles` or `Each angle must be distinct` (~lines 26, 65-66)
  - Commit after edits: message "Add structured output format spec and bullet compression to critical-review synthesis"
- **Verification**:
  - `grep -c "Do not soften or editorialize" skills/critical-review/SKILL.md` ≥ 1
  - `grep -c "Do not be balanced" skills/critical-review/SKILL.md` ≥ 1
  - `grep -c "Do not reassure" skills/critical-review/SKILL.md` ≥ 1
  - `grep -c "Skip sections where the agent returned no findings" skills/critical-review/SKILL.md` ≥ 1 (compression instruction present)
  - Interactive/session-dependent: before committing, review `git diff HEAD -- skills/critical-review/SKILL.md` and confirm changes are limited to format spec additions in the synthesis (Step 2d) and fallback (Step 2c) blocks only — no reviewer block content removed, no preservation anchors modified.
- **Status**: [x] complete

### Task 3: Axis A — lifecycle implement builder reply format (A3)
- **Files**: `skills/lifecycle/references/implement.md`
- **What**: Add a conversational reply format spec to the builder agent dispatch block specifying what the agent should report back after completing a task. The existing file-output instructions remain unchanged; this adds the reply format alongside them.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Current builder dispatch reply instruction: "Report what you did and any issues encountered" — expand to named fields
  - Format spec to add: "For each task completed, report: task name, status (completed/partial/failed), files modified, verification outcome, issues or deviations from the spec."
  - Location: inside the builder agent dispatch block — the block that sends per-task instructions to individual builder agents. Do not add to the orchestrator loop instructions or the outer lifecycle shell.
  - Also check: `Always use /commit for all commits` at ~line 155 — this is title-case `Always`, out of scope for Axis B (ALL-CAPS only). Do not modify it here.
  - Commit after edits: message "Add reply format spec to lifecycle implement builder dispatch"
- **Verification**:
  - `grep -c "For each\|Report.*:" skills/lifecycle/references/implement.md` ≥ 1
  - Interactive/session-dependent: before committing, review `git diff HEAD -- skills/lifecycle/references/implement.md` and confirm changes are limited to the reply format spec addition in the builder dispatch block; confirm the grep hit covers all five named fields (task name, status, files modified, verification outcome, issues or deviations).
- **Status**: [x] complete

### Task 4: Axis A — clarify-critic labeled output format (A4)
- **Files**: `skills/lifecycle/references/clarify-critic.md`
- **What**: Add at least one labeled section header or named-field list to the clarify-critic agent's return format. The existing "Return a list of objections only — one per finding, written as prose" instruction is supplemented, not replaced.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Current critic return spec: "Return a list of objections only — one per finding, written as prose" — no field-level structure
  - Add named fields: e.g., "For each objection: / - Finding: [what the spec claims or assumes] / - Concern: [why this is questionable]" — or equivalent labeled structure that makes each objection parseable by the orchestrator
  - The critic produces a list-of-objections; the format spec should make each item structurally consistent
  - Commit after edits: message "Add labeled output format to clarify-critic dispatch"
- **Verification**:
  - Interactive/session-dependent: before committing, review `git diff HEAD -- skills/lifecycle/references/clarify-critic.md` and confirm the diff adds labeled structure to the critic dispatch prompt alongside the existing objections instruction, with no existing instructions removed.
- **Status**: [x] complete

### Task 5: Axis A — orchestrator-review fix agent reply format (A5)
- **Files**: `skills/lifecycle/references/orchestrator-review.md`, `skills/discovery/references/orchestrator-review.md`
- **What**: Add a reply format spec to the fix agent dispatch blocks in both files. The existing file-rewrite instruction is primary; this adds the conversational acknowledgment format (what was changed and why) as a secondary requirement.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Current fix agent dispatch: file rewrite instruction only — no reply format specified
  - Format spec to add: "Report: what you changed and why. Format: changed [file path] — [one-sentence rationale]."
  - Apply the same addition to both files — they have the same structural gap
  - These files have no downstream consumer contracts on the conversational reply (the primary output is the file rewrite)
  - Commit after edits: message "Add reply format spec to orchestrator-review fix agent dispatch"
- **Verification**:
  - Interactive/session-dependent: before committing, review `git diff HEAD -- skills/lifecycle/references/orchestrator-review.md skills/discovery/references/orchestrator-review.md` and confirm each fix agent prompt has a reply format spec, with no existing rewrite instructions removed.
- **Status**: [x] complete

### Task 6: Axis A — diagnose competing-hypotheses format example (A6, optional)
- **Files**: `skills/diagnose/SKILL.md`
- **What**: Add a concrete format example for the three-field competing-hypotheses teammate output (root cause assertion, supporting evidence, rebuttal) near the point where the three-field output is described. Only apply if the edit fits naturally — if the section is already cluttered or the example would disrupt the flow, skip and document reasoning in task output.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Location: the section describing competing-hypotheses agent teams, gated by `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`
  - Format example to add: inline block showing `Root cause: [assertion] / Evidence: [supporting detail] / Rebuttal: [strongest objection to this hypothesis]`
  - Preservation anchors in this file — do NOT touch these (they are also Axis B exclusions):
    - `ALWAYS find root cause before attempting fixes` (~line 16) — preservation item, not a softening candidate
    - `Never fix just where the error appears` (~line 397) — preservation item, same protective family
    - `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` — must remain present
  - If the format example fits naturally: commit with message "Add format example to diagnose competing-hypotheses output spec"
  - If skipping: document clearly in task output why the edit was skipped
- **Verification**:
  - Interactive/session-dependent: if a change was made, review `git diff HEAD -- skills/diagnose/SKILL.md` and confirm the diff adds only the format example near the teammate output spec with no preservation anchors removed; OR task output documents the skip rationale.
- **Status**: [x] complete

### Task 7: Axis B — candidate enumeration scan (B1 + B2)
- **Files**: `lifecycle/archive/add-subagent-output-formats-compress-synthesis/axis-b-candidates.md` (created by this task)
- **What**: Scan all in-scope files for B1 core-table patterns and B2 analogue patterns. Apply exclusion categories to each match and produce a confirmed candidate list — exact file paths, line numbers, pattern matched, and exclusion-category decision. Write the list to a persistent file so Task 8 can read it from a known location. This is the discovery pass only; no skill file edits are made here.
- **Depends on**: [2, 3, 4, 5, 6]
- **Complexity**: simple
- **Context**:
  - In-scope files to scan: `skills/critical-review/SKILL.md`, `skills/diagnose/SKILL.md`, `skills/discovery/SKILL.md`, `skills/lifecycle/SKILL.md`, `skills/overnight/SKILL.md`, `skills/research/SKILL.md`, `skills/backlog/SKILL.md`, `skills/pr-review/SKILL.md`, `skills/lifecycle/references/implement.md`, `skills/lifecycle/references/clarify-critic.md`, `skills/lifecycle/references/orchestrator-review.md`, `skills/lifecycle/references/plan.md`, `skills/lifecycle/references/review.md`, `skills/discovery/references/orchestrator-review.md`
  - B1 grep pattern: `CRITICAL:\|[Yy]ou [Mm]ust\|ALWAYS \|NEVER \|REQUIRED to\|think about\|think through`
  - B2 grep pattern: `IMPORTANT:\|make sure to\|be sure to\|remember to`
  - Exclusion categories — a match in ANY category is excluded from the candidate list:
    1. Inside code fence (``` ``` or indented code block)
    2. Output-channel directive: controls downstream JSON schema, event format, or review verdict (e.g., `skills/lifecycle/references/review.md` CRITICAL/MUST instances — explicitly excluded per spec)
    3. Control-flow gate: gates entry into a named phase or step (e.g., `DO NOT attempt Fix #4 without completing team investigation protocol`)
    4. Preservation list item (all 14 P1 anchors — untouchable regardless of pattern)
    5. Mixed-case / bold / title-case variant: `Always`, `**Never**`, `**Critical rule**` — ALL-CAPS only, these are out of scope
    6. Single-word ALL-CAPS procedural marker: BEFORE, THEN, STOP, ANY — out of scope (not multi-word imperatives)
  - Note: `skills/dev/SKILL.md` is not in this scan — its Axis B work (DV1, DV2) is in Task 9
  - Write the confirmed-candidate list to `lifecycle/archive/add-subagent-output-formats-compress-synthesis/axis-b-candidates.md` with per-file, per-pattern documentation of each match and exclusion-category decision. Task 8 reads this file.
  - Expected output: most files show zero qualifying candidates; document every match even if excluded
- **Verification**:
  - `ls lifecycle/archive/add-subagent-output-formats-compress-synthesis/axis-b-candidates.md` — file exists
  - Interactive/session-dependent: candidate list produced; each match classified as qualifying candidate or excluded (with category noted).
- **Status**: [x] complete

### Task 8: Axis B — apply confirmed-candidate rewrites (B1 + B2)
- **Files**: Files with confirmed candidates from `axis-b-candidates.md` (expected ≤5 based on research findings of 2–4 total instances)
- **What**: Read the confirmed-candidate list from `lifecycle/archive/add-subagent-output-formats-compress-synthesis/axis-b-candidates.md`. Apply B1 core-table rewrites and B2 analogue confirmation passes to the confirmed candidate files only. Use pattern-bucketed commits (one commit per pattern that has ≥ 1 real instance). For patterns with zero qualifying instances, log as "confirmed zero" and skip the commit. Record post-edit grep counts per file.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**:
  - Read `lifecycle/archive/add-subagent-output-formats-compress-synthesis/axis-b-candidates.md` to determine which files and lines need edits
  - Read `lifecycle/archive/add-subagent-output-formats-compress-synthesis/axis-b-baseline.md` (from Task 1) to retrieve pre-edit per-file counts for post-edit comparison
  - B1 core rewrite table:
    - `CRITICAL: X` → `X` (bare statement)
    - `ALWAYS [verb]` → `[verb]` (direct imperative)
    - `NEVER [verb]` → `Don't [verb]`
    - `You MUST` / `you must` / `You must` → `You should`
    - `REQUIRED to` → `should`
    - `think about` → `consider`
    - `think through` → `evaluate`
  - B2 analogues (expected count ≈ 0): `IMPORTANT:`, `make sure to`, `be sure to`, `remember to`
  - Per-pattern commit strategy: one commit per pattern applied across all files. Example message: "Soften NEVER → Don't across skills"
- **Verification**:
  - `grep -rc "CRITICAL:\|[Yy]ou [Mm]ust\|ALWAYS \|NEVER \|REQUIRED to\|think about\|think through" skills/` — post-edit per-file counts ≤ baseline counts from `axis-b-baseline.md`
  - For any file where count is unchanged: task output documents "pattern not present outside exclusion categories in this file"
  - Interactive/session-dependent: before each pattern-bucketed commit, review `git diff HEAD` and confirm the diff touches only the qualifying candidate lines identified in `axis-b-candidates.md`, with no preservation-list content removed.
- **Status**: [x] complete

### Task 9: Axis B — dev/SKILL.md hedge clause removals (B3 + B4)
- **Files**: `skills/dev/SKILL.md`
- **What**: Two surgical removals. DV1: remove the hedging sentence ending from the Step 2 criticality pre-assessment prose. DV2: remove only the trailing hedge clause from within the criticality suggestion template while preserving the template structure.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - DV1: locate by content "This is a conversational suggestion — lifecycle runs its own full assessment in Step 3." — remove this sentence (or the trailing clause that makes it hedging). Search by content, not line number (~line 87 but may have drifted).
  - DV2: locate by content "Lifecycle will run its own full assessment; this is just a starting point." — remove only this trailing clause from within the template body. Template structure to preserve: `> **Criticality suggestion: \`<level>\`** — \`<one-sentence justification>\`.`
  - dev/SKILL.md has no Axis A work and no Axis B candidates other than DV1/DV2 — these are the complete scope for this file
  - Commit after edits: message "Remove hedge clauses from dev/SKILL.md criticality pre-assessment"
- **Verification**:
  - `grep -c "This is a conversational suggestion" skills/dev/SKILL.md` = 0
  - `grep -c "Lifecycle will run its own full assessment" skills/dev/SKILL.md` = 0
  - `grep -c "Criticality suggestion" skills/dev/SKILL.md` ≥ 1 (template structure preserved)
  - Interactive/session-dependent: before committing, review `git diff HEAD -- skills/dev/SKILL.md` and confirm the diff removes only the two targeted hedge clauses with no other content changed.
- **Status**: [x] complete

### Task 10: Post-edit verification (P1, B counts, V1, V4)
- **Files**: (read-only — no edits)
- **What**: Run all automated post-edit verification checks after all edits are complete. Covers P1 preservation anchors, B1/B2 post-edit count comparison vs. Task 1 baseline, just test (V1), and V4 review.md CRITICAL count vs. pre-edit baseline.
- **Depends on**: [8, 9]
- **Complexity**: simple
- **Context**:
  - P1: grep each of the 14 preservation anchors in their target files — each must return ≥ 1 match (same grep commands as Task 1)
  - B1/B2: read pre-edit baseline from `lifecycle/archive/add-subagent-output-formats-compress-synthesis/axis-b-baseline.md`; compare post-edit per-file grep counts — post-edit count must be ≤ pre-edit count per file
  - V1: `just test` — must exit 0
  - V4: read pre-edit CRITICAL count from `axis-b-baseline.md`; run `grep -c "CRITICAL:" skills/lifecycle/references/review.md` — must equal the pre-edit count
  - **If any check fails**: stop immediately. Report the specific failing check. Run `git log --oneline -5 -- <affected-file>` to show recent commits touching that file. Do not attempt remediation — this requires human review before proceeding.
  - V2 (manual diff review) is interactive and happened throughout Tasks 2-9 via per-task pre-commit diff review
- **Verification**:
  - All 14 P1 grep commands return ≥ 1 match in their target files
  - `just test` exits 0
  - `grep -c "CRITICAL:" skills/lifecycle/references/review.md` equals pre-edit count from `axis-b-baseline.md`
- **Status**: [x] complete

### Task 11: Critical-review dry-run spot check (V3)
- **Files**: (read-only — no edits)
- **What**: Invoke critical-review on a short existing plan artifact to confirm the synthesis format change (Task 2) produces structured output with adversarial stance intact. A minimal invocation (one short plan, one review pass) is sufficient.
- **Depends on**: [10]
- **Complexity**: simple
- **Context**:
  - Use a short existing plan artifact (e.g., a recent lifecycle plan.md from any completed lifecycle) — do not fabricate a synthetic test artifact
  - Success criteria: output contains labeled sections or named fields (not a single prose paragraph); no balanced or endorsement sections appear (no "## What Went Well", "## Strengths", no softened/encouraging framing)
  - This is an interactive test — must be run in a live session, not overnight
- **Verification**: Interactive/session-dependent: synthesis output contains labeled sections or named fields, adversarial stance is present, and no balanced or endorsement sections appear.
- **Status**: [x] complete

## Verification Strategy

End-to-end after all tasks complete:
1. **P1** — all 14 preservation anchors present by content-match grep (Task 10)
2. **B1/B2** — per-file post-edit pattern counts ≤ pre-edit baseline from `axis-b-baseline.md` (Task 10)
3. **V1** — `just test` exits 0 (Task 10)
4. **V4** — `skills/lifecycle/references/review.md` CRITICAL count equals pre-edit count from `axis-b-baseline.md` (Task 10)
5. **V3** — critical-review synthesis produces structured bullets, adversarial stance intact, no endorsement sections (Task 11)
6. **V2** — per-task diff review before each commit confirmed intent preserved and no unintended rewrites (Tasks 2–9 verification steps)
