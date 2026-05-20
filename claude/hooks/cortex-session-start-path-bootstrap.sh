#!/bin/bash
# SessionStart hook: PATH bootstrap for cortex-shaped repos.
# Prepends the dominant cortex-tool bin layouts to PATH so console scripts
# (cortex-worktree-resolve, etc.) are reachable from the first tool call in
# any session, including those started via macOS Dock/Finder where launchd
# provides a minimal PATH that excludes user-site bin directories.
#
# Cortex-shape gate: exits 0 silently if $CWD/cortex/lifecycle/ does not
# exist, matching the gate at hooks/cortex-scan-lifecycle.sh:29. This
# prevents PATH mutation in non-cortex repos.
#
# Emits the augmented PATH via $CLAUDE_ENV_FILE (Claude Code's hook output
# contract for environment variables in SessionStart hooks).

set -euo pipefail

INPUT=$(cat)

CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
[[ -n "$CWD" ]] || CWD="$(pwd)"

LIFECYCLE_DIR="$CWD/cortex/lifecycle"

# Cortex-shape gate: no cortex/lifecycle directory — nothing to do
[[ -d "$LIFECYCLE_DIR" ]] || exit 0

# Build the augmented PATH and write it to CLAUDE_ENV_FILE so Claude Code
# (and the owning session's Bash tool) picks it up on the first tool call.
AUGMENTED_PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:${PATH:-}"

PATH="$AUGMENTED_PATH" python3 -m cortex_command.doctor.path_self_test 2>/dev/null || true

if [[ -n "${CLAUDE_ENV_FILE:-}" ]]; then
  echo "export PATH='$AUGMENTED_PATH'" >> "$CLAUDE_ENV_FILE"
fi

exit 0
