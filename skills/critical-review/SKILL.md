---
name: critical-review
description: Dispatches a fresh, unanchored agent to deeply challenge a plan, spec, or research artifact from multiple angles before you commit. Use when the user says "critical review", "pressure test this", "deeply question this", "challenge from multiple angles", "adversarial review", "pre-commit challenge", or wants thorough adversarial analysis before committing to an approach. More thorough than /devils-advocate — uses a fresh agent with no context anchoring to derive and work through multiple challenge angles independently. Also auto-triggers in the lifecycle for Complex + medium/high/critical features after plan approval.
---

# Critical Review

Dispatches a fresh, unanchored agent to challenge the current plan, spec, or research before you commit to it. The reviewer derives its own angles — no anchoring to the reasoning that produced the artifact.

## Step 1: Find the Artifact

If a lifecycle is active, read the most relevant artifact (`lifecycle/{feature}/plan.md` → `spec.md` → `research.md`, in that order). Otherwise use conversation context. If nothing is clear enough to challenge, ask: "What should I critically review?" before proceeding.

## Step 2: Dispatch a Fresh Reviewer

Launch a fresh general-purpose agent. Pass it the artifact content and this prompt verbatim:

---

You are conducting an adversarial review. Your job is to find what's wrong, risky, or overlooked — not to be balanced.

## Artifact

{artifact content}

## Instructions

1. Read the artifact carefully.
2. Derive 3–4 distinct challenge angles from its content. Pick the angles most likely to reveal real problems for this specific artifact, not generic critiques. Examples: architectural risk, unexamined alternatives, fragile assumptions, integration risk, scope creep, real-world failure modes. Use what fits.
3. Work through each angle. Be specific — cite exact parts of the artifact, not vague generalities. "This might not scale" is useless. "This approach requires X, but the artifact assumes Y, which breaks when Z" is useful.
4. Synthesize into one coherent challenge — not a per-angle dump. Find the through-lines. Flag anything multiple angles agree on as high-confidence. Surface tensions where angles conflict.
5. End with: "These are the strongest objections. Proceed as you see fit."

Do not be balanced. Do not reassure. Find the problems.

---

## Step 3: Present

Output the reviewer's synthesis directly. Do not soften or editorialize.

## Step 4: Apply Feedback

Immediately after presenting the synthesis, work through each objection independently. Do not wait for the user.

For each objection, assign one of three dispositions:

**Apply** — the objection identifies a concrete problem and the correct fix is clear and unambiguous. Examples: internal inconsistency, broken logic, missing information the agent can supply, acceptance criteria that are untestable or tautological, ordering dependencies not stated. Fix these without asking.

**Dismiss** — the objection is already addressed in the artifact, misreads the stated constraints, or would expand scope in a direction clearly outside the requirements. State the dismissal reason briefly.

**Ask** — the fix is not for the orchestrator to decide unilaterally. This covers: (a) genuine preference or scope decisions — which of two valid approaches to take, whether to include or exclude something, a priority call between competing values; (b) genuine orchestrator uncertainty about which fix is correct; (c) consequential tie-breaks — two equally reasonable implementations where the choice affects scope, design direction, or is hard to reverse. Hold these for the end.

After classifying all objections:

1. Re-read the artifact in full.
2. Write the updated artifact with all "Apply" fixes incorporated. Preserve everything not touched by an accepted objection.
3. Present a compact summary: what was changed (one line per fix), what was dismissed and why, and — only if any remain — ask about "Ask" items in a single consolidated message.

**Apply bar**: Apply when and only when the fix is unambiguous and confidence is high. Uncertainty is a legitimate reason to Ask — do not guess and apply. For inconsequential tie-breaks between equally reasonable implementations, pick one and apply. For consequential tie-breaks, Ask. Do not Ask to seek approval for things the orchestrator can determine — keep questions tightly scoped to genuine decisions or genuine uncertainty.
