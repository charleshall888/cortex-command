#!/bin/bash
# SessionStart hook: inject GitHub PATs into sandboxed sessions.
#
# Problem: Claude Code's sandbox denies access to ~/.config/gh/ and
# ~/.git-credentials, so `gh` CLI operations fail with auth errors.
#
# Solution: read PATs from ~/.config/claude-code-secrets/ at session start and
# write them to /tmp/claude/ where skills can read them.
#
# Note: hooks run BEFORE the sandbox is initialized, so $TMPDIR is unset.
# Always write to hardcoded /tmp/claude/ — the path skills read from.
# Keychain (security command) is also inaccessible in sandbox (exits 44), so
# PATs are read from files written by just setup-github-pat / setup-github-pat-org.
#
# PAT files are written to /tmp/claude/ as fallback infrastructure only.
# GH_TOKEN is NOT injected into the session env — native gh OAuth handles auth.
# Injecting GH_TOKEN would override the SSO-authorized OAuth token and break
# git fetch/push on private org repos via the gh auth git-credential helper.
#
# Output channels (personal PAT):
#   1. /tmp/claude/github-pat (chmod 0600) — fallback, not used by default
#
# Output channels (org PAT):
#   1. /tmp/claude/github-pat-org (chmod 0600) — fallback, not used by default
#
# This hook must exit 0 in all cases — a non-zero exit would block the session.
set -uo pipefail

INPUT=$(cat)

# Hooks run before the sandbox is initialized, so $TMPDIR is unset/system default.
# Write directly to the known sandbox path that skills read from.
SANDBOX_TMP="/tmp/claude"
mkdir -p "$SANDBOX_TMP"

# --- Personal PAT: read from file (optional — missing file is non-fatal) ---
PAT_FILE="$HOME/.config/claude-code-secrets/github-pat"
if [[ -f "$PAT_FILE" ]]; then
  PAT=$(cat "$PAT_FILE")
  if [[ -n "$PAT" ]]; then
    printf '%s' "$PAT" > "$SANDBOX_TMP/github-pat"
    chmod 0600 "$SANDBOX_TMP/github-pat"
  fi
else
  echo "setup-github-pat: no personal PAT at $PAT_FILE — run \`just setup-github-pat\` if needed" >&2
fi

# --- Org PAT: read from file (optional — missing file is non-fatal) ---
PAT_ORG_FILE="$HOME/.config/claude-code-secrets/github-pat-org"
if [[ -f "$PAT_ORG_FILE" ]]; then
  PAT_ORG=$(cat "$PAT_ORG_FILE")
  if [[ -n "$PAT_ORG" ]]; then
    printf '%s' "$PAT_ORG" > "$SANDBOX_TMP/github-pat-org"
    chmod 0600 "$SANDBOX_TMP/github-pat-org"
  else
    rm -f "$SANDBOX_TMP/github-pat-org"
  fi
else
  # Clean up any stale file from a prior session
  rm -f "$SANDBOX_TMP/github-pat-org"
fi

exit 0
