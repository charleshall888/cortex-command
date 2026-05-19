#!/bin/bash
set -euo pipefail
command -v cortex >/dev/null || exit 0
input=$(cat)
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
[[ -d "$cwd/cortex/lifecycle" ]] || exit 0
# Probe subcommand presence; absent on older CLIs → silent skip (no version-skew assumption).
cortex hooks scan-lifecycle --help >/dev/null 2>&1 || exit 0
printf '%s' "$input" | exec cortex hooks scan-lifecycle
