# Plan: Run /claude-api migrate to opus-4-7 on throwaway branch and report diff

## Overview

Create an isolated git worktree at a non-`.claude/` path, run Anthropic's `/claude-api migrate this project to claude-opus-4-7` inside it, capture the resulting diff, author and commit a report at `research/opus-4-7-harness-adaptation/claude-api-migrate-results.md`, then clean up the worktree and spike branch. 8 tasks, strictly sequential (no parallel opportunities).

## Tasks

### Task 1: Create spike worktree at $TMPDIR path

- **Files**: `$TMPDIR/cortex-command-083-spike/` (new worktree checkout); `.git/worktrees/cortex-command-083-spike/` (git metadata).
- **What**: Record main-repo HEAD SHA (baseline reference for the report). Create a worktree via `git worktree add -b spike/083-claude-api-migrate "$TMPDIR/cortex-command-083-spike" HEAD`. Confirm the worktree is outside the main repo's `.claude/` subtree.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Per spec R1, R2. Target path is `$TMPDIR/cortex-command-083-spike`. Fallback path if `$TMPDIR` unavailable: `../cortex-command-083-spike` (sibling of the main repo). `just deploy-*` recipes check `git rev-parse --git-dir != --git-common-dir` at `justfile:41-44, 125-129` and self-block from worktrees — no additional guardrail required.
- **Verification**: `git worktree list --porcelain | awk '/^worktree / {print $2}' | grep -c "cortex-command-083-spike"` equals `1`; AND `test -d "$TMPDIR/cortex-command-083-spike/skills/commit"` exits `0` (worktree checkout has the full tree). Pass if both hold.
- **Status**: [ ] pending

### Task 2: Pre-flight isolation check

- **Files**: none (read-only verification).
- **What**: Confirm `~/.claude/skills/commit` still targets `/Users/charlie.hall/Workspaces/cortex-command/skills/commit` (the main repo), not the spike checkout. Abort the spike if the global symlink already points elsewhere (indicates a prior setup-run pollution that must be remediated before proceeding).
- **Depends on**: [1]
- **Complexity**: trivial
- **Context**: Per spec R1 AC. The `readlink` output is deterministic; if it points at the spike checkout, do not proceed — surface the issue to the user before running migrate.
- **Verification**: `readlink ~/.claude/skills/commit | grep -c '^/Users/charlie.hall/Workspaces/cortex-command/skills/commit$'` equals `1`. Pass if equals `1`.
- **Status**: [ ] pending

### Task 3: Run /claude-api migrate inside the worktree

- **Files**: `$TMPDIR/cortex-command-083-spike/**` (migrate-command edits — file count and paths unknown until the run completes).
- **What**: Execute the `claude-api` skill's migrate function with explicit scope "this project" and target model `claude-opus-4-7`, with operating cwd set to the spike worktree. Capture the full transcript and any end-of-run checklist. Do not merge or commit changes on the spike branch.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**: Per spec R4, Edge Cases "Migrate asks for scope confirmation" (handled by explicit scope in invocation — docs at `platform.claude.com/docs/en/agents-and-tools/agent-skills/claude-api-skill#migrating-to-a-newer-claude-model`), "Migrate asks additional mid-run confirmations" (document in transcript; no scope changes). Two viable invocation paths for the implementer to choose from — both produce an equivalent diff in the worktree:
  - (a) `cd $TMPDIR/cortex-command-083-spike` via a Bash call, then invoke the skill directly in this session via the `Skill` tool with args `migrate this project to claude-opus-4-7`. Simpler; the skill's tool calls inherit the session's cwd.
  - (b) Dispatch a subagent via the `Agent` tool with the subagent's cwd set to the worktree and a prompt instructing it to run `/claude-api migrate this project to claude-opus-4-7` and return the transcript + any checklist. More isolated; depends on subagent Skill-tool access.
  Implementer resolves between (a) and (b) based on session state at run time; the spec requires only that edits land in the worktree, not a specific invocation path.
- **Verification**: Interactive/session-dependent — `/claude-api migrate` is an interactive Claude Code skill with variable tool-call length and no non-interactive entry point. Evidence is the post-run diff (captured in Task 4) and the transcript quoted in the report (Task 5).
- **Status**: [ ] pending

### Task 4: Capture diff to scratch

- **Files**: `$TMPDIR/083-migrate.diff` (new; scratch).
- **What**: Save `git diff HEAD` output from inside the worktree to `$TMPDIR/083-migrate.diff`. Captures all migrate-produced edits against the baseline recorded in Task 1.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Per spec R5. Use `git diff HEAD` (not `git diff main...HEAD` — the spike branch is uncommitted during Task 3, so HEAD-vs-worktree is the correct comparator). Zero-change case: file will be empty (0 bytes); downstream tasks handle this explicitly.
- **Verification**: `test -f "$TMPDIR/083-migrate.diff"` exits `0`; AND `wc -c < "$TMPDIR/083-migrate.diff"` is `>= 0` (accepts empty file for the zero-change case). Pass if file exists — content is evidentiary, not a gate.
- **Status**: [ ] pending

### Task 5: Author the report

- **Files**: `research/opus-4-7-harness-adaptation/claude-api-migrate-results.md` (new).
- **What**: Write the report with the exact section headings required by spec R6 AC: `## Files Touched`, `## Change Categories`, `## Usable As-Is For #085`, `## Tentative Mergeability`, `## End-of-run Checklist`. Include baseline SHA from Task 1, migrate invocation command, transcript-summary prose, and any end-of-run checklist items the skill emitted verbatim. Cite `research/opus-4-7-harness-adaptation/research.md` (the epic research) as the evidentiary anchor for the doc-based DR-7 prediction.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: Per spec R6. Section headings must match exactly (case-sensitive, no trailing whitespace) or the AC grep-count will fail. Zero-change case: `## Files Touched` section states "no files modified"; `## Change Categories` section notes "(none — migrate reported 0 edits)"; `## Usable As-Is For #085` records "confirms DR-7 docs-based prediction empirically"; `## Tentative Mergeability` records "N/A — no changes to merge"; `## End-of-run Checklist` reproduces whatever the skill emitted (or "(none emitted)"). Follow prose style of sibling `research/opus-4-7-harness-adaptation/research.md`.
- **Verification**: `grep -c -E '^## (Files Touched|Change Categories|Usable As-Is For #085|Tentative Mergeability|End-of-run Checklist)' research/opus-4-7-harness-adaptation/claude-api-migrate-results.md` equals `5`. Pass if equals `5`. (Per P7 operational test: self-check is benign — this task's purpose *is* to create the report.)
- **Status**: [ ] pending

### Task 6: Embed or attach diff

- **Files**: `research/opus-4-7-harness-adaptation/claude-api-migrate-results.md` (edit); optionally `research/opus-4-7-harness-adaptation/claude-api-migrate.diff` (new).
- **What**: If the diff captured in Task 4 is `<` 500 lines (via `wc -l < "$TMPDIR/083-migrate.diff"`), embed inline in the report as a fenced ```` ```diff ```` block. Otherwise, copy it to `research/opus-4-7-harness-adaptation/claude-api-migrate.diff` and reference that path from the report.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: Per spec R5 (two satisfaction paths) and spec Edge Cases "migrate produces zero changes" (inline the empty-diff note: `"(no changes — migrate reported 0 files modified)"` in a diff fence, no sibling file needed).
- **Verification**: `grep -c '^\`\`\`diff' research/opus-4-7-harness-adaptation/claude-api-migrate-results.md` is `>= 1` OR `test -f research/opus-4-7-harness-adaptation/claude-api-migrate.diff` exits `0`. Pass if either holds.
- **Status**: [ ] pending

### Task 7: Commit the report via /commit

- **Files**: a new commit on `main` touching `research/opus-4-7-harness-adaptation/claude-api-migrate-results.md` and (if created in Task 6) `research/opus-4-7-harness-adaptation/claude-api-migrate.diff`.
- **What**: Invoke the `/commit` skill to create a commit on main. Do not run `git commit` directly; do not amend.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: Per spec R6 + repo-level commit conventions (`CLAUDE.md`): imperative, capitalized, no trailing period, ≤72-char subject. Suggested subject: `Report /claude-api migrate results for #083`. Body may cite the epic research and #085 as the consumer.
- **Verification**: `git log --oneline -1 -- research/opus-4-7-harness-adaptation/claude-api-migrate-results.md | wc -l` equals `1`; AND `git log -1 --format=%s -- research/opus-4-7-harness-adaptation/claude-api-migrate-results.md | head -c 72 | wc -c` is `<= 72`. Pass if both hold.
- **Status**: [ ] pending

### Task 8: Cleanup spike worktree and branch

- **Files**: removes `$TMPDIR/cortex-command-083-spike/` (worktree directory) and `.git/worktrees/cortex-command-083-spike/` (git metadata); deletes `spike/083-claude-api-migrate` branch.
- **What**: Run `git worktree remove "$TMPDIR/cortex-command-083-spike"` (add `--force` if the worktree has unreported dirty state — expected, since migrate's changes were never committed on the spike branch). Then `git branch -D spike/083-claude-api-migrate`.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: Per spec R7. `git worktree remove --force` is required because migrate-produced changes on the spike branch are uncommitted; `remove` without `--force` refuses to discard uncommitted work. The intent here is to discard — the diff has already been captured to `$TMPDIR/083-migrate.diff` and the report is committed on main.
- **Verification**: `git worktree list --porcelain | grep -c 'spike/083-claude-api-migrate'` equals `0`; AND `git branch --list spike/083-claude-api-migrate | wc -l` equals `0`. Pass if both hold.
- **Status**: [ ] pending

## Verification Strategy

End-to-end success = (a) all 8 task-level verifications pass, and (b) spec R1–R7 ACs hold post-cleanup.

Consolidated post-cleanup check (single command block):

```
readlink ~/.claude/skills/commit | grep -c '^/Users/charlie.hall/Workspaces/cortex-command/skills/commit$'
test -f research/opus-4-7-harness-adaptation/claude-api-migrate-results.md
grep -c -E '^## (Files Touched|Change Categories|Usable As-Is For #085|Tentative Mergeability|End-of-run Checklist)' research/opus-4-7-harness-adaptation/claude-api-migrate-results.md
git log --oneline -1 -- research/opus-4-7-harness-adaptation/claude-api-migrate-results.md | wc -l
git worktree list --porcelain | grep -c 'spike/083-claude-api-migrate'
git branch --list spike/083-claude-api-migrate | wc -l
```

Expected: `1`, exit `0`, `5`, `1`, `0`, `0` respectively.

## Veto Surface

- **Task 3 invocation mechanism** (path (a) direct Skill call vs path (b) subagent). Both produce equivalent diffs; path (a) is simpler but shares cwd/permissions with this session. Implementer's call — user may prefer one explicitly.
- **Commit subject text**. Suggested: `Report /claude-api migrate results for #083`. User may prefer alternative phrasing at `/commit` time.
- **Dirty files in main repo at Task 1 time**. `git status` on main currently shows ~15 modified files and several untracked files. These do NOT affect the worktree baseline (worktree starts from the last commit, `HEAD`), but a reviewer comparing the report's baseline SHA against a later main-repo state may want to know which uncommitted edits existed. The report's baseline-SHA note addresses this.
- **Scope answer on migrate prompt** is "entire working directory" (per spec R4 Edge Cases, aligned with user's Spec-interview choice). If migrate's scope confirmation surfaces despite the explicit scope-in-invocation, answer the same.

## Scope Boundaries

Maps directly to spec's Non-Requirements:

- No merges from `spike/083-claude-api-migrate` to `main`. The spike branch is discarded in Task 8.
- No direct modification of #085's scope or plan.
- No rewrites of `.md` prompt files by this spike.
- No `just setup` / `just deploy-*` in the spike checkout.
- No modification of `~/.claude/*` during the spike.
- No commits on `main` other than the report file (+ optional `.diff` sibling).
- No overnight/batch execution — migrate is interactive by design.
