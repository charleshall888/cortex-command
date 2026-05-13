#!/usr/bin/env bash
# Post-trim anchor check for Task 15 (R10, R11).
#
# Verifies every anchor enumerated in trim-anchor-audit.md is still
# resolvable in the trimmed cortex/requirements/project.md. Exits 0 on
# all-pass, 1 on any miss.
#
# Usage:
#   bash cortex/lifecycle/requirements-skill-v2/scripts/post-trim-anchor-check.sh
#
# Lives in the lifecycle dir as documentation of the post-trim verification;
# not wired into the runner.

set -euo pipefail

FILE="cortex/requirements/project.md"
if [ ! -f "$FILE" ]; then
  echo "error: $FILE not found" >&2
  exit 1
fi

ANCHORS=(
  '^## Overview$'
  '^## Philosophy of Work$'
  'Solution horizon'
  '^## Architectural Constraints$'
  'skill-helper'
  'size cap'
  'Per-repo sandbox registration'
  'SKILL.md-to-bin parity'
  'File-based state'
  '^## Quality Attributes$'
  'Graceful partial failure'
  'Defense-in-depth'
  'Maintainability through simplicity'
  'Iterative improvement'
  'Destructive operations'
  '^## Project Boundaries$'
  '### In Scope'
  '### Out of Scope'
  '### Deferred'
  'Published packages'
  '^## Conditional Loading$'
  'multi-agent'
  'observability'
  'pipeline'
  'remote-access'
  '^## Optional$'
  'Sandbox preflight gate'
  'Two-mode gate pattern'
  'Workflow trimming'
)

fail=0
for pattern in "${ANCHORS[@]}"; do
  count=$(grep -ciE "$pattern" "$FILE" || true)
  if [ "${count:-0}" -ge 1 ]; then
    echo "PASS: $pattern (matches=$count)"
  else
    echo "FAIL: $pattern" >&2
    fail=1
  fi
done

if [ "$fail" -ne 0 ]; then
  echo "post-trim anchor check: one or more anchors unresolved" >&2
  exit 1
fi

echo "post-trim anchor check: all anchors resolvable in $FILE"
