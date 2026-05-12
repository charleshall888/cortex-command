# Specification: critical-review-self-resolve-before-asking

## Problem Statement

Critical Review's Step 4 (Apply Feedback) classifies objections into three dispositions: Apply, Dismiss, and Ask. The existing Apply bar says "Do not Ask to seek approval for things the orchestrator can determine" but does not instruct the orchestrator HOW to investigate before classifying as Ask. This causes the orchestrator to default to Ask for items it could resolve with a brief check of the artifact, codebase, or project context — wasting human attention and creating a dead end during overnight execution where no human is available.

## Requirements

1. **Self-resolution instruction in Step 4**: Add a paragraph to Step 4 between the Ask definition (line 185) and the "After classifying all objections" block (line 187) that instructs the orchestrator to briefly investigate before classifying as Ask. The paragraph must include:
   - **Specific investigation steps**: re-read relevant artifact sections, check related codebase files, consult project context from Step 2a
   - **Bounded scope**: "a brief check, not an exhaustive search" — if the answer isn't evident from the artifact, loaded context, or a quick file read, classify as Ask
   - **Tighter evidence boundary**: resolve only when supported by verifiable evidence — specific file paths, artifact text, or explicit project context. NOT inferences from general principles or "logical consequences"
   - **Anchor check**: "if your resolution relies on reasoning you already held before investigating — conclusions from your work on this artifact rather than new evidence found during the check — treat it as Ask. That is anchoring, not resolution"
   - **Preserved burden of proof**: uncertainty still defaults to Ask. The Apply bar ("Uncertainty is a legitimate reason to Ask — do not guess and apply") remains unchanged and governs the final classification
   - AC: The paragraph exists in `skills/critical-review/SKILL.md` Step 4 between the Ask definition and the post-classification flow. Interactive/session-dependent: verification requires running critical-review and observing disposition behavior.

2. **Clarify-critic parallel update**: Add an adapted version of the self-resolution paragraph to `skills/lifecycle/references/clarify-critic.md`'s Disposition Framework section. The adaptation must account for:
   - **Context difference**: In clarify-critic, the "artifact" is the confidence assessment + source material, not a plan/spec/research document. Investigation means re-reading the source material and checking requirements context from clarify §2.
   - **Apply semantics**: Reclassifying a resolved item as Apply means revising a confidence dimension's rating, not editing artifact text.
   - **Merge order**: Self-resolution runs after classification and before the Ask-to-Q&A Merge Rule. Surviving Ask items merge into §4 Q&A as before.
   - **Disposition counts**: The `clarify_critic` event's `dispositions` counts reflect post-self-resolution values.
   - AC: `grep -c 'self-resolution\|anchor check' skills/lifecycle/references/clarify-critic.md` ≥ 1

## Non-Requirements

- **No fresh agent dispatch**: The orchestrator performs self-resolution inline. The anchoring risk is mitigated by the anchor check, not by agent isolation. The orchestrator in Step 4 is two structural separations from the artifact generator (independent reviewers → Opus synthesis → orchestrator), making the anchoring concern weaker than the generator-evaluator case the article describes.
- **No formal rubric**: The resolution criteria are embedded in the paragraph's evidence boundary and anchor check, not a separate 4-category taxonomy.
- **No event logging**: Critical-review Step 4 does not currently log events. Clarify-critic event logging IS updated (R2) because it already logs disposition counts.
- **No changes to Apply or Dismiss**: Only the Ask classification path gets a pre-classification check.
- **No changes to Steps 2c or 2d**: Upstream review and synthesis are unaffected.

## Edge Cases

- **All potential Ask items resolve during the check**: Valid outcome. Zero Ask items in the consolidated message.
- **No items initially trending toward Ask**: Self-resolution paragraph is effectively a no-op. No overhead.
- **Orchestrator's resolution relies on prior reasoning, not new evidence**: The anchor check catches this — reclassify as Ask. This mirrors the existing Dismiss anchor check pattern.
- **Investigation finds partial evidence**: If evidence is suggestive but not verifiable (e.g., "this is probably the convention but I can't confirm from the files I checked"), classify as Ask. The bounded-scope instruction ("if not evident quickly, classify as Ask") governs.

## Technical Constraints

- The self-resolution paragraph must be placed between the Ask definition and the post-classification flow — not after the Apply bar, which governs all dispositions
- The Apply bar text must remain verbatim — the self-resolution instruction operates alongside it, not as a replacement
- The clarify-critic adaptation must preserve the Ask-to-Q&A Merge Rule and event logging format
