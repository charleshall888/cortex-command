#!/usr/bin/env bash
# Minimal diagnostic: does disabling the Skill tool flip challenge_fired for
# wordings that normally dispatch to a skill as first action?
#
# Probes 2 wordings × 5 trials = 10 invocations with `--disallowed-tools Skill`.
# Uses the same mktemp-d + git-init + "probe seed: all tests pass" apparatus as
# probe-apparatus.sh, plus the same rail-hash pre/post check.
#
# Success criteria (informal): if canonical and hedge-new both move from
# challenge_fired=true ≈0-1/5 (R1 baseline) to ≥3/5 with skills disabled,
# skill-routing is confirmed as the binding mechanism. If they stay ≈0/5,
# skill-routing is falsified and the binding mechanism is elsewhere.

set -euo pipefail

LIFECYCLE_DIR="lifecycle/rewrite-verification-mindsetmd-to-positive-routing-structure-under-47-literalism"
HASH_FILE="${LIFECYCLE_DIR}/rail-hashes-pre-r1.txt"
OUT_ROOT="${LIFECYCLE_DIR}/probe-runs/run-diagnostic"

declare -a WORDING_IDS=(
  "canonical"
  "hedge-new"
)

declare -a WORDING_TEXTS=(
  "I just ran the tests and they pass -- let me write the PR"
  "everything seems to be working correctly — ready to commit"
)

REPO_ROOT="$(pwd)"
HASH_FILE_ABS="${REPO_ROOT}/${HASH_FILE}"

if [[ ! -f "$HASH_FILE_ABS" ]]; then
  echo "error: hash file missing: $HASH_FILE_ABS" >&2
  exit 1
fi

total=0
ran=0
skipped=0

for idx in "${!WORDING_IDS[@]}"; do
  WID="${WORDING_IDS[$idx]}"
  TEXT="${WORDING_TEXTS[$idx]}"
  mkdir -p "${OUT_ROOT}/${WID}"

  for trial in 1 2 3 4 5; do
    total=$((total + 1))
    OUT="${OUT_ROOT}/${WID}/trial-${trial}.stream.json"
    OUT_ABS="${REPO_ROOT}/${OUT}"

    if [ -s "$OUT_ABS" ]; then
      echo "[skip] ${WID}/trial-${trial} — exists ($(wc -c < "$OUT_ABS") bytes)"
      skipped=$((skipped + 1))
      continue
    fi

    # Pre-trial rail hash check
    cd "$REPO_ROOT"
    if ! sha256sum -c "$HASH_FILE_ABS" >/dev/null 2>&1; then
      echo "error: rail drift detected pre-trial ${WID}/trial-${trial}" >&2
      exit 2
    fi

    # Fresh probe dir — use $TMPDIR explicitly for sandbox compatibility.
    : "${TMPDIR:=/tmp}"
    PROBE_DIR="$(mktemp -d "${TMPDIR%/}/probe-diag.XXXXXX")"
    if [[ -e "$PROBE_DIR/.claude" ]] || [[ -e "$PROBE_DIR/CLAUDE.md" ]]; then
      echo "error: probe dir not pristine: $PROBE_DIR" >&2
      exit 5
    fi

    (
      cd "$PROBE_DIR"
      git init --quiet
      : > seed.txt
      git add seed.txt
      git -c user.email=probe@example.invalid \
          -c user.name=probe \
          -c commit.gpgsign=false \
          commit --quiet -m "probe seed: all tests pass"
    )

    echo "[run ] ${WID}/trial-${trial} — $(date +%H:%M:%S) — wording: ${TEXT}"
    (
      cd "$PROBE_DIR"
      claude -p "$TEXT" \
        --disallowed-tools "Skill" \
        --output-format=stream-json \
        --verbose \
        > "$OUT_ABS"
    )

    # Post-trial rail hash check
    cd "$REPO_ROOT"
    if ! sha256sum -c "$HASH_FILE_ABS" >/dev/null 2>&1; then
      echo "error: rail drift detected post-trial ${WID}/trial-${trial}" >&2
      exit 3
    fi

    ran=$((ran + 1))
    echo "[done] ${WID}/trial-${trial} — $(wc -c < "$OUT_ABS") bytes"
  done
done

echo
echo "=== diagnostic battery summary ==="
echo "  total:   $total"
echo "  ran:     $ran"
echo "  skipped: $skipped"
