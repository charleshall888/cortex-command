"""Shared finalization-staging verb for the lifecycle Complete + Refine phases.

``cortex-lifecycle-stage-artifacts --phase {complete|refine} --feature {slug}``
stages the *exact* per-phase artifact set each phase stages today, over a
single shared staging engine that owns the **"enumerate explicit paths, never
directory-glob"** discipline. It extracts the staging shared by
``complete.md`` Step 11a and ``post-refine-commit.md`` and emits a single
compact-JSON signal on stdout::

    {"signal": "staged"|"nothing_staged", "staged_paths": [...]}

The caller acts on ``signal``: ``nothing_staged`` (the index matches HEAD after
staging — equivalent to ``git diff --cached --quiet`` exiting 0) → skip
``/cortex-core:commit`` silently and continue (complete → Step 12; refine →
lifecycle Step 3); ``staged`` → proceed to commit. ``staged_paths`` is the
sorted ``git diff --cached --name-only`` set (repo-relative) — the actual
staged index, the same set the per-phase staged-set test pins.

Per-phase staged set
--------------------

``--phase complete`` (Req 9 + Req 11):

* ``cortex/lifecycle/{slug}/{research,spec,plan,review,index}.md`` +
  ``events.log`` — those present on disk;
* the review-drift ``**File**:`` path(s) — iff ``review.md`` carries a
  ``## Suggested Requirements Update`` section, by the exact recorded path
  (no directory-scoped add on ``cortex/requirements/``);
* the **narrowed** backlog write-back: the resolved ticket file
  (``cortex/backlog/<resolved-filename>``) + ``cortex/backlog/index.md``.
  This **drops** today's ``git add -u cortex/backlog/`` sweep (bug 2): the two
  explicit-path adds capture only the files this finalization touches, never an
  unrelated dirty sibling ticket.

``--phase refine`` (Reqs 9, 10):

* scan ``events.log`` bottom-up for the most recent transition —
  ``phase_transition specify→plan`` (approval) or ``lifecycle_cancelled``
  (cancel);
* ``research.md, spec.md, index.md, events.log`` — those present, with
  ``spec.md`` **omitted** on the cancel path (the user cancelled before refine
  wrote it);
* the resolved ticket file (Context A — an originating backlog item exists).

Explicit-add discipline
-----------------------

Staging is always ``git add -- <explicit paths>`` over paths present on disk;
**never** a directory-scoped add (``git add cortex/lifecycle/`` etc.) and
**never** the ``-u`` tracked-modified form on ``cortex/lifecycle/``,
``cortex/backlog/``, or ``cortex/requirements/``.

NOT backend-aware
-----------------

Per the spec's Non-Requirements the verb does **not** branch on backlog
backend. The narrowed backlog behavior is *emergent*: on ``none``/external
backends the resolver returns no match (so the ticket file does not stage) and
``index.md`` is unmodified (so its add no-ops) — no ``local``/``none``/
``cortex-backlog`` branch is needed.

Path resolution uses ``_resolve_user_project_root_from_cwd()`` (ignores
``CORTEX_REPO_ROOT`` and handles the ``.git``-file worktree marker), so an
invocation from inside an ``interactive/{slug}`` worktree stages that
worktree's artifacts. Exit codes: non-zero **only** on a usage error or an
unresolvable project root. Structure mirrors ``complete_route.py`` /
``_cli_detect_phase`` — pure helpers + a thin ``main(argv) -> int`` that
serializes the verdict with ``json.dumps(separators=(",", ":")) + "\\n"``.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from cortex_command.backlog.resolve_item import resolve
from cortex_command.common import (
    CortexProjectRootError,
    _resolve_user_project_root_from_cwd,
)

_GIT_TIMEOUT = 10

_DRIFT_HEADING = "## Suggested Requirements Update"
_FILE_LINE = re.compile(r"\*\*File\*\*:\s*(.+)")


# ---------------------------------------------------------------------------
# Subprocess helper (graceful degradation — any failure maps to None)
# ---------------------------------------------------------------------------


def _run(args: list[str], cwd: str) -> Optional[subprocess.CompletedProcess]:
    """Run ``git <args>`` in *cwd*; return the CompletedProcess or None."""
    try:
        return subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None


# ---------------------------------------------------------------------------
# events.log reader (tolerant per-line json.loads — matches complete_route)
# ---------------------------------------------------------------------------


def _read_events(events_log: Path) -> list[dict]:
    """Return the parsed event dicts from *events_log* (tolerant, in order)."""
    if not events_log.is_file():
        return []
    try:
        content = events_log.read_text(errors="replace")
    except OSError:
        return []
    events: list[dict] = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict):
            events.append(ev)
    return events


def _detect_refine_submode(events_log: Path) -> str:
    """Detect the refine sub-mode by scanning *events_log* bottom-up.

    Returns ``"cancel"`` when the most recent of the two relevant events is
    ``lifecycle_cancelled``; ``"approval"`` when it is
    ``phase_transition specify→plan`` (also the default when neither is found).
    """
    for ev in reversed(_read_events(events_log)):
        etype = ev.get("event")
        if etype == "lifecycle_cancelled":
            return "cancel"
        if (
            etype == "phase_transition"
            and ev.get("from") == "specify"
            and ev.get("to") == "plan"
        ):
            return "approval"
    return "approval"


# ---------------------------------------------------------------------------
# review-drift File extraction (no directory-scoped add on requirements/)
# ---------------------------------------------------------------------------


def _extract_drift_files(review_md: Path) -> list[str]:
    """Extract each ``**File**:`` value under a ``## Suggested Requirements
    Update`` section of *review_md*.

    Returns the recorded repo-relative path(s) verbatim (one per section, in
    document order); ``[]`` when no such section exists. The format follows
    ``review.md`` §4a (``File`` / ``Section`` / ``Content``); review.md permits
    one section per drifted requirements file.
    """
    if not review_md.is_file():
        return []
    try:
        text = review_md.read_text(errors="replace")
    except OSError:
        return []
    files: list[str] = []
    in_section = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("## "):
            in_section = stripped == _DRIFT_HEADING
            continue
        if in_section:
            m = _FILE_LINE.match(stripped)
            if m:
                value = m.group(1).strip()
                if value:
                    files.append(value)
    return files


# ---------------------------------------------------------------------------
# Backlog write-back resolution (narrowed — explicit paths only, bug-2 fix)
# ---------------------------------------------------------------------------


def _resolve_backlog_filename(slug: str, root: Path) -> Optional[str]:
    """Resolve *slug* to its originating backlog filename, or None.

    Uses the shared ``resolve_item.resolve`` library against
    ``{root}/cortex/backlog`` (the same contract behind
    ``cortex-resolve-backlog-item``: exit-0 ``filename`` field == ``path.name``;
    exit 3 / no match / ambiguous / IO error → silently skip). On ``none`` /
    external backends the directory is empty-but-present so ``resolve`` returns
    ``not_found`` and the ticket file does not stage (emergent — no backend
    branch). Never a ``{slug}.md`` glob: the lifecycle slug is a truncated
    prefix of the backlog filename and would match zero files.
    """
    backlog_dir = root / "cortex" / "backlog"
    try:
        result = resolve(slug, backlog_dir)
    except Exception:
        return None
    if result.status == "ok" and result.item is not None:
        return result.item.name
    return None


# ---------------------------------------------------------------------------
# Per-phase explicit-path collection
# ---------------------------------------------------------------------------


def collect_paths(phase: str, slug: str, root: Path) -> list[str]:
    """Build the per-phase explicit candidate set, filtered to paths present
    on disk.

    Returns repo-relative POSIX path strings (sorted, deduplicated). This is
    the exact set ``git add --`` is run on; ``git`` no-ops on any unmodified
    member, so the *staged* set (``git diff --cached --name-only``) is a subset.
    Never contains a directory path — explicit files only.
    """
    lifecycle_rel = f"cortex/lifecycle/{slug}"
    candidates: list[str] = []

    if phase == "complete":
        for name in ("research", "spec", "plan", "review", "index"):
            candidates.append(f"{lifecycle_rel}/{name}.md")
        candidates.append(f"{lifecycle_rel}/events.log")
        # Review-drift requirements file(s), by exact recorded path.
        candidates.extend(_extract_drift_files(root / lifecycle_rel / "review.md"))
        # Narrowed backlog write-back: resolved ticket file + index.md only.
        backlog_name = _resolve_backlog_filename(slug, root)
        if backlog_name is not None:
            candidates.append(f"cortex/backlog/{backlog_name}")
        candidates.append("cortex/backlog/index.md")

    elif phase == "refine":
        submode = _detect_refine_submode(root / lifecycle_rel / "events.log")
        candidates.append(f"{lifecycle_rel}/research.md")
        if submode != "cancel":
            # spec.md omitted on the cancel path.
            candidates.append(f"{lifecycle_rel}/spec.md")
        candidates.append(f"{lifecycle_rel}/index.md")
        candidates.append(f"{lifecycle_rel}/events.log")
        backlog_name = _resolve_backlog_filename(slug, root)
        if backlog_name is not None:
            candidates.append(f"cortex/backlog/{backlog_name}")

    # Filter to paths present on disk (so the single git add never aborts on a
    # missing pathspec), dedupe, and sort.
    present = {rel for rel in candidates if (root / rel).exists()}
    return sorted(present)


# ---------------------------------------------------------------------------
# Staging engine
# ---------------------------------------------------------------------------


def stage(phase: str, slug: str, root: Path) -> dict:
    """Stage the per-phase artifact set and report the staging signal.

    Runs a single ``git add -- <explicit paths>`` (never a directory or ``-u``
    add), then reads ``git diff --cached --name-only`` to derive both the
    ``signal`` and ``staged_paths``.
    """
    paths = collect_paths(phase, slug, root)
    if paths:
        _run(["add", "--"] + paths, cwd=str(root))

    diff = _run(["diff", "--cached", "--name-only"], cwd=str(root))
    if diff is None or diff.returncode != 0:
        staged: list[str] = []
    else:
        staged = sorted(
            line.strip() for line in diff.stdout.splitlines() if line.strip()
        )
    return {
        "signal": "staged" if staged else "nothing_staged",
        "staged_paths": staged,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-stage-artifacts",
        description=(
            "Stage the per-phase lifecycle finalization artifact set via "
            "explicit git-add paths (never a directory glob) and emit a "
            "{signal, staged_paths} JSON verdict on stdout."
        ),
    )
    parser.add_argument(
        "--phase",
        required=True,
        choices=["complete", "refine"],
        help="Lifecycle phase whose staged set to assemble.",
    )
    parser.add_argument(
        "--feature",
        required=True,
        metavar="SLUG",
        help="Feature slug (e.g. my-feature).",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        root = _resolve_user_project_root_from_cwd()
    except CortexProjectRootError as exc:
        sys.stderr.write(f"cortex-lifecycle-stage-artifacts: {exc}\n")
        return 1
    result = stage(args.phase, args.feature, root)
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
