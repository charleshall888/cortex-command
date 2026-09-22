# Morning Review Walkthrough

## 1. Executive summary

Before asking anything, show the verdict, feature counts (completed / failed / deferred), and session duration.

## 2. Completed features

Read `cortex/lifecycle/sessions/latest-overnight/overnight-state.json`, if readable, for each feature's `round_assigned`, `started_at`, `completed_at`. Show every feature at once, under `### Round N` headings only when rounds differ:

```
### {feature-name}
**Round:** N  |  **Duration:** Xm Ys  |  **Files changed:** N
```

then the report's "How to try" block, word for word. Duration is `completed_at − started_at`. Files changed is the number of bullets under "Key files changed". Omit a field whose source is missing.

Then ask once: `Which features have you verified? ("all", "none", or a space/comma-separated list of names)`. Match names loosely. The answer is for the report only; it does not block advancement.

## 2a. Demo offer

```
cortex-morning-review-resolve-demo-config
```

Skip silently when:

- `state: none`
- `$SSH_CONNECTION` is set
- `git rev-parse --verify {integration_branch}` fails (`integration_branch` is in the state file)
- list path only: the state file has no `"status": "merged"` feature

On the list path, pick the entry whose `label`/`command` best matches the night's merged features and their key files (already in context; no git reads). No clear winner → skip.

Ask once, no follow-ups: `Run {label} demo ({command}) from {integration_branch} in a fresh worktree? [y / n]` (single path: `Spin up a demo worktree of {integration_branch} at $TMPDIR/demo-{session_id}-{timestamp} and print the launch command? [y / n]`). On `y`:

```
git -c core.hooksPath=/dev/null worktree add "$(realpath "$TMPDIR")/demo-{session_id}-$(date -u +%Y%m%dT%H%M%SZ)" "{integration_branch}"
```

`-c` turns off tracked checkout hooks. Never use `--force`. Failure → print stderr and move on. Success → print:

```
Demo worktree created at: {path}

To start the demo, run this in a separate terminal or shell:
    {command}

When you're done, close the demo and remove the worktree:
    git worktree remove {path}
```

Do not run the command yourself. Go to 2b either way.

## 2b. Lifecycle advancement

For each completed feature, in report order:

```
cortex-morning-review-advance-lifecycle --feature {feature}
```

The command does the checkbox count, the review check, and the `events.log` append. One line per `state`:

- `no-lifecycle-dir` → `no lifecycle dir`
- `already-complete` → `already complete`
- `advanced-complete` → `advanced → complete`
- `advanced-crash-recovery` → `advanced → complete (crash recovery)`
- `missing-review` → `missing review — expected review but none found`
- `advance-refused` → `advance refused — no completion row written`. The feature is NOT complete; a person must fix its `events.log`.
- else → `unrecognized state: {state}`. Flag it; never treat it as success.

Print them under a `Lifecycle updates:` summary.

## 3. Deferred questions

For each `deferred/{feature}-q*.md` (report order, then filename), show the feature and filename, the question (body or `question:`), what was tried, and what is needed. Ask `Your answer (or "skip" to leave this question unanswered):`. On an answer, append this after the existing content and change nothing else:

```
## User Answer (YYYY-MM-DD)

{answer verbatim}
```

## 4. Failed features

For each: name, error summary, suggested next step.

If the entry says `Feature is on the integration branch`, the work merged and a later step failed. Say so, point to `cortex/lifecycle/sessions/latest-overnight/overnight-events.log` for the failed step, and offer no ticket; it would duplicate landed work.

Otherwise ask `Create a backlog investigation item for this failure? [yes / skip]`. On yes, run `cortex-read-backlog-backend` once:

- `cortex-backlog` → `/backlog-author compose` from the failure (why = what visibly failed, role = investigate root cause, integration = the feature, edges = non-goal: re-running the session), then `cortex-create-backlog-item --title "investigate <feature-slug>" --status should-have --type bug --body "<body>"`.
- `none` → one-line advisory; write nothing.
- external → file it as best you can per `backlog.instructions`. If that fails, show the body.

## 5. Commit

`/commit` the review's artifacts (completion rows in `events.log`, closed or archived tickets, the index). Do not ask for confirmation.

## 6. PR merge

```
cortex-morning-review-pr-status
```

- `no-branch` / `no-pr` / `several` / `merged` / `closed` / `gh-error` → show `message` and stop this section. `several` lists `candidates`; never pick one. `merged` only reports; touch no tickets.
- `open` → show `pr` (url, title) and run `open {url} 2>/dev/null || true`.

If `pr.draft` is true (a session that made no progress), GitHub blocks the merge. Offer:

- **mark ready and merge** — `gh pr ready {number}`, then the merge below
- **close** — `gh pr close {number}`; warn the remote branch `{integration_branch}` and any worktree remain and need manual deletion
- **leave as draft**

Otherwise ask `Merge this PR to main? [yes / no]`.

- Yes → `gh pr merge {number} --merge --delete-branch`. Success → "Merged. Remote branch deleted." If `worktree_path` exists, run `git worktree remove --force {worktree_path}`; report the result and never fail the review over it. Remove any demo worktree from 2a the same way. Failure → show the error and leave the PR open.
- No → "PR left open at {url} — merge manually when ready."

Run 6a and 6b only after a merge confirmed in this review.

## 6a. Post-merge sync

```
cortex-git-sync-rebase cortex_command/overnight/sync-allowlist.conf
```

Exit code:

- `0` → "Local main synced."
- `1` → rebase aborted (conflicts outside the allowlist, or budget exhausted; stderr says which). Resolve with `git pull --rebase origin main`.
- `2` → rebased but push failed. Run `git push origin main` when the network is back.
- `3` → behind-count unreadable, nothing touched. Check `git log --oneline origin/main..main`.
- `4` → fetch failed (network/auth), nothing touched.
- Other → treat main as unsynced.
- Missing script → skip and note "install the `cortex-core` plugin".

Continue to 6b in every case: the merge allows closing tickets, not the sync.

## 6b. Close tickets

Close every completed feature in one call; the command resolves the backend.

```
cortex-morning-review-close-tickets --item {feature}={identifier} [--item ...]
```

`{identifier}` is the zero-padded `backlog_id` from the state file (`078`), or the lifecycle slug if there is none. For each item's `state`:

- `closed` → `closed #{id}` (add `(parent epic also closed)` when `parent_closed`)
- `no-ticket` → `no ticket found`
- `ambiguous` → show `message`'s candidates and ask for a clearer name
- `skipped-disabled` → one-line advisory (`none` backend)
- `external` → close it as best you can per `backlog.instructions`; tell the user if that fails
- `error` → `close failed: {message}`, continue

Print a `Ticket closure results:` summary.

Then push. Until the closes reach main, they read `complete` only on this machine:

```
cortex-morning-review-push-closures --path {changed_path} [--path ...] --ticket {id} [--ticket ...]
```

`--path` takes every `changed_paths` entry of every `closed` item. `--ticket` takes every `closed` id whose `status_changed` is true. With none, the command commits nothing rather than push timestamp-only changes. By `state`:

- `pushed` → `closures pushed to main ({commit})`
- `no-op` → say nothing
- `push-failed` → show `message` and name `unpushed_tickets` as committed locally only. The review did not fully succeed.
- `error` → `push step failed: {message}`
