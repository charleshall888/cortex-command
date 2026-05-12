---
schema_version: "1"
uuid: ebdcac83-1152-4caa-9aae-7499771961c1
title: "Shared git index race between parallel Claude sessions causes wrong files to land in commits"
status: wontfix
priority: high
type: bug
created: 2026-04-22
updated: 2026-04-29
complexity: complex
criticality: high
---

## Problem

Multiple Claude Code sessions running `/commit` concurrently in the same git checkout can cause staged files to land in the wrong commit — the commit's subject line describes session A's intent while its diff contains session B's files.

Observed concretely on 2026-04-22 during lifecycle 127 completion:

- Session A (lifecycle 127, this session) staged 6 files via `git add <explicit paths>` for lifecycle 127 artifacts + requirements drift.
- Session A verified with `git diff --name-only --cached` that exactly the 6 expected files were staged.
- Session A ran the `/commit` skill, which composed a commit message "Land lifecycle 127 implement, review, and requirements drift".
- Commit `053ef22` landed with that subject line but the diff content is 2 files from a **different** lifecycle (#097: `remove-single-agent-worktree-dispatch-and-flip-recommended-default-to-current-branch`) — task checkbox flips and events.log entries. None of the 6 staged files from session A appeared in the commit; they were still modified/unstaged after the commit returned.
- Session A's files were then re-staged and committed cleanly as `c35355c`. Commit `053ef22` is now a permanent mismatch between subject and content.

Root cause hypothesis: the `/commit` skill's step 3 (stage) and step 5 (commit) are not atomic. A parallel `/commit` invocation can change the shared git index between these steps — either by running its own `git add` that replaces our staging, or by committing and consuming our staged files into a different commit message.

## Impact

- **Auditability**: commit subjects no longer reliably describe commit content. Log-scanning tools that attribute work based on `git log --oneline` messages are wrong.
- **Morning-report accuracy**: the overnight runner's morning report keys off commit subjects; the report will attribute the wrong work to the wrong session.
- **Overnight orchestrator correctness**: the orchestrator dispatches artifact commits from parallel sub-agents. If two sub-agents commit concurrently, the same race applies — worse, there's no human to notice and re-commit.
- **PR/review traceability**: PR descriptions generated from commit messages are wrong; reviewers get misleading context.
- **Non-deterministic**: the race is rare under low concurrency and catastrophic under high concurrency. Overnight sessions often commit many times per round.

## Proposed fix (candidates — spec phase will pick one)

1. **Advisory lock** on a dedicated file (e.g., `.git/claude-commit.lock`) acquired via `flock -n` before staging and released after committing. Enforced inside `/commit` skill and anywhere else the harness calls `git add` + `git commit`. Parallel sessions that don't honor the lock can still race — but if all harness entry points go through `/commit`, coverage is complete.
2. **Verify-before-commit**: `/commit` skill captures the expected staged-file list after its `git add` (step 3), then re-reads `git diff --name-only --cached` immediately before `git commit` (between steps 4 and 5). If the lists don't match, abort with a clear message and tell the user to re-stage. Catches the race but doesn't prevent it.
3. **Stage via index file isolation**: set `GIT_INDEX_FILE` to a session-scoped temporary index during stage+commit, then copy the resulting tree back. Heavy but fully race-free.
4. **Sequenced writes via the session's own index**: use `git commit-tree` directly on a constructed tree rather than going through the working-directory index at all.

Quickest path: #2 catches the bug, #1 prevents it. #2 + #1 together is belt-and-suspenders.

## Acceptance criteria

- Two parallel Claude sessions each running `/commit` in the same repo cannot produce a commit whose subject was composed by session A and whose content was staged by session B.
- A regression test that simulates concurrent staging (two `git add` calls interleaved with two `git commit` calls) and asserts each commit's content matches its message's author session.
- The overnight runner's artifact-commit path honors the chosen mitigation.

## Related

- Exposed during lifecycle 127 (`disambiguate-orchestrator-prompt-tokens-to-stop-lexical-priming-escape`) on 2026-04-22.
- Associated commits: `053ef22` (mislabeled — subject says 127 but content is #097), `c35355c` (the real 127 artifacts commit with an explanatory note in its body).

## Resolution: wontfix (2026-04-29)

Closed `wontfix` after running the value/complexity gate during refine. Rationale:

- **Value is small**. Bug observed once. Recoverable by re-staging and re-committing. Audit-trail mislabeling is real but has not been a pattern.
- **Lock-based fix is incomplete**. The chosen-and-rejected approach (Candidate 1, advisory `flock`) addresses only the **index** race. The pre-commit hook runs `just build-plugin`, which writes files into the **shared working tree** — two parallel sessions race on those writes regardless of any lock. Industry consensus across Cursor / Aider / Claude Code / Augment is per-agent worktree isolation, not locking.
- **Realistic complexity is much higher than the ticket suggests**. The research adversarial review surfaced lockfile-location, hook-side enforcement, `O_CLOEXEC`, NFS detection, head-of-line-blocking visibility, and ongoing per-caller upkeep. ~250 LOC plus tests, not the original "~50 LOC" framing.
- **The right architectural answer is daytime-worktree isolation** (extending the existing per-feature worktree pattern from overnight to interactive sessions), not locks. That is a separate, larger epic and is not pre-built for a once-observed bug.

**Research preserved** at `lifecycle/shared-git-index-race-between-parallel-claude-sessions-causes-wrong-files-to-land-in-commits/research.md`. Two latent fixes the research uncovered (`GIT_DIR` strip in `runner.py:_commit_followup_in_worktree`; `O_CLOEXEC` on `settings_merge.py` lockfile fd) and a worktree-parallelism guideline are filed as separate backlog items.
