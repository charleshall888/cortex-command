---
id: 007
title: "Build /setup-merge local skill"
type: feature
status: complete
priority: medium
parent: 003
blocked-by: []
tags: [shareability, install, setup, skills]
created: 2026-04-02
updated: 2026-04-03
discovery_source: research/shareable-install/research.md
session_id: null
lifecycle_phase: complete
lifecycle_slug: build-setup-merge-local-skill
complexity: complex
criticality: high
spec: lifecycle/build-setup-merge-local-skill/spec.md
---

# Build /setup-merge local skill

## Context

After `just setup` runs in additive mode (ticket 006), conflicting targets are skipped and a pending list is printed. `/setup-merge` resolves those conflicts — it merges cortex-command's contributions into the user's existing `~/.claude/settings.json` and handles any other skipped targets. It is a local project skill (in `.claude/skills/`) to avoid polluting the global context window.

## Findings

From `research/shareable-install/research.md` (DR-2, DR-5):

**State detection without manifest**: The skill reads the user's existing `~/.claude/settings.json` and diffs it against what cortex-command contributes. No separate tracking file needed — presence of hook entries, permission patterns, etc. is detectable directly.

**Required hooks — merged unconditionally** (no question asked):
`sync-permissions.py`, `scan-lifecycle.sh`, `cortex-validate-commit.sh`, `cortex-skill-edit-advisor.sh`, `cortex-tool-failure-tracker.sh`, `cortex-cleanup-session.sh`, `cortex-permission-audit-log.sh`, `cortex-worktree-create.sh`, `cortex-worktree-remove.sh`

**Optional hooks — asked separately**:
- `cortex-setup-gpg-sandbox-home.sh` — GPG/sandbox, macOS-specific
- `cortex-notify.sh` + `cortex-notify-remote.sh` — notifications, require local infrastructure

**Per-category opt-in** (each shows current value and what would change; Y/n per component):
- Deny rules — safety rules (sudo, rm -rf, force push, reading secrets); recommended yes
- Allow list — git, bash utils, gh, brew, docker, etc.; shown as delta over what user already has
- Sandbox network config — allowed domains + excludedCommands + autoAllowBashIfSandboxed
- StatusLine — cortex-command statusline script
- Plugins — context7, claude-md-management
- apiKeyHelper — stub reference pointing to `~/.claude/get-api-key.sh`

**Never touched**: model, effortLevel, alwaysThinkingEnabled, skipDangerousModePermissionPrompt, cleanupPeriodDays, attribution, env/experimental flags, sandbox.enabled, sandbox.filesystem.allowWrite

**Conflict handling**: if user's existing deny rules contradict cortex-command's allow list (or vice versa), surface for manual resolution — do not auto-merge.

**JSON write safety**: write to a `.tmp` file, parse-validate the result (confirm valid JSON), then `mv` atomically. If validation fails, abort and report — never leave `settings.json` in partial state.

## Acceptance Criteria

- Skill is local (`.claude/skills/setup-merge/`) and not deployed globally
- Required hooks merged without prompting; optional hooks asked with clear description of what they do
- Per-category questions each show current value and proposed change before asking
- Components already present shown as "already installed" and skipped
- deny/allow contradictions surfaced for manual resolution, not silently resolved
- Personal scalar settings untouched after merge
- `settings.json` write is atomic: tmp file → validate JSON → mv; interrupted write leaves original intact
- Running the skill twice is idempotent (second run shows everything as "already installed")
