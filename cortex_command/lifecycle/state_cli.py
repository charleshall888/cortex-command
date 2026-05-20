"""cortex-lifecycle-state — emit a feature's canonical criticality and tier as JSON.

Usage:
  cortex-lifecycle-state --feature <slug>
  cortex-lifecycle-state --feature <slug> --field criticality
  cortex-lifecycle-state --feature <slug> --field tier

Output:
  Without --field: {"criticality": "<value>", "tier": "<value>"} — keys absent
  when no relevant event was found in events.log (caller defaults criticality
  to "medium", tier to "simple"). When events.log is missing, output {}.

  With --field: JSON containing only the requested key (omitted when empty).

Canonical rules (mirror cortex_command.common.read_tier / read_criticality):
  criticality: most-recent `criticality` field on `lifecycle_start` or
               `criticality_override` events.
  tier:        `lifecycle_start.tier` superseded by `complexity_override.to`,
               whichever appears most recently.

JSONL streaming via `jq fromjson?` — tolerates the spaced (`"event": "X"`)
and compact (`"event":"X"`) serialization styles uniformly, and silently
skips torn or malformed lines.

Torn-line behavior: replicates jq-1.8.1 reduce semantics — if ANY line in
events.log fails JSON parsing, the reduce result is null (not a partial
accumulator). Stdout will contain "null" and exit 0, matching the bash+jq
pre-deletion capture.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional

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
  cortex-lifecycle-state --feature <slug> --field tier

Output:
  Without --field: {"criticality": "<value>", "tier": "<value>"} — keys absent
  when no relevant event was found in events.log (caller defaults criticality
  to "medium", tier to "simple"). When events.log is missing, output {}.

  With --field: JSON containing only the requested key (omitted when empty).

Canonical rules (mirror cortex_command.common.read_tier / read_criticality):
  criticality: most-recent `criticality` field on `lifecycle_start` or
               `criticality_override` events.
  tier:        `lifecycle_start.tier` superseded by `complexity_override.to`,
               whichever appears most recently.

JSONL streaming via `jq fromjson?` — tolerates the spaced (`"event": "X"`)
and compact (`"event":"X"`) serialization styles uniformly, and silently
skips torn or malformed lines.
"""

# Accepted --field values (from bash script lines 61-67).
_ACCEPTED_FIELDS = frozenset({"criticality", "tier"})


def _reduce_events(events_path: Path) -> object:
    """Read events.log and reduce to {criticality, tier} accumulator dict.

    Replicates jq-1.8.1 reduce semantics:
    - If ANY line fails JSON parsing, return None (jq's null).
    - Otherwise accumulate: lifecycle_start sets criticality + tier;
      criticality_override sets criticality (from .to or .criticality);
      complexity_override sets tier (from .to or .tier).
    - Keys absent when never set.

    Returns:
        A dict with at most two keys ("criticality", "tier"), or None if
        any line was malformed (replicating jq-1.8.1 reduce-to-null).
    """
    acc: dict[str, str] = {}

    for raw_line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            # Replicates jq-1.8.1: any malformed line collapses the
            # entire reduce to null.
            return None
        if not isinstance(record, dict):
            # Non-object lines collapse reduce to null (same semantics:
            # fromjson? on a non-object JSON value still yields a value,
            # but .event access on it yields null which falls to the
            # else branch — not a parse failure — so non-dict does NOT
            # trigger null. Treat it as a no-op (else branch below).
            continue
        event = record.get("event")
        if event == "lifecycle_start":
            crit = record.get("criticality")
            if isinstance(crit, str) and crit:
                acc["criticality"] = crit
            tier = record.get("tier")
            if isinstance(tier, str) and tier:
                acc["tier"] = tier
        elif event == "criticality_override":
            value = record.get("to") or record.get("criticality")
            if isinstance(value, str) and value:
                acc["criticality"] = value
        elif event == "complexity_override":
            value = record.get("to") or record.get("tier")
            if isinstance(value, str) and value:
                acc["tier"] = value

    return acc


def _filter_field(obj: object, field: str) -> object:
    """Apply --field filter to the accumulated result.

    Mirrors the jq logic:
      if $field == "criticality" then (if has("criticality") then {criticality} else {} end)
      elif $field == "tier" then (if has("tier") then {tier} else {} end)
      else .
      end

    When obj is None (torn-line reduce-to-null), returns None regardless
    of field (null | has("criticality") is false in jq, yielding {}).
    """
    if field == "criticality":
        if isinstance(obj, dict) and "criticality" in obj:
            return {"criticality": obj["criticality"]}
        return {}
    elif field == "tier":
        if isinstance(obj, dict) and "tier" in obj:
            return {"tier": obj["tier"]}
        return {}
    # No field filter: return as-is.
    return obj


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point for cortex-lifecycle-state."""
    args = sys.argv[1:] if argv is None else list(argv)

    feature: Optional[str] = None
    field: str = ""
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--feature":
            i += 1
            feature = args[i] if i < len(args) else ""
        elif arg == "--field":
            i += 1
            field = args[i] if i < len(args) else ""
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

    events_path = Path("cortex") / "lifecycle" / feature / "events.log"

    if not events_path.is_file():
        sys.stdout.write("{}\n")
        sys.exit(0)

    result = _reduce_events(events_path)

    if field:
        result = _filter_field(result, field)

    sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
