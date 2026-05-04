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
# On the success path: detach via `setsid nohup` wrapping
# `/usr/bin/caffeinate -i` wrapping the cortex binary invoked with
# `overnight start --launchd --session-id <id>`, redirect stdin from
# /dev/null and stdout/stderr to per-session log files, then disown and
# exit 0. The plist + launcher are removed AFTER the runner is
# successfully backgrounded.

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
# class without depending on shell-trap subtleties around how `setsid`
# propagates child exit codes. EPERM on exec() shows up as exit 126 in
# bash; we map both 1 and 126/127 to the failure handler.

if [ ! -x "${CORTEX_BIN}" ]; then
    handle_failure 127
fi

# ---------------------------------------------------------------------------
# Detach the runner.
# ---------------------------------------------------------------------------
#
# `setsid nohup caffeinate -i <cortex> overnight start --launchd
#  --session-id <id>` reparents the runner to PID 1 (init) so launchd
# considers the launcher complete after fork. Redirect stdin from
# /dev/null and append stdout/stderr to per-session log files so the
# runner does not hold the launchd-provided pipes open.

mkdir -p "${SESSION_DIR}" 2>/dev/null || true

# Detach. The spec (R9) says "setsid nohup ..."; stock macOS lacks
# setsid (it's a util-linux binary), so we prefer it when available
# (e.g. brew install util-linux) and fall back to plain `nohup` + `&` +
# `disown` otherwise. nohup + bash backgrounding + disown is the
# canonical macOS daemonization recipe; the resulting child is
# signal-immune and reparents to PID 1 once the parent (launchd-fired
# launcher) exits.
if command -v setsid >/dev/null 2>&1; then
    setsid nohup /usr/bin/caffeinate -i \
        "${CORTEX_BIN}" overnight start --launchd --session-id "${SESSION_ID}" \
        </dev/null \
        >>"${SESSION_DIR}/runner-stdout.log" \
        2>>"${SESSION_DIR}/runner-stderr.log" \
        &
else
    nohup /usr/bin/caffeinate -i \
        "${CORTEX_BIN}" overnight start --launchd --session-id "${SESSION_ID}" \
        </dev/null \
        >>"${SESSION_DIR}/runner-stdout.log" \
        2>>"${SESSION_DIR}/runner-stderr.log" \
        &
fi

spawn_rc=$?
if [ "${spawn_rc}" -ne 0 ]; then
    # The shell could not background the command at all (rare — usually
    # an EPERM on the setsid/caffeinate binaries themselves). Map to
    # EPERM so the morning report classifies it correctly.
    handle_failure 1
fi

disown 2>/dev/null || true

# Successful spawn — remove the plist and launcher copy. The runner
# itself is now responsible for its own lifecycle; we exit 0 so launchd
# marks the agent run complete.
cleanup_self

exit 0
