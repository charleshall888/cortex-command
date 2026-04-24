#!/usr/bin/env bash
# git-sync-rebase.sh — post-merge sync: fetch, rebase with allowlist conflict resolution, push.
#
# Usage: git-sync-rebase.sh [allowlist-file]
#   allowlist-file  Path to file with glob patterns for auto-resolve (default: cortex_command/overnight/sync-allowlist.conf)
#
# Exit codes:
#   0 — success (rebase + push completed, or nothing to rebase)
#   1 — conflict (rebase aborted, user must resolve manually)
#   2 — push failed (rebase succeeded but push to origin/main failed)

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ALLOWLIST_FILE="${1:-$REPO_ROOT/cortex_command/overnight/sync-allowlist.conf}"

# Maximum number of rebase --continue passes before giving up
MAX_PASSES=10
# Maximum non-allowlist conflicts before aborting
MAX_NON_ALLOWLIST=3

log() {
    echo "[git-sync-rebase] $*" >&2
}

# ---------------------------------------------------------------------------
# Load allowlist patterns
# ---------------------------------------------------------------------------

ALLOWLIST_PATTERNS=()

load_allowlist() {
    if [[ ! -f "$ALLOWLIST_FILE" ]]; then
        log "Warning: allowlist file not found: $ALLOWLIST_FILE"
        return
    fi

    while IFS= read -r line || [[ -n "$line" ]]; do
        # Skip comments and blank lines
        line="${line%%#*}"          # strip inline comments
        line="${line#"${line%%[![:space:]]*}"}"  # trim leading whitespace
        line="${line%"${line##*[![:space:]]}"}"  # trim trailing whitespace
        [[ -z "$line" ]] && continue
        ALLOWLIST_PATTERNS+=("$line")
    done < "$ALLOWLIST_FILE"

    log "Loaded ${#ALLOWLIST_PATTERNS[@]} allowlist patterns from $ALLOWLIST_FILE"
}

# ---------------------------------------------------------------------------
# Glob matching — bash fnmatch-style
# ---------------------------------------------------------------------------

matches_allowlist() {
    local filepath="$1"
    local pattern
    for pattern in "${ALLOWLIST_PATTERNS[@]}"; do
        # Handle directory patterns (trailing /)
        if [[ "$pattern" == */ ]]; then
            # Match any file under that directory prefix
            if [[ "$filepath" == ${pattern}* ]]; then
                return 0
            fi
        else
            # shellcheck disable=SC2254
            case "$filepath" in
                $pattern) return 0 ;;
            esac
        fi
    done
    return 1
}

# ---------------------------------------------------------------------------
# Step 1: Dirty rebase guard
# ---------------------------------------------------------------------------

if [[ -d "$REPO_ROOT/.git/rebase-merge" ]] || [[ -d "$REPO_ROOT/.git/rebase-apply" ]]; then
    log "Warning: stale rebase in progress detected — aborting it"
    git rebase --abort 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# Step 2: Fetch
# ---------------------------------------------------------------------------

log "Fetching origin..."
git fetch origin

# ---------------------------------------------------------------------------
# Step 3: Check if rebase is needed
# ---------------------------------------------------------------------------

BEHIND_COUNT=$(git rev-list HEAD..origin/main --count 2>/dev/null || echo "0")

if [[ "$BEHIND_COUNT" -eq 0 ]]; then
    log "Already up to date with origin/main — nothing to rebase"
    exit 0
fi

log "$BEHIND_COUNT commit(s) behind origin/main — starting rebase"

# ---------------------------------------------------------------------------
# Step 4: Attempt rebase
# ---------------------------------------------------------------------------

# Start the rebase; if no conflicts, this completes immediately
if git pull --rebase origin main 2>/dev/null; then
    log "Rebase completed cleanly"
else
    # ---------------------------------------------------------------------------
    # Step 5: Multi-pass conflict resolution loop
    # ---------------------------------------------------------------------------

    load_allowlist

    pass=0
    while [[ $pass -lt $MAX_PASSES ]]; do
        pass=$((pass + 1))
        log "Conflict resolution pass $pass/$MAX_PASSES"

        # Identify conflicted files
        mapfile -t conflicted < <(git diff --name-only --diff-filter=U 2>/dev/null)

        if [[ ${#conflicted[@]} -eq 0 ]]; then
            log "No conflicted files remain — continuing rebase"
            if GIT_EDITOR=true git rebase --continue 2>/dev/null; then
                log "Rebase completed after $pass pass(es)"
                break
            fi
            # rebase --continue may surface new conflicts in the next commit
            continue
        fi

        log "${#conflicted[@]} conflicted file(s) found"

        resolved=0
        non_allowlist=0
        non_allowlist_files=()

        for filepath in "${conflicted[@]}"; do
            if matches_allowlist "$filepath"; then
                log "  Auto-resolving (theirs): $filepath"
                git checkout --theirs -- "$filepath"
                git add -- "$filepath"
                resolved=$((resolved + 1))
            else
                log "  Non-allowlist conflict: $filepath"
                non_allowlist=$((non_allowlist + 1))
                non_allowlist_files+=("$filepath")
            fi
        done

        log "Resolved $resolved file(s), $non_allowlist non-allowlist conflict(s) remain"

        # Too many non-allowlist conflicts — abort
        if [[ $non_allowlist -gt $MAX_NON_ALLOWLIST ]]; then
            log "Error: $non_allowlist non-allowlist conflicts exceed threshold ($MAX_NON_ALLOWLIST) — aborting rebase"
            for f in "${non_allowlist_files[@]}"; do
                log "  Unresolved: $f"
            done
            git rebase --abort
            exit 1
        fi

        # If there are unresolved non-allowlist conflicts, abort
        if [[ $non_allowlist -gt 0 ]]; then
            log "Error: $non_allowlist non-allowlist conflict(s) cannot be auto-resolved — aborting rebase"
            for f in "${non_allowlist_files[@]}"; do
                log "  Unresolved: $f"
            done
            git rebase --abort
            exit 1
        fi

        # All conflicts resolved this pass — continue rebase
        if GIT_EDITOR=true git rebase --continue 2>/dev/null; then
            log "Rebase completed after $pass pass(es)"
            break
        fi
        # If rebase --continue didn't finish, there are more commits with conflicts — loop again
    done

    # Check if we exhausted passes
    if [[ $pass -ge $MAX_PASSES ]]; then
        log "Error: exceeded maximum resolution passes ($MAX_PASSES) — aborting rebase"
        git rebase --abort 2>/dev/null || true
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# Step 6: Push
# ---------------------------------------------------------------------------

log "Pushing to origin/main..."
if git push origin main; then
    log "Push succeeded"
    exit 0
else
    log "Error: push failed (rebase succeeded — local state is rebased)"
    exit 2
fi
