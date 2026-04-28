#!/usr/bin/env bash
# R16 first-run-green dry-run gate for the SKILL.md-to-bin parity linter.
#
# Per spec R16, the day-zero baseline must exit 0 cleanly under the
# default-mode linter run. This script is the mechanically reproducible
# form of that check; it is human-attended on day one (the maintainer
# reads the output before committing) and after day zero is a strict
# subset of the Phase 1.5 pre-commit hook.
#
# Lifecycle 102 (DR-5 parity linter) Task 12.

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

python3 bin/cortex-check-parity
