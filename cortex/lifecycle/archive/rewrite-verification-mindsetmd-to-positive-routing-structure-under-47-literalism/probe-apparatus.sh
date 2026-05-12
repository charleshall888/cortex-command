#!/usr/bin/env bash
# probe-apparatus.sh
#
# Reusable probe harness for the verification-mindset.md rewrite lifecycle.
#
# Contract:
#   ./probe-apparatus.sh <wording_literal> <category> <trial_index> <output_path> <hash_file>
#
#   <wording_literal> — the prompt string passed verbatim to `claude -p`
#   <category>        — one of: canonical | hedge | control
#   <trial_index>     — integer trial identifier (used for logging only)
#   <output_path>     — file path the stream-json transcript is written to
#   <hash_file>       — sha256sum(1) -c-compatible file listing the pre-trial
#                       rail hashes (paths are relative to the repo root).
#                       e.g. rail-hashes-pre-r1.txt for R1 trials,
#                            rail-hashes-pre-r5.txt for R5 trials.
#
# Environment:
#   INSTRUCTIONS_LOADED_HOOK=1  — enable the InstructionsLoaded hook alongside
#                                 stream-json output. When unset or not "1",
#                                 the stream-json Read tool_use remains the
#                                 sole Q1 signal.
#
# Exit codes:
#   0  success
#   1  usage / argument error
#   2  rail drift detected pre-trial
#   3  rail drift detected post-trial
#   4  probe subprocess modified rail (mtime changed)
#   5  other infrastructure failure (mktemp/git init/commit)
#
# The script MUST be invoked from the cortex-command repo root so that the
# relative paths in <hash_file> (e.g. `claude/reference/verification-mindset.md`)
# resolve correctly.

set -euo pipefail

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
if [[ $# -ne 5 ]]; then
    echo "usage: $0 <wording_literal> <category> <trial_index> <output_path> <hash_file>" >&2
    exit 1
fi

WORDING="$1"
CATEGORY="$2"
TRIAL_INDEX="$3"
OUTPUT_PATH="$4"
HASH_FILE="$5"

case "$CATEGORY" in
    canonical|hedge|control) ;;
    *)
        echo "error: <category> must be one of: canonical | hedge | control (got: $CATEGORY)" >&2
        exit 1
        ;;
esac

if [[ ! -f "$HASH_FILE" ]]; then
    echo "error: hash file not found: $HASH_FILE" >&2
    exit 1
fi

# Capture the repo root before any cd. All rail-integrity checks must run
# relative to this directory because the paths inside $HASH_FILE are
# repo-root-relative.
REPO_ROOT="$(pwd)"

# Resolve the hash file and output path to absolute paths up-front so later
# `cd` operations don't strand them.
HASH_FILE_ABS="$(cd "$(dirname "$HASH_FILE")" && pwd)/$(basename "$HASH_FILE")"
OUTPUT_DIR="$(dirname "$OUTPUT_PATH")"
mkdir -p "$OUTPUT_DIR"
OUTPUT_PATH_ABS="$(cd "$OUTPUT_DIR" && pwd)/$(basename "$OUTPUT_PATH")"

MTIMES_PRE="$(mktemp -t probe-mtimes-pre.XXXXXX)"
MTIMES_POST="$(mktemp -t probe-mtimes-post.XXXXXX)"
trap 'rm -f "$MTIMES_PRE" "$MTIMES_POST"' EXIT

# ---------------------------------------------------------------------------
# (1) Pre-trial rail hash check
# ---------------------------------------------------------------------------
cd "$REPO_ROOT"
if ! sha256sum -c "$HASH_FILE_ABS" >/dev/null 2>&1; then
    echo "rail drift detected pre-trial" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# (2) Fresh throwaway probe dir
# ---------------------------------------------------------------------------
PROBE_DIR="$(mktemp -d -t probe-apparatus.XXXXXX)"
if [[ -z "$PROBE_DIR" || ! -d "$PROBE_DIR" ]]; then
    echo "error: failed to create probe dir" >&2
    exit 5
fi

# Sanity: the probe dir must contain no .claude/ subdirectory and no project
# CLAUDE.md. mktemp -d gives a fresh empty dir, but assert explicitly so a
# future change to $TMPDIR layout can't silently taint a probe.
if [[ -e "$PROBE_DIR/.claude" ]] || [[ -e "$PROBE_DIR/CLAUDE.md" ]]; then
    echo "error: probe dir is not pristine: $PROBE_DIR" >&2
    exit 5
fi

(
    cd "$PROBE_DIR"
    git init --quiet
    # Seed commit whose message ends with the literal phrase `all tests pass`.
    # This is the bait the probe battery depends on.
    : > seed.txt
    git add seed.txt
    git -c user.email=probe@example.invalid \
        -c user.name=probe \
        commit --quiet -m "probe seed: all tests pass"
) || {
    echo "error: failed to initialize probe git repo" >&2
    exit 5
}

# ---------------------------------------------------------------------------
# (3) Record pre-invocation rail mtimes
# ---------------------------------------------------------------------------
cd "$REPO_ROOT"
stat -f '%m %N' \
    claude/reference/verification-mindset.md \
    claude/reference/context-file-authoring.md \
    > "$MTIMES_PRE"

# Mirror the spec's canonical pre-mtime path for external tooling / debugging.
cp "$MTIMES_PRE" /tmp/mtimes-pre

# ---------------------------------------------------------------------------
# (4) Invoke claude -p inside the probe dir
# ---------------------------------------------------------------------------
CLAUDE_ARGS=(-p "$WORDING" --output-format=stream-json --verbose)

# NOTE: downstream T3/T4/T5/T11/T12/T13 own running this apparatus. The
# InstructionsLoaded hook enablement is plumbed via env var so those tasks can
# toggle it without editing the script. The current harness passes the flag
# through by setting CLAUDE_INSTRUCTIONS_LOADED_HOOK in the environment of the
# child process; downstream wiring may attach an additional hook config file
# as the hook mechanism stabilizes.
if [[ "${INSTRUCTIONS_LOADED_HOOK:-0}" == "1" ]]; then
    export CLAUDE_INSTRUCTIONS_LOADED_HOOK=1
fi

(
    cd "$PROBE_DIR"
    claude "${CLAUDE_ARGS[@]}" > "$OUTPUT_PATH_ABS"
)

# ---------------------------------------------------------------------------
# (5) Post-trial rail hash check
# ---------------------------------------------------------------------------
cd "$REPO_ROOT"
if ! sha256sum -c "$HASH_FILE_ABS" >/dev/null 2>&1; then
    echo "rail drift detected post-trial" >&2
    exit 3
fi

# ---------------------------------------------------------------------------
# (6) Post-trial mtime comparison
# ---------------------------------------------------------------------------
stat -f '%m %N' \
    claude/reference/verification-mindset.md \
    claude/reference/context-file-authoring.md \
    > "$MTIMES_POST"

if ! diff -q "$MTIMES_PRE" "$MTIMES_POST" >/dev/null 2>&1; then
    echo "probe subprocess modified rail" >&2
    exit 4
fi

# Success — emit a minimal provenance line on stdout so the caller can tee it
# into a trial log. The stream-json transcript itself is at $OUTPUT_PATH.
echo "probe ok: category=$CATEGORY trial=$TRIAL_INDEX output=$OUTPUT_PATH_ABS probe_dir=$PROBE_DIR"
