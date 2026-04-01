#!/bin/bash
# Hook: scan lifecycle directories and inject state awareness (SessionStart).
set -euo pipefail

INPUT=$(cat)

# --- Session identity injection ---
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""')
if [[ -n "$SESSION_ID" && -n "${CLAUDE_ENV_FILE:-}" ]]; then
  echo "export LIFECYCLE_SESSION_ID=$SESSION_ID" >> "$CLAUDE_ENV_FILE"
elif [[ -n "$SESSION_ID" ]]; then
  echo "[scan-lifecycle] CLAUDE_ENV_FILE not set; cannot inject LIFECYCLE_SESSION_ID" >&2
fi

CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
[[ -n "$CWD" ]] || CWD="$(pwd)"

LIFECYCLE_DIR="$CWD/lifecycle"

# No lifecycle directory — nothing to inject
[[ -d "$LIFECYCLE_DIR" ]] || exit 0

# --- Session migration (survives /clear) ---
# When SESSION_ID (fresh, from JSON) differs from LIFECYCLE_SESSION_ID (stale, from env),
# both being non-empty means this is a /clear, not a fresh session. Migrate .session files
# so the active feature is still matched after /clear.

LIFECYCLE_SESSION_ID="${LIFECYCLE_SESSION_ID:-}"

if [[ -n "$SESSION_ID" && -n "$LIFECYCLE_SESSION_ID" && "$SESSION_ID" != "$LIFECYCLE_SESSION_ID" ]]; then
  migration_done=false

  # Phase 1: scan .session files for the stale ID (first /clear)
  for session_file in "$LIFECYCLE_DIR"/*/.session; do
    [[ -f "$session_file" ]] || continue
    file_id=$(cat "$session_file" 2>/dev/null | tr -d '[:space:]') || continue
    if [[ "$file_id" == "$LIFECYCLE_SESSION_ID" ]]; then
      feature_dir=$(dirname "$session_file")
      echo "$SESSION_ID" > "$session_file"
      echo "$LIFECYCLE_SESSION_ID" > "$feature_dir/.session-owner"
      migration_done=true
    fi
  done

  # Phase 2: chain migration via .session-owner (subsequent /clear)
  if [[ "$migration_done" == false ]]; then
    for owner_file in "$LIFECYCLE_DIR"/*/.session-owner; do
      [[ -f "$owner_file" ]] || continue
      owner_id=$(cat "$owner_file" 2>/dev/null | tr -d '[:space:]') || continue
      if [[ "$owner_id" == "$LIFECYCLE_SESSION_ID" ]]; then
        feature_dir=$(dirname "$owner_file")
        echo "$SESSION_ID" > "$feature_dir/.session"
        # .session-owner stays unchanged — it holds the original stale ID
      fi
    done
  fi
fi

# --- Fresh resume detection ---
# If lifecycle/.fresh-resume exists (written by /fresh skill before /clear),
# read the full handoff prompt and inject it directly. Delete after first read.
fresh_resume_prompt=""
fresh_resume_file="$LIFECYCLE_DIR/.fresh-resume"
if [[ -f "$fresh_resume_file" ]]; then
  fresh_resume_prompt=$(cat "$fresh_resume_file" 2>/dev/null)
  rm -f "$fresh_resume_file"
fi

# --- Pipeline state detection ---
# If an overnight-state.json exists and is non-complete, build a summary line.
# If phase == "complete" and Morning Review is not dismissed, suppress batch features
# from the incomplete list and inject a Morning Review note instead.

pipeline_context=""
morning_review_active=false
morning_review_count=0
morning_review_feature_set=()
PIPELINE_STATE="$LIFECYCLE_DIR/overnight-state.json"

if [[ -f "$PIPELINE_STATE" ]]; then
  pipeline_phase=""

  # Try jq first, fall back to grep/sed
  if command -v jq &>/dev/null; then
    pipeline_phase=$(jq -r '.phase // empty' "$PIPELINE_STATE" 2>/dev/null) || pipeline_phase=""
  fi

  if [[ -z "$pipeline_phase" ]]; then
    # grep fallback: extract "phase": "value"
    pipeline_phase=$(sed -n 's/.*"phase"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$PIPELINE_STATE" 2>/dev/null | head -1)
  fi

  if [[ "$pipeline_phase" == "complete" ]]; then
    # Collect merged feature names
    merged_features=()
    if command -v jq &>/dev/null; then
      while IFS= read -r fname; do
        [[ -n "$fname" ]] && merged_features+=("$fname")
      done < <(jq -r '.features | to_entries[] | select(.value.status == "merged") | .key' "$PIPELINE_STATE" 2>/dev/null)
    fi

    # Dismissal check: all merged features have feature_complete in their events.log
    dismissed=true
    if (( ${#merged_features[@]} == 0 )); then
      dismissed=true
    else
      for fname in "${merged_features[@]}"; do
        events_log="$LIFECYCLE_DIR/$fname/events.log"
        if ! grep -q '"feature_complete"' "$events_log" 2>/dev/null; then
          dismissed=false
          break
        fi
      done
    fi

    if [[ "$dismissed" == false ]]; then
      morning_review_active=true
      morning_review_count=${#merged_features[@]}
      morning_review_feature_set=("${merged_features[@]}")
      pipeline_context="☀️ Morning Review pending: $morning_review_count features"
    fi
  elif [[ -n "$pipeline_phase" ]]; then
    # Count features by status
    total=0 count_merged=0 count_executing=0 count_paused=0
    count_pending=0 count_reviewing=0 count_merging=0 count_failed=0

    if command -v jq &>/dev/null; then
      total=$(jq '[.features | to_entries[]] | length' "$PIPELINE_STATE" 2>/dev/null) || total=0
      count_merged=$(jq '[.features | to_entries[] | select(.value.status == "merged")] | length' "$PIPELINE_STATE" 2>/dev/null) || count_merged=0
      count_executing=$(jq '[.features | to_entries[] | select(.value.status == "executing")] | length' "$PIPELINE_STATE" 2>/dev/null) || count_executing=0
      count_paused=$(jq '[.features | to_entries[] | select(.value.status == "paused")] | length' "$PIPELINE_STATE" 2>/dev/null) || count_paused=0
      count_pending=$(jq '[.features | to_entries[] | select(.value.status == "pending")] | length' "$PIPELINE_STATE" 2>/dev/null) || count_pending=0
      count_reviewing=$(jq '[.features | to_entries[] | select(.value.status == "reviewing")] | length' "$PIPELINE_STATE" 2>/dev/null) || count_reviewing=0
      count_merging=$(jq '[.features | to_entries[] | select(.value.status == "merging")] | length' "$PIPELINE_STATE" 2>/dev/null) || count_merging=0
      count_failed=$(jq '[.features | to_entries[] | select(.value.status == "failed")] | length' "$PIPELINE_STATE" 2>/dev/null) || count_failed=0
    else
      # grep/sed fallback: count "status": "value" lines within features block
      total=$(grep -c '"status"' "$PIPELINE_STATE" 2>/dev/null) || total=0
      count_merged=$(grep -c '"status"[[:space:]]*:[[:space:]]*"merged"' "$PIPELINE_STATE" 2>/dev/null) || count_merged=0
      count_executing=$(grep -c '"status"[[:space:]]*:[[:space:]]*"executing"' "$PIPELINE_STATE" 2>/dev/null) || count_executing=0
      count_paused=$(grep -c '"status"[[:space:]]*:[[:space:]]*"paused"' "$PIPELINE_STATE" 2>/dev/null) || count_paused=0
      count_pending=$(grep -c '"status"[[:space:]]*:[[:space:]]*"pending"' "$PIPELINE_STATE" 2>/dev/null) || count_pending=0
      count_reviewing=$(grep -c '"status"[[:space:]]*:[[:space:]]*"reviewing"' "$PIPELINE_STATE" 2>/dev/null) || count_reviewing=0
      count_merging=$(grep -c '"status"[[:space:]]*:[[:space:]]*"merging"' "$PIPELINE_STATE" 2>/dev/null) || count_merging=0
      count_failed=$(grep -c '"status"[[:space:]]*:[[:space:]]*"failed"' "$PIPELINE_STATE" 2>/dev/null) || count_failed=0
    fi

    # Build the detail segments (only include non-zero counts)
    details=""
    for pair in "merged:$count_merged" "executing:$count_executing" "reviewing:$count_reviewing" \
                "merging:$count_merging" "paused:$count_paused" "pending:$count_pending" "failed:$count_failed"; do
      label="${pair%%:*}"
      count="${pair#*:}"
      if (( count > 0 )); then
        if [[ -n "$details" ]]; then
          details="$details, $count $label"
        else
          details="$count $label"
        fi
      fi
    done

    pipeline_context="Active pipeline: $pipeline_phase | Features: $total total, $details"
  fi
fi

# --- Phase detection ---
# Mirrors claude.common.detect_lifecycle_phase — keep in sync if phase model changes

determine_phase() {
  local dir="$1"

  # Event-based completion check — covers all tiers (including simple which skips review)
  if [[ -f "$dir/events.log" ]] && grep -q '"feature_complete"' "$dir/events.log" 2>/dev/null; then
    echo "complete"; return
  fi

  if [[ -f "$dir/review.md" ]]; then
    local verdict cycle
    verdict=$(sed -n 's/.*"verdict"[[:space:]]*:[[:space:]]*"\([A-Z_]*\)".*/\1/p' "$dir/review.md" 2>/dev/null | tail -1)
    cycle=$(sed -n 's/.*"cycle"[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/p' "$dir/review.md" 2>/dev/null | tail -1)
    [[ -n "$cycle" ]] || cycle=1

    case "$verdict" in
      APPROVED)          echo "complete"; return ;;
      CHANGES_REQUESTED) echo "implement-rework:$cycle"; return ;;
      REJECTED)          echo "escalated"; return ;;
    esac
  fi

  if [[ -f "$dir/plan.md" ]]; then
    local total checked
    total=$(grep -cE '\*\*Status\*\*:.*\[[ x]\]' "$dir/plan.md" 2>/dev/null) || total=0
    checked=$(grep -cE '\*\*Status\*\*:.*\[x\]' "$dir/plan.md" 2>/dev/null) || checked=0

    if (( total > 0 && checked == total )); then
      echo "review"
    else
      echo "implement:$checked/$total"
    fi
    return
  fi

  if [[ -f "$dir/spec.md" ]]; then echo "plan"; return; fi
  if [[ -f "$dir/research.md" ]]; then echo "specify"; return; fi
  echo "research"
}

# Human-readable phase label for context output
phase_label() {
  local phase="$1"
  case "$phase" in
    research)           echo "Research" ;;
    specify)            echo "Specify" ;;
    plan)               echo "Plan" ;;
    implement:*)        echo "Implement (${phase#implement:} tasks done)" ;;
    implement-rework:*) echo "Implement — rework (review cycle ${phase#implement-rework:})" ;;
    review)             echo "Review" ;;
    escalated)          echo "Escalated (REJECTED — needs user direction)" ;;
    complete)           echo "Complete" ;;
    *)                  echo "$phase" ;;
  esac
}

# --- Scan feature directories ---

incomplete_features=()
incomplete_phases=()

for dir in "$LIFECYCLE_DIR"/*/; do
  [[ -d "$dir" ]] || continue
  feature=$(basename "$dir")
  [[ "$feature" == "archive" ]] && continue

  # Suppress batch features from Morning Review (when review is active/not dismissed)
  if [[ "$morning_review_active" == true ]]; then
    skip=false
    for batch_feat in "${morning_review_feature_set[@]}"; do
      if [[ "$feature" == "$batch_feat" ]]; then
        skip=true
        break
      fi
    done
    [[ "$skip" == true ]] && continue
  fi

  phase=$(determine_phase "$dir")

  [[ "$phase" != "complete" ]] || continue

  incomplete_features+=("$feature")
  incomplete_phases+=("$phase")
done

# No incomplete features and no pipeline context — nothing to inject
if (( ${#incomplete_features[@]} == 0 )) && [[ -z "$pipeline_context" ]]; then
  exit 0
fi

# --- Determine active feature ---

active_feature=""
active_phase=""
active_idx=-1
session_matched=false

# Match session_id against lifecycle/{feature}/.session files
if [[ -n "$SESSION_ID" ]]; then
  for i in "${!incomplete_features[@]}"; do
    session_file="$LIFECYCLE_DIR/${incomplete_features[$i]}/.session"
    if [[ -f "$session_file" ]]; then
      file_session_id=$(cat "$session_file" 2>/dev/null | tr -d '[:space:]')
      if [[ "$file_session_id" == "$SESSION_ID" ]]; then
        active_feature="${incomplete_features[$i]}"
        active_phase="${incomplete_phases[$i]}"
        active_idx=$i
        session_matched=true
        break
      fi
    fi
  done
fi

# Single incomplete feature — auto-select
if [[ -z "$active_feature" ]] && (( ${#incomplete_features[@]} == 1 )); then
  active_feature="${incomplete_features[0]}"
  active_phase="${incomplete_phases[0]}"
  active_idx=0
  # Crash-recovery: claim the orphaned feature for this new session
  if [[ -n "$SESSION_ID" ]]; then
    echo "$SESSION_ID" > "$LIFECYCLE_DIR/$active_feature/.session"
  fi
fi

# --- Build context message ---

# Fresh resume: /fresh was invoked before /clear. Inject the full handoff prompt
# at the top of context so the agent immediately knows how to continue.
context=""
if [[ -n "$fresh_resume_prompt" ]]; then
  context="$fresh_resume_prompt
"
fi

if [[ -n "$active_feature" ]]; then
  label=$(phase_label "$active_phase")

  # /clear recovery (no fresh-resume): session_id matched a .session file.
  if [[ -z "$fresh_resume_prompt" && "$session_matched" == true ]]; then
    context="This session was working on $active_feature ($label). Resume with \`/lifecycle $active_feature\`.
"
  fi

  context="${context}Active lifecycle: $active_feature | Phase: $label
Artifacts: lifecycle/$active_feature/"

  # Interrupted state hints
  case "$active_phase" in
    implement:*)
      progress="${active_phase#implement:}"
      checked="${progress%/*}"
      total="${progress#*/}"
      if (( checked > 0 && checked < total )); then
        context="$context
Interrupted: implementation in progress ($checked of $total tasks done). Resume with /lifecycle $active_feature."
      fi
      ;;
    implement-rework:*)
      cycle="${active_phase#implement-rework:}"
      context="$context
Interrupted: review cycle $cycle returned CHANGES_REQUESTED. Re-enter implementation to address feedback. Resume with /lifecycle $active_feature."
      ;;
    escalated)
      context="$context
Action needed: review returned REJECTED. See lifecycle/$active_feature/review.md for analysis."
      ;;
  esac

  # Note other incomplete features if any
  if (( ${#incomplete_features[@]} > 1 )); then
    context="$context
Other incomplete lifecycles:"
    for i in "${!incomplete_features[@]}"; do
      (( i != active_idx )) || continue
      label=$(phase_label "${incomplete_phases[$i]}")
      context="$context
  - ${incomplete_features[$i]} ($label)"
    done
    context="$context
Switch with /lifecycle resume <feature>."
  fi

elif (( ${#incomplete_features[@]} > 1 )); then
  # Multiple incomplete, no session match
  context="Multiple incomplete lifecycles — select one to resume:"
  for i in "${!incomplete_features[@]}"; do
    label=$(phase_label "${incomplete_phases[$i]}")
    context="$context
  - ${incomplete_features[$i]} ($label)"
  done
  context="$context
Resume with /lifecycle resume <feature>."
fi

# --- Prepend pipeline context if present ---

if [[ -n "$pipeline_context" ]]; then
  if [[ -n "$context" ]]; then
    context="$pipeline_context
$context"
  else
    context="$pipeline_context"
  fi
fi

# --- Regenerate and inject metrics summary ---

if [[ -n "$active_feature" ]] && command -v python3 &>/dev/null; then
  python3 -m claude.pipeline.metrics --root "$CWD" >/dev/null 2>&1 || true

  METRICS_FILE="$LIFECYCLE_DIR/metrics.json"
  if [[ -f "$METRICS_FILE" ]]; then
    metrics_summary=""

    # Extract values with jq, fall back to sed
    if command -v jq &>/dev/null; then
      m_completed=$(jq -r '.features | length' "$METRICS_FILE" 2>/dev/null) || m_completed=""
      m_simple_tasks=$(jq -r '.aggregates.simple.avg_task_count // 0' "$METRICS_FILE" 2>/dev/null) || m_simple_tasks=""
      m_simple_rework=$(jq -r '.aggregates.simple.avg_rework_cycles // 0' "$METRICS_FILE" 2>/dev/null) || m_simple_rework=""
      m_complex_tasks=$(jq -r '.aggregates.complex.avg_task_count // 0' "$METRICS_FILE" 2>/dev/null) || m_complex_tasks=""
      m_complex_rework=$(jq -r '.aggregates.complex.avg_rework_cycles // 0' "$METRICS_FILE" 2>/dev/null) || m_complex_rework=""
    fi

    if [[ -z "$m_completed" ]]; then
      m_completed=$(sed -n 's/.*"avg_task_count"[[:space:]]*:[[:space:]]*\([0-9.]*\).*/found/p' "$METRICS_FILE" 2>/dev/null | wc -l | tr -d ' ')
      m_simple_tasks=$(sed -n '/"simple"/,/}/s/.*"avg_task_count"[[:space:]]*:[[:space:]]*\([0-9.]*\).*/\1/p' "$METRICS_FILE" 2>/dev/null | head -1)
      m_simple_rework=$(sed -n '/"simple"/,/}/s/.*"avg_rework_cycles"[[:space:]]*:[[:space:]]*\([0-9.]*\).*/\1/p' "$METRICS_FILE" 2>/dev/null | head -1)
      m_complex_tasks=$(sed -n '/"complex"/,/}/s/.*"avg_task_count"[[:space:]]*:[[:space:]]*\([0-9.]*\).*/\1/p' "$METRICS_FILE" 2>/dev/null | head -1)
      m_complex_rework=$(sed -n '/"complex"/,/}/s/.*"avg_rework_cycles"[[:space:]]*:[[:space:]]*\([0-9.]*\).*/\1/p' "$METRICS_FILE" 2>/dev/null | head -1)
    fi

    : "${m_completed:=0}"
    : "${m_simple_tasks:=0}"
    : "${m_simple_rework:=0}"
    : "${m_complex_tasks:=0}"
    : "${m_complex_rework:=0}"

    metrics_summary="Metrics: $m_completed completed features | Simple: avg $m_simple_tasks tasks, $m_simple_rework rework | Complex: avg $m_complex_tasks tasks, $m_complex_rework rework"

    if [[ -n "$context" ]]; then
      context="$context
$metrics_summary"
    else
      context="$metrics_summary"
    fi
  fi
fi

# --- Output (agent-specific format) ---

if [[ -n "$context" ]]; then
  if [[ "$AGENT" == "claude" ]]; then
    jq -n --arg ctx "$context" '{
      hookSpecificOutput: {
        hookEventName: "SessionStart",
        additionalContext: $ctx
      }
    }'
  else
    jq -n --arg ctx "$context" '{
      additional_context: $ctx
    }'
  fi
fi

exit 0
