---
schema_version: "1"
uuid: 45d25333-3a9e-4c96-ace3-6539443e54bb
title: cortex-lifecycle-next serves only the main-root log path, so a worktree session writes its artifacts into the wrong tree
status: complete
priority: medium
type: bug
created: 2026-08-19
updated: 2026-08-19
tags: ['lifecycle', 'worktree', 'next-verb', 'envelope']
areas: ['lifecycle']
---
Filed from wild-light, 2026-08-19, during `/cortex-core:build` Plan for
`continuous-waterline-for-submerging-structures` (#523) run from a git worktree.

**Not a request to change the two-anchor design.** That design is deliberate, documented and has an
incident behind it (`lifecycle/review_brief.py:705-712`, #484): artifacts follow the CWD, `events.log`
follows the pinned main-root resolver, because resolving the log from the CWD once read a worktree's
stale *committed* log and served "cycle 1 · full review" for cycle 2. The escape hatch already exists
(`--lifecycle-dir` pins both to one tree). This ticket is about the **served envelope**, not the resolver.

## Why

`cortex-lifecycle-next` reports exactly one of the two anchors, and it is the one the agent must NOT
write artifacts into.

The served envelope carries `advance_contract.log_path` and an `evidence_trace` row
`{"step": "log_resolution", "log_path": "<main-root absolute>", "anchor": "main-root"}`
(`lifecycle/next_verb.py:371`). It carries **no artifact root at all** — neither absolute nor relative,
neither CWD-anchored nor labelled.

So the only absolute path the agent is handed points at the main repo, in a session whose CWD is a
worktree. The natural reading of "here is where this feature's lifecycle lives" is wrong for every
tracked artifact the phase is about to write.

## What it cost, concretely

The Plan phase wrote `plan.md`, ran `register-artifact`, `advance plan-decision`, `stage-artifacts` and
the commit **all from the main repo root**, because the agent followed the one absolute path it was
given. Result: `plan.md` landed on `main` while the worktree branch that was doing the work could not
see it, and the backlog ticket file ended up modified in **both** trees with different content — the
worktree's copy carrying a stale `lifecycle_phase: research` from the earlier refine session that no
subsequent verb would ever correct, because every verb call had followed the agent into the other tree.

Nothing errored. Every verb returned its success envelope. The split is only visible if you think to
run `git status` in both trees.

## Role

`resolve_arguments` in `lifecycle/next_verb.py` already resolves both roots — it anchors identity and log
resolution at the main repo root, and the artifact root is implicitly the CWD. Only one of the two
reaches the caller.

## Integration

Add the artifact root to the served envelope beside the log path, and label both. Shape suggestion, not
a prescription:

```json
"roots": {
  "artifacts": {"path": "<cwd-anchored absolute>", "anchor": "cwd"},
  "events_log": {"path": "<main-root absolute>", "anchor": "main-root"}
}
```

The `evidence_trace` already has the right idiom — a `{step, path, anchor}` row — so a second
`artifact_resolution` row may be the smaller change. Either way the point is that **both anchors become
visible at the same moment**, so an agent cannot infer one from the other.

The consuming half is `skills/build/SKILL.md` and its `references/plan.md`: they should read the artifact
root from the envelope rather than composing `cortex/lifecycle/{feature}/` against an unstated CWD, and
say in one line that artifacts follow the CWD while the log does not.

## Edges

- **A non-worktree session must be unaffected.** The two roots coincide there, so the added field is
  redundant and must stay consistent rather than becoming a second source of truth.
- **`--lifecycle-dir` pins both to one tree.** When it is passed, both reported anchors must reflect
  that pin, not the unpinned resolution — otherwise the envelope contradicts the flag.
- **Do not report the artifact root as a relative path.** Relative is what makes this ambiguous in the
  first place; the whole defect is an unstated CWD.
- **This is a reporting change, not a behaviour change.** No verb should start writing anywhere new. A
  fix that silently redirects artifact writes would re-open #484 from the other side.
- The same asymmetry plausibly reaches `describe`, `review-brief` and `complete-route`, which all
  document main-root anchoring; worth a sweep rather than a single-file patch.

## Touch-points

- `cortex_command/lifecycle/next_verb.py` (`resolve_arguments`, the `evidence_trace` composition at `:371`)
- `cortex_command/lifecycle/review_brief.py:705-712` — the two-anchor rationale, the canonical statement
- `cortex_command/lifecycle/describe.py`, `complete_route.py` — same anchoring language, unchecked
- `claude/skills/build/SKILL.md` and `claude/skills/build/references/plan.md` — the consuming half
- `cortex_command/tests/test_lifecycle_event.py::test_write_from_a_real_worktree_lands_in_the_main_root`
  — the existing worktree fixture a reporting test can reuse

---

## Resolution, 2026-08-19 — both anchors reported; the consuming half cost negative bytes

The envelope now carries a `roots` block with both anchors labelled and absolute, plus an
`artifact_resolution` row in `evidence_trace` in the existing `{step, path, anchor}` idiom, so neither
anchor can be inferred from the other. Reporting only: no verb writes anywhere new, because a fix that
silently redirected artifact writes would re-open #484 from the other side.

The artifact path is resolved through `_resolve_user_project_root_from_cwd`, which is what
`register-artifact` and `stage-artifacts` both actually use — it reports what those verbs will do rather
than a second opinion. `build_served_envelope` stays pure over its inputs, as its docstring promises: the
caller resolves the directory and passes it in. If the CWD root cannot resolve, the path is `null` rather
than a guess — the whole defect was an anchor the caller could not see, and a fabricated one is worse
than an absent one.

**`--lifecycle-dir` does not apply here.** The Edge assumed this verb has that flag; it does not
(`review-brief` does). Nothing to reconcile.

**The consuming half made the skill smaller, not larger.** The prose composed
`cortex/lifecycle/{feature}/…` in four places — literally the unstated-CWD form this ticket is about —
so pointing those at `{roots.artifacts.path}` fixes the ambiguity and saves 16 bytes of reference prose.
One clause was added to the SKILL.md sentence that already enumerates the envelope's fields (+137 bytes
on the L1 surface, which every phase loads once), naming where artifacts go and that the log path is not
it. Net on `skills/build/references/`: the pin went 57323 → 57307.
