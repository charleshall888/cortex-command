#!/bin/bash
# launchd-fired launcher for cortex overnight scheduled runs (R6 / R7 / R9 / R13).
#
# This file is a TEMPLATE rendered at schedule time by
# MacOSLaunchAgentBackend._install_launcher_script. The following markers
# are substituted with concrete values before the file is written to
# $TMPDIR/cortex-overnight-launch/launcher-{label}.sh:
#
#   @@PLIST_PATH@@    Absolute path to the LaunchAgent plist on disk.
#   @@LAUNCHER_PATH@@ Absolute path to this launcher script on disk.
#   @@SESSION_DIR@@   Absolute path to the overnight session directory.
#   @@LABEL@@         launchd label string for this fire.
#   @@CORTEX_BIN@@    Absolute path to the cortex binary launchd will exec.
#   @@SESSION_ID@@    Overnight session identifier.
#
# Behavior summary (see spec §R6 / §R7 / §R9 / §R13 for the load-bearing
# contract):
#   1. Pre-flight: confirm the cortex binary exists and is executable. If
#      not, write a fail-marker JSON sentinel at
#      <session_dir>/scheduled-fire-failed.json BEFORE cleaning up, fire a
#      macOS notification, self-clean, and exit non-zero. This is the one
#      case where `start` never runs and bash must author the marker.
#   2. On the success path: invoke the cortex binary in the FOREGROUND
#      with `overnight start --state <abs> --format json --force
#      --scheduled` (and none of the legacy launchd/session-id flags).
#      Detachment now happens inside cortex: `start` routes through
#      `_spawn_runner_async`'s `subprocess.Popen(..., start_new_session=True)`,
#      which makes the runner its own session leader so it survives
#      launchd's process-group SIGTERM when the launcher exits.
#   3. After `start` returns, decide success/dead/advisory from the
#      ROBUST DISCRIMINATOR, NOT the process exit code. Under
#      `--scheduled`, `start` writes a single-token file at
#      <session_dir>/spawn-outcome containing exactly one of
#      `started` / `spawn_died` / `spawn_unconfirmed` (cli_handler.py
#      `_write_spawn_outcome`). The exit code is 1 for BOTH a dead fire
#      and a live-but-unconfirmed fire, so the launcher MUST key its
#      decision on the token file — read via shell builtins (`[ -f ]` +
#      `$(cat …)`), which need no interpreter and no PATH and are
#      therefore robust under launchd's `cwd=/` and whatever PATH the
#      plist injects. Branch:
#        - `started`            → success: self-clean and exit 0. (A
#          later task adds the spent-job `launchctl bootout` here.)
#        - `spawn_died` / exec  → genuine dead fire: write
#          scheduled-fire-failed.json with the REAL error_class, fire a
#          notification, self-clean, exit non-zero.
#        - `spawn_unconfirmed`  → live-but-slow runner: write a DISTINCT
#          ADVISORY marker (NOT a failure marker) carrying a kind/severity
#          field, self-clean, exit 0. The runner is alive; this is not a
#          failure and gets no failure notification.
#
# The legacy exit-code→EPERM mapping for the post-`start` path is GONE:
# `start` returning exit 1 is expected for both the dead and advisory
# cases, so an exit-code→error_class mapping would discard the real class
# the discriminator carries.

set -u

PLIST_PATH='@@PLIST_PATH@@'
LAUNCHER_PATH='@@LAUNCHER_PATH@@'
SESSION_DIR='@@SESSION_DIR@@'
LABEL='@@LABEL@@'
CORTEX_BIN='@@CORTEX_BIN@@'
SESSION_ID='@@SESSION_ID@@'

FAIL_MARKER="${SESSION_DIR}/scheduled-fire-failed.json"
ADVISORY_MARKER="${SESSION_DIR}/scheduled-fire-advisory.json"
SPAWN_OUTCOME="${SESSION_DIR}/spawn-outcome"

# ---------------------------------------------------------------------------
# Marker writers
# ---------------------------------------------------------------------------
#
# We hand-roll the JSON here (rather than shelling out to python) because
# (a) the launcher must remain a self-contained bash script with minimal
# external deps and (b) python may itself be the thing that failed (PATH
# issue, EPERM on python binary, etc.). Escape double-quotes and
# backslashes in the free-text payload.
_json_escape() {
    local raw="$1"
    raw="${raw//\\/\\\\}"
    raw="${raw//\"/\\\"}"
    printf '%s' "${raw}"
}

# Writes the fail-marker JSON BEFORE plist/launcher removal so a failed
# runner does not lose the diagnostic. Shape per spec R13:
# {ts, error_class, error_text, label, session_id}.
write_fail_marker() {
    local error_class="$1"
    local error_text="$2"

    # Best-effort mkdir; if the session dir cannot be created we still
    # try to write the marker (the morning-report scanner can recover
    # from a missing parent dir).
    mkdir -p "${SESSION_DIR}" 2>/dev/null || true

    local ts
    ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

    local escaped_error_text
    escaped_error_text="$(_json_escape "${error_text}")"

    cat > "${FAIL_MARKER}" <<EOF
{"ts": "${ts}", "error_class": "${error_class}", "error_text": "${escaped_error_text}", "label": "${LABEL}", "session_id": "${SESSION_ID}"}
EOF
}

# Writes the DISTINCT advisory marker (R6/R8): a live-but-unconfirmed
# fire is NOT a failure. The marker carries a ``kind``/``severity`` field
# so the morning-report scanner renders it as a non-failure "started, not
# yet confirmed" advisory rather than a failed fire. Distinct filename
# (scheduled-fire-advisory.json) AND a kind field — either alone marks it
# non-failure; both make the intent unambiguous.
write_advisory_marker() {
    local error_class="$1"
    local advisory_text="$2"

    mkdir -p "${SESSION_DIR}" 2>/dev/null || true

    local ts
    ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

    local escaped_text
    escaped_text="$(_json_escape "${advisory_text}")"

    cat > "${ADVISORY_MARKER}" <<EOF
{"ts": "${ts}", "kind": "advisory", "severity": "advisory", "error_class": "${error_class}", "error_text": "${escaped_text}", "label": "${LABEL}", "session_id": "${SESSION_ID}"}
EOF
}

fire_notification() {
    # Fire an immediate macOS notification. Best-effort: if osascript is
    # missing or the user has notifications muted, the run still failed
    # and the fail-marker is the durable signal. Suppress all output so
    # a notification failure does not pollute launchd logs.
    /usr/bin/osascript \
        -e "display notification \"Scheduled overnight run failed at fire time — see ${SESSION_DIR}\" with title \"cortex-overnight\" sound name \"Basso\"" \
        >/dev/null 2>&1 || true
}

cleanup_self() {
    # Remove the plist and launcher copy. Best-effort — the GC pass at
    # next schedule time also handles stragglers (R19).
    rm -f "${PLIST_PATH}" 2>/dev/null || true
    rm -f "${LAUNCHER_PATH}" 2>/dev/null || true
}

# Pre-flight failure handler. ONLY fires when `start` never ran (the
# cortex binary is missing or non-executable). Maps the bash-side exec
# error code to an error_class and authors the fail-marker. This path
# does NOT key off a `start` exit code (start did not run), so the
# EPERM/command-not-found mapping here is correct: it describes a
# bash-side exec failure, not a runner outcome.
handle_failure() {
    local exit_code="$1"
    local error_class
    if [ "${exit_code}" -eq 127 ]; then
        error_class="command_not_found"
    elif [ "${exit_code}" -eq 1 ]; then
        error_class="EPERM"
    else
        error_class="exit_${exit_code}"
    fi
    local error_text="cortex binary at ${CORTEX_BIN} could not be executed at fire time (exit ${exit_code})"
    write_fail_marker "${error_class}" "${error_text}"
    fire_notification
    cleanup_self
    exit "${exit_code}"
}

# ---------------------------------------------------------------------------
# Pre-flight: confirm the cortex binary exists and is executable.
# ---------------------------------------------------------------------------
#
# This is the one case where `start` never runs and bash must author the
# marker. Catching command-not-found (exit 127) up-front gives us a clean
# error class without depending on shell-trap subtleties around how the
# foreground `start` invocation propagates child exit codes.

if [ ! -x "${CORTEX_BIN}" ]; then
    handle_failure 127
fi

# ---------------------------------------------------------------------------
# Start the runner (foreground; cortex performs the detach).
# ---------------------------------------------------------------------------
#
# We invoke `cortex overnight start` in the FOREGROUND and let cortex
# detach the runner for us. `start` routes through
# `_spawn_runner_async`'s `subprocess.Popen(..., start_new_session=True)`,
# which calls setsid before returning, so the runner is already its own
# session leader by the time the spawn handshake begins — it survives
# launchd's process-group SIGTERM when this launcher exits. The launcher
# stays in the foreground only for the handshake; because the runner is
# already in its own session, the foreground wait cannot reap it.
#
# Flags (each load-bearing):
#   --state <abs>   Absolute per-session state path. cwd is `/` under
#                   launchd, so cwd-based auto-discovery cannot be used.
#   --format json   Mandatory: keeps the run-now `concurrent_runner`
#                   refusal active so a live runner holding the lock is
#                   not clobbered, and emits the JSON envelope.
#   --force         Bypasses ONLY the launcher's own pending-schedule
#                   guard, never live-runner protection.
#   --scheduled     Marks this as a fire-time start so `start` writes the
#                   single-token spawn-outcome discriminator (R6/R8) and
#                   uses the longer fire-path handshake budget.
#
# The legacy launchd flag (which re-implemented the broken bash detach)
# is gone, as is the session-id flag (`start` rejects it — argparse exit
# 2). The session is identified by the `--state` path; @@SESSION_ID@@ is
# still substituted into the marker `session_id` field above.

mkdir -p "${SESSION_DIR}" 2>/dev/null || true

STATE_PATH="${SESSION_DIR}/overnight-state.json"

# Run `start` in the foreground. We deliberately do NOT route a non-zero
# exit through handle_failure: under --scheduled, exit 1 is EXPECTED for
# both a dead fire and a live-but-unconfirmed fire. The spawn-outcome
# token file is the robust discriminator we branch on below. We still
# capture the JSON envelope on stdout (richer fallback) and tee stderr to
# a per-session log for diagnostics.
START_ENVELOPE="$(
    "${CORTEX_BIN}" overnight start \
        --state "${STATE_PATH}" \
        --format json \
        --force \
        --scheduled \
        </dev/null \
        2>>"${SESSION_DIR}/runner-stderr.log"
)"

# Persist the envelope for the morning report / fallback diagnostics.
printf '%s\n' "${START_ENVELOPE}" >>"${SESSION_DIR}/runner-stdout.log"

# ---------------------------------------------------------------------------
# Decide from the robust discriminator (token file), NOT the exit code.
# ---------------------------------------------------------------------------
#
# Read the single-token spawn-outcome file via shell builtins. `[ -f ]`
# and `$(cat …)` need no interpreter and no PATH, so this read is robust
# under launchd's degraded environment. If the file is missing (e.g.
# `start` crashed before writing it, or an older cortex that does not
# emit it), treat the absence — together with whether the runner claimed
# runner.pid — as the discriminator: a present runner.pid means a live
# runner (advisory), otherwise a dead fire.

SPAWN_TOKEN=""
if [ -f "${SPAWN_OUTCOME}" ]; then
    SPAWN_TOKEN="$(cat "${SPAWN_OUTCOME}" 2>/dev/null)"
fi

case "${SPAWN_TOKEN}" in
    started)
        # Success: the runner claimed runner.pid within the handshake
        # window and is its own session leader, responsible for its own
        # lifecycle. Self-clean and exit 0 so launchd marks the agent run
        # complete.
        #
        # SEAM (Task 12): the spent one-shot `launchctl bootout
        # gui/$(id -u)/${LABEL}` belongs HERE, before cleanup_self, so a
        # successful fire tears down its own (annually-recurring) schedule
        # and cannot refire ~a year later. Not implemented yet.
        cleanup_self
        exit 0
        ;;
    spawn_unconfirmed)
        # Live but slow: the runner is alive but had not yet claimed
        # runner.pid when the handshake budget elapsed. This is NOT a
        # failure — the runner is coming up. Record a DISTINCT advisory
        # marker (not a fail-marker, no failure notification), self-clean,
        # and exit 0.
        write_advisory_marker \
            "spawn_unconfirmed" \
            "scheduled overnight fire started but not yet confirmed (runner alive, runner.pid not yet claimed)"
        cleanup_self
        exit 0
        ;;
    spawn_died)
        # Genuine dead fire: the runner child died before claiming
        # runner.pid. Write the fail-marker with the REAL error_class
        # (spawn_died — NOT the legacy EPERM), fire a notification,
        # self-clean, and exit non-zero so launchd records the failure.
        write_fail_marker \
            "spawn_died" \
            "scheduled overnight fire died before claiming runner.pid (cortex binary at ${CORTEX_BIN})"
        fire_notification
        cleanup_self
        exit 1
        ;;
    *)
        # No (or unrecognized) token: `start` likely crashed before
        # writing the discriminator, or an exec/argparse error occurred.
        # Use runner.pid existence as a last-resort discriminator: a live
        # runner.pid means the runner is up (advisory), otherwise treat
        # it as a dead fire and surface it loudly.
        if [ -f "${SESSION_DIR}/runner.pid" ]; then
            write_advisory_marker \
                "spawn_unconfirmed" \
                "scheduled overnight fire produced no spawn-outcome token but runner.pid exists (runner appears live)"
            cleanup_self
            exit 0
        fi
        write_fail_marker \
            "spawn_died" \
            "scheduled overnight fire produced no spawn-outcome token and no runner.pid (cortex binary at ${CORTEX_BIN})"
        fire_notification
        cleanup_self
        exit 1
        ;;
esac
