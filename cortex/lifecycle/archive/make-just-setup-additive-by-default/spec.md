# Specification: make-just-setup-additive-by-default

> Epic reference: `research/shareable-install/research.md` — this ticket implements the DR-5 classification rubric and the `just setup` / `just setup-force` split from that research.

## Problem Statement

`just setup` uses `ln -sf` everywhere, silently overwriting any existing files or symlinks at target paths without warning. A new user who already has a custom `~/.claude/settings.json` or existing hooks will lose their config with no indication. The fix is to make `just setup` classify each target first — installing only safe targets, skipping conflicts, and printing a pending list so the user can resolve conflicts via `/setup-merge`. The destructive behavior is preserved under `just setup-force` for the repo owner who wants unconditional re-installation.

## Requirements

1. **Pre-install classification**: `just setup` classifies all symlink targets before making any changes. Each target is classified as one of: `new` (does not exist), `update` (exists as a symlink pointing to this repo — same absolute path), or `conflict` (exists as a regular file, a broken symlink, or a symlink pointing elsewhere). The classification report is printed before any install action, one line per target in this format:
   ```
   [new]      ~/.local/bin/update-item
   [update]   ~/.claude/settings.json
   [conflict] ~/.claude/hooks/validate-commit.sh — regular file
   [conflict] ~/.local/bin/jcc — symlink to /other/path
   [conflict] ~/.claude/skills/commit — broken symlink
   ```
   All three `conflict` sub-types (regular file, broken symlink, symlink to elsewhere) include the reason, since ticket 007 (`/setup-merge`) uses this information to determine how to resolve each conflict.

2. **Install behavior**: `new` and `update` targets are installed (or re-installed). `conflict` targets are skipped entirely — no write, no overwrite, no prompt.

3. **Pending conflict list**: After installation completes, `just setup` prints the list of skipped conflict targets with a fixed message. Format:
   ```
   N conflict(s) skipped. Open Claude in the cortex-command directory and run:
     /setup-merge
   to resolve the following targets:
     - ~/.claude/hooks/validate-commit.sh (regular file)
     - ~/.local/bin/jcc (symlink to /other/path)
   ```
   If there are no conflicts, this section is omitted entirely. The reason for each conflict is included so `/setup-merge` can determine the appropriate merge action for each target type.

4. **`just setup-force` preserves destructive behavior**: `just setup-force` installs all targets unconditionally via `ln -sf` / `ln -sfn` with no classification, no skipping, and no prompts. This is the current behavior of `just setup`. The repo owner runs this for a clean re-installation.

5. **`settings.local.json` always written**: `settings.local.json` is exempt from classification. It is always written with the correct `sandbox.filesystem.allowWrite` path for this clone location. If the file already exists and `jq` is available, the path is appended to the `allowWrite` array (deduplicated) rather than replaced — preserving paths from other clones. If `jq` is absent, the file is fully overwritten with a warning message: "Warning: jq not found — settings.local.json overwritten. Install jq to preserve allowWrite paths from other clones." If the file does not exist, it is created fresh regardless of jq availability.

6. **Zero conflicts on owner re-run**: Running `just setup` on a machine where all targets are already symlinks pointing to this repo must produce zero conflicts. All such targets classify as `update` and are re-installed cleanly.

7. **`deploy-*` recipes are independently additive**: Each `deploy-bin`, `deploy-reference`, `deploy-skills`, `deploy-hooks`, and `deploy-config` recipe is individually additive by default. Running any one recipe directly behaves the same as when called from `just setup`.

8. **Remove interactive prompts from `deploy-config`**: The existing `read -rp "Overwrite with symlink?"` prompts are removed. Regular file targets are treated as conflicts (skipped) without prompting. This makes setup non-interactive by default.

## Non-Requirements

- `/setup-merge` skill implementation (ticket 007 — this ticket only produces the pending conflict list)
- `settings.json` content-aware merge (ticket 007)
- `check-symlinks` modification — it stays strict; conflict-skipped targets will show as missing until 007 is run
- Hook prefix migration (`cortex-` prefix) — already completed (ticket 005)
- Skill directory symlink discovery fix (Claude Code issue #14836 — deferred)
- Backup-and-replace behavior (no `.bak` files created)
- Dry-run mode (a separate enhancement if needed)

## Edge Cases

- **Broken symlink (dangling)**: A symlink whose target has been deleted (`! -e && -L`) is treated as conflict — skip with message. Not treated as `new` since overwriting it might hide a configuration error.
- **Symlink pointing to a different clone**: If a target is a symlink pointing to a different copy of cortex-command (different clone path), it classifies as `conflict` — the stored absolute path does not match the current `$(pwd)`.
- **`settings.local.json` exists with existing `allowWrite` paths**: New path is appended using jq with `unique` dedup — existing paths are preserved. If the current path is already in the array, the file is unchanged.
- **`settings.local.json` exists but `jq` is absent**: File is fully overwritten with a warning: "Warning: jq not found — settings.local.json overwritten. Install jq to preserve allowWrite paths from other clones." Users with multiple clones should install jq to avoid path loss.
- **`deploy-reference` has no bash shebang**: Currently a plain just recipe (line-by-line shell commands). Must be converted to a bash block (add `#!/usr/bin/env bash` + `set -euo pipefail`) to support classification logic.
- **No conflicts exist**: `just setup` completes without printing a pending list section. Output is clean.
- **All targets are conflicts**: `just setup` prints all targets as conflicts, prints the pending list, installs nothing (except `settings.local.json`). Does not error out.
- **`python-setup` (uv sync)**: Not a symlink target — exempt from classification. Runs as before.

## Technical Constraints

- **Plain `readlink` (no `-f`)**: Symlink target comparison uses `readlink "$target"` with no flags. `readlink -f` is a GNU extension unavailable on macOS pre-12.3 and must not be used. Since `just setup` creates symlinks using `$(pwd)/...` (absolute), plain `readlink` comparison is reliable.
- **Absolute paths only**: Symlinks must be created with absolute source paths (`$(pwd)/...`). Classification depends on exact string comparison between `readlink "$target"` and the expected source. Relative paths would break the `update` classification.
- **File vs directory symlinks use different `ln` flags**: File symlink targets use `ln -sf`; directory symlink targets (deploy-skills) use `ln -sfn`. Classification logic (`readlink` comparison) works the same for both. The expected source path for directory targets is the directory path (e.g., `$(pwd)/skills/commit`), NOT a file inside it — the loop variable `skill in skills/*/SKILL.md` is used to enumerate skills, but the symlink target and readlink comparison use the parent directory path (`$(pwd)/skills/$name`).
- **jq availability for `settings.local.json` dedup**: The append-with-dedup operation requires `jq`. If absent, fall back to full overwrite with a warning (see Requirement 5).
- **Bash shebangs required**: All five deploy-* recipes must use `#!/usr/bin/env bash` + `set -euo pipefail`. Currently `deploy-reference` lacks a shebang — adding it is in scope for this ticket.
- **macOS and Linux compatibility**: All bash constructs must work on both platforms. Arrays (`declare -a`), `readlink`, and `ln -sf` all work portably.
- **`setup-force` implementation**: `setup-force` is a standalone recipe with inlined `ln -sf` / `ln -sfn` calls — it does not call the additive deploy-* recipes and does not use env var flags. This duplicates the target list, but is explicit with no invisible env var dependency. Per the project's "simplicity wins" principle, explicit duplication is preferable to env var threading. A comment in the recipe documents that any new symlink target added to a deploy-* recipe must also be added to `setup-force`.
