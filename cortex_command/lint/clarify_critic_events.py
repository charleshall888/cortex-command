"""clarify_critic events.log schema gate (#186, per #178 R7).

Validates the v3 write shape of ``clarify_critic`` events in lifecycle
``events.log`` files — the structural mitigation for the OQ3 soften that
turned ``skills/refine/references/clarify-critic.md``'s prose imperatives
into declarative phrasing. The one invariant the v3 counts-only schema can
still express programmatically:

    dismissals_count == dispositions.dismiss

plus field presence/typing for the documented v3 shape (``parent_epic_loaded``
bool, non-negative counts, ``dispositions.{apply,dismiss,ask}`` ints,
``status`` in {ok, failed}).

Scope: rows whose ``schema_version`` is an integer >= 3 — the only shape new
producers emit. Legacy shapes (minimal v1, v1+dismissals, v2, YAML-block) are
tolerated forever per the reference's legacy-tolerance rule, so they are
skipped, never flagged; the same scoping keeps the gate from flagging
historical events that pre-date the invariant (the ticket's stated risk).
Non-JSON lines are skipped too — torn-line tolerance is the readers'
discipline, not this gate's concern.

Two invocation shapes:

- explicit paths: validate exactly those events.log files.
- no paths: sweep ``<root>/cortex/lifecycle/**/events.log`` (``--root``
  defaults to the CWD; the sweep includes ``archive/``).

Exit codes: 0 clean, 1 violations found (each printed as
``<path>:<lineno>: <message>``), 2 usage error. Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

_EVENT_NAME = "clarify_critic"
_MIN_VALIDATED_SCHEMA = 3
_VALID_STATUS = ("ok", "failed")
_DISPOSITION_KEYS = ("apply", "dismiss", "ask")
_COUNT_FIELDS = ("findings_count", "applied_fixes_count", "dismissals_count")


def _is_count(value: object) -> bool:
    """True for a non-negative int that is not a bool."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def validate_event(obj: dict) -> List[str]:
    """Return violation messages for one parsed ``clarify_critic`` row.

    Empty list means the row is valid OR out of scope (a legacy shape this
    gate deliberately never flags).
    """
    schema_version = obj.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version < _MIN_VALIDATED_SCHEMA
    ):
        return []

    violations: List[str] = []

    if not isinstance(obj.get("parent_epic_loaded"), bool):
        violations.append(
            "parent_epic_loaded must be a bool "
            f"(got {obj.get('parent_epic_loaded')!r})"
        )

    for field in _COUNT_FIELDS:
        if not _is_count(obj.get(field)):
            violations.append(
                f"{field} must be a non-negative int (got {obj.get(field)!r})"
            )

    dispositions = obj.get("dispositions")
    if not isinstance(dispositions, dict):
        violations.append(
            f"dispositions must be an object (got {dispositions!r})"
        )
    else:
        for key in _DISPOSITION_KEYS:
            if not _is_count(dispositions.get(key)):
                violations.append(
                    f"dispositions.{key} must be a non-negative int "
                    f"(got {dispositions.get(key)!r})"
                )

    if obj.get("status") not in _VALID_STATUS:
        violations.append(
            f"status must be one of {_VALID_STATUS} (got {obj.get('status')!r})"
        )

    # The invariant the softened prose imperative used to carry: the
    # dismissals count and the dismiss disposition are one number.
    if (
        isinstance(dispositions, dict)
        and _is_count(dispositions.get("dismiss"))
        and _is_count(obj.get("dismissals_count"))
        and obj["dismissals_count"] != dispositions["dismiss"]
    ):
        violations.append(
            "invariant violated: dismissals_count "
            f"({obj['dismissals_count']}) != dispositions.dismiss "
            f"({dispositions['dismiss']})"
        )

    return violations


def check_file(path: Path) -> List[str]:
    """Validate every ``clarify_critic`` row in *path*.

    Returns ``<path>:<lineno>: <message>`` strings. An unreadable file is a
    single violation (fail closed — this gate exists to be loud).
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"{path}: unreadable ({exc})"]

    results: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue  # torn / YAML-block legacy lines are out of scope
        if not isinstance(obj, dict) or obj.get("event") != _EVENT_NAME:
            continue
        for message in validate_event(obj):
            results.append(f"{path}:{lineno}: {message}")
    return results


def _sweep(root: Path) -> List[Path]:
    """Return every events.log under ``<root>/cortex/lifecycle`` (sorted)."""
    lifecycle_dir = root / "cortex" / "lifecycle"
    if not lifecycle_dir.is_dir():
        return []
    return sorted(lifecycle_dir.rglob("events.log"))


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cortex-check-clarify-critic-events",
        description=(
            "Validate v3 clarify_critic events in lifecycle events.log files "
            "(field shape + the dismissals_count == dispositions.dismiss "
            "invariant). Legacy pre-v3 shapes are skipped, never flagged."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        metavar="EVENTS_LOG",
        help="Explicit events.log files; omitted, sweep <root>/cortex/lifecycle.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        metavar="DIR",
        help="Sweep root when no explicit paths are given (default: CWD).",
    )
    args = parser.parse_args(argv)

    targets = list(args.paths) if args.paths else _sweep(args.root)

    violations: List[str] = []
    for path in targets:
        violations.extend(check_file(path))

    for line in violations:
        print(line, file=sys.stderr)
    if violations:
        print(
            f"cortex-check-clarify-critic-events: {len(violations)} violation(s) "
            f"across {len(targets)} file(s); the v3 write shape is documented in "
            "skills/refine/references/clarify-critic.md §Event Logging.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
