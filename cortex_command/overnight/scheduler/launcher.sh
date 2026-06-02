#!/bin/bash
# launchd-fired launcher for cortex overnight scheduled runs (R9 / R13).
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
# Behavior summary (see spec §R9 / §R13 for the load-bearing contract):
#   1. Install an error trap covering EPERM (errno 1, mapped to exit 1)
#      and command-not-found (exit 127). On either, write a fail-marker
#      JSON sentinel at <session_dir>/scheduled-fire-failed.json BEFORE
#      cleaning up so the morning report scanner has a diagnostic.
#   2. Fire an immediate macOS notification via osascript so the user
#      sees the failure at fire time, not on next interaction.
#   3. Self-clean by removing the plist file and this launcher copy.
#   4. Exit non-zero so launchd records the failure in its own logs.
#
# On the success path: invoke the cortex binary in the FOREGROUND with
# `overnight start --state <abs> --format json --force` (and none of the
# legacy launchd/session-id flags). Detachment now happens inside
# cortex: `start` routes through `_spawn_runner_async`'s `subprocess.Popen(...,
# start_new_session=True)`, which makes the runner its own session
# leader so it survives launchd's process-group SIGTERM when the
# launcher exits. The launcher therefore does NOT background, setsid, or
# disown anything — it stays in the foreground only long enough for
# `start`'s spawn handshake, captures the JSON envelope on stdout for
# the fire-time liveness discriminator read, and then removes the plist
# + launcher and exits. `caffeinate` is no longer the launcher's
# concern; the idle-sleep assertion is held by a runner-lifetime-bound
# child of the runner itself.

set -u

PLIST_PATH='@@PLIST_PATH@@'
LAUNCHER_PATH='@@LAUNCHER_PATH@@'
SESSION_DIR='@@SESSION_DIR@@'
LABEL='@@LABEL@@'
CORTEX_BIN='@@CORTEX_BIN@@'
SESSION_ID='@@SESSION_ID@@'

FAIL_MARKER="${SESSION_DIR}/scheduled-fire-failed.json"

# ---------------------------------------------------------------------------
# Failure handler
# ---------------------------------------------------------------------------
#
# Writes the fail-marker JSON BEFORE plist/launcher removal so a failed
# runner does not lose the diagnostic. Then fires an osascript
# notification, removes the plist + launcher, and exits non-zero.
write_fail_marker() {
    local error_class="$1"
    local error_text="$2"

    # Best-effort mkdir; if the session dir cannot be created we still
    # try to write the marker (the morning-report scanner can recover
    # from a missing parent dir).
    mkdir -p "${SESSION_DIR}" 2>/dev/null || true

    local ts
    ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

    # JSON shape per spec R13: {ts, error_class, error_text, label, session_id}.
    # We hand-roll the JSON here (rather than shelling out to python)
    # because (a) the launcher must remain a self-contained bash script
    # with minimal external deps and (b) python may itself be the thing
    # that failed (PATH issue, EPERM on python binary, etc.). Escape
    # double-quotes and backslashes in the error_text payload.
    local escaped_error_text
    escaped_error_text="${error_text//\\/\\\\}"
    escaped_error_text="${escaped_error_text//\"/\\\"}"

    cat > "${FAIL_MARKER}" <<EOF
{"ts": "${ts}", "error_class": "${error_class}", "error_text": "${escaped_error_text}", "label": "${LABEL}", "session_id": "${SESSION_ID}"}
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
    local error_text="cortex binary at ${CORTEX_BIN} failed at fire time (exit ${exit_code})"
    write_fail_marker "${error_class}" "${error_text}"
    fire_notification
    cleanup_self
    exit "${exit_code}"
}

# ---------------------------------------------------------------------------
# Pre-flight: confirm the cortex binary exists and is executable.
# ---------------------------------------------------------------------------
#
# Catching command-not-found (exit 127) up-front gives us a clean error
# class without depending on shell-trap subtleties around how the
# foreground `start` invocation propagates child exit codes. EPERM on
# exec() shows up as exit 126 in bash; we map both 1 and 126/127 to the
# failure handler.

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
#   --format json   Mandatory: the JSON envelope on stdout is read by the
#                   fire-time liveness discriminator, and `--format json`
#                   keeps the run-now `concurrent_runner` refusal active so
#                   a live runner holding the lock is not clobbered.
#   --force         Bypasses ONLY the launcher's own pending-schedule
#                   guard, never live-runner protection.
#
# The legacy launchd flag (which re-implemented the broken bash detach)
# is gone, as is the session-id flag (`start` rejects it — argparse exit
# 2). The session is identified by the `--state` path; @@SESSION_ID@@ is
# still substituted into the fail-marker `session_id` field above.

mkdir -p "${SESSION_DIR}" 2>/dev/null || true

STATE_PATH="${SESSION_DIR}/overnight-state.json"

# Capture stdout (the JSON envelope) for the fire-time liveness
# discriminator read; tee stderr to a per-session log for diagnostics.
START_ENVELOPE="$(
    "${CORTEX_BIN}" overnight start \
        --state "${STATE_PATH}" \
        --format json \
        --force \
        </dev/null \
        2>>"${SESSION_DIR}/runner-stderr.log"
)"
start_rc=$?

if [ "${start_rc}" -ne 0 ]; then
    # cortex itself exited non-zero (binary EPERM, argparse error,
    # spawn failure, etc.). Route through the failure handler so the
    # morning report gets a diagnostic.
    handle_failure "${start_rc}"
fi

# Persist the envelope for the liveness discriminator / morning report.
printf '%s\n' "${START_ENVELOPE}" >>"${SESSION_DIR}/runner-stdout.log"

# Successful start — remove the plist and launcher copy. The runner is
# now its own session leader, responsible for its own lifecycle; we exit
# 0 so launchd marks the agent run complete.
cleanup_self

exit 0
