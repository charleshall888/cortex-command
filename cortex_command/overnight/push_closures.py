"""cortex-morning-review-push-closures — commits and pushes the ticket
closures morning-review walkthrough §6b just wrote, and reports whether the
push actually landed.

§6b closes each completed feature's backlog ticket and the review ends there.
``close_tickets.py`` has zero git calls, so a close written to repair a failed
overnight write-back stays in the local working tree and never reaches
``main`` — the ticket reads ``complete`` on this machine while still sitting
open for everyone else. This verb closes that gap.

What it does NOT do is delegate the push to ``cortex-git-sync-rebase``. That
binary returns at its up-to-date early exit (sync_rebase.py, ``if behind == 0:
return 0``) roughly a hundred lines before its ``git push``, and this
situation — a fresh local commit against a remote ``main`` that has not
moved — *is* ``behind == 0``. Its exit 0 is documented as "rebase + push completed, **or**
nothing to rebase", so its success signal cannot evidence a push. This verb
pushes directly and observes the result.

``pushed`` is derived from two observations, never from an exit code:

  1. HEAD is captured before and after the commit — ``committed`` is
     ``head_before != head_after``.
  2. ``git rev-list origin/main..HEAD --count`` is read *after* the push.

``pushed`` requires both. The ahead-count alone is not evidence: it reads 0
when the push landed *and* when nothing was ever committed, so a derivation
resting on it alone would report a phantom push on every no-op run. No
``git fetch`` is needed — ``git push`` updates ``refs/remotes/origin/main``
itself.

ADR-0019 (dumb arg-actor): the caller passes the paths and ticket ids it
already holds from ``cortex-morning-review-close-tickets``'s output rather
than this verb re-deriving them:

  --path    every entry of every closed item's ``changed_paths`` (repeatable).
            Task 9 filters gitignored derived state at its own chokepoint, so
            each reported path is stageable as given. These are the ONLY paths
            staged — the commit is pathspec-limited so a concurrent session's
            unrelated staged or dirty files cannot ride along to main.
  --ticket  the id of each closed item whose ``status_changed`` is true
            (repeatable).

``--ticket`` is the commit gate, and ``--path`` is the staging set — they are
deliberately different questions. A re-close of an already-complete ticket
still rewrites its file (``update_item`` bumps ``updated:`` unconditionally),
so ``changed_paths`` is non-empty even when nothing meaningful moved. The
overnight success path already maps ``merged`` → ``status: complete`` before
§6b runs, which makes that redundant re-close the common case. With no
``--ticket``, the whole diff is timestamp churn and no commit is made — the
review pushes nothing to main rather than pushing noise to it every morning.

States (``KNOWN_STATES``):
  pushed      — a commit was created and the push was verified by observation.
  no-op       — no ``--ticket`` was given (or no ``--path``): nothing
                meaningful changed, so nothing was committed or pushed.
  push-failed — the commit exists locally but the push did not land, or could
                not be verified. ``unpushed_tickets`` names the ids that are
                still only local. A rejected non-fast-forward is the expected
                shape here; it is reported, never forced.
  error       — the commit itself could not be made (a bad path, a hook
                rejection, an unresolvable repo root).

The CLI always emits a single JSON struct on stdout and exits 0.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from cortex_command.backlog import _telemetry
from cortex_command.common import _resolve_user_project_root

KNOWN_STATES = ("pushed", "no-op", "push-failed", "error")

_SUBJECT_LIMIT = 72


def _git(
    args: List[str], *, cwd: Path
) -> subprocess.CompletedProcess:
    """Run one git subcommand, capturing output.

    List-form only: a shell string would make every backlog path with a space
    or a quote in it an injection site.
    """
    return subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        check=False,
    )


def _head(root: Path) -> Optional[str]:
    """Return the current HEAD sha, or None if it cannot be read."""
    result = _git(["rev-parse", "HEAD"], cwd=root)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _ahead_count(root: Path) -> Optional[int]:
    """Return how many commits HEAD is ahead of ``origin/main``.

    Returns None when the count could not be determined — a missing
    ``origin/main``, an unparseable answer. None is distinct from a genuine 0:
    collapsing them would let a failed observation read as a verified push,
    which is the same fail-open shape ``_behind_count`` was repaired for.
    """
    result = _git(["rev-list", "origin/main..HEAD", "--count"], cwd=root)
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def _commit_subject(tickets: Sequence[str]) -> str:
    """Compose an imperative, ≤72-char, period-free commit subject."""
    if len(tickets) == 1:
        subject = f"Close backlog ticket #{tickets[0]} after overnight merge"
        if len(subject) <= _SUBJECT_LIMIT:
            return subject
    return f"Close {len(tickets)} backlog tickets after overnight merge"


def _commit_message(tickets: Sequence[str]) -> str:
    ids = ", ".join(f"#{t}" for t in tickets)
    return (
        f"{_commit_subject(tickets)}\n\n"
        f"Closed by morning-review Section 6b after this session's PR merged.\n\n"
        f"Tickets: {ids}\n"
    )


def push_closures(
    paths: Sequence[str],
    tickets: Sequence[str],
    project_root: Optional[Path] = None,
) -> dict:
    """Commit *paths* and push them to ``origin/main``, verifying the push.

    *tickets* are the ids whose status actually changed; an empty *tickets*
    (or *paths*) means the close moved nothing but timestamps, and the run is
    a no-op by design rather than a failure.
    """
    root = project_root or _resolve_user_project_root()
    paths = list(dict.fromkeys(paths))  # dedupe, preserve caller order
    tickets = list(dict.fromkeys(tickets))

    result: dict = {
        "state": "no-op",
        "committed": False,
        "pushed": False,
        "commit": None,
        "tickets": tickets,
        "paths": paths,
    }

    if not tickets or not paths:
        result["message"] = (
            "No status changed — nothing committed or pushed."
            if not tickets
            else "No changed paths given — nothing committed or pushed."
        )
        return result

    head_before = _head(root)
    if head_before is None:
        result["state"] = "error"
        result["message"] = f"Could not read HEAD in {root}."
        return result

    staged = _git(["add", "--"] + paths, cwd=root)
    if staged.returncode != 0:
        result["state"] = "error"
        result["message"] = f"Could not stage the closed paths: {staged.stderr.strip()}"
        return result

    # Pathspec-limited: records only these paths, so a concurrent session's
    # unrelated staged files stay out of the commit and off main.
    committed = _git(
        ["commit", "-m", _commit_message(tickets), "--"] + paths, cwd=root
    )
    head_after = _head(root)

    # Observation 1 — a commit exists only if HEAD moved. The exit code is not
    # consulted: "nothing to commit" and a hook rejection both leave HEAD put.
    if head_after is None or head_after == head_before:
        result["state"] = "error"
        result["message"] = (
            f"No commit was created: "
            f"{committed.stderr.strip() or committed.stdout.strip()}"
        )
        return result

    result["committed"] = True
    result["commit"] = head_after

    pushed = _git(["push", "origin", "HEAD:main"], cwd=root)

    # Observation 2 — read the ahead-count after the push. `git push` updates
    # the remote-tracking ref itself, so no fetch is needed.
    ahead = _ahead_count(root)

    if pushed.returncode == 0 and ahead == 0:
        result["state"] = "pushed"
        result["pushed"] = True
        return result

    result["state"] = "push-failed"
    result["unpushed_tickets"] = tickets
    if pushed.returncode != 0:
        detail = pushed.stderr.strip() or pushed.stdout.strip()
        result["message"] = (
            f"The close is committed locally ({head_after[:8]}) but the push "
            f"was rejected — tickets {', '.join('#' + t for t in tickets)} are "
            f"not on main: {detail}"
        )
    elif ahead is None:
        result["message"] = (
            f"The close is committed locally ({head_after[:8]}) and git push "
            f"reported success, but the push could not be verified — "
            f"origin/main is unreadable."
        )
    else:
        result["message"] = (
            f"The close is committed locally ({head_after[:8]}) and git push "
            f"reported success, but HEAD is still {ahead} commit(s) ahead of "
            f"origin/main — the push did not land."
        )
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-morning-review-push-closures",
        description=(
            "Commit and push the backlog-ticket closures morning-review "
            "walkthrough Section 6b wrote, verifying the push by observation. "
            "Emits a single JSON struct on stdout (always exit 0)."
        ),
    )
    parser.add_argument(
        "--path",
        dest="paths",
        action="append",
        default=None,
        metavar="PATH",
        help=(
            "One project-root-relative file the close wrote, from a closed "
            "item's changed_paths (repeatable). These are the only paths "
            "staged."
        ),
    )
    parser.add_argument(
        "--ticket",
        dest="tickets",
        action="append",
        default=None,
        metavar="ID",
        help=(
            "The id of one closed item whose status_changed is true "
            "(repeatable). With none given the diff is timestamp churn only "
            "and nothing is committed."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-morning-review-push-closures")
    args = _build_parser().parse_args(argv)
    try:
        result = push_closures(args.paths or [], args.tickets or [])
    except Exception as exc:  # noqa: BLE001 — always emit a JSON struct, never a traceback
        result = {
            "state": "error",
            "committed": False,
            "pushed": False,
            "message": repr(exc),
        }
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
