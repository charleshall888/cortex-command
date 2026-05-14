#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "mcp>=1.27,<2",
#     "packaging>=24,<26",
#     "pydantic>=2.5,<3",
# ]
# ///
"""Plugin-bundled cortex-overnight MCP server (PEP 723 single-file).

This module is the canonical location for the cortex MCP server. It
intentionally has zero ``cortex_command.*`` imports (R1 architectural
invariant): the only contract with the cortex CLI is
``subprocess.run(cortex_argv) + versioned JSON``.

Task 6 wires the five overnight tool handlers (``overnight_start_run``,
``overnight_status``, ``overnight_logs``, ``overnight_cancel``,
``overnight_list_sessions``) on top of the Task 5 skeleton. Each tool:

1. Builds an argv invoking ``cortex <verb> --format json``.
2. Calls ``subprocess.run(..., capture_output=True, text=True,
   timeout=N)`` with no ``check=True`` (per spec Technical
   Constraints).
3. Parses stdout JSON.
4. Enforces the schema-version floor: payloads whose major component
   differs from ``MCP_REQUIRED_CLI_VERSION``'s major are rejected;
   minor-greater is accepted, and unknown fields are silently dropped
   by Pydantic's ``extra="ignore"``.

The discovery cache (``cortex --print-root`` payload) is populated on
first tool call and never expires for the MCP-server lifetime. It is
*separate* from the R8 update-check cache (Task 7).
"""

from __future__ import annotations

import datetime as _datetime
import errno
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Literal, Optional


def _enforce_plugin_root() -> None:
    """R17 — confused-deputy mitigation.

    Verify, at startup, that this file lives under the resolved
    ``${CLAUDE_PLUGIN_ROOT}``. On mismatch (or absent env var), refuse
    to start: print ``"plugin path mismatch"`` to stderr and exit
    non-zero. This prevents an attacker who can override
    ``CLAUDE_PLUGIN_ROOT`` from pointing uv run at arbitrary Python.
    """

    plugin_root_env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not plugin_root_env:
        print(
            "plugin path mismatch (CLAUDE_PLUGIN_ROOT not set)",
            file=sys.stderr,
        )
        sys.exit(1)

    file_path = Path(__file__).resolve()
    plugin_root = Path(plugin_root_env).resolve()

    if not file_path.is_relative_to(plugin_root):
        print(
            f"plugin path mismatch (file={file_path} root={plugin_root})",
            file=sys.stderr,
        )
        sys.exit(1)


# Fail-fast: enforce the confused-deputy invariant at import time, before
# any MCP machinery is instantiated. Tests rely on this firing during a
# bare ``uv run --script server.py`` invocation.
_enforce_plugin_root()


# Import MCP machinery lazily so the confused-deputy check above runs
# first (and so static imports of this file do not require ``mcp`` to
# be present, which matters for test discovery on machines where the
# PEP 723 deps haven't been resolved yet).
from mcp.server.fastmcp import FastMCP  # noqa: E402
from pydantic import BaseModel, ConfigDict, Field  # noqa: E402


# ---------------------------------------------------------------------------
# Schema-version constants (R15)
# ---------------------------------------------------------------------------

#: Plugin/CLI version coupling (R5a). A two-element tuple binding the
#: git tag this plugin pins for CLI auto-install (element 0) and the
#: print-root JSON envelope schema major it requires (element 1). The
#: CLI does NOT consume this constant — the plugin tree is outside the
#: CLI's import path. Updates flow plugin -> CLI: bumping ``CLI_PIN``
#: and shipping a new plugin version drives the next MCP tool call to
#: reinstall the matching CLI tag via R4's ``_ensure_cortex_installed``.
CLI_PIN = ("v2.0.0", "2.0")

#: Schema floor the MCP refuses to operate below. ``M.m`` per Terraform's
#: ``format_version`` precedent: a *major* mismatch is hard-rejected
#: (breaking change); *minor* drift is silently tolerated for
#: forward-compat (Pydantic's ``extra="ignore"`` drops unknown fields).
#: Derived from :data:`CLI_PIN` (R5a) so a single bump propagates.
MCP_REQUIRED_CLI_VERSION = CLI_PIN[1]


class SchemaVersionError(RuntimeError):
    """Raised when a CLI payload's major version differs from the floor.

    The MCP runtime catches this and surfaces a structured error to the
    Claude Code client; the user's tool call fails (rather than
    silently consuming an incompatible payload).
    """


def _check_version(payload: dict, *, verb: str) -> None:
    """Enforce the schema-floor on a CLI JSON payload (R15).

    Raises :class:`SchemaVersionError` when:

    * ``payload['schema_version']`` is missing (with the documented
      exception for the legacy ``{"active": false}`` no-active-session
      shape from ``cortex overnight status --format json``, which
      pre-dates the versioned envelope).
    * ``payload['schema_version']``'s major component differs from
      ``MCP_REQUIRED_CLI_VERSION``'s major.

    Minor-greater is accepted; the payload's unknown fields are dropped
    by Pydantic's ``model_config = ConfigDict(extra="ignore")`` on each
    output model.
    """

    version = (
        payload.get("schema_version") if isinstance(payload, dict) else None
    )
    if version is None:
        # Legacy unversioned shape: ``cortex overnight status --format
        # json`` emits ``{"active": false}`` (and the active branch is
        # also unversioned in the current contract). The mcp-contract
        # doc commits to accepting these specific legacy shapes.
        if verb == "overnight_status":
            global _STATUS_LEGACY_VERSION_WARNED
            if not _STATUS_LEGACY_VERSION_WARNED:
                print(
                    "cortex MCP: accepting unversioned `cortex overnight "
                    "status` payload (legacy shape)",
                    file=sys.stderr,
                )
                _STATUS_LEGACY_VERSION_WARNED = True
            return
        raise SchemaVersionError(
            f"{verb}: missing 'schema_version' field in CLI JSON payload"
        )

    try:
        major = int(str(version).split(".")[0])
    except (ValueError, TypeError, AttributeError) as exc:
        raise SchemaVersionError(
            f"{verb}: malformed schema_version {version!r}: {exc}"
        ) from exc

    try:
        required_major = int(MCP_REQUIRED_CLI_VERSION.split(".")[0])
    except (ValueError, TypeError, AttributeError) as exc:
        raise SchemaVersionError(
            f"{verb}: malformed MCP_REQUIRED_CLI_VERSION "
            f"{MCP_REQUIRED_CLI_VERSION!r}: {exc}"
        ) from exc

    if major != required_major:
        raise SchemaVersionError(
            f"{verb}: major-version mismatch — CLI emitted {version!r}, "
            f"MCP requires major={required_major} "
            f"(MCP_REQUIRED_CLI_VERSION={MCP_REQUIRED_CLI_VERSION!r}); "
            f"downgrade plugin OR run `uv tool install --reinstall "
            f"git+https://github.com/charleshall888/cortex-command.git"
            f"@{CLI_PIN[0]}` to upgrade cortex CLI to the matching version."
        )


# Latch so we only emit the unversioned-status warning once per server
# lifetime (avoids stderr spam on tight polling loops).
_STATUS_LEGACY_VERSION_WARNED: bool = False


# ---------------------------------------------------------------------------
# Cortex CLI presence (S1 + S5)
# ---------------------------------------------------------------------------

#: Canonical user-facing error string emitted when the ``cortex`` CLI is
#: not discoverable on PATH. Shared by the module-import-time stderr
#: warning (S5) and the tool-body string-return path (S1) so the message
#: is byte-equal across surfaces. Per the Anthropic MCP Python reference
#: pattern, tool bodies return this verbatim (FastMCP wraps it into
#: ``CallToolResult(isError=True, content=[TextContent(text=...)])``).
_CORTEX_CLI_MISSING_ERROR = (
    "Error: cortex CLI not found on PATH. Install: see "
    "https://github.com/charleshall888/cortex-command#install "
    "(or `uv tool install -e .` from a local checkout for dev mode)."
)


class CortexCliMissing(OSError):
    """Internal disambiguator for ``FileNotFoundError`` on ``cortex`` argv0.

    Subclasses :class:`OSError` so existing handlers that catch
    ``OSError`` (e.g. ``_maybe_check_upstream``, ``_maybe_run_upgrade``)
    continue to work unchanged. Surfaces only at retry-site catch
    handlers (Task 3) — never raised through to the MCP framework, since
    tool bodies return :data:`_CORTEX_CLI_MISSING_ERROR` as a string and
    rely on FastMCP's documented error wrapping for the wire envelope.
    """


# Module-import-time best-effort visibility check (S5). If ``cortex`` is
# not on PATH right now, log the canonical missing-CLI message to stderr
# so operators see the issue at server start. We do *not* raise — the
# CLI may appear on PATH later in the process lifetime, and tool bodies
# will surface the same error string at call time if it remains absent.
if shutil.which("cortex") is None:
    print(
        f"cortex MCP: {_CORTEX_CLI_MISSING_ERROR}",
        file=sys.stderr,
    )


# R4g — startup probe for ``uv``. The auto-install hook (R4) shells out
# to ``uv tool install --reinstall git+...@<tag>``; without ``uv`` on
# PATH that hook cannot run, and the most common failure mode on macOS
# is the GUI-app + Homebrew + ``~/.zshrc`` misconfiguration: Homebrew
# adds ``uv`` to PATH from ``~/.zshrc``, which is only sourced for
# interactive login shells. A Claude Code GUI-app launch inherits the
# launchd environment, which does not load ``~/.zshrc``. The fix is to
# move the Homebrew PATH export into ``~/.zshenv`` (sourced by every
# zsh invocation, including non-interactive subshells spawned by GUI
# apps). Refuse to start so the operator sees the structured error
# rather than a confusing R4 install failure on first tool call.
if shutil.which("uv") is None:
    sys.stderr.write(
        "cortex MCP: `uv` not found on PATH. The cortex plugin requires "
        "`uv` to auto-install the cortex CLI on first tool call. On macOS, "
        "if you launched Claude Code as a GUI app and installed `uv` via "
        "Homebrew, the GUI launchd environment does not source `~/.zshrc` "
        "— move the Homebrew PATH export into `~/.zshenv` (sourced by "
        "every zsh invocation, including non-interactive subshells "
        "spawned by GUI apps), then restart Claude Code. "
        "See https://docs.astral.sh/uv/ for install options.\n"
    )
    sys.exit(2)


# ---------------------------------------------------------------------------
# Discovery cache (separate from R8's update-check cache; never expires)
# ---------------------------------------------------------------------------

#: Cache of the ``cortex --print-root`` payload, populated on first
#: access. ``None`` indicates not-yet-fetched. R8 (Task 7) reads
#: ``head_sha`` and ``remote_url`` from this cache.
#:
#: Concurrency: FastMCP's stdio transport runs tool handlers on a single
#: asyncio event loop, and ``_get_cortex_root_payload`` performs a sync
#: ``subprocess.run`` with no ``await`` between the cache-read and
#: cache-write. The event loop therefore serializes the check-then-act,
#: so no lock is required today. Any future move to ``asyncio.to_thread``
#: or thread-pool dispatch will require a lock around the
#: check-then-act in ``_get_cortex_root_payload`` (and the cache-clear
#: in the retry handler).
_CORTEX_ROOT_CACHE: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# R4 — first-install hook (Task 9)
# ---------------------------------------------------------------------------

#: Wait budget (seconds) for acquiring the cross-process first-install
#: flock at ``${XDG_STATE_HOME}/cortex-command/install.lock``. Spec R4c.
_INSTALL_FLOCK_WAIT_BUDGET_SECONDS = 60.0

#: Polling interval (seconds) used by the non-blocking install-flock
#: acquisition loop. Same trade-off as the R11 update flock.
_INSTALL_FLOCK_POLL_INTERVAL_SECONDS = 0.1

#: Timeout (seconds) for ``uv tool install --reinstall git+<url>@<tag>``.
#: A network-bound first install of the wheel; budget mirrors uv's own
#: default install behaviour for a fresh resolve + download.
_INSTALL_SUBPROCESS_TIMEOUT_SECONDS = 300.0

#: Timeout (seconds) for the post-install ``cortex --print-root --format
#: json`` verification probe. Bounded by argparse + a single state-file
#: read; 10s is generous.
_INSTALL_VERIFY_TIMEOUT_SECONDS = 10.0

#: Window (seconds) during which a recent ``install-failed.<ts>`` sentinel
#: short-circuits a re-attempt. Spec R4d: callers within 60s of a prior
#: failure surface the previous error rather than retrying on partial
#: state. After the window expires the sentinel is ignored and a fresh
#: install attempt is made.
_INSTALL_SENTINEL_WINDOW_SECONDS = 60.0


class CortexInstallFailed(RuntimeError):
    """Raised when first-install fails (subprocess error or verification).

    Carries a structured-failure context the MCP runtime surfaces to the
    Claude Code client. The hook returns silently on success; this
    exception is the only failure surface (apart from the hook being
    skipped via ``CORTEX_AUTO_INSTALL=0``, which falls through to the
    notice-only path that ``_CORTEX_CLI_MISSING_ERROR`` already covers).
    """


def _install_state_dir() -> Path:
    """Return ``${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command``.

    Resolved fresh on each call so tests can redirect ``HOME`` /
    ``XDG_STATE_HOME`` via ``monkeypatch`` (mirrors
    :func:`_last_error_log_path`).
    """
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        base = Path(xdg_state)
    else:
        base = Path(os.environ.get("HOME", str(Path.home()))) / ".local" / "state"
    return base / "cortex-command"


def _install_lock_path() -> Path:
    """Return the install-lock path under XDG state home (R4c)."""
    return _install_state_dir() / "install.lock"


def _recent_install_failed_sentinel() -> Optional[Path]:
    """Return a sentinel path if any ``install-failed.*`` is fresh.

    "Fresh" means the file's mtime is within
    :data:`_INSTALL_SENTINEL_WINDOW_SECONDS` of now (R4d). Returns the
    most recent qualifying sentinel so the caller can surface its
    context. Returns ``None`` when the state dir is missing or no
    qualifying sentinel exists.
    """
    state_dir = _install_state_dir()
    if not state_dir.is_dir():
        return None
    cutoff = time.time() - _INSTALL_SENTINEL_WINDOW_SECONDS
    candidates: list[tuple[float, Path]] = []
    try:
        for entry in state_dir.iterdir():
            if not entry.name.startswith("install-failed."):
                continue
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue
            if mtime >= cutoff:
                candidates.append((mtime, entry))
    except OSError:
        return None
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _write_install_failed_sentinel(error: str) -> Path:
    """Create ``${XDG_STATE_HOME}/cortex-command/install-failed.<ts>``.

    The sentinel body is the failure summary so a subsequent reader can
    surface the prior failure context (R4d). Best-effort: directory
    creation and write failures are swallowed and the would-be path is
    still returned, so the caller can include it in the user-facing
    error even when the on-disk write itself failed.
    """
    state_dir = _install_state_dir()
    sentinel_path = state_dir / f"install-failed.{int(time.time())}"
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        sentinel_path.write_text(error, encoding="utf-8")
    except OSError as exc:
        print(
            f"cortex MCP: failed to write install-failed sentinel "
            f"({exc.__class__.__name__}: {exc}); continuing",
            file=sys.stderr,
        )
    return sentinel_path


def _acquire_install_flock(lock_path: Path) -> Optional[int]:
    """Acquire ``fcntl.flock(LOCK_EX)`` on ``lock_path`` with a 60s budget.

    Pattern derived from R11 / ``cortex_command/init/settings_merge.py``:
    non-blocking poll so the wait budget is enforced cooperatively
    without depending on signal delivery (incompatible with the FastMCP
    runtime's signal handlers).

    Returns the open file descriptor on success. Returns ``None`` on
    budget expiry; the caller raises :class:`CortexInstallFailed` after
    logging the timeout.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    deadline = time.monotonic() + _INSTALL_FLOCK_WAIT_BUDGET_SECONDS
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except OSError as exc:
                if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                    os.close(fd)
                    raise
            if time.monotonic() >= deadline:
                os.close(fd)
                return None
            time.sleep(_INSTALL_FLOCK_POLL_INTERVAL_SECONDS)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _release_install_flock(fd: int) -> None:
    """Release the install flock acquired by :func:`_acquire_install_flock`."""
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _plugin_pid_verifier(pid_data: dict) -> bool:
    """Stdlib-only pid verifier for the plugin's PEP 723 venv (no psutil).

    The plugin's venv intentionally excludes psutil to keep the
    surface minimal; the vendored
    ``install_guard.check_in_flight_install_core`` therefore receives
    this verifier callable as a parameter rather than importing
    ``cortex_command.overnight.ipc``. Best-effort verification:

    * ``magic == "cortex-runner-v1"`` and ``schema_version`` is a
      positive int (matches the CLI-side schema floor).
    * ``os.kill(pid, 0)`` succeeds (process exists; treats EPERM as
      alive — kernel rejected the signal but the pid is bound).
    * On macOS/Linux a ``ps -p <pid> -o lstart=`` probe roughly
      matches the recorded ``start_time`` (within a generous tolerance
      to absorb recycled-pid risk).

    Returns ``False`` on any mismatch, missing-process, or probe
    failure — the conservative direction is to treat unverifiable pids
    as stale, allowing the install to proceed.
    """
    if not isinstance(pid_data, dict):
        return False

    if pid_data.get("magic") != "cortex-runner-v1":
        return False

    schema_version = pid_data.get("schema_version")
    if not isinstance(schema_version, int) or schema_version < 1:
        return False

    pid = pid_data.get("pid")
    if not isinstance(pid, int):
        return False

    # Step 1: existence check via signal 0. EPERM = process exists but
    # we lack permission to signal it (treat as alive). ESRCH = no such
    # process (definitively dead).
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists, owned by another user. Treat as alive — the
        # in-flight guard's purpose is to block clobbering a live
        # session, and we should err on the safe side.
        return True
    except OSError:
        return False

    # Step 2: optional recycled-pid mitigation via ``ps -p <pid>
    # -o lstart=``. Skip silently on probe failure (the os.kill check
    # already established existence, so we lean toward "alive" rather
    # than spuriously unblocking a real runner).
    start_time_str = pid_data.get("start_time")
    if not isinstance(start_time_str, str):
        return True

    try:
        proc = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (subprocess.TimeoutExpired, OSError):
        return True

    if proc.returncode != 0 or not proc.stdout.strip():
        # ps disagrees with os.kill — treat as stale (recycled pid).
        return False

    # The lstart format is "Day Mon DD HH:MM:SS YYYY"; we don't need
    # bit-exact parity with psutil's create_time(). The existence-plus-
    # ps-agreement signal is sufficient for the plugin's coarse
    # liveness check; the CLI-side path retains the precise
    # ``psutil.Process(pid).create_time()`` comparison via
    # ``ipc.verify_runner_pid``.
    return True


def _plugin_active_session_path() -> Path:
    """Return the active-session pointer path for the plugin venv.

    Mirrors ``cortex_command.install_guard._ACTIVE_SESSION_PATH`` —
    duplicated by design so the plugin's PEP 723 venv does not import
    ``cortex_command.*`` (R1 architectural invariant).
    """
    return (
        Path.home()
        / ".local"
        / "share"
        / "overnight-sessions"
        / "active-session.json"
    )


def _resolve_installed_cortex_path() -> Optional[str]:
    """Return the absolute path of the installed ``cortex`` console script.

    Strategy: shell out to ``uv tool list --show-paths`` and parse the
    ``- cortex (/abs/path)`` line under the ``cortex-command`` package
    block. This closes the PATH-poisoning surface flagged in research
    §H/§I: the post-install verification probe targets the absolute
    path uv just wrote, not whichever ``cortex`` happens to be first on
    PATH after the reinstall.

    Returns ``None`` on parse/probe failure; callers fall back to a
    failure-emitting NDJSON record rather than silently regressing to
    bare-PATH ``cortex``.
    """
    try:
        result = subprocess.run(
            ["uv", "tool", "list", "--show-paths"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    if result.returncode != 0:
        return None

    # Match lines like: ``- cortex (/Users/.../bin/cortex)``. The first
    # match is the cortex console script (other entries are
    # ``cortex-*`` siblings — we anchor the script name with a literal
    # space-paren to disambiguate).
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith("- cortex ("):
            continue
        # Strip ``- cortex (`` prefix and the trailing ``)``.
        path_str = line[len("- cortex (") :]
        if not path_str.endswith(")"):
            continue
        return path_str[:-1]
    return None


def _run_install_and_verify(*, stage: str) -> None:
    """Run ``uv tool install --reinstall`` + verification probe.

    Shared body for both the first-install branch (``stage=
    "first_install"``) and the version-mismatch branches (``stage=
    "version_mismatch_reinstall"`` and
    ``stage="version_mismatch_reinstall_parse_failure"``). All NDJSON
    records emitted from this helper carry the supplied ``stage`` so
    integration tests can disambiguate which branch fired.

    Acquires the install flock, re-verifies CLI presence under the
    lock (skip on contending process), runs ``uv tool install``, then
    verifies via the absolute-path-pinned ``cortex --print-root
    --format json`` (closes the PATH-poisoning surface).
    """
    lock_path = _install_lock_path()
    fd = _acquire_install_flock(lock_path)
    if fd is None:
        error = (
            f"timed out waiting "
            f"{int(_INSTALL_FLOCK_WAIT_BUDGET_SECONDS)}s for "
            f"{lock_path}"
        )
        _append_error_ndjson(
            stage=stage,
            error=error,
            context={
                "cli_pin": CLI_PIN[0],
                "exit_code": -1,
                "phase": "flock_timeout",
            },
        )
        raise CortexInstallFailed(
            f"cortex auto-install: {error}; another MCP session is "
            f"holding the install lock."
        )

    try:
        # Re-verify under the lock: a contending process may have just
        # finished installing matching version. For first-install,
        # bare ``which`` suffices. For version-mismatch we re-enter
        # the outer loop only by retry; this helper does not loop.
        if stage == "first_install" and shutil.which("cortex") is not None:
            return

        install_argv = [
            "uv",
            "tool",
            "install",
            "--reinstall",
            f"git+https://github.com/charleshall888/cortex-command.git"
            f"@{CLI_PIN[0]}",
        ]
        try:
            install_result = subprocess.run(
                install_argv,
                timeout=_INSTALL_SUBPROCESS_TIMEOUT_SECONDS,
                capture_output=True,
                text=True,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            error = f"{exc.__class__.__name__}: {exc}"
            sentinel_path = _write_install_failed_sentinel(error)
            _append_error_ndjson(
                stage=stage,
                error=error,
                context={
                    "cli_pin": CLI_PIN[0],
                    "exit_code": -1,
                    "phase": "uv_tool_install",
                    "sentinel": str(sentinel_path),
                },
            )
            raise CortexInstallFailed(
                f"cortex auto-install (`uv tool install --reinstall "
                f"git+...@{CLI_PIN[0]}`) failed: {error}"
            ) from exc

        if install_result.returncode != 0:
            error = (
                f"uv tool install exit={install_result.returncode}; "
                f"stderr={install_result.stderr!r}"
            )
            sentinel_path = _write_install_failed_sentinel(error)
            _append_error_ndjson(
                stage=stage,
                error=error,
                context={
                    "cli_pin": CLI_PIN[0],
                    "exit_code": install_result.returncode,
                    "phase": "uv_tool_install",
                    "sentinel": str(sentinel_path),
                },
            )
            raise CortexInstallFailed(
                f"cortex auto-install (`uv tool install --reinstall "
                f"git+...@{CLI_PIN[0]}`) failed: {error}"
            )

        # Resolve the absolute path of the just-installed cortex
        # console script. Falls back to a failure NDJSON record rather
        # than regressing to bare-PATH ``cortex`` (closes the
        # PATH-poisoning surface flagged in research §H/§I).
        cortex_abs_path = _resolve_installed_cortex_path()
        if cortex_abs_path is None:
            error = (
                "post-install verification: could not resolve absolute "
                "cortex path via `uv tool list --show-paths`"
            )
            sentinel_path = _write_install_failed_sentinel(error)
            _append_error_ndjson(
                stage=stage,
                error=error,
                context={
                    "cli_pin": CLI_PIN[0],
                    "exit_code": -1,
                    "phase": "resolve_absolute_path",
                    "sentinel": str(sentinel_path),
                },
            )
            raise CortexInstallFailed(error)

        # Post-install verification — `cortex --print-root --format json`,
        # invoked via the absolute path (NOT bare PATH).
        try:
            verify_result = subprocess.run(
                [cortex_abs_path, "--print-root", "--format", "json"],
                timeout=_INSTALL_VERIFY_TIMEOUT_SECONDS,
                capture_output=True,
                text=True,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            error = (
                f"post-install verification "
                f"(`{cortex_abs_path} --print-root --format json`) "
                f"raised: {exc.__class__.__name__}: {exc}"
            )
            sentinel_path = _write_install_failed_sentinel(error)
            _append_error_ndjson(
                stage=stage,
                error=error,
                context={
                    "cli_pin": CLI_PIN[0],
                    "exit_code": -1,
                    "phase": "verify_print_root",
                    "sentinel": str(sentinel_path),
                },
            )
            raise CortexInstallFailed(error) from exc

        if verify_result.returncode != 0:
            error = (
                f"post-install verification "
                f"(`{cortex_abs_path} --print-root --format json`) "
                f"exit={verify_result.returncode}; "
                f"stderr={verify_result.stderr!r}"
            )
            sentinel_path = _write_install_failed_sentinel(error)
            _append_error_ndjson(
                stage=stage,
                error=error,
                context={
                    "cli_pin": CLI_PIN[0],
                    "exit_code": verify_result.returncode,
                    "phase": "verify_print_root",
                    "sentinel": str(sentinel_path),
                },
            )
            raise CortexInstallFailed(error)

        try:
            json.loads(verify_result.stdout)
        except json.JSONDecodeError as exc:
            error = (
                f"post-install verification "
                f"(`{cortex_abs_path} --print-root --format json`) "
                f"emitted unparseable JSON: {exc}; "
                f"stdout={verify_result.stdout!r}"
            )
            sentinel_path = _write_install_failed_sentinel(error)
            _append_error_ndjson(
                stage=stage,
                error=error,
                context={
                    "cli_pin": CLI_PIN[0],
                    "exit_code": verify_result.returncode,
                    "phase": "verify_print_root_parse",
                    "sentinel": str(sentinel_path),
                },
            )
            raise CortexInstallFailed(error) from exc
    finally:
        _release_install_flock(fd)


def _ensure_cortex_installed() -> None:
    """R4 — auto-install/upgrade the ``cortex`` CLI on first MCP tool call.

    Two branches:

    * **First install** (R4) — ``shutil.which("cortex") is None``:
      acquire the install flock, run ``uv tool install --reinstall
      git+<url>@CLI_PIN[0]``, and verify via the absolute-path-pinned
      ``cortex --print-root --format json``. NDJSON records carry
      ``stage="first_install"``.
    * **Version-mismatch reinstall** (R9/R10/R12/R15/R16, Task 11) —
      ``cortex`` is on PATH: invoke ``cortex --print-root --format
      json``, parse ``payload["version"]`` (the package version under
      Phase 1's envelope migration), compare to ``CLI_PIN[0]`` via
      ``packaging.version.Version`` and reinstall on mismatch.

      Before reinstalling, the vendored
      ``install_guard.check_in_flight_install_core`` is consulted; an
      active overnight session aborts the reinstall with an NDJSON
      record carrying
      ``stage="version_mismatch_blocked_by_inflight_session"``. The
      session completes and the next tool call retries.

      On ``packaging.version.InvalidVersion`` the branch still
      reinstalls (defensive fallback), but the NDJSON record carries
      ``stage="version_mismatch_reinstall_parse_failure"`` instead of
      ``stage="version_mismatch_reinstall"`` so integration tests can
      disambiguate legitimate-mismatch from parse-failure-fallback.

    * If ``CORTEX_AUTO_INSTALL=0``, fall through to the notice-only
      path (return silently; the existing missing-CLI surface in
      :data:`_CORTEX_CLI_MISSING_ERROR` handles user messaging).
    * If a recent ``install-failed.*`` sentinel exists (within
      :data:`_INSTALL_SENTINEL_WINDOW_SECONDS`), raise
      :class:`CortexInstallFailed` with the prior failure context
      instead of retrying on partial state.

    Wired into :func:`_resolve_cortex_argv` so every cortex subprocess
    invocation triggers the hook implicitly (zero per-handler call-site
    additions).
    """
    # Lazy import — ``packaging`` is declared in the PEP 723 dependency
    # block. Deferring keeps the import cost off the hot path when the
    # hook returns immediately on the no-op success branch.
    from packaging.version import InvalidVersion, Version

    if os.environ.get("CORTEX_AUTO_INSTALL") == "0":
        # R19 notice-only path: the missing-CLI error string already
        # documents the user-facing remediation. Returning silently
        # lets the downstream subprocess raise FileNotFoundError, which
        # the existing CortexCliMissing handlers translate into the
        # canonical user-facing error.
        return

    sentinel = _recent_install_failed_sentinel()
    if sentinel is not None:
        try:
            prior = sentinel.read_text(encoding="utf-8").strip()
        except OSError:
            prior = "<sentinel unreadable>"
        raise CortexInstallFailed(
            f"cortex auto-install previously failed (sentinel "
            f"{sentinel.name} written within the last "
            f"{int(_INSTALL_SENTINEL_WINDOW_SECONDS)}s); "
            f"not retrying. Prior failure: {prior}. "
            f"Run `uv tool install --reinstall "
            f"git+https://github.com/charleshall888/cortex-command.git"
            f"@{CLI_PIN[0]}` manually to recover."
        )

    # ------------------------------------------------------------------
    # Branch A — first install (cortex absent from PATH)
    # ------------------------------------------------------------------
    if shutil.which("cortex") is None:
        _run_install_and_verify(stage="first_install")
        return

    # ------------------------------------------------------------------
    # Branch B — version-comparison reinstall (Task 11 / R9, R12, R16)
    # ------------------------------------------------------------------
    # ``cortex`` is on PATH; invoke ``--print-root`` and compare the
    # package version against ``CLI_PIN[0]``. Defensive: parse failure
    # falls through to a flagged-fallback reinstall so a malformed
    # payload doesn't lock the user out of upgrade-on-mismatch.
    try:
        probe_result = subprocess.run(
            ["cortex", "--print-root", "--format", "json"],
            timeout=_INSTALL_VERIFY_TIMEOUT_SECONDS,
            capture_output=True,
            text=True,
        )
    except (subprocess.TimeoutExpired, OSError):
        # Probe failed — treat as "cannot determine version, proceed
        # without reinstall and let downstream subprocess raise the
        # canonical missing/broken-CLI error".
        return

    if probe_result.returncode != 0:
        return

    try:
        probe_payload = json.loads(probe_result.stdout)
    except json.JSONDecodeError:
        return

    if not isinstance(probe_payload, dict):
        return

    installed_version_str = probe_payload.get("version")
    target_version_str = CLI_PIN[0].lstrip("v")

    if not isinstance(installed_version_str, str):
        # No package-version field on the payload — pre-T4 envelope or
        # a payload shape this branch cannot make a decision on. Bail
        # out silently rather than spuriously reinstalling: the
        # schema-floor check (R13) will surface a structured error
        # downstream if the envelope is truly incompatible.
        return

    try:
        installed_version = Version(installed_version_str)
        target_version = Version(target_version_str)
    except InvalidVersion:
        # Spec R9: the version-compare branch is wrapped in
        # try/except InvalidVersion. On parse failure we still
        # reinstall (defensive — better to refresh than leave a
        # potentially-broken pin in place), but the NDJSON record
        # carries ``stage="version_mismatch_reinstall_parse_failure"``
        # so the integration test (R23 phase c) can disambiguate
        # legitimate-mismatch from parse-failure-fallback.
        parse_failure = True
    else:
        if installed_version == target_version:
            # Versions match — no reinstall needed.
            return
        parse_failure = False

    # At this point: either a legitimate version mismatch OR a parse
    # failure. Both lead to reinstall, but with distinct NDJSON stage
    # labels so tests can disambiguate.
    mismatch_stage = (
        "version_mismatch_reinstall_parse_failure"
        if parse_failure
        else "version_mismatch_reinstall"
    )

    # R12 — honor the in-flight install guard via the vendored sibling
    # before clobbering the running package.
    try:
        from install_guard import check_in_flight_install_core
    except ImportError as exc:
        # The vendored sibling is required for R12; surface the import
        # failure rather than silently bypassing the guard.
        error = (
            f"cortex auto-install: cannot import vendored "
            f"install_guard sibling: {exc}"
        )
        _append_error_ndjson(
            stage=mismatch_stage,
            error=error,
            context={
                "cli_pin": CLI_PIN[0],
                "installed_version": installed_version_str,
                "exit_code": -1,
                "phase": "import_install_guard",
            },
        )
        raise CortexInstallFailed(error) from exc

    if os.environ.get("CORTEX_ALLOW_INSTALL_DURING_RUN") != "1":
        reason = check_in_flight_install_core(
            _plugin_active_session_path(),
            pid_verifier=_plugin_pid_verifier,
        )
        if reason is not None:
            _append_error_ndjson(
                stage="version_mismatch_blocked_by_inflight_session",
                error=reason,
                context={
                    "cli_pin": CLI_PIN[0],
                    "installed_version": installed_version_str,
                    "exit_code": -1,
                    "phase": "inflight_guard",
                },
            )
            # Surface the guard's remediation message to stderr; the
            # session completes, then the next MCP tool call retries
            # the reinstall.
            print(reason, file=sys.stderr, flush=True)
            return

    # Fall through to the shared install-and-verify helper, tagged
    # with the appropriate mismatch stage. The helper preserves the
    # sentinel/flock/post-install-verification logic and pins the
    # verification probe to the absolute path.
    _run_install_and_verify(stage=mismatch_stage)


def _resolve_cortex_argv() -> list[str]:
    """Return the argv prefix that invokes the ``cortex`` CLI.

    Always uses the bare ``cortex`` console script — the plugin's MCP
    runtime is reachable only when uv has resolved the user's
    ``cortex-command`` install, so ``cortex`` is on PATH by
    construction.

    R4 wiring: every cortex subprocess invocation passes through this
    helper, so calling :func:`_ensure_cortex_installed` here makes the
    first-install hook fire transparently for all five tool handlers
    without per-handler call-site additions.
    """
    _ensure_cortex_installed()
    return ["cortex"]


def _get_cortex_root_payload() -> dict[str, Any]:
    """Return the cached ``cortex --print-root`` payload (lazy-fetched).

    Spec Technical Constraints: ``capture_output=True, text=True``,
    explicit ``timeout``, no ``check=True``. Schema-version is enforced
    before caching — a CLI emitting a future-major payload prevents
    the MCP from committing the result to the cache.
    """
    global _CORTEX_ROOT_CACHE
    if _CORTEX_ROOT_CACHE is not None:
        return _CORTEX_ROOT_CACHE

    try:
        completed = subprocess.run(
            _resolve_cortex_argv() + ["--print-root"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise CortexCliMissing(
            exc.errno, exc.strerror, *exc.args[2:]
        ) from exc
    if completed.returncode != 0:
        raise RuntimeError(
            f"`cortex --print-root` exited {completed.returncode}: "
            f"stderr={completed.stderr!r}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"`cortex --print-root` emitted unparseable JSON: {exc}; "
            f"stdout={completed.stdout!r}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"`cortex --print-root` payload is not an object: "
            f"{type(payload).__name__}"
        )

    _check_version(payload, verb="cortex_print_root")
    _CORTEX_ROOT_CACHE = payload
    return payload


# ---------------------------------------------------------------------------
# R8/R9 throttled update-check + skip-predicate state (Task 7)
# ---------------------------------------------------------------------------
#
# Wheel-install dormancy (Task 16):
# Under non-editable wheel install, R8 throttle and R10 orchestration are
# dormant; the upgrade arrow flows plugin -> CLI via R4
# (``_ensure_cortex_installed``) on schema-floor mismatch (R13). The R8
# entry point (``_maybe_check_upstream``) and the R10 orchestration paths
# (``_orchestrate_upgrade`` / ``_orchestrate_schema_floor_upgrade``)
# detect wheel install via ``not (cortex_root / ".git").is_dir()`` and
# short-circuit early so consumers do not rely on empty-string-sentinel
# side effects. The detection is a simple filesystem probe — no NDJSON
# error log, no stderr noise — because wheel install is intended
# behavior, not a fault.

#: Per-MCP-server-lifetime cache for the upstream "is upstream ahead?"
#: check. The cache key is ``(cortex_root abs path, remote_url, "HEAD")``
#: per spec R8 (multi-fork installs share neither remote_url nor
#: cortex_root). The value is a boolean: ``True`` = upstream advanced
#: past local ``head_sha``; ``False`` = local matches upstream. ``None``
#: (key absent) means "not yet checked this lifetime".
_UPDATE_CHECK_CACHE: dict[tuple[str, str, str], bool] = {}

#: Per-process latch for skip-predicate stderr messages. We log each
#: distinct skip reason exactly once per MCP-server lifetime to avoid
#: spamming stderr on tight polling loops while still surfacing the
#: condition the first time it fires.
_SKIP_REASON_LOGGED: set[str] = set()


def _invalidate_update_cache() -> None:
    """Mark the R8 update-check cache as stale.

    Clears the in-memory cache wholesale so the next tool call re-shells
    out to ``git ls-remote``. Wired at every site enumerated by spec
    Technical Constraints "Cache invalidation rules for R8's instance
    cache":

    * On any successful upgrade (R10 or R13), the cache MUST be marked
      unset so the next tool call re-checks.
    * On R11 flock-budget expiry, the cache MUST be marked unset.
    * On any update-orchestration error (R14 NDJSON-logged failure),
      the cache MUST be marked unset.

    Tasks 8 and 10 wired the success-path and flock-expiry calls;
    Task 11 wired the orchestration-error sites alongside the NDJSON
    error-log surface.
    """
    _UPDATE_CHECK_CACHE.clear()


# ---------------------------------------------------------------------------
# R14 — NDJSON error log + stderr summary (Task 11)
# ---------------------------------------------------------------------------

#: Spec R14 stage values. Validated at append time so a typo in a call
#: site surfaces during development rather than landing as a malformed
#: audit record.
_NDJSON_ERROR_STAGES = frozenset(
    {
        "git_ls_remote",
        "cortex_upgrade",
        "verification_probe",
        "flock_timeout",
        "first_install",
        # R4 version-comparison branch stages (Task 11). See
        # ``_ensure_cortex_installed``.
        "version_mismatch_reinstall",
        "version_mismatch_reinstall_parse_failure",
        "version_mismatch_blocked_by_inflight_session",
    }
)


def _last_error_log_path() -> Path:
    """Return ``${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/last-error.log``.

    Per spec R14 the log lives under XDG state home with a fallback to
    ``$HOME/.local/state``. Resolved fresh on each call so tests can
    redirect ``HOME`` / ``XDG_STATE_HOME`` via ``monkeypatch``.
    """
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        base = Path(xdg_state)
    else:
        base = Path(os.environ.get("HOME", str(Path.home()))) / ".local" / "state"
    return base / "cortex-command" / "last-error.log"


def _append_error_ndjson(
    *,
    stage: str,
    error: str,
    context: Optional[dict[str, Any]] = None,
) -> None:
    """Append a single-line JSON record to the R14 error log.

    Schema (spec R14):

    .. code-block:: json

        {"ts": "<ISO 8601>", "stage": "<stage>",
         "error": "<message>", "context": {...}}

    Defensive: the helper itself never raises out to the caller. If the
    filesystem write fails (sandbox denial, disk full, etc.), the
    failure is logged to stderr and swallowed — the audit record is
    best-effort, but a failed audit-write must never collapse the
    user's tool call.
    """
    if stage not in _NDJSON_ERROR_STAGES:
        # Defensive: an unknown stage indicates a typo at the call site.
        # Log to stderr (one-liner) and substitute "unknown" so the
        # forensic record still lands rather than getting silently
        # dropped on a strict-validation branch.
        print(
            f"cortex MCP: NDJSON error-log received unknown stage "
            f"{stage!r}; recording as 'unknown'",
            file=sys.stderr,
        )
        stage = "unknown"

    record = {
        "ts": _datetime.datetime.now(_datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "stage": stage,
        "error": error,
        "context": context or {},
    }

    log_path = _last_error_log_path()
    try:
        os.makedirs(log_path.parent, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError as exc:
        # Best-effort: failed audit-write must never break the user's
        # tool call. Surface to stderr so the issue is at least visible.
        print(
            f"cortex MCP: failed to append NDJSON error record "
            f"({exc.__class__.__name__}: {exc}); continuing",
            file=sys.stderr,
        )


def _log_skip_reason_once(reason: str) -> None:
    """Log a skip-predicate reason to stderr at most once per process."""
    if reason in _SKIP_REASON_LOGGED:
        return
    _SKIP_REASON_LOGGED.add(reason)
    print(
        f"cortex MCP: update check skipped ({reason}); "
        f"proceeding against on-disk CLI",
        file=sys.stderr,
    )


def _evaluate_skip_predicates(cortex_root: str) -> Optional[str]:
    """Return the firing skip-reason or ``None`` if the check should run.

    Predicates evaluated lazily in spec-defined order so dev-mode
    short-circuits before any subprocess shell-out (R9 ordering):

    (a) ``CORTEX_DEV_MODE=1``        — explicit dev-mode bypass.
    (b) ``git status --porcelain``   — non-empty means uncommitted changes.
    (c) ``git rev-parse --abbrev-ref HEAD != "main"`` — feature branch.

    On a firing predicate, log the reason once to stderr (per-process
    latch) and return the reason string. The caller should proceed with
    the user's tool call against the on-disk CLI without checking
    upstream.
    """

    if os.environ.get("CORTEX_DEV_MODE") == "1":
        _log_skip_reason_once("CORTEX_DEV_MODE=1")
        return "CORTEX_DEV_MODE=1"

    # Predicate (b): dirty tree.
    try:
        status = subprocess.run(
            ["git", "-C", cortex_root, "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        # If `git status` itself fails, we cannot reason about the
        # tree's cleanliness — be conservative and skip the upstream
        # check. The tool call still proceeds; the next MCP-server
        # lifetime retries.
        _log_skip_reason_once(f"git_status_failed:{exc.__class__.__name__}")
        return f"git_status_failed:{exc.__class__.__name__}"
    if status.returncode == 0 and status.stdout.strip():
        _log_skip_reason_once("dirty_tree")
        return "dirty_tree"

    # Predicate (c): non-main branch.
    try:
        branch = subprocess.run(
            ["git", "-C", cortex_root, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        _log_skip_reason_once(f"git_branch_failed:{exc.__class__.__name__}")
        return f"git_branch_failed:{exc.__class__.__name__}"
    if branch.returncode == 0 and branch.stdout.strip() != "main":
        _log_skip_reason_once(f"branch={branch.stdout.strip()!r}")
        return "non_main_branch"

    return None


def _maybe_check_upstream(
    cortex_root_payload: Optional[dict[str, Any]] = None,
) -> Optional[bool]:
    """Throttled R8 update-check entry point.

    Consulted at the start of each tool call (wired by Tasks 8/10/16).
    For Task 7 the return value is *informational only*: callers do not
    yet trigger ``cortex upgrade`` (Task 8), surface a notice (Task 16
    on the FAIL fallback path), or run the verification probe (Task 9).

    Returns:

    * ``True``  — upstream is ahead; next stage should orchestrate an
      upgrade.
    * ``False`` — upstream matches local; nothing to do.
    * ``None``  — a skip predicate fired, the discovery cache is
      missing required fields, or ``git ls-remote`` failed; the caller
      should proceed against the on-disk CLI without escalating.
    """

    if cortex_root_payload is None:
        try:
            cortex_root_payload = _get_cortex_root_payload()
        except (RuntimeError, subprocess.SubprocessError, OSError):
            # Discovery cache not yet primed and the bootstrap fails —
            # fall through; the user's tool call still proceeds and
            # the next call retries.
            return None

    cortex_root = cortex_root_payload.get("root")
    remote_url = cortex_root_payload.get("remote_url")
    head_sha = cortex_root_payload.get("head_sha")

    # R8 throttle short-circuit under wheel install (Task 16): if the
    # discovery payload's ``root`` is not a git working tree, the CLI is
    # installed via non-editable wheel and there is no upstream to
    # probe. Return None silently — no NDJSON log, no stderr noise.
    # Schema-floor escalation (R13) calling R4's ``_ensure_cortex_installed``
    # is the upgrade arrow under wheel install; R8/R9/R10 are dormant.
    # This explicit check replaces the prior empty-string-sentinel
    # branch so consumers do not rely on the half-populated-payload
    # side effect to skip the throttle.
    if not cortex_root or not (Path(str(cortex_root)) / ".git").is_dir():
        return None
    if not remote_url or not head_sha:
        # Missing remote_url / head_sha despite a present .git/ —
        # defensive: cannot construct the cache key or compare. Skip
        # silently (R3 acceptance asserts the CLI populates these for
        # a clone install, but a half-formed payload must not crash
        # tool dispatch).
        return None

    # R9 skip-predicate evaluation precedes the throttle cache; the
    # cache is intentionally NOT consulted on the skip path so a
    # subsequent un-skipped invocation still pays the ls-remote cost
    # exactly once.
    if _evaluate_skip_predicates(str(cortex_root)) is not None:
        return None

    cache_key = (str(cortex_root), str(remote_url), "HEAD")
    cached = _UPDATE_CHECK_CACHE.get(cache_key)
    if cached is not None:
        return cached

    # First call for this key in this lifetime: run `git ls-remote`.
    # Per spec Technical Constraints, `subprocess.run` is invoked
    # without ``check=True``; both the exception path (TimeoutExpired /
    # OSError — DNS failure raising before the child process exists)
    # and the non-zero-returncode path (TCP RST / TLS error / auth
    # failure — child exited 128) require separate handler branches
    # that each emit an R14 NDJSON record and invalidate the cache.
    try:
        completed = subprocess.run(
            ["git", "ls-remote", str(remote_url), "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        # Network failure / timeout: do not cache. The user's tool call
        # proceeds against the on-disk CLI (per spec Edge Cases: "git
        # ls-remote timeout / network failure: skip predicate fires
        # implicitly"). Append the failure to the R14 NDJSON log and
        # invalidate the cache so the next tool call retries.
        print(
            f"cortex auto-update failed at git_ls_remote: "
            f"{exc.__class__.__name__}; "
            f"falling through to on-disk CLI",
            file=sys.stderr,
        )
        _append_error_ndjson(
            stage="git_ls_remote",
            error=f"{exc.__class__.__name__}: {exc}",
            context={
                "remote_url": str(remote_url),
                "cortex_root": str(cortex_root),
                "exception": exc.__class__.__name__,
            },
        )
        _invalidate_update_cache()
        return None

    if completed.returncode != 0:
        # Non-zero returncode (DNS resolution success but TCP RST /
        # TLS error / auth failure) — separate handler branch from
        # TimeoutExpired per spec Technical Constraints "never
        # `check=True`; catch and handle errors explicitly". Same
        # NDJSON + invalidate behavior as the exception branch.
        print(
            f"cortex auto-update failed at git_ls_remote: "
            f"exit={completed.returncode}; "
            f"falling through to on-disk CLI",
            file=sys.stderr,
        )
        _append_error_ndjson(
            stage="git_ls_remote",
            error=(
                f"non-zero returncode {completed.returncode}; "
                f"stderr={completed.stderr!r}"
            ),
            context={
                "remote_url": str(remote_url),
                "cortex_root": str(cortex_root),
                "returncode": completed.returncode,
                "stderr": completed.stderr,
            },
        )
        _invalidate_update_cache()
        return None

    # `git ls-remote <remote> HEAD` emits one line:
    #   "<sha>\tHEAD"
    # Take the first whitespace-separated token of the first line.
    first_line = completed.stdout.splitlines()[0] if completed.stdout else ""
    remote_sha = first_line.split()[0] if first_line.strip() else ""
    if not remote_sha:
        return None

    upstream_ahead = remote_sha != str(head_sha)
    _UPDATE_CHECK_CACHE[cache_key] = upstream_ahead
    return upstream_ahead


# ---------------------------------------------------------------------------
# R10/R11 upgrade orchestration with flock + post-flock re-verify (Task 8)
# ---------------------------------------------------------------------------

#: Wait budget (seconds) for acquiring the cross-process upgrade flock at
#: ``$cortex_root/.git/cortex-update.lock``. Spec R11.
_FLOCK_WAIT_BUDGET_SECONDS = 30.0

#: Polling interval (seconds) used by the non-blocking flock acquisition
#: loop. Small enough that contention drops sub-second; large enough that
#: a contending process does not burn CPU.
_FLOCK_POLL_INTERVAL_SECONDS = 0.1

#: Timeout (seconds) for the ``cortex upgrade`` subprocess. Spec R10.
_CORTEX_UPGRADE_TIMEOUT_SECONDS = 60.0

#: Timeout (seconds) for the post-flock fresh ``git ls-remote`` re-verify.
_POST_FLOCK_LS_REMOTE_TIMEOUT_SECONDS = 5.0

#: Timeout (seconds) for the post-flock fresh ``git rev-parse HEAD``
#: re-verify.
_POST_FLOCK_REV_PARSE_TIMEOUT_SECONDS = 5.0


def _acquire_update_flock(lock_path: Path) -> Optional[int]:
    """Acquire ``fcntl.flock(LOCK_EX)`` on ``lock_path`` with a 30s budget.

    Uses non-blocking polling (``fcntl.LOCK_EX | fcntl.LOCK_NB``) so the
    wait budget is enforced cooperatively without depending on signal
    delivery (which is process-wide and incompatible with the FastMCP
    runtime's own signal handlers).

    Returns the open file descriptor on success. Returns ``None`` when
    the budget expires; the caller is responsible for the no-upgrade
    fallback path.

    Caller must release via ``fcntl.flock(fd, fcntl.LOCK_UN)`` and
    ``os.close(fd)`` in a ``try/finally`` block.

    Spec R11. Pattern derived from
    ``cortex_command/init/settings_merge.py:69-85``.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    deadline = time.monotonic() + _FLOCK_WAIT_BUDGET_SECONDS
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except OSError as exc:
                if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                    # Genuine flock failure (not contention) — surface.
                    os.close(fd)
                    raise
            if time.monotonic() >= deadline:
                os.close(fd)
                return None
            time.sleep(_FLOCK_POLL_INTERVAL_SECONDS)
    except BaseException:
        # Defensive: if anything raises before we return, ensure we don't
        # leak the fd. The success path returns above without closing.
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _release_update_flock(fd: int) -> None:
    """Release the flock acquired by :func:`_acquire_update_flock`."""
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _post_flock_remote_sha(remote_url: str) -> Optional[str]:
    """Run a *fresh* ``git ls-remote <remote-url> HEAD`` post-flock.

    Per spec Technical Constraints "R11 post-acquire HEAD re-verification
    reference point": the freshness comparison MUST use a fresh
    ``git ls-remote`` (not the captured pre-flock remote_sha) so that an
    R10/R13-triggered upgrade by another MCP that landed past the
    captured pre-flock remote_sha during the wait is correctly detected
    as up-to-date.

    Returns the remote HEAD sha on success, ``None`` on failure.
    """
    try:
        completed = subprocess.run(
            ["git", "ls-remote", str(remote_url), "HEAD"],
            capture_output=True,
            text=True,
            timeout=_POST_FLOCK_LS_REMOTE_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if completed.returncode != 0:
        return None
    first_line = completed.stdout.splitlines()[0] if completed.stdout else ""
    sha = first_line.split()[0] if first_line.strip() else ""
    return sha or None


def _post_flock_local_head(cortex_root: str) -> Optional[str]:
    """Run a *fresh* ``git -C <cortex_root> rev-parse HEAD`` post-flock."""
    try:
        completed = subprocess.run(
            ["git", "-C", cortex_root, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=_POST_FLOCK_REV_PARSE_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if completed.returncode != 0:
        return None
    sha = completed.stdout.strip()
    return sha or None


def _run_cortex_upgrade() -> subprocess.CompletedProcess[str]:
    """Spawn ``cortex upgrade`` as a subprocess (timeout 60s).

    Spec R10. Spec Technical Constraints: ``capture_output=True,
    text=True``, explicit ``timeout``, no ``check=True``.
    """
    return subprocess.run(
        _resolve_cortex_argv() + ["upgrade"],
        capture_output=True,
        text=True,
        timeout=_CORTEX_UPGRADE_TIMEOUT_SECONDS,
    )


#: Timeout (seconds) for each verification-probe subprocess. The probes
#: are read-only CLI invocations (``--print-root`` + ``overnight status``)
#: that are bounded by argparse + a single state-file read; 30s is the
#: same envelope the per-tool delegations use.
_VERIFICATION_PROBE_TIMEOUT_SECONDS = 30.0


def _run_verification_probe() -> bool:
    """R12 verification probe — invoked after a successful ``cortex upgrade``.

    Runs two subprocess invocations against the upgraded on-disk CLI:

    1. ``cortex --print-root`` — must exit 0 with parseable JSON.
    2. ``cortex overnight status --format json`` (NO trailing positional
       — see the plan-task architectural-context callout: the spec text
       "against an empty/unknown session id" describes the
       session-discovery state, not a literal empty-string positional;
       the current CLI's ``overnight status`` subparser does not accept a
       positional session_id, only ``--session-dir``). This invocation
       forces import of ``cortex_command.overnight.cli_handler`` and
       catches the lazy-import failure mode from a partial
       ``uv tool install --force`` that succeeded at the shim layer but
       failed mid-rewrite of the module files.

    Returns ``True`` on success (both probes exit 0 with parseable JSON)
    so the orchestrator continues normally. Returns ``False`` on any
    probe failure: the orchestrator's caller falls through to delegating
    against the on-disk CLI (degraded path; user sees the upgrade-failure
    error in the tool-call response). On failure, a one-line summary is
    written to stderr — Task 11 will replace this with the NDJSON error
    log path (R14).

    Spec R12.
    """

    def _run_probe(argv: list[str]) -> tuple[bool, str]:
        """Run one probe step; return (ok, error_summary)."""
        try:
            completed = subprocess.run(
                _resolve_cortex_argv() + argv,
                capture_output=True,
                text=True,
                timeout=_VERIFICATION_PROBE_TIMEOUT_SECONDS,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return False, f"{exc.__class__.__name__}: {exc}"
        if completed.returncode != 0:
            return False, (
                f"exit={completed.returncode} "
                f"stderr={completed.stderr!r}"
            )
        try:
            json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            return False, (
                f"unparseable JSON: {exc}; stdout={completed.stdout!r}"
            )
        return True, ""

    ok, summary = _run_probe(["--print-root"])
    if not ok:
        print(
            f"cortex auto-update failed at verification_probe: "
            f"`cortex --print-root`: {summary}; "
            f"falling through to on-disk CLI",
            file=sys.stderr,
        )
        _append_error_ndjson(
            stage="verification_probe",
            error=summary,
            context={
                "probe_step": "cortex --print-root",
            },
        )
        _invalidate_update_cache()
        return False

    # NOTE: NO trailing empty-string positional. See the architectural-
    # context callout in the Task 9 plan brief: "against an empty/unknown
    # session id" describes the session-discovery state, not a literal
    # argv element. The R18 sandbox probe corrected this; the
    # verification probe matches that corrected form.
    ok, summary = _run_probe(["overnight", "status", "--format", "json"])
    if not ok:
        print(
            f"cortex auto-update failed at verification_probe: "
            f"`cortex overnight status --format json`: {summary}; "
            f"falling through to on-disk CLI",
            file=sys.stderr,
        )
        _append_error_ndjson(
            stage="verification_probe",
            error=summary,
            context={
                "probe_step": "cortex overnight status --format json",
            },
        )
        _invalidate_update_cache()
        return False

    return True


def _orchestrate_upgrade(cortex_root_payload: dict[str, Any]) -> None:
    """Orchestrate ``cortex upgrade`` under the cross-process flock (R10/R11).

    Called by :func:`_maybe_run_upgrade` after R8 detected upstream
    advance and skip predicates did not fire. Pre-conditions: the caller
    has confirmed (a) ``_maybe_check_upstream()`` returned ``True`` and
    (b) skip predicates did not fire.

    Behavior:

    1. Acquire ``fcntl.flock(LOCK_EX)`` on
       ``$cortex_root/.git/cortex-update.lock`` with a 30-second wait
       budget (spec R11). On budget expiry: log a one-liner to stderr,
       call ``_invalidate_update_cache()`` (so the next tool call
       retries), and return without upgrading.

    2. Post-acquire re-verify: run a *fresh* ``git ls-remote
       <remote-url> HEAD`` and ``git -C $cortex_root rev-parse HEAD``
       and compare. If they match, another MCP already applied the
       update — skip the redundant ``cortex upgrade`` invocation, call
       ``_invalidate_update_cache()`` (so the next tool call re-checks
       against the now-current local), and return.

    3. Otherwise: spawn ``subprocess.run(["cortex", "upgrade"], ...,
       timeout=60)``. On non-zero exit: log to stderr (placeholder for
       Task 11's NDJSON path) and return without invalidating the cache
       (the cache will be invalidated by the Task 11 NDJSON-error
       branch once that lands; for Task 8 we leave the cache alone so
       the next tool call doesn't infinite-loop on a broken upgrade).

    4. On successful upgrade: invoke the verification probe (R12 — the
       Task 9 implementation lives in :func:`_run_verification_probe`),
       then call ``_invalidate_update_cache()`` so the next tool call
       re-checks against the upgraded local HEAD.

    The lock is released in a ``try/finally`` block in all paths.

    Spec R10, R11, plus Technical Constraints "Cache invalidation rules
    for R8's instance cache".
    """
    cortex_root = cortex_root_payload.get("root")
    remote_url = cortex_root_payload.get("remote_url")
    if not cortex_root or not remote_url:
        # Defensive: discovery payload missing required fields. The
        # caller (``_maybe_check_upstream``) already filters on these,
        # but be safe.
        return

    # R10 orchestration deprecated under wheel install (Task 16):
    # ``cortex upgrade`` is now an advisory printer (Task 6) that exits
    # 0 without doing anything, and the flock path
    # ``$cortex_root/.git/cortex-update.lock`` does not exist when the
    # CLI is installed via non-editable wheel. R4's first-install hook
    # (``_ensure_cortex_installed``) plus R13's schema-floor gate is the
    # upgrade arrow. Short-circuit silently here so consumers do not
    # exercise the dead path.
    if not (Path(str(cortex_root)) / ".git").is_dir():
        # R10 orchestration deprecated under wheel install; R4
        # first-install hook + R13 schema-floor gate is the upgrade
        # arrow.
        return

    lock_path = Path(str(cortex_root)) / ".git" / "cortex-update.lock"
    fd = _acquire_update_flock(lock_path)
    if fd is None:
        # R11 flock-budget expiry. Log to stderr (one-liner per spec),
        # append a `flock_timeout` audit record, and invalidate the
        # cache so the next tool call retries.
        print(
            f"cortex auto-update failed at flock_timeout: "
            f"{_FLOCK_WAIT_BUDGET_SECONDS:.0f}s budget exceeded on "
            f"{lock_path}; falling through to on-disk CLI",
            file=sys.stderr,
        )
        _append_error_ndjson(
            stage="flock_timeout",
            error=(
                f"wait budget {_FLOCK_WAIT_BUDGET_SECONDS:.0f}s exceeded"
            ),
            context={
                "lock_path": str(lock_path),
                "wait_budget_seconds": _FLOCK_WAIT_BUDGET_SECONDS,
                "trigger": "r10_upgrade",
            },
        )
        _invalidate_update_cache()
        return

    try:
        # Post-flock re-verification: fresh ls-remote + rev-parse,
        # compared to each other (NOT to the captured pre-flock
        # remote_sha — see spec Technical Constraints).
        fresh_remote_sha = _post_flock_remote_sha(str(remote_url))
        fresh_local_head = _post_flock_local_head(str(cortex_root))

        if (
            fresh_remote_sha is not None
            and fresh_local_head is not None
            and fresh_remote_sha == fresh_local_head
        ):
            # Another MCP already applied the update during our flock
            # wait. Skip the redundant `cortex upgrade` invocation;
            # invalidate the cache so the next tool call sees the new
            # local HEAD.
            _invalidate_update_cache()
            return

        # Upstream is still ahead post-flock. Run `cortex upgrade`.
        try:
            completed = _run_cortex_upgrade()
        except (subprocess.TimeoutExpired, OSError) as exc:
            print(
                f"cortex auto-update failed at cortex_upgrade: "
                f"{exc.__class__.__name__}: {exc}; "
                f"falling through to on-disk CLI",
                file=sys.stderr,
            )
            _append_error_ndjson(
                stage="cortex_upgrade",
                error=f"{exc.__class__.__name__}: {exc}",
                context={
                    "cortex_root": str(cortex_root),
                    "exception": exc.__class__.__name__,
                    "trigger": "r10_upgrade",
                },
            )
            _invalidate_update_cache()
            return

        if completed.returncode != 0:
            print(
                f"cortex auto-update failed at cortex_upgrade: "
                f"exit={completed.returncode}; "
                f"falling through to on-disk CLI",
                file=sys.stderr,
            )
            _append_error_ndjson(
                stage="cortex_upgrade",
                error=(
                    f"non-zero returncode {completed.returncode}; "
                    f"stderr={completed.stderr!r}"
                ),
                context={
                    "cortex_root": str(cortex_root),
                    "returncode": completed.returncode,
                    "stderr": completed.stderr,
                    "trigger": "r10_upgrade",
                },
            )
            _invalidate_update_cache()
            return

        # R10 success path: run the verification probe (R12, Task 9),
        # then invalidate the R8 cache so the next tool call re-checks.
        _run_verification_probe()
        _invalidate_update_cache()
    finally:
        _release_update_flock(fd)


def _maybe_run_upgrade(
    cortex_root_payload: Optional[dict[str, Any]] = None,
) -> None:
    """R8/R10/R11 entry point: check upstream, orchestrate upgrade if needed.

    Wired from each MCP tool dispatch site (replacing the bare
    ``_maybe_check_upstream()`` informational call from Task 7). The
    return value is intentionally ``None`` — this helper either
    successfully orchestrates an upgrade (or skips because no upgrade
    is needed / a predicate fired / a budget expired) and the caller
    delegates the user's intended tool call against the on-disk CLI in
    all paths.
    """
    if cortex_root_payload is None:
        try:
            cortex_root_payload = _get_cortex_root_payload()
        except (RuntimeError, subprocess.SubprocessError, OSError):
            return

    upstream_ahead = _maybe_check_upstream(cortex_root_payload)
    if upstream_ahead is not True:
        # Either skip-predicate fired (None), upstream matches local
        # (False), or ls-remote failed (None). No orchestration needed.
        return

    _orchestrate_upgrade(cortex_root_payload)


# ---------------------------------------------------------------------------
# R13 — Synchronous schema-floor gate (Task 10)
# ---------------------------------------------------------------------------


def _schema_floor_violated(cortex_root_payload: dict[str, Any]) -> bool:
    """Return True iff ``MCP_REQUIRED_CLI_VERSION`` major > CLI major.

    Spec R13: closes the bidirectional staleness window during
    plugin-update + CLI-update interaction. The CLI's reported
    ``schema_version`` comes from the discovery cache (Task 6); that
    cache never expires for the MCP-server lifetime.

    Returns ``False`` when the discovery payload has no parseable
    schema_version (defensive: the caller falls through to the regular
    R8 throttle path; ``_check_version`` will surface the
    malformed-version error during tool dispatch).

    Under wheel install (no ``.git`` dir at ``cortex_root``), the
    R13/R10/R11/R12 flock + ``cortex upgrade`` machinery is inert (see
    :func:`_orchestrate_schema_floor_upgrade`). Rather than letting the
    caller invoke a silent no-op, surface a single-line stderr
    remediation message naming the manual ``uv tool install --reinstall``
    command the user must run, then return ``False`` so the caller skips
    the dead orchestration path. The return value remains a ``bool`` —
    callers that gate on truthiness still work.
    """
    cli_version = cortex_root_payload.get("schema_version")
    if cli_version is None:
        return False
    try:
        cli_major = int(str(cli_version).split(".")[0])
        required_major = int(MCP_REQUIRED_CLI_VERSION.split(".")[0])
    except (ValueError, TypeError, AttributeError):
        return False
    violated = required_major > cli_major
    if violated:
        cortex_root = cortex_root_payload.get("root")
        if cortex_root and not (Path(str(cortex_root)) / ".git").is_dir():
            print(
                f"Schema-floor violation: installed CLI schema_version="
                f"{cli_version}, required={CLI_PIN[1]}; run "
                f"'uv tool install --reinstall "
                f"git+https://github.com/charleshall888/cortex-command.git"
                f"@{CLI_PIN[0]}' to upgrade",
                file=sys.stderr,
            )
            return False
    return violated


def _orchestrate_schema_floor_upgrade(
    cortex_root_payload: dict[str, Any],
) -> None:
    """Run ``cortex upgrade`` synchronously under R11 flock + R12 probe.

    Spec R13 requires that when the schema floor is violated, the MCP
    runs ``cortex upgrade`` synchronously before delegating any tool
    call — regardless of throttle policy. Skip predicates (R9) do NOT
    apply: a schema-floor mismatch must be resolved or the MCP cannot
    serve any tool call.

    Reuses the same flock acquisition (R11) and verification-probe
    (R12) machinery as :func:`_orchestrate_upgrade`, but skips:

    * the post-flock fresh ls-remote / rev-parse comparison — even if
      another MCP advanced HEAD during our wait, the schema-floor
      violation is the trigger here, not upstream advance, so the
      ``cortex upgrade`` invocation is still the correct response.

    On successful upgrade: invoke the verification probe (R12) and
    invalidate the R8 update-check cache (same hook as R10) so the
    next tool call re-checks against the upgraded local HEAD.

    Spec R13 + Technical Constraints "Cache invalidation rules for
    R8's instance cache" — "On any successful upgrade (R10 or R13),
    the cache MUST be marked unset".
    """
    cortex_root = cortex_root_payload.get("root")
    if not cortex_root:
        return

    # R10 orchestration deprecated under wheel install (Task 16): the
    # schema-floor upgrade path reuses R10/R11/R12 machinery that
    # depends on a git working tree at ``cortex_root``. Under wheel
    # install the CLI is reinstalled by R4's ``_ensure_cortex_installed``
    # rather than by ``cortex upgrade`` under a flock — so short-circuit
    # this legacy orchestration. Task 9's R4 first-install hook handles
    # the schema-floor major-mismatch reinstall under wheel install.
    if not (Path(str(cortex_root)) / ".git").is_dir():
        # R10 orchestration deprecated under wheel install; R4
        # first-install hook + R13 schema-floor gate is the upgrade
        # arrow.
        return

    lock_path = Path(str(cortex_root)) / ".git" / "cortex-update.lock"
    fd = _acquire_update_flock(lock_path)
    if fd is None:
        # R11 flock-budget expiry on the R13 schema-floor path. Log to
        # stderr, append a `flock_timeout` audit record, and invalidate
        # the cache.
        print(
            f"cortex auto-update failed at flock_timeout: "
            f"{_FLOCK_WAIT_BUDGET_SECONDS:.0f}s budget exceeded on "
            f"{lock_path} during schema-floor upgrade; "
            f"falling through to on-disk CLI",
            file=sys.stderr,
        )
        _append_error_ndjson(
            stage="flock_timeout",
            error=(
                f"wait budget {_FLOCK_WAIT_BUDGET_SECONDS:.0f}s exceeded"
            ),
            context={
                "lock_path": str(lock_path),
                "wait_budget_seconds": _FLOCK_WAIT_BUDGET_SECONDS,
                "trigger": "r13_schema_floor",
            },
        )
        _invalidate_update_cache()
        return

    try:
        try:
            completed = _run_cortex_upgrade()
        except (subprocess.TimeoutExpired, OSError) as exc:
            print(
                f"cortex auto-update failed at cortex_upgrade: "
                f"{exc.__class__.__name__}: {exc} (schema-floor); "
                f"falling through to on-disk CLI",
                file=sys.stderr,
            )
            _append_error_ndjson(
                stage="cortex_upgrade",
                error=f"{exc.__class__.__name__}: {exc}",
                context={
                    "cortex_root": str(cortex_root),
                    "exception": exc.__class__.__name__,
                    "trigger": "r13_schema_floor",
                },
            )
            _invalidate_update_cache()
            return

        if completed.returncode != 0:
            print(
                f"cortex auto-update failed at cortex_upgrade: "
                f"exit={completed.returncode} (schema-floor); "
                f"falling through to on-disk CLI",
                file=sys.stderr,
            )
            _append_error_ndjson(
                stage="cortex_upgrade",
                error=(
                    f"non-zero returncode {completed.returncode}; "
                    f"stderr={completed.stderr!r}"
                ),
                context={
                    "cortex_root": str(cortex_root),
                    "returncode": completed.returncode,
                    "stderr": completed.stderr,
                    "trigger": "r13_schema_floor",
                },
            )
            _invalidate_update_cache()
            return

        # R13 success path: run the verification probe (R12), then
        # invalidate the R8 cache (same hook as R10).
        _run_verification_probe()
        _invalidate_update_cache()
    finally:
        _release_update_flock(fd)


def _gate_dispatch(
    cortex_root_payload: Optional[dict[str, Any]] = None,
) -> None:
    """Per-tool-call gate-dispatch entry point.

    Spec Technical Constraints "Gate dispatch order on every tool call":

    1. R13 schema-floor check first. If ``MCP_REQUIRED_CLI_VERSION``'s
       major > CLI's reported major, run ``cortex upgrade``
       synchronously under R11 flock + R12 probe — regardless of
       throttle policy. Skip predicates (R9) do NOT apply to R13.

    2. R8 throttle check + R9 skip-predicates second, only if R13 did
       not fire.

    3. R10 + R11 + R12 fire if R8 detected upstream advance and
       predicates didn't fire.

    Replaces the bare ``_maybe_run_upgrade()`` call at each tool
    dispatch site.
    """
    if cortex_root_payload is None:
        try:
            cortex_root_payload = _get_cortex_root_payload()
        except (RuntimeError, subprocess.SubprocessError, OSError):
            return

    # (1) R13 schema-floor check first — bypasses throttle + skip
    # predicates per spec.
    if _schema_floor_violated(cortex_root_payload):
        _orchestrate_schema_floor_upgrade(cortex_root_payload)
        return

    # (2) + (3) R8 throttle check; on upstream-advance, R10/R11/R12.
    _maybe_run_upgrade(cortex_root_payload)


# ---------------------------------------------------------------------------
# Pydantic models — input/output schemas for the MCP tool surface. R1
# forbids importing schema modules from the cortex_command package, so
# these models are defined inline here. Each output model carries
# ``extra="ignore"`` so minor-greater payloads silently drop unknown
# fields (R15 forward-compat).
# ---------------------------------------------------------------------------


_FORWARD_COMPAT = ConfigDict(extra="ignore")


# overnight_start_run -------------------------------------------------------


class StartRunInput(BaseModel):
    """Input for the ``overnight_start_run`` tool."""

    confirm_dangerously_skip_permissions: Literal[True]
    state_path: str | None = None


class StartRunOutput(BaseModel):
    """Output for the ``overnight_start_run`` tool."""

    model_config = _FORWARD_COMPAT

    started: bool = True
    session_id: str | None = None
    pid: int | None = None
    started_at: str | None = None
    reason: str | None = None
    existing_session_id: str | None = None


# overnight_status ----------------------------------------------------------


class StatusInput(BaseModel):
    """Input for the ``overnight_status`` tool."""

    session_id: str | None = None


class FeatureCounts(BaseModel):
    """Per-phase feature counts for ``overnight_status``."""

    model_config = _FORWARD_COMPAT

    pending: int = 0
    running: int = 0
    merged: int = 0
    paused: int = 0
    deferred: int = 0
    failed: int = 0


class StatusOutput(BaseModel):
    """Output for the ``overnight_status`` tool."""

    model_config = _FORWARD_COMPAT

    session_id: str | None = None
    phase: str
    current_round: int | None = None
    started_at: str | None = None
    updated_at: str | None = None
    features: FeatureCounts = Field(default_factory=FeatureCounts)
    integration_branch: str | None = None
    paused_reason: str | None = None


# overnight_logs ------------------------------------------------------------


class LogsInput(BaseModel):
    """Input for the ``overnight_logs`` tool."""

    session_id: str
    files: list[Literal["events", "agent-activity", "escalations"]] = Field(
        default_factory=lambda: ["events"]
    )
    cursor: str | None = None
    limit: int = 100
    tail: int | None = None


class LogsOutput(BaseModel):
    """Output for the ``overnight_logs`` tool."""

    model_config = _FORWARD_COMPAT

    lines: list[dict[str, Any]] = Field(default_factory=list)
    next_cursor: str | None = None
    eof: bool = False
    cursor_invalid: bool | None = None
    oversized_line: bool | None = None
    truncated: bool | None = None
    original_line_bytes: int | None = None


# overnight_cancel ----------------------------------------------------------


class CancelInput(BaseModel):
    """Input for the ``overnight_cancel`` tool."""

    session_id: str
    force: bool = False


class CancelOutput(BaseModel):
    """Output for the ``overnight_cancel`` tool."""

    model_config = _FORWARD_COMPAT

    cancelled: bool
    signal_sent: list[str] = Field(default_factory=list)
    reason: Literal[
        "cancelled",
        "no_runner_pid",
        "magic_mismatch",
        "start_time_skew",
        "signal_not_delivered_within_timeout",
    ]
    pid_file_unlinked: bool = False
    pid: int | None = None


# overnight_list_sessions ---------------------------------------------------


class ListSessionsInput(BaseModel):
    """Input for the ``overnight_list_sessions`` tool."""

    status: list[Literal["planning", "executing", "paused", "complete"]] | None = None
    since: str | None = None
    limit: int | None = 10
    cursor: str | None = None


class SessionSummary(BaseModel):
    """Compact session record used in ``overnight_list_sessions`` output."""

    model_config = _FORWARD_COMPAT

    session_id: str
    phase: str
    started_at: str | None = None
    updated_at: str | None = None
    integration_branch: str | None = None


class ListSessionsOutput(BaseModel):
    """Output for the ``overnight_list_sessions`` tool."""

    model_config = _FORWARD_COMPAT

    active: list[SessionSummary] = Field(default_factory=list)
    recent: list[SessionSummary] = Field(default_factory=list)
    total_count: int = 0
    next_cursor: str | None = None


# overnight_schedule_run ----------------------------------------------------


class ScheduleRunInput(BaseModel):
    """Input for the ``overnight_schedule_run`` tool."""

    confirm_dangerously_skip_permissions: Literal[True]
    target_time: str
    state_path: str | None = None


class ScheduleRunOutput(BaseModel):
    """Output for the ``overnight_schedule_run`` tool."""

    model_config = _FORWARD_COMPAT

    scheduled: bool
    session_id: str | None = None
    label: str | None = None
    scheduled_for_iso: str | None = None


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------


def _run_cortex(
    argv_tail: list[str],
    *,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    """Run ``cortex <argv_tail>`` and return the completed process.

    Spec Technical Constraints: ``capture_output=True, text=True``,
    explicit ``timeout``, no ``check=True``. The caller inspects
    ``returncode`` and parses stdout / stderr explicitly so structured
    error envelopes (like ``{"error": "concurrent_runner", ...}``) are
    not collapsed into a generic exception.
    """
    try:
        return subprocess.run(
            _resolve_cortex_argv() + argv_tail,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise CortexCliMissing(
            exc.errno, exc.strerror, *exc.args[2:]
        ) from exc


def _retry_on_cli_missing(
    budget: list[int],
    func: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Invoke ``func`` and retry once on :class:`CortexCliMissing`.

    ``budget`` is a single-element mutable list ``[remaining_retries]``
    owned by the caller (the verb-dispatch tool body) so the retry
    counter is per-tool-call (local to the dispatcher) rather than
    module-global. The first ``CortexCliMissing`` clears
    ``_CORTEX_ROOT_CACHE`` (in case a stale cache entry caused
    discovery to point at a now-missing CLI) and retries once. A
    second ``CortexCliMissing`` (or any failure once budget is
    exhausted) re-raises so the caller can return
    :data:`_CORTEX_CLI_MISSING_ERROR`.

    Catches exactly ``CortexCliMissing`` — never the broader ``OSError``
    parent — so unrelated failures (e.g., ``PermissionError``) propagate
    unchanged.
    """
    global _CORTEX_ROOT_CACHE
    try:
        return func(*args, **kwargs)
    except CortexCliMissing:
        if budget[0] <= 0:
            raise
        budget[0] -= 1
        _CORTEX_ROOT_CACHE = None
        return func(*args, **kwargs)


def _parse_json_payload(
    completed: subprocess.CompletedProcess[str],
    *,
    verb: str,
) -> dict:
    """Parse stdout JSON, enforce schema floor, and return the dict.

    Used by every tool that consumes a versioned JSON envelope. Raises
    :class:`RuntimeError` (unparseable) or :class:`SchemaVersionError`
    (major mismatch / missing version on a non-legacy shape).
    """
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{verb}: CLI stdout is not parseable JSON: {exc}; "
            f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"{verb}: CLI payload is not an object: "
            f"{type(payload).__name__}"
        )
    _check_version(payload, verb=verb)
    return payload


# ---------------------------------------------------------------------------
# Per-tool delegation logic — pure functions for testability
# ---------------------------------------------------------------------------


# Per-tool subprocess timeouts (seconds). 30s is sufficient for all
# read-only verbs. ``overnight_start_run`` also uses 30s (R12): the
# spawn path includes plist write + bootstrap + launchctl print verify
# + sidecar atomic write + concurrent-runner check; typical latency is
# sub-second, but 30s preserves headroom for slow-disk and
# disk-pressure cases without producing spurious MCP failures.
_DEFAULT_TOOL_TIMEOUT = 30.0
_START_RUN_TOOL_TIMEOUT = 30.0
_SCHEDULE_RUN_TOOL_TIMEOUT = 30.0


def _delegate_overnight_start_run(
    payload: StartRunInput,
) -> StartRunOutput | str:
    """Subprocess delegation for ``overnight_start_run``.

    The CLI either spawns the runner (no JSON envelope on stdout, exit
    0; runner detached under launchd by design — Task 6 async-spawn
    refactor) or refuses with ``concurrent_runner`` (exit non-zero,
    versioned JSON on stdout). Successful spawn is confirmed by the
    spawn-confirmation handshake (R18): the CLI polls for
    ``runner.pid`` within 5 s before returning exit 0.  The MCP layer
    treats exit-zero as ``started=True``; downstream consumers should
    poll ``overnight_status`` for live state.

    The subprocess timeout is 30 s (R12): the spawn path is normally
    sub-second but 30 s preserves headroom for slow-disk cases without
    producing spurious MCP failures.

    On unrecovered :class:`CortexCliMissing` (S1.3 retry exhausted),
    returns :data:`_CORTEX_CLI_MISSING_ERROR` (S5.2) so FastMCP wraps
    the response into the canonical missing-CLI error envelope.
    """

    # Validation gate is enforced at the FastMCP wrapper layer (the
    # input model's ``Literal[True]`` rejects missing/false confirmations
    # before we get here).

    # R13/R8/R9/R10/R11 gate dispatch (Task 10 wires R13 ahead of R8).
    _gate_dispatch()

    argv: list[str] = ["overnight", "start", "--format", "json"]
    if payload.state_path is not None:
        argv.extend(["--state", payload.state_path])

    # Per-tool-call retry budget for CortexCliMissing (S1.3). Local
    # variable, NOT module-global — each verb invocation gets its own.
    cli_retry_budget: list[int] = [1]
    try:
        completed = _retry_on_cli_missing(
            cli_retry_budget,
            _run_cortex,
            argv,
            timeout=_START_RUN_TOOL_TIMEOUT,
        )
    except CortexCliMissing:
        return _CORTEX_CLI_MISSING_ERROR

    # The CLI emits a JSON envelope only on the concurrent-runner
    # refusal path. A successful spawn returns 0 with no stdout JSON
    # (the runner is detached and writes its own logs).
    if completed.stdout.strip():
        # Try to parse — concurrent-runner refusal carries
        # ``{"version": "1.0", "error": "concurrent_runner",
        #   "session_id": "...", "existing_pid": <int>}``.
        try:
            parsed = _parse_json_payload(
                completed, verb="overnight_start_run"
            )
        except RuntimeError:
            # Not parseable — surface stderr verbatim.
            raise
        if parsed.get("error") == "concurrent_runner":
            return StartRunOutput(
                started=False,
                session_id=None,
                pid=parsed.get("existing_pid"),
                started_at=None,
                reason="concurrent_runner_alive",
                existing_session_id=parsed.get("session_id") or None,
            )
        # Unknown structured payload — let the caller see the JSON.
        raise RuntimeError(
            f"overnight_start_run: unrecognized JSON envelope: {parsed!r}"
        )

    if completed.returncode != 0:
        raise RuntimeError(
            f"overnight_start_run: cortex exited "
            f"{completed.returncode}; stderr={completed.stderr!r}"
        )

    # Successful spawn: the runner is detached. The CLI does not emit
    # session/pid metadata on this path. Return a minimal success
    # envelope; downstream consumers should poll ``overnight_status``
    # for live state.
    return StartRunOutput(
        started=True,
        session_id=None,
        pid=None,
        started_at=None,
        reason=None,
        existing_session_id=None,
    )


def _delegate_overnight_schedule_run(
    payload: ScheduleRunInput,
) -> ScheduleRunOutput | str:
    """Subprocess delegation for ``overnight_schedule_run``.

    Calls ``cortex overnight schedule <target_time> --format json`` and
    parses the JSON envelope.  On a non-zero exit the delegate returns
    ``ScheduleRunOutput(scheduled=False)``; on a subprocess timeout the
    exception propagates to the MCP layer (prefer an explicit tool error
    over a silent ``scheduled=False`` in case the plist was already
    written).

    On unrecovered :class:`CortexCliMissing` (S1.3 retry exhausted),
    returns :data:`_CORTEX_CLI_MISSING_ERROR` (S5.2).
    """

    # Validation gate is enforced at the FastMCP wrapper layer (the
    # input model's ``Literal[True]`` rejects missing/false confirmations
    # before we get here).

    _gate_dispatch()

    argv: list[str] = ["overnight", "schedule", payload.target_time, "--format", "json"]
    if payload.state_path is not None:
        argv.extend(["--state", payload.state_path])

    # Per-tool-call retry budget for CortexCliMissing (S1.3).
    cli_retry_budget: list[int] = [1]
    try:
        completed = _retry_on_cli_missing(
            cli_retry_budget,
            _run_cortex,
            argv,
            timeout=_SCHEDULE_RUN_TOOL_TIMEOUT,
        )
    except CortexCliMissing:
        return _CORTEX_CLI_MISSING_ERROR

    if completed.returncode != 0:
        return ScheduleRunOutput(
            scheduled=False,
            session_id=None,
            label=None,
            scheduled_for_iso=None,
        )

    parsed = _parse_json_payload(completed, verb="overnight_schedule_run")
    return ScheduleRunOutput(
        scheduled=True,
        session_id=parsed.get("session_id"),
        label=parsed.get("label"),
        scheduled_for_iso=parsed.get("scheduled_for_iso"),
    )


def _delegate_overnight_status(payload: StatusInput) -> StatusOutput | str:
    """Subprocess delegation for ``overnight_status``.

    On unrecovered :class:`CortexCliMissing` (S1.3 retry exhausted),
    returns :data:`_CORTEX_CLI_MISSING_ERROR` (S5.2).
    """

    # R13/R8/R9/R10/R11 gate dispatch (Task 10 wires R13 ahead of R8).
    _gate_dispatch()

    argv: list[str] = ["overnight", "status", "--format", "json"]
    # Per-tool-call retry budget for CortexCliMissing (S1.3). Shared
    # across BOTH _get_cortex_root_payload and _run_cortex below — the
    # whole tool invocation gets exactly one retry across all
    # subprocess hits.
    cli_retry_budget: list[int] = [1]
    # The CLI's ``--session-dir`` override is the way to target a
    # specific session; ``session_id`` from the MCP input maps to the
    # absolute session-dir under the resolved cortex root. Without an
    # override the CLI falls back to the active-session pointer.
    if payload.session_id is not None:
        # Build the session-dir using the home repo path (resolved CLI
        # side via _resolve_repo_path). We delegate that resolution to
        # the CLI by passing the override only when it makes sense; if
        # the caller passed a session_id, hand it through as the
        # directory basename and let the CLI resolve via its own
        # `_resolve_repo_path()`.
        try:
            root_payload = _retry_on_cli_missing(
                cli_retry_budget, _get_cortex_root_payload
            )
        except CortexCliMissing:
            return _CORTEX_CLI_MISSING_ERROR
        cortex_root = root_payload.get("root", "")
        # The CLI expects an absolute or repo-relative session dir; use
        # the cortex_root's cortex/lifecycle/sessions tree.
        session_dir = (
            Path(cortex_root) / "cortex" / "lifecycle" / "sessions" / payload.session_id
        )
        argv.extend(["--session-dir", str(session_dir)])

    try:
        completed = _retry_on_cli_missing(
            cli_retry_budget,
            _run_cortex,
            argv,
            timeout=_DEFAULT_TOOL_TIMEOUT,
        )
    except CortexCliMissing:
        return _CORTEX_CLI_MISSING_ERROR
    if completed.returncode != 0:
        raise RuntimeError(
            f"overnight_status: cortex exited "
            f"{completed.returncode}; stderr={completed.stderr!r}"
        )

    parsed = _parse_json_payload(completed, verb="overnight_status")

    # Legacy ``{"active": false}`` shape: surface as
    # ``phase="no_active_session"`` so existing callers see a stable
    # sentinel instead of a missing-key error.
    if parsed.get("active") is False:
        return StatusOutput(
            session_id=payload.session_id, phase="no_active_session"
        )

    # Active shape: pass through. Note that the current CLI emits the
    # ``features`` map keyed by feature-name; the MCP output model
    # collapses that into per-status counts. Compute the counts here
    # so the contract stays stable across the refactor.
    features_map = parsed.get("features") or {}
    counts = _feature_counts_from_map(features_map)

    return StatusOutput(
        session_id=parsed.get("session_id") or None,
        phase=str(parsed.get("phase", "")),
        current_round=parsed.get("current_round"),
        started_at=parsed.get("started_at"),
        updated_at=parsed.get("updated_at"),
        features=counts,
        integration_branch=parsed.get("integration_branch"),
        paused_reason=parsed.get("paused_reason"),
    )


def _feature_counts_from_map(features_map: Any) -> FeatureCounts:
    """Collapse the per-feature map into per-status totals.

    Output shape is preserved across the decoupling refactor: the same
    per-status totals (pending/running/merged/paused/deferred) the
    in-process MCP tool surfaced before R7 deleted it.
    """
    counts = {
        "pending": 0,
        "running": 0,
        "merged": 0,
        "paused": 0,
        "deferred": 0,
        "failed": 0,
    }
    if isinstance(features_map, dict):
        for entry in features_map.values():
            if not isinstance(entry, dict):
                continue
            status = entry.get("status")
            if status in counts:
                counts[status] += 1
    return FeatureCounts(**counts)


def _delegate_overnight_logs(payload: LogsInput) -> LogsOutput | str:
    """Subprocess delegation for ``overnight_logs``.

    The CLI's ``logs`` verb only handles a single ``--files`` selector
    per invocation; the MCP tool accepts a list of files. We invoke
    the CLI once per file in ``payload.files`` and aggregate.

    On unrecovered :class:`CortexCliMissing` (S1.3 retry exhausted),
    returns :data:`_CORTEX_CLI_MISSING_ERROR` (S5.2). The retry budget
    is shared across all loop iterations: the tool invocation as a
    whole gets one retry, not one-per-file.
    """

    # R13/R8/R9/R10/R11 gate dispatch (Task 10 wires R13 ahead of R8).
    _gate_dispatch()

    aggregated_lines: list[dict[str, Any]] = []
    next_cursor: str | None = None
    eof_flags: list[bool] = []
    # Per-tool-call retry budget for CortexCliMissing (S1.3). Shared
    # across all loop iterations below.
    cli_retry_budget: list[int] = [1]

    for file_key in payload.files:
        argv: list[str] = [
            "overnight",
            "logs",
            "--format",
            "json",
            "--files",
            file_key,
        ]
        if payload.cursor is not None:
            argv.extend(["--since", payload.cursor])
        if payload.tail is not None:
            argv.extend(["--tail", str(payload.tail)])
        if payload.limit is not None:
            argv.extend(["--limit", str(payload.limit)])
        argv.append(payload.session_id)

        try:
            completed = _retry_on_cli_missing(
                cli_retry_budget,
                _run_cortex,
                argv,
                timeout=_DEFAULT_TOOL_TIMEOUT,
            )
        except CortexCliMissing:
            return _CORTEX_CLI_MISSING_ERROR
        # Logs verb emits a versioned JSON envelope for both success
        # and error paths; check the envelope before falling back to
        # exit code.
        if not completed.stdout.strip():
            raise RuntimeError(
                f"overnight_logs: empty stdout from cortex; "
                f"returncode={completed.returncode} "
                f"stderr={completed.stderr!r}"
            )
        parsed = _parse_json_payload(completed, verb="overnight_logs")

        if parsed.get("error") == "invalid_cursor":
            return LogsOutput(
                lines=[],
                next_cursor=None,
                eof=False,
                cursor_invalid=True,
            )
        if parsed.get("error") is not None:
            raise RuntimeError(
                f"overnight_logs: cortex error {parsed['error']!r}: "
                f"{parsed.get('message', '')}"
            )

        for raw_line in parsed.get("lines", []):
            aggregated_lines.append(_parse_log_line(raw_line))
        if parsed.get("next_cursor") is not None:
            next_cursor = parsed["next_cursor"]
        # The CLI logs verb does not currently surface an explicit
        # ``eof`` flag — treat absence as "not at EOF" to keep clients
        # paginating; the next call returns zero new lines once the
        # cursor catches up.
        eof_flags.append(False)

    eof = all(eof_flags) if eof_flags else True

    return LogsOutput(
        lines=aggregated_lines,
        next_cursor=next_cursor,
        eof=eof,
    )


def _parse_log_line(line: Any) -> dict[str, Any]:
    """Parse a log line as JSON; fall back to ``{"raw": line}`` on failure.

    Events / agent-activity / escalations are all JSONL, so a failed
    parse means a malformed or partial line. Non-string inputs are
    coerced to ``str()`` first so the output stays a flat dict.
    """
    text = line if isinstance(line, str) else str(line)
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        return {"raw": text}
    if not isinstance(obj, dict):
        return {"raw": text}
    return obj


def _delegate_overnight_cancel(payload: CancelInput) -> CancelOutput | str:
    """Subprocess delegation for ``overnight_cancel``.

    The CLI's ``cancel`` verb signals the runner's process group; the
    MCP tool's richer contract (signal escalation, ``force`` flag,
    five enumerated reasons) is approximated by mapping the CLI's
    error envelope onto the matching reason code.

    On unrecovered :class:`CortexCliMissing` (S1.3 retry exhausted),
    returns :data:`_CORTEX_CLI_MISSING_ERROR` (S5.2).
    """

    # R13/R8/R9/R10/R11 gate dispatch (Task 10 wires R13 ahead of R8).
    _gate_dispatch()

    argv: list[str] = [
        "overnight",
        "cancel",
        "--format",
        "json",
        payload.session_id,
    ]
    # Per-tool-call retry budget for CortexCliMissing (S1.3).
    cli_retry_budget: list[int] = [1]
    try:
        completed = _retry_on_cli_missing(
            cli_retry_budget,
            _run_cortex,
            argv,
            timeout=_DEFAULT_TOOL_TIMEOUT,
        )
    except CortexCliMissing:
        return _CORTEX_CLI_MISSING_ERROR

    if not completed.stdout.strip():
        raise RuntimeError(
            f"overnight_cancel: empty stdout from cortex; "
            f"returncode={completed.returncode} "
            f"stderr={completed.stderr!r}"
        )
    parsed = _parse_json_payload(completed, verb="overnight_cancel")

    if parsed.get("cancelled"):
        return CancelOutput(
            cancelled=True,
            signal_sent=["SIGTERM"],
            reason="cancelled",
            pid_file_unlinked=False,
            pid=None,
        )

    err = parsed.get("error")
    if err == "no_active_session":
        return CancelOutput(
            cancelled=False,
            signal_sent=[],
            reason="no_runner_pid",
            pid_file_unlinked=False,
            pid=None,
        )
    if err == "stale_lock_cleared":
        # CLI self-heals on stale PID — the closest enum match is
        # ``start_time_skew`` (the recorded process is no longer the
        # one we expect; the IPC lock was cleared).
        return CancelOutput(
            cancelled=False,
            signal_sent=[],
            reason="start_time_skew",
            pid_file_unlinked=True,
            pid=None,
        )
    if err == "invalid_session_id":
        raise RuntimeError(
            f"overnight_cancel: invalid session id: {parsed.get('message', '')}"
        )
    if err == "cancel_failed":
        return CancelOutput(
            cancelled=False,
            signal_sent=["SIGTERM"],
            reason="signal_not_delivered_within_timeout",
            pid_file_unlinked=False,
            pid=None,
        )
    raise RuntimeError(
        f"overnight_cancel: unrecognized JSON envelope: {parsed!r}"
    )


def _delegate_overnight_list_sessions(
    payload: ListSessionsInput,
) -> ListSessionsOutput | str:
    """Subprocess delegation for ``overnight_list_sessions``.

    On unrecovered :class:`CortexCliMissing` (S1.3 retry exhausted),
    returns :data:`_CORTEX_CLI_MISSING_ERROR` (S5.2).
    """

    # R13/R8/R9/R10/R11 gate dispatch (Task 10 wires R13 ahead of R8).
    _gate_dispatch()

    argv: list[str] = ["overnight", "list-sessions", "--format", "json"]
    if payload.status is not None:
        for s in payload.status:
            argv.extend(["--status", s])
    if payload.since is not None:
        argv.extend(["--since", payload.since])
    if payload.limit is not None:
        argv.extend(["--limit", str(payload.limit)])

    # Per-tool-call retry budget for CortexCliMissing (S1.3).
    cli_retry_budget: list[int] = [1]
    try:
        completed = _retry_on_cli_missing(
            cli_retry_budget,
            _run_cortex,
            argv,
            timeout=_DEFAULT_TOOL_TIMEOUT,
        )
    except CortexCliMissing:
        return _CORTEX_CLI_MISSING_ERROR
    if completed.returncode != 0:
        raise RuntimeError(
            f"overnight_list_sessions: cortex exited "
            f"{completed.returncode}; stderr={completed.stderr!r}"
        )

    parsed = _parse_json_payload(completed, verb="overnight_list_sessions")

    return ListSessionsOutput(
        active=[
            SessionSummary(**entry)
            for entry in parsed.get("active", [])
            if isinstance(entry, dict)
        ],
        recent=[
            SessionSummary(**entry)
            for entry in parsed.get("recent", [])
            if isinstance(entry, dict)
        ],
        total_count=int(parsed.get("total_count", 0)),
        next_cursor=parsed.get("next_cursor"),
    )


# ---------------------------------------------------------------------------
# FastMCP wiring
# ---------------------------------------------------------------------------


server = FastMCP("cortex-overnight")
"""Stdio FastMCP instance with the six overnight tools registered."""


_START_RUN_WARNING = (
    "This tool spawns a multi-hour autonomous agent that bypasses "
    "permission prompts and consumes Opus tokens. Only call when the "
    "user has explicitly asked to start an overnight run."
)

_SCHEDULE_RUN_WARNING = (
    "This tool schedules a future overnight run via a LaunchAgent plist. "
    "Only call when the user has explicitly asked to schedule an overnight run."
)


@server.tool(
    name="overnight_start_run",
    description=_START_RUN_WARNING,
)
async def overnight_start_run(
    payload: StartRunInput,
) -> StartRunOutput | str:
    """Spawn the overnight runner via subprocess delegation.

    Return type union with ``str`` accommodates the
    :data:`_CORTEX_CLI_MISSING_ERROR` graceful-degrade path (S5.2):
    when the cortex CLI is unrecoverably missing, the delegate
    returns the canonical error string and FastMCP wraps it as a
    ``CallToolResult(isError=True, ...)`` envelope.
    """
    return _delegate_overnight_start_run(payload)


@server.tool(
    name="overnight_schedule_run",
    description=_SCHEDULE_RUN_WARNING,
)
async def overnight_schedule_run(
    payload: ScheduleRunInput,
) -> ScheduleRunOutput | str:
    """Schedule a future overnight run via subprocess delegation.

    Return type union with ``str`` accommodates the
    :data:`_CORTEX_CLI_MISSING_ERROR` graceful-degrade path (S5.2):
    when the cortex CLI is unrecoverably missing, the delegate
    returns the canonical error string and FastMCP wraps it as a
    ``CallToolResult(isError=True, ...)`` envelope.
    """
    return _delegate_overnight_schedule_run(payload)


@server.tool(
    name="overnight_status",
    description=(
        "Return the current overnight session status (phase, round, "
        "feature counts, integration branch)."
    ),
)
async def overnight_status(payload: StatusInput) -> StatusOutput | str:
    """Return overnight session status via subprocess delegation.

    Return type union with ``str`` accommodates the
    :data:`_CORTEX_CLI_MISSING_ERROR` graceful-degrade path (S5.2).
    """
    return _delegate_overnight_status(payload)


@server.tool(
    name="overnight_logs",
    description=(
        "Return paginated log lines for events / agent-activity / "
        "escalations using opaque cursor tokens."
    ),
)
async def overnight_logs(payload: LogsInput) -> LogsOutput | str:
    """Return overnight session logs via subprocess delegation.

    Return type union with ``str`` accommodates the
    :data:`_CORTEX_CLI_MISSING_ERROR` graceful-degrade path (S5.2).
    """
    return _delegate_overnight_logs(payload)


@server.tool(
    name="overnight_cancel",
    description=(
        "Cancel the active overnight runner via SIGTERM-then-SIGKILL "
        "against its process group."
    ),
)
async def overnight_cancel(payload: CancelInput) -> CancelOutput | str:
    """Cancel an overnight session via subprocess delegation.

    Return type union with ``str`` accommodates the
    :data:`_CORTEX_CLI_MISSING_ERROR` graceful-degrade path (S5.2).
    """
    return _delegate_overnight_cancel(payload)


@server.tool(
    name="overnight_list_sessions",
    description=(
        "List active and recent overnight sessions with optional "
        "status / since filters and cursor pagination."
    ),
)
async def overnight_list_sessions(
    payload: ListSessionsInput,
) -> ListSessionsOutput | str:
    """List overnight sessions via subprocess delegation.

    Return type union with ``str`` accommodates the
    :data:`_CORTEX_CLI_MISSING_ERROR` graceful-degrade path (S5.2).
    """
    return _delegate_overnight_list_sessions(payload)


def main() -> None:
    """Entrypoint for ``uv run --script server.py``.

    Runs the FastMCP stdio transport.
    """

    server.run()


if __name__ == "__main__":
    main()
