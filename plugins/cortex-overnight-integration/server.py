#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "mcp>=1.27,<2",
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
from typing import Any, Literal, Optional


def _enforce_plugin_root() -> None:
    """R17 — confused-deputy mitigation.

    Verify, at startup, that this file lives under the resolved
    ``${CLAUDE_PLUGIN_ROOT}``. On mismatch (or absent env var), refuse
    to start: print ``"plugin path mismatch"`` to stderr and exit
    non-zero. This prevents an attacker who can override
    ``CLAUDE_PLUGIN_ROOT`` from pointing uvx at arbitrary Python.
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

#: Schema floor the MCP refuses to operate below. ``M.m`` per Terraform's
#: ``format_version`` precedent: a *major* mismatch is hard-rejected
#: (breaking change); *minor* drift is silently tolerated for
#: forward-compat (Pydantic's ``extra="ignore"`` drops unknown fields).
MCP_REQUIRED_CLI_VERSION = "1.0"


class SchemaVersionError(RuntimeError):
    """Raised when a CLI payload's major version differs from the floor.

    The MCP runtime catches this and surfaces a structured error to the
    Claude Code client; the user's tool call fails (rather than
    silently consuming an incompatible payload).
    """


def _parse_major_minor(version: str) -> tuple[int, int]:
    """Parse a ``"M.m"`` string into ``(major, minor)``.

    Strict — raises :class:`ValueError` on any non-conforming input. The
    schema-version helper catches this and re-raises as
    :class:`SchemaVersionError` with context.
    """
    parts = str(version).split(".", 1)
    if len(parts) != 2:
        raise ValueError(f"version must be 'M.m'; got {version!r}")
    return int(parts[0]), int(parts[1])


def _check_version(payload: dict, *, verb: str) -> None:
    """Enforce the schema-floor on a CLI JSON payload (R15).

    Raises :class:`SchemaVersionError` when:

    * ``payload['version']`` is missing (with the documented exception
      for the legacy ``{"active": false}`` no-active-session shape from
      ``cortex overnight status --format json``, which pre-dates the
      versioned envelope).
    * ``payload['version']``'s major component differs from
      ``MCP_REQUIRED_CLI_VERSION``'s major.

    Minor-greater is accepted; the payload's unknown fields are dropped
    by Pydantic's ``model_config = ConfigDict(extra="ignore")`` on each
    output model.
    """

    version = payload.get("version") if isinstance(payload, dict) else None
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
            f"{verb}: missing 'version' field in CLI JSON payload"
        )

    try:
        major, _minor = _parse_major_minor(version)
    except (ValueError, TypeError) as exc:
        raise SchemaVersionError(
            f"{verb}: malformed version {version!r}: {exc}"
        ) from exc

    required_major, _ = _parse_major_minor(MCP_REQUIRED_CLI_VERSION)
    if major != required_major:
        raise SchemaVersionError(
            f"{verb}: major-version mismatch — CLI emitted {version!r}, "
            f"MCP requires major={required_major} "
            f"(MCP_REQUIRED_CLI_VERSION={MCP_REQUIRED_CLI_VERSION!r})"
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


# ---------------------------------------------------------------------------
# Discovery cache (separate from R8's update-check cache; never expires)
# ---------------------------------------------------------------------------

#: Cache of the ``cortex --print-root`` payload, populated on first
#: access. ``None`` indicates not-yet-fetched. R8 (Task 7) reads
#: ``head_sha`` and ``remote_url`` from this cache.
_CORTEX_ROOT_CACHE: Optional[dict[str, Any]] = None


def _resolve_cortex_argv() -> list[str]:
    """Return the argv prefix that invokes the ``cortex`` CLI.

    Always uses the bare ``cortex`` console script — the plugin's MCP
    runtime is reachable only when uv has resolved the user's
    ``cortex-command`` install, so ``cortex`` is on PATH by
    construction.
    """
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
    if not cortex_root or not remote_url or not head_sha:
        # Missing fields in discovery payload — cannot construct the
        # cache key or compare. Skip silently; this is a defensive
        # branch (R3 acceptance asserts these fields are populated by
        # the CLI, but we don't want a half-formed payload to crash
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
    ``version`` comes from the discovery cache (Task 6); that cache
    never expires for the MCP-server lifetime.

    Returns ``False`` when the discovery payload has no parseable
    version (defensive: the caller falls through to the regular R8
    throttle path; ``_check_version`` will surface the malformed-version
    error during tool dispatch).
    """
    cli_version = cortex_root_payload.get("version")
    if cli_version is None:
        return False
    try:
        cli_major, _ = _parse_major_minor(cli_version)
        required_major, _ = _parse_major_minor(MCP_REQUIRED_CLI_VERSION)
    except (ValueError, TypeError):
        return False
    return required_major > cli_major


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
# read-only verbs; ``overnight_start_run`` gets 60s because the CLI
# does real work (loads state, may invoke runner.run).
_DEFAULT_TOOL_TIMEOUT = 30.0
_START_RUN_TOOL_TIMEOUT = 60.0


def _delegate_overnight_start_run(payload: StartRunInput) -> StartRunOutput:
    """Subprocess delegation for ``overnight_start_run``.

    The CLI either spawns the runner (no JSON envelope on stdout, exit
    0; runner detached) or refuses with ``concurrent_runner`` (exit
    non-zero, versioned JSON on stdout). Successful spawn is signalled
    by parsing the runner.pid that the runner writes; for the MCP
    delegation we approximate by treating exit-zero as
    ``started=True`` with best-effort fields filled from the
    discovery-cache + the state file.
    """

    # Validation gate is enforced at the FastMCP wrapper layer (the
    # input model's ``Literal[True]`` rejects missing/false confirmations
    # before we get here).

    # R13/R8/R9/R10/R11 gate dispatch (Task 10 wires R13 ahead of R8).
    _gate_dispatch()

    argv: list[str] = ["overnight", "start", "--format", "json"]
    if payload.state_path is not None:
        argv.extend(["--state", payload.state_path])

    completed = _run_cortex(argv, timeout=_START_RUN_TOOL_TIMEOUT)

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


def _delegate_overnight_status(payload: StatusInput) -> StatusOutput:
    """Subprocess delegation for ``overnight_status``."""

    # R13/R8/R9/R10/R11 gate dispatch (Task 10 wires R13 ahead of R8).
    _gate_dispatch()

    argv: list[str] = ["overnight", "status", "--format", "json"]
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
        cortex_root = _get_cortex_root_payload().get("root", "")
        # The CLI expects an absolute or repo-relative session dir; use
        # the cortex_root's lifecycle/sessions tree.
        session_dir = (
            Path(cortex_root) / "lifecycle" / "sessions" / payload.session_id
        )
        argv.extend(["--session-dir", str(session_dir)])

    completed = _run_cortex(argv, timeout=_DEFAULT_TOOL_TIMEOUT)
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


def _delegate_overnight_logs(payload: LogsInput) -> LogsOutput:
    """Subprocess delegation for ``overnight_logs``.

    The CLI's ``logs`` verb only handles a single ``--files`` selector
    per invocation; the MCP tool accepts a list of files. We invoke
    the CLI once per file in ``payload.files`` and aggregate.
    """

    # R13/R8/R9/R10/R11 gate dispatch (Task 10 wires R13 ahead of R8).
    _gate_dispatch()

    aggregated_lines: list[dict[str, Any]] = []
    next_cursor: str | None = None
    eof_flags: list[bool] = []

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

        completed = _run_cortex(argv, timeout=_DEFAULT_TOOL_TIMEOUT)
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


def _delegate_overnight_cancel(payload: CancelInput) -> CancelOutput:
    """Subprocess delegation for ``overnight_cancel``.

    The CLI's ``cancel`` verb signals the runner's process group; the
    MCP tool's richer contract (signal escalation, ``force`` flag,
    five enumerated reasons) is approximated by mapping the CLI's
    error envelope onto the matching reason code.
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
    completed = _run_cortex(argv, timeout=_DEFAULT_TOOL_TIMEOUT)

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
) -> ListSessionsOutput:
    """Subprocess delegation for ``overnight_list_sessions``."""

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

    completed = _run_cortex(argv, timeout=_DEFAULT_TOOL_TIMEOUT)
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
"""Stdio FastMCP instance with the five overnight tools registered."""


_START_RUN_WARNING = (
    "This tool spawns a multi-hour autonomous agent that bypasses "
    "permission prompts and consumes Opus tokens. Only call when the "
    "user has explicitly asked to start an overnight run."
)


@server.tool(
    name="overnight_start_run",
    description=_START_RUN_WARNING,
)
async def overnight_start_run(payload: StartRunInput) -> StartRunOutput:
    """Spawn the overnight runner via subprocess delegation."""
    return _delegate_overnight_start_run(payload)


@server.tool(
    name="overnight_status",
    description=(
        "Return the current overnight session status (phase, round, "
        "feature counts, integration branch)."
    ),
)
async def overnight_status(payload: StatusInput) -> StatusOutput:
    """Return overnight session status via subprocess delegation."""
    return _delegate_overnight_status(payload)


@server.tool(
    name="overnight_logs",
    description=(
        "Return paginated log lines for events / agent-activity / "
        "escalations using opaque cursor tokens."
    ),
)
async def overnight_logs(payload: LogsInput) -> LogsOutput:
    """Return overnight session logs via subprocess delegation."""
    return _delegate_overnight_logs(payload)


@server.tool(
    name="overnight_cancel",
    description=(
        "Cancel the active overnight runner via SIGTERM-then-SIGKILL "
        "against its process group."
    ),
)
async def overnight_cancel(payload: CancelInput) -> CancelOutput:
    """Cancel an overnight session via subprocess delegation."""
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
) -> ListSessionsOutput:
    """List overnight sessions via subprocess delegation."""
    return _delegate_overnight_list_sessions(payload)


def main() -> None:
    """Entrypoint for ``uv run --script server.py``.

    Runs the FastMCP stdio transport.
    """

    server.run()


if __name__ == "__main__":
    main()
