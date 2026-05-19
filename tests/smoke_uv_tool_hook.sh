#!/bin/bash
# tests/smoke_uv_tool_hook.sh — uv-tool topology smoke test for the
# cortex-scan-lifecycle hook (spec req #7).
#
# Topology guard: this script only runs the assertions when `cortex`
# resolves into a uv-tool-managed venv (share/uv/tools/cortex-command/).
# On any other topology (dev-checkout, system install, missing cortex)
# it prints a clear skip message plus a suggested setup command and
# exits 0 — so `just test-smoke-hook` is safe in the default aggregator
# but only meaningful on a real uv-tool install.
#
# When the topology check passes, the script stages each of the six
# golden lifecycle fixtures, pipes the SessionStart JSON through the
# bash wrapper `hooks/cortex-scan-lifecycle.sh` (which in turn calls
# the installed `cortex hooks scan-lifecycle` subcommand), and diffs
# the extracted `hookSpecificOutput.additionalContext` against the
# golden expected text byte-for-byte. Any divergence is a fatal
# failure — this is the end-to-end topology-gap closure for the
# install-topology bug that Tasks 1-16 verified only under dev
# checkout.

set -euo pipefail

# --- Topology detection ----------------------------------------------------

if ! command -v cortex >/dev/null 2>&1; then
    echo "SKIP: \`cortex\` not on PATH; cannot verify uv-tool topology."
    echo "      To set up a uv-tool install for verification, run:"
    echo "          uv tool install git+https://github.com/charleshall888/cortex-command.git"
    exit 0
fi

CORTEX_RESOLVED="$(realpath "$(command -v cortex)")"
case "$CORTEX_RESOLVED" in
    *share/uv/tools/cortex-command*)
        ;; # On a uv-tool install — proceed with assertions.
    *)
        echo "SKIP: \`cortex\` resolves to $CORTEX_RESOLVED — not a uv-tool install."
        echo "      The smoke test only runs assertions under a uv-tool topology"
        echo "      (cortex resolving into share/uv/tools/cortex-command/...). To"
        echo "      stage a uv-tool install for verification, run:"
        echo "          uv tool install git+https://github.com/charleshall888/cortex-command.git"
        echo "      then re-run \`just test-smoke-hook\`."
        exit 0
        ;;
esac

# Subcommand-presence probe: the installed `cortex` CLI may pre-date the
# `hooks scan-lifecycle` subcommand (the wrapper's probe-then-exec
# pattern silently degrades in that case). Without the subcommand we
# can't exercise the chain this smoke test is designed to verify, so
# treat that as a skip with a clear setup suggestion.
if ! cortex hooks scan-lifecycle --help >/dev/null 2>&1; then
    echo "SKIP: \`cortex hooks scan-lifecycle\` subcommand not present in the"
    echo "      currently-installed uv-tool cortex at $CORTEX_RESOLVED."
    echo "      Upgrade the installed CLI to a version that ships the"
    echo "      subcommand before re-running this smoke test, e.g.:"
    echo "          uv tool install --force git+https://github.com/charleshall888/cortex-command.git"
    exit 0
fi

# --- Locate repo + fixtures ------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WRAPPER="$REPO_ROOT/hooks/cortex-scan-lifecycle.sh"
FIXTURE_DIR="$REPO_ROOT/tests/fixtures/hooks/scan_lifecycle"

if [[ ! -f "$WRAPPER" ]]; then
    echo "ERROR: wrapper not found at $WRAPPER" >&2
    exit 1
fi
if [[ ! -d "$FIXTURE_DIR" ]]; then
    echo "ERROR: fixture dir not found at $FIXTURE_DIR" >&2
    exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
    echo "ERROR: jq is required (brew install jq)" >&2
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required (the staging helper uses tests/_hook_fixture_helpers.py)" >&2
    exit 1
fi

# --- Per-case staging via inline Python (reuses tests/_hook_fixture_helpers) -

# Stage a tmp repo whose lifecycle state matches the named fixture case
# and echo the absolute repo path on stdout. The cases re-create exactly
# the state shapes captured in tests/test_hooks_scan_lifecycle.py's
# _stage_for_case so the emitted additionalContext matches the golden
# fixture byte-for-byte.
stage_case() {
    local case="$1"
    local tmp_root="$2"
    PYTHONPATH="$REPO_ROOT" python3 - "$case" "$tmp_root" <<'PYEOF'
import sys
from pathlib import Path

case = sys.argv[1]
tmp_root = Path(sys.argv[2])

from tests._hook_fixture_helpers import FeatureSpec, StageSpec, stage_lifecycle

if case == "a_no_lifecycle_dir":
    repo = stage_lifecycle(tmp_root, StageSpec(create_lifecycle_dir=False))
elif case == "b_single_incomplete_feature":
    repo = stage_lifecycle(
        tmp_root,
        StageSpec(features=[FeatureSpec(name="feature-b", research_md="# research\n")]),
    )
elif case == "c_multiple_incomplete_features":
    spec_approved_log = '{"event": "spec_approved"}\n'
    repo = stage_lifecycle(
        tmp_root,
        StageSpec(
            features=[
                FeatureSpec(name="feature-c1", research_md="# research c1\n"),
                FeatureSpec(name="feature-c2", research_md="# research c2\n"),
                FeatureSpec(
                    name="feature-c3",
                    research_md="# research c3\n",
                    spec_md="# spec c3\n",
                    events_log=spec_approved_log,
                ),
            ]
        ),
    )
elif case == "d_post_clear_session_migration":
    spec_approved_log = '{"event": "spec_approved"}\n'
    repo = stage_lifecycle(
        tmp_root,
        StageSpec(
            features=[
                FeatureSpec(
                    name="feature-d",
                    research_md="# research d\n",
                    spec_md="# spec d\n",
                    events_log=spec_approved_log,
                    session="OLD-SESSION-ID-d",
                )
            ]
        ),
    )
elif case == "e_morning_review_active":
    repo = stage_lifecycle(
        tmp_root,
        StageSpec(
            features=[
                FeatureSpec(name="merged-feature-e1", research_md="# research e1\n"),
                FeatureSpec(name="merged-feature-e2", research_md="# research e2\n"),
            ],
            pipeline_state={
                "phase": "complete",
                "features": {
                    "merged-feature-e1": {"status": "merged"},
                    "merged-feature-e2": {"status": "merged"},
                },
            },
        ),
    )
elif case == "f_pipeline_state_with_statuses":
    spec_approved_log = '{"event": "spec_approved"}\n'
    repo = stage_lifecycle(
        tmp_root,
        StageSpec(
            features=[
                FeatureSpec(
                    name="exec-feature-f1",
                    research_md="# research f1\n",
                    spec_md="# spec f1\n",
                    events_log=spec_approved_log,
                ),
                FeatureSpec(name="paused-feature-f2", research_md="# research f2\n"),
                FeatureSpec(name="failed-feature-f3", research_md="# research f3\n"),
            ],
            pipeline_state={
                "phase": "executing",
                "features": {
                    "exec-feature-f1": {"status": "executing"},
                    "paused-feature-f2": {"status": "paused"},
                    "failed-feature-f3": {"status": "failed"},
                },
            },
        ),
    )
else:
    print(f"unknown case: {case}", file=sys.stderr)
    sys.exit(2)

print(str(repo))
PYEOF
}

# --- Run each case ---------------------------------------------------------

NO_OUTPUT_SENTINEL=$'__NO_OUTPUT__\n'

CASES=(
    "a_no_lifecycle_dir"
    "b_single_incomplete_feature"
    "c_multiple_incomplete_features"
    "d_post_clear_session_migration"
    "e_morning_review_active"
    "f_pipeline_state_with_statuses"
)

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/cortex-smoke-uv-tool-XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT

PASSED=0
FAILED=0

for case in "${CASES[@]}"; do
    case_tmp="$TMP_ROOT/$case"
    mkdir -p "$case_tmp"

    repo="$(stage_case "$case" "$case_tmp")"

    in_fixture="$FIXTURE_DIR/$case.in.json"
    expected_fixture="$FIXTURE_DIR/$case.expected.additionalContext.txt"
    if [[ ! -f "$in_fixture" || ! -f "$expected_fixture" ]]; then
        echo "FAIL [$case]: missing fixture pair under $FIXTURE_DIR" >&2
        FAILED=$((FAILED + 1))
        continue
    fi

    # Substitute __TMPDIR__ placeholder with the staged repo path.
    stdin_json="$(jq --arg cwd "$repo" '.cwd = $cwd' "$in_fixture")"

    # Pipe through the bash wrapper. The wrapper resolves `cortex` via
    # PATH — since we asserted uv-tool topology above, that resolves
    # into share/uv/tools/cortex-command/ and exercises the topology
    # this smoke test exists to verify.
    set +e
    hook_stdout="$(printf '%s' "$stdin_json" | bash "$WRAPPER")"
    hook_rc=$?
    set -e

    if [[ $hook_rc -ne 0 ]]; then
        echo "FAIL [$case]: wrapper exited rc=$hook_rc" >&2
        echo "       stdout: ${hook_stdout:-<empty>}" >&2
        FAILED=$((FAILED + 1))
        continue
    fi

    expected_text="$(cat "$expected_fixture")"

    if [[ "$expected_text" == "${NO_OUTPUT_SENTINEL%$'\n'}" || "$expected_text" == "$NO_OUTPUT_SENTINEL" ]]; then
        # Sentinel case: wrapper must emit empty stdout.
        if [[ -n "$hook_stdout" ]]; then
            echo "FAIL [$case]: expected empty stdout (NO_OUTPUT sentinel); got: $hook_stdout" >&2
            FAILED=$((FAILED + 1))
            continue
        fi
        echo "PASS [$case] (empty stdout)"
        PASSED=$((PASSED + 1))
        continue
    fi

    # Non-empty fixture: extract additionalContext via jq and diff.
    if [[ -z "$hook_stdout" ]]; then
        echo "FAIL [$case]: wrapper emitted no stdout but expected non-empty additionalContext" >&2
        FAILED=$((FAILED + 1))
        continue
    fi

    actual_ctx="$(printf '%s' "$hook_stdout" | jq -r '.hookSpecificOutput.additionalContext')"

    if [[ "$actual_ctx" != "$expected_text" ]]; then
        echo "FAIL [$case]: additionalContext mismatch" >&2
        echo "       --- expected ---" >&2
        printf '%s\n' "$expected_text" | sed 's/^/       /' >&2
        echo "       --- actual ---" >&2
        printf '%s\n' "$actual_ctx" | sed 's/^/       /' >&2
        FAILED=$((FAILED + 1))
        continue
    fi

    echo "PASS [$case]"
    PASSED=$((PASSED + 1))
done

echo ""
if [[ $FAILED -gt 0 ]]; then
    echo "FAIL: $FAILED/$((PASSED + FAILED)) cases failed under uv-tool topology"
    exit 1
fi

echo "OK: all 6 cases passed"
exit 0
