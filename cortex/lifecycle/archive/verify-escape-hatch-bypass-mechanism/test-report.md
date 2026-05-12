# Test Report: Escape Hatch Bypass Verification

## Test Environment

- **Claude Code version**: v2.1.97 (Opus 4.6 model)
- **Session**: Interactive, sandboxed
- **Settings source**: `claude/settings.json` (symlinked to `~/.claude/settings.json`)
- **Relevant allow entries**: `Bash(bash *)`, `Bash(sh *)`, `Bash(python3 *)`
- **Relevant deny entries**: `Bash(git push --force *)`, `Bash(rm -rf *)`, `Bash(rm -fr *)`
- **Sandbox config**: `autoAllowBashIfSandboxed: true`, `excludedCommands: ["gh:*", "git:*", "WebFetch"]`
- **Permission audit log**: `cortex-permission-audit-log.sh` registered for `permission_prompt` events
- **Audit log result**: No audit log file created across all tests — zero permission prompts fired

## Results

| Test | Command | Expected Deny Pattern | Actual Outcome | Mechanism | Sandbox Involved | Conclusion |
|------|---------|----------------------|----------------|-----------|-----------------|------------|
| R1 | `bash -c "git push --force --dry-run origin main"` | `Bash(git push --force *)` | ALLOW | `Bash(bash *)` allow matched top-level command | No (git is sandbox-excluded) | Deny rule bypassed |
| R1-ctrl | `bash -c "echo hello"` | None (no deny for echo) | ALLOW | `Bash(bash *)` allow matched top-level command | No | Control confirms allow matches all bash -c commands |
| R2 | `python3 -c "import os; os.system('git push --force --dry-run origin main')"` | `Bash(git push --force *)` | ALLOW | `Bash(python3 *)` allow matched top-level command | No (git is sandbox-excluded via os.system) | Deny rule bypassed |
| R3 | `sh -c "rm -rf /tmp/test"` | `Bash(rm -rf *)` | ALLOW | `Bash(sh *)` allow matched top-level command | Possible (rm not sandbox-excluded, but -f flag on non-existent path produces no observable error) | Deny rule bypassed at permission layer |

## Mechanism Analysis

### Finding: Deny rules do NOT compose through interpreter wrappers

The permission system evaluates deny/ask/allow rules against the **full command string as a single unit**. When a command is wrapped in an interpreter call:

- `bash -c "git push --force --dry-run origin main"` → matched against `Bash(bash *)` (ALLOW), **not** `Bash(git push --force *)` (DENY)
- `python3 -c "import os; os.system('git push --force --dry-run origin main')"` → matched against `Bash(python3 *)` (ALLOW)
- `sh -c "rm -rf /tmp/test"` → matched against `Bash(sh *)` (ALLOW), **not** `Bash(rm -rf *)` (DENY)

The deny list patterns operate on the top-level command token only. Inner command arguments passed to interpreter wrappers are treated as opaque string arguments and are never evaluated against deny rules.

### f65 Classifier Did Not Intervene

Binary analysis of Claude Code identified a `f65` set of dangerous shell interpreter names that could potentially flag `bash`, `sh`, etc. as dangerous prefixes. **This classifier did not intervene in any test case.** Both R1 (denied inner command) and R1-ctrl (non-denied inner command) were silently allowed, confirming that the `f65` classifier either:

1. Does not operate in the glob-based permission evaluation path (only in auto-mode or compound-command analysis), or
2. Is overridden by the explicit `Bash(bash *)` allow rule in the user's settings

The protection suggested by binary analysis is **not active** in the current permission configuration.

### Compound Command Analysis vs. Interpreter Wrapper Analysis

Claude Code is documented to analyze compound commands (`&&`, `||`, `|`, `;`) by splitting them into subcommands for separate deny-rule evaluation. However, this analysis **does not extend** to interpreter wrappers (`bash -c`, `sh -c`, `python3 -c`). The interpreter wrapper is treated as a single command, not decomposed into its inner subcommands.

## Conclusion

**The escape hatch is confirmed OPEN.** Interpreter allow entries (`Bash(bash *)`, `Bash(sh *)`, `Bash(python3 *)`, etc.) completely bypass the deny list for any command wrapped in an interpreter call. This is the worst-case outcome for the security model:

1. **Any denied command can be executed** by wrapping it in `bash -c "..."`, `sh -c "..."`, or `python3 -c "import os; os.system('...')"` — the deny list is effectively optional
2. **Git commands are especially vulnerable** because `git:*` is also sandbox-excluded — neither the permission deny list nor the sandbox protects against `bash -c "git push --force origin main"`
3. **The only remaining protection** is Anthropic's stated position that deny rules are "not designed as a security barrier" and that the sandbox is the real enforcement layer — but for sandbox-excluded commands (git, gh, WebFetch), there is **no protection at all**

### DR-2 Recommendation

**Proceed with DR-2 (remove interpreter escape hatches) at HIGH priority.** The bypass is empirically confirmed. Removing `Bash(bash *)`, `Bash(sh *)`, `Bash(source *)`, `Bash(python *)`, `Bash(python3 *)`, and `Bash(node *)` from the allow list closes this escape hatch. Replacement patterns (`Bash(python3 -m claude.*)`, `Bash(uv run *)`, etc.) provide the specific access the framework needs without the blanket bypass.

### Ticket 057 Priority

**Set to HIGH** — all four test cases showed ALLOW (silent execution without prompt or deny). The bypass is universal across all three interpreter families tested (bash, sh, python3).
