"""Shared utilities for the claude toolchain.

Consolidates duplicated functions from overnight, pipeline, and backlog
modules into a single canonical location. All callers should import from
here instead of maintaining local copies.

Constants:
    TERMINAL_STATUSES -- Canonical set of "finished" backlog statuses.

Functions:
    slugify          -- Convert a title to a kebab-case slug.
    detect_lifecycle_phase -- Determine current lifecycle phase from artifacts.
    read_criticality -- Read the most recent criticality from events.log.
    read_tier        -- Read the most recent tier from events.log.
    requires_review  -- Gating matrix: does this tier+criticality need review?
    compute_dependency_batches -- Topological sort of tasks into batches.
    mark_task_done_in_plan -- Check off a task in a plan.md file.
    durable_fsync    -- fsync with F_FULLFSYNC on macOS, os.fsync elsewhere.
    atomic_write     -- Write a file atomically via temp + os.replace.
    normalize_status -- Map legacy status values to canonical vocabulary.
    _resolve_user_project_root -- Resolve user's cortex project root at call time.

Exceptions:
    CortexProjectRootError -- Raised when the user's project root cannot be resolved.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from functools import lru_cache
from pathlib import Path


# ---------------------------------------------------------------------------
# _resolve_user_project_root — single source of truth for user's project path
# ---------------------------------------------------------------------------
# Distinct from `cortex_command.init.handler:_resolve_repo_root`, which uses
# `git rev-parse --show-toplevel` and is reserved for `cortex init`'s own
# dispatch path (see spec Technical Constraints).


class CortexProjectRootError(RuntimeError):
    """Raised when the user's cortex project root cannot be resolved.

    Indicates that ``CORTEX_REPO_ROOT`` is unset and the current working
    directory does not look like a cortex project (no ``lifecycle/`` or
    ``backlog/`` subdirectory).
    """


def _resolve_user_project_root() -> Path:
    """Resolve the directory containing the user's cortex project.

    Returns ``Path(os.environ["CORTEX_REPO_ROOT"])`` when that environment
    variable is set (the user's explicit override is trusted verbatim).
    Otherwise returns ``Path.cwd().resolve()`` after verifying that the
    CWD looks like a cortex project (contains ``lifecycle/`` or ``backlog/``).

    This function is invoked at call time (never at module load) so that
    worker subprocesses, pytest fixtures using ``monkeypatch.chdir``, and
    users who chdir between cortex invocations in a long-running shell all
    resolve the project root correctly at the moment it is needed.

    Returns:
        Resolved absolute path to the user's cortex project root.

    Raises:
        CortexProjectRootError: When ``CORTEX_REPO_ROOT`` is unset and CWD
            does not contain ``lifecycle/`` or ``backlog/``.
    """
    env_root = os.environ.get("CORTEX_REPO_ROOT")
    if env_root:
        return Path(env_root)

    cwd = Path.cwd().resolve()
    if not (cwd / "lifecycle").is_dir() and not (cwd / "backlog").is_dir():
        raise CortexProjectRootError(
            "Run from your cortex project root, set CORTEX_REPO_ROOT, or "
            "create a new project here with `git init && cortex init` "
            "(cortex init requires a git repository)."
        )
    return cwd


# ---------------------------------------------------------------------------
# TERMINAL_STATUSES — canonical set of "finished" backlog statuses
# ---------------------------------------------------------------------------
# The union of the status values used by update_item.py and generate_index.py.
# Includes "won't-do" for completeness, but callers passing a status via the
# shell should use "wont-do" (no apostrophe) — the apostrophe in "won't-do"
# will be misinterpreted by the shell if not carefully quoted.
#
# NOTE: cortex_command/overnight/backlog.py defines its own TERMINAL_STATUSES tuple
# (5 values, missing the wont-do variants). Unifying that is a follow-up task.

TERMINAL_STATUSES: frozenset[str] = frozenset({
    "complete",
    "abandoned",
    "done",
    "resolved",
    "wontfix",
    "won't-do",
    "wont-do",
})


# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------

def slugify(title: str) -> str:
    """Convert a title to a lowercase-kebab-case slug.

    Canonical 4-line implementation from overnight/plan.py. Strips
    non-alphanumeric characters (except hyphens and spaces), collapses
    whitespace/hyphens, and lowercases the result.

    Examples:
        >>> slugify("Backlog Readiness Gate")
        'backlog-readiness-gate'
        >>> slugify("Create session plan artifact and /overnight skill")
        'create-session-plan-artifact-and-overnight-skill'
        >>> slugify("Fix duplicate test function in test_gameplay.gd")
        'fix-duplicate-test-function-in-test-gameplaygd'
        >>> slugify("Arena bounds tests — verify player/enemy containment")
        'arena-bounds-tests-verify-player-enemy-containment'
    """
    slug = title.lower()
    slug = re.sub(r"[_/]", " ", slug)
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug)
    slug = slug.strip("-")
    return slug


# ---------------------------------------------------------------------------
# detect_lifecycle_phase
# ---------------------------------------------------------------------------

def _stat_key(path: Path) -> tuple[bool, int, int]:
    """Return ``(exists, mtime_ns, size)`` for a path.

    Used as a per-file cache-key component for the lru-cached lifecycle
    readers. ``size`` closes the sub-mtime_ns append window (an append
    bumps file size even when mtime collides at filesystem resolution);
    ``exists`` distinguishes a missing file from a zero-byte/zero-mtime
    file.
    """
    try:
        s = path.stat()
        return (True, s.st_mtime_ns, s.st_size)
    except FileNotFoundError:
        return (False, 0, 0)


@lru_cache(maxsize=128)
def _detect_lifecycle_phase_inner(
    feature_dir_str: str,
    events_key: tuple[bool, int, int],
    plan_key: tuple[bool, int, int],
    review_key: tuple[bool, int, int],
    spec_key: tuple[bool, int, int],
    research_key: tuple[bool, int, int],
) -> dict[str, str | int]:
    """Cached implementation of :func:`detect_lifecycle_phase`.

    The five ``*_key`` tuples encode per-file ``(exists, mtime_ns, size)``
    state for events.log, plan.md, review.md, spec.md, and research.md
    so cached results invalidate when any of those files change.
    """
    feature_dir = Path(feature_dir_str)
    # Compute plan progress (used by the dict return regardless of phase).
    plan_md = feature_dir / "plan.md"
    checked = 0
    total = 0
    if plan_md.is_file():
        plan_content = plan_md.read_text(errors="replace")
        total = len(re.findall(r'\*\*Status\*\*:.*\[[ x]\]', plan_content))
        checked = len(re.findall(r'\*\*Status\*\*:.*\[x\]', plan_content))

    # Compute cycle from review.md verdict matches (default 1 when absent).
    review_md = feature_dir / "review.md"
    review_content: str | None = None
    cycle = 1
    verdict_matches: list[str] = []
    if review_md.is_file():
        review_content = review_md.read_text(errors="replace")
        verdict_matches = re.findall(
            r'"verdict"\s*:\s*"([A-Z_]+)"', review_content
        )
        if verdict_matches:
            cycle = len(verdict_matches)

    # Step 1: event-based completion check
    events_log = feature_dir / "events.log"
    if events_log.is_file():
        content = events_log.read_text(errors="replace")
        if '"feature_complete"' in content:
            return {
                "phase": "complete",
                "checked": checked,
                "total": total,
                "cycle": cycle,
            }

    # Step 2: review.md verdict
    if verdict_matches:
        verdict = verdict_matches[-1]
        if verdict == "APPROVED":
            return {
                "phase": "complete",
                "checked": checked,
                "total": total,
                "cycle": cycle,
            }
        elif verdict == "CHANGES_REQUESTED":
            return {
                "phase": "implement-rework",
                "checked": checked,
                "total": total,
                "cycle": cycle,
            }
        elif verdict == "REJECTED":
            return {
                "phase": "escalated",
                "checked": checked,
                "total": total,
                "cycle": cycle,
            }

    # Step 3: plan.md task completion
    if plan_md.is_file():
        if total > 0 and checked == total:
            return {
                "phase": "review",
                "checked": checked,
                "total": total,
                "cycle": cycle,
            }
        else:
            return {
                "phase": "implement",
                "checked": checked,
                "total": total,
                "cycle": cycle,
            }

    # Step 4: spec.md exists -> plan phase
    if (feature_dir / "spec.md").is_file():
        return {
            "phase": "plan",
            "checked": checked,
            "total": total,
            "cycle": cycle,
        }

    # Step 5: research.md exists -> specify phase
    if (feature_dir / "research.md").is_file():
        return {
            "phase": "specify",
            "checked": checked,
            "total": total,
            "cycle": cycle,
        }

    # Step 6: default -> research phase
    return {
        "phase": "research",
        "checked": checked,
        "total": total,
        "cycle": cycle,
    }


def detect_lifecycle_phase(feature_dir: Path) -> dict[str, str | int]:
    """Detect the current lifecycle phase for a feature directory.

    Artifact-presence state machine:
      1. events.log contains "feature_complete" -> "complete"
      2. review.md has verdict:
           APPROVED          -> "complete"
           CHANGES_REQUESTED -> "implement-rework"
           REJECTED          -> "escalated"
      3. plan.md exists:
           all **Status**: [x] (and at least one) -> "review"
           otherwise                              -> "implement"
      4. spec.md exists    -> "plan"
      5. research.md exists -> "specify"
      6. (default)          -> "research"

    Args:
        feature_dir: Path to the lifecycle feature directory
                     (e.g. Path("lifecycle/my-feature")).

    Returns:
        A dict with keys:
          - phase: one of "research", "specify", "plan", "implement",
            "implement-rework", "review", "complete", "escalated".
          - checked: integer count of completed plan tasks (0 when no plan.md).
          - total: integer count of total plan tasks (0 when no plan.md).
          - cycle: integer review-cycle number (1 when no review.md, otherwise
            the count of `verdict` regex matches in review.md).
    """
    events_key = _stat_key(feature_dir / "events.log")
    plan_key = _stat_key(feature_dir / "plan.md")
    review_key = _stat_key(feature_dir / "review.md")
    spec_key = _stat_key(feature_dir / "spec.md")
    research_key = _stat_key(feature_dir / "research.md")
    return _detect_lifecycle_phase_inner(
        str(feature_dir),
        events_key,
        plan_key,
        review_key,
        spec_key,
        research_key,
    )


# Expose the cached inner helper on the public API so callers (and tests)
# can introspect via ``detect_lifecycle_phase.__wrapped__`` per spec R1.
detect_lifecycle_phase.__wrapped__ = _detect_lifecycle_phase_inner  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# read_criticality
# ---------------------------------------------------------------------------

@lru_cache(maxsize=128)
def _read_criticality_inner(
    events_path_str: str,
    exists: bool,
    mtime_ns: int,
    size: int,
) -> str:
    """Cached implementation of :func:`read_criticality`.

    The ``(exists, mtime_ns, size)`` triple is part of the cache key so
    cached results invalidate when the events.log file changes.
    """
    if not exists:
        return "medium"

    criticality = "medium"
    found = False
    for line in Path(events_path_str).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = record.get("event")
        if kind == "lifecycle_start":
            value = record.get("criticality")
            if isinstance(value, str) and value:
                criticality = value
                found = True
        elif kind == "criticality_override":
            value = record.get("to")
            if isinstance(value, str) and value:
                criticality = value
                found = True
    return criticality if found else "medium"


def read_criticality(
    feature: str,
    lifecycle_base: Path = Path("lifecycle"),
) -> str:
    """Read the canonical criticality from a feature's events.log.

    Returns the ``criticality`` field from the most recent
    ``lifecycle_start`` event, superseded by the ``to`` field of any
    later ``criticality_override`` event. Stray ``criticality`` fields
    on other event types (e.g. ``critical_review``) are ignored.
    Defaults to ``"medium"`` if the file does not exist, is empty, or
    contains no relevant event.

    Args:
        feature: Feature slug string (e.g. "my-feature").
        lifecycle_base: Base directory for lifecycle data.
            Defaults to ``Path("lifecycle")``.

    Returns:
        The most recent criticality string, or ``"medium"``.
    """
    events_path = lifecycle_base / feature / "events.log"
    exists, mtime_ns, size = _stat_key(events_path)
    return _read_criticality_inner(str(events_path), exists, mtime_ns, size)


# Expose the cached inner helper on the public API for spec R1 introspection.
read_criticality.__wrapped__ = _read_criticality_inner  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# read_tier
# ---------------------------------------------------------------------------

@lru_cache(maxsize=128)
def _read_tier_inner(
    events_path_str: str,
    exists: bool,
    mtime_ns: int,
    size: int,
) -> str:
    """Cached implementation of :func:`read_tier`.

    The ``(exists, mtime_ns, size)`` triple is part of the cache key so
    cached results invalidate when the events.log file changes.
    """
    if not exists:
        return "simple"

    tier = "simple"
    found = False
    for line in Path(events_path_str).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = record.get("event")
        if kind == "lifecycle_start":
            value = record.get("tier")
            if isinstance(value, str) and value:
                tier = value
                found = True
        elif kind == "complexity_override":
            value = record.get("to")
            if isinstance(value, str) and value:
                tier = value
                found = True
    return tier if found else "simple"


def read_tier(
    feature: str,
    lifecycle_base: Path = Path("lifecycle"),
) -> str:
    """Read the active complexity tier from a feature's events.log.

    Scans the JSONL events log and returns the ``tier`` field from the
    most recent ``lifecycle_start`` event, superseded by the ``to`` field
    of any later ``complexity_override`` event. Defaults to ``"simple"``
    if the file does not exist, is empty, or contains no relevant event.

    Args:
        feature: Feature slug string (e.g. "my-feature").
        lifecycle_base: Base directory for lifecycle data.
            Defaults to ``Path("lifecycle")``.

    Returns:
        The active tier string, or ``"simple"``.
    """
    events_path = lifecycle_base / feature / "events.log"
    exists, mtime_ns, size = _stat_key(events_path)
    return _read_tier_inner(str(events_path), exists, mtime_ns, size)


# Expose the cached inner helper on the public API for spec R1 introspection.
read_tier.__wrapped__ = _read_tier_inner  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# requires_review
# ---------------------------------------------------------------------------

def requires_review(tier: str, criticality: str) -> bool:
    """Determine whether a feature requires post-merge review.

    Encodes the gating matrix:
        - complex tier at any criticality -> review
        - any tier at high or critical criticality -> review
        - otherwise -> skip

    Args:
        tier: Feature tier (e.g. "simple", "complex").
        criticality: Feature criticality (e.g. "low", "medium",
            "high", "critical").

    Returns:
        True if the feature should go through review.
    """
    return tier == "complex" or criticality in ("high", "critical")


# ---------------------------------------------------------------------------
# compute_dependency_batches
# ---------------------------------------------------------------------------

def compute_dependency_batches(tasks: list) -> list[list]:
    """Group tasks into dependency-ordered batches.

    Batch 0: tasks with no dependencies. Batch N: tasks whose deps
    all appear in batches 0..N-1. Tasks already done are skipped.

    Each task must have ``.number``, ``.status``, and ``.depends_on``
    attributes (matching ``FeatureTask`` from the pipeline parser).

    Args:
        tasks: List of task objects with number, status, depends_on.

    Returns:
        Ordered list of batches; each batch is a list of tasks
        that can run concurrently.

    Raises:
        ValueError: If a dependency cycle prevents progress.
    """
    pending = [t for t in tasks if t.status != "done"]
    done_numbers: set[int] = {t.number for t in tasks if t.status == "done"}
    batches: list[list] = []
    assigned: set[int] = set(done_numbers)

    while pending:
        batch = [t for t in pending if all(d in assigned for d in t.depends_on)]
        if not batch:
            remaining = [t.number for t in pending]
            raise ValueError(
                f"Dependency cycle or unresolvable deps among tasks: {remaining}"
            )
        batches.append(batch)
        for t in batch:
            assigned.add(t.number)
        pending = [t for t in pending if t.number not in assigned]

    return batches


# ---------------------------------------------------------------------------
# mark_task_done_in_plan
# ---------------------------------------------------------------------------

def mark_task_done_in_plan(plan_path: Path, task_number: int) -> None:
    """Update a task's status in a feature plan from [ ] to [x].

    Reads the plan file, finds the ``### Task N:`` heading and its
    ``**Status**: [ ]`` field, replaces with ``[x]``, and writes
    back atomically. Does nothing if the file does not exist or the
    pattern is not found.

    Args:
        plan_path: Path to the plan.md file.
        task_number: The task number to mark as done.
    """
    if not plan_path.exists():
        return

    text = plan_path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"(### Task {task_number}:.*?-\s+\*\*Status\*\*:\s*)\[ \]",
        re.DOTALL,
    )
    updated = pattern.sub(r"\1[x]", text, count=1)
    if updated != text:
        atomic_write(plan_path, updated)


# ---------------------------------------------------------------------------
# durable_fsync
# ---------------------------------------------------------------------------

def durable_fsync(fd: int) -> None:
    """Flush a file descriptor durably to stable storage.

    On macOS, ``os.fsync()`` does **not** guarantee data reaches the
    physical drive — it may only flush to the drive's volatile write
    cache.  ``fcntl.fcntl(fd, fcntl.F_FULLFSYNC)`` issues a barrier
    that waits for the drive to confirm persistence.

    On all other platforms this falls back to ``os.fsync(fd)`` which is
    sufficient on Linux (ext4/btrfs default to barrier writes).

    Args:
        fd: An open, writable file descriptor.
    """
    if sys.platform == "darwin":
        import fcntl

        fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
    else:
        os.fsync(fd)


# ---------------------------------------------------------------------------
# atomic_write
# ---------------------------------------------------------------------------

def atomic_write(
    path: Path,
    content: str,
    encoding: str = "utf-8",
) -> None:
    """Write a file atomically via tempfile + os.replace.

    Creates a temporary file in the same directory as ``path``, writes
    content, then atomically replaces the target. On any exception the
    temp file is cleaned up so no partial writes are left behind.

    Args:
        path: Destination file path.
        content: String content to write.
        encoding: Text encoding (default ``"utf-8"``).
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.stem}-",
        suffix=".tmp",
    )
    closed = False
    try:
        os.write(fd, content.encode(encoding))
        durable_fsync(fd)
        os.close(fd)
        closed = True
        os.replace(tmp_path, path)
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


# ---------------------------------------------------------------------------
# normalize_status
# ---------------------------------------------------------------------------

_STATUS_MAP: dict[str, str] = {
    "open": "backlog",
    "in-progress": "in_progress",
    "blocked": "backlog",
    "done": "complete",
    "resolved": "complete",
    "closed": "complete",
    "wontfix": "abandoned",
    "ready": "refined",
}


def normalize_status(raw: str) -> str:
    """Map a legacy status value to the canonical vocabulary.

    Known legacy mappings:
        open        -> backlog
        in-progress -> in_progress
        blocked     -> backlog
        done        -> complete
        resolved    -> complete
        closed      -> complete
        wontfix     -> abandoned
        ready       -> refined

    Unknown values pass through unchanged.

    Args:
        raw: The raw status string to normalize.

    Returns:
        The canonical status string.
    """
    return _STATUS_MAP.get(raw, raw)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _cli_detect_phase(args: list[str]) -> None:
    """Handle ``detect-phase <dir>`` subcommand."""
    if len(args) != 1:
        print("Usage: python3 -m cortex_command.common detect-phase <dir>", file=sys.stderr)
        sys.exit(1)
    result = detect_lifecycle_phase(Path(args[0]))
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")


def _cli_normalize_status(args: list[str]) -> None:
    """Handle ``normalize-status <status>`` subcommand."""
    if len(args) != 1:
        print("Usage: python3 -m cortex_command.common normalize-status <status>", file=sys.stderr)
        sys.exit(1)
    print(normalize_status(args[0]))


if __name__ == "__main__":
    argv = sys.argv[1:]

    if not argv:
        print(
            "Usage: python3 -m cortex_command.common <subcommand> [args]\n"
            "\n"
            "Subcommands:\n"
            "  detect-phase <dir>      Detect lifecycle phase for a feature directory\n"
            "  normalize-status <str>  Normalize a legacy status value",
            file=sys.stderr,
        )
        sys.exit(1)

    subcommand = argv[0]
    sub_args = argv[1:]

    if subcommand == "detect-phase":
        _cli_detect_phase(sub_args)
    elif subcommand == "normalize-status":
        _cli_normalize_status(sub_args)
    else:
        print(f"Unknown subcommand: {subcommand}", file=sys.stderr)
        sys.exit(1)
