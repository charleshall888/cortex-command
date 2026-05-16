"""Git worktree management for pipeline feature isolation.

Each pipeline feature gets its own git worktree so agents working on
different features never interfere with each other's working directory.
Same-repo worktrees default to $TMPDIR/cortex-worktrees/{feature} (canonicalized
via Path.resolve()) with branches named pipeline/{feature}. The default lives
outside Seatbelt's mandatory deny on .mcp.json, which applies under .claude/
regardless of user-level sandbox.filesystem.allowWrite entries.

Cross-repo worktrees (repo_path is not None) are placed at
$TMPDIR/overnight-worktrees/{session_id}/{feature} instead.

If CORTEX_WORKTREE_ROOT is set, same-repo worktrees are placed at
$CORTEX_WORKTREE_ROOT/{feature} instead. A cortex-registered worktree root
may also be supplied via a `<path>#cortex-worktree-root` sentinel-suffixed
entry in ~/.claude/settings.local.json::sandbox.filesystem.allowWrite.
"""

import json
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class WorktreeInfo:
    """Information about a pipeline git worktree."""

    feature: str
    path: Path
    branch: str
    exists: bool


@dataclass
class ProbeResult:
    """Result of a worktree writability probe."""

    ok: bool
    cause: str | None
    remediation_hint: str | None


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


def _registered_worktree_root() -> Path | None:
    """Return the cortex-registered worktree root from settings.local.json, if any.

    Reads ``~/.claude/settings.local.json`` and returns the first entry in
    ``sandbox.filesystem.allowWrite`` whose value uses the structurally-distinct
    sentinel-suffix marker scheme: an entry of the form
    ``"<path>#cortex-worktree-root"``. The entry is split on the first ``#``
    separator; only when the trailing segment equals ``cortex-worktree-root``
    is the entry treated as a cortex-registered worktree root. The leading
    segment is returned as the ``Path``.

    Unrelated entries that happen to contain the substring ``worktrees/`` in
    their path (e.g. ``/some/foreign/worktrees/path``) are ignored — the
    sentinel suffix is the only accepted marker.

    Returns None if the file is absent, the key is missing, or no matching
    entry is found.
    """
    settings_path = Path.home() / ".claude" / "settings.local.json"
    if not settings_path.exists():
        return None
    try:
        raw = settings_path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return None

    allow_write = (
        data.get("sandbox", {})
        .get("filesystem", {})
        .get("allowWrite", [])
    )
    if not isinstance(allow_write, list):
        return None

    for entry in allow_write:
        if not isinstance(entry, str):
            continue
        path_part, sep, marker = entry.partition("#")
        if sep and marker == "cortex-worktree-root":
            return Path(path_part)
    return None


def resolve_worktree_root(
    feature: str,
    session_id: str | None,
    repo_root: Path | None = None,
) -> Path:
    """Resolve the worktree root directory for a feature.

    Resolution order (R6):
        (a) ``CORTEX_WORKTREE_ROOT`` env var, after ``$TMPDIR`` expansion,
            appended with ``/<feature>``.
        (b) Cortex-registered path from ``~/.claude/settings.local.json``
            ``sandbox.filesystem.allowWrite`` (first entry whose value matches
            the structurally-distinct sentinel suffix ``#cortex-worktree-root``,
            with the leading segment used as the worktree root), appended with
            ``/<feature>``.
        (c) Default same-repo path: ``$TMPDIR/cortex-worktrees/<feature>``,
            canonicalized via ``Path.resolve()`` so downstream Seatbelt path
            comparisons that operate on the canonical ``/private/var/folders``
            form still match. ``$TMPDIR`` falls back to ``/tmp`` when unset
            (mirrors branch (d)). The ``repo_root`` parameter is preserved on
            the function signature for other callers but is no longer
            dereferenced on this branch — same-repo worktrees no longer live
            under ``<repo>/.claude/`` because Seatbelt's mandatory deny on
            ``.mcp.json`` blocks ``git worktree add`` there.
        (d) Cross-repo path: ``$TMPDIR/overnight-worktrees/<session_id>/<feature>``
            when ``session_id`` is provided (and no earlier branch matched).

    Args:
        feature: Feature name used as the final path component.
        session_id: Overnight session ID for cross-repo worktrees. Required
            for branch (d) to be reached; if None, branch (c) is returned.
        repo_root: Optional pre-resolved repo root. Preserved on the signature
            for callers that still pass it (e.g. ``cleanup_worktree``); branch
            (c) no longer dereferences it.

    Returns:
        Resolved absolute Path for the worktree directory.
    """
    # (a) Explicit env-var override with $TMPDIR expansion.
    override_root = os.environ.get("CORTEX_WORKTREE_ROOT", "")
    if override_root:
        expanded = os.path.expandvars(override_root)
        return Path(expanded) / feature

    # (b) Cortex-registered path from settings.local.json.
    registered = _registered_worktree_root()
    if registered is not None:
        return registered / feature

    # (d) Cross-repo: $TMPDIR-based path when session_id is provided.
    if session_id is not None:
        tmpdir = Path(os.environ.get("TMPDIR", "/tmp"))
        return tmpdir / "overnight-worktrees" / session_id / feature

    # (c) Default same-repo path: $TMPDIR/cortex-worktrees/<feature>,
    # canonicalized via Path.resolve() so downstream Seatbelt comparisons that
    # operate on /private/var/folders/... form still match. `repo_root` is
    # accepted on the signature for compatibility with other callers but is
    # no longer dereferenced here — same-repo worktrees live outside the repo
    # to escape Seatbelt's mandatory deny on .mcp.json under .claude/.
    return Path(os.environ.get("TMPDIR", "/tmp")).resolve() / "cortex-worktrees" / feature


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

    worktree_path = resolve_worktree_root(feature, session_id if cross_repo else None)

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
                    # Touch atime to defend against macOS dirhelper's nightly
                    # 3-day atime-based eviction of /var/folders/ — refreshes
                    # access time on lifecycle resume so paused/deferred
                    # features are not silently purged. Opt-out via
                    # CORTEX_SKIP_ATIME_TOUCH=1 for tests that need to
                    # observe the pre-touch atime.
                    if not os.environ.get("CORTEX_SKIP_ATIME_TOUCH"):
                        now = time.time()
                        os.utime(worktree_path, (now, now))
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
            if not os.environ.get("CORTEX_SKIP_ATIME_TOUCH"):
                now = time.time()
                os.utime(worktree_path, (now, now))
            return WorktreeInfo(
                feature=feature,
                path=worktree_path,
                branch=current_branch,
                exists=True,
            )

    branch = _resolve_branch_name(feature, repo)

    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["git", "worktree", "add", str(worktree_path), "-b", branch, base_branch],
        capture_output=True,
        text=True,
        cwd=str(repo),
    )
    if result.returncode != 0:
        subprocess.run(
            ["git", "branch", "-D", branch],
            capture_output=True,
            text=True,
            cwd=str(repo),
        )
        stderr_text = (result.stderr or "").strip() or "(no stderr)"
        raise ValueError(f"worktree_creation_failed: {stderr_text}")

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
            When None, derives the path by routing through
            ``resolve_worktree_root(feature, session_id=None, repo_root=repo)``
            so the fallback honors the same single resolver chokepoint as
            creation, including the branch (c) default and any operator
            overrides via env var or settings.local.json sentinel-suffix entry.
    """
    repo = repo_path if repo_path is not None else _repo_root()
    wt_path = (
        worktree_path
        if worktree_path is not None
        else resolve_worktree_root(feature, session_id=None, repo_root=repo)
    )

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


def probe_worktree_writable(root: Path) -> ProbeResult:
    """Probe whether a worktree root is writable and git-worktree-add-capable.

    Performs two checks in order:
        (a) No-op file create + delete under ``root`` — catches sandbox-blocked
            roots where the filesystem denies writes entirely.
        (b) No-op ``git worktree add <root>/cortex-probe-<uuid> <throwaway-branch>``
            + immediate cleanup — catches hardcoded-deny paths such as ``.vscode/``
            or ``.idea/`` that the Claude Code sandbox blocks even when the parent
            root passes check (a).

    On failure, returns a ``ProbeResult`` with ``ok=False``, a ``cause`` field
    naming the likely root cause, and a ``remediation_hint`` field. On success,
    returns a ``ProbeResult`` with ``ok=True`` and no artifacts left behind.

    Cleanup runs unconditionally via a ``finally`` block; cleanup failures are
    suppressed (they do not raise).

    Args:
        root: The worktree root directory to probe. Need not exist; created as
            a side-effect of the git worktree add probe if absent.

    Returns:
        ProbeResult with ``ok`` indicating whether the root is usable.
    """
    token = uuid.uuid4().hex[:8]
    probe_file = root / f".cortex-probe-{token}"
    probe_wt_path = root / f"cortex-probe-{token}"
    probe_branch = f"cortex-probe-{token}"

    # ------------------------------------------------------------------
    # Check (a): filesystem write access
    # ------------------------------------------------------------------
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe_file.write_text("")
        probe_file.unlink()
    except OSError as exc:
        return ProbeResult(
            ok=False,
            cause="sandbox_blocked",
            remediation_hint=(
                f"Cannot write to worktree root {root}: {exc}. "
                "Add the root to sandbox.filesystem.allowWrite in "
                "~/.claude/settings.local.json (run 'cortex init' to register it automatically)."
            ),
        )
    finally:
        # Best-effort cleanup; must not raise.
        try:
            if probe_file.exists():
                probe_file.unlink()
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Check (b): git worktree add capability (catches hardcoded denies)
    # ------------------------------------------------------------------
    # We need a git repo to run `git worktree add` from. Walk up from root
    # to find one; if none found, skip this check (not a blocker).
    repo = _find_git_repo(root)
    if repo is None:
        # No git repo reachable from root — skip check (b), report success.
        return ProbeResult(ok=True, cause=None, remediation_hint=None)

    # Create a throwaway branch name that doesn't exist yet.
    # We use an orphan commit-less worktree via --detach if the branch
    # would conflict, but the uuid prefix makes collision essentially impossible.
    probe_wt_created = False
    probe_branch_created = False
    try:
        # Create an empty throwaway commit so the branch has something to point at.
        # Use --orphan to avoid needing an existing commit. We run `git worktree add`
        # with `-b <branch>` from HEAD so it doesn't need a prior empty commit.
        result = subprocess.run(
            ["git", "worktree", "add", str(probe_wt_path), "-b", probe_branch, "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(repo),
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            return ProbeResult(
                ok=False,
                cause="hardcoded_deny",
                remediation_hint=(
                    f"git worktree add failed under {root}: {stderr}. "
                    "This likely means the root path falls under a Claude Code "
                    "hardcoded sandbox deny (e.g. .vscode/ or .idea/). "
                    "Workarounds: (1) use sparse-checkout to untrack the directory, "
                    "(2) add 'git' to excludedCommands to run outside the sandbox, "
                    "or (3) use dangerouslyDisableSandbox (last resort). "
                    "See https://github.com/anthropics/claude-code/issues/51303"
                ),
            )
        probe_wt_created = True
        probe_branch_created = True
        return ProbeResult(ok=True, cause=None, remediation_hint=None)
    finally:
        # Cleanup: remove the probe worktree and branch unconditionally.
        # All cleanup failures are suppressed.
        if probe_wt_created:
            try:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(probe_wt_path)],
                    capture_output=True,
                    text=True,
                    cwd=str(repo),
                )
            except Exception:  # noqa: BLE001
                pass
        if probe_branch_created:
            try:
                subprocess.run(
                    ["git", "branch", "-D", probe_branch],
                    capture_output=True,
                    text=True,
                    cwd=str(repo),
                )
            except Exception:  # noqa: BLE001
                pass
        # Prune stale worktree refs after cleanup.
        try:
            subprocess.run(
                ["git", "worktree", "prune"],
                capture_output=True,
                text=True,
                cwd=str(repo),
            )
        except Exception:  # noqa: BLE001
            pass
        # Remove probe worktree directory if still present.
        try:
            if probe_wt_path.exists():
                shutil.rmtree(probe_wt_path, ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass


def _find_git_repo(start: Path) -> Path | None:
    """Walk up from ``start`` to find the root of a git repository.

    Returns the first directory containing a ``.git`` entry, or None if none
    is found before reaching the filesystem root.
    """
    candidate = start.resolve()
    # Limit traversal to avoid infinite loops on unusual filesystems.
    for _ in range(64):
        if (candidate / ".git").exists():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    return None
