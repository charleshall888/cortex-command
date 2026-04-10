# Specification: Remove interpreter escape hatch commands

## Problem Statement

Six interpreter entries in the global `claude/settings.json` allow list (`bash *`, `sh *`, `source *`, `python *`, `python3 *`, `node *`) create a confirmed permission bypass where deny rules are not evaluated through interpreter wrappers. Spike 055 demonstrated that `bash -c "git push --force origin main"` auto-allows via `Bash(bash *)` without triggering the `Bash(git push --force *)` deny rule. For sandbox-excluded commands like git, this means zero protection layers. Removing these entries and adding targeted replacements closes the bypass while preserving all legitimate interactive workflows.

## Requirements

1. **Remove 6 interpreter entries from allow list**: Remove `Bash(bash *)`, `Bash(sh *)`, `Bash(source *)`, `Bash(python *)`, `Bash(python3 *)`, `Bash(node *)` from `claude/settings.json` `permissions.allow`. Acceptance criteria: `grep -c 'Bash(bash \*)' claude/settings.json` = 0, and same for all 6 patterns.

2. **Add 4 replacement patterns to allow list**: Add `Bash(python3 -m claude.*)`, `Bash(python3 -m json.tool *)`, `Bash(uv run *)`, `Bash(uv sync *)` to `claude/settings.json` `permissions.allow`, positioned near the remaining language runtime entries. Acceptance criteria: `grep -c 'python3 -m claude' claude/settings.json` = 1, and same for all 4 patterns.

3. **Rewrite `/commit` GPG check to avoid `bash -c`**: The commit skill at `skills/commit/SKILL.md:50` uses `bash -c` for GPG sandbox home detection. Rewrite to use `test -f` or `[ -f` (both already allowed). Acceptance criteria: `grep -c 'bash -c' skills/commit/SKILL.md` = 0.

4. **Rewrite `/morning-review` state update to avoid `python3 -c`**: The morning-review skill at `skills/morning-review/SKILL.md:36` uses `python3 -c` for atomic state update. Rewrite to use an approach that matches an allowed pattern (e.g., `jq` for JSON manipulation, or a dedicated script invoked via `python3 -m`). Acceptance criteria: `grep -c 'python3 -c' skills/morning-review/SKILL.md` = 0.

5. **Rewrite `/setup-merge` symlink check to avoid `python3 -c`**: The setup-merge skill at `.claude/skills/setup-merge/SKILL.md:15` uses `python3 -c` for symlink detection. Rewrite to use `test -L` (allowed via `Bash(test *)`). Acceptance criteria: `grep -c 'python3 -c' .claude/skills/setup-merge/SKILL.md` = 0.

6. **Valid JSON maintained**: `claude/settings.json` must remain valid JSON after edits. Acceptance criteria: `python3 -m json.tool claude/settings.json > /dev/null` exits 0.

## Non-Requirements

- **Overnight runner**: Not affected — bypasses permissions entirely via `--dangerously-skip-permissions`. No changes needed to `runner.sh` or dispatch scripts.
- **Other escape hatches**: `Bash(awk *)`, `Bash(make *)`, `Bash(docker *)`, `Bash(claude *)` remain. These are separate concerns for other tickets in epic 054.
- **`settings.local.json` cleanup mechanism**: The sync hook's additive-only merge means removed entries persist in existing project-level settings. This is a pre-existing design limitation of the sync hook, not introduced by this ticket. Document the manual cleanup step; don't build a migration mechanism here.
- **`setup-merge` removal handling**: The merge script only adds missing entries, not removes stale ones. This is existing behavior and out of scope for this ticket.
- **Narrowing `Bash(uv run *)`**: While `uv run` can transitively execute arbitrary Python, scoping it more narrowly (e.g., `Bash(uv run python3 -m claude.*)`) would break legitimate interactive usage patterns like `uv run pytest`. Accept the current breadth.

## Edge Cases

- **Existing deployments**: Users who previously ran `just setup` have the 6 entries in `~/.claude/settings.json`. The setup-merge skill will detect the 4 new entries as missing and offer to add them, but won't remove the 6 old entries. Expected behavior: document that users should manually remove the old entries, or re-run `just setup` with a fresh copy.
- **`cortex-sync-permissions.py` union merge**: The sync hook unions global permissions into project `settings.local.json`. After this change, it will stop injecting the 6 removed entries into new projects. Existing project-level files retain the old entries — the sync hook doesn't subtract. Expected behavior: acceptable for this ticket.
- **WorktreeCreate/Remove hooks**: Use `bash -c` in hook `command` fields. These are harness-executed, not Bash tool invocations. Expected behavior: unaffected.
- **Ad-hoc interpreter use in interactive sessions**: Commands like `python3 -c "print(2+2)"` or `node -e "console.log(1)"` will now trigger permission prompts. Expected behavior: user approves or adds to `settings.local.json`.

## Changes to Existing Behavior

- MODIFIED: `Bash(bash *)`, `Bash(sh *)`, `Bash(source *)` → removed from allow list (fall through to prompt)
- MODIFIED: `Bash(python *)`, `Bash(python3 *)`, `Bash(node *)` → removed from allow list (fall through to prompt)
- ADDED: `Bash(python3 -m claude.*)` to allow list (targeted module execution)
- ADDED: `Bash(python3 -m json.tool *)` to allow list (JSON formatting)
- ADDED: `Bash(uv run *)` to allow list (venv-managed execution)
- ADDED: `Bash(uv sync *)` to allow list (dependency installation)
- MODIFIED: `/commit` skill GPG check — `bash -c` → `test -f` equivalent
- MODIFIED: `/morning-review` state update — `python3 -c` → alternative approach
- MODIFIED: `/setup-merge` symlink check — `python3 -c` → `test -L`

## Technical Constraints

- `claude/settings.json` is deployed via symlink to `~/.claude/settings.json`. Edit the repo copy only.
- JSON must remain valid — settings.json is parsed by Claude Code at startup.
- Allow list entries are logically grouped (git, filesystem, text processing, language runtimes). Place replacement entries near the remaining runtime cluster (`npm`, `npx`, `pip3`, `deno`, `go`).
- The `Bash(python *)` entry (line 106) refers to `python` (Python 2 on some systems). Its removal is safe — no usage exists, and Python 2 is deprecated.

## Open Decisions

(none)
