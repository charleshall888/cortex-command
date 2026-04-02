#!/usr/bin/env bash
# Stub apiKeyHelper — delegates to a local override if present,
# otherwise exits 0 with no output (subscription billing fallback).

local_script="$HOME/.claude/get-api-key-local.sh"

if [[ -x "$local_script" ]]; then
  exec "$local_script" "$@"
fi

exit 0
