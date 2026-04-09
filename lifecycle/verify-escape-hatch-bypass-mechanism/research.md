# Research: Verify escape hatch bypass mechanism

## Epic Reference

Background epic research at `research/permissions-audit/research.md` (epic 054). This ticket verifies one specific open question from that research: whether `bash -c "denied-command"` bypasses deny-list pattern matching, which is a blocker for DR-2 (removing interpreter escape hatch commands).

## Codebase Analysis

### Current Allow/Deny Configuration

**Escape hatch allow entries** (`claude/settings.json`):
- `Bash(bash *)` — matches `bash -c "anything"`
- `Bash(sh *)` — matches `sh -c "anything"`
- `Bash(source *)` — matches `source any-script`
- `Bash(python *)`, `Bash(python3 *)` — matches interpreter execution
- `Bash(node *)` — matches node execution
- `Bash(* --version)`, `Bash(* --help *)` — leading wildcards match any binary

**Deny entries under test**:
- `Bash(git push --force *)` / variants
- `Bash(rm -rf *)` / `Bash(rm -fr *)`
- `Bash(git reset --hard*)`, `Bash(sudo *)`, `Bash(dd *)`, etc.

### Sandbox Configuration

- `sandbox.enabled: true`
- `sandbox.autoAllowBashIfSandboxed: true` — auto-approves non-denied commands within sandbox
- `sandbox.excludedCommands: ["gh:*", "git:*", "WebFetch"]` — **git commands bypass sandbox entirely**
- This makes `git push --force` the cleanest test case: the permission layer is the sole gatekeeper

### Observability

The `cortex-permission-audit-log.sh` hook logs `permission_prompt` events to `$TMPDIR/claude-permissions-{session_key}.log`. During empirical testing, this log shows whether commands triggered permission prompts (indicating they were not auto-allowed or auto-denied silently).

### Settings Deployment

- `claude/settings.json` is the template, symlinked to `~/.claude/settings.json`
- `.claude/settings.local.json` is a near-duplicate with minor additions
- `cortex-sync-permissions.py` keeps them in sync via hash-based change detection

### No Existing Tests

No unit or integration tests exist for permission evaluation behavior. Testing must be empirical within a live Claude Code session.

## Web Research

### Permission Pattern Matching Architecture

Claude Code's permission system uses glob-based pattern matching on Bash commands. Rules follow `Bash(pattern)` where `*` is a wildcard. Evaluation order: **deny first, then ask, then allow** — first match wins.

Official documentation confirms: "Claude Code is aware of shell operators (like `&&`) so a prefix match rule like `Bash(safe-cmd *)` won't give it permission to run the command `safe-cmd && other-cmd`." Compound commands get separate rules per subcommand (up to 5 per compound command).

### Interpreter Wrapper Handling: Undocumented Gap

**No documentation or discussion confirms that Claude Code recursively analyzes arguments inside interpreter wrappers** (`bash -c`, `sh -c`, `python3 -c`). This is the central finding.

A third-party reimplementation (claude-code-auto-approve) documents: "`bash -c 'echo hello'` has no shell metacharacters, so it takes the fast path and matches against the prefix list as-is without recursing."

The auto mode documentation mentions the classifier "evaluate[s] the real-world impact of an action" — but this refers to the auto-mode AI classifier (Sonnet 4.6), not the glob-based permission matcher.

### Binary Analysis: Three-Layer Permission System

Analysis of the Claude Code binary reveals a more sophisticated architecture than pure glob matching:

1. **Glob pattern matching** — the deny/ask/allow rules as configured in settings.json
2. **Tree-sitter AST-based parsing** — `tree-sitter-bash` decomposes commands into structured ASTs, splits on `&&`, `||`, `|`, `;` operators
3. **ML-based prefix classification** — a `f65` set of known dangerous shell interpreter names (`bash`, `sh`, `zsh`, `fish`, `csh`, `tcsh`, `ksh`, `dash`, etc.) triggers special handling. When detected, the prefix classifier returns `{commandPrefix: null, error: "dangerous_shell_prefix"}`
4. **Command injection detection** — a `command_injection_detected` return path exists from the prefix classifier

**Key implication**: The `f65` dangerous shell set strongly suggests interpreter-wrapped commands ARE caught at the prefix classification layer. However, this is inference from minified code — the exact execution path for `bash -c` arguments through all three layers cannot be traced definitively.

### Anthropic's Official Position

Anthropic's security team has stated: "Claude Code's deny rules are not designed as a security barrier against adversarial command construction. They are a convenience mechanism to constrain well-intentioned agent actions."

The recommended security model is **defense in depth**: deny rules prevent Claude from attempting restricted actions, while sandbox restrictions (OS-level enforcement) block the underlying process.

### Auto Mode Strips Interpreter Access

When entering auto mode, Claude Code automatically disables allow rules granting blanket shell access, including "wildcarded script interpreters (python, node, ruby, and similar)." This confirms Anthropic recognizes interpreter access as a high-risk vector.

### Historical Bypass Vulnerabilities

- **50-subcommand limit** (patched April 2026, v2.1.90): `MAX_SUBCOMMANDS_FOR_SECURITY_CHECK = 50` caused deny rules to silently fall back to "ask" for commands beyond position 50
- **Regex-based bypasses** (CVE-2025-66032, fixed v1.0.93): 8 different bypass techniques including `sed` e-flag execution, git argument abbreviation, `$IFS` manipulation
- **Read/Edit deny ≠ Bash deny**: Official docs warn `Read(./.env)` deny does not prevent `cat .env` in Bash

### Relevant References

- Claude Code permissions docs: https://code.claude.com/docs/en/permissions
- Claude Code security docs: https://code.claude.com/docs/en/security
- Adversa AI bypass research (April 2026): 50-subcommand limit
- Flatt Security research: 8 bypass techniques (CVE-2025-66032)
- GitHub issues: #4956 (compound command bypasses), #6036, #6631 (Read/Bash mismatch)

## Requirements & Constraints

### Scope: Interactive Sessions Only

The permission allow/deny list only governs **interactive Claude Code sessions**. The overnight runner bypasses permissions entirely via `--dangerously-skip-permissions`, and worker agents use `permission_mode="bypassPermissions"`. For overnight execution, the sandbox is the sole security boundary.

This means: escape hatch verification is relevant to interactive security posture and public template safety, but has no bearing on overnight runner security.

### Sandbox as Independent Layer

Even if deny-list patterns fail to catch interpreter-wrapped commands, the sandbox may independently block the underlying operation. Testing must distinguish "denied by permission system" from "blocked by sandbox." The git test case isolates this cleanly because `git:*` is sandbox-excluded.

### Public Distribution Impact

`claude/settings.json` becomes the **global** permissions for ALL Claude Code projects when deployed via `just setup`. If interpreter wrapping bypasses deny rules, this affects every project on the user's machine, not just cortex-command.

### Project Philosophy Constraints

From `requirements/project.md`:
- "Complexity must earn its place by solving a real problem that exists now"
- "ROI matters — the system exists to make shipping faster, not to be a project in itself"
- The work is justified by the epic research marking it as "BLOCKER for DR-2"

## Tradeoffs & Alternatives

### Approach A: Direct Execution in Live Session

**Description**: Attempt each test command in a live Claude Code session, observe whether permission system blocks, prompts, or allows.

**Pros**: Produces definitive ground-truth results. Tests the entire pipeline (glob + tree-sitter + ML classifier + sandbox). Distinguishes all three outcomes (deny/ask/allow).

**Cons**: Sandbox independently blocks some operations, making isolation hard for non-git test cases. Risk of executing destructive commands if all protections fail (mitigated by targeting non-existent remote state).

### Approach B: Settings Manipulation

**Description**: Temporarily modify settings to create controlled test environment with synthetic deny rules.

**Pros**: Fully controlled, repeatable. No destructive risk.

**Cons**: Requires session restart for settings to take effect. Tests synthetic patterns that may exercise different code paths than production deny rules. `cortex-sync-permissions.py` may overwrite changes.

### Approach C: Safe Command Substitution

**Description**: Test with harmless commands that have matching deny patterns (e.g., deny `Bash(echo FORBIDDEN *)`, then test `bash -c "echo FORBIDDEN test"`).

**Pros**: Zero risk even if all protections fail.

**Cons**: Same restart requirement as B. ML-based prefix classifier may behave differently for `echo` vs `git push --force`. May produce false confidence.

### Approach D: Code Reading (Binary Analysis)

**Description**: Read Claude Code's source/binary to understand pattern matching implementation deductively.

**Pros**: Authoritative for architecture. Already partially done — revealed three-layer system and `f65` dangerous shell set.

**Cons**: Compiled binary with minified JS; full path tracing infeasible. ML classifier behavior cannot be determined from code alone (calls an API). Findings are informative but not definitive.

### Approach E: Meta-Observation (This Session)

**Description**: Attempt commands from within this running session and observe permission behavior.

**Pros**: Immediate, no setup. Permission audit log provides observability. Tests actual production configuration.

**Cons**: Agent is constrained by the system being tested. Session settings may differ from template.

### Recommended: Approach F — Hybrid (Binary Analysis + Targeted Empirical Test)

**Rationale**: Binary analysis already provides architectural insight (three-layer system, `f65` dangerous shell set). The single best empirical test is `bash -c "git push --force origin main"` because:

1. `git:*` is sandbox-excluded — permission layer is the sole gatekeeper
2. `Bash(git push --force *)` is in the deny list
3. `Bash(bash *)` is in the allow list
4. The result is unambiguous: denied = escape hatch closed; prompted/allowed = escape hatch open
5. Even if allowed, targets non-existent remote state — no actual harm

Secondary tests: `python3 -c "import os; os.system('git push --force origin main')"` and `sh -c "rm -rf /tmp/test"` (sandbox would also block the latter, but the permission audit log shows whether the permission layer caught it first).

## Adversarial Review

Agent 5 (Adversarial) was unable to complete due to a rate limit. The following adversarial considerations are synthesized from the other agents' findings:

### Assumptions That May Not Hold

1. **Binary analysis reliability**: The `f65` dangerous shell set and `command_injection_detected` path are inferred from minified JavaScript in a compiled binary. Variable names are obfuscated (`bT`, `Dz7`, `f65`, `xW1`). The actual execution path may differ from what the structure suggests.

2. **Version coupling**: The binary analysis reflects the currently installed Claude Code version (v2.1.97). Permission handling has changed significantly across versions (CVE-2025-66032, 50-subcommand fix). Findings may not generalize to future versions.

3. **ML classifier opacity**: The prefix classifier calls an API (`j65` function). Its behavior is non-deterministic by nature and may change without notice. Even if it blocks `bash -c` today, Anthropic could alter the classifier's behavior in a model update.

4. **Settings.local.json divergence**: The test runs against the active session's merged permissions, not the template. If `settings.local.json` has overrides that affect interpreter handling, results may not reflect the public template's behavior.

### Failure Modes in Testing

5. **False negative on sandbox interaction**: For the `sh -c "rm -rf /tmp/test"` case, a sandbox block looks identical to a permission deny from the user's perspective. Without the permission audit log, these are indistinguishable. The audit log must be checked for every test case.

6. **Three-outcome blindness**: If a command triggers `ask` (permission prompt), the agent cannot proceed without user approval. The test "succeeds" (escape hatch partially open) but the agent may interpret the prompt as a "block" unless the protocol explicitly accounts for the ask outcome.

7. **Semantic vs. syntactic matching**: The tree-sitter parser decomposes shell ASTs syntactically. `bash -c "git push --force"` is syntactically a single command (`bash`) with arguments (`-c`, `"git push --force"`). The inner string is not a separate AST node. The `f65` set may flag `bash` as dangerous and block the entire command — but this is different from "the deny rule for `git push --force` fired through the wrapper." The mechanism matters for understanding the security model, not just the pass/fail result.

### Security Concerns

8. **Encoding variations**: Even if `bash -c "git push --force"` is caught, what about `bash -c $'git\x20push\x20--force\x20origin\x20main'` or `bash -c "$(echo git push --force origin main)"`? The test cases should include at least one encoding variation to test parser robustness.

9. **Indirect interpreter paths**: `/bin/bash -c`, `/usr/bin/env bash -c`, or `command bash -c` may not match the `f65` set if it only checks the command name, not the full path.

## Open Questions

- Does the `f65` dangerous shell prefix classifier block interpreter-wrapped commands at the permission layer (before glob matching), or does glob matching run first? The mechanism determines whether the defense is "deny rule fires through wrapper" vs. "interpreter command itself is flagged as dangerous regardless of arguments."
- Should the test protocol include encoding variations (e.g., `$'...'` quoting, command substitution) to test parser robustness beyond the three baseline cases?
