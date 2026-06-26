---
schema_version: "1"
uuid: cd473467-2134-4e1d-8d33-fddd125f120c
title: Offload complete.md PR-state routing and shared stage-artifacts to CLI verbs
status: backlog
priority: low
type: chore
created: 2026-06-25
updated: 2026-06-26
parent: 336
---
## Why

`complete.md` (15KB) is ~50-60% deterministic git/gh plumbing. Step 7's **PR-state router** (Branches 1-4, sub-cases 4a-4g) is a pure state machine over `events.log` + `pr.json` + `gh pr view` emitting ~10 fixed terminal messages — the same `detect-phase` pattern already used at Step 2. Step 11a's **finalization staging** (enumerated `git add`, resolver-filename lookup, stage-first guard, the "never directory-glob add" warning repeated ~5×) is near-identical to `post-refine-commit.md`'s staging. The agent hand-executes a script every Complete run. Surfaced in the 2026-06-25 lifecycle reference-file audit; **biggest single byte reduction.** Sibling of #326.

## Role

Two verbs:
- `cortex-lifecycle-complete-route <slug>` emits `{route, message, pr_state}`; the Step 7 prose collapses to "run it, act on `route`."
- `cortex-lifecycle-stage-artifacts --phase {complete|refine}` owns the staging shared by `complete.md`'s finalization step and `post-refine-commit.md`.

Residue that stays prose (genuine judgment / kept affordance): the `/cortex-core:commit` invocation, the PR-authoring step, the merge-wait pause, the preserve-lifecycle-dir guard, and the don't-clean-up-from-inside-the-worktree guard.

## Integration

New `cortex_command` verbs + edits to `references/complete.md` + `references/post-refine-commit.md` (+ mirrors) → lifecycle-gated. **Depends on #330's `--field` extension** — but the complete / post-refine event emission is built INTO these verbs here, not pre-migrated by #330 (those sites move as part of this ticket, to avoid touching the same lines twice). **PIN byte-identical `events.log` rows + identical staged-path sets.** complete.md's and post-refine-commit.md's prose trims also ride in this ticket — do not dedup them separately, since this rewrites those sections.

## Edges

- `gh`-absent / no-network → `complete-route` degrades gracefully (emit `pr_state: unknown`, never hard-fail).
- The stage-first `git diff --cached --quiet` guard and halt-on-commit-failure semantics must survive.
- Preserve both the `phase=none` and `phase!=none` close paths exactly.

## Touch-points

- new `cortex_command` modules (complete-route, stage-artifacts) + entries + tests
- `skills/lifecycle/references/complete.md`, `references/post-refine-commit.md` (+ mirrors)