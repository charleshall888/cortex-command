"""cortex-morning-review-close-tickets — composes morning-review walkthrough
§6b's per-feature backlog-ticket close loop into one call.

Before this consolidation, §6b narrated the loop as prose: for each
completed feature, run ``cortex-update-item {backlog_id} --status complete``
and report one of "closed #ID", "no ticket found", or "ambiguous slug" —
after resolving the active backlog backend once via
``cortex-read-backlog-backend`` and branching on its value.

This verb owns the loop and the ``cortex-backlog``/``none`` arms of that
3-arm routing. It reuses the SAME primitives ``cortex-update-item`` itself
is built from — ``cortex_command.backlog.update_item._find_item_with_status``
(the shared 5-step resolver) and ``update_item()`` (the atomic frontmatter
writer, which already prints "Parent epic also closed: ..." when the
terminal-status cascade closes a parent) — mirroring how
``cortex_command.overnight.outcome_router`` already calls these same two
functions directly rather than subprocessing to the console script. The
third arm (an external tracker) needs freeform judgment (``backlog.instructions``,
composing a best-effort ``gh issue close`` or equivalent) that only an agent
can perform, so it is NOT handled here — this verb reports ``external`` per
item and skill prose does the actual best-effort close.

ADR-0019 (dumb arg-actor): the caller passes an explicit ``--item
FEATURE=IDENTIFIER`` pair per feature (repeatable) rather than this verb
scanning ``overnight-state.json`` for backlog_id/feature pairs itself — the
skill already holds this list from Section 2's per-feature display. Likewise
the already-resolved ``--backend`` value is passed in; this verb does not
invoke ``cortex-read-backlog-backend`` itself.

Per-item states (nested in ``results[i]["state"]``):
  closed           — the item was resolved and its status set to complete.
                     ``id`` carries the item's numeric ID; ``parent_closed``
                     is set (true) only when the update cascaded a parent
                     epic close.
  no-ticket        — the resolver found no matching item.
  ambiguous        — the resolver found multiple candidates; ``message``
                     carries the same candidate listing
                     ``cortex-update-item`` would print to stderr.
  skipped-disabled — ``--backend`` is ``none``; nothing was touched.
  external         — ``--backend`` is neither ``cortex-backlog`` nor ``none``
                     (an external tracker); the caller must best-effort close
                     it per ``backlog.instructions``.
  error            — an unexpected exception (e.g. a malformed backlog item)
                     escaped resolution/update for this one item; it does not
                     abort the rest of the batch.

Top-level state (``KNOWN_STATES``) is always ``ok`` unless an exception
escapes ``close_tickets`` itself (e.g. the project root is unresolvable),
in which case ``main`` catches it and emits ``{"state": "error", ...}`` —
the CLI always emits a JSON struct and exits 0.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from cortex_command.backlog import _telemetry
from cortex_command.backlog.resolve_item import ResolutionError, _format_candidates, _parse_frontmatter
from cortex_command.backlog.update_item import _find_item_with_status, _get_item_id, update_item
from cortex_command.common import _resolve_user_project_root

KNOWN_STATES = ("ok", "error")
KNOWN_ITEM_STATES = (
    "closed",
    "no-ticket",
    "ambiguous",
    "skipped-disabled",
    "external",
    "error",
)

_CORTEX_BACKLOG = "cortex-backlog"
_DISABLED_BACKEND = "none"

_PARENT_CLOSED_MARKER = "Parent epic also closed:"


class _ItemAction(argparse.Action):
    """Collect repeated ``--item FEATURE=IDENTIFIER`` tokens into an ordered
    list of ``(feature, identifier)`` tuples, mirroring
    ``cortex_command.lifecycle_event._SetFieldAction``'s repeatable-flag shape.
    """

    def __call__(self, parser, namespace, values, option_string=None):
        if "=" not in values:
            parser.error(
                f"argument --item: expected FEATURE=IDENTIFIER, got {values!r}"
            )
        feature, identifier = values.split("=", 1)
        if not feature or not identifier:
            parser.error(
                f"argument --item: FEATURE and IDENTIFIER must both be "
                f"non-empty, got {values!r}"
            )
        items = getattr(namespace, self.dest, None)
        if items is None:
            items = []
            setattr(namespace, self.dest, items)
        items.append((feature, identifier))


def _close_one(feature: str, identifier: str, backend: str, backlog_dir: Path) -> dict:
    """Close one feature's backlog ticket, or report why it wasn't closed."""
    if backend == _DISABLED_BACKEND:
        return {"feature": feature, "state": "skipped-disabled"}

    if backend != _CORTEX_BACKLOG:
        return {"feature": feature, "state": "external"}

    try:
        result = _find_item_with_status(identifier, backlog_dir)
    except ResolutionError as exc:
        return {"feature": feature, "state": "error", "message": str(exc)}

    if result.status == "ambiguous":
        items_with_fm = []
        for path in result.candidates:
            try:
                items_with_fm.append((path, _parse_frontmatter(path)))
            except Exception:
                items_with_fm.append((path, {}))
        return {
            "feature": feature,
            "state": "ambiguous",
            "message": _format_candidates(result.candidates, items_with_fm),
        }

    if result.status == "not_found":
        return {"feature": feature, "state": "no-ticket"}

    item_path = result.item
    assert item_path is not None  # status="ok" guarantees item is set

    # update_item() prints "Parent epic also closed: <path>" to stdout when
    # the terminal-status cascade closes a parent epic — captured here rather
    # than re-deriving the cascade condition, since that logic (all siblings
    # terminal) already lives in update_item._check_and_close_parent.
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            # Unconditional completion writer: advance lifecycle_phase to
            # ``complete`` in the SAME write so a closed ticket's phase tracks its
            # status rather than freezing at its prior phase (#378 req-5).
            update_item(
                item_path,
                {"status": "complete", "lifecycle_phase": "complete"},
                backlog_dir,
            )
    except Exception as exc:  # noqa: BLE001 — one item's failure must not abort the batch
        return {"feature": feature, "state": "error", "message": repr(exc)}

    entry: dict = {"feature": feature, "state": "closed", "id": _get_item_id(item_path)}
    if _PARENT_CLOSED_MARKER in buf.getvalue():
        entry["parent_closed"] = True
    return entry


def close_tickets(
    items: List[Tuple[str, str]],
    backend: str,
    project_root: Optional[Path] = None,
) -> dict:
    """Close (or report on) each ``(feature, identifier)`` pair in *items*.

    *backend* is the already-resolved ``cortex-read-backlog-backend`` value —
    this verb routes on it but does not resolve it itself (ADR-0019).
    """
    root = project_root or _resolve_user_project_root()
    backlog_dir = root / "cortex" / "backlog"
    results = [
        _close_one(feature, identifier, backend, backlog_dir)
        for feature, identifier in items
    ]
    return {"state": "ok", "results": results}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-morning-review-close-tickets",
        description=(
            "Close each given feature's backlog ticket per morning-review "
            "walkthrough §6b, routed on an already-resolved backend value. "
            "Emits a single {state, results} struct on stdout (always exit 0)."
        ),
    )
    parser.add_argument(
        "--item",
        dest="items",
        action=_ItemAction,
        default=None,
        metavar="FEATURE=IDENTIFIER",
        help=(
            "One completed feature to close, as FEATURE=IDENTIFIER (repeatable). "
            "IDENTIFIER is whatever cortex-update-item accepts: the zero-padded "
            "numeric backlog_id, or the lifecycle feature slug as a fallback."
        ),
    )
    parser.add_argument(
        "--backend",
        required=True,
        help=(
            "The already-resolved cortex-read-backlog-backend value. "
            "'cortex-backlog' closes each item; 'none' skips all with an "
            "advisory; any other value is reported as 'external' for the "
            "caller to best-effort close."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-morning-review-close-tickets")
    args = _build_parser().parse_args(argv)
    items = args.items or []
    try:
        result = close_tickets(items, args.backend)
    except Exception as exc:  # noqa: BLE001 — always emit a JSON struct, never a traceback
        result = {"state": "error", "message": repr(exc)}
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
