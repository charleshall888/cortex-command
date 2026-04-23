---
name: critical-review
description: Dispatches parallel reviewer agents — each focused on a single challenge angle — then synthesizes findings with an Opus agent to deeply challenge a plan, spec, or research artifact from multiple angles before you commit. Domain context from project requirements is injected so reviewers can surface domain-specific failure modes even when the artifact doesn't mention them. Use when the user says "critical review", "pressure test", "adversarial review", "pre-commit challenge", "deeply question", or "challenge from multiple angles". More thorough than /devils-advocate because parallel agents remove anchoring bias and produce deeper per-angle coverage than a single sequential pass. Also auto-triggers in the lifecycle for Complex + medium/high/critical features after plan approval.
---

# Critical Review

Derives challenge angles from the artifact and domain context, dispatches one fresh reviewer agent per angle in parallel, then synthesizes findings with an Opus agent. Each reviewer works independently with no anchoring to the reasoning that produced the artifact.

## Step 1: Find the Artifact

If a lifecycle is active, read the most relevant artifact (`lifecycle/{feature}/plan.md` → `spec.md` → `research.md`, in that order). Otherwise use conversation context. If nothing is clear enough to challenge, ask: "What should I critically review?" before proceeding.

## Step 2: Review Setup and Dispatch

### Step 2a: Load Domain Context

Before dispatching any reviewer agent, load project context for injection into reviewer prompts:

1. If `requirements/project.md` exists, read it and extract the **Overview** section (or the first top-level summary section if none is labeled "Overview") — up to ~250 words.
2. If `lifecycle.config.md` exists, read it and check for a `type:` field. Only use the value if it is present, non-empty, and not commented out (i.e., the line is not prefixed with `#`). If the value is valid, include it as a one-line prefix: `**Project type:** {type}` before the project overview text.
3. Construct a `## Project Context` block from these inputs. **If neither file exists** (or `requirements/project.md` is absent and `lifecycle.config.md` has no valid `type:` value), **omit the `## Project Context` section entirely** — do not inject an empty placeholder into reviewer prompts.

### Step 2b: Derive Angles

The orchestrator (in main conversation context) derives 3-4 challenge angles from the artifact. Each angle must be **distinct** (no two angles are re-phrasings of each other) and must **reference specific sections or claims in the artifact** (not generic category labels).

#### Angle Menu

The menu below lists representative angle examples — not an exhaustive set. Pick angles most likely to reveal real problems for this specific artifact, choosing from the menu or inventing new angles that fit the artifact better. If domain context was loaded in Step 2a, weight domain-specific examples more heavily — but domain detection is optional, not required for angle derivation.

**General examples:**
- Architectural risk
- Unexamined alternatives
- Fragile assumptions
- Integration risk
- Scope creep
- Real-world failure modes

**Domain-specific examples (games):**
- Performance budget
- Game loop coupling
- Save/load state
- Platform store compliance

**Domain-specific examples (mobile):**
- Platform API constraints
- Offline behavior
- Haptic/accessibility
- Background execution limits

**Domain-specific examples (workflow/tooling):**
- Agent isolation
- Prompt injection
- State file corruption
- Failure propagation

#### Angle Count

- If the artifact is very short (< 10 lines): minimum 2 angles.
- Otherwise: target 3-4 angles.

#### Acceptance Criteria

- **Distinctness**: No two derived angles may be re-phrasings of the same concern. Each must probe a different failure surface.
- **Artifact-specificity**: Each angle must cite a specific section, claim, assumption, or design choice in the artifact — not a generic category label. "Fragile assumptions" alone is not an angle; "The retry logic in section 3 assumes idempotent endpoints, which breaks for the payment webhook described in section 5" is.

### Step 2c: Dispatch Parallel Reviewers

For each angle derived in Step 2b, dispatch one general-purpose agent as a parallel Task tool sub-task. All agents run simultaneously — do not wait for one to finish before launching the next.

Each agent receives the following prompt template verbatim, with bracketed variables substituted at runtime:

---

You are conducting an adversarial review of one specific angle.

## Artifact
{artifact content}

## Project Context
{## Project Context block from Step 2a, omit this entire section if no context was loaded}

## Your Angle
**{angle name}**: {angle description — 1-2 sentences describing what this angle investigates}

## Finding Classes

Each finding must be tagged with exactly one class. Multi-class tags are prohibited.

- **A — fix-invalidating**: the artifact's proposed change does not work as described, or makes the situation worse. Worked example: "the refactor removes a null check the caller depends on."
- **B — adjacent-gap**: the proposed change is internally correct but an adjacent code path, callsite, or contract is left misaligned. Worked example: "the fix is correct but the analytics event a layer up still fires on the old path."
- **C — framing**: the artifact's narrative or framing misrepresents the change, scope, or motivation. Worked example: "the commit message misrepresents the change scope."

### Straddle Protocol

If one observed problem decomposes into both an A-class and a B-class concern, **split** into two separate findings. If the concerns cannot be cleanly split, **bias up to A** — the conservative class wins on unsplittable cases. Multi-class tags on a single finding are prohibited.

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

After the prose findings above, emit a JSON envelope so the orchestrator can extract structured class tags. Place the `<!--findings-json-->` delimiter on a line by itself, then the JSON object on subsequent lines:

<!--findings-json-->
{
  "angle": "<angle name>",
  "findings": [
    {
      "class": "A" | "B" | "C",
      "finding": "<text>",
      "evidence_quote": "<verbatim quote from the artifact>",
      "straddle_rationale": "<optional: rationale when splitting per Straddle Protocol, or when biasing up to A on an unsplittable case>"
    }
  ]
}

---

#### Failure Handling

**(a) Partial failure** — some agents succeed, some fail: Collect all successful results. Unconditionally note "N of M reviewer angles completed" at the top of the synthesis output (Step 2d). Proceed to Step 2d with the successful findings only.

**(b) Total failure** — all agents fail: Fall back to a single-agent approach. Dispatch one general-purpose agent with this fallback prompt verbatim:

---

You are conducting an adversarial review. Your job is to find what's wrong, risky, or overlooked — not to be balanced.

## Artifact

{artifact content}

## Instructions

1. Read the artifact carefully.
2. Derive 3-4 distinct challenge angles from its content. Pick the angles most likely to reveal real problems for this specific artifact, not generic critiques. Examples: architectural risk, unexamined alternatives, fragile assumptions, integration risk, scope creep, real-world failure modes. Use what fits.
3. Work through each angle. Be specific — cite exact parts of the artifact, not vague generalities. "This might not scale" is useless. "This approach requires X, but the artifact assumes Y, which breaks when Z" is useful.
4. Synthesize into one coherent challenge — not a per-angle dump. Find the through-lines. Flag anything multiple angles agree on as high-confidence. Surface tensions where angles conflict.
5. End with: "These are the strongest objections. Proceed as you see fit."

## Output Format

Use the following named sections:

## Objections
## Through-lines
## Tensions
## Concerns

Use bullets, not prose paragraphs. Each finding is a discrete bullet. Bullets may be multi-sentence when quoting artifact text as evidence. Skip sections where the agent returned no findings — do not emit empty section headers. Do not include balanced or endorsement sections — no "## What Went Well", no "## Strengths", no "## Recommendation".

Do not be balanced. Do not reassure. Find the problems.

---

Output the fallback agent's result directly (no synthesis step). Prefix the output with this one-line note: "Note: parallel dispatch failed, falling back to single reviewer" before proceeding to Step 3.

### Step 2d: Opus Synthesis

After all parallel reviewer agents from Step 2c complete (or the successful subset), dispatch one `opus` model agent with the following prompt template verbatim, with bracketed variables substituted at runtime:

---

You are synthesizing findings from multiple independent adversarial reviewers into a single coherent challenge.

## Artifact
{artifact content}

## Reviewer Findings
{all reviewer findings, one `## Findings: {angle}` block per reviewer}

## Instructions
1. Read all reviewer findings carefully.
2. Find the through-lines — claims or concerns that appear across multiple angles. Flag these as high-confidence.
3. Surface tensions where angles conflict or pull in different directions.
4. Synthesize into a single coherent challenge. Do not produce a per-angle dump.
5. Be specific — cite exact parts of the artifact.
6. End with: "These are the strongest objections. Proceed as you see fit."

## Output Format

Use the following named sections:

## Objections
## Through-lines
## Tensions
## Concerns

Use bullets, not prose paragraphs. Each finding is a discrete bullet. Bullets may be multi-sentence when quoting artifact text as evidence. Skip sections where the agent returned no findings — do not emit empty section headers. Do not include balanced or endorsement sections — no "## What Went Well", no "## Strengths", no "## Recommendation".

Do not be balanced. Do not reassure. Find the through-lines and make the strongest case.

---

#### Partial Coverage

If partial coverage occurred in Step 2c (some agents succeeded, some failed), unconditionally prefix the synthesis output with "N of M reviewer angles completed." before the synthesis narrative.

#### Synthesis Failure

If the synthesis agent fails, skip synthesis and present the raw per-angle findings from Step 2c directly. Step 3 and Step 4 (Apply Feedback) then operate on the raw findings instead of a synthesized narrative.

**Note:** Step 2d is skipped entirely when Step 2c's total-failure fallback was used — that path proceeds directly to Step 3.

## Step 3: Present

Output the review result directly. Do not soften or editorialize.

## Step 4: Apply Feedback

Immediately after presenting the synthesis, work through each objection independently. Do not wait for the user.

For each objection, assign one of three dispositions:

**Apply** — the objection identifies a concrete problem and the correct fix is clear and unambiguous. Examples: internal inconsistency, broken logic, missing information the agent can supply, acceptance criteria that are untestable or tautological, ordering dependencies not stated. Fix these without asking.

**Dismiss** — the objection is already addressed in the artifact, misreads the stated constraints, or would expand scope in a direction clearly outside the requirements. State the dismissal reason briefly. **Anchor check**: if your dismissal reason cannot be pointed to in the artifact text and lives only in your memory of the conversation, treat it as Ask instead — that is anchoring, not a legitimate dismissal.

**Ask** — the fix is not for the orchestrator to decide unilaterally. This covers: (a) genuine preference or scope decisions — which of two valid approaches to take, whether to include or exclude something, a priority call between competing values; (b) genuine orchestrator uncertainty about which fix is correct; (c) consequential tie-breaks — two equally reasonable implementations where the choice affects scope, design direction, or is hard to reverse. Hold these for the end.

**Before classifying as Ask, attempt self-resolution.** For each objection you are considering classifying as Ask, do a brief check — not an exhaustive search. Re-read the relevant artifact sections, check related codebase files, and consult any project context loaded in Step 2a. If the answer is supported by verifiable evidence — a specific file path, explicit artifact text, or documented project context — resolve it yourself and classify as Apply or Dismiss instead. Do not resolve based on inferences from general principles or reasoning you already held before investigating. **Anchor check**: if your resolution relies on conclusions from your prior work on this artifact rather than new evidence found during the check, treat it as Ask — that is anchoring, not resolution. Uncertainty still defaults to Ask.

After classifying all objections:

1. Re-read the artifact in full.
2. Write the updated artifact with all "Apply" fixes incorporated. Preserve everything not touched by an accepted objection.
3. Present a compact summary in the following format:

   - **Apply bullets describe the direction of the change**, not the objection text. Use one of these verbs as the first word of each bullet: strengthened, narrowed, clarified, added, removed, inverted.
   - **Dismiss: N objections** — a single count line. Omit the Dismiss line when N = 0.
   - **Ask items consolidate into a single message when any remain.**

   Worked examples:
   - Compliant: R10 strengthened from SHOULD to MUST.
   - Compliant: R3 narrowed from "all endpoints" to "payment endpoints".
   - Non-compliant: R10 updated. (No direction verb; restates the artifact change as prose.)

**Apply bar**: Apply when and only when the fix is unambiguous and confidence is high. Uncertainty is a legitimate reason to Ask — do not guess and apply. For inconsequential tie-breaks between equally reasonable implementations, pick one and apply. For consequential tie-breaks, Ask. Do not Ask to seek approval for things the orchestrator can determine — keep questions tightly scoped to genuine decisions or genuine uncertainty.
