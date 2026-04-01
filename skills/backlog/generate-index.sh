#!/usr/bin/env bash
# Generate backlog/index.md from active item frontmatter.
# Produces a summary table sorted by priority then ID, Refined and Backlog sections,
# and warnings for stale blocked-by references or self-referential cycles.
#
# Usage:
#   bash generate-index.sh [BACKLOG_DIR]
#
# BACKLOG_DIR defaults to $(pwd)/backlog when not provided.
# This allows the script to be called from any project root, even when
# installed as a shared utility at ~/.claude/skills/backlog/generate-index.sh.
set -euo pipefail

BACKLOG_DIR="${1:-$(pwd)/backlog}"

# --- Priority sort order ---
priority_rank() {
  case "$1" in
    critical) echo 1 ;;
    high)     echo 2 ;;
    medium)   echo 3 ;;
    low)      echo 4 ;;
    *)        echo 9 ;;
  esac
}

# --- ID set helpers (bash 3.2 compatible, no associative arrays) ---
# Sets are colon-delimited strings of numeric IDs, e.g. ":1:5:12:"
archive_id_set=":"
active_id_set=":"

id_in_set() {
  local id="$1" set="$2"
  [[ "$set" == *":${id}:"* ]]
}

# --- Build archive ID set ---
for file in "$BACKLOG_DIR"/archive/[0-9]*-*.md; do
  [[ -f "$file" ]] || continue
  basename_file="$(basename "$file")"
  aid="${basename_file%%-*}"
  aid_num=$((10#$aid))
  archive_id_set="${archive_id_set}${aid_num}:"
done

# --- Collect active items ---
# Parallel arrays indexed by position.
ids=()
titles=()
statuses=()
priorities=()
types=()
blocked_bys=()

for file in "$BACKLOG_DIR"/[0-9]*-*.md; do
  [[ -f "$file" ]] || continue

  basename_file="$(basename "$file")"
  id="${basename_file%%-*}"

  # Extract frontmatter block (between --- delimiters)
  frontmatter=$(sed -n '/^---$/,/^---$/p' "$file")

  title=$(echo "$frontmatter" | sed -n 's/^title: *//p')
  status=$(echo "$frontmatter" | sed -n 's/^status: *//p')
  priority=$(echo "$frontmatter" | sed -n 's/^priority: *//p')
  type=$(echo "$frontmatter" | sed -n 's/^type: *//p')
  blocked_by=$(echo "$frontmatter" | sed -n 's/^blocked-by: \[\(.*\)\]/\1/p')

  # Skip terminal statuses — complete/abandoned items should be archived, not indexed
  # Recognizes both legacy (done, closed, resolved, wontfix) and canonical (complete, abandoned) values
  case "$status" in
    done|closed|resolved|wontfix|complete|abandoned) continue ;;
  esac

  ids+=("$id")
  titles+=("$title")
  statuses+=("$status")
  priorities+=("$priority")
  types+=("$type")
  blocked_bys+=("$blocked_by")

  id_num=$((10#$id))
  active_id_set="${active_id_set}${id_num}:"
done

# --- Sort by priority rank then ID ---
# Build sortable lines: "rank:id:index" then sort numerically.
sort_lines=""
for i in "${!ids[@]}"; do
  rank=$(priority_rank "${priorities[$i]}")
  sort_lines+="${rank}:${ids[$i]}:${i}"$'\n'
done

sorted_indices=()
if [[ -n "$sort_lines" ]]; then
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    idx="${line##*:}"
    sorted_indices+=("$idx")
  done < <(echo "$sort_lines" | sort -t: -k1,1n -k2,2n)
fi

# --- Generate index.md ---
output="# Backlog Index"$'\n'
output+=$'\n'
output+="| ID | Title | Status | Priority | Type | Blocked By |"$'\n'
output+="|-----|-------|--------|----------|------|------------|"$'\n'

if (( ${#sorted_indices[@]} > 0 )); then
  for i in "${sorted_indices[@]}"; do
    blocked_display="${blocked_bys[$i]}"
    if [[ -z "$blocked_display" ]]; then
      blocked_display="—"
    fi
    output+="| ${ids[$i]} | ${titles[$i]} | ${statuses[$i]} | ${priorities[$i]} | ${types[$i]} | ${blocked_display} |"$'\n'
  done
fi

# --- Refined section: status=refined (or legacy ready) with no unresolved blocked-by ---
output+=$'\n'
output+="## Refined"$'\n'
output+=$'\n'

if (( ${#sorted_indices[@]} > 0 )); then
  for i in "${sorted_indices[@]}"; do
    case "${statuses[$i]}" in
      refined|ready) ;;
      *) continue ;;
    esac

    if [[ -z "${blocked_bys[$i]}" ]]; then
      output+="- **${ids[$i]}** ${titles[$i]}"$'\n'
    else
      # Check if all blockers are resolved (not active)
      all_resolved=true
      IFS=', ' read -ra blockers <<< "${blocked_bys[$i]}"
      for b in "${blockers[@]}"; do
        b=$(echo "$b" | tr -d ' ')
        [[ -n "$b" ]] || continue
        b_num=$((10#$b))
        if id_in_set "$b_num" "$active_id_set"; then
          all_resolved=false
          break
        fi
      done
      if $all_resolved; then
        output+="- **${ids[$i]}** ${titles[$i]}"$'\n'
      fi
    fi
  done
fi

# --- Backlog section: status=backlog (or legacy open/blocked) with no unresolved blocked-by ---
output+=$'\n'
output+="## Backlog"$'\n'
output+=$'\n'

if (( ${#sorted_indices[@]} > 0 )); then
  for i in "${sorted_indices[@]}"; do
    case "${statuses[$i]}" in
      backlog|open|blocked) ;;
      *) continue ;;
    esac

    if [[ -z "${blocked_bys[$i]}" ]]; then
      output+="- **${ids[$i]}** ${titles[$i]}"$'\n'
    else
      # Check if all blockers are resolved (not active)
      all_resolved=true
      IFS=', ' read -ra blockers <<< "${blocked_bys[$i]}"
      for b in "${blockers[@]}"; do
        b=$(echo "$b" | tr -d ' ')
        [[ -n "$b" ]] || continue
        b_num=$((10#$b))
        if id_in_set "$b_num" "$active_id_set"; then
          all_resolved=false
          break
        fi
      done
      if $all_resolved; then
        output+="- **${ids[$i]}** ${titles[$i]}"$'\n'
      fi
    fi
  done
fi

# --- In-Progress section: status=in_progress, implementing, review (or legacy in-progress) ---
output+=$'\n'
output+="## In-Progress"$'\n'
output+=$'\n'

if (( ${#sorted_indices[@]} > 0 )); then
  for i in "${sorted_indices[@]}"; do
    case "${statuses[$i]}" in
      in_progress|implementing|review|in-progress)
        output+="- **${ids[$i]}** ${titles[$i]} (${statuses[$i]})"$'\n'
        ;;
    esac
  done
fi

# --- Warnings section ---
warnings=""

if (( ${#ids[@]} > 0 )); then
  for i in "${!ids[@]}"; do
    [[ -n "${blocked_bys[$i]}" ]] || continue

    id_num=$((10#${ids[$i]}))
    IFS=', ' read -ra blockers <<< "${blocked_bys[$i]}"
    for b in "${blockers[@]}"; do
      b=$(echo "$b" | tr -d ' ')
      [[ -n "$b" ]] || continue
      b_num=$((10#$b))

      # Self-referential cycle guard
      if (( b_num == id_num )); then
        warnings+="- **${ids[$i]}**: self-referential blocked-by (references own ID)"$'\n'
        continue
      fi

      # Stale reference: blocker exists only in archive
      if id_in_set "$b_num" "$archive_id_set" && ! id_in_set "$b_num" "$active_id_set"; then
        warnings+="- **${ids[$i]}**: blocked-by $b references archived item"$'\n'
      fi
    done
  done
fi

if [[ -n "$warnings" ]]; then
  output+=$'\n'
  output+="## Warnings"$'\n'
  output+=$'\n'
  output+="$warnings"
fi

printf '%s' "$output" > "$BACKLOG_DIR/index.md"
