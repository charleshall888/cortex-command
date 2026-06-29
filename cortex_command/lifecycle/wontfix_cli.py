"""cortex-lifecycle-wontfix — order-enforcing terminal wontfix verb.

Abandons a lifecycle as three sequential, gated, fail-forward steps in one
function:

    (a) archive-move  cortex/lifecycle/<slug> -> cortex/lifecycle/archive/<slug>
    (b) append a byte-faithful ``feature_wontfix`` row to the archived events.log
    (c) terminalize the linked backlog item (--status wontfix)

The order is load-bearing — the move first lands the safe end-state (the
name-based archive-skip at ``cortex_command/hooks/scan_lifecycle.py:907`` drops
the lifecycle from enumeration even if a later step fails). The structural
ordering here replaces the prose 3-step gate that used to live in
``skills/lifecycle/references/wontfix.md``; see ADR-0004 for the multi-step
sequentially-ordered-phase precedent this back-points to.

Fail-forward, never transactional: the move is never rolled back. On
re-invocation each step independently re-asserts its postcondition (move-if-not-
archived, append-if-no-row, terminalize-if-not-terminal), so an (a)-success /
(b)-failure partial run is fully repaired on re-run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.common import _resolve_user_project_root

# Private cross-module reuse: the flock + tempfile + os.replace atomic-append
# discipline. Imported as a name into THIS module's namespace so tests patch
# ``cortex_command.lifecycle.wontfix_cli._append_event_atomic`` (the binding the
# verb actually calls). The row-template regression test (test_wontfix_cli.py)
# pins the emitted bytes so a future refactor of the private helper fails loudly.
from cortex_command.lifecycle_event import _append_event_atomic

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class WontfixError(Exception):
    """Carries an exit code + operator-facing message for ``main`` to surface."""

    def __init__(self, exit_code: int, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.message = message


def _frontmatter_value(text: str, key: str) -> Optional[str]:
    m = re.search(rf"^{re.escape(key)}:\s*(\S+)", text, re.MULTILINE)
    return m.group(1) if m else None


def _read_backlog_target(index_md: Path) -> Optional[str]:
    """Resolve the backlog terminalization target from a lifecycle index.md.

    Prefers ``parent_backlog_uuid`` (deterministic) then ``parent_backlog_id``.
    Returns None for an ad-hoc lifecycle with no backlog parent (absent index.md
    or null parent fields) — step (c) is then a documented no-op.
    """
    if not index_md.is_file():
        return None
    text = index_md.read_text(encoding="utf-8")
    for key in ("parent_backlog_uuid", "parent_backlog_id"):
        value = _frontmatter_value(text, key)
        if value and value.lower() != "null":
            return value
    return None


def _archive_move(src: Path, dst: Path) -> None:
    """Step (a): 4-case pre-flight existence guard, then os.rename (fallback
    shutil.move). ``os.rename``/``shutil.move`` require the destination parent to
    exist, so the ``archive/`` dir is created first (init never scaffolds it)."""
    src_exists = src.exists()
    dst_exists = dst.exists()
    if dst_exists and not src_exists:
        return  # already archived — clean no-op
    if dst_exists and src_exists:
        raise WontfixError(1, f"both {src} and {dst} exist — refusing to nest; resolve manually")
    if not src_exists and not dst_exists:
        raise WontfixError(1, f"unknown slug: neither {src} nor {dst} exists")
    # src exists, dst does not -> move.
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(src, dst)
    except OSError:
        shutil.move(str(src), str(dst))


def _has_wontfix_row(events_log: Path) -> bool:
    if not events_log.is_file():
        return False
    for line in events_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Parsed event-field match — NOT a substring grep, which would
        # false-positive on a reason value containing "feature_wontfix".
        if obj.get("event") == "feature_wontfix":
            return True
    return False


def _append_wontfix_row(events_log: Path, slug: str, reason: str) -> None:
    """Step (b): idempotent byte-faithful append to the archived events.log."""
    if _has_wontfix_row(events_log):
        return
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Default json.dumps separators (", ", ": "), insertion-ordered keys,
    # Z-suffixed timestamp, no schema_version. The trailing newline is the
    # caller's responsibility — _append_event_atomic writes its arg verbatim.
    row = json.dumps(
        {"ts": ts, "event": "feature_wontfix", "feature": slug, "reason": reason}
    )
    _append_event_atomic(events_log, row + "\n")


def _terminalize_backlog(target: Optional[str]) -> None:
    """Step (c): shell to cortex-update-item. Ad-hoc lifecycle (no parent) is a
    documented no-op. Re-running on an already-wontfix item is idempotent."""
    if target is None:
        return
    result = subprocess.run(
        [
            "cortex-update-item",
            target,
            "--status",
            "wontfix",
            "--lifecycle-phase",
            "wontfix",
            "--session-id",
            "null",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return
    if result.returncode == 2:
        # Ambiguous resolution — candidates already on the child's stderr.
        if result.stderr:
            sys.stderr.write(result.stderr)
        raise WontfixError(2, f"ambiguous backlog resolution for {target!r}")
    raise WontfixError(
        1,
        f"backlog terminalization failed for {target!r} "
        f"(cortex-update-item exit {result.returncode}): {result.stderr.strip()}",
    )


def _run(args: argparse.Namespace) -> int:
    slug = args.slug
    if not _SLUG_RE.match(slug):
        # Path-traversal guard for direct callers — before any filesystem op.
        raise WontfixError(2, f"invalid slug {slug!r}: must match ^[a-z0-9]+(-[a-z0-9]+)*$")

    env_root = os.environ.get("CORTEX_REPO_ROOT")
    root = _resolve_user_project_root()
    # Worktree refusal: _resolve_user_project_root() returns the worktree root
    # (its own cortex/) when invoked from a worktree with no env override; a
    # worktree's .git is a gitdir-pointer FILE. Refuse rather than archive a
    # worktree-local copy while the main-resident lifecycle is untouched.
    if not env_root and (root / ".git").is_file():
        raise WontfixError(
            1,
            "refusing destructive archive from a worktree without CORTEX_REPO_ROOT set "
            "(would target a worktree-local copy, not the main-resident lifecycle)",
        )

    lifecycle = root / "cortex" / "lifecycle"
    src = lifecycle / slug
    dst = lifecycle / "archive" / slug

    # Resolve the backlog target BEFORE the move (read whichever dir exists, so a
    # re-run after a partial archive still finds index.md under archive/).
    if args.backlog_slug:
        target: Optional[str] = args.backlog_slug
    else:
        index_md = (src if src.exists() else dst) / "index.md"
        target = _read_backlog_target(index_md)

    _archive_move(src, dst)  # (a)
    _append_wontfix_row(dst / "events.log", slug, args.reason)  # (b)
    _terminalize_backlog(target)  # (c)

    sys.stdout.write(f"wontfix: archived {slug} -> cortex/lifecycle/archive/{slug}\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-wontfix",
        description=(
            "Abandon a lifecycle: archive it, append a feature_wontfix marker, "
            "and terminalize the linked backlog item (order-enforcing, "
            "fail-forward, idempotent)."
        ),
    )
    parser.add_argument("slug", help="Lifecycle slug to abandon (cortex/lifecycle/<slug>).")
    parser.add_argument(
        "--reason",
        default="",
        help="Short rationale recorded on the feature_wontfix event.",
    )
    parser.add_argument(
        "--backlog-slug",
        default=None,
        help="Override the backlog terminalization target (default: read from index.md parent).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-wontfix")
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except WontfixError as exc:
        sys.stderr.write(f"cortex-lifecycle-wontfix: {exc.message}\n")
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())
