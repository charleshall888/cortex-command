#!/bin/bash
# SessionStart-async hook: background cortex CLI reinstall on drift.
#
# Closes the daytime-user execution gap left by the visibility-only
# ``cortex-cli-version-sync.sh`` hook (#235) and the MCP-call-gated
# ``_ensure_cortex_installed`` path. On drift this hook spawns a
# detached uv-reinstall subprocess so users who never invoke a
# cortex-overnight MCP tool still get auto-upgraded.
#
# Registered with ``"async": true`` in ``hooks.json``. On Claude Code
# v2.1.139+ the field runs the hook in the background; on older
# clients the field is silently ignored but ``install_core``'s
# always-detach pattern (``subprocess.Popen(..., start_new_session=
# True)`` inside ``run_install_in_background``) still lets this script
# exit in ~50–200ms regardless of install duration, so Claude Code
# launch never freezes.
#
# All real work lives in ``install_core.run_install_in_background()``
# — including skip predicates (``CORTEX_DEV_MODE=1``,
# ``CORTEX_AUTO_INSTALL=0``), drift comparison against ``CLI_PIN``,
# the in-flight-session guard, the install flock, the under-lock
# re-check, the install-in-progress marker, and the detached
# uv-reinstall subprocess spawn. This script's job is the bash trampoline:
# PATH bootstrap, JSON stdin parse, env-export, Python heredoc, and
# defensive ``exit 0`` on every failure path.

set -euo pipefail

# PATH bootstrap so python3/jq/cortex are reachable on minimal-PATH
# (macOS Dock launchd) sessions — same shape as
# claude/hooks/cortex-session-start-path-bootstrap.sh:29.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:${PATH:-}"

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command"

# Parse stdin to find the cwd Claude was launched in, then hand off to
# Python. The async hook has no throttle sentinel of its own —
# ``install_core.run_install_in_background()`` is throttled by the
# ``session-install-failed.<ts>`` window (R22, 30 min) and by the
# under-lock re-check (R18) which short-circuits when a concurrent
# install already brought the version up to ``CLI_PIN``.
INPUT=$(cat)
HOOK_CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)
[[ -n "${HOOK_CWD:-}" ]] || HOOK_CWD="$(pwd)"

# ``CLAUDE_PLUGIN_ROOT`` is exported by Claude Code when a hook fires
# from a plugin context. If absent (manual invocation, test
# environment), silent skip — install_core's ``_enforce_plugin_root``
# would sys.exit(1) without it anyway.
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
[[ -n "$PLUGIN_ROOT" ]] || exit 0

export HOOK_CWD HOOK_STATE_DIR="$STATE_DIR" HOOK_PLUGIN_ROOT="$PLUGIN_ROOT" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT"

# Disable errexit around the heredoc so any unexpected Python failure
# (import error, sys.exit non-zero, unhandled exception) cannot brick
# Claude Code launch. Defensive ``exit 0`` per the hooks-never-crash
# contract.
set +e
python3 - <<'PY'
import os
import sys

try:
    plugin_root = os.environ.get("HOOK_PLUGIN_ROOT", "")
    if not plugin_root:
        sys.exit(0)

    # ``install_core`` is a stdlib-only sibling of ``server.py`` (factored
    # in Phase 2 / Task 8) so this hook never loads ``mcp``, ``fastmcp``,
    # ``pydantic``, or any other third-party dependency. The sys.path
    # insert lets the bare system python3 (no PEP 723 venv) import it.
    sys.path.insert(0, plugin_root)
    import install_core

    # All skip predicates (CORTEX_DEV_MODE, CORTEX_AUTO_INSTALL,
    # dirty cortex-command tree, non-main branch, recent
    # session-install-failed sentinel, in-flight session guard, probe
    # failure, no-drift), the under-lock re-check, the marker write,
    # and the detached Popen spawn all live inside
    # run_install_in_background(). On every path it returns None and
    # the bash trampoline exits 0.
    install_core.run_install_in_background()
except SystemExit:
    # _enforce_plugin_root raises SystemExit(1) when CLAUDE_PLUGIN_ROOT
    # is unset or this file is outside it. Suppress so the hook still
    # exits 0; the absence-of-CLAUDE_PLUGIN_ROOT case is the bash
    # guard above (we already exit 0 there), and the misplaced-file
    # case is a packaging bug surfaced by the pre-commit guard.
    pass
except Exception:
    # Catch-all: any other Python-side failure (ImportError, OSError
    # in install_core, etc.) must not propagate. The hook is
    # best-effort visibility; failures are recoverable on the next
    # session via the sync hook's prior-failure surfacing (R25).
    pass
PY
set -e

exit 0
