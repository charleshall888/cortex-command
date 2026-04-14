"""Outcome routing layer extracted from batch_runner.py.

This module contains the outcome routing layer extracted from
batch_runner.py. This module must not import from
`claude.overnight.batch_runner` or `claude.overnight.orchestrator`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from claude.overnight.batch_runner import BatchResult, BatchConfig

from claude.overnight.constants import CIRCUIT_BREAKER_THRESHOLD
from claude.overnight.events import (
    BACKLOG_WRITE_FAILED,
    log_event as overnight_log_event,
)
from claude.overnight.state import _normalize_repo_key
from claude.overnight.types import FeatureResult


logger = logging.getLogger(__name__)


@dataclass
class OutcomeContext:
    batch_result: BatchResult
    lock: asyncio.Lock
    consecutive_pauses_ref: list[int]
    recovery_attempts_map: dict[str, int]
    worktree_paths: dict[str, Path]
    worktree_branches: dict[str, str]
    repo_path_map: dict[str, Path | None]
    integration_worktrees: dict[str, Path]
    integration_branches: dict[str, str]
    session_id: str
    backlog_ids: dict[str, int | None]
    feature_names: list[str]
    config: BatchConfig


# ---------------------------------------------------------------------------
# Per-repo integration branch routing
# ---------------------------------------------------------------------------


def _effective_base_branch(
    repo_path: Path | None,
    integration_branches: dict[str, str],
    default: str,
) -> str:
    """Return the integration branch name for a given repo.

    If ``repo_path`` is not None and its string form is a key in
    ``integration_branches``, returns that mapped branch name.
    Otherwise returns ``default``.

    Args:
        repo_path: Absolute path to the target repository, or None for the
            default (current) repository.
        integration_branches: Mapping of absolute repo path string to
            integration branch name (from OvernightState.integration_branches).
        default: Fallback branch name — typically config.base_branch, which
            is always set to the home repo's integration branch by the
            orchestrator.

    Returns:
        The effective integration branch name for this repo.
    """
    if repo_path is not None and _normalize_repo_key(str(repo_path)) in integration_branches:
        return integration_branches[_normalize_repo_key(str(repo_path))]
    return default


def _effective_merge_repo_path(
    repo_path: Path | None,
    integration_worktrees: dict[str, str],
    integration_branches: dict[str, str],
    session_id: str,
) -> Path | None:
    """Return the integration worktree path for a given repo.

    Resolves the worktree that merge operations should target so merges
    run against an isolated integration worktree instead of the user's
    live working tree.

    Resolution order:
      1. ``repo_path is None`` → return ``None`` (default-repo case).
      2. Cached hit: key already in ``integration_worktrees`` and the
         path exists on disk → return it.
      3. Lazy creation: ``integration_branches`` must contain the key so
         we know which branch to check out.  Creates a new git worktree
         under ``$TMPDIR/overnight-worktrees/``.
      4. Handles ``git worktree add`` edge cases: "already exists" path
         collisions and stale tracking left after a TMPDIR wipe.

    Args:
        repo_path: Absolute path to the target repository, or None for
            the default (current) repository.
        integration_worktrees: Mutable mapping of normalized repo-path
            string to worktree path string (from
            ``OvernightState.integration_worktrees``).  May be mutated
            on lazy creation.
        integration_branches: Mapping of normalized repo-path string to
            integration branch name.
        session_id: Current overnight session identifier, used to
            namespace the worktree directory.

    Returns:
        Path to the integration worktree for this repo, or None.

    Raises:
        RuntimeError: If the repo has no configured integration branch
            or worktree creation fails.
    """
    if repo_path is None:
        return None

    key = _normalize_repo_key(str(repo_path))

    # Cached hit — worktree already exists on disk.
    if key in integration_worktrees and Path(integration_worktrees[key]).exists():
        return Path(integration_worktrees[key])

    # Need lazy creation — require an integration branch.
    if key not in integration_branches:
        raise RuntimeError(
            f"No integration branch configured for repo {repo_path!s} "
            f"(normalized key: {key}); cannot create worktree"
        )

    branch = integration_branches[key]
    tmpdir = os.environ.get("TMPDIR", "/tmp")
    repo_dir_name = Path(repo_path).name
    worktree_path = Path(tmpdir) / "overnight-worktrees" / f"{session_id}-lazy-{repo_dir_name}"

    # Build env without GIT_DIR to prevent git from inheriting an override.
    env = {k: v for k, v in os.environ.items() if k != "GIT_DIR"}

    result = subprocess.run(
        ["git", "worktree", "add", str(worktree_path), branch],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        env=env,
    )

    if result.returncode == 0:
        logger.warning(
            "Lazily created integration worktree for %s at %s",
            repo_path,
            worktree_path,
        )
        integration_worktrees[key] = str(worktree_path)
        return Path(worktree_path)

    stderr = result.stderr

    # Path collision — concurrent creation already placed a worktree here.
    if "already exists" in stderr:
        cached = integration_worktrees.get(key)
        if cached:
            return Path(cached)
        if worktree_path.exists():
            return worktree_path
        raise RuntimeError(
            f"Worktree path collision for {repo_path!s} but path "
            f"{worktree_path} does not exist: {stderr}"
        )

    # Stale git tracking — branch registered to a now-deleted path after
    # TMPDIR was cleared.  Prune and retry once.
    if "already checked out at" in stderr:
        prune_result = subprocess.run(
            ["git", "worktree", "prune"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            env=env,
        )
        retry = subprocess.run(
            ["git", "worktree", "add", str(worktree_path), branch],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            env=env,
        )
        if retry.returncode == 0:
            logger.warning(
                "Lazily created integration worktree for %s at %s "
                "(after pruning stale tracking)",
                repo_path,
                worktree_path,
            )
            integration_worktrees[key] = str(worktree_path)
            return Path(worktree_path)
        raise RuntimeError(
            f"Failed to create worktree for {repo_path!s} after pruning: "
            f"{retry.stderr}"
        )

    # Unknown failure.
    raise RuntimeError(
        f"Failed to create integration worktree for {repo_path!s}: {stderr}"
    )


# ---------------------------------------------------------------------------
# Shared helpers (called from _apply_feature_result and run_batch)
# ---------------------------------------------------------------------------


def _get_changed_files(feature: str, base_branch: str, branch: str | None = None) -> list[str]:
    """Get list of files changed between base branch and feature branch.

    ``branch`` is the fully-qualified branch name (e.g. ``pipeline/feat-2``).
    When omitted, falls back to the unsuffixed ``pipeline/{feature}`` construction.
    """
    actual_branch = branch if branch is not None else f"pipeline/{feature}"
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_branch}...{actual_branch}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return [f for f in result.stdout.strip().splitlines() if f]
    except (subprocess.TimeoutExpired, OSError):
        pass
    return []


def _classify_no_commit(feature: str, branch: str, base_branch: str) -> str:
    """Classify why a feature completed with no new commits.

    Inspects git state to determine whether the branch is stale (base has
    moved past it) or the agent simply produced no changes.  Always returns
    a non-empty human-readable string suitable for the morning report.
    """
    fallback = f"completed with no new commits (branch: {branch})"
    try:
        result = subprocess.run(
            ["git", "rev-list", f"{branch}..{base_branch}", "--count"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return fallback
        count = int(result.stdout.strip())
        if count > 0:
            return (
                f"branch appears stale — base branch ({base_branch}) has "
                f"{count} commit(s) already merged or ahead of {branch}"
            )
        return f"no changes produced — {branch} is at {base_branch} HEAD with no agent commits"
    except (subprocess.TimeoutExpired, OSError, Exception):
        return fallback


# ---------------------------------------------------------------------------
# Backlog write-back (R13)
# ---------------------------------------------------------------------------

# Ensure project root is importable for backlog/update_item.py
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Runtime backlog directory — set from overnight state so write-backs find items
# in external repos. Falls back to _PROJECT_ROOT / "backlog" when unset.
_backlog_dir: Optional[Path] = None


def set_backlog_dir(path: Path) -> None:
    """Set the backlog directory used by write-back helpers at runtime."""
    global _backlog_dir
    _backlog_dir = path


from backlog.update_item import update_item as _backlog_update_item  # noqa: E402
from backlog.update_item import _find_item as _backlog_find_item  # noqa: E402

# Mapping from overnight internal status to canonical backlog fields (R13).
# Keys: overnight status; Values: dict of backlog fields to write.
# "session_id" is a sentinel — "_CURRENT_" is replaced at call time.
_OVERNIGHT_TO_BACKLOG: dict[str, dict[str, Any]] = {
    "running": {
        "status": "implementing",
        "session_id": "_CURRENT_",
    },
    "merged": {
        "status": "complete",
        "session_id": None,
    },
    "paused": {
        "status": "in_progress",
        "session_id": None,
    },
    "failed": {
        "status": "refined",
        "session_id": None,
    },
    "deferred": {
        "status": "backlog",
        "session_id": None,
    },
}


def _find_backlog_item_path(feature: str, backlog_id: Optional[int] = None) -> Optional[Path]:
    """Locate the backlog item file for *feature*.

    Strategy:
      1. Exact match: ``backlog/NNN-{feature}.md``
      2. If *backlog_id* is provided, match ``backlog/{NNN}-*.md``
      3. Substring match via ``_find_item(feature)``
    """
    backlog_dir = _backlog_dir if _backlog_dir is not None else _PROJECT_ROOT / "backlog"

    # 1. Exact slug match
    for p in sorted(backlog_dir.glob("[0-9]*-*.md")):
        # p.stem is e.g. "056-my-feature"
        # Extract slug portion after NNN-
        slug_part = p.stem.split("-", 1)[1] if "-" in p.stem else p.stem
        if slug_part == feature:
            return p

    # 2. Match by backlog_id
    if backlog_id is not None:
        padded = str(backlog_id).zfill(3)
        candidates = sorted(backlog_dir.glob(f"{padded}-*.md"))
        if candidates:
            return candidates[0]

    # 3. Fallback: substring match via update_item's finder
    result = _backlog_find_item(feature)
    return result


def _write_back_to_backlog(
    feature: str,
    overnight_status: str,
    round_number: int,
    log_path: Path,
    backlog_id: Optional[int] = None,
) -> None:
    """Best-effort write of canonical status back to the backlog item.

    Maps *overnight_status* to the canonical backlog fields defined in R13
    and calls ``update_item()`` from ``backlog/update_item.py``. All
    exceptions are caught, logged to the overnight events log, and silently
    swallowed so the overnight session never aborts on a backlog write failure.
    """
    mapping = _OVERNIGHT_TO_BACKLOG.get(overnight_status)
    if mapping is None:
        return  # No write-back defined for this status (e.g. "pending")

    try:
        item_path = _find_backlog_item_path(feature, backlog_id)
        if item_path is None:
            raise FileNotFoundError(
                f"Backlog item not found for feature {feature!r}"
                + (f" (backlog_id={backlog_id})" if backlog_id else "")
            )

        # Build the fields dict, replacing the session_id sentinel
        session_id = os.environ.get("LIFECYCLE_SESSION_ID", "manual")
        fields: dict[str, Any] = {}
        for key, value in mapping.items():
            if value == "_CURRENT_":
                fields[key] = session_id
            else:
                fields[key] = value

        _backlog_update_item(item_path, fields, session_id=session_id)

    except Exception as exc:
        overnight_log_event(
            BACKLOG_WRITE_FAILED,
            round_number,
            feature=feature,
            details={"error": str(exc)},
            log_path=log_path,
        )
