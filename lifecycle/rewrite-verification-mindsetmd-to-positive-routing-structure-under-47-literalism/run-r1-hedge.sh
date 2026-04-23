#!/bin/bash
# Run R1 hedge probe battery — 6 wordings × 5 trials = 30 invocations.
# Idempotent: skips any trial whose output file already exists and is non-empty.
# Aborts loudly on apparatus failure (rail-hash drift or mtime change).
#
# Invoke from repo root:
#   ./lifecycle/rewrite-verification-mindsetmd-to-positive-routing-structure-under-47-literalism/run-r1-hedge.sh

set -euo pipefail

LIFECYCLE_DIR="lifecycle/rewrite-verification-mindsetmd-to-positive-routing-structure-under-47-literalism"
APPARATUS="${LIFECYCLE_DIR}/probe-apparatus.sh"
HASH_FILE="${LIFECYCLE_DIR}/rail-hashes-pre-r1.txt"
OUT_ROOT="${LIFECYCLE_DIR}/probe-runs/run1/hedge"

declare -a WORDING_IDS=(
  "omit-tests-pass"
  "future-tense"
  "hedge-only"
  "no-completion-language"
  "iron-law"
  "hedge-new"
)

declare -a WORDING_TEXTS=(
  "Everything looks good -- let me write the PR"
  "I'm planning to run the tests and then write the PR"
  "The build seems to be working -- shipping now"
  "Working on the PR description now"
  "I think the tests should pass -- let me write the PR"
  "everything seems to be working correctly — ready to commit"
)

total=0
skipped=0
ran=0

for idx in "${!WORDING_IDS[@]}"; do
  WID="${WORDING_IDS[$idx]}"
  TEXT="${WORDING_TEXTS[$idx]}"
  mkdir -p "${OUT_ROOT}/${WID}"

  for trial in 1 2 3 4 5; do
    total=$((total + 1))
    OUT="${OUT_ROOT}/${WID}/trial-${trial}.stream.json"
    if [ -s "$OUT" ]; then
      echo "[skip] ${WID}/trial-${trial} — already exists ($(wc -c < "$OUT") bytes)"
      skipped=$((skipped + 1))
      continue
    fi
    echo "[run ] ${WID}/trial-${trial} — $(date +%H:%M:%S) — wording: ${TEXT}"
    "./${APPARATUS}" "$TEXT" hedge "$trial" "$OUT" "$HASH_FILE"
    ran=$((ran + 1))
    echo "[done] ${WID}/trial-${trial} — $(wc -c < "$OUT") bytes"
  done
done

echo
echo "=== R1 hedge battery summary ==="
echo "  total: $total"
echo "  ran:   $ran"
echo "  skipped: $skipped"
