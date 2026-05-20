#!/bin/bash
# SessionStart hook: cortex CLI version drift detector (#235).
#
# Probes the installed CLI against ``CLI_PIN`` (regex-parsed from the
# cortex-overnight plugin's server.py) and emits ``additionalContext``
# on drift so Claude warns about stale Bash-subprocess ``cortex …``
# calls. Visibility-only — does NOT reinstall. The next MCP tool call
# into cortex-overnight triggers the real reinstall via
# ``_ensure_cortex_installed``.
#
# Ordering matters for throttle-hit cost: the freshness sentinel check
# fires BEFORE ``cat`` reads stdin, so a within-window invocation exits
# in ~10ms without paying for jq + python3 startup.

set -euo pipefail

# PATH bootstrap so python3/jq/cortex are reachable on minimal-PATH
# (macOS Dock launchd) sessions — same shape as
# claude/hooks/cortex-session-start-path-bootstrap.sh:29.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:${PATH:-}"

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command"
SENTINEL="$STATE_DIR/last-version-check"
THROTTLE_SECONDS=1800

# Throttle check BEFORE stdin/jq/python — sentinel mtime within window
# means we already probed recently. Cross-platform mtime via BSD
# (``stat -f %m``) or GNU (``stat -c %Y``).
if [[ -f "$SENTINEL" ]]; then
  mtime=$(stat -f %m "$SENTINEL" 2>/dev/null || stat -c %Y "$SENTINEL" 2>/dev/null || echo 0)
  now=$(date +%s)
  if (( now - mtime < THROTTLE_SECONDS )); then
    exit 0
  fi
fi

# Throttle-miss path: parse stdin to find the cwd Claude was launched
# in, then hand off to Python for the rest.
INPUT=$(cat)
HOOK_CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)
[[ -n "${HOOK_CWD:-}" ]] || HOOK_CWD="$(pwd)"

# ``CLAUDE_PLUGIN_ROOT`` is exported by Claude Code when a hook fires
# from a plugin context. If absent (manual invocation, test
# environment), silent skip.
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
[[ -n "$PLUGIN_ROOT" ]] || exit 0

export HOOK_CWD HOOK_STATE_DIR="$STATE_DIR" HOOK_SENTINEL="$SENTINEL" HOOK_PLUGIN_ROOT="$PLUGIN_ROOT"

# Disable errexit around the heredoc so a non-zero python3 exit cannot
# crash the hook (visibility-only contract). The heredoc-start marker
# MUST be the last non-newline content on the next line — the body
# extractor used by Task 3 (b)'s verification slices on the first
# occurrence of that marker and assumes the next character is a newline.
set +e
python3 - <<'PY'
import json
import os
import pathlib
import re
import subprocess
import sys


def emit_context(text):
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": text,
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


def touch_sentinel(state_dir, sentinel):
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        sentinel.touch()
    except OSError:
        pass


def parse_cli_pin(server_py):
    """Regex-match the ``CLI_PIN = ("vX.Y.Z", "M.m")`` literal in
    server.py. Format-tolerant — anchors on the same shape as
    ``bin/cortex-rewrite-cli-pin``'s ``CLI_PIN_RE``."""
    try:
        src = server_py.read_text()
    except OSError:
        return None
    m = re.search(
        r"^CLI_PIN\s*=\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,?\s*\)",
        src,
        re.MULTILINE,
    )
    if not m:
        return None
    return m.group(1), m.group(2)


def skip_predicate_fires(cwd):
    """Mirror server._evaluate_skip_predicates: dev-mode, dirty-tree,
    non-main branch. git failures are conservative skips."""
    if os.environ.get("CORTEX_DEV_MODE") == "1":
        return True
    try:
        status = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return True
    if status.returncode != 0 or status.stdout.strip():
        return True
    try:
        branch = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return True
    if branch.returncode != 0 or branch.stdout.strip() != "main":
        return True
    return False


def probe_installed():
    """Probe ``cortex --print-root --format json`` with 10s timeout.
    Returns parsed JSON payload or None on any failure."""
    try:
        result = subprocess.run(
            ["cortex", "--print-root", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return None


def version_tuple(v):
    """Convert ``vX.Y.Z`` (or ``X.Y.Z``) to an int tuple. PEP 440 prefix
    split only — no ``packaging`` import. Non-numeric segments truncate."""
    v = (v or "").lstrip("v")
    parts = []
    for seg in v.split("."):
        try:
            parts.append(int(seg))
        except ValueError:
            break
    return tuple(parts)


def schema_major(s):
    try:
        return int((s or "").split(".")[0])
    except (ValueError, IndexError):
        return None


try:
    cwd = os.environ.get("HOOK_CWD", "")
    state_dir_str = os.environ.get("HOOK_STATE_DIR", "")
    sentinel_str = os.environ.get("HOOK_SENTINEL", "")
    plugin_root_str = os.environ.get("HOOK_PLUGIN_ROOT", "")
    if not (cwd and state_dir_str and sentinel_str and plugin_root_str):
        sys.exit(0)

    STATE_DIR = pathlib.Path(state_dir_str)
    SENTINEL = pathlib.Path(sentinel_str)
    PLUGIN_ROOT = pathlib.Path(plugin_root_str)
    SERVER_PATH = PLUGIN_ROOT / "server.py"

    # Skip predicates fire BEFORE sentinel write so next session retries
    # if the operator switches off dev-mode or back onto main.
    if skip_predicate_fires(cwd):
        sys.exit(0)

    pin = parse_cli_pin(SERVER_PATH)
    if pin is None:
        # server.py missing or CLI_PIN refactored — do NOT write
        # sentinel; next session retries when fixed upstream.
        sys.exit(0)
    expected_tag, expected_schema = pin

    payload = probe_installed()
    # Sentinel write happens once the probe completes (success or
    # failure) so a broken cortex install doesn't hot-loop the probe on
    # every SessionStart. Per-session retry comes after the 1800s window.
    touch_sentinel(STATE_DIR, SENTINEL)
    if payload is None:
        sys.exit(0)

    installed_version = payload.get("version") or ""
    installed_schema = payload.get("schema_version") or ""
    cortex_root = payload.get("root") or ""

    # Schema-floor branch: wheel-only (no .git at cortex_root). Major
    # mismatch is hard-rejected per the CLI_PIN schema contract.
    expected_major = schema_major(expected_schema)
    installed_major = schema_major(installed_schema)
    is_wheel = bool(cortex_root) and not (pathlib.Path(cortex_root) / ".git").is_dir()
    if (
        is_wheel
        and expected_major is not None
        and installed_major is not None
        and installed_major < expected_major
    ):
        emit_context(
            "Schema-floor violation: installed CLI "
            "schema_version={installed_schema}, required={expected_schema}; "
            "run 'uv tool install --reinstall --refresh-package cortex-command "
            "git+https://github.com/charleshall888/cortex-command.git"
            "@{expected_tag}' to upgrade".format(
                installed_schema=installed_schema,
                expected_schema=expected_schema,
                expected_tag=expected_tag,
            )
        )
        sys.exit(0)

    # Drift branch: strict less-than on parsed version tuple. Empty
    # tuples (unparseable version strings) short-circuit to no-drift.
    expected_v = version_tuple(expected_tag)
    installed_v = version_tuple(installed_version)
    if installed_v and expected_v and installed_v < expected_v:
        installed_disp = installed_version.lstrip("v")
        expected_disp = expected_tag.lstrip("v")
        emit_context(
            "cortex CLI is drifted: installed v{installed}, "
            "expected v{expected}. The next MCP tool call will reinstall "
            "automatically. Bash 'cortex …' calls before then may fail "
            "with 'No such command' or import errors; if so, run "
            "'uv tool install --reinstall --refresh-package cortex-command "
            "git+https://github.com/charleshall888/cortex-command.git"
            "@v{expected}' manually.".format(
                installed=installed_disp,
                expected=expected_disp,
            )
        )
        sys.exit(0)

    sys.exit(0)
except Exception:
    sys.exit(0)
PY
set -e

exit 0
