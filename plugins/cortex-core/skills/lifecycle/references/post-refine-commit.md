# Post-Refine Commit

When refine returns control at the Specify → Plan boundary, follow this commit procedure.

## Flag Check

Run `cortex-read-commit-artifacts` to read the `commit-artifacts` flag from `cortex/lifecycle.config.md`. The binstub prints `true` or `false` on stdout.

- stdout `true` (the default, also fires when the file or field is absent): proceed to Staging.
- stdout `false`: skip the commit silently. Do not stage, do not invoke `/cortex-core:commit`. Return control to lifecycle Step 3.

## Staging

Stage the refine artifact set with the verb, then act on its `signal`:

```
cortex-lifecycle-stage-artifacts --phase refine --feature {feature}
```

The verb auto-detects the approval vs cancel sub-mode and stages the exact set by explicit paths only (never a directory glob): `research.md, index.md, events.log` plus the originating backlog ticket (Context A), with `spec.md` staged on the approval path and omitted on cancel (spec.md is absent on disk because the user cancelled before refine wrote it). It prints `{"signal": "staged"|"nothing_staged", "staged_paths": [...]}`.

The verb's `signal` is the stage-first outcome (equivalent to `git diff --cached --quiet`):

- `nothing_staged` (the index already matches HEAD — `git diff --cached --quiet` would exit 0): exit silently without invoking `/cortex-core:commit`. Return control to lifecycle Step 3 so it auto-advances to Plan (resume case).
- `staged`: proceed to Commit.

A non-zero verb exit is a staging failure: halt before Plan rather than committing a partial set.

## Commit Subject

Compose the commit subject from the staged set — the approval path stages `spec.md`, the cancel path omits it:

- Approval path (`spec.md` staged): `Refine {feature}: research and spec`
- Cancel path (`spec.md` absent): `Refine {feature}: cancelled at spec approval`

Invoke `/cortex-core:commit` with the chosen subject and a one-line body summarizing the contents (e.g., `- Research and spec produced by /cortex-core:refine for {feature}`).

## Halt-Before-Plan Gate

If `/cortex-core:commit` exits non-zero (index lock, pre-commit hook rejection, working-tree conflict, etc.), the orchestrator **MUST** surface the error to the operator and HALT. Do not auto-advance to Plan. The stranded `phase_transition` row (or `lifecycle_cancelled` row) remains uncommitted in the working tree until the operator resolves the underlying failure — resolve the conflict, re-run `/cortex-core:commit`, or revert — and re-invokes `/cortex-core:lifecycle`. On re-invocation, lifecycle's resume routing detects the working state and continues from the current phase.

## Constraints

- This reference does **not** introduce new event types (see `bin/.events-registry.md`).
- No user pause occurs in this procedure.
- Hand-edits to refine artifacts made before re-invocation are staged and committed under the Refine subject as-is — do not split, re-title, or pause.
