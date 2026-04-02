# Review: non-destructive-claude-md-strategy

## Stage 1: Spec Compliance

### Req 1: Verify `~/.claude/rules/` user-scope loading
- **Expected**: Verification confirms `~/.claude/rules/test.md` loads globally. Recorded as `req1_verified` event in events.log with `"result": "pass"`.
- **Actual**: `events.log` line 11 contains `{"event": "req1_verified", "result": "pass"}` with timestamp `2026-04-02T16:00:00Z`. Human-verified prior to implementation as noted in the spec.
- **Verdict**: PASS

### Req 2: Three-way content split of `claude/Agents.md`
- **Expected**: Both new files exist at `claude/rules/`. `claude/Agents.md` no longer contains the moved sections/bullets. Each file begins with a scope-boundary comment. The union of all content across three files equals the original `claude/Agents.md` content.
- **Actual**: Both `claude/rules/global-agent-rules.md` and `claude/rules/sandbox-behaviors.md` exist. Content split verified against the pre-split `Agents.md` (commit `6ee14b7`):
  - `global-agent-rules.md`: Contains the single-line `git commit -m` example and multi-`-m` flag pattern. Has scope-boundary comment on line 1.
  - `sandbox-behaviors.md`: Contains full "Git Commands: Never Use `git -C`" section, full "Compound Commands: Avoid Chaining" section, and the heredoc warning bullet (under new "Git Commits: Sandbox Constraints" header). Has scope-boundary comment on line 1.
  - `Agents.md` (trimmed): Retains "Git Commits: Always Use the `/commit` Skill" header with invocation requirement and GPG signing ref (minus moved bullets), "Settings Architecture" (full), and "Conditional Loading" (full). No moved sections remain.
  - Content union: Every bullet in the original is present in exactly one of the three files. No content lost, no content duplicated.
  - **Deficiency**: `claude/Agents.md` does not begin with a scope-boundary comment. The spec says "Each file begins with a one-line comment stating its scope boundary." The two new files comply; the trimmed `Agents.md` does not. Its role as the cortex-specific, repo-owner-only instruction file is not explicitly stated.
- **Verdict**: PARTIAL
- **Notes**: Missing scope-boundary comment on `claude/Agents.md`. The two new files have comments; the trimmed remnant does not.

### Req 3: `deploy-config` recipe updated
- **Expected**: Remove `~/.claude/CLAUDE.md` from the loop; add `mkdir -p ~/.claude/rules/`; add two new symlink deployments with regular-file-check warning guard.
- **Actual**: `justfile` `deploy-config` recipe (lines 84-118):
  - `~/.claude/CLAUDE.md` removed from the `for target in ...` loop (lines 91-104 now only contain `settings.json` and `statusline.sh`).
  - `mkdir -p ~/.claude/rules/` added at line 89.
  - Two new symlink deployments at lines 105-118 with the same regular-file-check warning guard pattern: `cortex-global.md` -> `global-agent-rules.md`, `cortex-sandbox.md` -> `sandbox-behaviors.md`.
  - Recipe is idempotent (re-running recreates symlinks safely via `ln -sf`).
- **Verdict**: PASS

### Req 4: `check-symlinks` recipe updated
- **Expected**: Remove `check ~/.claude/CLAUDE.md`; add checks for both rules symlinks.
- **Actual**: `check-symlinks` recipe (lines 445-491) includes `check ~/.claude/rules/cortex-global.md` (line 459) and `check ~/.claude/rules/cortex-sandbox.md` (line 460). No `check ~/.claude/CLAUDE.md` present anywhere in the recipe.
- **Verdict**: PASS

### Req 5: Atomicity -- split and deploy in a single commit
- **Expected**: Req 2, Req 3, Req 4, and Req 6 must ship in one commit containing `claude/Agents.md`, both new files, `justfile`, and doc files.
- **Actual**: Commit `2244d4a` ("Split claude/Agents.md into three files and deploy via ~/.claude/rules/") contains exactly 6 files: `README.md`, `claude/Agents.md`, `claude/rules/global-agent-rules.md`, `claude/rules/sandbox-behaviors.md`, `docs/setup.md`, `justfile`. No earlier commit contains a partial split.
- **Verdict**: PASS

### Req 6: Documentation updated
- **Expected**: `docs/setup.md` updated to reflect `rules/` deployment, not `~/.claude/CLAUDE.md`. `README.md` backup warning no longer describes `~/.claude/CLAUDE.md` being overwritten.
- **Actual**:
  - `docs/setup.md`: The "Full Setup (macOS)" code block now shows `mkdir -p ~/.claude/rules` and two `ln -sf` commands for `cortex-global.md` and `cortex-sandbox.md`. The old `ln -sf ... ~/.claude/CLAUDE.md` line is removed. Comments explain the non-destructive approach and reference ticket 006.
  - `README.md`: `~/.claude/CLAUDE.md` removed from the backup list. New paragraph added: `just setup` does **not** create or modify `~/.claude/CLAUDE.md` -- it creates new files in `~/.claude/rules/` only. Only `just setup-force` (future release) will deploy `~/.claude/CLAUDE.md`.
- **Verdict**: PASS

### Req 7: Human spot-check after deployment
- **Expected**: Out of scope for this review -- requires interactive session.
- **Actual**: Not evaluated.
- **Verdict**: PASS (not applicable to this review)

### Req 8: `skills/skill-creator/SKILL.md` updated
- **Expected**: Replace old Agents.md symlink pattern with three-file architecture description.
- **Actual**: Lines 221-229 of `skills/skill-creator/SKILL.md` now contain "The three-file rules architecture for agent instructions" section describing all three files, their content scope, and their deployment targets. The old single-file Agents.md pattern is replaced.
- **Verdict**: PASS

### Req 9: Ticket 006 updated
- **Expected**: Add `rules/` targets to collision detection; note `setup-force` must deploy both `rules/` AND `CLAUDE.md`.
- **Actual**: `backlog/006-make-just-setup-additive.md` acceptance criteria (lines 49-51) now include:
  - `just setup-force` must deploy BOTH `rules/` symlinks AND `~/.claude/CLAUDE.md` -> `claude/Agents.md`
  - Collision detection classifier covers `~/.claude/rules/cortex-global.md` and `~/.claude/rules/cortex-sandbox.md`
- **Verdict**: PASS

## Requirements Compliance

- **Complexity must earn its place**: The three-way split is justified by the problem statement (separating generic rules from sandbox rules from cortex-specific content). No speculative abstractions introduced. The `deploy-config` recipe reuses the existing regular-file guard pattern rather than inventing new machinery.
- **File-based state**: All artifacts are plain files (markdown, JSON logs). No new state mechanisms.
- **Graceful partial failure / Maintainability through simplicity**: The deploy recipe handles each rules symlink independently with the same guard pattern as existing targets. `check-symlinks` additions follow the established pattern exactly.
- **Quality bar**: Implementation matches spec. The one gap (missing scope-boundary comment on `Agents.md`) is cosmetic and does not affect functionality.

## Stage 2: Code Quality

- **Naming conventions**: `cortex-global.md` and `cortex-sandbox.md` follow the existing `cortex-*` prefix convention used by hooks (`cortex-validate-commit.sh`, `cortex-scan-lifecycle.sh`, etc.). Source file names (`global-agent-rules.md`, `sandbox-behaviors.md`) are descriptive and consistent with the repo's naming style.
- **Error handling**: The regular-file-check warning guard on the new rules symlinks mirrors the existing guard on `settings.json` and `statusline.sh`. Appropriate for the context -- warns before overwriting user files, skips on decline.
- **Test coverage**: Req 1 was human-verified and logged. `check-symlinks` provides deployment verification. No automated tests were added, but the changes are configuration/deployment rather than logic -- the existing `check-symlinks` and `verify-setup` recipes serve as the test harness.
- **Pattern consistency**: The new `deploy-config` loop for rules files exactly mirrors the existing loop structure. The `check-symlinks` additions follow the same `check` function pattern. The scope-boundary comments in the new files follow a consistent format. Documentation updates are thorough and match the existing writing style.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["Req 2 PARTIAL: claude/Agents.md is missing a scope-boundary comment (the two new files have them, but the spec says 'Each file begins with a one-line comment stating its scope boundary' which applies to all three)"]}
```
