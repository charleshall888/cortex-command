# Post-Refine Commit

When refine returns control at the Specify → Plan boundary, follow this commit procedure.

## Preconditions

Run only when the most recent significant event in `cortex/lifecycle/{feature}/events.log` is one of:

- `{"event": "phase_transition", "from": "specify", "to": "plan"}` — the approval path.
- `{"event": "lifecycle_cancelled"}` — the cancel path.

**Detection algorithm**: scan `events.log` bottom-up; the first occurrence of either event determines the path.

## Flag Check

Run `cortex-read-commit-artifacts` to read the `commit-artifacts` flag from `cortex/lifecycle.config.md`. The binstub prints `true` or `false` on stdout.

- stdout `true` (the default, also fires when the file or field is absent): proceed to Staging.
- stdout `false`: skip the commit silently. Do not stage, do not invoke `/cortex-core:commit`. Return control to lifecycle Step 3.

## Staging

Stage the explicit path set below — do **not** use a directory glob (a glob sweeps unrelated residue from sibling skills).

Approval path (most recent event is `phase_transition specify→plan`):

```
git add -- cortex/lifecycle/{feature}/research.md \
            cortex/lifecycle/{feature}/spec.md \
            cortex/lifecycle/{feature}/index.md \
            cortex/lifecycle/{feature}/events.log
```

Plus, when the feature has an originating backlog file (Context A — `cortex-resolve-backlog-item` returned exit 0 at Step 1), also stage that file:

```
git add -- cortex/backlog/{NNN}-{slug}.md
```

Cancel path (most recent event is `lifecycle_cancelled`): identical to the approval path **except** `spec.md` is omitted from staging — spec.md is absent on disk because the user cancelled before refine wrote it.

## No-Op Short-Circuit (Stage-First)

After running the targeted `git add` above, check whether anything was actually staged:

```
git diff --cached --quiet
```

- Exit 0 (nothing staged): nothing changed since the last commit. Exit silently without invoking `/cortex-core:commit`. Return control to lifecycle Step 3 so it auto-advances to Plan (resume case).
- Exit 1 (something staged): proceed to Commit.

## Commit Subject

Compose the commit subject from the detected path:

- Approval path: `Refine {feature}: research and spec`
- Cancel path: `Refine {feature}: cancelled at spec approval`

Path selection follows the Preconditions detection algorithm.

Invoke `/cortex-core:commit` with the chosen subject and a one-line body summarizing the contents (e.g., `- Research and spec produced by /cortex-core:refine for {feature}`).

## Halt-Before-Plan Gate

If `/cortex-core:commit` exits non-zero (index lock, pre-commit hook rejection, working-tree conflict, etc.), the orchestrator **MUST** surface the error to the operator and HALT. Do not auto-advance to Plan. The stranded `phase_transition` row (or `lifecycle_cancelled` row) remains uncommitted in the working tree until the operator resolves the underlying failure — resolve the conflict, re-run `/cortex-core:commit`, or revert — and re-invokes `/cortex-core:lifecycle`. On re-invocation, lifecycle's resume routing detects the working state and continues from the current phase.

## Constraints

- This reference does **not** introduce new event types (see `bin/.events-registry.md`).
- No user pause occurs in this procedure.
- Hand-edits to refine artifacts made before re-invocation are staged and committed under the Refine subject as-is — do not split, re-title, or pause.
