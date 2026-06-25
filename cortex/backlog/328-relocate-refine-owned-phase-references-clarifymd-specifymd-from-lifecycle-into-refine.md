---
schema_version: "1"
uuid: efc74282-7740-4ec2-a2fc-ceceff70a1fc
title: Relocate refine-owned phase references (clarify.md, specify.md) from lifecycle into refine
status: complete
priority: low
type: chore
created: 2026-06-25
updated: 2026-06-25
---
## Why

`clarify.md` and `specify.md` describe the Clarify and Spec phases, which `/cortex-core:refine` owns — refine runs them standalone ("refine produces spec only") and lifecycle merely delegates to refine for them. Yet both files live in `skills/lifecycle/references/`, so `refine/SKILL.md` reaches *across the skill boundary* (`../lifecycle/references/clarify.md`, `../lifecycle/references/specify.md`) to execute its own core phases. The coupling is inverted: the wrapper (lifecycle) should depend on the sub-skill (refine), not the reverse. This is extraction debt — refine was split out of lifecycle after the fact; the SKILL.md moved but the phase references never followed. Surfaced in the 2026-06-25 lifecycle skill-trimming audit.

Evidence: the only runtime consumers of `clarify.md`/`specify.md` are inside refine (`refine/SKILL.md:35,68,91,102,152,163`), plus intra-phase cross-refs (`specify.md`↔`clarify.md`) and the shared `criticality-matrix.md`. Lifecycle-proper never reads them — its only mentions are the four Kept-pauses *audit* bullets (`SKILL.md:175–178`), which are themselves relocating under #327.

## Role

Relocate `clarify.md` and `specify.md` from `skills/lifecycle/references/` to `skills/refine/references/`, making refine self-contained for its own phases and flipping the coupling to the correct direction — lifecycle reaches *into* refine when delegating, exactly as it already does for `clarify-critic.md` (which correctly lives in refine). After the move, the `clarify.md → clarify-critic.md` reference becomes intra-refine (cleaner), and refine's `../lifecycle/references/` reaches for these two files disappear.

Explicitly OUT of scope — the genuinely shared seam files stay put: `load-requirements.md`, `orchestrator-review.md`, `critical-review-gate.md`, `complexity-escalation.md`, `discovery-bootstrap.md`, `post-refine-commit.md`, `criticality-matrix.md` are each consumed by both a refine phase and a lifecycle-proper phase (e.g. `orchestrator-review` runs at both the Specify and Plan gates; `load-requirements` is consulted by Clarify, Specify, and lifecycle Review). Moving those just inverts the coupling the other way, and the body-only `${CLAUDE_SKILL_DIR}` constraint gives no clean shared home. `load-requirements.md` is the one borderline call (2 of its 3 consumers move to refine) — evaluate it in this ticket; do not move reflexively.

## Integration

Lifecycle-gated (edits `skills/`). Update every reference when the files move:

- `refine/SKILL.md`: `../lifecycle/references/clarify.md|specify.md` → own-dir resolution (`${CLAUDE_SKILL_DIR}/references/...` in the body per ADR-0009, not a bare relative path).
- `lifecycle/references/criticality-matrix.md:40`: `specify.md` ref → `../refine/references/specify.md`.
- `lifecycle/references/specify.md → clarify.md` (`:65`) and `clarify.md → clarify-critic.md` (`:48`): become intra-refine relative refs after the move.
- Lifecycle body-propagation manifest + `refine-delegation.md`: confirm whether lifecycle still needs to thread these at all — likely it does NOT, since refine resolves its own references when invoked, which would shrink the manifest.
- Regenerate the mirror (`just build-plugin`); the moved files ship under `plugins/cortex-core/skills/refine/references/`.

## Edges

- **Interacts with #327** (Kept-pauses inventory relocation): the inventory anchors `clarify.md:57` and `specify.md:36/67/155` must repoint to `skills/refine/references/...`. Coordinate ordering so the parity test (`tests/test_lifecycle_kept_pauses_parity.py`, which already scans both `skills/lifecycle` and `skills/refine`) stays green. The pause-anchor line numbers (36/67/155) must stay within the test's ±35 tolerance after any same-file edits.
- `specify.md` carries cross-skill mirror notes to interview / requirements-gather (see the pr-16 audit fixture) — preserve those notes and their canonical-pointer wording through the move.
- `discovery` has its OWN `references/clarify.md` — do not conflate; this move touches only lifecycle's copy.

## Touch-points

- move `skills/lifecycle/references/clarify.md`, `specify.md` → `skills/refine/references/` (+ mirrors)
- `skills/refine/SKILL.md` (path refs), `skills/lifecycle/references/criticality-matrix.md`, `skills/lifecycle/SKILL.md` manifest + Kept-pauses anchors, `refine-delegation.md`
- `tests/test_lifecycle_kept_pauses_parity.py` (anchor repoint, coordinated with #327)