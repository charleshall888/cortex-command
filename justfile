set dotenv-load
set quiet

default:
    @just --list

# --- Setup ---

# Deploy the full agentic layer: bin, reference, skills, hooks, config, Python deps
setup:
    just deploy-bin
    just deploy-reference
    just deploy-skills
    just deploy-hooks
    just deploy-config
    just python-setup
    @echo ""
    @echo "Setup complete. Add the following to your shell profile (.zshrc, .bashrc, etc.):"
    @echo ""
    @echo "  export CORTEX_COMMAND_ROOT=\"$(pwd)\""
    @echo ""
    @echo "Then restart your shell and run: just verify-setup"

# Force-deploy the full agentic layer unconditionally (clean re-install)
setup-force:
    #!/usr/bin/env bash
    set -euo pipefail
    # Note: when adding new symlink targets to any deploy-* recipe, also add them here.
    if [ "$(git rev-parse --git-dir)" != "$(git rev-parse --git-common-dir)" ]; then
        echo "Error: setup-force must run from the main repo, not a worktree." >&2
        echo "  Run from: $(git rev-parse --path-format=absolute --git-common-dir | sed 's|/\.git$||')" >&2
        exit 1
    fi
    # --- bin ---
    mkdir -p ~/.local/bin
    ln -sf "$(pwd)/bin/count-tokens" ~/.local/bin/count-tokens
    ln -sf "$(pwd)/bin/audit-doc" ~/.local/bin/audit-doc
    ln -sf "$(pwd)/backlog/update_item.py" ~/.local/bin/update-item
    ln -sf "$(pwd)/backlog/create_item.py" ~/.local/bin/create-backlog-item
    ln -sf "$(pwd)/backlog/generate_index.py" ~/.local/bin/generate-backlog-index
    ln -sf "$(pwd)/bin/jcc" ~/.local/bin/jcc
    ln -sf "$(pwd)/bin/overnight-start" ~/.local/bin/overnight-start
    # --- reference ---
    mkdir -p ~/.claude/reference
    ln -sf "$(pwd)/claude/reference/verification-mindset.md" ~/.claude/reference/verification-mindset.md
    ln -sf "$(pwd)/claude/reference/parallel-agents.md" ~/.claude/reference/parallel-agents.md
    ln -sf "$(pwd)/claude/reference/context-file-authoring.md" ~/.claude/reference/context-file-authoring.md
    ln -sf "$(pwd)/claude/reference/claude-skills.md" ~/.claude/reference/claude-skills.md
    # --- skills ---
    mkdir -p ~/.claude/skills
    for skill in skills/*/SKILL.md; do
        name=$(basename "$(dirname "$skill")")
        ln -sfn "$(pwd)/skills/$name" "$HOME/.claude/skills/$name"
    done
    # --- hooks ---
    mkdir -p ~/.claude/hooks
    for hook in hooks/*.sh; do
        [ -f "$hook" ] || continue
        name=$(basename "$hook")
        if [ "$name" = "cortex-notify.sh" ]; then
            ln -sf "$(pwd)/$hook" "$HOME/.claude/notify.sh"
        else
            ln -sf "$(pwd)/$hook" "$HOME/.claude/hooks/$name"
        fi
    done
    for hook in claude/hooks/*; do
        [ -f "$hook" ] || continue
        name=$(basename "$hook")
        ln -sf "$(pwd)/$hook" "$HOME/.claude/hooks/$name"
    done
    # --- config ---
    mkdir -p ~/.claude
    mkdir -p ~/.claude/rules
    ln -sf "$(pwd)/claude/settings.json" ~/.claude/settings.json
    ln -sf "$(pwd)/claude/statusline.sh" ~/.claude/statusline.sh
    ln -sf "$(pwd)/claude/rules/global-agent-rules.md" ~/.claude/rules/cortex-global.md
    ln -sf "$(pwd)/claude/rules/sandbox-behaviors.md" ~/.claude/rules/cortex-sandbox.md
    # --- settings.local.json ---
    LOCAL_SETTINGS="$HOME/.claude/settings.local.json"
    ALLOW_PATH="$(pwd)/lifecycle/sessions/"
    if [ -f "$LOCAL_SETTINGS" ]; then
        if command -v jq &>/dev/null; then
            jq --arg path "$ALLOW_PATH" '
                .sandbox.filesystem.allowWrite = (
                    (.sandbox.filesystem.allowWrite // []) + [$path] | unique
                )
            ' "$LOCAL_SETTINGS" > "$LOCAL_SETTINGS.tmp"
            mv "$LOCAL_SETTINGS.tmp" "$LOCAL_SETTINGS"
        else
            echo "Warning: jq not found — settings.local.json overwritten. Install jq to preserve allowWrite paths from other clones."
            printf '{\n  "sandbox": {\n    "filesystem": {\n      "allowWrite": ["%s"]\n    }\n  }\n}\n' "$ALLOW_PATH" > "$LOCAL_SETTINGS"
        fi
    else
        mkdir -p "$(dirname "$LOCAL_SETTINGS")"
        printf '{\n  "sandbox": {\n    "filesystem": {\n      "allowWrite": ["%s"]\n    }\n  }\n}\n' "$ALLOW_PATH" > "$LOCAL_SETTINGS"
    fi
    just python-setup

# Deploy bin/ utilities to ~/.local/bin/
# Refuses to run from a git worktree — symlinks must point to the real repo root.
deploy-bin:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "$(git rev-parse --git-dir)" != "$(git rev-parse --git-common-dir)" ]; then
        echo "Error: deploy-bin must run from the main repo, not a worktree." >&2
        echo "  Run from: $(git rev-parse --path-format=absolute --git-common-dir | sed 's|/\.git$||')" >&2
        exit 1
    fi
    mkdir -p ~/.local/bin
    ln -sf $(pwd)/bin/count-tokens ~/.local/bin/count-tokens
    ln -sf $(pwd)/bin/audit-doc ~/.local/bin/audit-doc
    ln -sf $(pwd)/backlog/update_item.py ~/.local/bin/update-item
    ln -sf $(pwd)/backlog/create_item.py ~/.local/bin/create-backlog-item
    ln -sf $(pwd)/backlog/generate_index.py ~/.local/bin/generate-backlog-index
    ln -sf $(pwd)/bin/jcc ~/.local/bin/jcc
    ln -sf $(pwd)/bin/overnight-start ~/.local/bin/overnight-start

# Deploy reference docs to ~/.claude/reference/ as symlinks
deploy-reference:
    mkdir -p ~/.claude/reference
    ln -sf $(pwd)/claude/reference/verification-mindset.md ~/.claude/reference/verification-mindset.md
    ln -sf $(pwd)/claude/reference/parallel-agents.md ~/.claude/reference/parallel-agents.md
    ln -sf $(pwd)/claude/reference/context-file-authoring.md ~/.claude/reference/context-file-authoring.md
    ln -sf $(pwd)/claude/reference/claude-skills.md ~/.claude/reference/claude-skills.md

# Deploy skills to ~/.claude/skills/ as symlinks
deploy-skills:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p ~/.claude/skills
    for skill in skills/*/SKILL.md; do
        name=$(basename "$(dirname "$skill")")
        ln -sfn "$(pwd)/skills/$name" "$HOME/.claude/skills/$name"
    done

# Deploy hooks to ~/.claude/hooks/ and ~/.claude/notify.sh as symlinks
deploy-hooks:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p ~/.claude/hooks
    # Shared hooks
    for hook in hooks/*.sh; do
        [ -f "$hook" ] || continue
        name=$(basename "$hook")
        if [ "$name" = "cortex-notify.sh" ]; then
            # notify.sh goes directly to ~/.claude/notify.sh (settings.json references this path)
            ln -sf "$(pwd)/$hook" "$HOME/.claude/notify.sh"
        else
            ln -sf "$(pwd)/$hook" "$HOME/.claude/hooks/$name"
        fi
    done
    # Claude-specific hooks
    for hook in claude/hooks/*; do
        [ -f "$hook" ] || continue
        name=$(basename "$hook")
        ln -sf "$(pwd)/$hook" "$HOME/.claude/hooks/$name"
    done

# Deploy config files (settings.json, statusline, and rules/)
deploy-config:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p ~/.claude
    mkdir -p ~/.claude/rules/
    # Warn if target exists as a regular file (not a symlink)
    for target in ~/.claude/settings.json ~/.claude/statusline.sh; do
        if [ -f "$target" ] && [ ! -L "$target" ]; then
            echo "Warning: $target exists as a regular file (not a symlink)."
            read -rp "  Overwrite with symlink? [y/N] " answer
            if [[ ! "$answer" =~ ^[Yy] ]]; then
                echo "  Skipping $target"
                continue
            fi
        fi
        case "$target" in
            *settings.json) ln -sf "$(pwd)/claude/settings.json" "$target" ;;
            *statusline.sh) ln -sf "$(pwd)/claude/statusline.sh" "$target" ;;
        esac
    done
    for target in ~/.claude/rules/cortex-global.md ~/.claude/rules/cortex-sandbox.md; do
        if [ -f "$target" ] && [ ! -L "$target" ]; then
            echo "Warning: $target exists as a regular file (not a symlink)."
            read -rp "  Overwrite with symlink? [y/N] " answer
            if [[ ! "$answer" =~ ^[Yy] ]]; then
                echo "  Skipping $target"
                continue
            fi
        fi
        case "$target" in
            *cortex-global.md)  ln -sf "$(pwd)/claude/rules/global-agent-rules.md" "$target" ;;
            *cortex-sandbox.md) ln -sf "$(pwd)/claude/rules/sandbox-behaviors.md" "$target" ;;
        esac
    done
    # Write settings.local.json with correct allowWrite path for this clone location
    LOCAL_SETTINGS="$HOME/.claude/settings.local.json"
    ALLOW_PATH="$(pwd)/lifecycle/sessions/"
    if [ -f "$LOCAL_SETTINGS" ] && command -v jq &>/dev/null; then
        # Merge into existing settings.local.json
        jq --arg path "$ALLOW_PATH" '.sandbox.filesystem.allowWrite = [$path]' "$LOCAL_SETTINGS" > "$LOCAL_SETTINGS.tmp"
        mv "$LOCAL_SETTINGS.tmp" "$LOCAL_SETTINGS"
    else
        # Create new settings.local.json
        mkdir -p "$(dirname "$LOCAL_SETTINGS")"
        printf '{\n  "sandbox": {\n    "filesystem": {\n      "allowWrite": ["%s"]\n    }\n  }\n}\n' "$ALLOW_PATH" > "$LOCAL_SETTINGS"
    fi

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

# --- GPG / PAT ---

# Configure gpg-agent extra socket for Claude Code sandbox signing
setup-gpg-sandbox:
    #!/usr/bin/env bash
    set -euo pipefail
    SIGNING_KEY=$(git config --global user.signingkey 2>/dev/null || true)
    if [ -z "$SIGNING_KEY" ]; then
        echo "user.signingkey is not set in git config."
        echo "Run: git config --global user.signingkey <your-key-id>"
        exit 1
    fi
    SOCKET_DIR="$HOME/.local/share/gnupg"
    AGENT_CONF="$HOME/.gnupg/gpg-agent.conf"
    EXTRA_LINE="extra-socket $HOME/.local/share/gnupg/S.gpg-agent.sandbox"
    if [ -d "$SOCKET_DIR" ]; then
        echo "Directory already exists: $SOCKET_DIR"
    else
        mkdir -p "$SOCKET_DIR"
        echo "Created directory: $SOCKET_DIR"
    fi
    if [ \! -f "$AGENT_CONF" ]; then
        echo "$EXTRA_LINE" > "$AGENT_CONF"
        echo "Created $AGENT_CONF with extra-socket line"
    elif grep -q "extra-socket" "$AGENT_CONF"; then
        echo "extra-socket already configured in $AGENT_CONF"
    else
        echo "$EXTRA_LINE" >> "$AGENT_CONF"
        echo "Appended extra-socket line to $AGENT_CONF"
    fi
    gpg --export "$SIGNING_KEY" > "$SOCKET_DIR/signing-key.pgp"
    chmod 0600 "$SOCKET_DIR/signing-key.pgp"
    KEYBYTES=$(wc -c < "$SOCKET_DIR/signing-key.pgp")
    if [ "$KEYBYTES" -eq 0 ]; then
        echo "Error: signing-key.pgp is empty — gpg --export produced no output."
        echo "Check that key $SIGNING_KEY exists in ~/.gnupg and is accessible."
        exit 1
    fi
    echo "Exported signing key to $SOCKET_DIR/signing-key.pgp ($KEYBYTES bytes)"
    echo ""
    echo "Run: gpgconf --kill gpg-agent"
    echo "The agent will auto-restart on next use with the new config."
    echo "signing-key.pgp contains the public key for sandbox GPG import."

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
    bash "{{justfile_directory()}}/claude/overnight/runner.sh" --state {{ state }} --time-limit {{ time-limit }} --max-rounds {{ max-rounds }} --tier {{ tier }}

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
        "bash \"{{justfile_directory()}}/claude/overnight/runner.sh\" $STATE_ARG --time-limit {{ time-limit }} --max-rounds {{ max-rounds }} --tier {{ tier }}"
    echo "Overnight runner started in tmux session '$SESSION'"
    echo "  Attach : tmux attach -t $SESSION"
    echo "  Watch  : tail -f lifecycle/sessions/latest-overnight/overnight-events.log"
    just overnight-status

# Show a live auto-refreshing status display for the active overnight session
overnight-status:
    #!/usr/bin/env bash
    trap 'exit 0' INT
    while true; do
        clear
        uv run python3 -m claude.overnight.status
        sleep 5
    done

# Run the overnight smoke test (verifies worker commit round-trip)
overnight-smoke-test:
    uv run python3 -m claude.overnight.smoke_test

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
    PID_FILE="claude/dashboard/.pid"
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "Dashboard already running (PID $PID). Open http://localhost:{{dashboard_port}}"
            exit 0
        fi
    fi
    echo "Dashboard running at http://0.0.0.0:{{dashboard_port}}"
    uv run uvicorn claude.dashboard.app:app --host 0.0.0.0 --port {{dashboard_port}}

# Write fixture files for visual dashboard testing (overnight state, events, features, backlog)
dashboard-seed:
    uv run python3 -m claude.dashboard.seed

# Remove all fixture files written by dashboard-seed
dashboard-seed-clean:
    uv run python3 -m claude.dashboard.seed --clean

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
    python3 skills/skill-creator/scripts/validate-skill.py skills/

# Validate preconditions for a specific skill
validate-skill-preconditions skill:
    python3 skills/skill-creator/scripts/validate-preconditions.py {{skill}}

# Check that all expected symlinks are intact
check-symlinks:
    #!/usr/bin/env bash
    set -euo pipefail
    errors=0
    check() {
        if [ -L "$1" ]; then
            printf '  ✓ %s\n' "$1"
        else
            printf '  ✗ %s (missing)\n' "$1"
            errors=$((errors + 1))
        fi
    }
    echo "Checking symlinks..."
    check ~/.claude/settings.json
    check ~/.claude/rules/cortex-global.md
    check ~/.claude/rules/cortex-sandbox.md
    check ~/.claude/statusline.sh
    check ~/.claude/notify.sh
    check ~/.claude/hooks/cortex-validate-commit.sh
    check ~/.claude/hooks/cortex-scan-lifecycle.sh
    check ~/.claude/hooks/cortex-setup-gpg-sandbox-home.sh
    check ~/.claude/hooks/cortex-sync-permissions.py
    check ~/.claude/hooks/cortex-tool-failure-tracker.sh
    check ~/.claude/hooks/cortex-skill-edit-advisor.sh
    check ~/.claude/hooks/cortex-permission-audit-log.sh
    check ~/.local/bin/count-tokens
    check ~/.local/bin/audit-doc
    check ~/.local/bin/update-item
    check ~/.local/bin/create-backlog-item
    check ~/.local/bin/generate-backlog-index
    check ~/.local/bin/jcc
    check ~/.local/bin/overnight-start
    for skill in skills/*/SKILL.md; do
        name=$(basename "$(dirname "$skill")")
        check ~/.claude/skills/"$name"
    done
    check ~/.claude/reference/verification-mindset.md
    check ~/.claude/reference/parallel-agents.md
    check ~/.claude/reference/context-file-authoring.md
    check ~/.claude/reference/claude-skills.md
    echo ""
    if [ "$errors" -eq 0 ]; then
        echo "All symlinks intact."
    else
        echo "$errors symlink(s) missing."
        exit 1
    fi

# Verify full setup health: symlinks, prerequisites, and environment
verify-setup:
    #!/usr/bin/env bash
    set -euo pipefail
    errors=0
    pass() { printf '  ✓ %s\n' "$1"; }
    fail() { printf '  ✗ %s — %s\n' "$1" "$2"; errors=$((errors + 1)); }
    echo "Checking symlinks..."
    just check-symlinks || errors=$((errors + 1))
    echo ""
    echo "Checking prerequisites..."
    # Python 3.12+
    if python3 -c "import sys; exit(0 if sys.version_info >= (3, 12) else 1)" 2>/dev/null; then
        pass "Python $(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    else
        fail "Python 3.12+" "install Python 3.12 or later"
    fi
    # uv
    if command -v uv &>/dev/null; then
        pass "uv"
    else
        fail "uv" "install with: brew install uv"
    fi
    # claude CLI
    if command -v claude &>/dev/null; then
        pass "claude CLI"
    else
        fail "claude CLI" "install from https://docs.anthropic.com/en/docs/claude-code"
    fi
    # CORTEX_COMMAND_ROOT
    if [ -z "${CORTEX_COMMAND_ROOT:-}" ]; then
        fail "CORTEX_COMMAND_ROOT" "add to shell profile: export CORTEX_COMMAND_ROOT=\"$(pwd)\""
    elif [ "$(cd "$CORTEX_COMMAND_ROOT" && pwd)" = "$(pwd)" ]; then
        pass "CORTEX_COMMAND_ROOT=$CORTEX_COMMAND_ROOT"
    else
        fail "CORTEX_COMMAND_ROOT" "set to $(pwd) (currently $CORTEX_COMMAND_ROOT)"
    fi
    echo ""
    if [ "$errors" -eq 0 ]; then
        echo "All checks passed."
    else
        echo "$errors check(s) failed."
        exit 1
    fi

# Verify setup including full test suite
verify-setup-full:
    just verify-setup
    just test

# --- Testing ---

# Run skill contract tests (validates SKILL.md frontmatter across all skills)
test-skill-contracts:
    #!/usr/bin/env bash
    set -euo pipefail
    python3 skills/skill-creator/scripts/validate-skill.py skills/
    uv run pytest tests/test_skill_contracts.py -q

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
    .venv/bin/pytest claude/pipeline/tests/ -q

# Run overnight runner tests (requires venv — run 'just python-setup' first)
test-overnight:
    #!/usr/bin/env bash
    set -euo pipefail
    [ -f .venv/bin/pytest ] || { echo "venv not found — run 'just python-setup' first"; exit 1; }
    .venv/bin/pytest claude/overnight/tests/ -q

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
    run_test "tests" uv run pytest tests/ -q
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
