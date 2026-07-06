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

Reuses ``cortex_command.lifecycle.complete_route``'s existing
``_atomic_write_json`` / ``_gh_repo`` primitives (Step 4's mechanics were
already duplicated once, for the Branch-3 orphan-PR reconstruction) rather
than re-implementing them a third time.

Takes the PR number (already known to the caller, having just run
``gh pr create`` via ``/cortex-core:pr``) and looks up its ``url``/
``head_branch`` via ``gh pr view`` — deterministic enrichment, not judgment.

States:
  ok        — ``pr.json`` written and ``pr_opened`` logged; ``number``,
              ``url``, ``head_branch``, ``opened_at``, ``repo`` are set.
  gh-error  — repo identity or PR metadata could not be resolved via ``gh``;
              ``message`` carries the diagnostic. Neither file is written.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.common import _resolve_user_project_root_from_cwd
from cortex_command.lifecycle.complete_route import _atomic_write_json, _gh_repo
from cortex_command.lifecycle_event import _append_event_atomic, _now_iso

KNOWN_STATES = ("ok", "gh-error")


def _gh_pr_view(number: int) -> Optional[dict]:
    """Return ``{"url": ..., "head_branch": ...}`` for *number*, or None on failure."""
    gh = shutil.which("gh")
    if gh is None:
        return None
    try:
        proc = subprocess.run(
            [gh, "pr", "view", str(number), "--json", "url,headRefName"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
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
    feature: str, number: int, project_root: Optional[Path] = None
) -> dict:
    """Resolve repo/PR identity, write ``pr.json``, and log ``pr_opened``."""
    repo = _gh_repo()
    if not repo:
        return {
            "state": "gh-error",
            "message": "gh repo view failed to resolve nameWithOwner",
        }

    pr_meta = _gh_pr_view(number)
    if pr_meta is None:
        return {
            "state": "gh-error",
            "message": f"gh pr view {number} failed to resolve url/headRefName",
        }

    root = project_root or _resolve_user_project_root_from_cwd()
    lifecycle_dir = root / "cortex" / "lifecycle" / feature
    opened_at = _now_iso()

    pr_obj = {
        "number": number,
        "url": pr_meta["url"],
        "head_branch": pr_meta["head_branch"],
        "opened_at": opened_at,
        "repo": repo,
    }
    _atomic_write_json(lifecycle_dir / "pr.json", pr_obj)

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
    _append_event_atomic(lifecycle_dir / "events.log", json.dumps(row) + "\n")

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
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-record-pr-opened")
    args = _build_parser().parse_args(argv)
    sys.stdout.write(json.dumps(record_pr_opened(args.feature, args.number)) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
