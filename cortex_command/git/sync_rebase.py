"""Python port of bin/cortex-git-sync-rebase.

Post-merge sync: fetch, rebase with allowlist conflict resolution, push.

Usage: ``cortex-git-sync-rebase [allowlist-file]``

Exit codes:
  0 — success (rebase + push completed, or nothing to rebase)
  1 — conflict (rebase aborted, user must resolve manually)
  2 — push failed (rebase succeeded but push to origin/main failed)
  3 — behind-count undetermined (git rev-list failed or returned
      unparseable output; sync state is unknown, nothing was rebased)

The allowlist file contains ``<side> <pattern>`` lines: a glob pattern for
files whose conflicts may be auto-resolved, and which side wins for that
pattern — ``remote`` (the merged pull request's revision) or ``local`` (the
replayed session commit's revision). The per-pattern ruling is ADR-0029:
lifecycle phase artifacts are owned by the merged PR (remote wins); backlog
item files carry the review's later, better-informed closes (local wins). A
line without a valid side is skipped with a warning, so a mis-edited entry
fails safe: its conflicts abort the rebase loudly instead of silently picking
a side.

Git swaps the ours/theirs nomenclature during a rebase — the upstream
(remote) commits are checked out first and the local commits are replayed on
top — so ``--theirs`` names the replayed side (**local**) and ``--ours``
names the upstream side (**remote**); see the Note in ``git-checkout(1)``.
When a remote-wins resolution supersedes everything the replayed commit
carried, the emptied commit is dropped via ``git rebase --skip``.
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
from typing import List, Optional, Tuple


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


# The two resolvable sides (ADR-0029). ``local`` keeps the replayed session
# commit's revision (``git checkout --theirs`` during a rebase); ``remote``
# keeps the merged pull request's revision (``--ours``).
_SIDES = ("local", "remote")
_SIDE_TO_CHECKOUT_FLAG = {"local": "--theirs", "remote": "--ours"}


def _load_allowlist(allowlist_file: Path) -> List[Tuple[str, str]]:
    """Parse the allowlist file into ordered ``(side, pattern)`` entries.

    Each non-blank, non-comment line is ``<side> <pattern>`` where ``side`` is
    ``local`` or ``remote`` (ADR-0029: which revision survives a conflict on
    that pattern). Inline comments are stripped and whitespace trimmed. A line
    that does not carry a valid side is skipped WITH a warning — never
    defaulted: a mis-edited entry must fail safe (its conflicts abort the
    rebase loudly) rather than silently pick a side nobody ruled on.
    """
    if not allowlist_file.is_file():
        _log(f"Warning: allowlist file not found: {allowlist_file}")
        return []

    entries: List[Tuple[str, str]] = []
    text = allowlist_file.read_text(encoding="utf-8")
    for raw_line in text.splitlines():
        # Strip inline comments (everything from first '#' onward).
        line = raw_line.split("#", 1)[0]
        line = line.strip()
        if not line:
            continue
        tokens = line.split()
        if len(tokens) != 2 or tokens[0] not in _SIDES:
            _log(
                f"Warning: skipping malformed allowlist line {line!r} — "
                f"expected '<side> <pattern>' with side in {_SIDES}; conflicts "
                "on this pattern will abort the rebase instead"
            )
            continue
        entries.append((tokens[0], tokens[1]))

    _log(f"Loaded {len(entries)} allowlist patterns from {allowlist_file}")
    return entries


def _resolve_side(filepath: str, entries: List[Tuple[str, str]]) -> Optional[str]:
    """Return the winning side for *filepath*, or None when no pattern matches.

    First matching entry wins (declaration order). Directory patterns
    (trailing ``/``) match any file whose path starts with that prefix. Other
    patterns use :func:`fnmatch.fnmatch` for glob-style matching, mirroring
    bash's ``case`` statement ``fnmatch``-style behaviour.
    """
    for side, pattern in entries:
        if pattern.endswith("/"):
            # Directory prefix match.
            if filepath.startswith(pattern):
                return side
        else:
            if fnmatch.fnmatch(filepath, pattern):
                return side
    return None


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
                side = _resolve_side(filepath, patterns)
                if side is not None:
                    # ADR-0029 per-pattern ruling. Git inverts ours/theirs in a
                    # rebase: --theirs is the replayed (local) side, --ours the
                    # upstream (remote) side.
                    flag = _SIDE_TO_CHECKOUT_FLAG[side]
                    _log(f"  Auto-resolving (keep {side}): {filepath}")
                    _git(["checkout", flag, "--", filepath], cwd=repo_root)
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

            # All conflicts resolved this pass — continue the rebase. When a
            # remote-wins resolution superseded everything the replayed commit
            # carried, the index now matches HEAD and --continue would refuse
            # ("no changes"); the emptied commit is dropped with --skip instead.
            staged = _git(["diff", "--cached", "--quiet"], cwd=repo_root)
            if staged.returncode == 0:
                _log("Replayed commit emptied by resolution — skipping it")
                step = "--skip"
            else:
                step = "--continue"
            cont = subprocess.run(
                ["git", "rebase", step],
                capture_output=True,
                text=True,
                cwd=str(repo_root),
                env={**__import__("os").environ, "GIT_EDITOR": "true"},
            )
            if cont.returncode == 0:
                _log(f"Rebase completed after {pass_num} pass(es)")
                completed = True
                break
            # --continue/--skip didn't finish — more commits with conflicts; loop.

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
