# Specification: critical-review-skill-audit

## Problem Statement

The `/critical-review` skill currently dispatches a single general-purpose agent and instructs it to derive 3–4 challenge angles from the artifact, work through each, and synthesize. In practice, the angle derivation is only as good as the artifact's vocabulary — if the artifact doesn't surface domain-specific concerns (frame budget, haptic latency, platform compatibility, etc.), the reviewer won't raise them. A single agent also covers all angles sequentially in one pass, which limits depth per angle. The result is reviews that work well for agentic workflow specs (the artifact language matches the reviewer's defaults) but miss the most important failure modes for other project types. The fix: derive angles up front, dispatch one agent per angle in parallel for deeper focus, inject project domain context so agents can bring domain knowledge to sparse artifacts, and run a synthesis agent on the combined findings.

## Requirements

1. **Angle derivation before dispatch** (Must-have — without this the parallel dispatch produces no coherent per-angle focus; it is the input to everything else): Before dispatching any reviewer agent, the orchestrator derives 3–4 challenge angles from the artifact in the main conversation context. The derivation prompt must include: (a) the artifact content, (b) domain context from `requirements/project.md` (if available), and (c) an expanded angle menu that lists domain-specific failure mode examples alongside the existing examples (architectural risk, fragile assumptions, scope creep, integration risk, real-world failure modes). Domain-specific examples include: for games — performance budget, game loop coupling, save/load state, platform store compliance; for mobile — platform API constraints, offline behavior, haptic/accessibility, background execution limits; for workflow/tooling — agent isolation, prompt injection, state file corruption, failure propagation.
   - Acceptance criteria: angle derivation runs before any reviewer agent is dispatched; angles are distinct (no two angles are re-phrasings of each other); angles reference specific sections or claims in the artifact (not generic categories).

2. **Parallel reviewer dispatch** (Must-have — this is the core structural change the feature exists to deliver; without it the skill remains a single sequential pass): The orchestrator dispatches one general-purpose agent per derived angle as parallel Task tool sub-tasks. Each agent receives: (a) the full artifact content, (b) its single assigned angle, (c) the project context summary, (d) instructions to focus exclusively on its angle and return structured findings.
   - Acceptance criteria: agents are dispatched concurrently in a single message; each agent's prompt includes its assigned angle name and a description; orchestrator waits for all agents before proceeding to synthesis.

3. **Structured reviewer output format** (Must-have — the synthesis agent cannot parse and combine unstructured free-text from parallel agents; the fixed format is the contract between reviewers and synthesis): Each reviewer agent returns findings in a fixed structure: `## Findings: {angle name}` with subsections `### What's wrong` (specific problems cited from the artifact with quotes), `### Assumptions at risk` (assumptions this angle reveals as fragile), and `### Convergence signal` (a one-line note on whether this angle's concerns overlap with other likely angles — the orchestrator uses this to identify through-lines). Agents must cite exact artifact text — "this might not scale" is not acceptable.
   - Acceptance criteria: orchestrator can extract per-angle findings; at least one concrete artifact quote per finding.

4. **Domain context injection** (Must-have — without domain context the improvement is only structural; reviewers will miss domain-specific failure modes for non-workflow artifacts, which is the stated motivation for this feature): Before dispatching reviewer agents (as a pre-dispatch step within Step 2), the orchestrator reads `requirements/project.md` if it exists at the project root. If found, pass the Overview section verbatim (or the first top-level summary section if no section is explicitly labeled "Overview", up to ~250 words) as a `## Project Context` block in each reviewer agent's prompt. If `lifecycle.config.md` exists at the project root and contains a non-empty `type:` field, include the type value as a one-line prefix before the project context text.
   - Acceptance criteria: reviewer agents receive a `## Project Context` section when `requirements/project.md` exists, containing substantive project context (not a sentence summary); the section is omitted (not an empty placeholder) when the file does not exist; skill works correctly in both cases.

5. **Opus synthesis agent** (Must-have — user explicitly chose synthesis agent over orchestrator merging; without it parallel findings are dumped as-is, which does not produce a coherent review): After all parallel reviewer agents complete (or the successful subset, per failure handling), dispatch one Opus synthesis agent. The synthesis agent receives: (a) the full artifact content, (b) all reviewer findings in their structured format. Pass the synthesis agent this prompt verbatim:

   > You are synthesizing findings from multiple independent adversarial reviewers into a single coherent challenge.
   >
   > ## Artifact
   > {artifact content}
   >
   > ## Reviewer Findings
   > {all reviewer findings, one `## Findings: {angle}` block per reviewer}
   >
   > ## Instructions
   > 1. Read all reviewer findings carefully.
   > 2. Find the through-lines — claims or concerns that appear across multiple angles. Flag these as high-confidence.
   > 3. Surface tensions where angles conflict or pull in different directions.
   > 4. Synthesize into a single coherent narrative challenge. Do not produce a per-angle dump.
   > 5. Be specific — cite exact parts of the artifact.
   > 6. End with: "These are the strongest objections. Proceed as you see fit."
   >
   > Do not be balanced. Do not reassure. Find the through-lines and make the strongest case.

   - Acceptance criteria: synthesis agent is dispatched after all parallel agents complete; synthesis agent model is `opus`; output is a synthesized narrative (not a list of per-angle sections); ends with the required closing line.

6. **Failure handling** (Must-have — total-failure fallback preserves existing behavior and ensures the skill always returns something; without it a single agent crash breaks the skill entirely for all users): If some (but not all) reviewer agents fail: collect results from successful agents, always note "N of M reviewer angles completed" at the top of the synthesis output (unconditionally, regardless of impact assessment), and pass only successful findings to the synthesis agent. If all reviewer agents fail: fall back to the current single-agent approach — dispatch one general-purpose agent with the full existing Step 2 prompt (no parallel dispatch, no synthesis agent). The fallback note ("Note: parallel dispatch failed, falling back to single reviewer") is output as a one-line prefix to the normal Step 3 presentation — it does not create a new step.
   - Acceptance criteria: a partial failure (some agents succeed) does not halt the skill; partial coverage is always noted in the output as "N of M reviewer angles completed"; a total failure (all agents fail) produces a single-agent review using the existing prompt; fallback note appears as a prefix to Step 3 output.

## Non-Requirements

- The Apply/Dismiss/Ask classification logic (Step 4) is unchanged — this is the orchestrator's job and runs after synthesis exactly as it does today.
- The callsites that trigger critical-review are not changed — `specify.md`, `plan.md`, and `discovery/references/research.md` continue to invoke the skill as-is.
- The skill does not need to detect project type from CLAUDE.md, conversation history, or any source other than `requirements/project.md` and `lifecycle.config.md`.
- Step 1 (artifact discovery logic) is unchanged. Domain context loading is a new pre-dispatch step within Step 2, not a modification to Step 1.
- Step 3 (present synthesis) is unchanged.
- No new config file or settings field is introduced for this feature.
- The expanded angle menu is illustrative, not exhaustive — reviewer agents are not limited to listed examples and should derive the most relevant angles for the specific artifact.

## Edge Cases

- **No `requirements/project.md`**: Reviewer agents receive no `## Project Context` section. The skill works the same as today but without domain context injection. This is the graceful degradation case — the skill should be meaningfully better when context is available but still functional without it.
- **`lifecycle.config.md` present but `type:` field absent or commented out**: Treat as if the file does not exist for the purposes of domain context — do not inject an empty or null type.
- **Partial reviewer agent failure**: 1 of 4 agents fails — collect 3 results and proceed to synthesis. The synthesis agent notes coverage was partial only if it affects the quality of findings (e.g., a critical angle is missing).
- **Total reviewer agent failure**: All agents fail — fall back to single-agent review. This preserves the existing behavior and ensures the skill always returns something useful.
- **Synthesis agent fails**: Surface the error to the user and present raw per-angle findings directly (skip synthesis, present all agent outputs). Step 4 operates on the raw findings.
- **Artifact is very short (< 10 lines)**: Angle derivation may produce fewer than 3 distinct angles. Minimum is 2; do not pad with redundant angles. Dispatch whatever can be derived.
- **Skill invoked on conversation context (no lifecycle active)**: Behavior unchanged — extract artifact from conversation context, proceed with angle derivation and multi-agent dispatch as normal.

## Technical Constraints

- Parallel reviewer agents use Task tool dispatch (not Agent tool) — same pattern as lifecycle `research.md` §1a and `plan.md` §1b. No `isolation: worktree` needed (read-only).
- Synthesis agent is dispatched sequentially after parallel agents complete — it is a dependency on all reviewer findings.
- Reviewer agent model: general-purpose (default model). Synthesis agent model: Opus.
- `requirements/project.md` is read in the main orchestrator context before dispatching agents — the orchestrator already has the file content available from the lifecycle/refine flow. It should not dispatch a subagent to read it.
- The total added latency is: (max individual reviewer latency) + (synthesis agent latency). This replaces the current single reviewer latency. For most artifacts, this will be slower overall but produce deeper output.
