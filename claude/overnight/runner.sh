#!/usr/bin/env bash
# Overnight round-loop runner.
#
# Spawns a fresh Claude orchestrator agent per round, monitors progress
# via the overnight state file, and enforces time limits and circuit
# breakers. This is the outermost safety net — if everything else fails,
# it kills the session and writes a partial event.
#
# Usage:
#   bash claude/overnight/runner.sh [OPTIONS]
#
# Options:
#   --state <path>       Path to overnight-state.json (default: auto-discovers most recent executing session)
#   --time-limit <hours> Maximum wall-clock hours (default: 6)
#   --max-rounds <n>     Maximum number of rounds (default: 10)
#   --test-command <cmd> Shell command to run as integration gate after each merge (default: none)

set -euo pipefail

# ---------------------------------------------------------------------------
# Python venv activation
# ---------------------------------------------------------------------------

# Resolve REPO_ROOT to the real repo, not a worktree, so the .venv is always found.
# Guard: allow callers (e.g. integration tests) to pre-set REPO_ROOT to redirect writes.
if [[ -z "${REPO_ROOT:-}" ]]; then
    _SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    _GIT_COMMON="$(git -C "$_SCRIPT_DIR" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
    if [[ "$_GIT_COMMON" == */.git ]]; then
        REPO_ROOT="${_GIT_COMMON%/.git}"
    else
        REPO_ROOT="$(cd "$_SCRIPT_DIR/../.." && pwd)"
    fi
fi
if [ ! -f "$REPO_ROOT/.venv/bin/activate" ]; then
    echo "Error: Python venv not found at $REPO_ROOT/.venv — run: just python-setup" >&2
    exit 1
fi
source "$REPO_ROOT/.venv/bin/activate"
export PYTHONPATH="$REPO_ROOT"

# ---------------------------------------------------------------------------
# API key resolution for SDK subagents
# ---------------------------------------------------------------------------
# apiKeyHelper only authenticates the parent `claude` process — it does NOT
# export ANTHROPIC_API_KEY into child processes. SDK-spawned subagents need
# the key injected explicitly. We check settings.json then settings.local.json
# for apiKeyHelper and export the result so it propagates into dispatch.py.
# If no apiKeyHelper is configured, subagents use subscription billing.
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    _API_KEY=$(python3 - <<'PYEOF' 2>/dev/null
import json, shlex, subprocess, pathlib, sys
home = pathlib.Path.home()
helper = ""
for p in [home / ".claude" / "settings.json", home / ".claude" / "settings.local.json"]:
    if p.exists():
        helper = json.loads(p.read_text()).get("apiKeyHelper", "")
        if helper:
            break
if helper:
    parts = shlex.split(helper.replace("~", str(home)))
    r = subprocess.run(parts, capture_output=True, text=True, timeout=5)
    if r.returncode == 0:
        sys.stdout.write(r.stdout.strip())
PYEOF
)
    if [[ -n "$_API_KEY" ]]; then
        export ANTHROPIC_API_KEY="$_API_KEY"
    else
        echo "Warning: no apiKeyHelper configured or returned empty — overnight subagents will use subscription billing" >&2
    fi
    unset _API_KEY
fi

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

STATE_PATH=""  # resolved below after arg parsing if not set via --state
TIME_LIMIT_HOURS=6
MAX_ROUNDS=10
TIER="max_100"
PROMPT_TEMPLATE="$REPO_ROOT/claude/overnight/prompts/orchestrator-round.md"
EVENTS_PATH=""  # set after session ID read
PLAN_PATH=""    # set after session ID read
TEST_COMMAND=""
INTEGRATION_DEGRADED=false
INTEGRATION_WARNING_FILE="$TMPDIR/overnight-integration-warning.txt"
INTEGRATION_TEST_OUTPUT="$TMPDIR/overnight-integration-test-output.txt"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case "$1" in
        --state)
            STATE_PATH="$2"
            shift 2
            ;;
        --time-limit)
            TIME_LIMIT_HOURS="${2%h}"  # Strip trailing 'h' if present (e.g. 6h -> 6)
            shift 2
            ;;
        --max-rounds)
            MAX_ROUNDS="$2"
            shift 2
            ;;
        --tier)
            TIER="$2"
            shift 2
            ;;
        --test-command)
            TEST_COMMAND="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Auto-discover state file if not explicitly set
# ---------------------------------------------------------------------------

if [[ -z "$STATE_PATH" ]]; then
    STATE_PATH=$(OVERNIGHT_LIFECYCLE="$REPO_ROOT/lifecycle" python3 - <<'PYEOF'
import json
import os
import subprocess
from pathlib import Path

_lifecycle = Path(os.environ["OVERNIGHT_LIFECYCLE"])

# First candidate: check if latest-overnight symlink resolves to an executing session
latest_symlink = _lifecycle / "sessions" / "latest-overnight" / "overnight-state.json"
try:
    resolved = subprocess.run(
        ["realpath", str(latest_symlink)],
        capture_output=True, text=True
    )
    if resolved.returncode == 0:
        resolved_path = Path(resolved.stdout.strip())
        if resolved_path.exists():
            state = json.loads(resolved_path.read_text())
            if state.get("phase") == "executing":
                print(resolved_path)
                raise SystemExit(0)
except Exception:
    pass

# Fall back: find all overnight-state.json files under lifecycle/sessions/
candidates = sorted(
    (_lifecycle / "sessions").glob("*/overnight-state.json"),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)

for path in candidates:
    try:
        state = json.loads(path.read_text())
        if state.get("phase") == "executing":
            print(path)
            break
    except Exception:
        continue
PYEOF
)
    if [[ -z "$STATE_PATH" ]]; then
        echo "Error: no overnight session with phase 'executing' found under lifecycle/sessions/." >&2
        echo "Hint: run /overnight in Claude Code to initialize a new session." >&2
        exit 1
    fi
    echo "Using session: $STATE_PATH"
fi

# Resolve STATE_PATH to an absolute path so that SESSION_DIR, EVENTS_PATH,
# PLAN_PATH, and the lock file remain valid after any subsequent cd.
STATE_PATH="$(realpath "$STATE_PATH")"

# Update latest-overnight symlink to point to the active session directory,
# so that status.py, overnight-logs, and other tools always reflect the
# current session regardless of how the state file was resolved.
SESSION_DIR="$(dirname "$STATE_PATH")"
ln -sf "$SESSION_DIR" "$REPO_ROOT/lifecycle/sessions/latest-overnight" 2>/dev/null || true

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

if [[ ! -f "$STATE_PATH" ]]; then
    echo "Error: state file not found at $STATE_PATH" >&2
    exit 1
fi

if [[ ! -f "$PROMPT_TEMPLATE" ]]; then
    echo "Error: prompt template not found at $PROMPT_TEMPLATE" >&2
    exit 1
fi

# Verify state phase is 'executing'
PHASE=$(STATE_PATH="$STATE_PATH" python3 -c "
import json, os
state = json.load(open(os.environ['STATE_PATH']))
print(state.get('phase', ''))
")
if [[ "$PHASE" != "executing" ]]; then
    echo "Error: overnight state phase is '$PHASE', expected 'executing'" >&2
    exit 1
fi

# Read session ID and derive per-session events log path
SESSION_ID=$(STATE_PATH="$STATE_PATH" python3 -c "
import json, os
state = json.load(open(os.environ['STATE_PATH']))
print(state.get('session_id', ''))
")
if [[ -z "$SESSION_ID" ]]; then
    echo "Error: session_id not found in state file" >&2
    exit 1
fi
EVENTS_PATH="${SESSION_DIR}/overnight-events.log"
PLAN_PATH="${SESSION_DIR}/overnight-plan.md"

# For new-style sessions (worktree_path set), update latest-overnight to an
# absolute symlink pointing into the worktree session directory.
WORKTREE_PATH=$(STATE_PATH="$STATE_PATH" python3 -c "
import json, os
s = json.load(open(os.environ['STATE_PATH']))
print(s.get('worktree_path') or '')
")
if [[ -n "$WORKTREE_PATH" ]]; then
    ln -sf "${WORKTREE_PATH}/lifecycle/sessions/${SESSION_ID}" "$REPO_ROOT/lifecycle/sessions/latest-overnight" 2>/dev/null || true
fi

# Write active-session pointer so the dashboard can find sessions from any repo
SESSION_ID="$SESSION_ID" REPO_ROOT="$REPO_ROOT" STATE_PATH="$STATE_PATH" python3 -c "
import json, os, tempfile
from pathlib import Path
from datetime import datetime, timezone

pointer_dir = Path.home() / '.local' / 'share' / 'overnight-sessions'
pointer_dir.mkdir(parents=True, exist_ok=True)
pointer_path = pointer_dir / 'active-session.json'
data = {
    'session_id': os.environ['SESSION_ID'],
    'repo_path': os.environ['REPO_ROOT'],
    'state_path': os.environ['STATE_PATH'],
    'started_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'phase': 'executing',
}
with tempfile.NamedTemporaryFile(mode='w', dir=str(pointer_dir), delete=False, suffix='.tmp') as f:
    json.dump(data, f)
    tmp_path = f.name
os.replace(tmp_path, pointer_path)
" || true

# For cross-repo sessions, the overnight skill writes overnight-plan.md to
# the home repo's session dir (REPO_ROOT/lifecycle/sessions/SESSION_ID/), not
# the target repo's session dir that SESSION_DIR points to. Override PLAN_PATH.
if [[ -n "$WORKTREE_PATH" ]]; then
    PLAN_PATH="$REPO_ROOT/lifecycle/sessions/${SESSION_ID}/overnight-plan.md"
fi

# Derive integration branch name from scalar state field (fallback: "main").
# Used by batch_runner invocation (--base-branch) later in the round loop.
INTEGRATION_BRANCH=$(STATE_PATH="$STATE_PATH" python3 -c "
import json, os
data = json.load(open(os.environ['STATE_PATH']))
print(data.get('integration_branch') or 'main')
")

# Derive the home project root from the first key of integration_branches.
# For home-repo sessions this equals REPO_ROOT; for per-repo sessions
# it equals the target project root (e.g. wild-light).
HOME_PROJECT_ROOT=$(STATE_PATH="$STATE_PATH" REPO_ROOT="$REPO_ROOT" python3 -c "
import json, os
data = json.load(open(os.environ['STATE_PATH']))
branches = data.get('integration_branches', {})
print(os.path.realpath(next(iter(branches)))) if branches else print(os.path.realpath(os.environ['REPO_ROOT']))
")

# Derive the target project root — the single non-home repo in integration_branches.
# For cross-repo sessions this is the external project (e.g. wild-light);
# for home-only sessions this is empty (all keys resolve to REPO_ROOT).
TARGET_PROJECT_ROOT=$(STATE_PATH="$STATE_PATH" HOME_PROJECT_ROOT="$HOME_PROJECT_ROOT" python3 -c "
import json, os
data = json.load(open(os.environ['STATE_PATH']))
mc = os.path.realpath(os.environ['HOME_PROJECT_ROOT'])
for repo_path in data.get('integration_branches', {}):
    if os.path.realpath(repo_path) != mc:
        print(repo_path)
        break
")

# Derive the integration worktree path for the target project.
# Looks up integration_worktrees in state JSON for an entry whose key resolves
# to TARGET_PROJECT_ROOT. Sets TARGET_INTEGRATION_WORKTREE if found and valid.
TARGET_INTEGRATION_WORKTREE=""
if [[ -n "$TARGET_PROJECT_ROOT" ]]; then
    _IW_LOOKUP=$(STATE_PATH="$STATE_PATH" TARGET_PROJECT_ROOT="$TARGET_PROJECT_ROOT" python3 -c "
import json, os
data = json.load(open(os.environ['STATE_PATH']))
target = os.path.realpath(os.environ['TARGET_PROJECT_ROOT'])
for k, v in data.get('integration_worktrees', {}).items():
    if os.path.realpath(k) == target:
        print(v)
        break
")
    if [[ -z "$_IW_LOOKUP" ]]; then
        log_event "integration_worktree_missing" "$(( ROUND - 1 ))" "{\"reason\": \"no entry in integration_worktrees for target\", \"target\": \"$TARGET_PROJECT_ROOT\"}"
    elif [[ ! -d "$_IW_LOOKUP" ]]; then
        log_event "integration_worktree_missing" "$(( ROUND - 1 ))" "{\"reason\": \"path not on disk\", \"path\": \"$_IW_LOOKUP\", \"target\": \"$TARGET_PROJECT_ROOT\"}"
    else
        TARGET_INTEGRATION_WORKTREE="$_IW_LOOKUP"
    fi
fi

# ---------------------------------------------------------------------------
# Concurrency guard — prevent multiple runner processes on the same session
# ---------------------------------------------------------------------------

LOCK_FILE="$SESSION_DIR/.runner.lock"
if [[ -f "$LOCK_FILE" ]]; then
    LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
    if [[ -n "$LOCK_PID" ]] && kill -0 "$LOCK_PID" 2>/dev/null; then
        echo "Error: another runner is already executing session $SESSION_ID (PID $LOCK_PID)" >&2
        echo "Attach to it with: tmux attach -t overnight-runner" >&2
        exit 1
    fi
    echo "Removing stale lock file (PID ${LOCK_PID:-unknown})" >&2
fi
echo $$ > "$LOCK_FILE"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

log_event() {
    local event="$1"
    local round_num="$2"
    local details="${3:-}"
    LOG_EVENT_NAME="$event" LOG_ROUND="$round_num" LOG_DETAILS="$details" LOG_EVENTS_PATH="$EVENTS_PATH" python3 -c "
import json, os
from claude.overnight.events import log_event
from pathlib import Path
raw = os.environ.get('LOG_DETAILS', '')
details = json.loads(raw) if raw else None
log_event(os.environ['LOG_EVENT_NAME'], int(os.environ['LOG_ROUND']), details=details, log_path=Path(os.environ['LOG_EVENTS_PATH']))
"
}

count_pending() {
    STATE_PATH="$STATE_PATH" python3 -c "
import json, os
state = json.load(open(os.environ['STATE_PATH']))
features = state.get('features', {})
count = sum(1 for f in features.values() if f.get('status') in ('pending', 'running', 'paused'))
print(count)
"
}

fill_prompt() {
    local round_num="$1"
    STATE_PATH="$STATE_PATH" PLAN_PATH="$PLAN_PATH" EVENTS_PATH="$EVENTS_PATH" \
    SESSION_DIR="$SESSION_DIR" \
    ROUND_NUM="$round_num" TIER="$TIER" TEMPLATE="$PROMPT_TEMPLATE" python3 -c "
import os
t = open(os.environ['TEMPLATE']).read()
t = t.replace('{state_path}', os.environ['STATE_PATH'])
t = t.replace('{plan_path}', os.environ['PLAN_PATH'])
t = t.replace('{events_path}', os.environ['EVENTS_PATH'])
t = t.replace('{session_dir}', os.environ['SESSION_DIR'])
t = t.replace('{round_number}', os.environ['ROUND_NUM'])
t = t.replace('{tier}', os.environ['TIER'])
print(t, end='')
"
}


watch_events_log() {
    local log_path="$1"
    local timeout_secs="$2"
    local target_pid="$3"
    local poll_interval=30

    while true; do
        sleep "$poll_interval"
        # If the target process is already gone, exit cleanly
        if ! kill -0 "$target_pid" 2>/dev/null; then
            return 0
        fi
        # Get last line of log and extract timestamp
        local last_line
        last_line=$(tail -1 "$log_path" 2>/dev/null || true)
        if [[ -z "$last_line" ]]; then
            continue
        fi
        local last_ts
        last_ts=$(python3 -c "
import json, sys
try:
    line = json.loads(sys.stdin.read())
    print(line.get('ts', ''))
except Exception:
    print('')
" <<< "$last_line" 2>/dev/null || true)
        if [[ -z "$last_ts" ]]; then
            continue
        fi
        local age_secs
        age_secs=$(python3 -c "
from datetime import datetime, timezone
import sys
ts = sys.argv[1]
try:
    t = datetime.fromisoformat(ts)
    now = datetime.now(timezone.utc)
    print(int((now - t).total_seconds()))
except Exception:
    print(0)
" "$last_ts" 2>/dev/null || echo 0)
        if [[ "$age_secs" -ge "$timeout_secs" ]]; then
            # Log STALL_TIMEOUT event
            LOG_EVENT_NAME="stall_timeout" LOG_ROUND="$ROUND" LOG_DETAILS="{\"session_id\": \"$SESSION_ID\", \"last_event_ago_seconds\": $age_secs, \"round\": $ROUND}" LOG_EVENTS_PATH="$EVENTS_PATH" python3 -c "
import json, os
from claude.overnight.events import log_event
from pathlib import Path
raw = os.environ.get('LOG_DETAILS', '')
details = json.loads(raw) if raw else None
log_event(os.environ['LOG_EVENT_NAME'], int(os.environ['LOG_ROUND']), details=details, log_path=Path(os.environ['LOG_EVENTS_PATH']))
" 2>/dev/null || true
            # Write stall flag and kill the target's entire process group
            echo "1" > "$STALL_FLAG"
            kill -- -"$target_pid" 2>/dev/null || true
            return 0
        fi
    done
}

elapsed_hours() {
    local now
    now=$(date +%s)
    local diff=$(( now - START_TIME ))
    echo $(( diff / 3600 ))
}

# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------

cleanup() {
    # Kill child process groups first — with set -m they won't receive our signals
    [[ -n "${CLAUDE_PID:-}" ]] && kill -- -"$CLAUDE_PID" 2>/dev/null || true
    [[ -n "${BATCH_PID:-}" ]] && kill -- -"$BATCH_PID" 2>/dev/null || true
    [[ -n "${WATCHDOG_PID:-}" ]] && kill -- -"$WATCHDOG_PID" 2>/dev/null || true
    [[ -n "${BATCH_WATCHDOG_PID:-}" ]] && kill -- -"$BATCH_WATCHDOG_PID" 2>/dev/null || true
    rm -f "${LOCK_FILE:-}"
    echo ""
    echo "Signal received — pausing overnight session"
    STATE_PATH="$STATE_PATH" python3 -c "
import os
from claude.overnight.state import load_state, save_state, transition
from pathlib import Path
state = load_state(Path(os.environ['STATE_PATH']))
if state.phase != 'complete' and state.phase != 'paused':
    state = transition(state, 'paused')
    state.paused_reason = 'signal'
    save_state(state, Path(os.environ['STATE_PATH']))
    print(f'State saved (paused from {state.paused_from}, reason: signal)')
"
    # Update active-session pointer to reflect paused phase
    SESSION_ID="$SESSION_ID" python3 -c "
import json, os, tempfile
from pathlib import Path

pointer_path = Path.home() / '.local' / 'share' / 'overnight-sessions' / 'active-session.json'
if pointer_path.exists():
    try:
        data = json.loads(pointer_path.read_text())
        if data.get('session_id') == os.environ['SESSION_ID']:
            data['phase'] = 'paused'
            with tempfile.NamedTemporaryFile(mode='w', dir=str(pointer_path.parent), delete=False, suffix='.tmp') as f:
                json.dump(data, f)
                tmp_path = f.name
            os.replace(tmp_path, pointer_path)
    except Exception:
        pass
" || true
    log_event "circuit_breaker" "$ROUND" "{\"reason\": \"signal\"}"
    STATE_PATH="$STATE_PATH" EVENTS_PATH="$EVENTS_PATH" TARGET_PROJECT_ROOT="$TARGET_PROJECT_ROOT" REPO_ROOT="$REPO_ROOT" SESSION_ID="$SESSION_ID" python3 -c "
import os
from pathlib import Path
from datetime import datetime, timezone
from claude.overnight.report import collect_report_data, create_followup_backlog_items, generate_report, write_report
data = collect_report_data(state_path=Path(os.environ['STATE_PATH']), events_path=Path(os.environ['EVENTS_PATH']))
data.new_backlog_items = create_followup_backlog_items(data)
report = generate_report(data)
ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
report = f'> **Interrupted Session** — partial report generated at {ts}\n\n' + report
target = os.environ['TARGET_PROJECT_ROOT'] if os.environ['TARGET_PROJECT_ROOT'] else os.environ['REPO_ROOT']
sid = os.environ['SESSION_ID']
write_report(report, path=Path(target) / 'lifecycle' / 'sessions' / sid / 'morning-report.md')
write_report(report, path=Path(target) / 'lifecycle' / 'morning-report.md')
" || true
    ~/.claude/notify.sh "Overnight session killed — partial report in lifecycle/sessions/${SESSION_ID}/. Session: $SESSION_ID" || true
    exit 130
}

trap cleanup SIGINT SIGTERM SIGHUP

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

START_TIME=$(date +%s)
ROUND=$(STATE_PATH="$STATE_PATH" python3 -c "import json, os; print(json.load(open(os.environ['STATE_PATH']))['current_round'])")
STALL_COUNT=0
STALL_FLAG=$(mktemp -p "${TMPDIR:-/tmp}")

echo "=== Overnight Runner ==="
echo "  State:      $STATE_PATH"
echo "  Time limit: ${TIME_LIMIT_HOURS}h"
echo "  Max rounds: $MAX_ROUNDS"
echo "  Tier:       $TIER"
echo "  Started:    $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo ""

# Create integration branches in cross-repo target repos
STATE_PATH="$STATE_PATH" HOME_PROJECT_ROOT="$HOME_PROJECT_ROOT" python3 -c "
import json, os, subprocess
data = json.load(open(os.environ['STATE_PATH']))
repo_root = os.path.realpath(os.environ['HOME_PROJECT_ROOT'])
integration_worktrees = data.get('integration_worktrees', {})
worktree_repos = set(os.path.realpath(k) for k in integration_worktrees)
for repo_path, branch_name in data.get('integration_branches', {}).items():
    real_repo = os.path.realpath(repo_path)
    if real_repo == repo_root:
        continue
    if real_repo in worktree_repos:
        result = subprocess.run(
            ['git', 'show-ref', '--verify', '--quiet', 'refs/heads/' + branch_name],
            cwd=repo_path, capture_output=True)
        if result.returncode == 0:
            continue
    print(repo_path + '|' + branch_name)
" | while IFS='|' read -r REPO_PATH BRANCH_NAME; do
    (cd "$REPO_PATH" && git branch "$BRANCH_NAME" 2>/dev/null || echo "Warning: branch $BRANCH_NAME already exists in $REPO_PATH")
done

log_event "session_start" "1" "{\"time_limit_hours\": $TIME_LIMIT_HOURS, \"max_rounds\": $MAX_ROUNDS}"

# Reset any features stuck in running status from a previous interrupted session
python3 -m claude.overnight.interrupt "$STATE_PATH"

# For new-style sessions, cd into the worktree so all subsequent agent spawns
# operate in the correct git context. Old-style sessions (no worktree_path)
# continue running from the main repo — no cd.
if [[ -n "$WORKTREE_PATH" ]]; then
    if [[ ! -d "$WORKTREE_PATH" ]]; then
        echo "Worktree missing at $WORKTREE_PATH -- attempting auto-recovery..." >&2
        # Prune stale git metadata. --expire now bypasses the default 2-week grace
        # period so recently-created-but-missing entries are cleaned up too.
        (cd "$HOME_PROJECT_ROOT" && git worktree prune --expire now) || true
        mkdir -p "$(dirname "$WORKTREE_PATH")"
        if (cd "$HOME_PROJECT_ROOT" && git worktree add "$WORKTREE_PATH" "$INTEGRATION_BRANCH") 2>&1; then
            echo "Worktree recreated at $WORKTREE_PATH" >&2
        else
            echo "" >&2
            echo "Error: could not recreate worktree at $WORKTREE_PATH" >&2
            echo "  Branch:     $INTEGRATION_BRANCH" >&2
            echo "  State file: $STATE_PATH" >&2
            echo "" >&2
            echo "Check that the integration branch exists:" >&2
            echo "  (cd \"$HOME_PROJECT_ROOT\" && git branch -l \"$INTEGRATION_BRANCH\")" >&2
            exit 1
        fi
    fi
    cd "$WORKTREE_PATH"
fi

while [[ $ROUND -le $MAX_ROUNDS ]]; do
    # Check for pending features
    PENDING=$(count_pending)
    if [[ "$PENDING" -eq 0 ]]; then
        echo "Round $ROUND: No pending features — all done"
        break
    fi

    # Skip rounds whose results file already exists (resume from completed round)
    if [[ -f "${SESSION_DIR}/batch-${ROUND}-results.json" ]]; then
        echo "Round $ROUND: results file already exists — skipping"
        STATE_PATH="$STATE_PATH" ROUND="$ROUND" python3 -c "
import os
from claude.overnight.state import load_state, save_state
from pathlib import Path
state = load_state(Path(os.environ['STATE_PATH']))
state.current_round = int(os.environ['ROUND']) + 1
save_state(state, Path(os.environ['STATE_PATH']))
"
        ROUND=$(( ROUND + 1 ))
        continue
    fi

    # Capture merged count at start of round (per-round, after completed-round skip)
    MERGED_BEFORE=$(STATE_PATH="$STATE_PATH" python3 -c "
import json, os
state = json.load(open(os.environ['STATE_PATH']))
features = state.get('features', {})
print(sum(1 for f in features.values() if f.get('status') == 'merged'))
")

    echo "--- Round $ROUND (${PENDING} features pending) ---"
    log_event "round_start" "$ROUND" "{\"pending\": $PENDING}"

    # Fill the prompt template
    FILLED_PROMPT=$(fill_prompt "$ROUND")

    # Spawn Claude agent for this round (background) + watchdog
    echo "Spawning orchestrator agent for round $ROUND..."
    # Clear stall flag for this round
    > "$STALL_FLAG"
    set +e
    # set -m gives the child its own PGID so the watchdog can kill the
    # entire process group. $! == PGID only holds for direct cmd & (not pipelines).
    set -m
    claude -p "$FILLED_PROMPT" \
        --dangerously-skip-permissions \
        --max-turns 50 2>&1 & CLAUDE_PID=$!
    set +m
    set -m
    ( watch_events_log "$EVENTS_PATH" 1800 $CLAUDE_PID ) & WATCHDOG_PID=$!
    set +m
    wait $CLAUDE_PID
    EXIT_CODE=$?
    CLAUDE_PID=""
    kill -- -$WATCHDOG_PID 2>/dev/null || true
    wait $WATCHDOG_PID 2>/dev/null || true
    set -e

    # Check if the watchdog triggered a stall timeout
    STALLED=false
    if [[ -s "$STALL_FLAG" ]]; then
        STALLED=true
        echo "Warning: watchdog killed orchestrator due to event log silence (stall timeout)"
        STATE_PATH="$STATE_PATH" python3 -c "
import os
from claude.overnight.state import load_state, save_state, transition
from pathlib import Path
state = load_state(Path(os.environ['STATE_PATH']))
if state.phase != 'paused' and state.phase != 'complete':
    state = transition(state, 'paused')
    state.paused_reason = 'stall_timeout'
    save_state(state, Path(os.environ['STATE_PATH']))
    print('Session transitioned to paused due to stall timeout')
"
        ~/.claude/notify.sh "Overnight session stalled — no pipeline activity for 30+ minutes. Session paused. Session: $SESSION_ID" || true
    elif [[ $EXIT_CODE -ne 0 ]]; then
        echo "Warning: orchestrator agent exited with code $EXIT_CODE"
        LOG_EVENT_NAME="orchestrator_failed" LOG_ROUND="$ROUND" LOG_DETAILS="{\"exit_code\": $EXIT_CODE}" LOG_EVENTS_PATH="$EVENTS_PATH" python3 -c "
import json, os
from claude.overnight.events import log_event
from pathlib import Path
raw = os.environ.get('LOG_DETAILS', '')
details = json.loads(raw) if raw else None
log_event(os.environ['LOG_EVENT_NAME'], int(os.environ['LOG_ROUND']), details=details, log_path=Path(os.environ['LOG_EVENTS_PATH']))
" 2>/dev/null || true
    fi

    # If watchdog triggered stall timeout, break out of round loop
    if [[ "$STALLED" == "true" ]]; then
        echo "Round $ROUND aborted by stall timeout — stopping"
        break
    fi

    # -----------------------------------------------------------------------
    # Step 5: Invoke batch_runner.py (if orchestrator produced a batch plan)
    # -----------------------------------------------------------------------
    BATCH_PLAN_PATH="$SESSION_DIR/batch-plan-round-$ROUND.md"
    if [[ ! -f "$BATCH_PLAN_PATH" ]] && [[ -n "$WORKTREE_PATH" ]]; then
        # Fallback: orchestrator may have written the batch plan inside the worktree
        WORKTREE_BATCH_PLAN="$WORKTREE_PATH/lifecycle/sessions/$SESSION_ID/batch-plan-round-$ROUND.md"
        if [[ -f "$WORKTREE_BATCH_PLAN" ]]; then
            cp "$WORKTREE_BATCH_PLAN" "$BATCH_PLAN_PATH"
            echo "Round $ROUND: batch plan found in worktree — copied to session dir"
        fi
    fi
    if [[ ! -f "$BATCH_PLAN_PATH" ]]; then
        log_event "orchestrator_no_plan" "$ROUND" "{\"round\": $ROUND}"
        echo "Round $ROUND: no batch plan produced — skipping batch_runner"
    else
        export LIFECYCLE_SESSION_ID="$SESSION_ID"
        # Clear stall flag for batch_runner watchdog
        > "$STALL_FLAG"
        set +e
        # set -m gives batch_runner its own PGID for process group kill.
        # $! == PGID only holds for direct cmd & (not pipelines).
        set -m
        python3 -m claude.overnight.batch_runner \
            --plan "$BATCH_PLAN_PATH" \
            --batch-id $ROUND \
            --tier $TIER \
            --base-branch $INTEGRATION_BRANCH \
            --state-path "$STATE_PATH" \
            --events-path "$EVENTS_PATH" \
            --test-command "${TEST_COMMAND:-none}" & BATCH_PID=$!
        set +m
        set -m
        ( watch_events_log "$EVENTS_PATH" 1800 $BATCH_PID ) & BATCH_WATCHDOG_PID=$!
        set +m
        wait $BATCH_PID
        BATCH_EXIT=$?
        BATCH_PID=""
        kill -- -$BATCH_WATCHDOG_PID 2>/dev/null || true
        wait $BATCH_WATCHDOG_PID 2>/dev/null || true
        set -e

        # Check if the watchdog triggered a stall timeout on batch_runner
        if [[ -s "$STALL_FLAG" ]]; then
            echo "Warning: watchdog killed batch_runner due to event log silence (stall timeout)"
            log_event "batch_runner_stalled" "$ROUND" "{\"round\": $ROUND}"
            STATE_PATH="$STATE_PATH" python3 -c "
import os
from claude.overnight.state import load_state, save_state, transition
from pathlib import Path
state = load_state(Path(os.environ['STATE_PATH']))
if state.phase != 'paused' and state.phase != 'complete':
    state = transition(state, 'paused')
    state.paused_reason = 'stall_timeout'
    save_state(state, Path(os.environ['STATE_PATH']))
    print('Session transitioned to paused due to batch_runner stall timeout')
"
            ~/.claude/notify.sh "Overnight batch_runner stalled — no pipeline activity for 30+ minutes. Session paused. Session: $SESSION_ID" || true
            break
        elif [[ $BATCH_EXIT -ne 0 ]]; then
            echo "Warning: batch_runner exited with code $BATCH_EXIT"
            log_event "orchestrator_failed" "$ROUND" "{\"exit_code\": $BATCH_EXIT}"
        fi

        # Check if session was paused due to budget exhaustion
        PAUSED_REASON=$(STATE_PATH="$STATE_PATH" python3 -c "import json, os; state = json.load(open(os.environ['STATE_PATH'])); print(state.get('paused_reason') or '')")
        if [[ "$PAUSED_REASON" == "budget_exhausted" ]]; then
            echo "Session paused: API budget exhausted — stopping round loop"
            log_event "circuit_breaker" "$ROUND" "{\"reason\": \"budget_exhausted\"}"
            break
        fi

        # -------------------------------------------------------------------
        # Step 6: Invoke map_results.py to update state and strategy
        # -------------------------------------------------------------------
        python3 -m claude.overnight.map_results \
            --batch-id $ROUND \
            --plan "$BATCH_PLAN_PATH" \
            --state-path "$STATE_PATH" \
            --events-path "$EVENTS_PATH" \
            --strategy-path "$SESSION_DIR/overnight-strategy.json" \
            || echo "Warning: map_results.py failed — feature statuses may not be updated"
    fi

    # Count merged features after this round
    MERGED_AFTER=$(STATE_PATH="$STATE_PATH" python3 -c "
import json, os
state = json.load(open(os.environ['STATE_PATH']))
features = state.get('features', {})
print(sum(1 for f in features.values() if f.get('status') == 'merged'))
")

    MERGED_THIS_ROUND=$(( MERGED_AFTER - MERGED_BEFORE ))
    echo "Round $ROUND complete: $MERGED_THIS_ROUND features merged this round ($MERGED_AFTER total)"

    log_event "round_complete" "$ROUND" "{\"merged_this_round\": $MERGED_THIS_ROUND, \"merged_total\": $MERGED_AFTER}"
    log_event "round_setup_start" "$ROUND"

    # Progress circuit breaker
    if [[ $MERGED_THIS_ROUND -le 0 ]]; then
        STALL_COUNT=$(( STALL_COUNT + 1 ))
        echo "Warning: zero features merged this round (stall count: $STALL_COUNT/2)"
        if [[ $STALL_COUNT -ge 2 ]]; then
            echo "Circuit breaker: 2 consecutive rounds with zero progress — stopping"
            log_event "circuit_breaker" "$ROUND" "{\"reason\": \"stall\", \"stall_count\": $STALL_COUNT}"
            REMAINING_PENDING=$(STATE_PATH="$STATE_PATH" python3 -c "import json, os; state = json.load(open(os.environ['STATE_PATH'])); features = state.get('features', {}); print(sum(1 for f in features.values() if f.get('status') in ('pending', 'paused')))")
            if [[ "$REMAINING_PENDING" -eq 0 ]]; then
                ~/.claude/notify.sh "Overnight session abandoned — no progress after 2 rounds. Session: $SESSION_ID. Check morning report." || true
            fi
            log_event "round_setup_complete" "$ROUND"
            break
        fi
    else
        STALL_COUNT=0
    fi

    MERGED_BEFORE=$MERGED_AFTER

    # Time limit check
    HOURS=$(elapsed_hours)
    if [[ $HOURS -ge $TIME_LIMIT_HOURS ]]; then
        echo "Time limit reached (${HOURS}h >= ${TIME_LIMIT_HOURS}h) — stopping"
        log_event "circuit_breaker" "$ROUND" "{\"reason\": \"time_limit\", \"elapsed_hours\": $HOURS}"
        log_event "round_setup_complete" "$ROUND"
        break
    fi

    # Update round in state
    STATE_PATH="$STATE_PATH" ROUND="$ROUND" python3 -c "
import os
from claude.overnight.state import load_state, save_state
from pathlib import Path
state = load_state(Path(os.environ['STATE_PATH']))
state.current_round = int(os.environ['ROUND']) + 1
save_state(state, Path(os.environ['STATE_PATH']))
"
    log_event "round_setup_complete" "$ROUND"

    ROUND=$(( ROUND + 1 ))
done

# Clean up temp files
rm -f "$STALL_FLAG"

# ---------------------------------------------------------------------------
# Security model
# ---------------------------------------------------------------------------
# Privilege separation: the bash runner (this script) owns all privileged
# operations — git push and gh pr create — with full terminal credentials
# (SSH keys, gh auth). Claude agents own code work and commits only.
#
# Agent sandboxing: orchestrator and commit agents run with --dangerously-
# skip-permissions (bypasses permission prompts, not FS restrictions) and
# optionally with the global sandbox (claude/settings.json sandbox.enabled).
# GPG commit signing in sandboxed agents works via cortex-setup-gpg-sandbox-home.sh
# (extra socket at ~/.local/share/gnupg/S.gpg-agent.sandbox, GNUPGHOME in
# $TMPDIR/gnupghome). The --dangerously-skip-permissions flag must remain;
# removing it blocks autonomous execution.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Post-loop
# ---------------------------------------------------------------------------

echo ""
echo "=== Overnight Session Complete ==="

FINAL_MERGED=$(STATE_PATH="$STATE_PATH" python3 -c "
import json, os
state = json.load(open(os.environ['STATE_PATH']))
features = state.get('features', {})
merged = sum(1 for f in features.values() if f.get('status') == 'merged')
total = len(features)
print(f'{merged}/{total}')
")
echo "  Features merged: $FINAL_MERGED"
echo "  Rounds executed: $(( ROUND - 1 ))"
echo "  Finished:        $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

log_event "session_complete" "$(( ROUND - 1 ))" "{\"features_merged\": \"$FINAL_MERGED\"}"

# Transition state to complete if all features are done
STATE_PATH="$STATE_PATH" python3 -c "
import os
from claude.overnight.state import load_state, save_state, transition
from pathlib import Path
state = load_state(Path(os.environ['STATE_PATH']))
pending = sum(1 for f in state.features.values() if f.status in ('pending', 'running'))
if pending == 0 and state.phase == 'executing':
    state = transition(state, 'complete')
    save_state(state, Path(os.environ['STATE_PATH']))
    print('Session marked complete')
else:
    print(f'{pending} features still pending — session remains in executing phase')
"

# Sync active-session pointer phase with the updated state
STATE_PATH="$STATE_PATH" python3 -c "
import json, os, tempfile
from pathlib import Path

pointer_path = Path.home() / '.local' / 'share' / 'overnight-sessions' / 'active-session.json'
if pointer_path.exists():
    try:
        data = json.loads(pointer_path.read_text())
        state = json.loads(Path(os.environ['STATE_PATH']).read_text())
        data['phase'] = state.get('phase', data['phase'])
        with tempfile.NamedTemporaryFile(mode='w', dir=str(pointer_path.parent), delete=False, suffix='.tmp') as f:
            json.dump(data, f)
            tmp_path = f.name
        os.replace(tmp_path, pointer_path)
    except Exception:
        pass
" || true

# Integration gate: test integration branch before push
if [[ -n "$TEST_COMMAND" ]] && [[ -n "$WORKTREE_PATH" ]] && [[ -d "$WORKTREE_PATH" ]]; then
    echo "Running integration gate: $TEST_COMMAND"
    set +e
    ( cd "$WORKTREE_PATH" && bash -c "$TEST_COMMAND" ) > "$INTEGRATION_TEST_OUTPUT" 2>&1
    GATE_EXIT=$?
    set -e
    if [[ $GATE_EXIT -ne 0 ]]; then
        echo "Integration gate failed (exit $GATE_EXIT) — attempting recovery"
        set +e
        python3 -m claude.overnight.integration_recovery \
            --state "$STATE_PATH" \
            --test-command "$TEST_COMMAND" \
            --worktree "$WORKTREE_PATH" \
            --events-path "$EVENTS_PATH" \
            --test-output "$(head -20 "$INTEGRATION_TEST_OUTPUT")"
        RECOVERY_EXIT=$?
        set -e
        if [[ $RECOVERY_EXIT -ne 0 ]]; then
            INTEGRATION_DEGRADED=true
            STATE_PATH="$STATE_PATH" python3 -c "
import os
from pathlib import Path
from claude.overnight.strategy import load_strategy, save_strategy
_p = Path(os.environ['STATE_PATH']).parent / 'overnight-strategy.json'
_s = load_strategy(_p)
_s.integration_health = 'degraded'
save_strategy(_s, _p)
" || echo "Warning: failed to persist integration_health=degraded to strategy file"
            echo "Recovery failed — integration branch in degraded state; PR will include warning"
            cat > "$INTEGRATION_WARNING_FILE" << 'WARN_EOF'
⚠️ **Integration branch test failure — manual review required**

Tests on the integration branch failed before PR creation. One recovery attempt was made but tests still fail.

**Failing test output (truncated)**:
```
WARN_EOF
            head -20 "$INTEGRATION_TEST_OUTPUT" >> "$INTEGRATION_WARNING_FILE"
            cat >> "$INTEGRATION_WARNING_FILE" << 'WARN_EOF'
```

All features that merged successfully are included in this PR. Review the failing tests above before merging.

---
WARN_EOF
        else
            echo "Integration recovery succeeded — proceeding with PR"
        fi
    else
        echo "Integration gate passed"
    fi
fi

# ---------------------------------------------------------------------------
# Commit lifecycle and session artifacts to integration branch
# ---------------------------------------------------------------------------
if [[ -n "$WORKTREE_PATH" ]]; then
    echo "Committing lifecycle and session artifacts to integration branch"

    # Copy batch results and overnight-strategy to the appropriate project
    if [[ -n "$TARGET_INTEGRATION_WORKTREE" ]]; then
        # Cross-repo session: copy artifacts to the target project's session dir
        mkdir -p "$TARGET_INTEGRATION_WORKTREE/lifecycle/sessions/${SESSION_ID}/"
        cp "$SESSION_DIR"/batch-*-results.json      "$TARGET_INTEGRATION_WORKTREE/lifecycle/sessions/${SESSION_ID}/" 2>/dev/null || true
        cp "$SESSION_DIR/overnight-strategy.json"   "$TARGET_INTEGRATION_WORKTREE/lifecycle/sessions/${SESSION_ID}/" 2>/dev/null || true
    else
        # Home-only session: copy artifacts to the home repo's session dir
        mkdir -p "$REPO_ROOT/lifecycle/sessions/${SESSION_ID}/"
        cp "$SESSION_DIR"/batch-*-results.json      "$REPO_ROOT/lifecycle/sessions/${SESSION_ID}/" 2>/dev/null || true
        cp "$SESSION_DIR/overnight-strategy.json"   "$REPO_ROOT/lifecycle/sessions/${SESSION_ID}/" 2>/dev/null || true
    fi

    # Home-repo git-add subshell — always runs in both cross-repo and home-only sessions.
    # For cross-repo sessions, batch results won't be in the home repo, but any home-repo lifecycle
    # artifacts that changed during the session are still committed here.
    set +e
    (
        cd "$REPO_ROOT"
        git add "lifecycle/sessions/${SESSION_ID}/"            2>/dev/null || true
        git add "lifecycle/*/research.md"                      2>/dev/null || true
        git add "lifecycle/*/spec.md"                          2>/dev/null || true
        git add "lifecycle/*/plan.md"                          2>/dev/null || true
        git add "lifecycle/*/agent-activity.jsonl"             2>/dev/null || true
        git add "lifecycle/pipeline-events.log"                2>/dev/null || true
        git add "backlog/index.md"                             2>/dev/null || true
        git add "backlog/archive/"                             2>/dev/null || true
        if ! git diff --cached --quiet; then
            if ! git commit -m "Overnight session ${SESSION_ID}: record artifacts"; then
                log_event "artifact_commit_failed" "$(( ROUND - 1 ))" "{\"session_id\": \"$SESSION_ID\"}"
                ~/.claude/notify.sh "Overnight: artifact commit failed for session ${SESSION_ID}" || true
            fi
        fi
    )
    set -e
fi

# ---------------------------------------------------------------------------
# Cross-repo PR creation
# ---------------------------------------------------------------------------
# Iterate integration_branches, skip the home repo, create PRs for repos
# with at least one merged feature. Collect PR URLs in a temp JSON file for
# the morning report.
# ---------------------------------------------------------------------------
PR_URLS_FILE="$TMPDIR/overnight-pr-urls.json"
echo '{}' > "$PR_URLS_FILE"
PUSH_FAILED_REPOS_FILE="$TMPDIR/overnight-push-failed-repos.txt"
> "$PUSH_FAILED_REPOS_FILE"

STATE_PATH="$STATE_PATH" HOME_PROJECT_ROOT="$HOME_PROJECT_ROOT" python3 -c "
import json, os
data = json.load(open(os.environ['STATE_PATH']))
repo_root = os.path.realpath(os.environ['HOME_PROJECT_ROOT'])
for repo_path, branch_name in data.get('integration_branches', {}).items():
    if os.path.realpath(repo_path) == repo_root:
        continue
    print(repo_path + '|' + branch_name)
" | while IFS='|' read -r REPO_PATH BRANCH_NAME; do
    REPO_NAME=$(basename "$REPO_PATH")

    # Count merged features for this repo
    MERGED_COUNT=$(STATE_PATH="$STATE_PATH" REPO_PATH="$REPO_PATH" python3 -c "
import json, os
data = json.load(open(os.environ['STATE_PATH']))
repo_path = os.path.realpath(os.environ['REPO_PATH'])
count = 0
for fs in data.get('features', {}).values():
    rp = fs.get('repo_path')
    if rp is not None and os.path.realpath(rp) == repo_path and fs.get('status') == 'merged':
        count += 1
print(count)
")

    if [[ "$MERGED_COUNT" -eq 0 ]]; then
        echo "Skipping $REPO_NAME — no merged features"
        continue
    fi

    # Derive GitHub remote
    REPO_REMOTE=$(cd "$REPO_PATH" && git remote get-url origin 2>/dev/null)
    if [[ -z "$REPO_REMOTE" ]]; then
        echo "Warning: could not determine remote for $REPO_PATH — skipping PR creation" >&2
        continue
    fi

    # Push integration branch
    (cd "$REPO_PATH" && git push -u origin "$BRANCH_NAME")
    PUSH_EXIT=$?
    if [[ $PUSH_EXIT -ne 0 ]]; then
        echo "Warning: failed to push $BRANCH_NAME in $REPO_PATH — skipping PR creation" >&2
        ~/.claude/notify.sh "Overnight push failed — $BRANCH_NAME not pushed in $REPO_NAME. Session: $SESSION_ID" || true
        echo "$REPO_PATH" >> "$PUSH_FAILED_REPOS_FILE"
        continue
    fi

    # Write PR body to temp file
    PR_BODY_FILE_CROSS="$TMPDIR/overnight-pr-body-${REPO_NAME}.txt"
    echo "Overnight session $SESSION_ID: $MERGED_COUNT features merged. See morning-report.md for details." > "$PR_BODY_FILE_CROSS"

    # Create PR, capture URL
    PR_ERR_FILE="$TMPDIR/pr-err-${REPO_NAME}.txt"
    PR_URL=$(gh pr create \
        --repo "$REPO_REMOTE" \
        --title "Overnight session: $BRANCH_NAME" \
        --base main \
        --head "$BRANCH_NAME" \
        --body-file "$PR_BODY_FILE_CROSS" \
        2>"$PR_ERR_FILE")
    PR_CREATE_EXIT=$?

    if [[ $PR_CREATE_EXIT -ne 0 ]] || [[ "$PR_URL" != https://* ]]; then
        # Attempt recovery for "already exists" case
        PR_URL=$(gh pr view --repo "$REPO_REMOTE" --head "$BRANCH_NAME" --json url --jq .url 2>/dev/null || echo "")
        if [[ "$PR_URL" != https://* ]]; then
            echo "Warning: PR creation failed for $REPO_NAME (exit $PR_CREATE_EXIT): $(cat "$PR_ERR_FILE")" >&2
            ~/.claude/notify.sh "Overnight PR creation failed — $REPO_NAME $BRANCH_NAME. Session: $SESSION_ID" || true
            PR_URL=""
        else
            echo "PR already exists for $REPO_NAME: $PR_URL"
        fi
    else
        echo "PR created for $REPO_NAME: $PR_URL"
    fi

    # Append to PR URLs JSON
    PR_URLS_FILE="$PR_URLS_FILE" REPO_PATH="$REPO_PATH" PR_URL="$PR_URL" python3 -c "
import json, os
from pathlib import Path
f = Path(os.environ['PR_URLS_FILE'])
data = json.loads(f.read_text())
data[os.environ['REPO_PATH']] = os.environ['PR_URL']
f.write_text(json.dumps(data))
"
done

# Create PR from integration branch to main
INTEGRATION_BRANCH=$(STATE_PATH="$STATE_PATH" python3 -c "
import json, os
state = json.load(open(os.environ['STATE_PATH']))
print(state.get('integration_branch') or '')
")

if [[ -n "$INTEGRATION_BRANCH" ]]; then
    # Push integration branch to remote before creating PR
    git push -u origin "$INTEGRATION_BRANCH" \
        && echo "Pushed $INTEGRATION_BRANCH to origin" \
        || {
            log_event "push_failed" "$(( ROUND - 1 ))" "{\"session_id\": \"$SESSION_ID\", \"branch\": \"$INTEGRATION_BRANCH\"}"
            ~/.claude/notify.sh "Overnight push failed — $INTEGRATION_BRANCH was not pushed to origin. Session: $SESSION_ID" || true
        }

    PR_BODY_FILE="$TMPDIR/overnight-pr-body.txt"
    MC_MERGED_COUNT=$(STATE_PATH="$STATE_PATH" python3 -c "
import json, os
state = json.load(open(os.environ['STATE_PATH']))
count = sum(
    1 for fs in state.get('features', {}).values()
    if fs.get('status') == 'merged' and fs.get('repo_path') is None
)
print(count)
")
    if [[ "$INTEGRATION_DEGRADED" == "true" ]] && [[ -f "$INTEGRATION_WARNING_FILE" ]]; then
        cat "$INTEGRATION_WARNING_FILE" > "$PR_BODY_FILE"
        echo "Overnight session $SESSION_ID: $MC_MERGED_COUNT features merged. See morning-report.md for details." >> "$PR_BODY_FILE"
    else
        echo "Overnight session $SESSION_ID: $MC_MERGED_COUNT features merged. See morning-report.md for details." > "$PR_BODY_FILE"
    fi
    MC_PR_URL=$(gh pr create \
        --title "Overnight session: $INTEGRATION_BRANCH" \
        --base main \
        --head "$INTEGRATION_BRANCH" \
        --body-file "$PR_BODY_FILE" \
        2>/dev/null)
    MC_PR_EXIT=$?
    if [[ $MC_PR_EXIT -ne 0 ]] || [[ "$MC_PR_URL" != https://* ]]; then
        MC_PR_URL=$(gh pr view --head "$INTEGRATION_BRANCH" --json url --jq .url 2>/dev/null || echo "")
        if [[ "$MC_PR_URL" != https://* ]]; then
            echo "Warning: PR creation failed (branch may already have a PR)"
            MC_PR_URL=""
        else
            echo "PR already exists for $INTEGRATION_BRANCH: $MC_PR_URL"
        fi
    else
        echo "PR created from $INTEGRATION_BRANCH to main: $MC_PR_URL"
    fi
    if [[ -n "$MC_PR_URL" ]]; then
        PR_URLS_FILE="$PR_URLS_FILE" HOME_PROJECT_ROOT="$HOME_PROJECT_ROOT" MC_PR_URL="$MC_PR_URL" python3 -c "
import json, os
from pathlib import Path
f = Path(os.environ['PR_URLS_FILE'])
data = json.loads(f.read_text()) if f.exists() else {}
data[os.path.realpath(os.environ['HOME_PROJECT_ROOT'])] = os.environ['MC_PR_URL']
f.write_text(json.dumps(data))
"
    fi
fi

# Generate morning report (after all PR creation so URLs are available)
if [[ -n "$TARGET_INTEGRATION_WORKTREE" ]]; then
    PR_URLS_FILE="$PR_URLS_FILE" STATE_PATH="$STATE_PATH" EVENTS_PATH="$EVENTS_PATH" HOME_PROJECT_ROOT="$HOME_PROJECT_ROOT" TARGET_INTEGRATION_WORKTREE="$TARGET_INTEGRATION_WORKTREE" SESSION_ID="$SESSION_ID" python3 -c "
import json, os
from pathlib import Path
from claude.overnight.report import generate_and_write_report
pr_urls_file = Path(os.environ['PR_URLS_FILE'])
pr_urls = json.loads(pr_urls_file.read_text()) if pr_urls_file.exists() else {}
sid = os.environ['SESSION_ID']
tiw = os.environ['TARGET_INTEGRATION_WORKTREE']
generate_and_write_report(
    state_path=Path(os.environ['STATE_PATH']),
    events_path=Path(os.environ['EVENTS_PATH']),
    deferred_dir=Path(os.environ['HOME_PROJECT_ROOT']) / 'lifecycle' / 'deferrals',
    pr_urls=pr_urls,
    report_dir=Path(tiw) / 'lifecycle' / 'sessions' / sid,
    results_dir=Path(tiw) / 'lifecycle' / 'sessions' / sid,
    project_root=Path(tiw),
)
" || echo "Warning: morning report generation failed"
else
    PR_URLS_FILE="$PR_URLS_FILE" STATE_PATH="$STATE_PATH" EVENTS_PATH="$EVENTS_PATH" HOME_PROJECT_ROOT="$HOME_PROJECT_ROOT" REPO_ROOT="$REPO_ROOT" SESSION_ID="$SESSION_ID" python3 -c "
import json, os
from pathlib import Path
from claude.overnight.report import generate_and_write_report
pr_urls_file = Path(os.environ['PR_URLS_FILE'])
pr_urls = json.loads(pr_urls_file.read_text()) if pr_urls_file.exists() else {}
sid = os.environ['SESSION_ID']
generate_and_write_report(
    state_path=Path(os.environ['STATE_PATH']),
    events_path=Path(os.environ['EVENTS_PATH']),
    deferred_dir=Path(os.environ['HOME_PROJECT_ROOT']) / 'lifecycle' / 'deferrals',
    pr_urls=pr_urls,
    report_dir=Path(os.environ['REPO_ROOT']) / 'lifecycle' / 'sessions' / sid,
)
" || echo "Warning: morning report generation failed"
fi

# ---------------------------------------------------------------------------
# Commit morning report
# ---------------------------------------------------------------------------
set +e
(
    cd "$REPO_ROOT"
    git add "lifecycle/sessions/${SESSION_ID}/morning-report.md" 2>/dev/null || true
    git add "lifecycle/morning-report.md"                        2>/dev/null || true
    git diff --cached --quiet || git commit -m "Overnight session ${SESSION_ID}: add morning report"
)

# Commit morning report in target project (cross-repo sessions only)
if [[ -n "$TARGET_INTEGRATION_WORKTREE" ]]; then
    TARGET_INTEGRATION_BRANCH=$(STATE_PATH="$STATE_PATH" HOME_PROJECT_ROOT="$HOME_PROJECT_ROOT" python3 -c "
import json, os
data = json.load(open(os.environ['STATE_PATH']))
branches = data.get('integration_branches', {})
repo_root = os.path.realpath(os.environ['HOME_PROJECT_ROOT'])
target = [b for k, b in branches.items() if os.path.realpath(k) != repo_root]
print(target[0] if target else '')
")
    if [[ -n "$TARGET_INTEGRATION_BRANCH" ]]; then
        (
            cd "$TARGET_INTEGRATION_WORKTREE"
            git add "lifecycle/sessions/${SESSION_ID}/morning-report.md"       2>/dev/null || true
            git add "lifecycle/sessions/${SESSION_ID}/batch-"*"-results.json"  2>/dev/null || true
            git add "lifecycle/sessions/${SESSION_ID}/overnight-strategy.json" 2>/dev/null || true
            git add "lifecycle/morning-report.md"                              2>/dev/null || true
            git diff --cached --quiet || git commit -m "Overnight session ${SESSION_ID}: add morning report and session artifacts"
        )
    fi
fi

# ---------------------------------------------------------------------------
# Push morning report to integration branch
# ---------------------------------------------------------------------------
if [[ -n "$INTEGRATION_BRANCH" ]]; then
    git push origin "${INTEGRATION_BRANCH}" \
        || {
            log_event "morning_report_commit_failed" "$(( ROUND - 1 ))" "{\"session_id\": \"$SESSION_ID\"}"
            ~/.claude/notify.sh "Overnight: morning report push failed for session ${SESSION_ID}" || true
        }
fi
# Push morning report in target project (cross-repo sessions only)
if [[ -n "$TARGET_INTEGRATION_WORKTREE" && -n "$TARGET_INTEGRATION_BRANCH" ]]; then
    (
        cd "$TARGET_INTEGRATION_WORKTREE"
        git push origin "$TARGET_INTEGRATION_BRANCH" \
            || {
                log_event "morning_report_commit_failed" "$(( ROUND - 1 ))" "{\"session_id\": \"$SESSION_ID\", \"target\": \"$TARGET_PROJECT_ROOT\"}"
                ~/.claude/notify.sh "Overnight: morning report push failed for target project ${TARGET_PROJECT_ROOT} session ${SESSION_ID}" || true
            }
    )
fi
set -e

# Notify on successful session completion
TOTAL_MERGED=$(STATE_PATH="$STATE_PATH" python3 -c "
import json, os
state = json.load(open(os.environ['STATE_PATH']))
count = sum(1 for fs in state.get('features', {}).values() if fs.get('status') == 'merged')
print(count)
")
TOTAL_FEATURES=$(STATE_PATH="$STATE_PATH" python3 -c "
import json, os
state = json.load(open(os.environ['STATE_PATH']))
print(len(state.get('features', {})))
")
PAUSED_REASON_FINAL=$(STATE_PATH="$STATE_PATH" python3 -c "import json, os; state = json.load(open(os.environ['STATE_PATH'])); print(state.get('paused_reason') or '')")
if [[ "$PAUSED_REASON_FINAL" == "budget_exhausted" ]]; then
    ~/.claude/notify.sh "Overnight session paused — API budget exhausted. Resume with /overnight resume when Anthropic limit resets. Session: $SESSION_ID" || true
else
    ~/.claude/notify.sh "Overnight complete — ${TOTAL_MERGED}/${TOTAL_FEATURES} features merged. Morning report ready. Session: $SESSION_ID" || true
fi

# ---------------------------------------------------------------------------
# Post-session cleanup: remove integration worktree and local branch
# ---------------------------------------------------------------------------
# Runs only on natural loop exit (complete, circuit-breaker, time-limit).
# SIGINT/SIGTERM triggers the cleanup() trap instead, which transitions to
# paused state — the worktree is intentionally kept for /overnight resume.
if [[ -n "$WORKTREE_PATH" ]]; then
    cd "$HOME_PROJECT_ROOT"

    # Update latest-overnight symlinks to point at permanent session dirs
    # (not the worktree path, which is about to be removed).
    ln -sfn "$REPO_ROOT/lifecycle/sessions/${SESSION_ID}" "$REPO_ROOT/lifecycle/sessions/latest-overnight" 2>/dev/null || true
    if [[ -n "$TARGET_PROJECT_ROOT" ]]; then
        mkdir -p "$TARGET_PROJECT_ROOT/lifecycle/sessions/"
        mkdir -p "$TARGET_PROJECT_ROOT/lifecycle/sessions/${SESSION_ID}/"
        ln -sfn "$TARGET_PROJECT_ROOT/lifecycle/sessions/${SESSION_ID}" "$TARGET_PROJECT_ROOT/lifecycle/sessions/latest-overnight" 2>/dev/null || true
    fi

    # Sync active-session pointer phase after symlink adjustment
    STATE_PATH="$STATE_PATH" python3 -c "
import json, os, tempfile
from pathlib import Path

pointer_path = Path.home() / '.local' / 'share' / 'overnight-sessions' / 'active-session.json'
if pointer_path.exists():
    try:
        data = json.loads(pointer_path.read_text())
        state = json.loads(Path(os.environ['STATE_PATH']).read_text())
        data['phase'] = state.get('phase', data['phase'])
        with tempfile.NamedTemporaryFile(mode='w', dir=str(pointer_path.parent), delete=False, suffix='.tmp') as f:
            json.dump(data, f)
            tmp_path = f.name
        os.replace(tmp_path, pointer_path)
    except Exception:
        pass
" || true

    git worktree remove --force "$WORKTREE_PATH" \
        && echo "Worktree removed: $WORKTREE_PATH" \
        || echo "Warning: failed to remove worktree at $WORKTREE_PATH" >&2
fi

if [[ -n "$INTEGRATION_BRANCH" ]]; then
    git branch -D "$INTEGRATION_BRANCH" \
        && echo "Local branch deleted: $INTEGRATION_BRANCH" \
        || echo "Warning: could not delete local branch $INTEGRATION_BRANCH" >&2
fi

# Delete integration branches in cross-repo target repos
# (push already happened in the PR creation block above;
# skip branch deletion for push-failed repos to preserve local work)
STATE_PATH="$STATE_PATH" HOME_PROJECT_ROOT="$HOME_PROJECT_ROOT" python3 -c "
import json, os
data = json.load(open(os.environ['STATE_PATH']))
repo_root = os.path.realpath(os.environ['HOME_PROJECT_ROOT'])
for repo_path, branch_name in data.get('integration_branches', {}).items():
    if os.path.realpath(repo_path) == repo_root:
        continue
    print(repo_path + '|' + branch_name)
" | while IFS='|' read -r REPO_PATH BRANCH_NAME; do
    # Skip branch deletion if push failed (local branch is only remaining reference)
    if grep -qF "$REPO_PATH" "$PUSH_FAILED_REPOS_FILE" 2>/dev/null; then
        echo "Skipping branch deletion for $REPO_PATH — push failed, preserving local branch"
        continue
    fi
    (cd "$REPO_PATH" && git branch -D "$BRANCH_NAME") \
        || echo "Warning: failed to delete $BRANCH_NAME in $REPO_PATH" >&2
done

rm -f "$LOCK_FILE"
echo "Done."
