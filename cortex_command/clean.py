"""``cortex-clean`` console script — ad-hoc snapshot retention recipe.

Task 8 / Phase 2 of ticket-255 (gate-policy-taxonomy-and-critical-review).
Ships the skeleton for the ``cortex clean --adhoc`` retention recipe
specified in Requirement 9 of the spec. The ``--adhoc`` subcommand:

  1. Scans ``cortex/_adhoc/<sha[:2]>/<sha[2:]>/`` snapshot directories.
  2. Builds a pin set by walking all three iteration classes of
     ``cortex/lifecycle/``:
       - active lifecycles at ``cortex/lifecycle/<feature>/events.log`` (depth-1)
       - archived lifecycles at ``cortex/lifecycle/archive/<feature>/events.log``
         (depth-2)
       - sessions at ``cortex/lifecycle/sessions/<uuid>/events.log`` (depth-2)
     The materialized list is collected before iteration so a concurrent
     ``git mv`` (e.g. a lifecycle being archived) cannot produce a
     duplicate read or a missing pin; per-file ``FileNotFoundError``
     during iteration is tolerated.
  3. Deletes snapshot directories whose computed SHA (derived from
     ``<sha[:2]> + <sha[2:]>``) is NOT in the pin set AND whose
     directory mtime is older than 7 days.

Snapshot directories whose names do NOT match the SHA-256 fanout shape
(``^[0-9a-f]{2}/[0-9a-f]{62}/$``) are skipped — this guards against
false-positive deletion of stray non-snapshot directories.

In-flight snapshots (``.staging-*``, written by ``_snapshot_adhoc`` in
``cortex_command/critical_review.py`` before the final ``os.rename``)
and queued deletions (``.tombstone-*``, used by Task 9's tombstone-rename
atomicity logic) are ignored.

Malformed JSONL rows in any events.log are skipped with a stderr
``WARN: skipped malformed row at <path>:<lineno>: <reason>`` line; the
pin-set construction continues. Exit-code policy:

  0 — clean parse, deletions (if any) succeeded
  2 — at least one malformed JSONL row was skipped (warning)
  3+ — hard failure (unexpected exception, IO error outside per-file
       FileNotFoundError, etc.)

``--dry-run`` prints deletion candidates to stdout without modifying
anything.

Deferred to Task 9:
  - Tombstone-rename concurrency invariant (Task 9 replaces the plain
    ``shutil.rmtree`` here with rename-then-rmtree).
  - Concurrency test scenarios (d) and (e) from the spec.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RETENTION_SECONDS = 7 * 24 * 60 * 60  # 7 days

# Fanout dirs are 2 lowercase hex chars; leaf dirs are 62 lowercase hex
# chars (full SHA-256 = 64 hex chars = 2 prefix + 62 suffix).
_FANOUT_RE = re.compile(r"^[0-9a-f]{2}$")
_LEAF_RE = re.compile(r"^[0-9a-f]{62}$")


# ---------------------------------------------------------------------------
# Pin-set construction
# ---------------------------------------------------------------------------


def _enumerate_events_logs(lifecycle_root: Path) -> list[Path]:
    """Materialize the three-tier events.log path list for ``lifecycle_root``.

    Walks all three iteration classes:
      - ``<lifecycle_root>/*/events.log`` (active lifecycles, depth-1)
      - ``<lifecycle_root>/archive/*/events.log`` (archived, depth-2)
      - ``<lifecycle_root>/sessions/*/events.log`` (sessions, depth-2)

    Tolerates non-existent ``archive/`` or ``sessions/`` subdirectories
    (a fresh repo may not have them).

    The result is a single materialized list so callers iterate over a
    stable snapshot of the filesystem at scan time. Concurrent moves
    (e.g. ``git mv cortex/lifecycle/foo cortex/lifecycle/archive/foo``)
    after the list is built can still produce per-file
    ``FileNotFoundError`` when the caller opens an entry — the caller
    is responsible for tolerating that.
    """
    if not lifecycle_root.is_dir():
        return []
    active = list(lifecycle_root.glob("*/events.log"))
    archive_root = lifecycle_root / "archive"
    archived = (
        list(archive_root.glob("*/events.log")) if archive_root.is_dir() else []
    )
    sessions_root = lifecycle_root / "sessions"
    sessions = (
        list(sessions_root.glob("*/events.log")) if sessions_root.is_dir() else []
    )
    return active + archived + sessions


def _build_pin_set(
    lifecycle_root: Path,
    *,
    stderr=None,
) -> tuple[set[str], int]:
    """Return ``(pin_set, malformed_count)`` for all events.log files.

    Parses each events.log line-by-line. For each row that parses as
    JSON, if the row contains a ``snapshot_sha`` field, the value is
    added to the pin set. Rows without ``snapshot_sha`` are silently
    skipped (they pin nothing).

    Malformed JSONL rows are skipped with a stderr
    ``WARN: skipped malformed row at <path>:<lineno>: <reason>`` line
    and the malformed counter is incremented; parsing of the rest of
    the file continues.

    ``FileNotFoundError`` opening an enumerated events.log is tolerated
    silently — a concurrent ``git mv`` between enumeration and read
    can race with cleanup; the path is skipped without warning.
    """
    if stderr is None:
        stderr = sys.stderr
    pin_set: set[str] = set()
    malformed = 0
    for events_log in _enumerate_events_logs(lifecycle_root):
        try:
            fh = events_log.open("r", encoding="utf-8")
        except FileNotFoundError:
            # Race with a concurrent rename/move — drop silently and
            # continue with the next enumerated path.
            continue
        with fh:
            for lineno, raw in enumerate(fh, start=1):
                line = raw.rstrip("\n")
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    malformed += 1
                    print(
                        f"WARN: skipped malformed row at {events_log}:{lineno}: "
                        f"{exc.msg}",
                        file=stderr,
                    )
                    continue
                if not isinstance(event, dict):
                    continue
                sha = event.get("snapshot_sha")
                if isinstance(sha, str) and sha:
                    pin_set.add(sha)
    return pin_set, malformed


# ---------------------------------------------------------------------------
# Snapshot enumeration + deletion
# ---------------------------------------------------------------------------


def _enumerate_snapshot_dirs(adhoc_root: Path) -> list[tuple[Path, str]]:
    """Return ``[(leaf_dir, computed_sha), ...]`` for snapshot dirs under root.

    A snapshot directory has the shape
    ``<adhoc_root>/<sha[:2]>/<sha[2:]>/`` where ``<sha[:2]>`` is 2
    lowercase hex chars and ``<sha[2:]>`` is 62 lowercase hex chars.
    Any directory whose name does not match those regexes is skipped
    (silently — strays should not trigger deletion).

    ``.staging-*`` (in-flight snapshots) and ``.tombstone-*`` (queued
    deletions from Task 9) are ignored at both fanout and leaf levels.
    """
    if not adhoc_root.is_dir():
        return []
    out: list[tuple[Path, str]] = []
    for fanout in sorted(adhoc_root.iterdir()):
        if not fanout.is_dir():
            continue
        name = fanout.name
        if name.startswith(".staging-") or name.startswith(".tombstone-"):
            continue
        if not _FANOUT_RE.match(name):
            continue
        for leaf in sorted(fanout.iterdir()):
            if not leaf.is_dir():
                continue
            leaf_name = leaf.name
            if leaf_name.startswith(".staging-") or leaf_name.startswith(
                ".tombstone-"
            ):
                continue
            if not _LEAF_RE.match(leaf_name):
                continue
            out.append((leaf, name + leaf_name))
    return out


def _is_old(leaf_dir: Path, *, now: float, retention: int) -> bool:
    """Return True if ``leaf_dir``'s mtime is older than ``retention`` seconds."""
    try:
        mtime = leaf_dir.stat().st_mtime
    except FileNotFoundError:
        return False
    return (now - mtime) > retention


def _delete_snapshot(leaf_dir: Path) -> None:
    """Delete the snapshot directory.

    Task 8 uses plain ``shutil.rmtree``; Task 9 will replace this with
    a tombstone-rename pattern for atomicity against concurrent readers
    and concurrent cleaners.
    """
    shutil.rmtree(leaf_dir, ignore_errors=False)


# ---------------------------------------------------------------------------
# --adhoc subcommand
# ---------------------------------------------------------------------------


def run_adhoc(
    repo_root: Path,
    *,
    dry_run: bool = False,
    now: float | None = None,
    retention: int = RETENTION_SECONDS,
    stdout=None,
    stderr=None,
) -> int:
    """Execute the ``--adhoc`` retention pass against ``repo_root``.

    Returns the integer exit code:
      0 — clean parse, deletions completed (or no deletions needed)
      2 — at least one malformed JSONL row was skipped during pin-set
          construction
      3+ — hard failure (unexpected exception during deletion)

    ``dry_run`` prints deletion candidates without modifying anything.
    ``now`` and ``retention`` are injectable for tests.
    """
    if stdout is None:
        stdout = sys.stdout
    if stderr is None:
        stderr = sys.stderr
    if now is None:
        now = time.time()

    lifecycle_root = repo_root / "cortex" / "lifecycle"
    adhoc_root = repo_root / "cortex" / "_adhoc"

    pin_set, malformed = _build_pin_set(lifecycle_root, stderr=stderr)
    snapshots = _enumerate_snapshot_dirs(adhoc_root)

    candidates: list[Path] = []
    for leaf, sha in snapshots:
        if sha in pin_set:
            continue
        if not _is_old(leaf, now=now, retention=retention):
            continue
        candidates.append(leaf)

    if dry_run:
        for c in candidates:
            print(str(c), file=stdout)
        return 2 if malformed else 0

    try:
        for c in candidates:
            _delete_snapshot(c)
    except Exception as exc:  # noqa: BLE001 — hard-failure surface
        print(f"ERROR: failed to delete snapshot: {exc}", file=stderr)
        return 3

    return 2 if malformed else 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-clean",
        description=(
            "Cortex cleanup recipes. Currently ships --adhoc for "
            "cortex/_adhoc/ snapshot retention (7-day + events.log-pinned)."
        ),
    )
    parser.add_argument(
        "--adhoc",
        action="store_true",
        help="Run the ad-hoc snapshot retention pass.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print deletion candidates without modifying anything.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help=(
            "Repository root (parent of cortex/). Defaults to the current "
            "working directory."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """``cortex-clean`` console-script entry point.

    Returns an integer exit code via ``sys.exit``-compatible semantics.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.adhoc:
        parser.print_help(sys.stderr)
        return 3

    repo_root = (args.repo_root or Path.cwd()).resolve()
    return run_adhoc(repo_root, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
