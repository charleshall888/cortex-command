# Specification: investigate-overnight-morning-review-git-sync-gaps

## Problem Statement

After overnight sessions, local `main` accumulates unpushed commits (artifact recording in `runner.sh` lines 984–1000 and morning report in lines 1206–1211). When morning review merges the overnight PR via `gh pr merge`, remote `main` advances with feature work while local `main` has divergent artifact commits. This forces manual `git pull --rebase` with merge conflicts in generated lifecycle files (`lifecycle/*/plan.md`). The morning review workflow should be "strategic review, not debugging sessions" (per `requirements/project.md`), but the current git state management undermines this.

## Requirements

1. **Move artifact recording to integration branch**: The runner.sh Phase D artifact commit (lines 984–1000) must commit to the integration branch worktree instead of local `main`. This requires coordinated changes beyond the `cd` line: (a) the session artifact copy block (lines 974–977) must copy to the worktree path, not `$REPO_ROOT`; (b) the backlog write-back path resolution in `batch_runner.py` (`_PROJECT_ROOT` at line 1071) must be updated or the backlog files must be explicitly copied to the worktree before the commit; (c) `pipeline-events.log` write path must target the worktree. Acceptance criteria: after an overnight session completes, `git log main..overnight/{session_id} --oneline` includes the artifact commit; `git log --oneline -1 main` does NOT show an artifact commit from the current session. Interactive/session-dependent: requires running an overnight session to verify.

2. **Keep morning report on main**: The runner.sh Phase F morning report commit (lines 1206–1211) stays on local `main`. Acceptance criteria: after runner.sh completes, `git log --oneline -1 main` shows the morning report commit. No change from current behavior — this requirement documents the deliberate decision.

3. **Add post-PR-merge sync to morning review**: After `gh pr merge` succeeds in Step 6 (walkthrough.md Section 6), morning review must sync local `main` with remote. The sync step runs: `git fetch origin`, `git pull --rebase origin main`, then `git push origin main`. Acceptance criteria: after the sync step completes, `git rev-list HEAD..origin/main --count` outputs `0` and `git rev-list origin/main..HEAD --count` outputs `0` (local and remote are identical). Interactive/session-dependent: requires a merged PR to verify.

4. **Pattern-based auto-resolve allowlist**: A shared configuration file defines glob patterns for files that are safe to auto-resolve with `--theirs` (remote version wins) during the post-merge rebase. Acceptance criteria: `test -f claude/overnight/sync-allowlist.conf` exits 0; the file contains glob patterns, one per line, with comments supported via `#`.

5. **Selective conflict resolution during post-merge sync**: When `git pull --rebase origin main` produces conflicts, the sync step must run a **multi-pass resolution loop** (one pass per commit being replayed): (a) identify conflicted files via `git diff --name-only --diff-filter=U`; (b) auto-resolve files matching the allowlist using `git checkout --theirs`; (c) for non-allowlist files, check if git can resolve them automatically; (d) if unresolved non-allowlist conflicts remain or the situation is complex (>3 conflicted non-allowlist files), `git rebase --abort` and surface the conflicts to the user; (e) if all conflicts resolved, `git add` resolved files and `git rebase --continue`; (f) if `--continue` triggers another conflict on the next commit, re-enter the loop from (a). Acceptance criteria: Interactive/session-dependent: requires actual conflicts to verify resolution behavior.

6. **Update morning review success message**: After PR merge and successful sync (including push), the message "Merged — main is now up to date" (walkthrough.md line 301) becomes accurate. Acceptance criteria: `grep -c "up to date" skills/morning-review/references/walkthrough.md` = 1; the message is only shown after sync succeeds.

7. **Restructure pre-runner batch spec commit**: The overnight skill's Step 4 batch spec extraction commit (SKILL.md line 204) must commit to the integration branch worktree instead of local `main`, or the step must be reordered so the commit happens before worktree creation (making the specs available on the integration branch via the shared ancestor). Acceptance criteria: after `/overnight` completes Step 4, `git log --oneline -1 main` does NOT show a batch spec extraction commit from the current session.

8. **Dirty rebase state guard**: Before attempting the post-merge sync, check for `.git/rebase-merge/` or `.git/rebase-apply/` directories. If present, run `git rebase --abort`, warn the user that a stale rebase state was cleaned up, and then proceed with the sync. Acceptance criteria: `test -d .git/rebase-merge || test -d .git/rebase-apply` after cleanup exits non-zero (directories removed).

## Non-Requirements

- **Push local main from runner.sh**: The runner does NOT push local `main` at any point. Artifact commits move to the integration branch; morning report is the only local-only commit. The push happens in morning review's post-merge sync step, not in runner.sh.
- **Retry consolidation**: Not addressed — moving artifacts to the integration branch eliminates retry accumulation on local `main` as a concern.
- **Multiple overnight sessions before morning review**: Out of scope for this spike. The post-merge sync handles one PR merge at a time.
- **Cross-repo session changes**: The cross-repo artifact recording and morning report logic (lines 1214–1249) is not modified. Cross-repo sessions have a separate target integration worktree that already commits morning reports there.
- **Conflict auto-resolution for user-authored content**: The allowlist only covers generated/managed files. User-authored content is never silently overwritten.

## Edge Cases

- **Integration worktree file layout divergence**: The worktree branches off `main` at session start. Files written directly to `$REPO_ROOT` by runner.sh or batch_runner.py (session artifacts, backlog modifications, pipeline-events.log) do NOT exist in the worktree — they must have their write paths updated or be explicitly copied to the worktree before the artifact commit. The `2>/dev/null || true` error suppression pattern must NOT be relied on for this migration — it would silently drop files. The artifact commit should fail loudly if expected files are missing.
- **Post-merge rebase with zero conflicts**: The most common case — `git pull --rebase origin main` succeeds cleanly because artifacts now travel with the PR. The sync step should handle this as a fast path.
- **Post-merge rebase with only allowlist conflicts**: All conflicted files match the allowlist. Auto-resolve with `--theirs`, continue rebase, and report success.
- **Post-merge rebase with mixed conflicts**: Some files match the allowlist, others don't. Auto-resolve allowlist files, then check if remaining conflicts can be resolved by git. If not, abort and surface to user.
- **Post-merge rebase fails completely (not just conflicts)**: Network error, detached HEAD, or corrupted state. Abort, surface the error, and leave the user to resolve manually.
- **Remote main diverged independently**: Someone pushed to remote `main` during the overnight session (e.g., manual hotfix). The post-merge sync handles this via standard rebase — local commits rebase on top of both the PR merge and the independent push.
- **Two local-only commits to rebase**: After artifact migration, there are at least two local-only commits: the morning report (from runner.sh Phase F) and the morning review artifacts (from Step 5 — events.log, backlog changes). The multi-pass resolution loop (Req 5) handles sequential conflicts from replaying each commit.
- **backlog/ conflicts during post-merge rebase**: The overnight PR modifies `backlog/index.md` and `backlog/archive/` (feature completion updates). The Step 5 review-artifacts commit also modifies backlog files. This is a common conflict source. `backlog/index.md` and `backlog/archive/` should be included in the allowlist since the overnight version (from the merged PR) is authoritative for feature status updates, and the morning review regenerates the index after sync.
- **`gh pr merge` fails**: No sync step runs. This is existing behavior — the walkthrough already handles this case (line 339).
- **Allowlist file missing or empty**: If `claude/overnight/sync-allowlist.conf` doesn't exist or is empty, treat all conflicts as non-allowlist — no auto-resolve, full user-facing conflict handling.
- **Dirty rebase state from prior crash**: If `.git/rebase-merge/` or `.git/rebase-apply/` exists from a prior failed sync or interrupted session, the guard (Req 8) aborts it before attempting the new sync.
- **Push fails after successful rebase**: If `git push origin main` fails (network error, remote rejection), surface the error but do not undo the rebase — local main is in a good state, just not pushed yet.

## Changes to Existing Behavior

- MODIFIED: `runner.sh` Phase D artifact commit (lines 984–1000) — changes `cd "$REPO_ROOT"` to `cd "$WORKTREE_PATH"`, AND updates copy targets (lines 974–977) to write to the worktree, AND ensures backlog/pipeline-events paths resolve to the worktree
- MODIFIED: `batch_runner.py` `_write_back_to_backlog()` — path resolution must target the worktree during overnight sessions, or backlog files must be copied to the worktree before the artifact commit
- MODIFIED: `skills/overnight/SKILL.md` Step 4 — batch spec extraction commit must target the integration branch worktree instead of local `main`, or be reordered before worktree creation
- ADDED: Post-PR-merge sync step in `skills/morning-review/references/walkthrough.md` Section 6 — after `gh pr merge` succeeds, runs `git fetch origin` + `git pull --rebase origin main` + selective conflict resolution + `git push origin main`
- ADDED: `claude/overnight/sync-allowlist.conf` — shared pattern-based allowlist file for auto-resolvable files
- ADDED: Sync resolution logic — a shared shell script that reads the allowlist and applies multi-pass `--theirs` resolution during rebase conflicts
- ADDED: Dirty rebase state guard — detects and cleans up stale `.git/rebase-merge/` or `.git/rebase-apply/` before sync
- MODIFIED: Morning review success message in walkthrough.md — now only displayed after sync (including push) succeeds

## Technical Constraints

- **Worktree path variable**: `$WORKTREE_PATH` is set at runner.sh line 249 and available in scope for Phase D. The migration requires changes beyond the `cd` line — session artifact copy targets (lines 974–977), backlog write-back path resolution in `batch_runner.py`, and `pipeline-events.log` write path must all be updated to target the worktree.
- **File origin distinction**: Files in the artifact commit come from two sources: (a) files created by feature branches that merge into the integration branch (lifecycle/*/research.md, spec.md, plan.md, agent-activity.jsonl) — these already exist in the worktree; (b) files written directly to `$REPO_ROOT` by runner.sh or batch_runner.py (session artifacts, backlog modifications, pipeline-events.log) — these must have their write paths changed or be copied to the worktree. The `2>/dev/null || true` error suppression must be replaced with explicit checks for category (b) files to prevent silent data loss.
- **Multi-pass rebase resolution**: During `git pull --rebase`, each replayed commit can produce its own conflict set. The resolution script must loop: identify conflicts, resolve allowlist matches, check non-allowlist conflicts, `git rebase --continue`, and re-enter if the next commit also conflicts. `git rebase --abort` at any point discards ALL progress including previously-resolved commits.
- **Morning review runs on main**: The morning review skill assumes it's on the `main` branch (SKILL.md line 112). The post-merge sync must also run on `main`.
- **Sandbox constraints**: The post-merge sync runs within a Claude Code sandbox session. Git operations are allowed per the sandbox config, but the resolution script must not require interactive input.
- **`--merge` strategy dependency**: The post-merge sync's `--theirs` semantics during rebase depend on the PR being merged with `gh pr merge --merge` (not `--squash` or `--rebase`). The `--merge` flag creates a merge commit that preserves integration branch file content. If the merge strategy were changed, the `--theirs` resolution would need re-evaluation. This is a load-bearing coupling.

## Open Decisions

- **Batch spec extraction reordering vs. worktree commit**: The pre-runner commit (overnight SKILL.md Step 4) could either be reordered before worktree creation (so the integration branch inherits it from main HEAD) or redirected to commit in the worktree after creation. The choice depends on whether `extract_batch_specs()` modifies files that must exist in the worktree's `lifecycle/` directories — requires reading the function to determine. Deferred: implementation-level code inspection needed.
- **Backlog write-back path strategy**: The `_write_back_to_backlog()` function in `batch_runner.py` resolves paths via `_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent`. Options: (a) pass the worktree path as a parameter so writes target the worktree directly; (b) keep writes to `$REPO_ROOT` and copy the modified files to the worktree before the artifact commit. Deferred: implementation-level code inspection needed to assess the change scope of each approach.
