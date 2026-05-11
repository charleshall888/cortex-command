# Angle Menu (Step 2b reference)

The orchestrator derives 3-4 challenge angles in Step 2b. The menu below
lists representative examples — not an exhaustive set. Pick angles most
likely to reveal real problems for this specific artifact, choosing from
the menu or inventing new angles that fit the artifact better. If domain
context was loaded in Step 2a, weight domain-specific examples more heavily
— but domain detection is optional, not required for angle derivation.

## General Examples

- Architectural risk
- Unexamined alternatives
- Fragile assumptions
- Integration risk
- Scope creep
- Real-world failure modes

## Domain-Specific Examples (games)

- Performance budget
- Game loop coupling
- Save/load state
- Platform store compliance

## Domain-Specific Examples (mobile)

- Platform API constraints
- Offline behavior
- Haptic/accessibility
- Background execution limits

## Domain-Specific Examples (workflow/tooling)

- Agent isolation
- Prompt injection
- State file corruption
- Failure propagation

## Angle Count

- If the artifact is very short (< 10 lines): minimum 2 angles.
- Otherwise: target 3-4 angles.

## Acceptance Criteria

- **Distinctness**: No two derived angles may be re-phrasings of the same concern. Each must probe a different failure surface.
- **Artifact-specificity**: Each angle must cite a specific section, claim, assumption, or design choice in the artifact — not a generic category label. "Fragile assumptions" alone is not an angle; "The retry logic in section 3 assumes idempotent endpoints, which breaks for the payment webhook described in section 5" is.
