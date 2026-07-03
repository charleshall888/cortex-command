# Angle Menu (Step 2b reference)

Representative examples, not an exhaustive set — prefer inventing angles that
fit the specific artifact, and weight domain-specific examples when Step 2a
loaded a domain (optional).

## General Examples

A diversity nudge across concerns like architectural risk, fragile
assumptions, integration risk, and scope creep — not a checklist.

## Domain-Specific Examples

Weight by the loaded domain: games, mobile, and workflow/tooling (this repo's
usual subject) each surface their own failure modes — e.g. save/load state,
offline behavior, prompt injection, and state-file corruption.

## Angle Count

- If the artifact is very short (< 10 lines): minimum 2 angles.
- Otherwise: target 3-4 angles.

## Acceptance Criteria

- **Distinctness / artifact-specificity**: No two derived angles may be re-phrasings of the same concern, and each must cite a specific section, claim, assumption, or design choice in the artifact — not a generic category label. "Fragile assumptions" alone is not an angle; "The retry logic in section 3 assumes idempotent endpoints, which breaks for the payment webhook described in section 5" is.
