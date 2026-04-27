# Research: Remove interpreter escape hatch commands

## Epic Reference

Background context from `research/permissions-audit/research.md` (epic 054). This ticket implements DR-2 from the permissions-audit discovery — removing 6 interpreter escape hatch entries from the allow list after spike 055 confirmed the bypass is open.

## Codebase Analysis

### Files that will change

**Primary change:**
- `claude/settings.json` — Remove 6 entries from `permissions.allow`, add 4 replacements

**Entries to remove:**
- Line 91: `"Bash(bash *)"`
- Line 92: `"Bash(sh *)"`
- Line 93: `"Bash(source *)"`
- Line 106: `"Bash(python *)"`
- Line 107: `"Bash(python3 *)"`
- Line 108: `"Bash(node *)"`

**Entries to add** (positioned near remaining language runtime cluster — `npm`, `npx`, `pip3`, `deno`, `go`):
- `"Bash(python3 -m claude.*)"`
- `"Bash(python3 -m json.tool *)"`
- `"Bash(uv run *)"`
- `"Bash(uv sync *)"`

### Skills affected by the removal

Three skills use `bash -c` or `python3 -c` via Claude's Bash tool and will start prompting after the change:

1. **`/commit` skill** (`skills/commit/SKILL.md:50`): Uses `bash -c 'if [ -f "$TMPDIR/gnupghome/S.gpg-agent" ]; then echo "GNUPGHOME=$TMPDIR/gnupghome"; fi'` for GPG sandbox home detection. Can be rewritten to use `test -f` (already allowed via `Bash(test *)`).

2. **`/morning-review` skill** (`skills/morning-review/SKILL.md:36`): Uses `python3 -c "import json, os, tempfile, pathlib..."` to atomically update overnight state. Can be converted to a script invoked via `python3 -m` or `uv run`.

3. **`/setup-merge` skill** (`.claude/skills/setup-merge/SKILL.md:15`): Uses `python3 -c "import pathlib; exit(0 if pathlib.Path('~/.claude/settings.json').expanduser().is_symlink() else 1)"` for symlink check. Can be rewritten to use `test -L` (allowed via `Bash(test *)`).

These skills should be rewritten before or alongside the settings change to avoid regressions in the most frequently used workflows.

### Integration points — no changes needed

- **`cortex-sync-permissions.py`**: Union-merges global permissions into project `settings.local.json`. Does not hardcode specific entries — will propagate the new allow list automatically. However, it only adds entries, never removes — see Open Questions.
- **`setup-merge` script** (`merge_settings.py`): Computes set differences and applies deltas. Will detect 4 new entries as absent from user settings and offer to add them. Does not handle removals — old entries persist in deployed settings until manually removed.
- **WorktreeCreate/Remove hooks**: Use `bash -c` in hook `command` fields. These are executed by the Claude Code harness directly, outside permission evaluation. Unaffected.
- **Overnight runner**: Uses `python3 -c`, `bash -c`, and `source` extensively as direct subprocess calls in `runner.sh`, not via Claude's Bash tool. Also bypasses permissions entirely via `--dangerously-skip-permissions`. Unaffected.
- **Tests**: No tests validate specific allow-list entries. Generic sync-permissions tests (hash detection, merge, idempotency) will continue to pass.

## Web Research

### Claude Code permission system behavior

- Rules follow `Bash(pattern)` syntax with glob `*` wildcards. Evaluation order: deny → ask → allow (first match wins).
- Claude Code splits compound commands (`&&`, `||`, `;`) into subcommands for separate evaluation.
- Interpreter wrapper commands (`bash -c`, `python3 -c`, `sh -c`) are NOT decomposed. They match as a single unit against the top-level command pattern. Inner arguments are opaque.
- Spike 055 empirically confirmed: all 4 test cases returned ALLOW. Deny rules are not evaluated through interpreter wrappers.

### Anthropic's position on interpreter access

- Auto mode automatically strips allow rules for "wildcarded script interpreters (python, node, ruby, and similar)" — confirming Anthropic recognizes interpreter access as a high-risk vector.
- Anthropic's official position: "Claude Code's deny rules are not designed as a security barrier against adversarial command construction. They are a convenience mechanism to constrain well-intentioned agent actions."
- The recommended model is defense-in-depth: permissions prevent Claude from attempting actions; sandbox provides OS-level enforcement.

### Historical Claude Code security issues

- **50-subcommand threshold bypass** (patched v2.1.90): `bashPermissions.ts` had `MAX_SUBCOMMANDS_FOR_SECURITY_CHECK = 50`. Commands with 50+ subcommands silently skipped deny enforcement.
- **Command chaining bypass** (Issue #4956, Sept 2025): Demonstrated bypass via `&&`, `||`, `;`, pipes, and command/process substitution. May have been patched since.
- **Command option insertion** (Issue #13371, open): `git -C /path commit` bypasses deny on `git commit` via `startsWith()` matching failure.

### No community precedent

No community-published settings.json configurations address the interpreter wrapper bypass. This is an under-recognized gap.

## Requirements & Constraints

### Defense-in-depth mandate (`requirements/project.md`)

> Defense-in-depth for permissions: The global `settings.json` template ships conservative defaults — minimal allow list, comprehensive deny list, sandbox enabled. For sandbox-excluded commands (git, gh, WebFetch), the permission allow/deny list is the sole enforcement layer; keep global allows read-only and let write operations fall through to prompt.

### Relevant constraints

1. **Template is global**: `claude/settings.json` deploys to `~/.claude/settings.json` via `just setup`, becoming permissions for ALL projects on the machine.
2. **Overnight bypasses permissions**: `--dangerously-skip-permissions` and `permission_mode="bypassPermissions"`. This change only affects interactive sessions.
3. **`autoAllowBashIfSandboxed: true`**: Removed entries fall through to prompt (no matching allow, no matching deny → defaultMode `"default"` → prompt).
4. **Sandbox excludes git, gh, WebFetch**: For these commands, the allow/deny list is the sole enforcement. Interpreter wrappers make this enforcement zero for sandbox-excluded operations.
5. **Spike 055 is resolved**: Confirmed bypass is OPEN. The "if bypass confirmed" path is now operative.

## Tradeoffs & Alternatives

### A: Remove all 6 + add 4 specific replacements (ticket's proposal) — RECOMMENDED

**Pros**: Fully closes the interpreter bypass. Replacements cover all confirmed interactive usage. Minimal attack surface. Aligns with Anthropic's auto-mode behavior.
**Cons**: Ad-hoc `python3 -c`, `python3 -m pytest` prompt. Users add entries to `settings.local.json` which drifts.
**Risk**: Low.

### B: Remove all 6 + add broader `python3 -m *`

**Pros**: Covers all module invocations (pytest, py_compile, json.tool, etc.). Does not re-open the escape hatch since `python3 -m` cannot pass shell commands as module arguments.
**Cons**: Broader than necessary. Minor risk from `python3 -m os` or similar (not practically exploitable via module runner interface).
**Risk**: Low.

### C: Remove all 6 with no replacements

**Pros**: Maximum security. Simplest change.
**Cons**: Every `uv run`, `uv sync`, `python3 -m json.tool` prompts. Would likely drive users to re-add broad patterns to `settings.local.json`.
**Risk**: Low security risk, high usability risk.

### D: Move to deny list instead of removing from allow

**Pros**: Deny evaluates first, would block `bash -c`.
**Cons**: Does not work comprehensively. `bash script.sh`, `bash -ec`, `bash --norc -c` all bypass specific deny patterns. Creates an arms race of increasingly specific deny entries.
**Risk**: High. False sense of security.

### E: Keep `python3 *`, remove the other 5

**Pros**: Preserves Python convenience.
**Cons**: Leaves the confirmed bypass open for Python. `python3 -c "import os; os.system('git push --force origin main')"` still auto-allows. Inconsistent security posture.
**Risk**: High.

### Recommended: Alternative A

The only approach that fully closes the confirmed bypass. The 4 replacements cover every legitimate interactive use case. Variant B (`python3 -m *` instead of specific modules) is defensible if broader Python convenience is desired.

## Adversarial Review

### Confirmed risks

1. **`settings.local.json` persistence**: The sync hook performs union merges — it only adds entries, never removes. Existing project-level `settings.local.json` files already contain the 6 entries and will retain them after the template change. Since local project settings have higher precedence than user global settings, the escape hatches remain active in every project that has been used before. This is a pre-existing limitation of the sync hook's additive-only design, affecting all allow-list removals — not specific to this ticket.

2. **Skill regressions if not rewritten**: The `/commit`, `/morning-review`, and `/setup-merge` skills use `bash -c` or `python3 -c` via Claude's Bash tool. Landing the settings change without rewriting these skills creates regressions in the most frequently used workflows.

3. **`Bash(uv run *)` is broad**: `uv run python3 -c "import os; os.system('...')"` could bypass deny rules. Constrained to the project's venv but functionally similar to `Bash(python3 *)` with a prefix.

### Acknowledged but out-of-scope

4. **Other escape hatches remain**: `Bash(awk *)` (awk `system()`), `Bash(make *)` (Makefile recipes), `Bash(docker *)` (container execution), `Bash(claude *)` (nested invocations), `Bash(sed *)` (GNU sed `e` flag) all have similar bypass potential. These belong to other tickets in epic 054, not this one. This ticket closes 6 of the identified interpreter escape hatches.

5. **`Bash(python3 -m claude.*)` minor escape**: An attacker could create a module in the `claude/` directory (`claude/exploit/__main__.py`) and `python3 -m claude.exploit` would auto-allow. Lower severity — requires Write tool access to create the module first.

### Mitigations

- Rewrite 3 affected skills before or alongside the settings change
- Document that `settings.local.json` cleanup is needed for existing deployments
- Consider scoping `Bash(uv run *)` more narrowly if usability permits

## Open Questions

- **`settings.local.json` stale entry cleanup**: The sync hook's additive-only merge means removed entries persist in project-level settings indefinitely. Should this ticket include a one-time cleanup mechanism, or is that a separate concern for the sync hook's design? (Deferred: this is a pre-existing limitation affecting all allow-list removals. The sync hook's design is a separate concern — document the manual cleanup step for now.)
