"""Lifecycle-start backlog write-back verb (caller-routed by ``--backend``).

``cortex-lifecycle-start-sync --backend B --backlog-file F --phase P
--session-id S --lifecycle-slug L`` owns the lifecycle-start
``cortex-update-item`` write-backs that ``backlog-writeback.md``'s "Backlog
Write-Back (Lifecycle Start)" section previously narrated inline.

Backend routing applies **ADR-0019's structural-guard principle**: the verb
acts on the caller-passed ``--backend`` and NEVER self-resolves it. (Scope note:
this extends ADR-0019's recorded events.log-verb precedent — ``start-sync``
writes backlog *frontmatter* via ``cortex-update-item`` and its ``--backend``
guard gates the verb's *entire* primary action, not just a single parameter.
The extension is recorded in ADR-0019's Trade-off/Consequences section.)

Per-arm behavior, given ``ref = Path(--backlog-file).stem`` (the
``cortex-update-item`` positional is a slug/id/uuid, never a path):

* ``--backlog-file ""`` → no match (resolver exit-3): zero calls, ``no_backlog``.
* ``cortex-backlog`` → ``cortex-update-item <ref> --status in_progress
  --session-id <S> --lifecycle-phase research``; and **only when ``--phase``
  is ``none``** (a brand-new lifecycle) additionally ``cortex-update-item <ref>
  --lifecycle-slug <L>``.
* ``none`` → zero ``cortex-update-item`` calls + a one-line advisory.
* any other value (an external tracker) → zero local calls + a one-line
  advisory; the skill's unchanged external-arm prose composes the equivalent
  update on the configured tracker (the verb carries no ``gh``/adapter logic).

Exit-2 passthrough (clones ``wontfix_cli._terminalize_backlog``): if any
``cortex-update-item`` call exits 2 (ambiguous slug), its candidate stderr is
re-emitted and ``main`` returns 2.

The verb shells ``cortex-update-item`` only — it reads/writes no repo files, so
it resolves no project root (``cortex-update-item`` resolves its own via
``CORTEX_REPO_ROOT``). This is the one honest deviation from the
``stage_artifacts`` skeleton's ``try/except CortexProjectRootError`` clone:
there is no root to resolve here.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from cortex_command.backlog import _telemetry

_UPDATE_ITEM = "cortex-update-item"


class _Exit2(Exception):
    """Signals a ``cortex-update-item`` exit-2 (ambiguous slug) to ``main``."""


def _update_item(item_args: list[str]) -> None:
    """Run ``cortex-update-item <item_args>``; passthrough exit-2 (Req 9).

    Clones ``wontfix_cli._terminalize_backlog``'s exit-2 handling: on
    returncode 2 (ambiguous slug) re-emit the child's stderr (the candidate
    list) and raise ``_Exit2`` so ``main`` returns 2. Any other returncode is
    treated as best-effort — the historic prose did not halt the lifecycle on a
    non-ambiguous write-back failure ("attempt to write the lifecycle start
    back").
    """
    result = subprocess.run(
        [_UPDATE_ITEM] + item_args,
        capture_output=True,
        text=True,
    )
    if result.returncode == 2:
        if result.stderr:
            sys.stderr.write(result.stderr)
        raise _Exit2()


def sync(
    *,
    backend: str,
    backlog_file: str,
    phase: str,
    session_id: str,
    lifecycle_slug: str,
) -> dict:
    """Run the caller-routed lifecycle-start write-backs; return a result dict.

    Raises ``_Exit2`` when a ``cortex-update-item`` call exits 2.
    """
    if not backlog_file:
        # Resolver exit-3 / no backlog match — nothing to write back.
        return {"signal": "no_backlog", "backend": backend}

    ref = Path(backlog_file).stem

    if backend == "cortex-backlog":
        calls: list[str] = []
        _update_item(
            [
                ref,
                "--status",
                "in_progress",
                "--session-id",
                session_id,
                "--lifecycle-phase",
                "research",
            ]
        )
        calls.append("status")
        if phase == "none":
            _update_item([ref, "--lifecycle-slug", lifecycle_slug])
            calls.append("lifecycle_slug")
        return {"signal": "synced", "backend": backend, "calls": calls}

    if backend == "none":
        return {
            "signal": "skipped",
            "backend": "none",
            "note": "backlog write-back disabled for this repo",
        }

    # Any other value — an external tracker. No local write, no adapter logic;
    # the skill's external-arm prose composes the equivalent update.
    return {
        "signal": "external",
        "backend": backend,
        "note": (
            "external backlog backend — compose the in-progress update "
            "(and, on a new lifecycle, the lifecycle-slug association) on the "
            "configured tracker per backlog.instructions"
        ),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-start-sync",
        description=(
            "Run the lifecycle-start backlog write-backs for the caller-passed "
            "--backend (ADR-0019 structural guard; never self-resolves) and "
            "emit a compact-JSON outcome on stdout."
        ),
    )
    parser.add_argument(
        "--backend",
        required=True,
        help="Caller-resolved backlog backend (cortex-backlog | none | other).",
    )
    parser.add_argument(
        "--backlog-file",
        required=True,
        help='Resolver filename basename (e.g. 326-foo.md); "" on no match.',
    )
    parser.add_argument(
        "--phase",
        required=True,
        help="Current phase (none for a brand-new lifecycle, else any value).",
    )
    parser.add_argument(
        "--session-id",
        required=True,
        help="Lifecycle session id ($LIFECYCLE_SESSION_ID).",
    )
    parser.add_argument(
        "--lifecycle-slug",
        required=True,
        help="Lifecycle slug (written only on a new lifecycle, --phase none).",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-start-sync")
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = sync(
            backend=args.backend,
            backlog_file=args.backlog_file,
            phase=args.phase,
            session_id=args.session_id,
            lifecycle_slug=args.lifecycle_slug,
        )
    except _Exit2:
        return 2
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
