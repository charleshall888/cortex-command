# Complete Phase — First-Run PR Flow

Read only on `first_run` routing from complete.md, or on a fresh `complete` entry that hasn't opened a PR. Creates a PR, then pauses for merge; re-invocation routing and finalization stay in complete.md.

## Step 1 — Tests

From `cortex/lifecycle.config.md`: `test-command` set → run it.
<!-- pause: complete-test-command-ask question -->
Config present without `test-command` → ask the user whether there are tests to run. No config → skip, noting "No `cortex/lifecycle.config.md` found — skipping test step."

Failures → report and halt until resolved. First-run only; the router skips this on re-invocation.

## Step 2 — Commit artifacts

`cortex-read-commit-artifacts`: `true` (default) → stage `cortex/lifecycle/{slug}/` plus any uncommitted source and commit via `/cortex-core:commit`; `false` → commit only the source.

## Step 3 — Push and open the PR

Push the branch, then create a PR whose title and body reflect the feature's purpose and link the lifecycle directory. Capture the PR number, URL, and current branch for Step 4.

If this lifecycle runs from inside an `interactive/{slug}` worktree — both `read_lock(slug)` returns non-None **and** `git rev-parse --show-toplevel` is that worktree root — wrap `/cortex-core:pr` in a cd-in-then-out around the worktree. Otherwise invoke it from the current cwd. Advisory, non-blocking.

## Step 4 — Record it

One call resolves repo identity, atomically writes `cortex/lifecycle/{slug}/pr.json`, and logs the opened-PR event. Pass `--url`/`--head-branch` from Step 3 so the verb skips its `gh pr view` fallback:

```bash
cortex-lifecycle-record-pr-opened --feature {slug} --number {pr-number} --url {pr-url} --head-branch {head-branch}
```

`ok` → Step 5. `gh-error` → surface `message` and halt; do not hand off without a recorded PR. `repo` is resolved at PR-creation time and locked, so complete.md's router hits the right repository even if `origin` later changes.

<!-- pause: complete-merge-wait phase-exit-wait -->
## Step 5 — Phase-exit pause

Exit with this handoff and go no further:

> PR open at `<url>`; merge on GitHub, then re-run `/cortex-core:lifecycle complete <slug>` to finalize.

Don't poll — manual re-invocation is the gate.
