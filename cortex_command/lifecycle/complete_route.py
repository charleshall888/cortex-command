"""Stateful recovery + routing verb for the lifecycle Complete phase.

``cortex-lifecycle-complete-route <slug>`` reproduces ``complete.md`` Step 7's
strict-order PR-state branch state machine and emits a single compact-JSON
verdict on stdout::

    {"route": ..., "terminal": ..., "continue_to": ..., "message": ...,
     "pr_state": ..., "pr_url": ..., "pr_number": ..., "head_branch": ...}

(plus ``candidates`` on the ``orphan_ambiguous`` route).

It is **not** a pure read-only classifier and must NOT be wired into
latency-sensitive or speculative surfaces (statusline, dashboard, hooks).
Two kinds of side effect occur:

* network ``gh`` calls (``gh auth status`` / ``gh pr list`` / ``gh pr view``);
* a single conditional write — the Branch-3 single-match ``pr.json``
  reconstruction (tempfile + ``os.replace`` in the lifecycle dir), idempotent
  across sequential re-invocations (once ``pr.json`` exists Branch 3 no longer
  fires).

Structure is modelled on ``_cli_detect_phase`` / ``detect_lifecycle_phase``
(``cortex_command/common.py``): a classifier function plus a thin
``main(argv) -> int`` that serializes the verdict with
``json.dumps(..., separators=(",", ":")) + "\\n"``. Path resolution uses
``_resolve_user_project_root_from_cwd()`` (ignores ``CORTEX_REPO_ROOT`` and
handles the ``.git``-file worktree marker), so an invocation from inside an
``interactive/{slug}`` worktree reads that worktree's artifacts.

Exit codes: non-zero **only** on a usage error (missing slug) or an
unresolvable project root. Every ``gh`` failure routes to Branch 4a
(``pr_state: "unknown"``) with exit 0 — never a traceback.

Route enumeration and the ``{terminal, continue_to, pr_state}`` triple per
route::

    wontfix                 True   None    ""
    already_complete        False  step12  ""
    on_main                 False  step9   ""
    first_run               False  step1   ""
    orphan_ambiguous        False  None    ""        (+ candidates)
    pr_unknown   (4a)       True   None    "unknown"
    pr_not_found (4b)       True   None    ""
    pr_open      (4c)       True   None    "OPEN"
    merged_dirty (4d)       True   None    "MERGED"
    merged_clean_ancestor   False  step8   "MERGED"  (4e)
    merged_not_ancestor     True   None    "MERGED"  (4f)
    pr_closed    (4g)       True   None    "CLOSED"
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from cortex_command.common import (
    CortexProjectRootError,
    _resolve_user_project_root_from_cwd,
)

_GIT_TIMEOUT = 10
_GH_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Subprocess helpers (graceful degradation — any failure maps to None)
# ---------------------------------------------------------------------------


def _run(
    cmd: list[str],
    cwd: Optional[str] = None,
    timeout: int = _GH_TIMEOUT,
) -> Optional[subprocess.CompletedProcess]:
    """Run *cmd*, returning the CompletedProcess or None on exec failure."""
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _git_out(args: list[str], cwd: Optional[str] = None) -> Optional[str]:
    """Return git stdout on exit 0, else None (exec failure or non-zero)."""
    proc = _run(["git"] + args, cwd=cwd, timeout=_GIT_TIMEOUT)
    if proc is None or proc.returncode != 0:
        return None
    return proc.stdout


def _git_rc(args: list[str], cwd: Optional[str] = None) -> Optional[int]:
    """Return git's returncode, or None on exec failure.

    Used for ``merge-base --is-ancestor`` where the returncode is the answer.
    """
    proc = _run(["git"] + args, cwd=cwd, timeout=_GIT_TIMEOUT)
    if proc is None:
        return None
    return proc.returncode


def _current_branch() -> str:
    """Resolve the current branch name; "" on any failure (safe default)."""
    out = _git_out(["rev-parse", "--abbrev-ref", "HEAD"])
    return out.strip() if out else ""


def _resolve_worktree_path(slug: str, root: Path) -> str:
    """Resolve the worktree path for *slug* across all completion paths.

    Prefers the ``interactive/{slug}`` worktree (branch ``refs/heads/
    interactive/{slug}`` or a path containing ``interactive-{slug}``). If no
    such worktree exists (the feature-branch / on-main path — the same case
    Step 8's prefix-check skips), falls back to the current checkout root
    (``git rev-parse --show-toplevel``), then finally to *root*. The result is
    always non-empty so the 4d/4f dirty/ancestor guards run against a real
    path rather than silently defaulting to clean.
    """
    out = _git_out(["worktree", "list", "--porcelain"])
    if out:
        blocks: list[tuple[str, Optional[str]]] = []
        path: Optional[str] = None
        branch: Optional[str] = None
        for line in out.splitlines() + [""]:
            if line.startswith("worktree "):
                path = line[len("worktree "):].strip()
                branch = None
            elif line.startswith("branch "):
                branch = line[len("branch "):].strip()
            elif not line.strip():
                if path:
                    blocks.append((path, branch))
                path, branch = None, None
        target = f"refs/heads/interactive/{slug}"
        for p, b in blocks:
            if b == target:
                return p
        for p, b in blocks:
            if f"interactive-{slug}" in p or f"interactive/{slug}" in p:
                return p
    top = _git_out(["rev-parse", "--show-toplevel"])
    if top and top.strip():
        return top.strip()
    return str(root)


def _atomic_write_json(path: Path, obj: dict) -> None:
    """Atomically write *obj* as JSON to *path* (tempfile + os.replace).

    The tempfile is created in *path*'s parent directory so ``os.replace`` is
    atomic within a single filesystem (per ``complete.md`` Step 4).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# gh helpers
# ---------------------------------------------------------------------------


def _gh_repo() -> str:
    """Resolve ``owner/name`` for the current origin; "" on any failure.

    Mirrors complete.md Step 4's ``gh repo view --json nameWithOwner`` so a
    Branch-3 reconstruction locks the repo into ``pr.json`` for the subsequent
    Branch-4 ``--repo`` query.
    """
    gh = shutil.which("gh")
    if gh is None:
        return ""
    proc = _run([gh, "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
    if proc is None or proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def _orphan_probe(slug: str) -> dict:
    """Run the Branch-3 orphan-PR probe.

    Returns ``{"error": bool, "matches": list}``. ``error`` is True when gh is
    absent or the probe call fails (routes to Branch 4a unknown).
    """
    gh = shutil.which("gh")
    if gh is None:
        return {"error": True, "matches": []}
    proc = _run([
        gh, "pr", "list",
        "--head", f"interactive/{slug}",
        "--state", "all",
        "--json", "number,state,mergedAt",
        "--limit", "5",
    ])
    if proc is None or proc.returncode != 0:
        return {"error": True, "matches": []}
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return {"error": False, "matches": []}
    if not isinstance(data, list):
        return {"error": False, "matches": []}
    return {"error": False, "matches": data}


def _reconstruct_pr_json(slug: str, lifecycle_dir: Path, match: dict) -> dict:
    """Reconstruct ``pr.json`` from a single orphan-probe match (Branch 3·one).

    The probe response carries only ``number``/``state``/``mergedAt``; the head
    branch is ``interactive/{slug}`` by construction (the ``--head`` we queried)
    and the repo is resolved via ``gh repo view`` (Step-4 pattern). ``url`` and
    ``opened_at`` are not present in the probe response and are left empty.
    """
    number = match.get("number") if isinstance(match, dict) else None
    repo = _gh_repo()
    pr_obj = {
        "number": number,
        "url": "",
        "head_branch": f"interactive/{slug}",
        "opened_at": "",
        "repo": repo,
    }
    _atomic_write_json(lifecycle_dir / "pr.json", pr_obj)
    return pr_obj


# ---------------------------------------------------------------------------
# Route construction
# ---------------------------------------------------------------------------


def _base_result() -> dict:
    return {
        "route": "",
        "terminal": True,
        "continue_to": None,
        "message": "",
        "pr_state": "",
        "pr_url": "",
        "pr_number": None,
        "head_branch": "",
    }


def _route_4a(result: dict) -> dict:
    """Branch 4a — gh unavailable / unauthenticated / network error."""
    result["route"] = "pr_unknown"
    result["terminal"] = True
    result["continue_to"] = None
    result["pr_state"] = "unknown"
    result["message"] = (
        "PR state unknown; gh unauthenticated or network error; "
        "retry later. (Worktree retained.)"
    )
    return result


def _route_4b(result: dict, slug: str, root: Path, number) -> dict:
    """Branch 4b — gh resolved the query but the PR was not found."""
    path = _resolve_worktree_path(slug, root)
    result["route"] = "pr_not_found"
    result["terminal"] = True
    result["continue_to"] = None
    result["pr_state"] = ""
    result["message"] = (
        f"PR {number} referenced in pr.json was not found on GitHub. "
        "The PR may have been deleted. "
        f"Run `git worktree remove {path}` manually if appropriate, "
        "or restore the PR. (Worktree retained.)"
    )
    return result


# ---------------------------------------------------------------------------
# Branch 4 — query PR state via gh pr view
# ---------------------------------------------------------------------------


def _branch4(result: dict, slug: str, root: Path, pr_obj: dict, lifecycle_dir: Path) -> dict:
    number = pr_obj.get("number")
    url = pr_obj.get("url", "") or ""
    repo = pr_obj.get("repo", "") or ""
    head_branch = pr_obj.get("head_branch", "") or ""

    result["pr_url"] = url
    result["pr_number"] = number
    result["head_branch"] = head_branch

    gh = shutil.which("gh")
    if gh is None:
        return _route_4a(result)

    auth = _run([gh, "auth", "status"])
    if auth is None or auth.returncode != 0:
        return _route_4a(result)

    view_cmd = [gh, "pr", "view", str(number), "--json", "state,mergedAt"]
    if repo:
        view_cmd += ["--repo", repo]
    view = _run(view_cmd)
    if view is None or view.returncode != 0:
        stderr = (view.stderr if view is not None else "") or ""
        low = stderr.lower()
        if "could not resolve to a pullrequest" in low or "graphql: not found" in low:
            return _route_4b(result, slug, root, number)
        return _route_4a(result)

    try:
        data = json.loads(view.stdout or "{}")
    except json.JSONDecodeError:
        return _route_4a(result)
    if not isinstance(data, dict):
        return _route_4a(result)
    state = data.get("state")

    # 4c — OPEN
    if state == "OPEN":
        result["route"] = "pr_open"
        result["terminal"] = True
        result["continue_to"] = None
        result["pr_state"] = "OPEN"
        result["message"] = f"PR open at {url}; merge first."
        return result

    # 4d / 4e / 4f — MERGED
    if state == "MERGED":
        result["pr_state"] = "MERGED"
        path = _resolve_worktree_path(slug, root)
        status = _git_out(["status", "--porcelain"], cwd=path)
        # Conservative: a failed status check counts as dirty (do not auto-clean).
        dirty = (status is None) or bool(status.strip())
        if dirty:
            result["route"] = "merged_dirty"
            result["terminal"] = True
            result["continue_to"] = None
            result["message"] = f"uncommitted changes at {path}; resolve first."
            return result
        rc = _git_rc(
            ["merge-base", "--is-ancestor", head_branch, "origin/main"],
            cwd=path,
        )
        if rc == 0:
            result["route"] = "merged_clean_ancestor"
            result["terminal"] = False
            result["continue_to"] = "step8"
            return result
        result["route"] = "merged_not_ancestor"
        result["terminal"] = True
        result["continue_to"] = None
        result["message"] = (
            "branch head is not in origin/main (possible squash with "
            "non-ancestor commit or fork-merge); refusing cleanup until "
            f"verified. Run `git worktree remove {path}` manually to override."
        )
        return result

    # 4g — CLOSED without merge
    if state == "CLOSED":
        result["pr_state"] = "CLOSED"
        path = _resolve_worktree_path(slug, root)
        result["route"] = "pr_closed"
        result["terminal"] = True
        result["continue_to"] = None
        result["message"] = (
            f"PR {url} was closed without merging. Either reopen and merge, "
            f"run `git worktree remove {path}` manually to abandon, or invoke "
            f"`/cortex-core:lifecycle wontfix {slug}` if appropriate. "
            "(Worktree retained.)"
        )
        return result

    # Unrecognized state → degrade to unknown rather than mis-route.
    return _route_4a(result)


# ---------------------------------------------------------------------------
# classify — the strict-order state machine
# ---------------------------------------------------------------------------


def classify(slug: str, root: Path) -> dict:
    """Classify the Complete-phase route for *slug* under *root*.

    Strict order, first match wins: Branch 1 (feature_wontfix) → Branch 2
    (feature_complete) → on-main short-circuit / Branch 3 (pr.json absent
    orphan probe) → Branch 4 (gh pr view).
    """
    lifecycle_dir = root / "cortex" / "lifecycle" / slug
    pr_json = lifecycle_dir / "pr.json"
    events_log = lifecycle_dir / "events.log"

    result = _base_result()

    # --- events.log scan (Branch 1 + Branch 2) ---
    wontfix_ts: Optional[str] = None
    complete_seen = False
    if events_log.is_file():
        try:
            content = events_log.read_text(errors="replace")
        except OSError:
            content = ""
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(ev, dict):
                continue
            etype = ev.get("event")
            if etype == "feature_wontfix" and wontfix_ts is None:
                wontfix_ts = ev.get("ts", "")
            elif etype == "feature_complete":
                # Shape-agnostic: match on the event key only (the 6-key merge
                # row and the 3-key close row alike), never on field count.
                complete_seen = True

    # Branch 1 — feature_wontfix (precedes ALL pr.json / PR-state checks).
    if wontfix_ts is not None:
        result["route"] = "wontfix"
        result["terminal"] = True
        result["continue_to"] = None
        result["message"] = (
            f"lifecycle was wontfix'd at {wontfix_ts}; "
            "nothing to complete (worktree cleanup skipped)."
        )
        return result

    # Branch 2 — feature_complete already present (idempotent short-circuit).
    if complete_seen:
        result["route"] = "already_complete"
        result["terminal"] = False
        result["continue_to"] = "step12"
        return result

    current_branch = _current_branch()

    # Branch 3 / on-main short-circuit (pr.json absent).
    if not pr_json.is_file():
        if current_branch in ("main", "master"):
            # complete.md:21 — direct-to-main work has no PR; skip the orphan
            # probe and jump to Steps 9-12.
            result["route"] = "on_main"
            result["terminal"] = False
            result["continue_to"] = "step9"
            return result
        probe = _orphan_probe(slug)
        if probe["error"]:
            return _route_4a(result)
        matches = probe["matches"]
        if len(matches) == 0:
            result["route"] = "first_run"
            result["terminal"] = False
            result["continue_to"] = "step1"
            return result
        if len(matches) > 1:
            # Stop-for-user-pick: surface candidates, write no pr.json. The
            # prose owns the pick + the re-run (kept affordance).
            result["route"] = "orphan_ambiguous"
            result["terminal"] = False
            result["continue_to"] = None
            result["candidates"] = matches
            return result
        # Exactly one — reconstruct pr.json then fall through to Branch 4.
        pr_obj = _reconstruct_pr_json(slug, lifecycle_dir, matches[0])
        return _branch4(result, slug, root, pr_obj, lifecycle_dir)

    # pr.json present → Branch 4.
    try:
        pr_obj = json.loads(pr_json.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError):
        pr_obj = {}
    if not isinstance(pr_obj, dict):
        pr_obj = {}
    return _branch4(result, slug, root, pr_obj, lifecycle_dir)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-complete-route",
        description=(
            "Classify the lifecycle Complete-phase route for a feature slug "
            "and emit a JSON verdict on stdout."
        ),
    )
    parser.add_argument("slug", help="Feature slug (e.g. my-feature)")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        root = _resolve_user_project_root_from_cwd()
    except CortexProjectRootError as exc:
        sys.stderr.write(f"cortex-lifecycle-complete-route: {exc}\n")
        return 1
    result = classify(args.slug, root)
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
