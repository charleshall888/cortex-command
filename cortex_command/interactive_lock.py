"""Interactive-session concurrency lock for the worktree-interactive mode.

Provides per-feature ``interactive.pid`` lock acquisition, liveness
verification, stale recovery, and release.  ``acquire``, ``read``,
``inspect``, and ``force-release`` all resolve their lock/events paths to
the **main repo root** via ``_resolve_main_repo_root()`` regardless of the
CWD — which may be a git worktree carrying its own co-located, git-tracked
``cortex/`` under the Variant A interactive model (see #271).  That
convergence is what lets ``acquire`` (run pre-``EnterWorktree`` from the
main CWD) and ``read_lock`` (re-invoked from inside a worktree by
``complete.md`` Step 3's Variant-A detection) agree on the same lock file
rather than reading a worktree-local one and falsely detecting "no lock".

The lock keeps a resolver **separate** from
``common._resolve_user_project_root`` on purpose: the shared resolver
accepts the first ``cortex/``-bearing ancestor (the worktree itself, from a
worktree CWD), so consolidating the two would silently reintroduce the
worktree false-negative.  The structural guard against that regression is
``tests/test_interactive_lock.py::test_resolve_main_repo_root_worktree_with_cortex_resolves_to_main``,
which fails on any walk-first implementation or a revert of the
``_lock_path`` / ``_events_log_path`` wiring.

``scan_live_locks`` is the deliberate exception: it does not call
``_resolve_main_repo_root()`` but takes ``project_root`` from its caller and
stays main-anchored via the overnight orchestrator's ``CORTEX_REPO_ROOT=main``
env-pin (intentionally unchanged).

Lock file schema (``cortex/lifecycle/{slug}/interactive.pid``):

.. code-block:: json

    {
        "schema_version": 1,
        "magic": "cortex-interactive-lock",
        "session_id": "<CLAUDE_CODE_SESSION_ID or null>",
        "pid": <int>,
        "start_time": <float | null>,
        "acquired_at": "<ISO 8601 UTC>"
    }

Liveness predicate (R4 eight-row branch table):

    1. env-var matches stored session_id → LIVE
    2. env-var absent/mismatch, os.kill → ESRCH  → STALE (esrch)
    3. env-var absent/mismatch, os.kill → EPERM  → LIVE  (conservative)
    4. env-var absent/mismatch, os.kill succeeds, lock start_time=null → LIVE (conservative)
    5. env-var absent/mismatch, os.kill succeeds, start_time non-null, matches ±2s → LIVE
    6. env-var absent/mismatch, os.kill succeeds, start_time non-null, mismatches → STALE (start_time_mismatch)
    7. env-var absent/mismatch, os.kill succeeds, start_time non-null, psutil.NoSuchProcess → STALE (nosuchprocess)
    8. env-var absent/mismatch, os.kill succeeds, start_time non-null, any other psutil exception → LIVE (conservative)

Atomic writes mirror ``cortex_command/overnight/state.py:421-464``
(tempfile + ``os.replace``, mode 0o600).

PID+start_time tolerance mirrors ``cortex_command/overnight/ipc.py:392-437``
(±2s). The ``_START_TIME_TOLERANCE_SECONDS`` constant is locally defined
to preserve module boundaries; do NOT import it from ``ipc.py``.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cortex_command.common import _resolve_user_project_root

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

_INTERACTIVE_LOCK_MAGIC = "cortex-interactive-lock"
_SCHEMA_VERSION = 1

# Mirror of ipc.py's _START_TIME_TOLERANCE_SECONDS — locally defined to
# preserve module boundaries (do not import from ipc.py).
_START_TIME_TOLERANCE_SECONDS = 2.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _main_root_from_gitfile(git_file: Path) -> Optional[Path]:
    """Resolve the MAIN repo root from a worktree ``.git`` *file*.

    A git worktree's ``.git`` is a file containing ``gitdir: <$GIT_DIR>``
    (the worktree's admin dir, ``<main>/.git/worktrees/<id>``). The main
    repo's ``.git`` is found via the ``commondir`` file inside ``$GIT_DIR``
    (relative pointer, typically ``../..``). The main repo root is that
    common ``.git``'s ``.parent``.

    Pure-Python parse only — no ``git rev-parse`` subprocess (empirically
    ``git rev-parse --git-common-dir`` exits 128 against a hand-built
    fixture and against non-``.git`` ``cortex/`` projects, per #271 research).

    Returns the candidate main root, or ``None`` when the gitfile is
    unreadable, the ``gitdir:`` line is malformed/missing, or the
    ``commondir`` file is present-but-unreadable. The caller applies the
    ``cortex/``-existence guard before trusting the result.
    """
    try:
        content = git_file.read_text(encoding="utf-8")
    except OSError:
        return None

    gitdir_target: Optional[str] = None
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("gitdir:"):
            gitdir_target = stripped[len("gitdir:"):].strip()
            break
    if not gitdir_target:
        return None

    git_dir = Path(gitdir_target)
    if not git_dir.is_absolute():
        # Relative ``gitdir:`` pointers resolve against the ``.git`` file's dir.
        git_dir = git_file.parent / git_dir
    git_dir = git_dir.resolve()

    commondir_file = git_dir / "commondir"
    if commondir_file.is_file():
        try:
            common_pointer = commondir_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not common_pointer:
            return None
        common = Path(common_pointer)
        if not common.is_absolute():
            # ``commondir`` pointers resolve relative to ``$GIT_DIR``.
            common = git_dir / common
        # ``common`` is now ``<main>/.git``; the main root is its parent.
        return common.resolve().parent

    # No ``commondir`` → synthetic direct ``gitdir: <main>/.git`` shape;
    # the main root is the gitdir target's parent.
    return git_dir.parent


def _resolve_main_repo_root() -> Path:
    """Resolve the MAIN repo root regardless of CWD (lock-scoped resolver).

    Distinct from ``common._resolve_user_project_root()`` (whose upward walk
    accepts the first ``cortex/``-bearing ancestor and so returns the
    *worktree* root when a git-tracked ``cortex/`` is co-located there). The
    interactive lock must agree on the **main** repo root from any CWD, so
    that ``acquire`` (run pre-``EnterWorktree`` from main) and ``read_lock``
    (re-invoked from inside a worktree) converge on the same lock file.

    Order is load-bearing (eager worktree-detect, NOT walk-first):

    (a) If ``CORTEX_REPO_ROOT`` is set, return it ``.resolve()``-canonicalized
        verbatim (no ``.git`` parse, no subprocess) — preserves the overnight
        env-pin.
    (b) Else eagerly walk from ``Path.cwd().resolve()`` upward; on the first
        ``.git`` entry that is a **file** (a worktree gitfile), parse it via
        :func:`_main_root_from_gitfile`. This branch takes precedence over any
        co-located ``cortex/``. A ``.git`` *directory* is a real-repo boundary
        — it never enters the parse branch; the walk stops and routes to (c),
        preserving #201's anti-leak boundary (an unrelated nested git repo
        with no ``cortex/`` still raises via (c)'s bounded walk).
    (b-guard) Only return the parsed candidate when ``(<candidate>/"cortex")``
        is a dir; a malformed/missing pointer or a non-``cortex/`` candidate
        falls through to (c).
    (c) Otherwise return a literal ``_resolve_user_project_root()`` call (the
        shared resolver — also keeps #241 R2's reference-count grep ≥ 2).
    """
    env_root = os.environ.get("CORTEX_REPO_ROOT")
    if env_root:
        return Path(env_root).resolve()

    current = Path.cwd().resolve()
    while True:
        git_entry = current / ".git"
        if git_entry.is_file():
            candidate = _main_root_from_gitfile(git_entry)
            if candidate is not None and (candidate / "cortex").is_dir():
                return candidate.resolve()
            # Malformed pointer or candidate lacks cortex/ → step (c).
            break
        if git_entry.is_dir():
            # Real-repo boundary; a .git directory never enters branch (b).
            break
        parent = current.parent
        if parent == current:
            break
        current = parent

    return _resolve_user_project_root()


def _lock_path(feature_slug: str) -> Path:
    """Return the absolute lock file path for a given feature slug.

    Path is always resolved against the main repo root (never CWD-relative).
    """
    root = _resolve_main_repo_root()
    return root / "cortex" / "lifecycle" / feature_slug / "interactive.pid"


def _events_log_path(feature_slug: str) -> Path:
    """Return the absolute events.log path for a given feature slug."""
    root = _resolve_main_repo_root()
    return root / "cortex" / "lifecycle" / feature_slug / "events.log"


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(tz=timezone.utc).isoformat()


def _emit_event(feature_slug: str, event: dict) -> None:
    """Append a JSON event row to the per-feature events.log.

    Creates the parent directory if absent.  ``event`` is written as a
    single JSON line with a leading ``ts`` field and ``event`` key.
    """
    log_path = _events_log_path(feature_slug)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    row = json.dumps(event, separators=(",", ":")) + "\n"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(row)


def _write_lock_atomic(lock_path: Path, payload: dict) -> None:
    """Write *payload* to *lock_path* atomically (tempfile + os.replace).

    Parent directory is created if absent.  File mode is 0o600.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, sort_keys=False) + "\n"

    fd, tmp_path = tempfile.mkstemp(
        dir=lock_path.parent,
        prefix=".interactive-lock-",
        suffix=".tmp",
    )
    closed = False
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        closed = True
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, lock_path)
    except BaseException:
        if not closed:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _get_start_time(pid: int) -> Optional[float]:
    """Return psutil create_time for *pid*, rounded to ms, or None.

    psutil is imported lazily so module load works on Pythons without it;
    callers needing the auxiliary PID liveness probe pay the import cost
    at first call.
    """
    import psutil

    try:
        return round(psutil.Process(pid).create_time(), 3)
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        return None


# ---------------------------------------------------------------------------
# Public primitives
# ---------------------------------------------------------------------------


def acquire_lock(feature_slug: str) -> bool:
    """Acquire the interactive lock for *feature_slug*.

    Checks for a live owner first.  If the existing lock is stale,
    emits ``interactive_lock_stale_recovered``, unlinks the stale file,
    and proceeds to write a fresh lock.  If the existing lock is live,
    emits ``interactive_lock_rejected_concurrent`` and returns False.

    Returns True on successful acquisition, False when a live owner blocks.

    Stale recovery is NON-destructive: no git state manipulation,
    no worktree removal, no filesystem writes beyond the lock file itself.
    Worktree directory contents are untouched.
    """
    lock_path = _lock_path(feature_slug)
    ts = _now_iso()
    current_session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")

    existing = read_lock(feature_slug)
    if existing is not None:
        live, recovery_reason = _verify_live_owner_with_reason(existing)
        if live:
            # Emit rejection event and return False
            _emit_event(feature_slug, {
                "ts": ts,
                "event": "interactive_lock_rejected_concurrent",
                "feature": feature_slug,
                "session_id": current_session_id,
                "existing_session_id": existing.get("session_id"),
                "existing_acquired_at": existing.get("acquired_at"),
            })
            return False
        else:
            # Stale lock — emit recovery event, unlink, then proceed
            _emit_event(feature_slug, {
                "ts": ts,
                "event": "interactive_lock_stale_recovered",
                "feature": feature_slug,
                "prior_session_id": existing.get("session_id"),
                "prior_pid": existing.get("pid"),
                "prior_start_time": existing.get("start_time"),
                "prior_acquired_at": existing.get("acquired_at"),
                "recovery_reason": recovery_reason,
            })
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

    # Build the fresh lock payload
    pid = os.getppid()
    start_time = _get_start_time(pid)
    acquired_at = _now_iso()

    payload = {
        "schema_version": _SCHEMA_VERSION,
        "magic": _INTERACTIVE_LOCK_MAGIC,
        "session_id": current_session_id,
        "pid": pid,
        "start_time": start_time,
        "acquired_at": acquired_at,
    }
    _write_lock_atomic(lock_path, payload)

    # Emit acquisition event
    session_id_source = "env" if current_session_id is not None else "env_absent_pid_only"
    _emit_event(feature_slug, {
        "ts": acquired_at,
        "event": "interactive_lock_acquired",
        "feature": feature_slug,
        "session_id": current_session_id,
        "pid": pid,
        "start_time": start_time,
        "acquired_at": acquired_at,
        "session_id_source": session_id_source,
    })

    return True


def read_lock(feature_slug: str) -> Optional[dict]:
    """Return the parsed lock dict for *feature_slug*, or None if absent.

    Returns None on missing file, JSON parse failure, or schema mismatch
    (defensive — prefer false-negative over false-positive blocking).
    """
    lock_path = _lock_path(feature_slug)
    if not lock_path.exists():
        return None
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("magic") != _INTERACTIVE_LOCK_MAGIC:
        return None
    return data


def _verify_live_owner_with_reason(lock: dict) -> tuple[bool, Optional[str]]:
    """Evaluate the R4 eight-row branch table.

    Returns ``(is_live: bool, recovery_reason: str | None)``.
    ``recovery_reason`` is one of ``{"esrch", "start_time_mismatch",
    "nosuchprocess"}`` when ``is_live`` is False, else None.
    """
    stored_session_id = lock.get("session_id")
    current_session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")

    # Row 1: env-var match → authoritative LIVE
    if (
        stored_session_id is not None
        and current_session_id is not None
        and stored_session_id == current_session_id
    ):
        return True, None

    # Rows 2-8: env-var absent or mismatch → fall through to PID check
    pid = lock.get("pid")
    if not isinstance(pid, int):
        # Cannot check PID; treat conservatively as STALE (no valid pid)
        return False, "esrch"

    try:
        os.kill(pid, 0)
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            # Row 2: process does not exist
            return False, "esrch"
        else:
            # Row 3: EPERM — process exists but we lack permission → LIVE (conservative)
            return True, None

    # os.kill succeeded → process is running
    lock_start_time = lock.get("start_time")

    if lock_start_time is None:
        # Row 4: no start_time recorded → LIVE (conservative)
        return True, None

    # Rows 5-8: start_time non-null, compare with psutil. Lazy import so
    # callers that never reach this branch (e.g., module loaded but liveness
    # never queried) don't require psutil at install time.
    import psutil

    try:
        actual_start_time = psutil.Process(pid).create_time()
    except psutil.NoSuchProcess:
        # Row 7: process vanished between kill and psutil query
        return False, "nosuchprocess"
    except Exception:
        # Row 8: any other psutil exception → LIVE (conservative)
        return True, None

    if abs(actual_start_time - lock_start_time) <= _START_TIME_TOLERANCE_SECONDS:
        # Row 5: start_time matches within ±2s
        return True, None
    else:
        # Row 6: start_time mismatch
        return False, "start_time_mismatch"


def verify_live_owner(lock: dict) -> bool:
    """Return True if the recorded session is judged live.

    Applies the R4 eight-row branch table (env-var authoritative,
    auxiliary PID is hint).  All eight cases are enumerated; no
    fall-through.
    """
    is_live, _ = _verify_live_owner_with_reason(lock)
    return is_live


def release_lock(feature_slug: str) -> None:
    """Unlink the lock file for *feature_slug* and emit a release event.

    Idempotent — if the lock file is already absent, emits the event
    with ``was_present: false`` and returns without error.
    """
    lock_path = _lock_path(feature_slug)
    ts = _now_iso()
    current_session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")

    was_present = lock_path.exists()
    if was_present:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            was_present = False

    _emit_event(feature_slug, {
        "ts": ts,
        "event": "interactive_lock_released",
        "feature": feature_slug,
        "session_id": current_session_id,
        "was_present": was_present,
    })


def scan_live_locks(project_root: Path) -> set[str]:
    """Return the set of feature slugs with live interactive owners.

    Scans ``project_root/cortex/lifecycle/*/interactive.pid`` for valid,
    live lock files.  Files that fail to parse or whose owner is STALE
    are silently skipped (no mutation, no events).  Used by the overnight
    orchestrator's per-round inverse scan (Phase 2).
    """
    lifecycle_dir = project_root / "cortex" / "lifecycle"
    if not lifecycle_dir.is_dir():
        return set()

    live_slugs: set[str] = set()
    for pid_file in lifecycle_dir.glob("*/interactive.pid"):
        feature_slug = pid_file.parent.name
        try:
            data = json.loads(pid_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("magic") != _INTERACTIVE_LOCK_MAGIC:
            continue
        is_live, _ = _verify_live_owner_with_reason(data)
        if is_live:
            live_slugs.add(feature_slug)

    return live_slugs


# ---------------------------------------------------------------------------
# Console-script entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    """Argparse entry for the ``cortex-interactive-lock`` console script.

    Subcommands:

    - ``acquire <slug>``       — acquire the lock; exit 0 on success, 1 if blocked
    - ``release <slug>``       — release the lock unconditionally
    - ``inspect <slug>``       — print the lock JSON and liveness verdict
    - ``force-release <slug>`` — unconditional unlink without event emission
    """
    parser = argparse.ArgumentParser(
        prog="cortex-interactive-lock",
        description="Manage per-feature interactive session locks.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    acquire_p = sub.add_parser("acquire", help="Acquire the interactive lock")
    acquire_p.add_argument("slug", help="Feature slug")

    release_p = sub.add_parser("release", help="Release the interactive lock")
    release_p.add_argument("slug", help="Feature slug")

    inspect_p = sub.add_parser("inspect", help="Inspect lock state and liveness")
    inspect_p.add_argument("slug", help="Feature slug")

    force_p = sub.add_parser(
        "force-release",
        help="Force-release the lock without event emission (for false-LIVE recovery)",
    )
    force_p.add_argument("slug", help="Feature slug")

    args = parser.parse_args(argv)

    if args.command == "acquire":
        ok = acquire_lock(args.slug)
        if not ok:
            lock = read_lock(args.slug)
            session_id = lock.get("session_id") if lock else "unknown"
            acquired_at = lock.get("acquired_at") if lock else "unknown"
            sys.stderr.write(
                f"Interactive session already active on this feature "
                f"(session {session_id}, acquired {acquired_at}). "
                f"Wait for it to exit, or work on a different feature, "
                f"or run `cortex-interactive-lock inspect {args.slug}` for details.\n"
            )
            return 1
        return 0

    elif args.command == "release":
        release_lock(args.slug)
        return 0

    elif args.command == "inspect":
        lock = read_lock(args.slug)
        if lock is None:
            sys.stdout.write(f"No lock file found for feature: {args.slug}\n")
            return 0
        is_live = verify_live_owner(lock)
        verdict = "LIVE" if is_live else "STALE"
        sys.stdout.write(json.dumps(lock, indent=2) + "\n")
        sys.stdout.write(f"Liveness verdict: {verdict}\n")
        return 0

    elif args.command == "force-release":
        lock_path = _lock_path(args.slug)
        try:
            lock_path.unlink()
            sys.stdout.write(f"Force-released lock for feature: {args.slug}\n")
        except FileNotFoundError:
            sys.stdout.write(f"No lock file to remove for feature: {args.slug}\n")
        return 0

    # Unreachable (argparse requires subcommand), but satisfies type checker
    return 1


if __name__ == "__main__":
    sys.exit(main())
