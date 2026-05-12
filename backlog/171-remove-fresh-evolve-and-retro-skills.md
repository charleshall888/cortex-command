---
schema_version: "1"
uuid: 79b9e087-25bd-49fa-93ec-55e2aed015b6
title: "Remove /fresh, /evolve, and /retro skills"
status: complete
priority: medium
type: chore
tags: [skills, cleanup, deprecation]
created: 2026-05-06
updated: 2026-05-06
complexity: complex
criticality: high
spec: cortex/lifecycle/remove-fresh-evolve-and-retro-skills/spec.md
areas: [skills]
session_id: null
lifecycle_phase: complete
---

# Remove /fresh, /evolve, and /retro skills

## Context

The session-feedback loop (write a retro at session end → analyze retros for recurring trends → route fixes back into the lifecycle) is no longer needed. Remove the three skills that implement it.

## Scope

Delete from canonical sources (the pre-commit dual-source hook will regenerate the `plugins/cortex-core/skills/` mirrors):

- `skills/fresh/`
- `skills/evolve/`
- `skills/retro/`

## Touch points to clean up

- `hooks/cortex-scan-lifecycle.sh` — has `/fresh` resume-prompt integration (`scan-lifecycle/fresh-resume-fires` test in `tests/test_hooks.sh`). Decide whether the hook keeps a non-fresh resume mechanism or drops it.
- `skills/fresh/SKILL.md` Step 0 auto-invokes `/cortex-core:retro` for human-initiated sessions — this integration disappears with the skills.
- Docs referencing the skills: `docs/setup.md`, `docs/overnight-operations.md`, `docs/agentic-layer.md`, `docs/skills-reference.md`.
- Sibling skill references: `skills/refine/references/clarify-critic.md`, `skills/requirements/references/gather.md` (check whether retro mentions are load-bearing or just illustrative).
- `tests/test_hooks.sh` — drop the `scan-lifecycle/fresh-resume-fires` test case (currently failing per #170).

## Open questions

- **`retros/` directory** (162 historical retros): keep as read-only archive, move to `retros/archive/`, or delete? Default suggestion: keep in place — they're cheap to retain and may have historical reference value.
- **`CLAUDE_AUTOMATED_SESSION` env var**: introduced for `/fresh` Step 0 to skip auto-retro in automated sessions. Check whether anything else reads it; remove if not.
