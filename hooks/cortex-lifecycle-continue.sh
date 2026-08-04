#!/bin/bash
# Hook: resume the build loop when it ends a turn mid-lifecycle at a phase the
# state machine already says crosses without asking. Registered on Stop.
#
# Why a hook and not prose (#445, superseding #423's prose attempt): by the
# time the model has emitted its summary, every instruction it was given has
# already run and lost. A prose fix is a bet that the model will not end its
# turn; Stop is the only lever that acts *after* the turn ends.
set -euo pipefail

INPUT=$(cat)

CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty')
[[ -n "$CWD" ]] || CWD="$(pwd)"

LIFECYCLE_DIR="$CWD/cortex/lifecycle"

# Cheapest possible guard, first: one stat. This hook has no matcher, so it
# fires on every turn end in every repo the plugin is installed into. Repos
# with no lifecycle pay a directory test and nothing else -- never a process
# spawn.
[[ -d "$LIFECYCLE_DIR" ]] || exit 0

# Operator escape hatch, before any work.
[[ -z "${CORTEX_NO_AUTOCONTINUE:-}" ]] || exit 0

SESSION_ID=$(printf '%s' "$INPUT" | jq -r '.session_id // ""')
[[ -n "$SESSION_ID" ]] || exit 0

# Only ever act on the lifecycle bound to THIS session. A .session naming a
# different session is another session's in-flight work, and in-flight is
# indistinguishable from stalled when you are looking at someone else's
# events.log -- the phase you would "resume" is one that session is mid-way
# through writing.
FEATURE=""
for session_file in "$LIFECYCLE_DIR"/*/.session; do
  [[ -f "$session_file" ]] || continue
  [[ "$(cat "$session_file" 2>/dev/null)" == "$SESSION_ID" ]] || continue
  FEATURE=$(basename "$(dirname "$session_file")")
  break
done
[[ -n "$FEATURE" ]] || exit 0

FEATURE_DIR="$LIFECYCLE_DIR/$FEATURE"
[[ ! -f "$FEATURE_DIR/.autocontinue-off" ]] || exit 0

# A finished feature also serves state "complete" (the selector reads
# "feature_complete logged or review APPROVED"), so the served state alone
# cannot tell "needs completing" from "is completed". Check the terminal
# event directly or the hook re-enters a done lifecycle.
! grep -q '"event": "feature_complete"' "$FEATURE_DIR/events.log" 2>/dev/null || exit 0

command -v cortex-lifecycle-next >/dev/null || exit 0
ENVELOPE=$(cortex-lifecycle-next "$FEATURE" 2>/dev/null) || exit 0
STATE=$(printf '%s' "$ENVELOPE" | jq -r '.state // ""')

# Scoped to the phases whose own arms already say to cross without asking:
# review.md "approved -> Complete: announce briefly and auto-advance", and
# complete. Plan gates on an approval surface and implement owns batch-failure
# triage, so neither is auto-continued.
#
# Note on complete: `complete` is terminal=True in the transition table, so its
# in-phase pauses (complete-merge-wait's PR handoff, the orphan-PR pick) live in
# prose and are NOT visible in pause_spec below. The progress key is what bounds
# that exposure -- entering complete nudges once, and a legitimate handoff after
# it moves neither state nor event count, so the hook goes quiet.
case "$STATE" in
  review | complete) ;;
  *) exit 0 ;;
esac

# The state machine's own answer to "is a user surface owed here". Any active
# pause spec (plan approval, batch-failure triage, an escalated verdict) stops.
[[ "$(printf '%s' "$ENVELOPE" | jq -r '.pause_spec.active // false')" != "true" ]] || exit 0

# Nudge once per unit of real lifecycle progress, keyed on (state, event
# count). This is what keeps the hook from becoming a taskmaster: it fires on
# *every* turn end while a lifecycle is bound, including turns where the
# operator broke off to ask an unrelated question. Conversation writes no
# events and changes no state, so the key is unchanged and the hook stays
# silent. A boundary crossing writes phase_transition, so the key moves and the
# stall gets exactly one nudge. A rework round-trip also moves it, so the
# second implement->review crossing is covered too.
#
# TOTAL is a backstop, not the main guard: the Stop contract has no
# platform-level protection against a hook that always blocks, and the key
# alone cannot bound a pathological loop that writes an event every turn.
TOTAL_CAP=10
EVENTS=$(grep -c "" "$FEATURE_DIR/events.log" 2>/dev/null || echo 0)
COUNTER="$FEATURE_DIR/.autocontinue"
PREV_KEY=""
TOTAL=0
if [[ -f "$COUNTER" ]]; then
  IFS=: read -r PREV_KEY TOTAL <"$COUNTER" || true
fi
[[ "$TOTAL" =~ ^[0-9]+$ ]] || TOTAL=0
[[ "$PREV_KEY" != "$STATE@$EVENTS" ]] || exit 0
((TOTAL < TOTAL_CAP)) || exit 0
printf '%s@%s:%s\n' "$STATE" "$EVENTS" "$((TOTAL + 1))" >"$COUNTER"

cat >&2 <<EOF
Lifecycle "$FEATURE" is at phase "$STATE", which crosses without operator
confirmation. Continue it now: execute that phase from the Step 3 table in the
build skill. Do not ask whether to proceed -- that question is what this hook
exists to stop.

To hand back to the operator here instead:
  touch "$FEATURE_DIR/.autocontinue-off"
EOF
exit 2
