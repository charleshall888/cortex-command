# Plan: non-destructive-claude-md-strategy

## Overview

Creates two new rules files by extracting content from `claude/Agents.md`, trims the source file, and updates `deploy-config` + `check-symlinks` in the justfile to deploy via `~/.claude/rules/` instead of `~/.claude/CLAUDE.md`. All content changes, recipe changes, and docs ship in a single atomic commit. Post-commit: `skills/skill-creator/SKILL.md` and ticket 006 backlog item updated in a separate commit.

**Precondition**: Req 1 (live verification of `~/.claude/rules/` user-scope loading) must be completed by a human before this plan is executed. If Req 1 was not verified or failed, halt at the precondition check; do not execute Tasks 2–8. (Req 1 failure path: proceed with Tasks 2–4 only, skip Tasks 5–6, follow fallback documentation in Req 1 failure path from spec.)

---

## Tasks

### Task 1: Verify Req 1 completion and confirm execution path
- **Files**: `lifecycle/non-destructive-claude-md-strategy/events.log` (read only)
- **What**: Confirm the human has already run and recorded the live `~/.claude/rules/` verification test (Req 1) before any file is modified. Determine whether to proceed with the primary path (Tasks 2–8) or the fallback path.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Read `lifecycle/non-destructive-claude-md-strategy/events.log` and look for a pre-existing `req1_verified` event with `"result": "pass"`. This event must have been written by a human during a prior daytime verification session — the agent must NOT write it. If no such event exists in events.log, **halt immediately** and surface this message: "Req 1 has not been verified. Run the live verification test (see spec Req 1), then record the result by appending this event to events.log: `{\"ts\": \"<ISO 8601>\", \"event\": \"req1_verified\", \"feature\": \"non-destructive-claude-md-strategy\", \"result\": \"pass\"}`. Re-run the plan after recording." Do not proceed to Task 2.
- **Verification**: `events.log` already contains a `req1_verified` entry with `"result": "pass"` that precedes this plan execution. The agent did not create this entry.
- **Status**: [x] complete

### Task 2: Create `claude/rules/global-agent-rules.md`
- **Files**: `claude/rules/global-agent-rules.md` (create new)
- **What**: Extract the single-line `-m` example and the multi-`-m` flag pattern from `claude/Agents.md`'s "Git Commits" section into a new generic rules file.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Content comes from `claude/Agents.md` lines ~23-28 (the "Git Commits" section). Extract specifically:
  - The bullet: `- For single-line commits: git commit -m "Subject line here"`
  - The bullet + code block: `- For multi-line commits, use multiple -m flags...` with the accompanying fenced block
  File structure:
  - Scope-boundary comment at top: `<!-- Generic rules: safe to inject globally for any Claude Code user, regardless of cortex-command install state -->`
  - Section heading: `## Git Commit Format`
  - The two extracted bullets (single-line example, then multi-line example + code block)
  Deploy target: `~/.claude/rules/cortex-global.md` (symlink added in Task 5)
- **Verification**: `claude/rules/global-agent-rules.md` exists; contains both the single-line and multi-line commit format examples; begins with the scope-boundary comment; does not contain any reference to the `/commit` skill or cortex-command infrastructure.
- **Status**: [x] complete

### Task 3: Create `claude/rules/sandbox-behaviors.md`
- **Files**: `claude/rules/sandbox-behaviors.md` (create new)
- **What**: Extract the three sandbox-specific behavioral rules from `claude/Agents.md` into a new file: the "git -C" section, the "Compound Commands" section, and the heredoc warning bullet.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Content comes from `claude/Agents.md`:
  - Lines ~5-10: full "## Git Commands: Never Use `git -C`" section
  - Lines ~12-16: full "## Compound Commands: Avoid Chaining" section
  - Line ~22: the bullet `- Do NOT use $(cat <<'EOF' ... EOF) for commit messages -- it creates temp files that fail in sandboxed environments` (from the "Git Commits" section)
  File structure:
  - Scope-boundary comment at top: `<!-- Sandbox-specific behaviors: rules that apply when Claude Code runs in a sandboxed environment with Bash allow/deny rules -->`
  - Include the two full sections verbatim (with their headings)
  - Add a third section: `## Git Commits: Sandbox Constraints` containing only the heredoc warning bullet
  Deploy target: `~/.claude/rules/cortex-sandbox.md` (symlink added in Task 5)
- **Verification**: `claude/rules/sandbox-behaviors.md` exists; contains both full sections and the heredoc warning; begins with the scope-boundary comment; does not contain the single-line or multi-line `-m` examples (those are in global-agent-rules.md).
- **Status**: [x] complete

### Task 4: Trim `claude/Agents.md`
- **Files**: `claude/Agents.md` (modify)
- **What**: Remove the three bullets/sections that were extracted into the new files, leaving only the cortex-specific content.
- **Depends on**: [2, 3]
- **Complexity**: simple
- **Context**: `claude/Agents.md` is the live symlink target for the repo owner's `~/.claude/CLAUDE.md`. Modifying it creates a window where the live symlink points to a gutted file until Task 9 commits. **Recovery path if interrupted before Task 9**: run `git checkout -- claude/Agents.md` to restore the file to its last committed state. This is safe — the new rule files (Tasks 2–3) are separate files and are not affected by the restore. Keep Task 4 through Task 9 within the same session pass to minimise the degradation window; do not exit the session between Task 4 and Task 9.
  Remove from `claude/Agents.md`:
  - The full "## Git Commands: Never Use `git -C`" section (moved to sandbox-behaviors.md)
  - The full "## Compound Commands: Avoid Chaining" section (moved to sandbox-behaviors.md)
  - From "## Git Commits" section: the heredoc warning bullet, the single-line `-m` example bullet, and the multi-line `-m` example bullet + code block
  Retain in `claude/Agents.md` (keep exactly, do not reword):
  - Header: `# Global Agent Instructions` + preamble line
  - `## Git Commits: Always Use the `/commit` Skill` — header + two bullets: `/commit` skill invocation requirement and the GPG signing/validation reference
  - `## Settings Architecture` — full section
  - `## Conditional Loading` — full table + note
  After editing, verify that the three remaining sections are intact and no content was accidentally dropped.
- **Verification**: `claude/Agents.md` no longer contains "Never Use `git -C`", "Avoid Chaining", the heredoc warning, or the `-m` format examples. Still contains the `/commit` skill requirement, Settings Architecture, and Conditional Loading sections. Line count is noticeably reduced (was ~44 lines; after trim should be ~25 lines).
- **Status**: [x] complete

### Task 5: Update `deploy-config` in `justfile`
- **Files**: `justfile` (modify)
- **What**: Remove `~/.claude/CLAUDE.md` from the `deploy-config` recipe's target loop and add two new symlink deployments for the rules/ files.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: `deploy-config` recipe is at `justfile` lines 85–116. The `for target in` loop at line 90 currently lists three targets: `~/.claude/settings.json ~/.claude/CLAUDE.md ~/.claude/statusline.sh`. The `case` statement at lines 99-103 handles each target.
  Changes needed:
  1. Remove `~/.claude/CLAUDE.md` from the `for target in` loop (line 90)
  2. Remove the `*CLAUDE.md)` case (line 101) from the `case` statement
  3. After `mkdir -p ~/.claude` (line 88), add `mkdir -p ~/.claude/rules/`
  4. After the existing `for` loop's `done`, add a new loop for the two rules/ targets. Follow the same regular-file-check guard pattern (`[ -f "$target" ] && [ ! -L "$target" ]` → prompt → `ln -sf`) already used in the existing loop (lines 90-104). Add `case` branches mapping `*cortex-global.md)` to `$(pwd)/claude/rules/global-agent-rules.md` and `*cortex-sandbox.md)` to `$(pwd)/claude/rules/sandbox-behaviors.md`.
- **Verification**: `just deploy-config` runs without error; creates `~/.claude/rules/cortex-global.md` and `~/.claude/rules/cortex-sandbox.md` as symlinks; does NOT create or modify `~/.claude/CLAUDE.md` on a fresh machine. Confirm symlink targets: `readlink ~/.claude/rules/cortex-global.md` returns the absolute path to `claude/rules/global-agent-rules.md`; same for sandbox.
- **Status**: [x] complete

### Task 6: Update `check-symlinks` in `justfile`
- **Files**: `justfile` (modify)
- **What**: Replace the `~/.claude/CLAUDE.md` check with the two new rules/ symlink checks.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: `check-symlinks` recipe at `justfile` line 431+. Current line 445: `check ~/.claude/CLAUDE.md`. Replace this single line with two lines:
  ```
  check ~/.claude/rules/cortex-global.md
  check ~/.claude/rules/cortex-sandbox.md
  ```
- **Verification**: `just check-symlinks` exits 0 after running `just deploy-config`. Does not print a failure for `~/.claude/CLAUDE.md` being absent. Prints success for both rules/ symlinks.
- **Status**: [x] complete

### Task 7: Update `docs/setup.md`
- **Files**: `docs/setup.md` (modify)
- **What**: Update the Claude Code configuration section to reflect that `just setup` now deploys `~/.claude/rules/` files instead of `~/.claude/CLAUDE.md`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Find the section of `docs/setup.md` that describes `deploy-config` or lists `~/.claude/CLAUDE.md` as a deployment target. Update to:
  - State that `~/.claude/CLAUDE.md` is NOT deployed by the additive `just setup`
  - Describe the new rules/ deployment: two symlinks (`cortex-global.md` and `cortex-sandbox.md`) are created in `~/.claude/rules/`
  - Note that `~/.claude/CLAUDE.md` is only deployed by `just setup-force` (ticket 006, not yet available) for the repo owner
  If Req 1 verification failed and the fallback path is being taken: add a "Manual deployment (fallback)" section as specified in the Req 1 failure path (spec).
- **Verification**: `docs/setup.md` does not describe `just setup` as deploying `~/.claude/CLAUDE.md`. Mentions `~/.claude/rules/cortex-global.md` and `cortex-sandbox.md`.
- **Status**: [x] complete

### Task 8: Update `README.md` backup warning
- **Files**: `README.md` (modify)
- **What**: Revise the "Backup Warning" section (lines 86-95) to remove the description of `just setup` overwriting `~/.claude/CLAUDE.md`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `README.md` lines 86-95 contain a backup warning: "`just setup` creates symlinks that **replace** existing files in `~/.claude/`." The bulleted list includes `~/.claude/CLAUDE.md`. Update this section to reflect the non-destructive default: `just setup` no longer replaces `~/.claude/CLAUDE.md` — it creates new files in `~/.claude/rules/` only. The warning about `~/.claude/settings.json`, statusline.sh, skills, and hooks still applies. Note that only `just setup-force` will replace `~/.claude/CLAUDE.md` (when available in ticket 006).
- **Verification**: `README.md` backup warning section does not list `~/.claude/CLAUDE.md` as a file that `just setup` overwrites. `~/.claude/settings.json` and other files remain in the warning.
- **Status**: [x] complete

### Task 9: Atomic commit — content split, deploy, docs
- **Files**: `claude/Agents.md`, `claude/rules/global-agent-rules.md`, `claude/rules/sandbox-behaviors.md`, `justfile`, `docs/setup.md`, `README.md`
- **What**: Stage all changes from Tasks 2–8 and commit in a single atomic commit.
- **Depends on**: [2, 3, 4, 5, 6, 7, 8]
- **Complexity**: simple
- **Context**: Before committing, verify the split is complete:
  - `git diff --stat` should show changes to all 6 files listed
  - `git diff claude/Agents.md` should show only removals (no additions)
  - `claude/rules/global-agent-rules.md` and `claude/rules/sandbox-behaviors.md` should be new files
  - `git status` should show `claude/rules/` as a new directory with both files staged
  Commit message: `Split claude/Agents.md into three files and deploy via ~/.claude/rules/`
  Use `/commit` skill.
- **Verification**: Before staging: run `git check-ignore -v claude/rules/global-agent-rules.md claude/rules/sandbox-behaviors.md` — if either file is gitignored, fix the `.gitignore` before proceeding (do not use `git add -f`). After commit: `git log --oneline -1` shows one commit with all 6 files changed. `git show --stat HEAD` lists `claude/Agents.md`, both new files, `justfile`, `docs/setup.md`, `README.md` — verify all 6 are present. No earlier commit in the branch introduces a partial split.
- **Status**: [x] complete

### Task 10: Update `skills/skill-creator/SKILL.md`
- **Files**: `skills/skill-creator/SKILL.md` (modify)
- **What**: Replace the stale "Agents.md symlink pattern" at lines 221-227 with a description of the current three-file rules/ architecture.
- **Depends on**: [9]
- **Complexity**: simple
- **Context**: `skills/skill-creator/SKILL.md` lines 221-227:
  ```
  **The Agents.md symlink pattern for project instructions:**
  When a skill creates or references project instruction files, follow the `Agents.md` symlink pattern — write the canonical instructions once in `Agents.md`, then symlink for each agent:
  ln -s Agents.md CLAUDE.md
  ```
  Replace with a description of the current architecture: generic rules live in `claude/rules/global-agent-rules.md` and `claude/rules/sandbox-behaviors.md` (deployed to `~/.claude/rules/`); cortex-specific instructions live in `claude/Agents.md` (deployed to `~/.claude/CLAUDE.md` only for repo owners via `just setup-force`). A new contributor should use `claude/rules/` for content that applies globally, not a monolithic `Agents.md` → `~/.claude/CLAUDE.md` symlink.
- **Verification**: `skills/skill-creator/SKILL.md` no longer contains `ln -s Agents.md CLAUDE.md` or the old symlink pattern description. Contains a reference to the three-file architecture and `~/.claude/rules/`.
- **Status**: [x] complete

### Task 11: Update ticket 006 backlog item
- **Files**: `backlog/006-make-just-setup-additive.md` (modify)
- **What**: Add `~/.claude/rules/cortex-global.md` and `~/.claude/rules/cortex-sandbox.md` to ticket 006's collision detection targets, and note that `just setup-force` must deploy both rules/ symlinks AND `~/.claude/CLAUDE.md` → `claude/Agents.md`.
- **Depends on**: [9]
- **Complexity**: simple
- **Context**: `backlog/006-make-just-setup-additive.md` — find the Acceptance Criteria section. Add:
  - In the collision detection classifier list: `~/.claude/rules/cortex-global.md` and `~/.claude/rules/cortex-sandbox.md` as `new`/`update`/`conflict` classifiable targets
  - In the `just setup-force` requirements: "must deploy BOTH the rules/ symlinks (cortex-global.md and cortex-sandbox.md) AND `~/.claude/CLAUDE.md` → `claude/Agents.md` to give the repo owner the complete instruction set"
- **Verification**: `backlog/006-make-just-setup-additive.md` mentions the two new rules/ targets and the setup-force deploy requirement.
- **Status**: [x] complete

### Task 12: Commit tasks 10-11
- **Files**: `skills/skill-creator/SKILL.md`, `backlog/006-make-just-setup-additive.md`
- **What**: Commit the skill-creator docs update and ticket 006 backlog update together.
- **Depends on**: [10, 11]
- **Complexity**: simple
- **Context**: Separate from the main atomic commit (Task 9). Commit message: `Update skill-creator docs and ticket 006 for three-file rules architecture`
  Use `/commit` skill.
- **Verification**: `git log --oneline -2` shows two recent commits: the atomic main commit and this follow-up commit.
- **Status**: [x] complete

---

## Verification Strategy

After Task 9 commits:
1. Run `just deploy-config` — confirm `~/.claude/rules/cortex-global.md` and `~/.claude/rules/cortex-sandbox.md` are created as symlinks; confirm `~/.claude/CLAUDE.md` was not created or modified.
2. Run `just check-symlinks` — confirm exit 0 with no failures for the two new rules/ targets.
3. Human spot-check (Req 7): open a Claude Code CLI session in any project without a `.claude/CLAUDE.md`. Run `/context`. Confirm both `~/.claude/rules/cortex-global.md` and `~/.claude/rules/cortex-sandbox.md` appear in context output.
4. Verify `claude/Agents.md` still contains the `/commit` skill requirement, Settings Architecture, and Conditional Loading sections.
5. Verify the repo owner's existing `~/.claude/CLAUDE.md` (if present) still points to `claude/Agents.md` and loads the cortex-specific instructions.
