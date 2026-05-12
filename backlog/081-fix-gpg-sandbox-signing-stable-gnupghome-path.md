---
id: 081
title: Fix GPG sandbox signing with stable gnupghome path and read-only options
type: feature
status: complete
priority: high
tags: [gpg, sandbox, hooks, signing]
created: 2026-04-13
updated: 2026-04-13
discovery_source: cortex/research/gpg-signing-claude-code-sandbox/research.md
---

# Fix GPG sandbox signing with stable gnupghome path and read-only options

## Resolution: scaffolding deleted (2026-04-13)

Closed without implementing the proposed fix. The premise was wrong.

`claude/settings.json` → `sandbox.excludedCommands` lists `git:*`, which excludes the entire git process tree from the Seatbelt sandbox — including pre-commit hooks and spawned `gpg -bsau`. git children see the host TMPDIR and have unrestricted access to `~/.gnupg/` and the standard `S.gpg-agent` socket. Signing has always worked via the host gpg-agent; the sandbox `GNUPGHOME` redirect scheme was solving a problem that did not exist.

Direct `gpg` invocations from Bash are sandboxed; git-spawned gpg is not. That asymmetry hid the truth from the original investigation.

**Deleted:**
- `claude/hooks/cortex-setup-gpg-sandbox-home.sh` SessionStart hook and its registration in `claude/settings.json`
- `Bash(GNUPGHOME=* git commit *)` entry in `claude/settings.json` allow list
- `~/.local/share/gnupg/S.gpg-agent.sandbox` entry in `sandbox.network.allowUnixSockets`
- Step 5 (sandbox signing check) and Step 6's GNUPGHOME-prefix variants in `skills/commit/SKILL.md`
- `setup-gpg-sandbox` recipe in `justfile` and its `check-symlinks` line
- `cortex-setup-gpg-sandbox-home.sh` references in `docs/setup.md`, `docs/agentic-layer.md`, `.claude/skills/setup-merge/SKILL.md`, `.claude/skills/setup-merge/scripts/merge_settings.py`

The correction note on `research/gpg-signing-claude-code-sandbox/research.md` explains what the original research missed for future readers. Cached host-side artifacts (`~/.local/share/gnupg/signing-key.pgp`, `~/.local/share/gnupg/S.gpg-agent.sandbox`, `gpg-agent.conf` extra-socket line) were left in place — they're harmless and can be removed by hand if desired.

## Original problem statement (preserved)

GPG commit signing has been silently broken in all sandboxed Claude Code sessions since initial deployment. The `cortex-setup-gpg-sandbox-home.sh` SessionStart hook always exits early without creating the gnupghome directory because it detects sandbox context by checking `$TMPDIR` against `/tmp/claude*` patterns — but hooks run outside the sandbox and see the macOS system TMPDIR (`/var/folders/...`) instead.

The premise was wrong: signing was never broken. Every commit in `git log` showed `G` (good signature). The fix was to delete the dead scaffolding, not implement a replacement.
