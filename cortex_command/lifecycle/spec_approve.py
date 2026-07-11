"""cortex-lifecycle-spec-approve — order-enforcing spec-approval decision verb.

Composes the multi-emission spec-approval cluster the ``refine.md`` spec-approval
gate (and the lifecycle-wrapped ``lifecycle.md`` §Specify→Plan hand-off) used to
narrate as back-to-back ``cortex-lifecycle-event`` + ``cortex-update-item`` calls.
The function body IS the ordering invariant: the exact per-arm event sequence and
the backend-gated backlog write-back live here, so the emit-before-transition
stranding, drift, and buggy re-implementations a prose gate invited cannot recur.
Returns ONE ``{state, ...}`` JSON envelope whose ``state`` echoes the decision
discriminant the skill routes on.

This verb owns spec approval across THREE contexts, distinguished only by the
``--emit-transition`` / ``--no-emit-transition`` flag the caller passes:

  * **standalone refine** (``--no-emit-transition``) — refine stops at ``spec.md``
    and must NOT emit a ``specify→plan`` row (preserving today's standalone
    behavior); it still records the approval and the backend-gated write-back.
  * **lifecycle-wrapped refine** (``--emit-transition``) — the lifecycle continues
    to Plan, so the ``specify→plan`` phase_transition IS emitted.
  * **mid-sequence halt-before-Plan commit gate** — a crash between emissions is
    repaired by re-running the whole verb; each emission presence-checks
    independently.

The three decision arms and their EXACT ordered emissions:

  approved  → (a) ``spec_approved`` {decision: approved} — the optional consent
                  field records durable operator approval (Task-6 field)
              (b) IF ``--emit-transition``: ``phase_transition`` from=specify to=plan
              (c) backend-gated backlog write-back (status:refined + spec + areas)
                  via in-process ``update_item`` — the finalize precedent
  cancelled → (a) ``lifecycle_cancelled`` — nothing else
  revise    → nothing (short-circuit return before any mutation)

Each emission independently presence-checks ``events.log`` first — a **parsed**
``event``-field match (plus the discriminating ``from``/``to`` fields for
``phase_transition``, which shares its event name with the feature's earlier
lifecycle transitions), never a substring — so re-running the whole verb after a
crash between emissions repairs rather than duplicates. The backend write-back
(c) is idempotent by ``update_item``'s own nature (re-setting ``status:refined``
overwrites to the same value). The short-circuit ``revise`` arm returns before the
first mutating step.

Emission goes ONLY through ``log_event`` (the flock + O_APPEND + spaced-json
writer) so each row is byte-identical to what the equivalent typed
``cortex-lifecycle-event`` subcommand (``spec-approved``, ``phase-transition``,
``lifecycle-cancelled``) would produce.

``--areas`` is **preserve-on-omit**: omission is the common case, so an omitted
``--areas`` leaves the item's ``areas`` field untouched (the key is dropped from
the ``update_item`` fields dict). Clearing requires the explicit ``--clear-areas``
sentinel — mere omission never clears.

ADR-0019 "taken knowingly" scope-crossing: like ``cortex-lifecycle-start-sync``
(the #326 precedent), this verb's ``--backend`` guard gates the verb's *entire*
primary backlog action — on ``none`` / an external tracker it makes zero local
``cortex-update-item`` calls, and on ``cortex-backlog`` it writes backlog
*frontmatter* (``status:refined`` + ``spec`` + ``areas``) via in-process
``update_item`` rather than only the local ``events.log``. This boundary crossing
is taken knowingly (recorded on ADR-0019's precedent list, per the operator's
plan-approval choice), not silently. Per the dumb-arg-actor rule the verb acts on
the caller-passed ``--backend`` / ``--backlog-file`` — it never self-resolves them.

EXIT-2 CARVE-OUT: an ambiguous ``--backlog-file`` slug (multiple matching backlog
items) propagates as exit 2 with the candidate list on stderr, mirroring
``finalize``'s ``_Exit2``. This error class is exempt from the never-crash JSON
envelope — the caller applies the same disambiguation rule it applied to the
underlying ``cortex-update-item`` exit-2. Only *unexpected* exceptions JSON-encode.

A slug-shape guard rejects path separators and ``..`` in ``--feature`` before any
filesystem access. ``main`` never tracebacks: any escaping exception (and the
guard) yields a ``{"state": "error", ...}`` envelope on stdout at exit 0.

Root resolution uses the cwd flavor (``_resolve_user_project_root_from_cwd``),
matching ``lifecycle_event``/``finalize``/``plan_decision``/``review_verdict``:
``log_event`` resolves its own write target from the physical CWD and cannot be
handed a root, so this verb reads the same-tree ``events.log`` for the presence
checks and resolves the backlog dir under the same root. Caller-passed args only
(ADR-0019).
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
from cortex_command.lifecycle.protocol import PROTOCOL_VERSION
from cortex_command.lifecycle_event import log_event

_DECISIONS = ("approved", "cancelled", "revise")

KNOWN_STATES = (
    "approved",
    "cancelled",
    "revise",
    "error",
)

_CORTEX_BACKLOG = "cortex-backlog"


class _Exit2(Exception):
    """Signals an ambiguous-slug backlog resolution to ``main`` (→ exit 2)."""


def _reject_unsafe_slug(feature: str) -> Optional[dict]:
    """Return an error envelope when *feature* is empty or carries a path
    separator / ``..`` — a path-traversal guard applied BEFORE any filesystem
    access. Returns None when the slug is safe to use as a directory component.
    """
    if not feature or "/" in feature or "\\" in feature or ".." in feature:
        return {
            "state": "error",
            "message": f"unsafe feature slug {feature!r}: no path separators or '..'",
        }
    return None


def _event_exists(
    events_log_path: Path, event_name: str, match_fields: Optional[dict] = None
) -> bool:
    """Return True when ``events.log`` already carries a row whose parsed
    ``event`` field equals *event_name* (and, when *match_fields* is given, whose
    every listed key equals the given value).

    Each line is parsed defensively (non-JSON / malformed lines skipped, never
    raised on) and matched on parsed fields — never a substring — so the guard
    never false-matches a body that merely mentions the event string. The
    ``match_fields`` refinement is load-bearing for ``phase_transition``: the
    feature's ``events.log`` already carries earlier lifecycle transitions under
    the same event name, so only the ``from``/``to`` pair distinguishes the
    ``specify→plan`` row this verb owns. Missing/unreadable log → False.
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
        if not isinstance(event, dict) or event.get("event") != event_name:
            continue
        if match_fields and any(event.get(k) != v for k, v in match_fields.items()):
            continue
        return True
    return False


def _apply_backlog_writeback(
    backend: str,
    backlog_file: str,
    spec_path: str,
    areas: Optional[List[str]],
    clear_areas: bool,
    root: Path,
) -> str:
    """Run the backend-gated spec-approval write-back; return a ``backlog`` signal.

    Mirrors ``finalize._apply_backlog_writeback`` but sets ``status:refined`` +
    the ``spec`` path + (preserve-on-omit) ``areas`` rather than ``status:complete``.

    ``none`` → ``skipped`` (zero calls). An external tracker → ``external`` (the
    skill owns the best-effort update). ``cortex-backlog`` → resolve the item from
    *backlog_file* and ``update_item`` it; an empty or unresolved reference is
    ``no-item`` (skip silently). An ambiguous reference raises ``_Exit2`` after
    writing the candidate list to stderr.

    ``areas`` semantics: an omitted ``--areas`` (``areas is None`` and not
    *clear_areas*) drops the ``areas`` key so ``update_item`` leaves it untouched;
    ``--clear-areas`` writes an empty list; a non-empty list writes it.
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

    # status == "ok": set status:refined + spec + (preserve-on-omit) areas.
    fields: dict = {"status": "refined", "spec": spec_path}
    if clear_areas:
        fields["areas"] = []
    elif areas:
        fields["areas"] = areas
    update_item(result.item, fields, backlog_dir, session_id=None)
    return "updated"


def spec_approve(
    *,
    feature: str,
    decision: str,
    backend: str,
    backlog_file: str,
    spec_path: str,
    emit_transition: bool,
    areas: Optional[List[str]] = None,
    clear_areas: bool = False,
    project_root: Optional[Path] = None,
) -> dict:
    """Compose the spec-approval decision into its ordered, idempotent emissions
    plus the backend-gated backlog write-back.

    On ``approved``: (a) ``spec_approved{decision: approved}`` → (b) when
    *emit_transition*, ``phase_transition specify→plan`` → (c) the backend-gated
    write-back. On ``cancelled``: ``lifecycle_cancelled`` only. On ``revise``:
    nothing. Returns the ``{state, ...}`` envelope; ``state`` echoes *decision* on
    a handled arm, or ``"error"`` for the slug guard. Raises ``_Exit2`` on an
    ambiguous backlog slug (→ the caller maps to exit 2).
    """
    guard = _reject_unsafe_slug(feature)
    if guard is not None:
        return guard

    # revise: short-circuit before root resolution / any filesystem access.
    if decision == "revise":
        return {"state": "revise", "feature": feature, "emitted": []}

    root = project_root or _resolve_user_project_root_from_cwd()
    events_log = root / "cortex" / "lifecycle" / feature / "events.log"
    emitted: List[str] = []

    if decision == "cancelled":
        # (a) lifecycle_cancelled — nothing else.
        if not _event_exists(events_log, "lifecycle_cancelled"):
            log_event(event="lifecycle_cancelled", feature=feature)
            emitted.append("lifecycle_cancelled")
        return {"state": "cancelled", "feature": feature, "emitted": emitted}

    if decision == "approved":
        # (a) spec_approved{decision: approved} — record durable operator consent.
        if not _event_exists(events_log, "spec_approved"):
            log_event(
                event="spec_approved",
                feature=feature,
                fields=[("str", "decision", "approved")],
            )
            emitted.append("spec_approved")
        # (b) phase_transition specify->plan — ONLY when the caller wraps refine
        #     in the lifecycle (--emit-transition). Standalone refine suppresses
        #     it. from/to qualified so it never false-skips an earlier transition.
        if emit_transition and not _event_exists(
            events_log, "phase_transition", {"from": "specify", "to": "plan"}
        ):
            log_event(
                event="phase_transition",
                feature=feature,
                fields=[("str", "from", "specify"), ("str", "to", "plan")],
            )
            emitted.append("phase_transition")
        # (c) backend-gated backlog write-back — status:refined + spec + areas.
        #     May raise _Exit2 on an ambiguous slug (→ exit 2). Idempotent.
        backlog_signal = _apply_backlog_writeback(
            backend, backlog_file, spec_path, areas, clear_areas, root
        )
        return {
            "state": "approved",
            "feature": feature,
            "decision": "approved",
            "backend": backend,
            "backlog": backlog_signal,
            "emit_transition": emit_transition,
            "emitted": emitted,
        }

    # Unreachable via the CLI (argparse pins --decision to _DECISIONS); a direct
    # caller passing an unknown decision gets an error envelope, never a crash.
    return {"state": "error", "message": f"unknown decision {decision!r}"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-spec-approve",
        description=(
            "Resolve the spec-approval decision to a single {state, ...} JSON "
            "struct on stdout, emitting the arm's exact ordered events "
            "(idempotently) via the shared events.log writer and running the "
            "backend-gated backlog write-back (status:refined + spec + areas). "
            "Exit 2 propagates an ambiguous backlog slug; every other outcome is "
            "exit 0."
        ),
    )
    parser.add_argument("--feature", required=True, metavar="SLUG", help="Lifecycle feature slug.")
    parser.add_argument(
        "--decision",
        required=True,
        choices=list(_DECISIONS),
        help="Spec-approval decision discriminant (approved also feeds the consent field).",
    )
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
    parser.add_argument(
        "--spec-path",
        required=True,
        metavar="PATH",
        help="Spec artifact path written to the item's spec frontmatter field.",
    )
    transition = parser.add_mutually_exclusive_group()
    transition.add_argument(
        "--emit-transition",
        dest="emit_transition",
        action="store_true",
        help="Emit phase_transition specify->plan (lifecycle-wrapped refine).",
    )
    transition.add_argument(
        "--no-emit-transition",
        dest="emit_transition",
        action="store_false",
        help="Suppress the specify->plan transition (standalone refine; default).",
    )
    parser.set_defaults(emit_transition=False)
    parser.add_argument(
        "--areas",
        nargs="*",
        default=None,
        metavar="AREA",
        help="Areas to set (preserve-on-omit; omission leaves areas untouched).",
    )
    parser.add_argument(
        "--clear-areas",
        action="store_true",
        help="Explicit sentinel to clear the areas field (omission never clears).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-spec-approve")
    args = _build_parser().parse_args(argv)
    try:
        result = spec_approve(
            feature=args.feature,
            decision=args.decision,
            backend=args.backend,
            backlog_file=args.backlog_file,
            spec_path=args.spec_path,
            emit_transition=args.emit_transition,
            areas=args.areas,
            clear_areas=args.clear_areas,
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
