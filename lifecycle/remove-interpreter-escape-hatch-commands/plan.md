# Plan: Remove interpreter escape hatch commands

## Overview

Mechanical edit to `claude/settings.json` (remove 6 interpreter entries, add 4 replacements) plus 3 skill rewrites to eliminate `bash -c` and `python3 -c` usage. All 4 tasks are independent and can execute in parallel.

## Tasks

### Task 1: Edit settings.json allow list
- **Files**: `claude/settings.json`
- **What**: Remove 6 interpreter escape hatch entries and add 4 targeted replacement patterns to the allow list.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Remove these 6 entries from `permissions.allow`: `"Bash(bash *)"` (line 91), `"Bash(sh *)"` (line 92), `"Bash(source *)"` (line 93), `"Bash(python *)"` (line 106), `"Bash(python3 *)"` (line 107), `"Bash(node *)"` (line 108). Add these 4 entries in the same region, near the remaining language runtime cluster (`npm`, `npx`, `pip3`, `deno`, `go`): `"Bash(python3 -m claude.*)"`, `"Bash(python3 -m json.tool *)"`, `"Bash(uv run *)"`, `"Bash(uv sync *)"`.
- **Verification**: `python3 -m json.tool claude/settings.json > /dev/null` — pass if exit 0 (valid JSON). `grep -c 'Bash(bash \*)' claude/settings.json` = 0. `grep -c 'Bash(sh \*)' claude/settings.json` = 0. `grep -c 'Bash(source \*)' claude/settings.json` = 0. `grep -c 'Bash(python \*)' claude/settings.json` = 0 (must not match `python3`; use `grep -cP 'Bash\(python \*\)' claude/settings.json`). `grep -c 'Bash(python3 \*)' claude/settings.json` = 0 (must not match `python3 -m`; use `grep -cP 'Bash\(python3 \*\)"' claude/settings.json`). `grep -c 'Bash(node \*)' claude/settings.json` = 0. `grep -c 'python3 -m claude' claude/settings.json` = 1. `grep -c 'python3 -m json.tool' claude/settings.json` = 1. `grep -c 'uv run' claude/settings.json` = 1. `grep -c 'uv sync' claude/settings.json` = 1.
- **Status**: [x] done

### Task 2: Rewrite /commit GPG check
- **Files**: `skills/commit/SKILL.md`
- **What**: Replace the `bash -c 'if [ -f "$TMPDIR/gnupghome/S.gpg-agent" ]; then echo "GNUPGHOME=$TMPDIR/gnupghome"; fi'` command with an equivalent using `test -f` (allowed via `Bash(test *)`).
- **Depends on**: none
- **Complexity**: simple
- **Context**: At `skills/commit/SKILL.md:50`, the skill instructs Claude to run a `bash -c` command that checks for the GPG agent socket and prints a `GNUPGHOME=` prefix. The equivalent using allowed commands: `test -f "$TMPDIR/gnupghome/S.gpg-agent"` (exit 0 if exists, 1 if not). Claude can then conditionally print the GNUPGHOME prefix based on the exit code without needing `bash -c`. Update the surrounding prose instructions (Step 5) to describe the new approach.
- **Verification**: `grep -c 'bash -c' skills/commit/SKILL.md` = 0 — pass if count = 0.
- **Status**: [x] done

### Task 3: Rewrite /morning-review state update
- **Files**: `skills/morning-review/SKILL.md`
- **What**: Replace the `python3 -c` block that atomically updates overnight state JSON with a `jq`-based approach (jq is already in the allow list).
- **Depends on**: none
- **Complexity**: simple
- **Context**: At `skills/morning-review/SKILL.md:36-50`, the skill instructs Claude to run an inline Python script that reads `overnight-state.json`, checks if `phase == "executing"`, updates it to `"complete"`, and writes atomically via tempfile+fsync+rename. Replace with jq: read the phase with `jq -r '.phase' <path>`, check if it equals `"executing"`, then update with `jq '.phase = "complete"' <path>` written to a temp file and moved into place. The `jq` approach is simpler and already allowed. The atomicity guarantee (fsync) is not critical here — this runs in an interactive session, not the overnight runner. Also update the pointer file update instruction (line 53) to use the same jq pattern.
- **Verification**: `grep -c 'python3 -c' skills/morning-review/SKILL.md` = 0 — pass if count = 0.
- **Status**: [x] done

### Task 4: Rewrite /setup-merge symlink check
- **Files**: `skills/setup-merge/SKILL.md`
- **What**: Replace the `python3 -c "import pathlib; exit(0 if pathlib.Path('~/.claude/settings.json').expanduser().is_symlink() else 1)"` command with `test -L ~/.claude/settings.json` (allowed via `Bash(test *)`).
- **Depends on**: none
- **Complexity**: simple
- **Context**: At `skills/setup-merge/SKILL.md:15` (symlinked to `.claude/skills/setup-merge/SKILL.md`), the skill checks whether `~/.claude/settings.json` is a symlink. `test -L` does the same thing: exit 0 if the path is a symbolic link, exit 1 otherwise. Direct drop-in replacement. The repo source is `skills/setup-merge/SKILL.md`; the `.claude/skills/setup-merge/SKILL.md` is a symlink to it.
- **Verification**: `grep -c 'python3 -c' skills/setup-merge/SKILL.md` = 0 — pass if count = 0.
- **Status**: [x] done

## Verification Strategy

After all 4 tasks complete:
1. `python3 -m json.tool claude/settings.json > /dev/null` exits 0 (valid JSON)
2. `grep -c 'Bash(bash \*)' claude/settings.json` = 0 (all 6 interpreter entries removed)
3. `grep -c 'python3 -m claude' claude/settings.json` = 1 (all 4 replacements added)
4. `grep -c 'bash -c' skills/commit/SKILL.md` = 0 (commit skill rewritten)
5. `grep -c 'python3 -c' skills/morning-review/SKILL.md` = 0 (morning-review skill rewritten)
6. `grep -c 'python3 -c' skills/setup-merge/SKILL.md` = 0 (setup-merge skill rewritten)
