"""cortex-lifecycle-state — emit a feature's canonical criticality and tier as JSON.

Usage:
  cortex-lifecycle-state --feature <slug>
  cortex-lifecycle-state --feature <slug> --field criticality
  cortex-lifecycle-state --feature <slug> --field tier [--raw]

Output:
  Without --field: {"criticality": "<value>", "tier": "<value>"} — keys absent
  when no relevant event was found in events.log (caller defaults criticality
  to "medium", tier to "simple"). When events.log is missing, output {}.

  With --field: JSON containing only the requested key (omitted when empty).

  With --field --raw: the bare scalar (no JSON), for command substitution —
  e.g. cortex-resolve-model --criticality "$(cortex-lifecycle-state ... --raw)".
  An axis never set emits the documented caller default (criticality "medium",
  tier "simple"); a corrupted log whose axis is unknowable exits 2 instead of
  guessing (use the JSON form, which carries "corrupted": true).

Canonical rules (delegated to cortex_command.common.reduce_lifecycle_state,
the single tolerant reducer shared with read_tier / read_criticality and
refine, so all three readers agree by construction):
  criticality: `lifecycle_start.criticality` superseded by
               `criticality_override.to`, whichever appears most recently.
  tier:        `lifecycle_start.tier` superseded by `complexity_override.to`,
               whichever appears most recently.

Torn-line behavior: a torn or out-of-vocabulary line is skipped (and
recorded for the CLI warning) rather than collapsing the whole reduction.
The last valid value for each axis wins, so stdout is the recovered
accumulator dict (never "null") with exit 0.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional

from cortex_command.common import reduce_lifecycle_state

# ---------------------------------------------------------------------------
# Help text — extracted from the bash script's docblock (lines 2-25, stripped
# of leading `# ` or `#`) to preserve byte-identical parity on --help.
# The bash script used: sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
# ---------------------------------------------------------------------------

_HELP_TEXT = """\
cortex-lifecycle-state — emit a feature's canonical criticality and tier as JSON.

Usage:
  cortex-lifecycle-state --feature <slug>
  cortex-lifecycle-state --feature <slug> --field criticality
  cortex-lifecycle-state --feature <slug> --field tier [--raw]

Output:
  Without --field: {"criticality": "<value>", "tier": "<value>"} — keys absent
  when no relevant event was found in events.log (caller defaults criticality
  to "medium", tier to "simple"). When events.log is missing, output {}.

  With --field: JSON containing only the requested key (omitted when empty).

  With --field --raw: the bare scalar (no JSON), for command substitution.
  An axis never set emits the documented caller default (criticality "medium",
  tier "simple"); a corrupted log whose axis is unknowable exits 2 instead of
  guessing (use the JSON form, which carries "corrupted": true).

Canonical rules (delegated to cortex_command.common.reduce_lifecycle_state,
shared with read_tier / read_criticality and refine):
  criticality: `lifecycle_start.criticality` superseded by
               `criticality_override.to`, whichever appears most recently.
  tier:        `lifecycle_start.tier` superseded by `complexity_override.to`,
               whichever appears most recently.

A torn or out-of-vocabulary line is skipped (last valid value wins) rather
than collapsing the reduction; stdout is the accumulator dict, never "null".
"""

# The documented caller-side defaults (--raw emits them when the axis was
# never set, so a command substitution always yields a valid enum).
_RAW_DEFAULTS = {"criticality": "medium", "tier": "simple"}

# Accepted --field values (from bash script lines 61-67).
_ACCEPTED_FIELDS = frozenset({"criticality", "tier"})


def _reduce_events(events_path: Path) -> dict:
    """Reduce events.log to the {criticality, tier} accumulator dict.

    Thin compatibility wrapper over ``common.reduce_lifecycle_state`` — kept
    (rather than inlined) because tests import it as the canonical reduction
    oracle. A torn or out-of-vocabulary line is skipped (never collapses the
    reduction to ``null``); the last valid value for each axis wins, and keys
    are absent when never set.

    Returns:
        A dict with at most two keys ("criticality", "tier").
    """
    return reduce_lifecycle_state(events_path).state


def _filter_field(obj: dict, field: str) -> dict:
    """Apply the --field filter to the accumulated result.

    The reduction is always a dict (the shared reducer never returns ``null``),
    so this projects to a single-key dict when the requested key is present,
    else ``{}``. With no ``--field``, returns the dict unchanged.
    """
    if field == "criticality":
        if "criticality" in obj:
            return {"criticality": obj["criticality"]}
        return {}
    elif field == "tier":
        if "tier" in obj:
            return {"tier": obj["tier"]}
        return {}
    # No field filter: return as-is.
    return obj


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point for cortex-lifecycle-state."""
    args = sys.argv[1:] if argv is None else list(argv)

    feature: Optional[str] = None
    field: str = ""
    raw = False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--feature":
            i += 1
            feature = args[i] if i < len(args) else ""
        elif arg == "--field":
            i += 1
            field = args[i] if i < len(args) else ""
        elif arg == "--raw":
            raw = True
        elif arg in ("-h", "--help"):
            sys.stdout.write(_HELP_TEXT)
            sys.exit(0)
        else:
            sys.stderr.write(
                f"cortex-lifecycle-state: unknown argument: {arg}\n"
            )
            sys.exit(2)
        i += 1

    if not feature:
        sys.stderr.write(
            "cortex-lifecycle-state: --feature <slug> is required\n"
        )
        sys.exit(2)

    if field and field not in _ACCEPTED_FIELDS:
        sys.stderr.write(
            f"cortex-lifecycle-state: --field must be 'criticality' or 'tier'"
            f" (got: {field})\n"
        )
        sys.exit(2)

    if raw and not field:
        sys.stderr.write(
            "cortex-lifecycle-state: --raw requires --field\n"
        )
        sys.exit(2)

    events_path = Path("cortex") / "lifecycle" / feature / "events.log"

    if not events_path.is_file():
        if raw:
            # No log at all: the documented caller default, same as an axis
            # never set — a command substitution still yields a valid enum.
            sys.stdout.write(_RAW_DEFAULTS[field] + "\n")
            sys.exit(0)
        sys.stdout.write("{}\n")
        sys.exit(0)

    reduction = reduce_lifecycle_state(events_path)

    # CLI-only diagnostic: one stderr warning per skipped line (parse failure
    # or out-of-vocabulary rejection), exit code unchanged. The library readers
    # (read_tier/read_criticality/refine) stay silent — only this CLI surfaces
    # the lines. "unusable" rather than "malformed" because skipped_lines also
    # covers vocab-rejected lines that parsed fine but carried no accepted value.
    for lineno in reduction.skipped_lines:
        sys.stderr.write(
            f"cortex-lifecycle-state: warning: skipped unusable line at "
            f"{events_path}:{lineno}\n"
        )

    result = reduction.state

    if raw:
        # Bare-scalar composition mode (#400): the value when present, the
        # documented caller default when the axis was simply never set, and a
        # loud exit 2 when corruption left it unknowable — never a silently
        # defaulted enum a gate-deciding consumer would trust.
        value = result.get(field)
        if value is not None:
            sys.stdout.write(str(value) + "\n")
            sys.exit(0)
        if reduction.corrupted:
            sys.stderr.write(
                f"cortex-lifecycle-state: {field} unknowable (corrupted "
                f"events.log) — use the JSON form, which carries "
                f'"corrupted": true\n'
            )
            sys.exit(2)
        sys.stdout.write(_RAW_DEFAULTS[field] + "\n")
        sys.exit(0)

    if field:
        result = _filter_field(result, field)

    # Additive corruption signal: when corruption left the tier or criticality
    # unknowable, surface "corrupted": true so the gate-deciding consumers
    # (which read --field tier) fail safe toward review. Appended after the
    # filter so it rides through on both the unfiltered and --field paths;
    # absent entirely for every clean log (output shape unchanged).
    if reduction.corrupted:
        result = {**result, "corrupted": True}

    sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
