#!/bin/bash
# SessionStart hook: construct a minimal GNUPGHOME in $TMPDIR for sandboxed sessions.
#
# Problem: Claude Code's sandbox blocks access to ~/.gnupg, so git commit -S
# (GPG signing) fails. Private key material must never enter the sandbox.
#
# Solution: create a minimal GNUPGHOME in $TMPDIR/gnupghome/ that contains:
#   - S.gpg-agent    Assuan redirect pointing to the extra socket
#   - pubring.kbx    Public key (binary export)
#   - gpg.conf       no-autostart (prevents agent spawn inside sandbox)
#
# Note: common.conf is intentionally omitted. GnuPG 2.4.x falls back to
# direct keybox access when keyboxd is not running; no opt-out config needed.
#
# The extra socket lives at a stable path outside ~/.gnupg, whitelisted in
# sandbox.network.allowUnixSockets. All crypto operations happen in gpg-agent
# running outside the sandbox; only the public key and socket redirect are
# inside $TMPDIR.
#
# This hook runs at SessionStart (outside the sandbox). The commit skill then
# passes GNUPGHOME=$TMPDIR/gnupghome inline when invoking git commit.
set -euo pipefail

INPUT=$(cat)

# --- Sandbox detection ---
# Only act in Claude sessions. Claude sets $TMPDIR to /tmp/claude (symlink to
# /private/tmp/claude) for all sandboxed sessions. Check both the symlink form
# and the resolved form to catch both /tmp/claude* and /private/tmp/claude*.
if [[ "${TMPDIR:-}" != /private/tmp/claude* && "${TMPDIR:-}" != /tmp/claude* ]]; then
  exit 0
fi

# --- Configuration ---
SIGNING_KEY=$(git config --global user.signingkey 2>/dev/null || true)
if [[ -z "$SIGNING_KEY" ]]; then
  echo "setup-gpg-sandbox-home: user.signingkey not set in git config" >&2
  exit 0
fi
EXTRA_SOCKET="$HOME/.local/share/gnupg/S.gpg-agent.sandbox"
GNUPG_HOME="$TMPDIR/gnupghome"

# --- Ensure gpg-agent is running with the extra socket ---
# The extra socket directory must exist
EXTRA_SOCKET_DIR=$(dirname "$EXTRA_SOCKET")
if [[ ! -d "$EXTRA_SOCKET_DIR" ]]; then
  mkdir -p "$EXTRA_SOCKET_DIR"
  chmod 0700 "$EXTRA_SOCKET_DIR"
fi

if [[ ! -S "$EXTRA_SOCKET" ]]; then
  # Start gpg-agent; it reads its config for extra-socket from gpg-agent.conf
  gpg-agent --daemon 2>/dev/null || true

  # Wait briefly for the extra socket to appear (up to 3 seconds)
  for i in 1 2 3 4 5 6; do
    if [[ -S "$EXTRA_SOCKET" ]]; then
      break
    fi
    sleep 0.5
  done

  if [[ ! -S "$EXTRA_SOCKET" ]]; then
    echo "setup-gpg-sandbox-home: extra socket not found at $EXTRA_SOCKET after waiting" >&2
    echo "setup-gpg-sandbox-home: gpg signing will not work in this session" >&2
    exit 0
  fi
fi

# --- Construct minimal GNUPGHOME ---
SIGNING_KEY_FILE="$EXTRA_SOCKET_DIR/signing-key.pgp"

# 1. Missing-file guard: signing key must be pre-cached by `just setup-gpg-sandbox`
if [[ ! -f "$SIGNING_KEY_FILE" ]]; then
  echo "setup-gpg-sandbox-home: signing key file not found at $SIGNING_KEY_FILE" >&2
  echo "setup-gpg-sandbox-home: run 'just setup-gpg-sandbox' to create it" >&2
  exit 0
fi

# 2. Check-before-clean: if gnupghome already has the key, skip rebuild (fast path)
if GNUPGHOME="$GNUPG_HOME" gpg --list-keys "$SIGNING_KEY" >/dev/null 2>&1; then
  exit 0
fi

# 3. Cleanup and recreate
rm -rf "$GNUPG_HOME"
mkdir -p "$GNUPG_HOME"
chmod 0700 "$GNUPG_HOME"

# 4. Write gpg.conf before any GPG command touches GNUPGHOME
printf 'no-autostart\n' > "$GNUPG_HOME/gpg.conf"
chmod 0600 "$GNUPG_HOME/gpg.conf"

# 5. Import public key from pre-cached file
GNUPGHOME="$GNUPG_HOME" gpg --import "$SIGNING_KEY_FILE" || true

# 6. Post-import verification: remove gnupghome on failure
if ! GNUPGHOME="$GNUPG_HOME" gpg --list-keys "$SIGNING_KEY" >/dev/null 2>&1; then
  rm -rf "$GNUPG_HOME"
  echo "setup-gpg-sandbox-home: key import failed — gnupghome removed" >&2
  echo "setup-gpg-sandbox-home: run 'just setup-gpg-sandbox' to re-export the key" >&2
  exit 0
fi

# 7. Assuan redirect file: tells GPG client to connect to the extra socket
# Format: exactly two lines, each \n-terminated, total max 511 bytes
printf '%s\n%s\n' '%Assuan%' "socket=$EXTRA_SOCKET" > "$GNUPG_HOME/S.gpg-agent"
chmod 0600 "$GNUPG_HOME/S.gpg-agent"

# --- Export GNUPGHOME into the session environment ---
if [[ -n "${CLAUDE_ENV_FILE:-}" ]]; then
  echo "export GNUPGHOME=$GNUPG_HOME" >> "$CLAUDE_ENV_FILE"
fi

exit 0
