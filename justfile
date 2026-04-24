set dotenv-load
set quiet

default:
    @just --list

# --- Dependencies ---

# Set up Python virtual environment and install dependencies
python-setup:
    #!/usr/bin/env bash
    set -euo pipefail
    if \! command -v uv &>/dev/null; then
        echo "uv not found — install with: brew install uv"
        exit 1
    fi
    uv sync

# Upgrade Python dependencies to latest and update uv.lock
upgrade-deps:
    uv sync --upgrade

# --- PAT ---

# Store a GitHub PAT in macOS Keychain for sandbox-safe gh operations
setup-github-pat:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== GitHub PAT Setup ==="
    echo "This stores a fine-grained PAT in macOS Keychain so Claude Code"
    echo "sandbox sessions can authenticate with GitHub via gh."
    echo ""
    read -rs -p "GitHub PAT (fine-grained, hidden): " PAT
    echo
    if [ -z "$PAT" ]; then
        echo "Error: PAT cannot be empty."
        exit 1
    fi
    echo "Validating token..."
    if ! LOGIN=$(GH_TOKEN="$PAT" gh api user --jq '.login' 2>&1); then
        echo "Token invalid or gh api call failed:"
        echo "  $LOGIN"
        exit 1
    fi
    echo "Authenticated as: $LOGIN"
    echo ""
    read -rp "Expiry date (YYYY-MM-DD): " EXPIRY
    if [ -z "$EXPIRY" ]; then
        echo "Error: expiry date cannot be empty."
        exit 1
    fi
    security add-generic-password -U -s github-pat -a default -w "$PAT"
    echo "Stored PAT in Keychain (service: github-pat)"
    security add-generic-password -U -s github-pat-expiry -a default -w "$EXPIRY"
    echo "Stored expiry in Keychain (service: github-pat-expiry)"
    mkdir -p ~/.config/claude-code-secrets
    printf '%s' "$PAT" > ~/.config/claude-code-secrets/github-pat
    chmod 0600 ~/.config/claude-code-secrets/github-pat
    echo "Stored PAT in ~/.config/claude-code-secrets/github-pat (sandbox fallback)"
    echo ""
    echo "Done! To enable the session-start hook, run:"
    echo "  ln -s $(pwd)/claude/hooks/setup-github-pat.sh ~/.claude/hooks/setup-github-pat.sh"

# Store a GitHub org PAT in macOS Keychain for sandbox-safe gh operations on org repos
setup-github-pat-org:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== GitHub Org PAT Setup ==="
    echo "This stores a fine-grained org PAT in macOS Keychain so Claude Code"
    echo "sandbox sessions can authenticate with GitHub org repos via gh."
    echo ""
    read -rp "GitHub org name (e.g., my-org): " ORG
    if [ -z "$ORG" ]; then
        echo "Error: org name cannot be empty."
        exit 1
    fi
    read -rs -p "GitHub org PAT (fine-grained, hidden): " PAT
    echo
    if [ -z "$PAT" ]; then
        echo "Error: PAT cannot be empty."
        exit 1
    fi
    echo "Validating token against org $ORG..."
    if ! ORG_LOGIN=$(GH_TOKEN="$PAT" gh api "orgs/$ORG" --jq '.login' 2>&1); then
        echo "Token invalid or org not accessible. Check that:"
        echo "  1. The PAT has the correct scopes for $ORG repos"
        echo "  2. The PAT has been SSO-authorized for $ORG (see reminder below)"
        echo "  $ORG_LOGIN"
        exit 1
    fi
    echo "Authenticated — org $ORG_LOGIN is accessible"
    echo ""
    read -rp "Expiry date (YYYY-MM-DD): " EXPIRY
    if [ -z "$EXPIRY" ]; then
        echo "Error: expiry date cannot be empty."
        exit 1
    fi
    security add-generic-password -U -s github-pat-org -a default -w "$PAT"
    echo "Stored org PAT in Keychain (service: github-pat-org)"
    security add-generic-password -U -s github-pat-org-expiry -a default -w "$EXPIRY"
    echo "Stored expiry in Keychain (service: github-pat-org-expiry)"
    mkdir -p ~/.config/claude-code-secrets
    printf '%s' "$PAT" > ~/.config/claude-code-secrets/github-pat-org
    chmod 0600 ~/.config/claude-code-secrets/github-pat-org
    echo "Stored org PAT in ~/.config/claude-code-secrets/github-pat-org (sandbox fallback)"
    echo ""
    echo "IMPORTANT: This PAT must be SSO-authorized before it will work."
    echo "  Go to: https://github.com/settings/tokens"
    echo "  Find your PAT → 'Configure SSO' → authorize for org $ORG"
    echo ""
    echo "Done! The session-start hook will inject the org PAT automatically."
    echo "To use in an org repo, add a .use-org-pat file at the repo root."

# Add tmux socket to sandbox allowlist so sandboxed sessions can access tmux
setup-tmux-socket:
    #!/usr/bin/env bash
    set -euo pipefail
    SETTINGS="$HOME/.claude/settings.json"
    LOCAL_SETTINGS="$HOME/.claude/settings.local.json"
    TMUX_SOCKET="/private/tmp/tmux-$(id -u)/default"
    if ! command -v jq &>/dev/null; then
        echo "Error: jq is required. Install with: brew install jq" >&2
        exit 1
    fi
    if [ ! -f "$SETTINGS" ]; then
        echo "Error: $SETTINGS not found. Install the cortex-interactive plugin first." >&2
        exit 1
    fi
    # Check if tmux socket is already in settings.local.json
    if [ -f "$LOCAL_SETTINGS" ] && jq -e --arg sock "$TMUX_SOCKET" '.sandbox.network.allowUnixSockets // [] | map(select(. == $sock)) | length > 0' "$LOCAL_SETTINGS" >/dev/null 2>&1; then
        echo "tmux socket already present in $LOCAL_SETTINGS — skipping."
        exit 0
    fi
    # Read existing allowUnixSockets from settings.json (contains GPG socket etc.)
    EXISTING_SOCKETS=$(jq -c '.sandbox.network.allowUnixSockets // []' "$SETTINGS")
    # Build combined array: existing sockets + tmux socket, deduplicated
    COMBINED=$(echo "$EXISTING_SOCKETS" | jq -c --arg sock "$TMUX_SOCKET" '. + [$sock] | unique')
    # Deep-merge into settings.local.json (or create if missing)
    if [ -f "$LOCAL_SETTINGS" ]; then
        jq --argjson sockets "$COMBINED" '.sandbox.network.allowUnixSockets = $sockets' "$LOCAL_SETTINGS" > "$LOCAL_SETTINGS.tmp"
        mv "$LOCAL_SETTINGS.tmp" "$LOCAL_SETTINGS"
    else
        mkdir -p "$(dirname "$LOCAL_SETTINGS")"
        jq -n --argjson sockets "$COMBINED" '{"sandbox": {"network": {"allowUnixSockets": $sockets}}}' > "$LOCAL_SETTINGS"
    fi
    echo "Adding tmux socket access to sandbox allowlist. This grants sandboxed sessions access to ALL tmux sessions on this machine."
    echo ""
    echo "Socket path: $TMUX_SOCKET"
    echo "Updated: $LOCAL_SETTINGS"
    jq '.sandbox.network.allowUnixSockets' "$LOCAL_SETTINGS"

# --- Overnight ---

# Run the overnight round-loop runner
# Usage: just overnight-run <state-path> <time-limit-hours>  (args are positional)
overnight-run state="lifecycle/sessions/latest-overnight/overnight-state.json" time-limit="6" max-rounds="10" tier="max_100":
    #!/usr/bin/env bash
    set -euo pipefail
    STATE="{{ state }}"
    if [[ "$STATE" == --* || "$STATE" == *=* ]]; then
        echo "Error: wrong arg format — use positional syntax:" >&2
        echo "  just overnight-run <state-path> <time-limit-hours>" >&2
        echo "  just overnight-run lifecycle/sessions/.../overnight-state.json 6h" >&2
        exit 1
    fi
    bash "{{justfile_directory()}}/cortex_command/overnight/runner.sh" --state {{ state }} --time-limit {{ time-limit }} --max-rounds {{ max-rounds }} --tier {{ tier }}

# Launch overnight runner in a detached tmux session (recommended for unattended runs)
# Usage: just overnight-start <state-path> <time-limit-hours>  (args are positional)
overnight-start state="" time-limit="6" max-rounds="10" tier="max_100":
    #!/usr/bin/env bash
    set -euo pipefail
    STATE="{{ state }}"
    if [[ "$STATE" == --* || "$STATE" == *=* ]]; then
        echo "Error: wrong arg format — use positional syntax:" >&2
        echo "  just overnight-start <state-path> <time-limit-hours>" >&2
        echo "  just overnight-start lifecycle/sessions/.../overnight-state.json 6h" >&2
        exit 1
    fi
    if \! command -v tmux &>/dev/null; then
        echo "tmux not found — run in foreground with: just overnight-run" >&2
        exit 1
    fi
    SESSION="overnight-runner"
    N=2
    while tmux has-session -t "=$SESSION" 2>/dev/null; do
        SESSION="overnight-runner-$N"
        N=$((N + 1))
    done
    REPO_ROOT="{{justfile_directory()}}"
    STATE_ARG=""
    if [[ -n "{{ state }}" ]]; then
        STATE_ARG="--state {{ state }}"
    fi
    tmux new-session -d -s "$SESSION" -c "$REPO_ROOT" \
        "bash \"{{justfile_directory()}}/cortex_command/overnight/runner.sh\" $STATE_ARG --time-limit {{ time-limit }} --max-rounds {{ max-rounds }} --tier {{ tier }}"
    echo "Overnight runner started in tmux session '$SESSION'"
    echo "  Attach : tmux attach -t $SESSION"
    echo "  Watch  : tail -f lifecycle/sessions/latest-overnight/overnight-events.log"
    just overnight-status

# Schedule an overnight run to start at a specific time (e.g. just overnight-schedule 23:00)
overnight-schedule target-time state="" time-limit="6" max-rounds="10" tier="max_100":
    overnight-schedule "{{ target-time }}" "{{ state }}" "{{ time-limit }}" "{{ max-rounds }}" "{{ tier }}"

# Show a live auto-refreshing status display for the active overnight session
overnight-status:
    #!/usr/bin/env bash
    trap 'exit 0' INT
    while true; do
        clear
        uv run python3 -m cortex_command.overnight.status
        sleep 5
    done

# Run the overnight smoke test (verifies worker commit round-trip)
overnight-smoke-test:
    uv run python3 -m cortex_command.overnight.smoke_test

# Tail the current session's events log with pretty-printed JSON output
overnight-logs:
    #!/usr/bin/env bash
    set -euo pipefail
    LOGFILE="lifecycle/sessions/latest-overnight/overnight-events.log"
    if [ \! -f "$LOGFILE" ]; then
        echo "No active session log"
        exit 1
    fi
    if command -v jq > /dev/null 2>&1; then
        tail -f "$LOGFILE" | jq '.'
    else
        tail -f "$LOGFILE" | python3 -m json.tool
    fi

# --- Dashboard ---

dashboard_port := env_var_or_default("DASHBOARD_PORT", "8080")

# Start the dashboard FastAPI server (no-op if already running)
dashboard:
    #!/usr/bin/env bash
    set -e
    PID_FILE="cortex_command/dashboard/.pid"
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "Dashboard already running (PID $PID). Open http://localhost:{{dashboard_port}}"
            exit 0
        fi
    fi
    echo "Dashboard running at http://0.0.0.0:{{dashboard_port}}"
    uv run uvicorn cortex_command.dashboard.app:app --host 0.0.0.0 --port {{dashboard_port}}

# Write fixture files for visual dashboard testing (overnight state, events, features, backlog)
dashboard-seed:
    uv run python3 -m cortex_command.dashboard.seed

# Remove all fixture files written by dashboard-seed
dashboard-seed-clean:
    uv run python3 -m cortex_command.dashboard.seed --clean

# --- Backlog ---

# Regenerate the backlog index
backlog-index:
    python3 backlog/generate_index.py

# Mark a backlog item as complete by name, ID, or UUID (updates frontmatter in place, cleans blocked-by, regenerates index)
backlog-close feature="":
    python3 backlog/update_item.py {{ feature }} status=complete

# Move completed lifecycle dirs (events.log contains "feature_complete") to lifecycle/archive/
lifecycle-archive:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p lifecycle/archive
    # Build list of active worktree paths to avoid moving checked-out worktrees
    worktree_paths=$(git worktree list --porcelain | awk '/^worktree / {print $2}')
    count=0
    for events_log in lifecycle/*/events.log; do
        [ -f "$events_log" ] || continue
        dir=$(dirname "$events_log")
        # Skip lifecycle/archive and lifecycle/sessions
        case "$dir" in
            lifecycle/archive|lifecycle/archive/*|lifecycle/sessions|lifecycle/sessions/*) continue ;;
        esac
        # Skip if this dir is an active git worktree
        abs_dir=$(realpath "$dir")
        skip=0
        while IFS= read -r wt_path; do
            if [ "$abs_dir" = "$wt_path" ]; then
                skip=1
                break
            fi
        done <<< "$worktree_paths"
        [ "$skip" -eq 1 ] && continue
        # Only archive if events.log contains feature_complete
        if grep -q '"feature_complete"' "$events_log"; then
            mv "$dir" lifecycle/archive/
            count=$((count + 1))
        fi
    done
    echo "$count lifecycle directories archived"

# --- Validation ---

# Test the commit message hook
validate-commit msg="Test commit message":
    echo "{{ msg }}" | bash hooks/cortex-validate-commit.sh

# Validate prompt contract frontmatter across all skills
validate-skills:
    python3 scripts/validate-skill.py skills/

# Validate preconditions for a specific skill
validate-skill-preconditions skill:
    python3 scripts/validate-preconditions.py {{skill}}

# Validate spec.md structural compliance (pre-flight before orchestrator review)
validate-spec *args:
    python3 bin/validate-spec {{args}}

# Verify setup including full test suite
verify-setup-full:
    just verify-setup
    just test

# --- Testing ---

# Run skill contract tests (validates SKILL.md frontmatter across all skills)
test-skill-contracts:
    #!/usr/bin/env bash
    set -euo pipefail
    python3 scripts/validate-skill.py skills/
    python3 scripts/validate-callgraph.py skills/ .claude/skills/
    uv run pytest tests/test_skill_contracts.py tests/test_skill_callgraph.py -q

# Run commit hook regression tests
test-hook-commit:
    bash tests/test_hook_commit.sh

# Run all hook regression tests
test-hooks:
    bash tests/test_hooks.sh

# Run lifecycle state machine tests
test-lifecycle-state:
    uv run pytest tests/test_lifecycle_state.py -q

# Run behavioral tests for the commit skill hook
test-skill-behavior:
    bash tests/test_skill_behavior.sh

# Run pressure tests for a specific skill (expensive, on-demand only)
test-skill-pressure skill:
    python3 tests/pressure_runner.py {{ skill }}

# Run the transition failure matrix report
failure-matrix:
    python3 tests/failure_matrix.py

# Run pipeline dispatcher tests (requires venv — run 'just python-setup' first)
test-pipeline:
    #!/usr/bin/env bash
    set -euo pipefail
    [ -f .venv/bin/pytest ] || { echo "venv not found — run 'just python-setup' first"; exit 1; }
    .venv/bin/pytest cortex_command/pipeline/tests/ -q

# Run overnight runner tests (requires venv — run 'just python-setup' first)
test-overnight:
    #!/usr/bin/env bash
    set -euo pipefail
    [ -f .venv/bin/pytest ] || { echo "venv not found — run 'just python-setup' first"; exit 1; }
    .venv/bin/pytest cortex_command/overnight/tests/ -q

# Run all pipeline and overnight test suites and print aggregate pass/fail summary
test:
    #!/usr/bin/env bash
    set -uo pipefail
    passed=0
    failed=0
    run_test() {
        local name="$1"
        shift
        local output
        if output=$("$@" 2>&1); then
            echo "[PASS] $name"
            passed=$((passed + 1))
        else
            echo "[FAIL] $name"
            echo "$output" | sed 's/^/       /'
            failed=$((failed + 1))
        fi
    }
    run_test "test-pipeline" just test-pipeline
    run_test "test-overnight" just test-overnight
    run_test "tests" .venv/bin/pytest tests/ -q
    total=$((passed + failed))
    echo ""
    echo "Test suite: $passed/$total passed"
    if [ "$failed" -gt 0 ]; then
        exit 1
    fi

# Run all test suites and print aggregate pass/fail summary
test-skills:
    #!/usr/bin/env bash
    set -uo pipefail
    passed=0
    failed=0
    run_test() {
        local name="$1"
        shift
        local output
        if output=$("$@" 2>&1); then
            echo "[PASS] $name"
            passed=$((passed + 1))
        else
            echo "[FAIL] $name"
            echo "$output" | sed 's/^/       /'
            failed=$((failed + 1))
        fi
    }
    run_test "test-skill-contracts" just test-skill-contracts
    run_test "test-hook-commit"     just test-hook-commit
    run_test "test-hooks"           just test-hooks
    run_test "test-lifecycle-state" just test-lifecycle-state
    total=$((passed + failed))
    echo ""
    echo "Test suite: $passed/$total passed"
    if [ "$failed" -gt 0 ]; then
        exit 1
    fi

# --- Claude ---

# Launch Claude with --dangerously-skip-permissions
dangerous:
    claude --dangerously-skip-permissions
