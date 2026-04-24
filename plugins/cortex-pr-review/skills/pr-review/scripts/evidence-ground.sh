#!/usr/bin/env bash
# evidence-ground.sh
#
# Evidence-grounding pre-step for the multi-agent PR review pipeline.
# Runs between Stage 3 (four critic subagents) and Stage 4 (Opus synthesizer).
#
# Consumes: stdin JSON of the shape
#   {
#     "critics": {
#       "agent1": {"findings": [...]},
#       "agent2": {"findings": [...]},
#       "agent3": {"findings": [...]},
#       "agent4": {"findings": [...]}
#     },
#     "diff_path": "<absolute path to unified diff file>"
#   }
#
# Emits (stdout JSON only - stderr is reserved for diagnostics and will be
# discarded by the caller):
#   {
#     "grounded": {
#       "agent1": {"findings": [<findings that passed grounding>]},
#       "agent2": {"findings": [...]},
#       "agent3": {"findings": [...]},
#       "agent4": {"findings": [...]}
#     },
#     "drops": [
#       {"finding": {...}, "reason": "evidence-not-found"
#                                   | "evidence-context-mismatch"
#                                   | "critic-malformed-json",
#        "critic": "agentN"},
#       ...
#     ],
#     "failed_critics": ["agentN", ...]
#   }
#
# Exit codes:
#   0  - success (including zero grounded findings; that is a normal outcome)
#   1  - unrecoverable error (e.g. diff_path unreadable, missing jq/python3,
#        internal parser error)
#
# Timeout: self-terminates after ~120 seconds. The caller sets a 150s safety
# net on the Bash tool invocation.
#
# Environment requirements (guaranteed by Stage 0 preflight):
#   bash, awk (BSD awk acceptable), grep, sed, jq, python3
#
# Matching algorithm (per finding):
#   0. Per-critic validation: if critic root JSON is malformed or findings[]
#      is missing/non-array, add critic to failed_critics and skip its
#      findings.
#   1. If label_hint is "question" or "cross-cutting" AND quoted_text is
#      null AND rationale is non-null -> pass-through with matched_side=null.
#   2. Else normalize quoted_text (strip leading [+- ], CRLF->LF, whitespace
#      collapse, NFC via python3).
#   3. Normalize evidence.path to POSIX forward slashes. quoted_text is NEVER
#      slash-normalized.
#   4. Extract + / - / ' ' (context) lines from the diff hunk at evidence.path
#      within the bounds of evidence.line_range (post-image line numbers).
#   5. Multi-line quoted_text must match consecutive diff lines within a
#      single hunk. Cross-hunk -> evidence-context-mismatch.
#   6. Substring match priority: + -> pass, matched_side="+"; - -> pass,
#      matched_side="-"; context-only -> fail, evidence-context-mismatch;
#      no match -> fail, evidence-not-found.

set -u
# Intentionally not using `set -e` - we need to continue processing other
# critics when one fails, and we rely on explicit exit-code checks.

# --- defense-in-depth preflight ---------------------------------------------
# Stage 0 (Task 7) is the primary gate for environment tooling. Check here as
# well so that if this script is ever invoked standalone the failure mode is
# clear rather than a cryptic "command not found" deep in the pipeline.
if ! command -v jq >/dev/null 2>&1; then
  printf '{"grounded":{"agent1":{"findings":[]},"agent2":{"findings":[]},"agent3":{"findings":[]},"agent4":{"findings":[]}},"drops":[],"failed_critics":[],"error":"jq not found on PATH"}\n'
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  printf '{"grounded":{"agent1":{"findings":[]},"agent2":{"findings":[]},"agent3":{"findings":[]},"agent4":{"findings":[]}},"drops":[],"failed_critics":[],"error":"python3 not found on PATH"}\n'
  exit 1
fi

# --- self-timeout -----------------------------------------------------------
# Self-terminate after 120 seconds via a background watchdog.
SELF_TIMEOUT_SECS=120
(
  sleep "$SELF_TIMEOUT_SECS"
  kill -TERM $$ 2>/dev/null
) &
TIMEOUT_WATCHER_PID=$!

# --- tmp dir ----------------------------------------------------------------
# Prefer mktemp -d under $TMPDIR; fall back to a timestamped path under
# $TMPDIR (some sandboxes block mktemp but still permit writes to $TMPDIR).
TMP_BASE="${TMPDIR:-/tmp}"
TMP_DIR="$(mktemp -d "$TMP_BASE/evground.XXXXXX" 2>/dev/null || echo "$TMP_BASE/evground.$$.$RANDOM")"
mkdir -p "$TMP_DIR" 2>/dev/null || true

trap 'rm -rf "$TMP_DIR" 2>/dev/null; kill "$TIMEOUT_WATCHER_PID" 2>/dev/null || true' EXIT

# --- read and validate top-level input --------------------------------------
INPUT="$(cat)"
if [ -z "$INPUT" ]; then
  printf '{"grounded":{"agent1":{"findings":[]},"agent2":{"findings":[]},"agent3":{"findings":[]},"agent4":{"findings":[]}},"drops":[],"failed_critics":[],"error":"empty stdin"}\n'
  exit 1
fi

# Validate top-level JSON. Missing top-level structure is a hard error.
if ! printf '%s' "$INPUT" | jq -e '.critics and .diff_path' >/dev/null 2>&1; then
  printf '{"grounded":{"agent1":{"findings":[]},"agent2":{"findings":[]},"agent3":{"findings":[]},"agent4":{"findings":[]}},"drops":[],"failed_critics":[],"error":"malformed input: missing critics or diff_path"}\n'
  exit 1
fi

DIFF_PATH="$(printf '%s' "$INPUT" | jq -r '.diff_path')"
if [ ! -r "$DIFF_PATH" ]; then
  printf '{"grounded":{"agent1":{"findings":[]},"agent2":{"findings":[]},"agent3":{"findings":[]},"agent4":{"findings":[]}},"drops":[],"failed_critics":[],"error":"diff_path not readable: %s"}\n' "$DIFF_PATH"
  exit 1
fi

# --- diff parsing -----------------------------------------------------------
# Extract diff lines for a given file path, along with their side marker
# (+, -, or space) and post-image line number. This uses awk with only
# BSD-awk-safe features: no gensub, no asorti, no length() on associative
# arrays.
#
# Output to stdout: one record per line, tab-separated:
#   <hunk_id>\t<post_line_num>\t<side>\t<content>
# where side is "+", "-", or " " (space).
#
# post_line_num is the post-image line number (right side of diff). For `-`
# lines, we report the post_line that line would have occupied if it were
# context - this is a best-effort placement for line_range bounding.
#
# hunk_id is a monotonic integer that increments per @@ header seen for this
# file, so consumers can require "same hunk" for multi-line matches.
extract_diff_lines() {
  local target_path="$1"
  # Normalize target_path to forward slashes (path names only; quoted_text
  # content is never slash-normalized).
  target_path="$(printf '%s' "$target_path" | tr '\\' '/')"

  awk -v target="$target_path" '
    BEGIN {
      current_file = ""
      in_target = 0
      post_line = 0
      hunk_id = 0
    }
    /^diff --git / {
      current_file = ""
      in_target = 0
      next
    }
    /^\+\+\+ / {
      p = substr($0, 5)
      if (p == "/dev/null") {
        current_file = ""
        in_target = 0
        next
      }
      if (substr(p, 1, 2) == "b/") {
        p = substr(p, 3)
      }
      gsub(/\\/, "/", p)
      current_file = p
      in_target = (current_file == target) ? 1 : 0
      post_line = 0
      next
    }
    /^--- / { next }
    /^@@ / {
      if (!in_target) { next }
      hunk_id++
      if (match($0, /\+[0-9]+/)) {
        plus_token = substr($0, RSTART, RLENGTH)
        post_line = substr(plus_token, 2) + 0
        # Subtract 1 so the pre-increment logic below works uniformly.
        post_line = post_line - 1
      }
      next
    }
    {
      if (!in_target) { next }
      c = substr($0, 1, 1)
      if (c == "\\") { next }
      if (c != "+" && c != "-" && c != " ") { next }
      content = substr($0, 2)
      if (c == "+" || c == " ") {
        post_line++
        printf "%d\t%d\t%s\t%s\n", hunk_id, post_line, c, content
      } else {
        # "-" line: synthetic post_line (best effort).
        printf "%d\t%d\t%s\t%s\n", hunk_id, post_line + 1, c, content
      }
    }
  ' "$DIFF_PATH"
}

# --- matching core ----------------------------------------------------------
# Given a quoted_text (possibly multi-line), a file path, and a line_range,
# determine match outcome.
#
# Returns via stdout one of:
#   "match:+"       - matched on an added line
#   "match:-"       - matched only on a removed line
#   "match:context" - matched only on a context line (-> evidence-context-mismatch)
#   "nomatch"       - no match anywhere (-> evidence-not-found)
match_quoted_text() {
  local quoted_text="$1"
  local path="$2"
  local line_start="$3"
  local line_end="$4"

  # Widen line_range by a small tolerance - critics often quote a line but
  # report the line_range of the surrounding block.
  local slack=10
  local lo=$((line_start - slack))
  local hi=$((line_end + slack))
  if [ "$lo" -lt 1 ]; then lo=1; fi

  # Normalize quoted_text line-by-line (CRLF -> LF, whitespace collapse, NFC,
  # strip trailing blank lines). Emit tab-separated per-line tokens.
  local normalized_quote
  normalized_quote="$(
    printf '%s' "$quoted_text" | python3 -c '
import sys, unicodedata, re
raw = sys.stdin.read()
raw = raw.replace("\r\n", "\n").replace("\r", "\n")
lines = raw.split("\n")
out = []
for ln in lines:
    n = unicodedata.normalize("NFC", ln)
    n = re.sub(r"\s+", " ", n).strip()
    out.append(n)
while out and out[-1] == "":
    out.pop()
sys.stdout.write("\t".join(out))
'
  )"

  if [ -z "$normalized_quote" ]; then
    printf 'nomatch\n'
    return 0
  fi

  # Get diff lines for this path and filter to the line_range window.
  local diff_lines
  diff_lines="$(
    extract_diff_lines "$path" | awk -F'\t' -v lo="$lo" -v hi="$hi" '
      { if ($2 + 0 >= lo && $2 + 0 <= hi) print $0 }
    '
  )"

  if [ -z "$diff_lines" ]; then
    printf 'nomatch\n'
    return 0
  fi

  # Normalize diff content with the same rules as quoted_text.
  local normalized_diff
  normalized_diff="$(
    printf '%s\n' "$diff_lines" | python3 -c '
import sys, unicodedata, re
for line in sys.stdin:
    line = line.rstrip("\n")
    if not line:
        continue
    parts = line.split("\t", 3)
    if len(parts) < 4:
        continue
    hunk_id, post_line, side, content = parts[0], parts[1], parts[2], parts[3]
    n = unicodedata.normalize("NFC", content)
    n = re.sub(r"\s+", " ", n).strip()
    sys.stdout.write(f"{hunk_id}\t{post_line}\t{side}\t{n}\n")
'
  )"

  if [ -z "$normalized_diff" ]; then
    printf 'nomatch\n'
    return 0
  fi

  # Perform the consecutive-match scan in python3 - awk handling of tabs
  # within content + array slicing is fiddly under the BSD-awk constraint.
  python3 -c '
import sys

quote_lines = sys.argv[1].split("\t")
diff_blob = sys.argv[2]

records = []
for line in diff_blob.splitlines():
    if not line:
        continue
    parts = line.split("\t", 3)
    if len(parts) < 4:
        continue
    hid, pln, sd, ct = parts
    try:
        pln_i = int(pln)
    except ValueError:
        continue
    records.append((hid, pln_i, sd, ct))

if not records or not quote_lines:
    print("nomatch")
    sys.exit(0)

k = len(quote_lines)

def rank(side):
    return {"+": 3, "-": 2, " ": 1}.get(side, 0)

def better(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return a if rank(a) >= rank(b) else b

best = None

for i in range(len(records) - k + 1):
    window = records[i:i+k]
    hid0 = window[0][0]
    if any(w[0] != hid0 for w in window):
        continue
    # Substring-match each quote line against each window record in order.
    wi = 0
    all_matched = True
    sides_hit = []
    for q in quote_lines:
        matched_here = False
        while wi < len(window):
            _, _, sd, ct = window[wi]
            wi += 1
            if q in ct:
                matched_here = True
                sides_hit.append(sd)
                break
        if not matched_here:
            all_matched = False
            break
    if not all_matched:
        continue
    local_best = None
    for s in sides_hit:
        local_best = better(local_best, s)
    best = better(best, local_best)
    if best == "+":
        break

# Fallback for multi-line quotes that did not match consecutively: check
# whether any individual quote line exists anywhere so we can distinguish
# "absent from file" from "appears but not consecutively".
if best is None and k > 1:
    for q in quote_lines:
        for _, _, sd, ct in records:
            if q in ct:
                best = better(best, sd)
                break

if best is None:
    print("nomatch")
elif best == "+":
    print("match:+")
elif best == "-":
    print("match:-")
else:
    print("match:context")
' "$normalized_quote" "$normalized_diff"
}

# --- per-finding grounding --------------------------------------------------
# Given a single finding (as JSON), emit one of:
#   "pass\t<finding_with_matched_side_set>"
#   "drop\t<reason>\t<finding>"
# Reasons: evidence-not-found, evidence-context-mismatch
ground_finding() {
  local finding_json="$1"

  local label_hint
  local quoted_text_is_null
  local rationale_is_null
  local quoted_text
  local path
  local line_start
  local line_end

  label_hint="$(printf '%s' "$finding_json" | jq -r '.label_hint // "null"')"
  # Distinguish JSON null from empty string with an explicit type check -
  # jq -r has no portable way to preserve that distinction textually.
  quoted_text_is_null="$(printf '%s' "$finding_json" | jq -r '(.evidence.quoted_text == null) | tostring')"
  rationale_is_null="$(printf '%s' "$finding_json" | jq -r '(.evidence.rationale == null) | tostring')"
  quoted_text="$(printf '%s' "$finding_json" | jq -r '.evidence.quoted_text // ""')"
  path="$(printf '%s' "$finding_json" | jq -r '.evidence.path // ""')"
  line_start="$(printf '%s' "$finding_json" | jq -r '.evidence.line_range[0] // 0')"
  line_end="$(printf '%s' "$finding_json" | jq -r '.evidence.line_range[1] // 0')"

  # Rule 1: pass-through for question / cross-cutting with null quoted_text
  # and non-null rationale.
  if { [ "$label_hint" = "question" ] || [ "$label_hint" = "cross-cutting" ]; } \
     && [ "$quoted_text_is_null" = "true" ] \
     && [ "$rationale_is_null" = "false" ]; then
    local out
    out="$(printf '%s' "$finding_json" | jq -c '.evidence.matched_side = null')"
    printf 'pass\t%s\n' "$out"
    return 0
  fi

  # Require quoted_text for grounding.
  if [ "$quoted_text_is_null" = "true" ] || [ -z "$quoted_text" ]; then
    printf 'drop\tevidence-not-found\t%s\n' "$finding_json"
    return 0
  fi

  if [ -z "$path" ]; then
    printf 'drop\tevidence-not-found\t%s\n' "$finding_json"
    return 0
  fi

  # Normalize evidence.path to POSIX forward slashes for the match call
  # (path only; quoted_text content is never slash-normalized).
  local norm_path
  norm_path="$(printf '%s' "$path" | tr '\\' '/')"

  local result
  result="$(match_quoted_text "$quoted_text" "$norm_path" "$line_start" "$line_end")"

  case "$result" in
    match:+)
      local out
      out="$(printf '%s' "$finding_json" | jq -c '.evidence.matched_side = "+"')"
      printf 'pass\t%s\n' "$out"
      ;;
    match:-)
      local out
      out="$(printf '%s' "$finding_json" | jq -c '.evidence.matched_side = "-"')"
      printf 'pass\t%s\n' "$out"
      ;;
    match:context)
      printf 'drop\tevidence-context-mismatch\t%s\n' "$finding_json"
      ;;
    nomatch|*)
      printf 'drop\tevidence-not-found\t%s\n' "$finding_json"
      ;;
  esac
}

# --- per-critic processing --------------------------------------------------
TMP_GROUNDED_AGENT1="$TMP_DIR/grounded_agent1.jsonl"
TMP_GROUNDED_AGENT2="$TMP_DIR/grounded_agent2.jsonl"
TMP_GROUNDED_AGENT3="$TMP_DIR/grounded_agent3.jsonl"
TMP_GROUNDED_AGENT4="$TMP_DIR/grounded_agent4.jsonl"
TMP_DROPS="$TMP_DIR/drops.jsonl"
TMP_FAILED="$TMP_DIR/failed_critics.txt"
: >"$TMP_GROUNDED_AGENT1"
: >"$TMP_GROUNDED_AGENT2"
: >"$TMP_GROUNDED_AGENT3"
: >"$TMP_GROUNDED_AGENT4"
: >"$TMP_DROPS"
: >"$TMP_FAILED"

process_critic() {
  local critic_name="$1"
  local grounded_file="$2"

  # Per-critic validation: extract findings[] as an array. If absent or
  # non-array, mark critic as failed (critic-malformed-json) and skip.
  if ! printf '%s' "$INPUT" | jq -e ".critics.\"$critic_name\".findings | type == \"array\"" >/dev/null 2>&1; then
    printf '%s\n' "$critic_name" >>"$TMP_FAILED"
    # Record a drop entry with reason "critic-malformed-json" so the drop
    # taxonomy is complete and exercisable in downstream tests.
    printf '{"finding":null,"reason":"critic-malformed-json","critic":"%s"}\n' "$critic_name" >>"$TMP_DROPS"
    return 0
  fi

  local findings
  findings="$(printf '%s' "$INPUT" | jq -c ".critics.\"$critic_name\".findings[]" 2>/dev/null)"

  if [ -z "$findings" ]; then
    return 0
  fi

  while IFS= read -r finding; do
    [ -z "$finding" ] && continue
    local ground_out
    ground_out="$(ground_finding "$finding")"
    local kind
    kind="${ground_out%%$'\t'*}"
    local rest="${ground_out#*$'\t'}"
    case "$kind" in
      pass)
        printf '%s\n' "$rest" >>"$grounded_file"
        ;;
      drop)
        local reason="${rest%%$'\t'*}"
        local finding_body="${rest#*$'\t'}"
        printf '{"finding":%s,"reason":"%s","critic":"%s"}\n' \
          "$finding_body" "$reason" "$critic_name" >>"$TMP_DROPS"
        ;;
    esac
  done <<EOF
$findings
EOF
}

process_critic agent1 "$TMP_GROUNDED_AGENT1"
process_critic agent2 "$TMP_GROUNDED_AGENT2"
process_critic agent3 "$TMP_GROUNDED_AGENT3"
process_critic agent4 "$TMP_GROUNDED_AGENT4"

# --- assemble final JSON ----------------------------------------------------
assemble_array() {
  local jsonl_file="$1"
  if [ ! -s "$jsonl_file" ]; then
    printf '[]'
  else
    jq -cs '.' "$jsonl_file"
  fi
}

GROUNDED1_ARR="$(assemble_array "$TMP_GROUNDED_AGENT1")"
GROUNDED2_ARR="$(assemble_array "$TMP_GROUNDED_AGENT2")"
GROUNDED3_ARR="$(assemble_array "$TMP_GROUNDED_AGENT3")"
GROUNDED4_ARR="$(assemble_array "$TMP_GROUNDED_AGENT4")"
DROPS_ARR="$(assemble_array "$TMP_DROPS")"

if [ -s "$TMP_FAILED" ]; then
  FAILED_ARR="$(jq -cR . "$TMP_FAILED" | jq -cs '.')"
else
  FAILED_ARR='[]'
fi

jq -nc \
  --argjson g1 "$GROUNDED1_ARR" \
  --argjson g2 "$GROUNDED2_ARR" \
  --argjson g3 "$GROUNDED3_ARR" \
  --argjson g4 "$GROUNDED4_ARR" \
  --argjson drops "$DROPS_ARR" \
  --argjson failed "$FAILED_ARR" \
  '{
     grounded: {
       agent1: {findings: $g1},
       agent2: {findings: $g2},
       agent3: {findings: $g3},
       agent4: {findings: $g4}
     },
     drops: $drops,
     failed_critics: $failed
   }'

exit 0
