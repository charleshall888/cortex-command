#!/usr/bin/env bash
# Overnight-active probe sidecar — shared implementation used by the
# interactive overnight-check path (implement.md §1, R7).
#
# Usage:
#   cat skills/lifecycle/references/_interactive_overnight_check.sh | bash -s -- "<rejection-wording>" "<expected-repo-path>"
#
# Arguments:
#   $1  Rejection-wording template string surfaced to the caller on exit 1.
#   $2  Expected repo_path to match against the active session's repo_path.
#
# Exit codes:
#   0   No overnight session active — caller may proceed.
#   1   Overnight runner is live for the expected repo — caller surfaces $1.
#   2   Stale runner detected (runner.pid absent or process dead) — caller
#       surfaces a warn-and-continue diagnostic.

_rejection_wording="$1"
_expected_repo_path="$2"

# Step 1: Read the active-session pointer.
_active_session_json=$(cat ~/.local/share/overnight-sessions/active-session.json 2>/dev/null)
if [ -z "$_active_session_json" ]; then
    exit 0
fi

# Step 2: Parse repo_path and session_dir from the active-session JSON.
_repo_path=$(python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('repo_path',''))" <<< "$_active_session_json")
_session_dir=$(python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('session_dir',''))" <<< "$_active_session_json")
_session_id=$(python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('session_id',''))" <<< "$_active_session_json")
_phase=$(python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('phase',''))" <<< "$_active_session_json")

if [ "$_repo_path" != "$_expected_repo_path" ]; then
    exit 0
fi

if [ -z "$_session_dir" ]; then
    exit 0
fi

# Step 3: Read runner.pid from the session directory.
_runner_pid_json=$(cat "${_session_dir}/runner.pid" 2>/dev/null)
if [ -z "$_runner_pid_json" ]; then
    exit 2
fi

# Step 4: Parse the pid field from runner.pid JSON.
_runner_pid=$(python3 -c "import json,sys; print(json.load(sys.stdin)['pid'])" <<< "$_runner_pid_json")
if [ -z "$_runner_pid" ]; then
    exit 2
fi

if kill -0 "$_runner_pid" 2>/dev/null; then
    echo "$_rejection_wording" >&2
    exit 1
fi

exit 2
