# Specification: Non-destructive CLAUDE.md strategy

> **Implementation note**: Req 1 is a human-only interactive step that cannot be automated. This ticket is not suitable for fully unattended overnight execution. Intended execution flow: (1) human runs Req 1 during a daytime session; (2) if verification passes, remaining Reqs (2–8) can run overnight; (3) human spot-checks Req 7 after deployment.

## Problem Statement

`just setup` currently replaces `~/.claude/CLAUDE.md` with a symlink to `claude/Agents.md`, destroying any global agent instructions a new user already has. The fix is to inject cortex-command's instructions via `~/.claude/rules/` symlinks — a user-scope directory that Claude Code loads automatically for all projects — without touching `~/.claude/CLAUDE.md` at all. `claude/Agents.md` must also be refactored: it currently conflates sandbox-specific behavioral rules and cortex-command-specific install-dependent instructions into one file, making the categories indistinguishable for new users who should only receive the sandbox rules.

The beneficiary is any new user who clones or forks cortex-command. After this change, `just setup` enriches their environment without clobbering it.

---

## Requirements

**[Must] Req 1 — Verify `~/.claude/rules/` user-scope loading** *(Human-only: requires interactive Claude Code session)*

Before any file split or recipe change is committed, run the live verification test:
1. Create `~/.claude/rules/test.md` with a distinctive, unique instruction (e.g., "Whenever asked to count to 3, respond with VERIFICATION-SUCCESS instead")
2. Open a Claude Code CLI session in a project that has no `.claude/CLAUDE.md` and no project-scope rules
3. Confirm the instruction is active via `/context` output showing the file is loaded, or via behavioral observation
4. Delete the test file

*Acceptance criteria*: Verification confirms `~/.claude/rules/test.md` loads globally in the Claude Code CLI. If verification passes, proceed to Req 2. **If verification fails**, proceed to the Req 1 failure path below — do not proceed to Req 3 or Req 4.

*Req 1 failure path*: If `~/.claude/rules/` does not load at user scope:
1. Still execute Req 2 (the file split is valid regardless of deployment strategy).
2. **Halt Reqs 3 and 4** (do not update `deploy-config` or `check-symlinks`).
3. Add a "Manual deployment (fallback)" section to `docs/setup.md` documenting the manual symlink commands: `mkdir -p ~/.claude/rules && ln -sf $(pwd)/claude/rules/global-agent-rules.md ~/.claude/rules/cortex-global.md && ln -sf $(pwd)/claude/rules/sandbox-behaviors.md ~/.claude/rules/cortex-sandbox.md`
4. Note that if `~/.claude/rules/` does not load even after manual symlink creation, the `@import` fallback has a known regression bug (issue #8765 for `@~/.claude/` paths, NOT_PLANNED). Open a follow-up issue to track resolution.
5. *Failure path AC*: `docs/setup.md` contains a "Manual deployment (fallback)" section with the above commands; Reqs 3 and 4 are not implemented; Req 2 is complete.

**[Must] Req 2 — Three-way content split of `claude/Agents.md`**
Split `claude/Agents.md` content into three files. Each file begins with a one-line comment stating its scope boundary.

| Target file | Content from `claude/Agents.md` | Deployed to |
|---|---|---|
| `claude/rules/global-agent-rules.md` | From "Git Commits" section: single-line `git commit -m` example; multi-`-m` flag pattern for multi-line commits (both currently in the "Git Commits: Always Use the `/commit` Skill" section) | `~/.claude/rules/cortex-global.md` |
| `claude/rules/sandbox-behaviors.md` | "Git Commands: Never Use `git -C`" section (full); "Compound Commands: Avoid Chaining" section (full); the `$(cat <<'EOF')` heredoc warning bullet from the "Git Commits" section | `~/.claude/rules/cortex-sandbox.md` |
| `claude/Agents.md` (trimmed) | "Git Commits: Always Use the `/commit` Skill" — header line + `/commit` invocation requirement + GPG signing reference (minus the moved heredoc warning and minus the moved `-m` examples); "Settings Architecture" section (full); "Conditional Loading" section (full) | `~/.claude/CLAUDE.md` (repo owner only, via future `just setup-force`) |

*Acceptance criteria*: Both new files exist at `claude/rules/`. `claude/Agents.md` no longer contains the sections and bullets moved to the other two files. Each file begins with a scope-boundary comment. The union of all content across three files equals the original `claude/Agents.md` content — every bullet, example, and section appears in exactly one output file.

**[Must] Req 3 — `deploy-config` recipe updated** *(only if Req 1 passes)*
The `deploy-config` justfile recipe (lines 85–116) must be modified:
- Remove `~/.claude/CLAUDE.md` from the `for target in ...` loop and the `*CLAUDE.md)` case
- Add `mkdir -p ~/.claude/rules/` before the new rules deployments
- Add two new symlink deployments using `ln -sf` (with the same regular-file-check warning guard already used for other targets):
  - `~/.claude/rules/cortex-global.md` → `$(pwd)/claude/rules/global-agent-rules.md`
  - `~/.claude/rules/cortex-sandbox.md` → `$(pwd)/claude/rules/sandbox-behaviors.md`

*Acceptance criteria*: After running `just deploy-config` on a fresh machine: `~/.claude/rules/cortex-global.md` and `~/.claude/rules/cortex-sandbox.md` exist as symlinks pointing to the repo's source files. `~/.claude/CLAUDE.md` is not created or modified. Re-running `just deploy-config` is idempotent (`ln -sf`).

**[Must] Req 4 — `check-symlinks` recipe updated** *(only if Req 1 passes)*
In the `check-symlinks` justfile recipe:
- Remove the `check ~/.claude/CLAUDE.md` line
- Add `check ~/.claude/rules/cortex-global.md` and `check ~/.claude/rules/cortex-sandbox.md`

*Acceptance criteria*: `just check-symlinks` exits 0 for a fresh install that ran `just deploy-config` post-split. The recipe does not check for or fail on the absence of `~/.claude/CLAUDE.md`.

**[Must] Req 5 — Atomicity: split and deploy in a single commit** *(only if Req 1 passes)*
Req 2 (content split), Req 3 (`deploy-config` update), Req 4 (`check-symlinks` update), and Req 6 (docs) must ship in a single commit. The rules/ symlinks must never be deployed pointing to the wrong file.

*Acceptance criteria*: Git log shows one commit containing changes to `claude/Agents.md`, both new files at `claude/rules/`, `justfile`, and documentation files. No earlier commit in the PR contains a partial split.

**[Must] Req 6 — Documentation updated**
- `docs/setup.md`: update to reflect that `just setup` deploys rules/ files, not `~/.claude/CLAUDE.md`
- `README.md`: remove or revise the backup warning section (lines 86–95) that describes `~/.claude/CLAUDE.md` being overwritten

*Acceptance criteria*: Neither `docs/setup.md` nor `README.md` describes the additive `just setup` as deploying `~/.claude/CLAUDE.md`.

**[Must] Req 7 — Cortex-command instructions active after install** *(Human spot-check after deployment)*

After running `just setup` on a machine with no prior cortex-command install, both rules files are active in all Claude Code CLI sessions.

*Acceptance criteria*: A human opens a Claude Code CLI session in any project (including one with no `.claude/CLAUDE.md`) and runs `/context` — both `~/.claude/rules/cortex-global.md` and `~/.claude/rules/cortex-sandbox.md` appear in the context output.

**[Should] Req 8 — `skills/skill-creator/SKILL.md` updated if stale**
If `skills/skill-creator/SKILL.md` references the old pattern of deploying global agent instructions via `claude/Agents.md` → `~/.claude/CLAUDE.md`, update to describe the new three-file rules/ architecture.

*Acceptance criteria*: `skills/skill-creator/SKILL.md` does not describe the additive install path as deploying `~/.claude/CLAUDE.md`.

**[Should] Req 9 — Ticket 006 updated for new deployment targets**
After this ticket ships: update `backlog/006-make-just-setup-additive.md` acceptance criteria to:
- Add `~/.claude/rules/cortex-global.md` and `~/.claude/rules/cortex-sandbox.md` as classifiable targets in ticket 006's collision detection classifier
- Note that `just setup-force` (ticket 006's deliverable) must deploy BOTH the rules/ symlinks AND `~/.claude/CLAUDE.md` → `claude/Agents.md` for the repo owner's complete instruction set

*Acceptance criteria*: Ticket 006 backlog item updated before this lifecycle is closed.

---

## Non-Requirements

- **No `@import` injection code**: The fallback path (if Req 1 verification fails) is documented manual symlink steps only, not implemented code. The `@~/.claude/` import path has a known NOT_PLANNED regression (issue #8765).
- **No commit message format conventions added**: The commit format rules (imperative mood, 72 chars, etc.) live in `CLAUDE.md` (project-level), not `claude/Agents.md`. They are out of scope for this split. `global-agent-rules.md` contains only the `-m` flag syntax examples extracted from the existing `/commit` skill section.
- **No hook file renaming**: Ticket 004's scope.
- **No `settings.json` merge logic**: Ticket 007's scope.
- **No skill directory symlink fix**: GitHub #14836, explicitly deferred.
- **No VSCode extension support**: Issue #13914, out of scope.
- **No `just setup-force` implementation**: Ticket 006's scope. This ticket only removes CLAUDE.md from the additive path.
- **No content additions**: The split is a reorganization of content that already exists in `claude/Agents.md`. Every bullet in `global-agent-rules.md` and `sandbox-behaviors.md` must trace directly to a line in the current `claude/Agents.md`.

---

## Edge Cases

- **DR-4 live verification fails**: Follow the Req 1 failure path — execute Req 2 (file split), skip Reqs 3 and 4, add manual deployment docs. Do not attempt @import injection if `~/.claude/rules/` is unconfirmed.

- **User already has `~/.claude/rules/` with their own files**: `ln -sf` for the two new symlinks only creates/overwrites those specific filenames. Existing files in `~/.claude/rules/` are not touched.

- **User already has `~/.claude/rules/cortex-global.md` or `cortex-sandbox.md` as regular files**: The existing regular-file-check guard in `deploy-config` (`[ -f "$target" ] && [ ! -L "$target" ]`) will prompt before overwriting. Same behavior as `settings.json` and `statusline.sh`.

- **Repo owner upgrading (CLAUDE.md symlink exists from before)**: Running `just deploy-config` post-split does not remove the existing `~/.claude/CLAUDE.md` symlink. It remains pointing to `claude/Agents.md` (now the trimmed cortex-specific file). The repo owner also gains the two new rules/ symlinks. All three instruction sets are active — this is the correct state for the repo owner until `just setup-force` (ticket 006) formalizes this.

- **Clean repo-owner install post-005 pre-006**: On a brand-new machine after ticket 005 ships but before ticket 006 delivers `just setup-force`, the repo owner running `just setup` gets the rules/ files but not `~/.claude/CLAUDE.md`. The Conditional Loading table and Settings Architecture section are not deployed. This is an acknowledged temporary gap; ticket 006 closes it.

- **`claude/Agents.md` modified before commit (live symlink degradation)**: The repo owner's `~/.claude/CLAUDE.md` symlinks to `claude/Agents.md`. Modifying the file before committing degrades live instructions. Mitigation: see Technical Constraints (write new files first, modify `claude/Agents.md` last).

- **`claude/rules/` directory not yet tracked by git**: New directory. Must be added via `git add claude/rules/` and verified not gitignored before committing.

---

## Technical Constraints

- **Req 1 is human-only and must precede all code changes**: The live verification test requires opening an interactive Claude Code CLI session. This cannot be automated. Complete and confirm Req 1 before writing any files.

- **Write new files before modifying `claude/Agents.md`**: The existing `claude/Agents.md` is the live symlink target for the repo owner's `~/.claude/CLAUDE.md`. To minimize the window of degraded live instructions, create `claude/rules/global-agent-rules.md` and `claude/rules/sandbox-behaviors.md` first, then trim `claude/Agents.md` in the same editing pass immediately before committing.

- **`ln -sf` is the established symlink pattern**: All rules/ deployments follow the same pattern as existing `deploy-config` symlinks.

- **`mkdir -p ~/.claude/rules/` is required** before the first `ln -sf` for rules/ targets. The directory does not exist on new machines.

- **The regular-file-check guard** (`[ -f "$target" ] && [ ! -L "$target" ]`) must wrap the new rules/ symlink deployments, matching the pattern used for `settings.json` and `statusline.sh`.

- **`check-symlinks` hardcodes expected paths**: New deployment targets must be added to `check-symlinks` in the same commit as `deploy-config`.

- **`claude/rules/` must be tracked by git**: New directory and files must be committed. Verify no `.gitignore` rule matches `claude/rules/` before the atomic commit.

- **`@~/.claude/` import paths are unreliable**: GitHub issue #8765 (NOT_PLANNED). Any fallback documentation must reference manual symlink creation, not `@import` syntax pointing into `~/.claude/`.
