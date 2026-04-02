# Specification: Consolidate /devils-advocate and /critical-review

## Problem Statement

The `/devils-advocate` skill (121 lines) has a structural inversion: roughly 60% of its content is error handling and examples, while only 40% addresses the critique task itself. Its 4-element critique framework is specified as a prose suggestion, making it unreliably enforced by Claude models — structured output schema specified in prose is not consistently followed. Additionally, both skills share near-synonymous trigger phrases ("stress test" / "pressure test"), which causes routing ambiguity. Finally, `clarify-critic.md` delegates its Apply/Dismiss/Ask logic to `/critical-review` by reference ("mirror CR's framework exactly") rather than defining it inline, creating a silent drift risk if CR's framework evolves. This spec addresses all three issues: restructuring DA, fixing trigger domain collision, and decoupling clarify-critic.md from CR.

## Requirements

All requirements below are **Must-have** — each addresses a concrete, in-scope problem identified in research with no viable deferral.

1. **[M] DA 4-element framework enforced via section headers**: `skills/devils-advocate/SKILL.md` Step 2 uses H3 headers for each of the four critique elements — `### Strongest Failure Mode`, `### Unexamined Alternatives`, `### Fragile Assumption`, `### Tradeoff Blindspot`. The current "write a flowing narrative covering these four things" instruction is replaced with section-oriented instructions under each header.
   - AC: Step 2 contains four H3 headers matching the element names above
   - AC: Each H3 section has a one-paragraph instruction for that element (specificity guidance, example of useless vs. useful framing, etc.)
   - AC: The phrase "flowing narrative" is removed
   - Target (non-binding): After all DA restructuring (Reqs 1–3) is applied, `skills/devils-advocate/SKILL.md` is in the range of 70–85 lines. This is a goal to keep the restructuring honest, not a hard gate — the success criteria section and "What This Isn't" are retained, so exact line count depends on blank lines and header density.

2. **[M] DA error handling compacted to a failure table**: The current three-subsection error handling block is replaced with a compact 3-row table. Columns: Error | Detection | Recovery.
   - AC: Error handling is a single markdown table with rows: "No direction", "Vague direction", "Insufficient context"
   - AC: Each row's Recovery column contains one actionable sentence (or at most two)
   - AC: The verbose sub-bullet recovery steps in the current version are removed

3. **[M] DA output examples reduced to one**: The current two output examples are replaced with a single tight example that demonstrates the new H3 section structure.
   - AC: Exactly one output example remains
   - AC: The retained example uses the four H3 headers (demonstrates the new format)
   - AC: The second verbose example (Input Validation Failure) is removed

4. **[M] Non-overlapping trigger domains + execution model distinction**: DA and CR are assigned distinct, non-overlapping trigger phrase sets. Crucially, both descriptions must also state their execution model — the key semantic differentiator — so the routing decision is based on mechanism, not just keyword matching.
   - DA domain: "challenge this", "poke holes", "devil's advocate", "argue against", "what could go wrong", "stress-test this". DA's description must note: inline critique from the current agent, no fresh agent, works mid-conversation with no lifecycle required.
   - CR domain: "critical review", "pressure test", "adversarial review", "pre-commit challenge", "deeply question", "challenge from multiple angles". CR's description must note: dispatches a fresh unanchored agent to reduce anchoring bias; more thorough than /devils-advocate.
   - AC: DA's `description` frontmatter includes inline/mid-conversation framing and does NOT contain "pressure test"
   - AC: CR's `description` frontmatter includes fresh-agent/anchoring-bias framing and does NOT contain "stress test"
   - AC: No trigger phrase appears verbatim in both descriptions

5. **[M] clarify-critic.md cross-reference sentence removed**: The Apply/Dismiss/Ask definitions are already inline in `clarify-critic.md` — the definitions appear directly after the phrase "Mirror the critical-review skill's framework exactly:". The cross-reference sentence is the only thing to remove. The inline definitions that follow it are retained as-is.
   - AC: The sentence "Mirror the critical-review skill's framework exactly:" is removed from `clarify-critic.md`
   - AC: The Apply, Dismiss, and Ask definition blocks that follow it remain unchanged
   - AC: A brief comment is added noting the connection to CR's Step 4 to aid future readers: e.g., "Apply/Dismiss/Ask framework — matches /critical-review Step 4"

## Non-Requirements

- This spec does NOT change `/critical-review`'s core structure, dispatch prompt, Step 4 logic, or Apply/Dismiss/Ask definitions
- This spec does NOT add a complexity gate to discovery's `/critical-review` call (separate concern, out of scope)
- This spec does NOT introduce any "DA invokes CR" or "CR invokes DA" delegation pattern
- This spec does NOT change how lifecycle or discovery invoke CR — those call sites use the Skill tool by name and are unaffected by description field changes
- This spec does NOT merge or remove either skill entirely
- This spec does NOT modify lifecycle reference files (specify.md, plan.md, SKILL.md) beyond clarify-critic.md

## Edge Cases

- **DA reads lifecycle artifacts in Step 1**: The new H3 section structure in Step 2 does not change Step 1 artifact-reading behavior. The step 1 read-order (plan.md → spec.md → research.md) stays intact.
- **CR description changes must not affect auto-trigger**: CR is auto-triggered by lifecycle using the Skill tool by name, not by description-based routing. Changes to CR's description field do not affect its lifecycle call sites.
- **clarify-critic.md inlined framework must be semantically identical**: The inline reproduction must not paraphrase, abbreviate, or reinterpret CR's Apply/Dismiss/Ask logic. A future reader should be able to compare the two files and confirm they define the same framework.
- **DA's "What This Isn't" section**: This section ("Not a blocker. Stop after making the case.") should be retained as-is — it is behavioral guidance not covered by the 4 elements, and it is not part of the error handling or examples being trimmed.
- **DA's Success Criteria section**: Update the first criterion from "The argument is coherent and narrative (not a bullet list of gripes)" to "Each section contains substantive, specific prose — not a one-line bullet or vague generalization." The H3 section structure would otherwise contradict the "not a bullet list" criterion. The other four criteria are retained unchanged.

## Technical Constraints

- **DA section headers must use H3 (`###`)**: The skill already uses H2 (`##`) for top-level sections (Input Validation, Step 1, Step 2, etc.). H3 headers inside Step 2 are consistent with the nesting convention.
- **clarify-critic.md currently at line 60**: The sentence "Mirror the critical-review skill's framework exactly:" is the only target. The Apply/Dismiss/Ask definitions that follow it (lines 62–67) are already inline and correct — do not replace them. Remove only the cross-reference sentence and add a brief comment noting the CR connection.
- **Symlink architecture**: `skills/` is symlinked to `~/.claude/skills/`. Changes take effect immediately on file save — no deploy step needed.
