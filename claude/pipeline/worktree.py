"""Git worktree management for pipeline feature isolation.

Each pipeline feature gets its own git worktree so agents working on
different features never interfere with each other's working directory.
Worktrees are created at {repo_root}/.claude/worktrees/{feature} with branches
named pipeline/{feature}.

Cross-repo worktrees (repo_path is not None) are placed at
$TMPDIR/overnight-worktrees/{session_id}/{feature} instead.
"""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class WorktreeInfo:
    """Information about a pipeline git worktree."""

    feature: str
    path: Path
    branch: str
    exists: bool


def _repo_root() -> Path:
    """Get the repository root via git rev-parse."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


def _branch_exists(branch: str, repo: Path) -> bool:
    """Check if a git branch exists."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/heads/{branch}"],
        capture_output=True,
        text=True,
        cwd=repo,
    )
    return result.returncode == 0


def _resolve_branch_name(feature: str, repo: Path) -> str:
    """Find an available branch name for the feature.

    Tries pipeline/{feature} first, then pipeline/{feature}-2, -3, etc.
    """
    base = f"pipeline/{feature}"
    if not _branch_exists(base, repo):
        return base
    suffix = 2
    while _branch_exists(f"{base}-{suffix}", repo):
        suffix += 1
    return f"{base}-{suffix}"


def create_worktree(
    feature: str,
    base_branch: str = "main",
    repo_path: Path | None = None,
    session_id: str | None = None,
) -> WorktreeInfo:
    """Create a git worktree for a pipeline feature.

    Args:
        feature: Feature name (used for directory and branch naming).
        base_branch: Branch to base the worktree on (default: main).
        repo_path: Explicit repository path for cross-repo features.
            When None, uses _repo_root() (current behavior).
        session_id: Overnight session ID, required when repo_path is set.
            Used to namespace worktree paths under $TMPDIR.

    Returns:
        WorktreeInfo with path and actual branch name used.

    Raises:
        ValueError: If repo_path is set but session_id is None.

    If the worktree already exists and is valid, returns its info
    (idempotent behavior).
    """
    cross_repo = repo_path is not None
    if cross_repo and session_id is None:
        raise ValueError("cross-repo worktrees require session_id")

    repo = repo_path if cross_repo else _repo_root()

    if cross_repo:
        tmpdir = Path(os.environ.get("TMPDIR", "/tmp"))
        worktree_path = tmpdir / "overnight-worktrees" / session_id / feature
    else:
        worktree_path = repo / ".claude" / "worktrees" / feature

    # If the worktree path already exists and is a valid worktree, return it
    if worktree_path.exists():
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(repo),
        )
        current_path: str | None = None
        current_branch: str | None = None
        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                current_path = line[9:]
                current_branch = None
            elif line.startswith("branch refs/heads/"):
                current_branch = line[len("branch refs/heads/"):]
            elif line == "":
                if current_path == str(worktree_path) and current_branch:
                    return WorktreeInfo(
                        feature=feature,
                        path=worktree_path,
                        branch=current_branch,
                        exists=True,
                    )
                current_path = None
                current_branch = None
        # Check last entry if output doesn't end with a blank line
        if current_path == str(worktree_path) and current_branch:
            return WorktreeInfo(
                feature=feature,
                path=worktree_path,
                branch=current_branch,
                exists=True,
            )

    branch = _resolve_branch_name(feature, repo)

    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["git", "worktree", "add", str(worktree_path), "-b", branch, base_branch],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(repo),
    )

    # Copy project-local settings (gitignored) so the CLI resolves auth
    # the same way in worktrees as in the source repo.
    # Skip for cross-repo worktrees — they use a different repo's settings.
    if not cross_repo:
        local_settings = repo / ".claude" / "settings.local.json"
        if local_settings.exists():
            (worktree_path / ".claude").mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_settings, worktree_path / ".claude" / "settings.local.json")

        # Symlink .venv so runner.sh's venv check succeeds in worktrees.
        repo_venv = repo / ".venv"
        if repo_venv.exists():
            (worktree_path / ".venv").symlink_to(repo_venv)

    return WorktreeInfo(feature=feature, path=worktree_path, branch=branch, exists=True)


def cleanup_worktree(
    feature: str,
    repo_path: Path | None = None,
    worktree_path: Path | None = None,
) -> None:
    """Remove a worktree and its branch after a feature is merged.

    Handles the case where the worktree or branch no longer exists
    (idempotent — safe to call multiple times).

    Args:
        feature: Feature name matching the worktree directory name.
        repo_path: Explicit repository path for cross-repo features.
            When None, uses _repo_root().
        worktree_path: Explicit worktree path (e.g. $TMPDIR-based).
            When None, derives from repo / ".claude" / "worktrees" / feature.
    """
    repo = repo_path if repo_path is not None else _repo_root()
    wt_path = worktree_path if worktree_path is not None else (repo / ".claude" / "worktrees" / feature)

    # Remove the worktree if it exists
    if wt_path.exists():
        result = subprocess.run(
            ["git", "worktree", "remove", str(wt_path)],
            capture_output=True,
            text=True,
            cwd=str(repo),
        )
        # If normal remove fails, try with --force
        if result.returncode != 0:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(wt_path)],
                capture_output=True,
                text=True,
                cwd=str(repo),
            )

    # Prune stale worktree references
    subprocess.run(
        ["git", "worktree", "prune"],
        capture_output=True,
        text=True,
        cwd=str(repo),
    )

    # Delete the branch (best-effort — don't fail if missing or unmerged)
    branch = f"pipeline/{feature}"
    if _branch_exists(branch, repo):
        subprocess.run(
            ["git", "branch", "-d", branch],
            capture_output=True,
            text=True,
            cwd=str(repo),
        )


def cleanup_stale_lock(feature: str, repo_path: Path | None = None) -> bool:
    """Remove stale index.lock files from a worktree.

    Checks for .git/worktrees/{feature}/index.lock and removes it
    only if no process currently holds the file (checked via lsof
    on macOS).

    Args:
        feature: Feature name matching the worktree directory name.
        repo_path: Explicit repository path for cross-repo features.
            When None, uses _repo_root().

    Returns:
        True if a stale lock was found and removed, False otherwise.
    """
    repo = repo_path if repo_path is not None else _repo_root()
    lock_path = repo / ".git" / "worktrees" / feature / "index.lock"

    if not lock_path.exists():
        return False

    # Check if any process holds the lock file (macOS: lsof)
    result = subprocess.run(
        ["lsof", str(lock_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        # A process is actively using this lock — not stale
        return False

    # No process holds the lock — safe to remove
    lock_path.unlink()
    return True


def list_worktrees(repo_path: Path | None = None) -> list[WorktreeInfo]:
    """List all pipeline worktrees.

    Parses the output of `git worktree list --porcelain` and returns
    info for worktrees with pipeline/* branches.

    Args:
        repo_path: Explicit repository path for cross-repo features.
            When None, uses _repo_root().

    Returns:
        List of WorktreeInfo for worktrees whose branch starts with
        pipeline/.
    """
    repo = repo_path if repo_path is not None else _repo_root()
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(repo),
    )

    worktrees: list[WorktreeInfo] = []
    current_path: str | None = None
    current_branch: str | None = None

    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            current_path = line[9:]
            current_branch = None
        elif line.startswith("branch refs/heads/"):
            current_branch = line[len("branch refs/heads/"):]
        elif line == "":
            # End of a worktree entry — emit if it's a pipeline branch
            if current_path and current_branch and current_branch.startswith("pipeline/"):
                wt_path = Path(current_path)
                # Extract feature name from the branch
                # pipeline/{feature} -> {feature}
                # pipeline/{feature}-2 -> {feature} (base feature name)
                feature_part = current_branch[len("pipeline/"):]
                # Strip numeric suffixes like -2, -3 for the feature name
                feature = feature_part
                worktrees.append(
                    WorktreeInfo(
                        feature=feature,
                        path=wt_path,
                        branch=current_branch,
                        exists=wt_path.exists(),
                    )
                )
            current_path = None
            current_branch = None

    # Handle the last entry if the output doesn't end with a blank line
    if current_path and current_branch and current_branch.startswith("pipeline/"):
        wt_path = Path(current_path)
        feature_part = current_branch[len("pipeline/"):]
        feature = feature_part
        worktrees.append(
            WorktreeInfo(
                feature=feature,
                path=wt_path,
                branch=current_branch,
                exists=wt_path.exists(),
            )
        )

    return worktrees
