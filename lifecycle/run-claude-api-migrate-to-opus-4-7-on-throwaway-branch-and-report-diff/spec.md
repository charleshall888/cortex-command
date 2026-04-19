# Specification: Run /claude-api migrate to opus-4-7 on throwaway branch and report diff

> Epic reference: `research/opus-4-7-harness-adaptation/research.md` (DR-7, Open Question 1).

## Problem Statement

Before ticket #085 hand-edits cortex-command's prompt surface (SKILL.md files + reference docs) for Claude Opus 4.7, confirm empirically what Anthropic's built-in `/claude-api migrate this project to claude-opus-4-7` automation actually changes on this codebase. Research established with HIGH confidence from Anthropic's published docs that the command targets SDK call sites and excludes markdown files (`rg --type-not md` in its file-discovery heuristic). This spike runs the command on an isolated checkout, produces a committed catalog of the resulting diff, and delivers a tentative mergeability assessment for #085 — closing Epic Open Question 1.

## Requirements

All R1–R7 are must-have for the spike to be considered complete. Won't-do items are in Non-Requirements; fallback paths for individual requirements are in Edge Cases.

1. **Isolated execution — no propagation to live global agent environment**: the migrate command runs in a checkout physically decoupled from the main repo working tree, so writes produced during the run do not reach the paths targeted by `~/.claude/*` symlinks.
   - **AC**: After the spike completes (before cleanup), `readlink ~/.claude/skills/commit` outputs `/Users/charlie.hall/Workspaces/cortex-command/skills/commit` (main repo path, unchanged). Pass if `readlink ~/.claude/skills/commit | grep -c '^/Users/charlie.hall/Workspaces/cortex-command/skills/commit$'` equals `1`.

2. **Worktree at a non-`.claude/` path**: created via `git worktree add -b spike/083-claude-api-migrate <target-path> HEAD` where `<target-path>` is outside `/Users/charlie.hall/Workspaces/cortex-command/.claude/` (e.g., `$TMPDIR/cortex-command-083-spike` or a sibling directory like `../cortex-command-083-spike`).
   - **AC**: `git worktree list --porcelain | awk '/^worktree / {print $2}' | grep -c '^/Users/charlie.hall/Workspaces/cortex-command/\.claude/'` returns no match for the spike worktree path (checked while the worktree exists). Pass if the spike worktree line's path does not begin with the main repo's `.claude/` subtree.

3. **No `just setup` or `just deploy-*` in the spike checkout**: the global symlinks must continue targeting the main repo throughout the spike.
   - **AC**: Interactive/session-dependent — `just setup` is a destructive reconfiguration action that would rewrite `~/.claude/*` symlinks to target the spike checkout; the only verification is to not invoke it. Post-hoc confirmation is via R1's `readlink` check.

4. **Interactive migrate run**: `/claude-api migrate this project to claude-opus-4-7` executed in an interactive Claude Code session with cwd set to the spike checkout. The scope-confirmation prompt (documented behavior) is answered "entire working directory" to preserve the as-ticketed framing.
   - **AC**: Interactive/session-dependent — `/claude-api migrate` is an interactive Claude Code slash command; no CLI or non-interactive entry exists. Evidence is captured via the migrate transcript, referenced from the report.

5. **Diff captured in full**: working-tree changes produced by the migrate command are recorded either as an inline fenced ```` ```diff ```` block in the report or as a sibling file `research/opus-4-7-harness-adaptation/claude-api-migrate.diff`.
   - **AC (inline)**: `grep -c '^\`\`\`diff' research/opus-4-7-harness-adaptation/claude-api-migrate-results.md` is `>= 1`. **AC (sibling)**: `test -f research/opus-4-7-harness-adaptation/claude-api-migrate.diff` exits `0`. Pass if either holds. When migrate produces zero changes, the diff stub is `"(no changes — migrate reported 0 files modified)"` and the report's Change Categories section notes this explicitly.

6. **Report committed at the exact deliverable path, with the required sections**: `research/opus-4-7-harness-adaptation/claude-api-migrate-results.md`, committed to `main` via the `/commit` skill.
   - **AC**: `test -f research/opus-4-7-harness-adaptation/claude-api-migrate-results.md` exits `0`; AND `grep -c -E '^## (Files Touched|Change Categories|Usable As-Is For #085|Tentative Mergeability|End-of-run Checklist)' research/opus-4-7-harness-adaptation/claude-api-migrate-results.md` equals `5`; AND `git log --oneline -- research/opus-4-7-harness-adaptation/claude-api-migrate-results.md | wc -l` is `>= 1`.

7. **Cleanup — spike worktree and branch removed**: after the report is committed on `main`, the worktree is removed and the spike branch is deleted.
   - **AC**: `git worktree list --porcelain | grep -c 'spike/083-claude-api-migrate'` equals `0`; AND `git branch --list spike/083-claude-api-migrate | wc -l` equals `0`.

## Non-Requirements

- **No merges from `spike/083-claude-api-migrate` to `main`**. Cherry-picks, rebases, and merges of the migrate output are explicitly out of scope — #085's Plan phase decides adoption.
- **No direct modification of #085's scope or plan**. The mergeability appendix is a tentative advisory produced while context is loaded; binding decisions belong to #085.
- **No rewrites of `.md` prompt files by this spike**. Per Anthropic docs, `/claude-api migrate` excludes markdown; if the empirical run contradicts this, the report flags it but does not itself edit `.md` files.
- **No `just setup` / `just deploy-*` in the spike checkout**, and no other invocation that could retarget `~/.claude/*` symlinks.
- **No modification of `~/.claude/` paths during the spike**, including `~/.claude/skills/*`, `~/.claude/settings.json`, `~/.claude/CLAUDE.md`, `~/.claude/reference/*`, `~/.claude/hooks/*`, `~/.claude/notify.sh`, `~/.claude/statusline.sh`, `~/.claude/rules/*`.
- **No commits on `main` other than the report file** (and standard lifecycle-managed backlog state updates via `update-item`).
- **Overnight/batch execution is out of scope**. `/claude-api migrate` is interactive by design; the spike is a daytime task.

## Edge Cases

- **Migrate produces zero changes**: report explicitly states this, includes a zero-diff receipt, and closes the "usable for #085" question with "confirms docs-based prediction — no SKILL.md edits attempted, no SDK call sites to update beyond X files." The spike is still complete and commits the report per R6.
- **Migrate produces a change set that touches `.md` files** (contradicts HIGH-confidence docs prediction): report's "Files Touched" section flags the contradiction prominently, quotes the docs passage (`--type-not md` exclusion, "does not modify documentation"), records the actual modifications verbatim, and surfaces the tension in the "Tentative Mergeability" appendix for #085 to resolve. Does not self-revert; the commit captures the evidence.
- **Migrate asks for scope confirmation** (expected per Anthropic docs): response is "entire working directory" to preserve the as-ticketed framing (per user's Spec-interview choice of "Run empirically as-ticketed" over "Narrow to SDK-only scope").
- **Migrate asks additional mid-run confirmations**: document each in the transcript and the report; do not improvise scope changes.
- **`git worktree add` fails** (e.g., path exists, disk space): fallback is `git clone /Users/charlie.hall/Workspaces/cortex-command $TMPDIR/cortex-command-083-spike` with the same "no `just setup`" guardrail. `git diff` capture then uses the clone's local history against the baseline commit SHA noted at step 1.
- **Migrate's end-of-run checklist flags manual items** (expected — docs say it produces one for integration tests / length-control tuning / cost re-baselining): reproduce the checklist verbatim in the report's `## End-of-run Checklist` section so #085 can re-validate.
- **Interactive session stalls or times out mid-run**: abort via `git worktree remove --force` and the fallback-clone path; the spike is retry-safe.

## Changes to Existing Behavior

- **ADDED**: `research/opus-4-7-harness-adaptation/claude-api-migrate-results.md` — new research artifact consumed by #085's scope decision.
- **ADDED** (transient): `spike/083-claude-api-migrate` branch and a worktree on it — both removed during R7 cleanup.

## Technical Constraints

- **Symlink architecture** (verified by inode inspection in research; authoritative statement in repo-root `CLAUDE.md`): `~/.claude/{skills,hooks,reference,notify.sh,statusline.sh,settings.json,CLAUDE.md,rules}` are symlinks into `/Users/charlie.hall/Workspaces/cortex-command/{skills,hooks,claude/reference,hooks/cortex-notify.sh,claude/statusline.sh,claude/settings.json,claude/Agents.md,claude/rules}` respectively. Writes to those main-repo paths propagate to the live global agent environment immediately.
- **`just setup` self-blocks from worktrees** (`justfile:41-44, 125-129` — every `deploy-*` recipe checks `git rev-parse --git-dir != --git-common-dir`), but does NOT self-block from clones. A worktree is self-enforcing against accidental setup runs; a clone is not.
- **`/claude-api migrate` is interactive** — documented at `platform.claude.com/docs/en/agents-and-tools/agent-skills/claude-api-skill#migrating-to-a-newer-claude-model`; prompts for scope confirmation before editing.
- **Most probable edit targets in this repo** (per Anthropic docs' auto-activation heuristic — SDK imports): `claude/pipeline/dispatch.py` (contains the model-selection matrix in code per `requirements/multi-agent.md:51-62`), `claude/sdk/*` if present, `claude/dashboard/*.py`, the overnight runner.
- **Backlog state lifecycle-managed** via `update-item` (repo-root `CLAUDE.md`). The spike does not set `status`/`session_id`/`lifecycle_phase` directly; the Complete phase closes them.
- **Commit convention**: use `/commit` skill; messages are imperative, capitalized, no trailing period, ≤72-char subject. Multi-line messages use multiple `-m` flags (sandbox-compatible). Do not use heredocs.

## Open Decisions

(None — resolved during Spec interview. See `events.log` for the spec-interview Q&A outcomes.)
