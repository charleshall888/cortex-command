"""cortex-morning-review-pr-status — locate and classify the overnight
session's integration PR in one call.

Morning-review walkthrough §6 used to spend two or three turns on this: read
``integration_branch`` from the session state file, run ``gh pr list``, then
reason about an array that can hold zero, one, or several PRs (head-branch
names repeat across sessions) in any of GitHub's states. The classification
is mechanical, so it lives here and the prose only routes on ``state``.

The verb reads ``overnight-state.json`` (``--state`` overrides the default
``cortex/lifecycle/sessions/latest-overnight/overnight-state.json``), runs
``gh pr list --head <branch> --state all --json number,url,state,title,isDraft``
(``--state all`` because gh's default hides merged and closed PRs), and emits
one JSON struct on stdout — always exit 0, never a traceback.

States (``KNOWN_STATES``):
  no-branch — state file missing/unreadable, or ``integration_branch`` absent
              or empty. Nothing to look up.
  gh-error  — ``gh`` is missing, exited non-zero, or returned unparseable
              output; ``message`` carries the detail.
  no-pr     — the array was empty.
  several   — more than one PR shares the head branch; ``candidates`` lists
              them. The caller must never pick one on the reader's behalf.
  merged    — exactly one PR and it is MERGED. This does not establish whose
              commits are in main (a same-named branch from an earlier
              session produces the same match), so the caller reports only.
  closed    — exactly one PR and it was closed without merging.
  open      — exactly one OPEN PR; ``pr.draft`` says whether GitHub will
              refuse a direct merge.

Every envelope carries ``integration_branch``, ``worktree_path`` (from the
same state file; the merge step removes it), and ``message`` — a ready-to-
relay sentence for every non-``open`` state.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.common import _resolve_user_project_root

KNOWN_STATES = ("no-branch", "gh-error", "no-pr", "several", "merged", "closed", "open")

_STATE_REL = Path("cortex/lifecycle/sessions/latest-overnight/overnight-state.json")
_GH_TIMEOUT = 60


def _read_state(state_path: Path) -> Optional[dict]:
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _gh_pr_list(branch: str) -> tuple[Optional[list], Optional[str]]:
    """Return ``(prs, None)`` on success or ``(None, message)`` on failure."""
    argv = [
        "gh", "pr", "list",
        "--head", branch,
        "--state", "all",
        "--json", "number,url,state,title,isDraft",
    ]
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=_GH_TIMEOUT, check=False
        )
    except FileNotFoundError:
        return None, "gh is not installed or not on PATH."
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"gh pr list failed: {exc!r}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return None, f"gh pr list exited {proc.returncode}: {detail[-500:]}"
    try:
        parsed = json.loads(proc.stdout or "[]")
    except ValueError:
        return None, "gh pr list returned unparseable output."
    if not isinstance(parsed, list):
        return None, "gh pr list returned a non-list payload."
    return parsed, None


def _summarize(pr: dict) -> dict:
    return {
        "number": pr.get("number"),
        "url": pr.get("url"),
        "title": pr.get("title"),
        "state": pr.get("state"),
        "draft": bool(pr.get("isDraft", False)),
    }


def pr_status(state_path: Optional[Path] = None, project_root: Optional[Path] = None) -> dict:
    root = project_root or _resolve_user_project_root()
    path = state_path or (root / _STATE_REL)
    state = _read_state(path)
    branch = (state or {}).get("integration_branch") or ""
    worktree_path = (state or {}).get("worktree_path") or None
    base = {
        "integration_branch": branch or None,
        "worktree_path": worktree_path,
        "pr": None,
        "candidates": [],
    }
    if not branch:
        return {**base, "state": "no-branch",
                "message": "No integration branch found — skipping PR step."}

    prs, err = _gh_pr_list(branch)
    if prs is None:
        return {**base, "state": "gh-error", "message": err}

    if not prs:
        return {**base, "state": "no-pr", "message": (
            f"No PR found for `{branch}`. The runner may have failed to create "
            "one. Use `/pr` to create it manually.")}

    if len(prs) > 1:
        candidates = [_summarize(p) for p in prs]
        return {**base, "state": "several", "candidates": candidates, "message": (
            f"Several PRs share the head branch `{branch}` — identify this "
            "session's PR and act on it manually.")}

    pr = _summarize(prs[0])
    gh_state = (pr["state"] or "").upper()
    if gh_state == "MERGED":
        return {**base, "state": "merged", "pr": pr, "message": (
            f"A PR for `{branch}` is already merged: {pr['url']}. Reporting "
            "only — this does not establish that this session's work landed.")}
    if gh_state == "CLOSED":
        return {**base, "state": "closed", "pr": pr, "message": (
            f"The PR for `{branch}` was closed without merging: {pr['url']}.")}
    return {**base, "state": "open", "pr": pr, "message": ""}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-morning-review-pr-status",
        description=(
            "Locate and classify the overnight session's integration PR for "
            "morning-review walkthrough Section 6. Emits one JSON struct on "
            "stdout (always exit 0)."
        ),
    )
    parser.add_argument(
        "--state",
        default=None,
        metavar="PATH",
        help=(
            "overnight-state.json to read integration_branch from (default: "
            "cortex/lifecycle/sessions/latest-overnight/overnight-state.json)."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-morning-review-pr-status")
    args = _build_parser().parse_args(argv)
    try:
        result = pr_status(Path(args.state) if args.state else None)
    except Exception as exc:  # noqa: BLE001 — always emit a JSON struct, never a traceback
        result = {"state": "gh-error", "message": repr(exc), "pr": None,
                  "candidates": [], "integration_branch": None, "worktree_path": None}
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
