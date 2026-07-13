"""cortex-lifecycle-finalize — composes the Complete-phase finalization
(Steps 9–11) into one call.

Before the corpus-trim wave-2 follow-up, ``complete.md`` narrated three
back-to-back CLI calls in prose: mark the backlog item ``complete`` (Step 9),
resync the backlog index (Step 10), and log the ``feature_complete`` event
(Step 11). This verb composes them and returns ONE ``{state, ...}`` JSON
envelope, mirroring how ``cortex-lifecycle-enter`` composed the Step-2 entry.

The three composed pieces:

  1. **Backend-gated backlog write-back** — on ``--backend cortex-backlog`` the
     item is resolved from ``--backlog-file`` and ``update_item`` marks it
     ``complete`` with ``session_id=null`` (Step 9). ``update_item``'s own tail
     regenerates the backlog index via subprocess, so Step 10's separate
     two-tier index-regen fallback is retired — the composition does NOT add a
     second regen. That regen is **best-effort by ``update_item``'s contract**:
     a non-zero regen subprocess prints a WARNING but does NOT fail the update,
     so finalize does not verify it and reports ``index_regen: best-effort``
     (``not-run`` when no write-back ran) rather than masking the outcome under a
     bare ``finalized``. ``--backend none`` skips the write-back; any other value
     is an external tracker the skill updates best-effort (``external-backend``).
  2. **Counters read** — ``count_tasks``/``count_rework_cycles`` over the
     feature's ``plan.md``/``events.log`` supply the ``feature_complete``
     event's ``tasks_total``/``rework_cycles`` fields.
  3. **Idempotent ``feature_complete`` emission** — ``log_event`` writes the
     row **with ``merge_anchor: "merge"``**. This anchor is load-bearing:
     ``cortex_command/pipeline/metrics.py`` segments interactive from
     legacy-overnight completions on it, so it must be emitted here (the
     overnight ``advance_lifecycle.py`` path deliberately omits it and is NOT a
     template for this verb). Emission is skipped when a ``feature_complete``
     row already exists in ``events.log`` — matched on a **parsed** JSON
     ``event`` field, never a substring — so a commit-retry double invocation
     never appends a duplicate.

States:

  finalized        — cortex-backlog or none backend: the write-back ran
                     (or was skipped for want of an item / a disabled backend)
                     and the event was emitted (or idempotently skipped).
  external-backend — an external tracker backend: the local write-back was
                     skipped; the skill composes the equivalent completion
                     update on the configured tracker best-effort. The event
                     is still emitted (it is local and backend-independent).
  error            — an unexpected exception escaped ``finalize``; ``main``
                     catches it so the CLI emits a JSON struct and exits 0
                     rather than a traceback (the ``prepare_worktree`` pattern).

EXIT-2 CARVE-OUT: an ambiguous ``--backlog-file`` slug (multiple matching
backlog items) propagates as exit 2 with the candidate list on stderr, mirroring
``start_sync``'s ``_Exit2``. This error class is exempt from the never-crash JSON
envelope — the caller applies the same disambiguation rule it applied to the
underlying ``cortex-update-item`` exit-2. Only *unexpected* exceptions
JSON-encode.

Path resolution uses the cwd flavor (``_resolve_user_project_root_from_cwd``)
so the counters read, the idempotent ``events.log`` scan, and ``log_event``'s
own write target all resolve against the same physical tree — ``log_event``
resolves its path from cwd internally and cannot be handed a root, so finalize
matches it rather than diverging under ``CORTEX_REPO_ROOT``.

Root-resolution invariant across the verb family: ``enter`` resolves the project
root via ``CORTEX_REPO_ROOT`` (env-honoring) while ``finalize`` and
``register-artifact`` resolve it from cwd; callers must ensure the two agree
(overnight runs with cwd == repo root).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.backlog.resolve_item import (
    _format_candidates,
    _parse_frontmatter,
    resolve,
)
from cortex_command.backlog.update_item import update_item
from cortex_command.common import _resolve_user_project_root_from_cwd
from cortex_command.lifecycle.counters import count_rework_cycles, count_tasks
from cortex_command.lifecycle.protocol import PROTOCOL_VERSION
from cortex_command.lifecycle_event import log_event

KNOWN_STATES = ("finalized", "external-backend", "error")

_CORTEX_BACKLOG = "cortex-backlog"


class _Exit2(Exception):
    """Signals an ambiguous-slug backlog resolution to ``main`` (→ exit 2)."""


def _feature_complete_exists(events_log_path: Path) -> bool:
    """Return True when ``events.log`` already carries a ``feature_complete`` row.

    Each line is parsed defensively (non-JSON / malformed lines skipped, not
    raised on) and matched on the parsed ``event`` field — never a substring —
    so a commit-retry double invocation is guarded without false-matching a body
    that merely mentions the string. Missing/unreadable log → False.
    """
    if not events_log_path.exists():
        return False
    try:
        text = events_log_path.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(event, dict) and event.get("event") == "feature_complete":
            return True
    return False


def _apply_backlog_writeback(backend: str, backlog_file: str, root: Path) -> str:
    """Run the backend-gated Step-9 write-back; return a ``backlog`` signal.

    ``none`` → ``skipped`` (zero calls). An external tracker → ``external`` (the
    skill owns the best-effort update). ``cortex-backlog`` → resolve the item
    from *backlog_file* and ``update_item`` it to ``complete``; an empty or
    unresolved reference is ``no-item`` (skip silently, matching Step 9). An
    ambiguous reference raises ``_Exit2`` after writing the candidate list to
    stderr.
    """
    if backend == "none":
        return "skipped"
    if backend != _CORTEX_BACKLOG:
        return "external"

    if not backlog_file:
        return "no-item"

    backlog_dir = root / "cortex" / "backlog"
    ref = Path(backlog_file).stem
    result = resolve(ref, backlog_dir)

    if result.status == "ambiguous":
        items_with_fm = []
        for p in result.candidates:
            try:
                items_with_fm.append((p, _parse_frontmatter(p)))
            except Exception:  # noqa: BLE001 — a malformed candidate still lists
                items_with_fm.append((p, {}))
        sys.stderr.write(_format_candidates(result.candidates, items_with_fm) + "\n")
        raise _Exit2()

    if result.status == "not_found":
        return "no-item"

    # status == "ok": update_item regenerates the backlog index in its own tail.
    # This is the unconditional Complete-phase writer, so it advances
    # lifecycle_phase to ``complete`` in the SAME write — closing the #378 req-5
    # omission that otherwise froze finalized items at their prior phase (research).
    update_item(
        result.item,
        {"status": "complete", "lifecycle_phase": "complete"},
        backlog_dir,
        session_id=None,
    )
    return "updated"


def finalize(
    *,
    feature: str,
    backend: str,
    backlog_file: str,
    project_root: Optional[Path] = None,
) -> dict:
    """Compose the backend-gated write-back, counters read, and idempotent
    ``feature_complete`` emission.

    Returns the ``{state, ...}`` envelope. Raises ``_Exit2`` on an ambiguous
    backlog slug (→ the caller maps to exit 2).
    """
    root = project_root or _resolve_user_project_root_from_cwd()

    backlog_signal = _apply_backlog_writeback(backend, backlog_file, root)
    state = "finalized" if backend in (_CORTEX_BACKLOG, "none") else "external-backend"

    feature_dir = root / "cortex" / "lifecycle" / feature
    tasks_total, _tasks_checked = count_tasks(feature_dir / "plan.md")
    events_log = feature_dir / "events.log"
    rework_cycles = count_rework_cycles(events_log)

    if _feature_complete_exists(events_log):
        emitted = False
    else:
        log_event(
            event="feature_complete",
            feature=feature,
            fields=[
                ("json", "tasks_total", tasks_total),
                ("json", "rework_cycles", rework_cycles),
                ("str", "merge_anchor", "merge"),
            ],
        )
        emitted = True

    return {
        "state": state,
        "feature": feature,
        "backend": backend,
        "backlog": backlog_signal,
        "index_regen": "best-effort" if backlog_signal == "updated" else "not-run",
        "emitted": emitted,
        "tasks_total": tasks_total,
        "rework_cycles": rework_cycles,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-finalize",
        description=(
            "Compose the Complete-phase finalization — backend-gated backlog "
            "write-back, counters read, and idempotent feature_complete "
            "emission (with merge_anchor: merge) — into a single {state, ...} "
            "JSON struct on stdout. Exit 2 propagates an ambiguous backlog "
            "slug; every other outcome is exit 0."
        ),
    )
    parser.add_argument("--feature", required=True, metavar="SLUG", help="Lifecycle feature slug.")
    parser.add_argument(
        "--backend",
        required=True,
        help="Caller-resolved backlog backend (cortex-backlog | none | other).",
    )
    parser.add_argument(
        "--backlog-file",
        required=True,
        metavar="BASENAME",
        help='Resolver filename basename (e.g. 326-foo.md); "" when no item was identified.',
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-finalize")
    args = _build_parser().parse_args(argv)
    try:
        result = finalize(
            feature=args.feature,
            backend=args.backend,
            backlog_file=args.backlog_file,
        )
    except _Exit2:
        return 2
    except Exception as exc:  # noqa: BLE001 — always emit a JSON struct, never a traceback
        result = {"state": "error", "message": repr(exc)}
    result["protocol"] = PROTOCOL_VERSION
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
