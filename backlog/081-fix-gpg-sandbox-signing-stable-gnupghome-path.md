---
id: 081
title: Fix GPG sandbox signing with stable gnupghome path and read-only options
type: feature
status: ready
priority: high
tags: [gpg, sandbox, hooks, signing]
created: 2026-04-13
updated: 2026-04-13
discovery_source: research/gpg-signing-claude-code-sandbox/research.md
---

# Fix GPG sandbox signing with stable gnupghome path and read-only options

## Problem

GPG commit signing has been silently broken in all sandboxed Claude Code sessions since initial deployment. The `cortex-setup-gpg-sandbox-home.sh` SessionStart hook always exits early without creating the gnupghome directory because it detects sandbox context by checking `$TMPDIR` against `/tmp/claude*` patterns — but hooks run outside the sandbox and see the macOS system TMPDIR (`/var/folders/...`) instead. The commit skill then tests `$TMPDIR/gnupghome/S.gpg-agent` inside a sandboxed Bash call (where TMPDIR is `/tmp/claude-503`), always finds it missing, and commits without GPG signing.

## Research Context

Research confirmed (via diagnostic logging and Claude Code docs investigation):

- **Hooks are not sandboxed**: SessionStart hooks run in the host process environment. TMPDIR is the macOS system default, never the sandbox TMPDIR. There is no documented mechanism for hooks to discover the sandbox TMPDIR.
- **Stable path is accessible**: `~/.local/share/gnupg/` is not in the sandbox read deny list. A gnupghome created there by the hook (outside sandbox) can be read by sandboxed `git commit`.
- **Write access is not needed**: With Assuan socket redirect and `no-autostart`, all signing is delegated to the external agent. Adding `no-random-seed-file`, `no-auto-check-trustdb`, and `lock-never` to gpg.conf makes GNUPGHOME fully read-only during signing — no sandbox write allowlist changes required.
- **CLAUDE_ENV_FILE**: Real mechanism available since v2.1.45+. The hook already has code to write GNUPGHOME to it (lines 111–113), but it was unreachable due to the early exit. Keep it after the fix as a bonus; don't depend on it as the primary detection mechanism (known resume bug: issue #24775).

## Scope

Changes to:
- `~/.claude/hooks/cortex-setup-gpg-sandbox-home.sh` (symlinked from `hooks/cortex-setup-gpg-sandbox-home.sh`)
- `~/.claude/skills/commit/SKILL.md` (symlinked from `skills/commit/SKILL.md`)

Also remove the diagnostic `echo` line added during investigation (hook line that writes TMPDIR to `~/.claude/debug/gpg-setup.log`).
