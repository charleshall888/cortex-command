# Plan: critical-review-skill-audit

## Overview

Rewrite `skills/critical-review/SKILL.md` Step 2 to replace the single-agent dispatch with a four-stage process: domain context loading, orchestrator-driven angle derivation, parallel reviewer dispatch (one agent per angle), and an Opus synthesis step. Steps 1, 3, and 4 are unchanged. Then update the description in `docs/skills-reference.md`.

## Tasks

### Task 1: Add Step 2a — Load Domain Context
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Rename Step 2 from "Dispatch a Fresh Reviewer" to "Review Setup and Dispatch", then add a new Step 2a sub-section before the existing dispatch content. Step 2a instructs the orchestrator to: (1) read `requirements/project.md` if it exists and extract the Overview section (up to ~250 words); (2) read `lifecycle.config.md` if it exists and extract the `type:` field value if non-empty; (3) construct a `## Project Context` block from these inputs (omit entirely if neither file exists). Update the frontmatter `description:` field to reflect multi-agent dispatch.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current SKILL.md is at `skills/critical-review/SKILL.md`, 61 lines. Step 2 header is on approximately line 10. The frontmatter `description:` field (line 3) currently reads "Dispatches a fresh, unanchored agent to deeply challenge a plan, spec, or research artifact from multiple angles before you commit. Use when..." — update this to mention parallel agents and Opus synthesis while keeping the trigger phrases intact. The `## Project Context` block omission rule: if neither `requirements/project.md` nor a non-empty `lifecycle.config.md` `type:` field exists, omit the entire section from reviewer prompts — do not inject an empty placeholder. `lifecycle.config.md` type field note: the file may exist but have `type:` commented out or absent — check for a non-empty, non-commented value.
- **Verification**: Read the updated SKILL.md — confirm frontmatter description is updated; Step 2 is now titled "Review Setup and Dispatch" with a "Step 2a: Load Domain Context" sub-section; the sub-section specifies the fallback behavior when context files are absent.

### Task 2: Add Step 2b — Derive Angles
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Add Step 2b immediately after Step 2a. The orchestrator (in main conversation context) derives 3–4 challenge angles from the artifact. Each angle must be distinct (no two angles are re-phrasings of each other) and must reference specific sections or claims in the artifact (not generic category labels). The derivation uses an expanded angle menu.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: The expanded angle menu is the existing examples (architectural risk, unexamined alternatives, fragile assumptions, integration risk, scope creep, real-world failure modes) plus domain-specific additions:
  - For games: performance budget, game loop coupling, save/load state, platform store compliance
  - For mobile: platform API constraints, offline behavior, haptic/accessibility, background execution limits
  - For workflow/tooling: agent isolation, prompt injection, state file corruption, failure propagation
  The orchestrator uses domain context from Step 2a (if available) to weight which examples are most relevant when deriving angles. If no project context is available, the menu is still expanded — domain detection is optional, not required for angle derivation. Minimum 2 angles if the artifact is very short (< 10 lines); target 3–4 otherwise.
- **Verification**: Read SKILL.md — confirm Step 2b exists after Step 2a; the angle menu includes both original and domain-specific examples; acceptance criteria for angle distinctness and artifact-specificity are stated.

### Task 3: Add Step 2c — Parallel Reviewer Dispatch
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Add Step 2c, replacing the current single-agent dispatch block. Dispatch one general-purpose agent per derived angle as parallel Task tool sub-tasks. Include the verbatim reviewer agent prompt template. Include failure handling (partial and total). The current Step 2 prompt content is removed and replaced with the new template.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**: Reviewer prompt template — pass this verbatim (substituting bracketed vars):
  ```
  You are conducting an adversarial review of one specific angle.

  ## Artifact
  {artifact content}

  ## Project Context
  {## Project Context block from Step 2a, omit this entire section if no context was loaded}

  ## Your Angle
  **{angle name}**: {angle description — 1–2 sentences describing what this angle investigates}

  ## Instructions
  1. Read the artifact focusing exclusively on your assigned angle.
  2. Be specific — cite exact artifact text. "This might not scale" is not acceptable.
  3. Return findings in this exact format:

  ## Findings: {angle name}

  ### What's wrong
  [Specific problems, each citing exact artifact text in quotes]

  ### Assumptions at risk
  [Assumptions this angle reveals as fragile]

  ### Convergence signal
  [One line: whether this angle's concerns likely overlap with other possible review angles, and which]

  Do not cover other angles. Do not be balanced.
  ```
  Failure handling: (a) partial failure — some agents succeed — collect successful results, proceed to Step 2d; (b) total failure — all agents fail — fall back to the current single-agent approach: dispatch one general-purpose agent with the original Step 2 prompt verbatim (no parallel dispatch, no synthesis); the fallback note "Note: parallel dispatch failed, falling back to single reviewer" is output as a one-line prefix before Step 3 presentation.
- **Verification**: Read SKILL.md — Step 2c exists after Step 2b; the reviewer prompt template is present verbatim with all four sections (Artifact, Project Context, Your Angle, Instructions + output format); failure handling covers both partial and total failure cases.

### Task 4: Add Step 2d — Opus Synthesis
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Add Step 2d immediately after Step 2c. After all parallel reviewer agents complete (or the successful subset), dispatch one Opus synthesis agent using the verbatim prompt template from the spec. Handle synthesis agent failure (present raw per-angle findings directly if synthesis fails). If partial coverage occurred, always prefix the output with "N of M reviewer angles completed."
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Synthesis agent prompt template — pass this verbatim:
  ```
  You are synthesizing findings from multiple independent adversarial reviewers into a single coherent challenge.

  ## Artifact
  {artifact content}

  ## Reviewer Findings
  {all reviewer findings, one `## Findings: {angle}` block per reviewer}

  ## Instructions
  1. Read all reviewer findings carefully.
  2. Find the through-lines — claims or concerns that appear across multiple angles. Flag these as high-confidence.
  3. Surface tensions where angles conflict or pull in different directions.
  4. Synthesize into a single coherent narrative challenge. Do not produce a per-angle dump.
  5. Be specific — cite exact parts of the artifact.
  6. End with: "These are the strongest objections. Proceed as you see fit."

  Do not be balanced. Do not reassure. Find the through-lines and make the strongest case.
  ```
  Model: `opus`. If partial coverage: prefix the output with "N of M reviewer angles completed" (e.g., "3 of 4 reviewer angles completed") unconditionally, before the synthesis narrative. If synthesis agent fails: present raw per-angle findings from Step 2c directly, skipping synthesis — Step 4 (Apply Feedback) then operates on the raw findings. Also update Step 3's current language from "Output the reviewer's synthesis directly" to "Output the review result directly" — this wording change is required because three code paths (normal synthesis, synthesis failure with raw findings, total-dispatch-failure with single-agent review) all terminate at Step 3 with different content shapes. "Do not soften or editorialize" stays unchanged. Step 4 (Apply Feedback) is unchanged.
- **Verification**: Read SKILL.md — Step 2d exists after Step 2c; synthesis prompt template is present verbatim; model is specified as `opus`; partial coverage note is unconditional; synthesis failure case (present raw findings) is documented; Step 3 wording says "output the review result directly" (not "the reviewer's synthesis"); Step 4 is unmodified.

### Task 5: Update docs/skills-reference.md
- **Files**: `docs/skills-reference.md`
- **What**: Update the `### critical-review` entry description to reflect multi-agent parallel dispatch and Opus synthesis. The existing description says "Dispatches a fresh, unanchored agent" — update to describe the parallel reviewer + synthesis approach while keeping the description concise (2–3 sentences).
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: Current entry is at `docs/skills-reference.md` lines 105–108. The link to `skills/critical-review/SKILL.md` should remain. The updated description should convey: (1) derives 3-4 challenge angles from artifact + project context, (2) dispatches one reviewer agent per angle in parallel, (3) Opus synthesis agent produces final coherent challenge. Trigger phrases are defined in SKILL.md frontmatter, not here — the docs entry is for human orientation, not skill triggering.
- **Verification**: Read `docs/skills-reference.md` lines 103–110 — description no longer says "a fresh, unanchored agent" (single-agent); description accurately reflects multi-agent parallel + synthesis behavior.

## Verification Strategy

After all tasks complete:
1. Read `skills/critical-review/SKILL.md` in full — confirm the step flow is: Step 1 (find artifact, unchanged) → Step 2a (load domain context) → Step 2b (derive angles) → Step 2c (dispatch parallel reviewers) → Step 2d (Opus synthesis) → Step 3 (present, unchanged) → Step 4 (apply feedback, unchanged).
2. Manually trace through the skill with a hypothetical mobile game spec: confirm the angle derivation step would use mobile-specific angle examples, the `## Project Context` section would be present in reviewer prompts (if requirements/project.md exists), and the synthesis agent would receive structured findings.
3. Confirm fallback paths are reachable: partial failure → synthesis receives N < M findings and notes coverage; total failure → single-agent path fires; synthesis failure → raw findings presented.
4. Read `docs/skills-reference.md` — confirm the critical-review entry description is updated.
