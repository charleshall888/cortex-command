# Review: critical-review-skill-audit

## Stage 1: Spec Compliance

### Requirement 1: Angle derivation before dispatch
- **Expected**: Orchestrator derives 3-4 challenge angles in the main conversation context before dispatching any reviewer agent. Derivation prompt includes artifact content, domain context from `requirements/project.md` (if available), and an expanded angle menu with domain-specific failure mode examples (games, mobile, workflow/tooling). Angles must be distinct, reference specific artifact sections/claims.
- **Actual**: Step 2b ("Derive Angles") runs after Step 2a (domain context loading) and before Step 2c (dispatch). The angle menu (lines 29-56) includes all six general examples and all domain-specific examples for games (4), mobile (4), and workflow/tooling (4) as specified. Angle count rules (lines 59-62) correctly set minimum 2 for short artifacts, target 3-4 otherwise. Acceptance criteria (lines 64-66) require distinctness and artifact-specificity with concrete examples of what qualifies.
- **Verdict**: PASS

### Requirement 2: Parallel reviewer dispatch
- **Expected**: One general-purpose agent per angle dispatched as parallel Task tool sub-tasks. Each agent receives: full artifact content, its assigned angle, project context summary, instructions for exclusive angle focus with structured findings. Agents dispatched concurrently in a single message.
- **Actual**: Step 2c (lines 69-70) specifies "dispatch one general-purpose agent as a parallel Task tool sub-task" per angle, with "All agents run simultaneously -- do not wait for one to finish before launching the next." The prompt template (lines 73-104) includes all four required elements: artifact content (`## Artifact`), project context (`## Project Context`, conditionally omitted), assigned angle (`## Your Angle` with name and description), and focused instructions with structured output format. Uses Task tool as required by technical constraints.
- **Verdict**: PASS

### Requirement 3: Structured reviewer output format
- **Expected**: Each reviewer returns findings as `## Findings: {angle name}` with subsections `### What's wrong`, `### Assumptions at risk`, and `### Convergence signal`. Must cite exact artifact text.
- **Actual**: The reviewer prompt template (lines 92-101) specifies exactly this structure verbatim. The instructions (line 89) explicitly state: "Be specific -- cite exact artifact text. 'This might not scale' is not acceptable." The format is embedded in the prompt so agents are instructed to follow it.
- **Verdict**: PASS

### Requirement 4: Domain context injection
- **Expected**: Read `requirements/project.md` Overview section (up to ~250 words) in main orchestrator context. If `lifecycle.config.md` has a non-empty `type:` field, include as prefix. Pass as `## Project Context` block. Omit entirely when files don't exist.
- **Actual**: Step 2a (lines 18-23) covers all cases: reads `requirements/project.md` and extracts Overview (or first top-level summary, up to ~250 words); reads `lifecycle.config.md` for `type:` field with explicit handling for absent, empty, or commented-out values; constructs `## Project Context` block; omits section entirely when no context is available. The reviewer prompt template (lines 81-82) includes the conditional `## Project Context` section with the instruction to "omit this entire section if no context was loaded." Edge case for commented-out `type:` field (line 21, "the line is not prefixed with `#`") correctly handles the spec's edge case.
- **Verdict**: PASS

### Requirement 5: Opus synthesis agent
- **Expected**: After all parallel agents complete, dispatch one Opus synthesis agent with a specific verbatim prompt. Output must be a synthesized narrative (not per-angle dump) ending with "These are the strongest objections. Proceed as you see fit."
- **Actual**: Step 2d (lines 135-169) dispatches an `opus` model agent after all parallel reviewers complete. The synthesis prompt (lines 140-158) matches the spec's required verbatim prompt character-for-character: same intro line, same section headers (`## Artifact`, `## Reviewer Findings`, `## Instructions`), same six numbered instructions, same closing line "Do not be balanced. Do not reassure. Find the through-lines and make the strongest case." Step 2d is correctly skipped when total-failure fallback is used (line 169).
- **Verdict**: PASS

### Requirement 6: Failure handling
- **Expected**: Partial failure: collect successful results, unconditionally note "N of M reviewer angles completed", pass to synthesis. Total failure: fall back to single-agent with existing Step 2 prompt, prefix with "Note: parallel dispatch failed, falling back to single reviewer" as one-line prefix to Step 3 (not a new step).
- **Actual**: Step 2c failure handling (lines 107-133) covers both cases. Partial failure (lines 109): "Unconditionally note 'N of M reviewer angles completed' at the top of the synthesis output." Total failure (lines 111-133): falls back to single agent with the original prompt structure (derive angles, work through each, synthesize, end with closing line). Fallback note (line 133): "Prefix the output with this one-line note: 'Note: parallel dispatch failed, falling back to single reviewer' before proceeding to Step 3" -- correctly implemented as a prefix, not a new step. Synthesis failure (lines 166-168): skips synthesis, presents raw findings, Step 3 and Step 4 operate on raw findings. Step 2d partial coverage prefix (lines 161-163) reiterates the unconditional "N of M" note.
- **Verdict**: PASS

### Non-requirements verification
- **Step 1 unchanged**: Step 1 (lines 12-13) is identical to the original commit -- artifact discovery logic is untouched. PASS.
- **Step 3 unchanged**: Step 3 (lines 172-173) has a minor wording change from "reviewer's synthesis" to "review result" to accommodate the multi-agent output paths (synthesis, raw findings, or fallback). This is a necessary accommodation, not a behavioral change. PASS.
- **Step 4 unchanged**: Step 4 (lines 177-193) is character-identical to the original commit. PASS.
- **No new config files**: No new settings fields or config files introduced. PASS.
- **Callsites unchanged**: No callsite modifications in the diff. PASS.

## Requirements Compliance

- **Graceful partial failure**: The implementation provides three layers of degradation (partial reviewer failure -> synthesis with note; total reviewer failure -> single-agent fallback; synthesis failure -> raw findings). This aligns with the project requirement that "individual tasks in an autonomous plan may fail" while the system continues.
- **Maintainability through simplicity**: The skill adds structural complexity (4 sub-steps within Step 2) but each sub-step has a clear, singular responsibility. The prompt templates are verbatim blocks rather than procedural logic, which aids readability. The fallback path reuses the original single-agent prompt rather than introducing a separate fallback mechanism. Reasonable for the scope of the change.
- **Complexity must earn its place**: The spec's problem statement establishes a concrete observed problem (single-agent reviews miss domain-specific failure modes, sequential coverage limits depth). The multi-agent approach directly addresses these. The implementation does not introduce speculative features beyond what the spec requires.
- **File-based state**: No new state files introduced. Domain context is read from existing `requirements/project.md` and `lifecycle.config.md`. Consistent with the architectural constraint.
- **Symlink architecture**: The skill lives in `skills/critical-review/SKILL.md` (the repo copy). No files created at destination paths. Consistent.

## Stage 2: Code Quality

- **Naming conventions**: Step numbering follows the existing project pattern (Step 1, Step 2, Step 3, Step 4) with sub-steps using letter suffixes (2a, 2b, 2c, 2d) -- consistent with how other complex skills like `/lifecycle` and `/research` organize multi-phase steps. Frontmatter uses `name` and `description` fields matching the established pattern in `/devils-advocate` and `/diagnose`. The `skills-reference.md` entry follows the same format as all other entries (heading, description paragraph, link).

- **Error handling**: The three-tier failure handling (partial, total, synthesis failure) is well-structured. Each failure mode has a clear detection condition and recovery path. The total-failure fallback preserves existing behavior rather than introducing a novel recovery mechanism. The synthesis failure path (present raw findings) is the most reasonable degradation since the structured per-angle format is already designed for readability. Compared to `/diagnose` (which has multi-phase escalation) and `/devils-advocate` (which has an error handling table), the approach here is proportionate -- failure paths are described inline at the point where failures can occur rather than in a separate section, which is appropriate since the failure modes are step-specific.

- **Pattern consistency**: The skill follows the same structural conventions as peer skills. Like `/devils-advocate`, it has a clear step progression (find artifact -> process -> present -> apply). Like `/diagnose`, it uses sub-steps for complex phases. Prompt templates use the `---` fence convention seen in the original skill. The frontmatter description length is similar to other complex skills. The `## Project Context` conditional injection pattern is clean -- omit when absent rather than inject empty blocks. The "verbatim" prompt specification (for both reviewer and synthesis agents) ensures consistent agent behavior, matching how `/research` specifies its agent prompts.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": []}
```
