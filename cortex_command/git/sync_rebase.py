"""Python port of bin/cortex-git-sync-rebase.

Post-merge sync: fetch, rebase with allowlist conflict resolution, push.

Usage: ``cortex-git-sync-rebase [allowlist-file]``

Exit codes:
  0 — success (rebase + push completed, or nothing to rebase)
  1 — conflict (rebase aborted, user must resolve manually)
  2 — push failed (rebase succeeded but push to origin/main failed)
  3 — behind-count undetermined (git rev-list failed or returned
      unparseable output; sync state is unknown, nothing was rebased)

The allowlist file contains glob patterns for files that may be
auto-resolved using ``--theirs`` during a conflict pass. Git swaps the
ours/theirs nomenclature during a rebase — the upstream (remote) commits are
checked out first and the local commits are replayed on top — so ``--theirs``
names the replayed side: auto-resolution keeps the **local** revision and
discards the remote one (see the Note in ``git-checkout(1)``). Whether local
is the side that should win is an open question tracked separately; this
docstring records the behavior, not an endorsement of it.
Default allowlist path: ``<repo-root>/cortex_command/overnight/sync-allowlist.conf``.

Subprocess invocations for git plumbing are retained verbatim — no
libgit2 binding is introduced — so the runtime contract mirrors the
bash original's PATH dependency on ``git``.
"""

from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_ALLOWLIST_REL = "cortex_command/overnight/sync-allowlist.conf"
_MAX_PASSES = 10


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _log(msg: str) -> None:
    """Write a prefixed diagnostic line to stderr."""
    sys.stderr.write(f"[git-sync-rebase] {msg}\n")
    sys.stderr.flush()


# ---------------------------------------------------------------------------
# Allowlist helpers
# ---------------------------------------------------------------------------


def _load_allowlist(allowlist_file: Path) -> List[str]:
    """Parse the allowlist file and return a list of non-blank, non-comment patterns.

    Mirrors the bash original's comment-stripping and whitespace-trimming
    behaviour: inline comments are stripped, leading/trailing whitespace is
    removed, blank results are skipped.
    """
    if not allowlist_file.is_file():
        _log(f"Warning: allowlist file not found: {allowlist_file}")
        return []

    patterns: List[str] = []
    text = allowlist_file.read_text(encoding="utf-8")
    for raw_line in text.splitlines():
        # Strip inline comments (everything from first '#' onward).
        line = raw_line.split("#", 1)[0]
        line = line.strip()
        if line:
            patterns.append(line)

    _log(f"Loaded {len(patterns)} allowlist patterns from {allowlist_file}")
    return patterns


def _matches_allowlist(filepath: str, patterns: List[str]) -> bool:
    """Return True if filepath matches any allowlist pattern.

    Directory patterns (trailing ``/``) match any file whose path starts with
    that prefix. Other patterns use :func:`fnmatch.fnmatch` for glob-style
    matching, mirroring bash's ``case`` statement ``fnmatch``-style behaviour.
    """
    for pattern in patterns:
        if pattern.endswith("/"):
            # Directory prefix match.
            if filepath.startswith(pattern):
                return True
        else:
            if fnmatch.fnmatch(filepath, pattern):
                return True
    return False


# ---------------------------------------------------------------------------
# Git subprocess helpers
# ---------------------------------------------------------------------------


def _git(args: List[str], *, cwd: Optional[Path] = None, check: bool = False) -> subprocess.CompletedProcess:
    """Run a git subcommand, capturing output."""
    return subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        check=check,
    )


def _repo_root() -> Optional[Path]:
    """Resolve the repo root via ``git rev-parse --show-toplevel``."""
    result = _git(["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        return None
    stripped = result.stdout.strip()
    return Path(stripped) if stripped else None


def _stale_rebase_in_progress(repo_root: Path) -> bool:
    """Return True if a stale rebase directory exists."""
    return (
        (repo_root / ".git" / "rebase-merge").is_dir()
        or (repo_root / ".git" / "rebase-apply").is_dir()
    )


def _behind_count(repo_root: Path) -> Optional[int]:
    """Return the number of commits HEAD is behind origin/main.

    Returns ``None`` when the count could not be determined — a missing
    ``origin/main``, a shallow clone, an auth or network failure, or output
    git did not render as an integer. ``None`` is distinct from a legitimate
    ``0``: collapsing the two would render every such failure as "already up
    to date" and exit 0 without pushing anything.
    """
    result = _git(
        ["rev-list", "HEAD..origin/main", "--count"],
        cwd=repo_root,
    )
    if result.returncode != 0:
        _log(
            f"Error: could not determine behind-count — git rev-list "
            f"HEAD..origin/main exited {result.returncode}: "
            f"{result.stderr.strip()}"
        )
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        _log(
            f"Error: could not determine behind-count — git rev-list "
            f"HEAD..origin/main returned unparseable output: "
            f"{result.stdout.strip()!r}"
        )
        return None


def _conflicted_files(repo_root: Path) -> List[str]:
    """Return the list of files currently in conflict (unmerged)."""
    result = _git(
        ["diff", "--name-only", "--diff-filter=U"],
        cwd=repo_root,
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line]


# ---------------------------------------------------------------------------
# Core sync logic
# ---------------------------------------------------------------------------


def sync_rebase(
    repo_root: Path,
    allowlist_file: Optional[Path] = None,
) -> int:
    """Run the full fetch → check → rebase → push cycle.

    :param repo_root: Absolute path to the git repository root.
    :param allowlist_file: Path to the glob-pattern allowlist. Defaults to
        ``<repo_root>/cortex_command/overnight/sync-allowlist.conf``.
    :returns: Exit code: 0=success, 1=unresolvable conflict, 2=push failure,
        3=behind-count undetermined.
    """
    if allowlist_file is None:
        allowlist_file = repo_root / _DEFAULT_ALLOWLIST_REL

    # Step 1: abort any stale rebase.
    if _stale_rebase_in_progress(repo_root):
        _log("Warning: stale rebase in progress detected — aborting it")
        _git(["rebase", "--abort"], cwd=repo_root)

    # Step 2: fetch.
    _log("Fetching origin...")
    fetch = _git(["fetch", "origin"], cwd=repo_root)
    if fetch.returncode != 0:
        _log(f"Error: git fetch failed: {fetch.stderr.strip()}")
        return 1

    # Step 3: check if rebase is needed.
    behind = _behind_count(repo_root)
    if behind is None:
        _log(
            "Error: aborting sync — the behind-count check failed, so the "
            "sync state is unknown. Nothing was rebased or pushed."
        )
        return 3
    if behind == 0:
        _log("Already up to date with origin/main — nothing to rebase")
        return 0

    _log(f"{behind} commit(s) behind origin/main — starting rebase")

    # Step 4: attempt rebase.
    pull = subprocess.run(
        ["git", "pull", "--rebase", "origin", "main"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )

    if pull.returncode == 0:
        _log("Rebase completed cleanly")
    else:
        # Step 5: multi-pass conflict resolution loop.
        patterns = _load_allowlist(allowlist_file)

        completed = False
        for pass_num in range(1, _MAX_PASSES + 1):
            _log(f"Conflict resolution pass {pass_num}/{_MAX_PASSES}")

            conflicted = _conflicted_files(repo_root)

            if not conflicted:
                _log("No conflicted files remain — continuing rebase")
                cont = subprocess.run(
                    ["git", "rebase", "--continue"],
                    capture_output=True,
                    text=True,
                    cwd=str(repo_root),
                    env={**__import__("os").environ, "GIT_EDITOR": "true"},
                )
                if cont.returncode == 0:
                    _log(f"Rebase completed after {pass_num} pass(es)")
                    completed = True
                    break
                # --continue surfaced new conflicts in the next commit; loop.
                continue

            _log(f"{len(conflicted)} conflicted file(s) found")

            resolved = 0
            non_allowlist: List[str] = []

            for filepath in conflicted:
                if _matches_allowlist(filepath, patterns):
                    _log(f"  Auto-resolving (theirs): {filepath}")
                    _git(["checkout", "--theirs", "--", filepath], cwd=repo_root)
                    _git(["add", "--", filepath], cwd=repo_root)
                    resolved += 1
                else:
                    _log(f"  Non-allowlist conflict: {filepath}")
                    non_allowlist.append(filepath)

            _log(
                f"Resolved {resolved} file(s), {len(non_allowlist)} non-allowlist "
                "conflict(s) remain"
            )

            if non_allowlist:
                _log(
                    f"Error: {len(non_allowlist)} non-allowlist conflict(s) cannot "
                    "be auto-resolved — aborting rebase"
                )
                for f in non_allowlist:
                    _log(f"  Unresolved: {f}")
                _git(["rebase", "--abort"], cwd=repo_root)
                return 1

            # All conflicts resolved this pass — continue rebase.
            cont = subprocess.run(
                ["git", "rebase", "--continue"],
                capture_output=True,
                text=True,
                cwd=str(repo_root),
                env={**__import__("os").environ, "GIT_EDITOR": "true"},
            )
            if cont.returncode == 0:
                _log(f"Rebase completed after {pass_num} pass(es)")
                completed = True
                break
            # --continue didn't finish — more commits with conflicts; loop.

        if not completed:
            _log(
                f"Error: exceeded maximum resolution passes ({_MAX_PASSES}) "
                "— aborting rebase"
            )
            _git(["rebase", "--abort"], cwd=repo_root)
            return 1

    # Step 6: push.
    _log("Pushing to origin/main...")
    push = _git(["push", "origin", "main"], cwd=repo_root)
    if push.returncode == 0:
        _log("Push succeeded")
        return 0
    else:
        _log("Error: push failed (rebase succeeded — local state is rebased)")
        return 2


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    """Console-script entry point for ``cortex-git-sync-rebase``.

    argv[0] is the optional allowlist-file path (mirroring positional arg 1
    from the bash original). When omitted the default path under the repo
    root is used.
    """
    args = list(sys.argv[1:] if argv is None else argv)

    repo_root_path = _repo_root()
    if repo_root_path is None:
        # Fall back to cwd when not inside a git repo (e.g., tests pass an
        # explicit allowlist and a synthetic repo is set up via cwd).
        repo_root_path = Path.cwd()

    allowlist_file: Optional[Path] = None
    if args:
        allowlist_file = Path(args[0])

    return sync_rebase(repo_root=repo_root_path, allowlist_file=allowlist_file)


if __name__ == "__main__":
    sys.exit(main())
