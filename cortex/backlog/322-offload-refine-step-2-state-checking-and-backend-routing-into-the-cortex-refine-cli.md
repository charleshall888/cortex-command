---
schema_version: "1"
uuid: f58eb929-c4ec-4f64-b3ae-db01f9f9bc9f
title: Offload refine Step 2 state-checking and backend routing into the cortex-refine CLI
status: backlog
priority: low
type: chore
created: 2026-06-24
updated: 2026-06-24
---
## Why

`/cortex-core:refine` Step 2 ("Check State") carries deterministic, repetitive logic the model re-derives on every run: a ~13-line resume-point decision tree (which artifacts exist → which phase to resume) and a two-arm `emit-lifecycle-start` backend-routing branch. Both bloat a high-traffic skill body and put avoidable judgment in the hot path. Surfaced during a 2026-06-24 skill-trimming audit, alongside the already-landed exit-code fold and the seed→reconcile invariant relocation.

## Role

Move Step 2's state determination and backend-aware seeding out of the skill prose and into the `cortex-refine` CLI, so the skill shrinks to a thin command call plus the behavioral guards a CLI cannot carry. Four threads (widened by the 2026-06-24 skill-trimming audit), ideally one ticket:

1. **Resume-point determination.** Today the skill stats `spec.md`/`research.md` and branches in prose. One approach might be a `cortex-refine resume-point --lifecycle-slug {slug}` subcommand that returns the resume state as JSON; research could also explore folding this into the existing `cortex-lifecycle-state`. Either way, the skill should retain only the behavioral guards the CLI cannot encode — on "complete": do not prompt or offer a menu, re-run only on explicit user request; on spec-without-research: warn and skip Clarify since intent was already established.

2. **Backend-aware seeding.** Today the skill resolves the backend and then chooses whether to pass `--backlog-slug` to `emit-lifecycle-start` (a two-arm branch). Consider having `emit-lifecycle-start` resolve the backend itself and ignore `--backlog-slug` on non-`cortex-backlog` backends, so the skill can issue one unconditional call.

3. **Backend-aware `reconcile-clarify` (Step 5).** The Spec-phase `reconcile-clarify` invocation carries the same two-arm Context A / Context B branch as thread 2's `emit-lifecycle-start`. Fold it into the same backend-resolution approach so the skill stops carrying a parallel routing branch — preserving the seed→reconcile→gate ordering invariant (see Integration).

4. **Harden the considerations arg-interface.** `/cortex-core:refine` passes alignment findings to `/cortex-core:research` as `research-considerations="..."`, a `key="value"` argument that cannot contain `=` or `"` — forcing *both* skills to carry prose that strips/paraphrases those characters (refine's "Alignment-Considerations Propagation"; research Step 1). Explore a less brittle hand-off (e.g. a temp-file or stdin channel) so neither skill needs the escaping caveat. This is interface-shaped rather than a pure CLI offload, but shares the "the prose exists because the mechanism is fragile" root cause.

## Integration

Touches `cortex_command/refine.py` and `skills/refine/SKILL.md` Step 2 (plus the auto-generated mirror under `plugins/cortex-core/`). Lifecycle-gated, since it edits `refine.py` and `skills/`.

The backend-aware-seeding thread must preserve the seed→reconcile→gate ordering invariant documented in `skills/lifecycle/references/criticality-matrix.md` ("Seed → reconcile → gate ordering"): the seed still writes simple/medium defaults on non-local backends, and `reconcile-clarify` still ratchets up from Clarify's computed values so the critical-review gate stays fed.

## Edges

- Missing lifecycle dir → resume at clarify (start from beginning).
- "spec exists but research missing" is a distinct resume state, not the same as "research done."
- The local `cortex-backlog` arm must stay behaviorally identical (byte-identical events.log rows); preserve the idempotent read-after-write verify and the sandbox-write remediation message.

## Touch-points

- `cortex_command/refine.py` (`_cmd_emit_lifecycle_start`, `_cmd_reconcile_clarify`, the argparse surface, any new subcommand)
- `skills/refine/SKILL.md` Step 2 (resume-point block + seed-routing bullets), Step 5 (reconcile routing), and the considerations propagation block + mirror
- `skills/research/SKILL.md` Step 1 (considerations arg-parsing) + mirror
- Tests for the new/changed CLI surface and the considerations hand-off