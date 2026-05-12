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
        echo "Error: $SETTINGS not found. Install the cortex-core plugin first." >&2
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

# Async-spawn the overnight round-loop runner (detaches; use `cortex overnight status` to track)
# Usage: just overnight-run <state-path> <time-limit-seconds>  (args are positional)
overnight-run state="cortex/lifecycle/sessions/latest-overnight/overnight-state.json" time-limit="21600" max-rounds="10" tier="simple":
    #!/usr/bin/env bash
    set -euo pipefail
    STATE="{{ state }}"
    if [[ "$STATE" == --* || "$STATE" == *=* ]]; then
        echo "Error: wrong arg format — use positional syntax:" >&2
        echo "  just overnight-run <state-path> <time-limit-seconds>" >&2
        echo "  just overnight-run cortex/lifecycle/sessions/.../overnight-state.json 21600" >&2
        exit 1
    fi
    cortex overnight start --state {{ state }} --time-limit {{ time-limit }} --max-rounds {{ max-rounds }} --tier {{ tier }}

# Run the overnight smoke test (verifies worker commit round-trip)
overnight-smoke-test:
    uv run python3 -m cortex_command.overnight.smoke_test

# Tail the current session's events log with pretty-printed JSON output
overnight-logs:
    #!/usr/bin/env bash
    set -euo pipefail
    LOGFILE="cortex/lifecycle/sessions/latest-overnight/overnight-events.log"
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
    PID_FILE="${XDG_CACHE_HOME:-$HOME/.cache}/cortex/dashboard.pid"
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
    cortex-generate-backlog-index

# Mark a backlog item as complete by name, ID, or UUID (updates frontmatter in place, cleans blocked-by, regenerates index)
backlog-close feature="":
    cortex-update-item {{ feature }} status=complete

# Move completed lifecycle dirs (events.log contains "feature_complete") to lifecycle/archive/
# Flags:
#   --dry-run               Print archive + rewrite candidates without performing mv or path rewrites.
#   --from-file <path>      Limit iteration to slugs (basenames) listed in <path>, one per line.
# Recovery on mid-run failure: `git checkout -- .` (working-tree changes since precheck baseline).
# The manifest at lifecycle/archive/.archive-manifest.jsonl is for audit/inspection only.
lifecycle-archive *args:
    #!/usr/bin/env bash
    set -euo pipefail
    # CRITICAL: just shebang recipes do NOT auto-pass declared args as $1, $2,
    # ...  — they must be made positional explicitly. Without this `set --`,
    # the flag-parser below sees $# = 0, dry_run stays 0, from_file stays "",
    # and EVERY invocation runs destructively on ALL candidates. Verified by
    # incident where `just lifecycle-archive --dry-run` archived 111 dirs.
    set -- {{args}}
    # --- Parse flags ---
    dry_run=0
    from_file=""
    exclude_dir_paths=()
    while [ $# -gt 0 ]; do
        case "$1" in
            --dry-run) dry_run=1; shift ;;
            --from-file) from_file="${2:-}"; shift 2 ;;
            --from-file=*) from_file="${1#--from-file=}"; shift ;;
            --exclude-dir) exclude_dir_paths+=("${2:-}"); shift 2 ;;
            --exclude-dir=*) exclude_dir_paths+=("${1#--exclude-dir=}"); shift ;;
            *) echo "lifecycle-archive: unknown arg: $1" >&2; exit 2 ;;
        esac
    done
    # Build forwarded helper args from exclude_dir_paths (one --exclude-dir per value).
    # Bash 3.2 + set -u: bare "${arr[@]}" on empty array triggers unbound; guard with +.
    exclude_dir_args=()
    for excl in "${exclude_dir_paths[@]+"${exclude_dir_paths[@]}"}"; do
        exclude_dir_args+=(--exclude-dir "$excl")
    done
    # --- Clean-tree precheck (applies to BOTH dry-run and real-run; spec §N6.5 + edge case) ---
    if ! git diff --quiet HEAD || ! git diff --quiet --cached HEAD; then
        echo "lifecycle-archive: working tree is dirty; commit or stash before running (this applies to --dry-run too)." >&2
        exit 1
    fi
    # --- Load --from-file slug filter (if given) ---
    # Use a newline-delimited string (with leading+trailing newline sentinels)
    # rather than `declare -A` so the recipe runs on macOS bash 3.2, which
    # predates associative arrays. Membership test below is a fixed-string
    # grep against "\n<slug>\n".
    from_file_slugs=$'\n'
    use_from_file=0
    if [ -n "$from_file" ]; then
        if [ ! -f "$from_file" ]; then
            echo "lifecycle-archive: --from-file path not found: $from_file" >&2
            exit 1
        fi
        use_from_file=1
        while IFS= read -r line || [ -n "$line" ]; do
            # Strip whitespace and skip blanks/comments
            slug="${line%%#*}"
            slug="$(echo "$slug" | awk '{$1=$1; print}')"
            [ -z "$slug" ] && continue
            from_file_slugs="${from_file_slugs}${slug}"$'\n'
        done < "$from_file"
    fi
    mkdir -p cortex/lifecycle/archive
    manifest="cortex/lifecycle/archive/.archive-manifest.jsonl"
    lockdir="cortex/lifecycle/archive/.archive-manifest.lock"
    # Build list of active worktree paths to avoid moving checked-out worktrees
    worktree_paths=$(git worktree list --porcelain | awk '/^worktree / {print $2}')
    # --- Pass 1: build candidate slug list ---
    candidates=()
    for events_log in cortex/lifecycle/*/events.log; do
        [ -f "$events_log" ] || continue
        dir=$(dirname "$events_log")
        # Skip cortex/lifecycle/archive and cortex/lifecycle/sessions
        case "$dir" in
            cortex/lifecycle/archive|cortex/lifecycle/archive/*|cortex/lifecycle/sessions|cortex/lifecycle/sessions/*) continue ;;
        esac
        # Stale-symlink guard: skip broken symlinks before realpath (spec edge case "N6 stale symlinks")
        [ -e "$dir" ] || continue
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
        # Match both NDJSON-form ("event": "feature_complete") and YAML-block-form (event: feature_complete) entries.
        grep -qE '"event":[[:space:]]*"feature_complete"|^[[:space:]]*event:[[:space:]]*feature_complete[[:space:]]*$' "$events_log" || continue
        slug="$(basename "$dir")"
        # Apply --from-file slug filter if set (fixed-string membership test
        # against the newline-delimited from_file_slugs sentinel string).
        if [ "$use_from_file" -eq 1 ]; then
            case "$from_file_slugs" in
                *$'\n'"$slug"$'\n'*) ;; # match — keep
                *) continue ;;          # not in sample list — skip
            esac
        fi
        candidates+=("$dir")
    done
    # --- Dry-run: print candidates + rewrite candidates and exit ---
    if [ "$dry_run" -eq 1 ]; then
        echo "archive candidates:"
        if [ "${#candidates[@]}" -eq 0 ]; then
            echo "  (none)"
        else
            for d in "${candidates[@]}"; do
                echo "  $d"
            done
        fi
        echo "rewrite candidates:"
        if [ "${#candidates[@]}" -eq 0 ]; then
            echo "  (none)"
        else
            # Use the same boundary-anchored pattern the helper (T12) will use:
            # boundary char class [A-Za-z0-9_/-] treats hyphens as word-equivalent
            # so prefix-substring slugs (add-foo vs add-foo-bar) do not collide.
            for d in "${candidates[@]}"; do
                slug="$(basename "$d")"
                # Pattern matches lifecycle/<slug> not preceded/followed by [A-Za-z0-9_/-].
                pat='(^|[^A-Za-z0-9_/-])lifecycle/'"$slug"'($|[^A-Za-z0-9_/-])'
                # Search *.md under repo root, excluding .git, lifecycle/archive,
                # lifecycle/sessions, and retros (retros are immutable).
                files=$(grep -rlE "$pat" \
                    --include='*.md' \
                    --exclude-dir=.git \
                    --exclude-dir=archive \
                    --exclude-dir=sessions \
                    --exclude-dir=retros \
                    . 2>/dev/null || true)
                # Post-filter: drop paths under any --exclude-dir value.
                # grep --exclude-dir matches directory names, not paths, so
                # a value like research/repo-spring-cleaning will not be
                # honored by grep itself; this filter enforces it.
                for excl in "${exclude_dir_paths[@]+"${exclude_dir_paths[@]}"}"; do
                    excl_norm="${excl%/}"
                    excl_norm="${excl_norm#./}"
                    files=$(printf '%s\n' "$files" | grep -vE "^\\./?${excl_norm}/" || true)
                done
                if [ -n "$files" ]; then
                    echo "  [$slug]"
                    echo "$files" | sed 's|^|    |'
                fi
            done
        fi
        echo "(dry-run: no mv or rewrite performed; ${#candidates[@]} candidate dir(s))"
        exit 0
    fi
    # --- Real run: per-slug rewrite + mv + manifest append ---
    count=0
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    for dir in "${candidates[@]}"; do
        slug="$(basename "$dir")"
        # --- Rewrite step (T12: bin/cortex-archive-rewrite-paths) ---
        # Python helper handles the three citation forms (slash, wikilink,
        # bare) with explicit boundary char classes (NOT regex \b — BSD sed
        # silently no-ops on \b, and \b treats hyphens as word boundaries
        # which incorrectly accepts add-foo inside add-foo-bar). Writes are
        # atomic via tempfile + os.replace, so no .bak cleanup is needed.
        # Helper emits one JSON line per slug to stdout: we capture it and
        # extract rewritten_files for the manifest entry below.
        rewrite_json=$(bin/cortex-archive-rewrite-paths --slug "$slug" "${exclude_dir_args[@]+"${exclude_dir_args[@]}"}")
        rewritten_json=$(printf '%s' "$rewrite_json" | python3 -c 'import json,sys; print(json.dumps(json.loads(sys.stdin.read())["rewritten_files"]))')
        src="$dir"
        dst="cortex/lifecycle/archive/$slug"
        line=$(python3 -c 'import json,sys; print(json.dumps({"ts": sys.argv[1], "src": sys.argv[2], "dst": sys.argv[3], "rewritten_files": json.loads(sys.argv[4])}))' "$ts" "$src" "$dst" "$rewritten_json")
        # --- Atomic append under mkdir-based lock (portable; flock unavailable on macOS) ---
        # Acquire lock (busy-wait briefly; mkdir is atomic on POSIX).
        attempts=0
        until mkdir "$lockdir" 2>/dev/null; do
            attempts=$((attempts + 1))
            if [ "$attempts" -gt 50 ]; then
                echo "lifecycle-archive: could not acquire manifest lock at $lockdir" >&2
                exit 1
            fi
            sleep 0.1
        done
        trap 'rmdir "$lockdir" 2>/dev/null || true' EXIT
        # Tempfile + mv for atomic durable append: copy current manifest (if any),
        # append the new line, then mv into place.
        tmp_manifest="${manifest}.tmp.$$"
        if [ -f "$manifest" ]; then
            cp "$manifest" "$tmp_manifest"
        else
            : > "$tmp_manifest"
        fi
        printf '%s\n' "$line" >> "$tmp_manifest"
        mv "$tmp_manifest" "$manifest"
        rmdir "$lockdir" 2>/dev/null || true
        trap - EXIT
        # --- Move the directory ---
        mv "$dir" cortex/lifecycle/archive/
        count=$((count + 1))
    done
    echo "$count lifecycle directories archived"

# --- Validation ---

# Test the commit message hook
validate-commit msg="Test commit message":
    echo "{{ msg }}" | bash hooks/cortex-validate-commit.sh

# Validate prompt contract frontmatter across all skills
validate-skills:
    ./scripts/validate-skill.py skills/

# Validate preconditions for a specific skill
validate-skill-preconditions skill:
    ./scripts/validate-preconditions.py {{skill}}

# Check SKILL.md-to-bin parity (per DR-5 / lifecycle 102)
check-parity *args:
    python3 bin/cortex-check-parity {{args}}

# Check skill-prompt emissions are declared in bin/.events-registry.md (R5 staged-mode gate)
check-events-registry:
    bin/cortex-check-events-registry --staged

# Check ticket bodies / skill prose for prescriptive-prose violations (LEX-1 scanner, R6/R7)
check-prescriptive-prose *args:
    bin/cortex-check-prescriptive-prose --staged {{args}}

# Measure per-skill combined description: + when_to_use: UTF-8 byte size (L1 boot-context surface)
measure-l1-surface:
    bin/cortex-measure-l1-surface

# Audit the events registry for stale deprecation rows or missing owners (R5 audit mode, off critical path)
check-events-registry-audit:
    bin/cortex-check-events-registry --audit

# --- Testing ---

# Run skill contract tests (validates SKILL.md frontmatter across all skills)
test-skill-contracts:
    #!/usr/bin/env bash
    set -euo pipefail
    ./scripts/validate-skill.py skills/
    ./scripts/validate-callgraph.py skills/ .claude/skills/
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

# Run cortex init tests (requires venv — run 'just python-setup' first)
test-init:
    #!/usr/bin/env bash
    set -euo pipefail
    [ -f .venv/bin/pytest ] || { echo "venv not found — run 'just python-setup' first"; exit 1; }
    .venv/bin/pytest cortex_command/init/tests/ -q

# Run skill-design test infrastructure (descriptions, handoffs, size budget, lifecycle refs)
test-skill-design:
    .venv/bin/pytest tests/test_skill_descriptions.py tests/test_skill_handoff.py tests/test_skill_size_budget.py tests/test_lifecycle_references_resolve.py -q

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
    run_test "test-init" just test-init
    run_test "test-install" bash tests/test_install.sh
    run_test "tests" .venv/bin/pytest tests/ -q
    run_test "tests-takeover-stress" .venv/bin/pytest tests/test_runner_concurrent_start_race.py::test_two_starters_with_stale_preexisting_lock --count=50 -p no:cacheprovider -q
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
    run_test "test-skill-design" just test-skill-design
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

# --- Plugin ---

BUILD_OUTPUT_PLUGINS := "cortex-core cortex-overnight"
HAND_MAINTAINED_PLUGINS := "cortex-pr-review cortex-ui-extras android-dev-extras cortex-dev-extras"

_list-build-output-plugins:
    #!/usr/bin/env bash
    set -euo pipefail
    echo '{{BUILD_OUTPUT_PLUGINS}}' | tr ' ' '\n'

_list-hand-maintained-plugins:
    #!/usr/bin/env bash
    set -euo pipefail
    echo '{{HAND_MAINTAINED_PLUGINS}}' | tr ' ' '\n'

# Regenerate build-output plugin trees from top-level sources (skills/, bin/cortex-*, hooks/cortex-*.sh, claude/hooks/cortex-*.sh)
build-plugin:
    #!/usr/bin/env bash
    set -euo pipefail
    for p in {{BUILD_OUTPUT_PLUGINS}}; do
        [[ -d plugins/$p/.claude-plugin ]] || { echo "build-plugin: skipping $p (not yet materialized)" >&2; continue; }
        BIN=()
        case "$p" in
            cortex-core)
                SKILLS=(commit pr lifecycle backlog requirements research discovery refine dev diagnose critical-review)
                HOOKS=(hooks/cortex-validate-commit.sh claude/hooks/cortex-worktree-create.sh claude/hooks/cortex-worktree-remove.sh)
                BIN=(cortex-)
                ;;
            cortex-overnight)
                BIN=()
                SKILLS=(overnight morning-review)
                HOOKS=(hooks/cortex-cleanup-session.sh hooks/cortex-scan-lifecycle.sh claude/hooks/cortex-tool-failure-tracker.sh claude/hooks/cortex-permission-audit-log.sh)
                ;;
            *)
                echo "build-plugin: no manifest for $p" >&2
                continue
                ;;
        esac
        for s in "${SKILLS[@]}"; do
            rsync -a --delete "skills/$s/" "plugins/$p/skills/$s/"
        done
        rm -f plugins/$p/hooks/cortex-*.sh
        for h in "${HOOKS[@]}"; do
            rsync -a "$h" "plugins/$p/hooks/$(basename "$h")"
        done
        if [[ ${#BIN[@]} -gt 0 ]]; then
            rsync -a --delete --include='cortex-*' --exclude='*' bin/ "plugins/$p/bin/"
        fi
    done

# Point git at .githooks/ so the dual-source drift pre-commit hook runs on every commit
setup-githooks:
    git config core.hooksPath .githooks
    echo "git hooksPath set to .githooks/ — dual-source drift pre-commit hook is active."
