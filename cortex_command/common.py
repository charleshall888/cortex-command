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
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# TERMINAL_STATUSES — canonical set of "finished" backlog statuses
# ---------------------------------------------------------------------------
# The union of the status values used by update_item.py and generate_index.py.
# Includes "won't-do" for completeness, but callers passing a status via the
# shell should use "wont-do" (no apostrophe) — the apostrophe in "won't-do"
# will be misinterpreted by the shell if not carefully quoted.
#
# NOTE: claude/overnight/backlog.py defines its own TERMINAL_STATUSES tuple
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

def detect_lifecycle_phase(feature_dir: Path) -> str:
    """Detect the current lifecycle phase for a feature directory.

    Artifact-presence state machine:
      1. events.log contains "feature_complete" -> "complete"
      2. review.md has verdict:
           APPROVED          -> "complete"
           CHANGES_REQUESTED -> "implement"
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
        One of: "research", "specify", "plan", "implement",
                "review", "complete", "escalated".
    """
    # Step 1: event-based completion check
    events_log = feature_dir / "events.log"
    if events_log.is_file():
        content = events_log.read_text(errors="replace")
        if '"feature_complete"' in content:
            return "complete"

    # Step 2: review.md verdict
    review_md = feature_dir / "review.md"
    if review_md.is_file():
        content = review_md.read_text(errors="replace")
        matches = re.findall(r'"verdict"\s*:\s*"([A-Z_]+)"', content)
        if matches:
            verdict = matches[-1]
            if verdict == "APPROVED":
                return "complete"
            elif verdict == "CHANGES_REQUESTED":
                return "implement"
            elif verdict == "REJECTED":
                return "escalated"

    # Step 3: plan.md task completion
    plan_md = feature_dir / "plan.md"
    if plan_md.is_file():
        content = plan_md.read_text(errors="replace")
        total_matches = re.findall(r'\*\*Status\*\*:.*\[[ x]\]', content)
        total = len(total_matches)
        checked_matches = re.findall(r'\*\*Status\*\*:.*\[x\]', content)
        checked = len(checked_matches)

        if total > 0 and checked == total:
            return "review"
        else:
            return "implement"

    # Step 4: spec.md exists -> plan phase
    if (feature_dir / "spec.md").is_file():
        return "plan"

    # Step 5: research.md exists -> specify phase
    if (feature_dir / "research.md").is_file():
        return "specify"

    # Step 6: default -> research phase
    return "research"


# ---------------------------------------------------------------------------
# read_criticality
# ---------------------------------------------------------------------------

def read_criticality(
    feature: str,
    lifecycle_base: Path = Path("lifecycle"),
) -> str:
    """Read the most recent criticality from a feature's events.log.

    Scans the JSONL events log for lines containing a ``criticality``
    field and returns the value from the last such line. Defaults to
    ``"medium"`` if the file does not exist, is empty, or contains no
    criticality entries.

    Args:
        feature: Feature slug string (e.g. "my-feature").
        lifecycle_base: Base directory for lifecycle data.
            Defaults to ``Path("lifecycle")``.

    Returns:
        The most recent criticality string, or ``"medium"``.
    """
    events_path = lifecycle_base / feature / "events.log"
    if not events_path.exists():
        return "medium"

    last = "medium"
    for line in events_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "criticality" in record:
            last = record["criticality"]
    return last


# ---------------------------------------------------------------------------
# read_tier
# ---------------------------------------------------------------------------

def read_tier(
    feature: str,
    lifecycle_base: Path = Path("lifecycle"),
) -> str:
    """Read the most recent tier from a feature's events.log.

    Scans the JSONL events log for lines containing a ``tier``
    field and returns the value from the last such line. Defaults to
    ``"simple"`` if the file does not exist, is empty, or contains no
    tier entries.

    Args:
        feature: Feature slug string (e.g. "my-feature").
        lifecycle_base: Base directory for lifecycle data.
            Defaults to ``Path("lifecycle")``.

    Returns:
        The most recent tier string, or ``"simple"``.
    """
    events_path = lifecycle_base / feature / "events.log"
    if not events_path.exists():
        return "simple"

    last = "simple"
    for line in events_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "tier" in record:
            last = record["tier"]
    return last


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
    print(detect_lifecycle_phase(Path(args[0])))


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
