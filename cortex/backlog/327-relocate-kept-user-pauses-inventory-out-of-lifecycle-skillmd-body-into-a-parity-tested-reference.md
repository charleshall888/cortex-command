---
schema_version: "1"
uuid: fe52c238-c021-4b08-a8aa-bc025c6641e9
title: Relocate Kept user pauses inventory out of lifecycle SKILL.md body into a parity-tested reference
status: complete
priority: low
type: chore
created: 2026-06-25
updated: 2026-06-25
---
## Why

The "Kept user pauses" inventory (~11 `file:line` bullets under Phase Transition in `skills/lifecycle/SKILL.md`) is governance/audit material — its consumers are the parity test (`tests/test_lifecycle_kept_pauses_parity.py`) and human reviewers, not the running agent. The agent encounters each pause where it is defined in the relevant phase reference; a flat anchor table is context pollution in the hot skill body. The operative runtime rule — "auto-proceed except where a phase reference defines a kept pause" — already lives one line up in Phase Transition. Surfaced in the 2026-06-25 lifecycle skill-trimming audit.

## Role

Move the inventory to `skills/lifecycle/references/kept-pauses.md` (or a data file), leave a one-line pointer in SKILL.md ("canonical, parity-tested inventory: references/kept-pauses.md"), and keep the operative rule in-body. Preserves the governance ratchet; removes ~15 audit lines from the agent's runtime context.

## Integration

Coupled change — these must move together:

- `tests/test_lifecycle_kept_pauses_parity.py`: repoint inventory-parsing from `SKILL_MD` to the new file. The new file contains "AskUserQuestion" in prose, so it needs the same call-site exclusion that SKILL.md currently gets in `_askuserquestion_sites()`.
- `CLAUDE.md`: the "Skill / phase authoring guidelines" section names the inventory's location ("lives in `skills/lifecycle/SKILL.md` under the 'Kept user pauses' section") — update the pointer.
- The Phase Transition rule's "...inventory below" phrasing → "...inventory in references/kept-pauses.md".

## Edges

- The parity test currently excludes the whole Phase Transition section from the AskUserQuestion-site scan; after the move, the new reference file must likewise be excluded as a call-site *source*, or its prose anchors get read as real sites.
- Keep bidirectional parity intact (every inventory entry ↔ every AskUserQuestion site) — just sourced from the new location.
- Mirror regenerates under `plugins/cortex-core/` — the new reference file ships there too.

## Touch-points

- `skills/lifecycle/SKILL.md` Phase Transition (+ mirror)
- new `skills/lifecycle/references/kept-pauses.md` (+ mirror)
- `tests/test_lifecycle_kept_pauses_parity.py`
- `CLAUDE.md` authoring-guidelines pointer