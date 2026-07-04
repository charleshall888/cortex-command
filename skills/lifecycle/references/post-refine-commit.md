# Post-Refine Commit

Follow this when refine returns control at the Specify → Plan boundary.

## Flag check

Run `cortex-read-commit-artifacts` (the `commit-artifacts` flag from `cortex/lifecycle.config.md`). `false` → skip the commit silently (no staging, no `/cortex-core:commit`) and return to lifecycle Step 3. `true` → proceed to Staging.

## Staging

Stage the refine artifact set, then act on the verb's `signal`:

```
cortex-lifecycle-stage-artifacts --phase refine --feature {feature}
```

It prints `{"signal": "staged"|"nothing_staged", "staged_paths": [...]}`:

- `nothing_staged` → exit silently (no commit) and return to Step 3 so it auto-advances to Plan (resume case).
- `staged` → proceed to Commit.

A non-zero verb exit is a staging failure: halt before Plan rather than commit a partial set.

## Commit subject

From the staged set — the approval path stages `spec.md`, the cancel path omits it:

- `spec.md` staged → `Refine {feature}: research and spec`
- `spec.md` absent → `Refine {feature}: cancelled at spec approval`

Invoke `/cortex-core:commit` with that subject and a one-line body (e.g. `- Research and spec produced by /cortex-core:refine for {feature}`).

## Halt-before-Plan gate

If `/cortex-core:commit` exits non-zero (index lock, pre-commit hook rejection, working-tree conflict), surface the error and HALT — do not auto-advance to Plan. The uncommitted `phase_transition` (or `lifecycle_cancelled`) row waits in the working tree until the operator resolves the failure and re-invokes `/cortex-core:lifecycle`; resume continues from the current phase.

## Constraints

- Hand-edits made before re-invocation are staged and committed under the Refine subject as-is — do not split, re-title, or pause.
