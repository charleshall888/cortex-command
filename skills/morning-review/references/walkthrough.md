# Morning Review Walkthrough

## 1. Executive summary

Before any interaction: verdict, feature counts (completed / failed / deferred), session duration.

## 2. Completed features

Read `cortex/lifecycle/sessions/latest-overnight/overnight-state.json` best-effort for each feature's `round_assigned`, `started_at`, `completed_at`. Display every feature at once, under `### Round N` headings only when rounds differ:

```
### {feature-name}
**Round:** N  |  **Duration:** Xm Ys  |  **Files changed:** N
```

then the report's verbatim "How to try" block. Duration is `completed_at − started_at`; files changed is the bullet count of "Key files changed". Omit any field whose source is missing.

Then one question: `Which features have you verified? ("all", "none", or a space/comma-separated list of names)`. Match names loosely. Verified/skipped is reporting context only — it does not gate advancement.

## 2a. Demo offer

```
cortex-morning-review-resolve-demo-config
```

`state: none` → skip silently. Also skip when `$SSH_CONNECTION` is set, when `git rev-parse --verify {integration_branch}` fails (`integration_branch` from the state file), or — list path only — when the state file has no `"status": "merged"` feature. On the list path pick the entry whose `label`/`command` best matches the night's merged features and their key files (already in context; no git reads); no clear winner → skip.

Ask once, no follow-ups: `Run {label} demo ({command}) from {integration_branch} in a fresh worktree? [y / n]` (single path: `Spin up a demo worktree of {integration_branch} at $TMPDIR/demo-{session_id}-{timestamp} and print the launch command? [y / n]`). On `y`:

```
git -c core.hooksPath=/dev/null worktree add "$(realpath "$TMPDIR")/demo-{session_id}-$(date -u +%Y%m%dT%H%M%SZ)" "{integration_branch}"
```

(`-c` neutralizes tracked checkout hooks; never `--force`.) Failure → print stderr and move on. Success → print:

```
Demo worktree created at: {path}

To start the demo, run this in a separate terminal or shell:
    {command}

When you're done, close the demo and remove the worktree:
    git worktree remove {path}
```

Do not run the command yourself; proceed immediately to 2b either way.

## 2b. Lifecycle advancement

For each completed feature, in report order:

```
cortex-morning-review-advance-lifecycle --feature {feature}
```

The verb owns the checkbox count, the review gate, and the `events.log` append. Map `state` to a line: `no-lifecycle-dir` → `no lifecycle dir`; `already-complete` → `already complete`; `advanced-complete` → `advanced → complete`; `advanced-crash-recovery` → `advanced → complete (crash recovery)`; `missing-review` → `missing review — expected review but none found`; `advance-refused` → `advance refused — no completion row written` (the feature is NOT complete; its `events.log` needs an operator). Anything else → `unrecognized state: {state}`, flagged — never read as success. Print a `Lifecycle updates:` summary.

## 3. Deferred questions

For each `deferred/{feature}-q*.md` (report order, then filename): show the feature and filename, the question (body or `question:`), what was tried, what is needed. Ask `Your answer (or "skip" to leave this question unanswered):`. On an answer append after existing content, touching nothing else:

```
## User Answer (YYYY-MM-DD)

{answer verbatim}
```

## 4. Failed features

For each: name, error summary, suggested next step. If the entry says `Feature is on the integration branch`, the work merged before a post-merge step failed — say so, point at `cortex/lifecycle/sessions/latest-overnight/overnight-events.log` for the failed step, and offer no ticket (it would duplicate landed work). Otherwise ask `Create a backlog investigation item for this failure? [yes / skip]`. On yes resolve the backend once with `cortex-read-backlog-backend`: `cortex-backlog` → `/backlog-author compose` from the failure (why = what failed observably, role = investigate root cause, integration = the feature, edges = non-goal: re-running the session), then `cortex-create-backlog-item --title "investigate <feature-slug>" --status should-have --type bug --body "<body>"`; `none` → one-line advisory, nothing written; external → file best-effort per `backlog.instructions`, surfacing the body if that fails.

## 5. Commit

Invoke `/commit` for the review's artifacts (completion rows in `events.log`, closed or archived tickets, the index). No extra confirmation — the review is authoritative.

## 6. PR merge

`integration_branch` missing from the state file → "No integration branch found — skipping PR step." Otherwise:

```
gh pr list --head {integration_branch} --state all --json number,url,state,title,isDraft
```

`--state all` is required — the default hides merged and closed PRs. Head names repeat across sessions: empty → "No PR found for `{integration_branch}`. The runner may have failed to create one. Use `/pr` to create it manually."; several → list them and stop, never pick one; `MERGED` → report the url and stop without claiming this session's work landed or touching tickets; `CLOSED` → report and stop.

Show the open PR (url, title, state) and `open {url} 2>/dev/null || true`. Draft (a zero-progress session) → GitHub blocks the merge; offer **mark ready and merge** (`gh pr ready {number}` then the merge below), **close** (`gh pr close {number}`, warning that the remote branch `{integration_branch}` and any worktree survive and need manual deletion), or **leave as draft**. Otherwise ask `Merge this PR to main? [yes / no]`.

Yes → `gh pr merge {number} --merge --delete-branch`. Success → "Merged. Remote branch deleted."; if the state file's `worktree_path` exists, `git worktree remove --force {worktree_path}` (report either outcome, never fail the review), and remove any demo worktree from 2a the same way. Failure → show the error, leave the PR open. No → "PR left open at {url} — merge manually when ready."

Sections 6a and 6b run only after a merge confirmed in this review.

## 6a. Post-merge sync

```
cortex-git-sync-rebase cortex_command/overnight/sync-allowlist.conf
```

Exit `0` → "Local main synced." `1` → rebase aborted (conflicts outside the allowlist or budget exhausted — stderr says which); resolve with `git pull --rebase origin main`. `2` → rebased but push failed; `git push origin main` when the network is back. `3` → behind-count unreadable, nothing touched; check `git log --oneline origin/main..main`. `4` → fetch failed (network/auth); nothing touched. Other → treat main as unsynced. Missing script → skip, note "install the `cortex-core` plugin". Continue to 6b regardless — closure is authorized by the merge, not the sync.

## 6b. Close tickets

Resolve the backend once with `cortex-read-backlog-backend`, then close every completed feature in one call:

```
cortex-morning-review-close-tickets --item {feature}={identifier} [--item ...] --backend {resolved-backend}
```

`{identifier}` is the zero-padded `backlog_id` from the state file (`078`), falling back to the lifecycle slug. Per-item `state`: `closed` → `closed #{id}` (`(parent epic also closed)` when `parent_closed`); `no-ticket` → `no ticket found`; `ambiguous` → show `message`'s candidates, ask for a disambiguated re-invoke; `skipped-disabled` → one-line advisory (`none` backend); `external` → make the equivalent close best-effort per `backlog.instructions`, surfacing it if it fails; `error` → `close failed: {message}`, continue. Print a `Ticket closure results:` summary.

Then push — until they reach main, a close reads `complete` only on this machine:

```
cortex-morning-review-push-closures --path {changed_path} [--path ...] --ticket {id} [--ticket ...]
```

`--path` takes every `changed_paths` entry of every `closed` item; `--ticket` every `closed` id whose `status_changed` is true (none → the verb commits nothing rather than pushing timestamp churn). `pushed` → `closures pushed to main ({commit})`; `no-op` → silent; `push-failed` → surface `message` and name `unpushed_tickets` as committed locally only — the review did not fully succeed; `error` → `push step failed: {message}`.

The review is complete.
