# Specification: Foundation cleanup for /setup-merge hook discovery and REQUIRED/OPTIONAL reconciliation

> **Scope note**: This ticket was originally scoped as "per-component opt-in for skills and hooks" (see `research/user-configurable-setup/research.md` and the earlier version of this spec preserved in git history). During the spec phase, a cost/benefit review concluded that the full opt-in feature did not earn its complexity for a single-maintainer project where the maintainer built the skills and primarily uses them. The per-component opt-in work is deferred indefinitely. This ticket ships only the latent bug fixes the adversarial research pass surfaced — changes that are load-bearing regardless of whether opt-in is ever built. The deferred opt-in feature can reuse this foundation if revisited.

## Problem Statement

Two latent bugs exist in the `/setup-merge` / `merge_settings.py` pipeline that should be fixed regardless of whether per-component opt-in is ever built:

1. **`discover_symlinks` walks `hooks/cortex-*` but not `claude/hooks/cortex-*`**, so 7 hooks (including Band C `cortex-sync-permissions.py`) are invisible to `/setup-merge`'s conflict detection and merge logic. `deploy-hooks` in the justfile walks both directories correctly, so `just setup` itself symlinks everything — but when `/setup-merge` runs conflict resolution, it operates on an incomplete inventory, potentially missing conflicts and producing misleading status reports.

2. **`REQUIRED_HOOK_SCRIPTS` / `OPTIONAL_HOOK_SCRIPTS` in `merge_settings.py` diverge from what's actually wired in `claude/settings.json`:**
   - `cortex-output-filter.sh` is wired unconditionally in `PreToolUse[Bash]` (L267-269) but is in **neither** `REQUIRED_HOOK_SCRIPTS` nor `OPTIONAL_HOOK_SCRIPTS`. It's invisible to `/setup-merge`'s merge logic entirely.
   - `cortex-setup-gpg-sandbox-home.sh` is wired unconditionally in `SessionStart` (L239) but sits in `OPTIONAL_HOOK_SCRIPTS` and is prompted as optional. If the user says "n," their next session hits a blocking SessionStart hook pointing at a missing file.
   - `cortex-notify.sh` is wired unconditionally in `Notification` and `Stop` (as `~/.claude/notify.sh`, L279, L297) but sits in `OPTIONAL_HOOK_SCRIPTS`. Same footgun.
   - `cortex-notify-remote.sh` is wired unconditionally in `Notification` and `Stop` (L283, L301) but sits in `OPTIONAL_HOOK_SCRIPTS`. Same footgun.

After the reconciliation, `OPTIONAL_HOOK_SCRIPTS` becomes empty (every currently-declared "optional" hook is actually unconditionally wired) and the `/setup-merge` prompt step that iterates over it becomes dead code. The cleanup also deletes that step.

The beneficiary is the maintainer: fewer latent footguns, a merge_settings.py that matches reality, and a `/setup-merge` prompt flow without dead branches.

## Requirements

**MoSCoW classification**: All 3 requirements are must-have. R1 is a pure coverage fix; R2 is the constant reconciliation that makes the truthful set match reality; R3 is the dead-code removal that follows from R2.

### R1 — Extend `discover_symlinks` to walk `claude/hooks/cortex-*`

In `.claude/skills/setup-merge/scripts/merge_settings.py` the `discover_symlinks()` function (L94-185) currently has one hooks-directory walk at L141-158 that globs `hooks/cortex-*`. Extend it with a parallel walk of `claude/hooks/cortex-*` using the same target mapping logic (target is `home / ".claude" / "hooks" / item.name`, same `ln_flag: "-sf"`, same `classify()` call). Non-hook files in `claude/hooks/` (`bell.ps1`, `output-filters.conf`, `setup-github-pat.sh`) are excluded naturally by the `cortex-*` prefix glob. The hardcoded special case for `cortex-notify.sh → ~/.claude/notify.sh` (L148-150) only applies to `hooks/`; the `claude/hooks/` walk does not need the special case (no `cortex-notify.sh` lives there).

Add a comment above the extended walk: "Hooks live in two directories — `hooks/` (shared cortex-command hooks) and `claude/hooks/` (repo-specific hooks including worktree, output filter, sync-permissions). Both are walked. A hook is any file matching `cortex-*` in either directory, regardless of extension — `cortex-sync-permissions.py` is a Python file, everything else is shell."

**Acceptance criteria**:
- `python3 .claude/skills/setup-merge/scripts/merge_settings.py detect --repo-root "$(pwd)"` output (via parsing the tempfile path returned on stdout) contains entries for every file in `claude/hooks/cortex-*`, pass if `jq -r '.symlink_entries[].source' <detect_output> | grep -c 'claude/hooks/cortex-'` returns at least 7 (the 7 cortex-prefixed files in `claude/hooks/`: `cortex-output-filter.sh`, `cortex-permission-audit-log.sh`, `cortex-setup-gpg-sandbox-home.sh`, `cortex-skill-edit-advisor.sh`, `cortex-sync-permissions.py`, `cortex-tool-failure-tracker.sh`, `cortex-worktree-create.sh`, `cortex-worktree-remove.sh`). Note: that's actually 8 — including the one that's a `.py`.
- The same output does NOT include `bell.ps1`, `output-filters.conf`, or `setup-github-pat.sh`, pass if `jq -r '.symlink_entries[].source' <detect_output> | grep -Ec 'bell.ps1|output-filters.conf|setup-github-pat'` returns 0.

### R2 — Reconcile `REQUIRED_HOOK_SCRIPTS` / `OPTIONAL_HOOK_SCRIPTS` with `claude/settings.json` wiring

In `.claude/skills/setup-merge/scripts/merge_settings.py` (L14-32), reshape the two constants to match every hook that is actually referenced in `claude/settings.json`'s hooks block:

**New `REQUIRED_HOOK_SCRIPTS`** (13 entries — every hook wired in `claude/settings.json`):
- `cortex-sync-permissions.py` (SessionStart — already in REQUIRED)
- `cortex-scan-lifecycle.sh` (SessionStart — already in REQUIRED)
- `cortex-setup-gpg-sandbox-home.sh` (SessionStart — **moved from OPTIONAL**)
- `cortex-cleanup-session.sh` (SessionEnd — already in REQUIRED)
- `cortex-validate-commit.sh` (PreToolUse[Bash] — already in REQUIRED)
- `cortex-output-filter.sh` (PreToolUse[Bash] — **added, was missing from both sets**)
- `cortex-notify.sh` (Notification/Stop via `~/.claude/notify.sh` — **moved from OPTIONAL**)
- `cortex-notify-remote.sh` (Notification/Stop — **moved from OPTIONAL**)
- `cortex-permission-audit-log.sh` (Notification — already in REQUIRED)
- `cortex-tool-failure-tracker.sh` (PostToolUse[Bash] — already in REQUIRED)
- `cortex-skill-edit-advisor.sh` (PostToolUse[Write|Edit] — already in REQUIRED)
- `cortex-worktree-create.sh` (WorktreeCreate via `$CWD` — already in REQUIRED; see Technical Constraints)
- `cortex-worktree-remove.sh` (WorktreeRemove via `$CWD` — already in REQUIRED; see Technical Constraints)

**`OPTIONAL_HOOK_SCRIPTS`**: deleted. After the reshape, every wired hook is required; there are no truly optional hooks to prompt for individually. The concept is gone from the module.

Add a comment above `REQUIRED_HOOK_SCRIPTS` explaining the invariant: "Every hook referenced in `claude/settings.json`'s hooks block must appear in this set. If you add or remove a hook in settings.json, update this set in the same commit. Verified by R12 integration test [NOTE: no integration test in this ticket; verify manually]. Mismatch produces latent bugs — hooks invisible to the merge logic, or prompts asking the user about a hook that cannot actually be disabled."

**Acceptance criteria**:
- `REQUIRED_HOOK_SCRIPTS` contains exactly 13 entries and equals the set enumerated above, pass if `python3 -c "import sys; sys.path.insert(0, '.claude/skills/setup-merge/scripts'); from merge_settings import REQUIRED_HOOK_SCRIPTS; print(sorted(REQUIRED_HOOK_SCRIPTS))"` outputs the sorted list of the 13 names.
- `OPTIONAL_HOOK_SCRIPTS` is deleted, pass if `grep -c 'OPTIONAL_HOOK_SCRIPTS' .claude/skills/setup-merge/scripts/merge_settings.py` returns 0.
- Manual verification: `python3 .claude/skills/setup-merge/scripts/merge_settings.py detect --repo-root "$(pwd)"` surfaces every hook in the new REQUIRED set as part of the detect output's hook discovery.
- Every hook command string in `claude/settings.json`'s hooks block corresponds to a basename in `REQUIRED_HOOK_SCRIPTS` (after resolving `~/.claude/notify.sh` → `cortex-notify.sh` via the known symlink mapping), pass if an ad-hoc audit script walks the settings.json hooks block, extracts basenames, and confirms every extracted basename is in the set.

### R3 — Remove dead OPTIONAL hook prompt step from `/setup-merge` SKILL.md

After R2 deletes `OPTIONAL_HOOK_SCRIPTS`, the `/setup-merge` SKILL.md step that prompts the user individually for optional hooks becomes dead code. Remove it. The simplified flow has one hook-related step: "merge all REQUIRED_HOOK_SCRIPTS entries unconditionally." Update any references in the SKILL.md that describe the optional-hook prompt as a user-facing step.

**Acceptance criteria**:
- `grep -c 'optional hook' .claude/skills/setup-merge/SKILL.md` returns 0 after the edit (or any residual references are in a comment explaining the deletion, not a user-visible prompt step), pass if the grep count is 0 or the remaining matches are only in commented-out context.
- `grep -c 'OPTIONAL_HOOK_SCRIPTS' .claude/skills/setup-merge/SKILL.md` returns 0.
- Running `/setup-merge` manually against a fresh clone produces zero "[Y/n]" prompts for individual hooks (all hooks are merged silently as part of the required set), pass if visual inspection of the prompt flow confirms no per-hook Y/n prompts appear.

## Non-Requirements

- **Per-component opt-in for skills or hooks**: deferred indefinitely. The original ticket scope; see the scope note at the top of this spec. If revisited, this foundation cleanup is a prerequisite.
- **`lifecycle.config.md` schema changes**: no new top-level `skills:` or `hooks:` sections. No frontmatter writes from `/setup-merge`.
- **`test -f` guards on hook commands**: not needed because every wired hook is required and always deployed; there is no "opted-out hook" state to guard against.
- **`install-floor: true` frontmatter migration** on SKILL.md files or hook header comments: no code reads the markers in this ticket, so adding them now is dead documentation.
- **Derived allowlist file** (`~/.claude/.cortex-bin-allowlist`): no per-skill opt-out means no need to gate bin utilities. `deploy-bin` stays unchanged.
- **`deploy-bin` changes**: the recipe stays exactly as it is today.
- **Cluster headers in prompts**: no per-component prompt flow, so no cluster UX.
- **`CLAUDE_CONFIG_DIR` honoring**: `merge_settings.py` continues to hardcode `Path.home() / ".claude"`. Users with `CLAUDE_CONFIG_DIR` set will find hooks at `~/.claude` as before. Follow-up alongside ticket #065 if ever needed.
- **`derive_wired_hook_scripts()` runtime helper**: not introduced. `REQUIRED_HOOK_SCRIPTS` stays a hand-maintained constant.
- **Integration test harness for `/setup-merge`**: not introduced. A 3-requirement bugfix does not justify building sandboxed `TEST_CLAUDE_HOME` infrastructure from scratch. Manual verification per R1/R2/R3 acceptance criteria is sufficient. A proper test harness can land with the opt-in work when/if it happens.
- **`lifecycle.config.md` template update**: no schema changes, so no template examples to add.
- **Committed `claude/settings.json` changes**: the settings.json file is unchanged by this ticket. R2 reconciles the Python constants TO match settings.json, not the other way around. (Exception: if R3's dead-code removal reveals any stale hook command in settings.json, flag it to the user — but baseline assumption is the settings.json is already correct.)
- **Worktree hook `$CWD` pattern fix**: out of scope. Worktree hooks stay in `REQUIRED_HOOK_SCRIPTS` and their settings.json commands remain unchanged.
- **`setup-force` reconciliation**: out of scope. `setup-force` remains as-is.

## Edge Cases

- **Fresh clone running `just setup`**: unaffected. `deploy-hooks` already walks both `hooks/` and `claude/hooks/` correctly, so every hook is symlinked regardless of what `merge_settings.py` knew.
- **Existing install running `/setup-merge` after this ticket lands**: the new REQUIRED_HOOK_SCRIPTS set covers every hook already in the user's `~/.claude/settings.json`. `discover_symlinks` now sees `claude/hooks/cortex-*`, so any conflict that was previously invisible is now surfaced. If the user's `~/.claude/hooks/` already has the 7 claude/hooks/cortex-* files symlinked (from a prior `just setup` run), the new detect run sees them as `update` status; if not, they show as `new` and get symlinked.
- **User says "n" to a prompt that no longer exists**: not applicable after R3 — there is no optional-hook prompt step to answer.
- **Hook added to `claude/settings.json` but not to `REQUIRED_HOOK_SCRIPTS`**: caught during manual verification per R2 acceptance criterion 4. No automated CI check is added in this ticket. The invariant comment in R2 warns future maintainers.
- **Hook removed from `claude/settings.json` but not from `REQUIRED_HOOK_SCRIPTS`**: surfaces as a stale entry at the next `/setup-merge` run — `merge_settings.py` will look for a file that's no longer wired. The merge logic tolerates this (the hook file itself may still exist in the repo and still be a valid symlink target), but the intent mismatch should be fixed by the maintainer. Same manual-verification expectation.
- **A `.py` hook is added to `hooks/` or `claude/hooks/`**: the `cortex-*` prefix glob in R1 catches it regardless of extension, so the discovery walk surfaces it correctly.
- **A shell script without the `cortex-*` prefix is added to `hooks/` or `claude/hooks/`**: silently excluded by the glob. Intentional — non-`cortex-*` files are treated as non-hooks by convention.

## Changes to Existing Behavior

- **MODIFIED — `discover_symlinks()` in `merge_settings.py`**: now walks both `hooks/cortex-*` and `claude/hooks/cortex-*`. Previously, `claude/hooks/cortex-*` (8 files including Band C `cortex-sync-permissions.py`) were invisible to `/setup-merge`'s conflict detection.
- **MODIFIED — `REQUIRED_HOOK_SCRIPTS` constant**: expanded from 9 entries to 13 by moving all 3 `OPTIONAL_HOOK_SCRIPTS` entries into REQUIRED and adding the missing `cortex-output-filter.sh`.
- **REMOVED — `OPTIONAL_HOOK_SCRIPTS` constant**: deleted. The concept is gone from `merge_settings.py`.
- **REMOVED — optional-hook prompt step in `/setup-merge` SKILL.md**: the individual-prompt loop for optional hooks is deleted. All hook-related behavior is "merge the required set, done."

## Technical Constraints

- **Worktree hook `$CWD` pattern**: the worktree hooks (`cortex-worktree-create.sh`, `cortex-worktree-remove.sh`) are registered in `claude/settings.json` with a `$CWD`-relative command (`bash -c '... [ -f "$CWD/claude/hooks/cortex-worktree-create.sh" ] && ...'`). The commands already contain an inline `[ -f ]` guard that is unrelated to this ticket — it's for working-directory-relative resolution, not symlink guarding. The ticket does not touch the worktree hook commands. Worktree hooks remain in `REQUIRED_HOOK_SCRIPTS` because they ARE wired in settings.json and their source files must be symlinked to `~/.claude/hooks/` by the merge logic even though the settings.json commands use a different path base. This is a pre-existing design wart and stays out of scope.
- **Defense-in-depth for permissions** (from `requirements/project.md`): `cortex-sync-permissions.py` stays in `REQUIRED_HOOK_SCRIPTS` unconditionally. This hook merges global permissions into project `.claude/settings.local.json` and is load-bearing for the sandbox-excluded-commands enforcement layer.
- **No YAML parser added**: this ticket does not introduce PyYAML or any other YAML parsing dependency. All changes are to Python constants and prompt-flow markdown.
- **File-based state** (from `requirements/project.md`): no new files or state surfaces are introduced.
- **Manual verification is the test plan**: this ticket does not add an integration test harness. The 3 requirements are small and testable by running `/setup-merge` once against a clean clone and inspecting the output. Building a sandboxed test infrastructure for this ticket alone would violate the project's "complexity must earn its place" principle.
- **Landing order**: R1, R2, R3 should all land in the same commit. Splitting would create a mid-flight state where (a) after R1 only, the discovery walks claude/hooks/ but R2's constant still doesn't know about `cortex-output-filter.sh`, leaving it discovered-but-unmerged; (b) after R1 + R2 only, OPTIONAL_HOOK_SCRIPTS is empty but the prompt step still tries to iterate over it (no-op at runtime, dead code); (c) after R1 + R3 only, prompt step is gone but R2 hasn't fixed the actual invariant. Single commit.
