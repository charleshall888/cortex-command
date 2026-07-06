"""cortex-lifecycle-record-pr-opened — composes the Complete phase's
mechanical PR-recording bookkeeping (write ``pr.json`` + emit the
``pr_opened`` event) into one call.

Before this consolidation, ``complete.md`` Steps 4 and 5 narrated this as two
separate actions: resolve repo identity + atomically write ``pr.json`` (Step
4), then append a hand-written ``pr_opened`` row to ``events.log`` (Step 5).
This verb composes them, mirroring how Step 11a's
``cortex-lifecycle-stage-artifacts`` consolidated its own multi-step staging
mechanics — leaving the judgment-bearing PR creation itself (Step 3's
``/cortex-core:pr`` invocation, which crafts a title/body) in skill prose,
since that is an LLM action this verb cannot perform.

``pr_opened`` is one of ADR-0020's hand-written exempt events — its canonical
shape places ``schema_version`` before ``feature``, unlike the uniform
``{ts, event, feature, ...}`` shape ``cortex_command.lifecycle_event.log_event``
enforces — so this verb writes the row directly rather than funneling
through ``log_event``, preserving the exempt schema exactly (same field
names, order, and types as the pre-consolidation hand-written row).

Reuses ``cortex_command.lifecycle.complete_route``'s existing ``_run`` /
``_atomic_write_json`` / ``_gh_repo`` primitives (Step 4's mechanics were
already duplicated once, for the Branch-3 orphan-PR reconstruction) rather
than re-implementing them a third time.

``--url``/``--head-branch`` (ADR-0019 dumb-arg-actor shape): the caller has
just run ``gh pr create`` via ``/cortex-core:pr`` and already holds both the
PR's URL and its own current branch — passing them in lets this verb skip the
``gh pr view`` round-trip entirely. When either is omitted, the verb falls
back to resolving them via ``gh pr view --repo <repo>`` (the repo locked by
``_gh_repo()`` moments earlier, so the query cannot land on the wrong repo
even if ``origin`` is ambiguous).

States:
  ok                    — ``pr.json`` written and ``pr_opened`` logged;
                          ``number``, ``url``, ``head_branch``, ``opened_at``,
                          ``repo`` are set.
  gh-error              — repo identity or PR metadata could not be resolved
                          via ``gh``; ``message`` carries the diagnostic.
                          Neither file is written.
  project-root-error    — the project root could not be resolved (e.g. cwd
                          outside a cortex project); neither file is written.
  pr-json-write-failed  — ``pr.json`` could not be written (disk error);
                          neither file is written.
  event-append-failed   — ``pr.json`` WAS written, but appending the
                          ``pr_opened`` row to ``events.log`` failed;
                          ``message`` names the gap so the caller can retry
                          the event append rather than re-running the whole
                          verb (which would re-write pr.json harmlessly but
                          re-query gh needlessly).

Every state above is reached without raising — the verb always emits a
``{"state": ..., ...}`` struct on stdout and exits 0 (see ``main``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.common import (
    CortexProjectRootError,
    _resolve_user_project_root_from_cwd,
)
from cortex_command.lifecycle.complete_route import _atomic_write_json, _gh_repo, _run
from cortex_command.lifecycle_event import _append_event_atomic, _now_iso

KNOWN_STATES = (
    "ok",
    "gh-error",
    "project-root-error",
    "pr-json-write-failed",
    "event-append-failed",
)


def _gh_pr_view(number: int, repo: str) -> Optional[dict]:
    """Return ``{"url": ..., "head_branch": ...}`` for *number* via *repo*.

    Routes through ``complete_route._run`` rather than a local subprocess
    wrapper. *repo* is already resolved by the caller (``_gh_repo()``, which
    itself confirmed ``gh`` is on PATH), so no second ``shutil.which`` probe
    is needed here — ``--repo`` is passed so the query targets the locked
    repo even if ``origin`` later changes. Returns ``None`` on any failure.
    """
    cmd = ["gh", "pr", "view", str(number), "--json", "url,headRefName"]
    if repo:
        cmd += ["--repo", repo]
    proc = _run(cmd)
    if proc is None or proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    url = data.get("url")
    head_branch = data.get("headRefName")
    if not isinstance(url, str) or not isinstance(head_branch, str):
        return None
    return {"url": url, "head_branch": head_branch}


def record_pr_opened(
    feature: str,
    number: int,
    project_root: Optional[Path] = None,
    *,
    url: Optional[str] = None,
    head_branch: Optional[str] = None,
) -> dict:
    """Resolve repo/PR identity, write ``pr.json``, and log ``pr_opened``.

    Never raises — every failure mode returns a distinct ``state`` instead
    (see the module docstring), so the CLI's exit-0 contract holds by
    construction rather than relying on a try/except in ``main``.
    """
    repo = _gh_repo()
    if not repo:
        return {
            "state": "gh-error",
            "message": "gh repo view failed to resolve nameWithOwner",
        }

    if url and head_branch:
        # Caller already holds both (just ran `gh pr create`) — skip the
        # gh pr view round-trip entirely.
        pr_meta = {"url": url, "head_branch": head_branch}
    else:
        pr_meta = _gh_pr_view(number, repo)
        if pr_meta is None:
            return {
                "state": "gh-error",
                "message": f"gh pr view {number} failed to resolve url/headRefName",
            }

    try:
        root = project_root or _resolve_user_project_root_from_cwd()
    except CortexProjectRootError as exc:
        return {
            "state": "project-root-error",
            "message": f"could not resolve the project root: {exc}",
        }

    lifecycle_dir = root / "cortex" / "lifecycle" / feature
    opened_at = _now_iso()

    pr_obj = {
        "number": number,
        "url": pr_meta["url"],
        "head_branch": pr_meta["head_branch"],
        "opened_at": opened_at,
        "repo": repo,
    }
    try:
        _atomic_write_json(lifecycle_dir / "pr.json", pr_obj)
    except OSError as exc:
        return {
            "state": "pr-json-write-failed",
            "message": f"failed to write pr.json: {exc}",
        }

    # Hand-written ADR-0020 exempt event — schema_version precedes feature,
    # so this bypasses cortex_command.lifecycle_event.log_event on purpose.
    row = {
        "schema_version": 1,
        "ts": opened_at,
        "event": "pr_opened",
        "feature": feature,
        "number": number,
        "url": pr_meta["url"],
        "head_branch": pr_meta["head_branch"],
        "repo": repo,
    }
    try:
        _append_event_atomic(lifecycle_dir / "events.log", json.dumps(row) + "\n")
    except OSError as exc:
        return {
            "state": "event-append-failed",
            "message": f"pr.json written but pr_opened event append failed: {exc}",
            **pr_obj,
        }

    return {"state": "ok", **pr_obj}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-record-pr-opened",
        description=(
            "Resolve repo/PR identity, write pr.json, and log the pr_opened "
            "event — a single {state, ...} struct on stdout (always exit 0)."
        ),
    )
    parser.add_argument("--feature", required=True, help="Lifecycle feature slug.")
    parser.add_argument(
        "--number", required=True, type=int, help="The just-created PR number."
    )
    parser.add_argument(
        "--url",
        help=(
            "The just-created PR's URL. Paired with --head-branch, skips the "
            "gh pr view round-trip."
        ),
    )
    parser.add_argument(
        "--head-branch",
        help=(
            "The just-created PR's head branch. Paired with --url, skips the "
            "gh pr view round-trip."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-record-pr-opened")
    args = _build_parser().parse_args(argv)
    result = record_pr_opened(
        args.feature, args.number, url=args.url, head_branch=args.head_branch
    )
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
