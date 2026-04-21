"""Skill-side 3-tier fallback reader for daytime-result.json.

Implements the classification logic described in spec R6/R7 as pure-Python
helpers with a testable interface. The skill's Bash §1b vii may invoke this
module via:

    python3 -m claude.overnight.daytime_result_reader --feature {slug}

which prints a JSON dict to stdout.

Tier 1 — daytime-result.json:
    Parse JSON; check schema_version == 1 (hard equality per R7); compare
    dispatch_id against daytime-dispatch.json for freshness. On match:
    classify from outcome + terminated_via + error + pr_url + deferred_files.
    On any failure: fall to Tier 2.

Tier 2 — discrimination context from daytime-state.json:
    Does NOT classify outcome. Reads top-level ``phase`` field to determine
    which Tier-3 message to surface:
        phase == "complete" (or other terminal) → terminal
        phase == "executing" or non-terminal     → non-terminal
        file absent                              → absent

Tier 3 — surface outcome: "unknown" with discriminated message:
    Three verbatim messages (spec R6). Appends last 20 lines of daytime.log.

Return dict schema:
    {
        "outcome": str,
        "terminated_via": Optional[str],
        "message": str,
        "source_tier": int,
        "pr_url": Optional[str],
        "deferred_files": list[str],
        "error": Optional[str],
        "log_tail": Optional[str],
    }
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Verbatim Tier-3 discriminated messages — spec R6.
# These strings MUST match spec R6 exactly; tests assert them verbatim.
# ---------------------------------------------------------------------------

_MSG_TERMINAL = (
    "Subprocess likely completed but its result file is missing or invalid. "
    "Check `lifecycle/{slug}/daytime.log` for the final outcome."
)
_MSG_NON_TERMINAL = (
    "Subprocess did not complete (still running, killed, or crashed "
    "mid-execution). Check `lifecycle/{slug}/daytime.log`."
)
_MSG_ABSENT = (
    "Subprocess never started (pre-flight failure). "
    "Check `lifecycle/{slug}/daytime.log`."
)

# Terminal phase values — any phase in this set → tier-2 says "terminal".
_TERMINAL_PHASES = {"complete", "done", "finished"}

# Default lifecycle root (repo root).
_DEFAULT_LIFECYCLE_ROOT = Path("lifecycle")


def _lifecycle_root(lifecycle_root: Optional[Path]) -> Path:
    return lifecycle_root if lifecycle_root is not None else _DEFAULT_LIFECYCLE_ROOT


def _read_log_tail(slug: str, lifecycle_root: Optional[Path], n: int = 20) -> Optional[str]:
    """Return the last ``n`` lines of daytime.log, or None if unreadable."""
    log_path = _lifecycle_root(lifecycle_root) / slug / "daytime.log"
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:]) if lines else ""
    except (FileNotFoundError, OSError):
        return None


def _tier3_message(slug: str, discrimination: str) -> str:
    """Return the verbatim tier-3 message for the given discrimination context."""
    if discrimination == "terminal":
        return _MSG_TERMINAL.format(slug=slug)
    elif discrimination == "non_terminal":
        return _MSG_NON_TERMINAL.format(slug=slug)
    else:
        return _MSG_ABSENT.format(slug=slug)


def _tier2_discrimination(slug: str, lifecycle_root: Optional[Path]) -> str:
    """Determine tier-2 discrimination context from daytime-state.json.

    Returns one of: "terminal", "non_terminal", "absent".
    """
    state_path = _lifecycle_root(lifecycle_root) / slug / "daytime-state.json"
    try:
        text = state_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return "absent"

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return "absent"

    phase = data.get("phase", "")
    if phase in _TERMINAL_PHASES:
        return "terminal"
    elif phase:
        return "non_terminal"
    else:
        return "absent"


def classify_result(
    feature_slug: str,
    lifecycle_root: Optional[Path] = None,
) -> dict:
    """Classify the outcome of a daytime dispatch via 3-tier fallback.

    Args:
        feature_slug: The feature slug (subdirectory name under lifecycle/).
        lifecycle_root: Path to the lifecycle/ directory. Defaults to
            Path("lifecycle") relative to cwd — i.e., the repo root must
            be the cwd. Pass an explicit path in tests.

    Returns:
        A JSON-serializable dict with keys:
            outcome, terminated_via, message, source_tier, pr_url,
            deferred_files, error, log_tail.
    """
    root = _lifecycle_root(lifecycle_root)
    result_path = root / feature_slug / "daytime-result.json"
    dispatch_path = root / feature_slug / "daytime-dispatch.json"

    # ------------------------------------------------------------------
    # Tier 1 — attempt to read and validate daytime-result.json.
    # ------------------------------------------------------------------
    tier1_reason: Optional[str] = None

    try:
        result_text = result_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        tier1_reason = "result file absent"
        result_text = None

    if result_text is not None:
        try:
            result_data = json.loads(result_text)
        except json.JSONDecodeError:
            tier1_reason = "result file malformed JSON"
            result_data = None
    else:
        result_data = None

    if result_data is not None:
        # R7: hard schema_version == 1 equality check.
        if result_data.get("schema_version") != 1:
            tier1_reason = f"schema_version != 1 (got {result_data.get('schema_version')!r})"
            result_data = None

    if result_data is not None:
        # Freshness check: compare dispatch_id against daytime-dispatch.json.
        result_dispatch_id = result_data.get("dispatch_id")

        try:
            dispatch_text = dispatch_path.read_text(encoding="utf-8")
            dispatch_data = json.loads(dispatch_text)
            expected_dispatch_id = dispatch_data.get("dispatch_id")
        except (FileNotFoundError, OSError):
            tier1_reason = "daytime-dispatch.json absent — cannot validate freshness"
            result_data = None
            expected_dispatch_id = None
        except json.JSONDecodeError:
            tier1_reason = "daytime-dispatch.json malformed JSON"
            result_data = None
            expected_dispatch_id = None
        else:
            if result_dispatch_id != expected_dispatch_id:
                tier1_reason = (
                    f"dispatch_id mismatch: result has {result_dispatch_id!r}, "
                    f"dispatch file has {expected_dispatch_id!r}"
                )
                result_data = None

    if result_data is not None:
        # Tier 1 success — classify directly from the result file.
        return {
            "outcome": result_data.get("outcome", "unknown"),
            "terminated_via": result_data.get("terminated_via"),
            "message": f"Classified from daytime-result.json (tier 1).",
            "source_tier": 1,
            "pr_url": result_data.get("pr_url"),
            "deferred_files": result_data.get("deferred_files", []),
            "error": result_data.get("error"),
            "log_tail": None,
        }

    # ------------------------------------------------------------------
    # Tier 2 — discrimination context from daytime-state.json.
    # Tier 3 — surface outcome: "unknown" with discriminated message.
    # ------------------------------------------------------------------
    discrimination = _tier2_discrimination(feature_slug, lifecycle_root)
    message = _tier3_message(feature_slug, discrimination)
    log_tail = _read_log_tail(feature_slug, lifecycle_root)

    return {
        "outcome": "unknown",
        "terminated_via": None,
        "message": message,
        "source_tier": 3,
        "pr_url": None,
        "deferred_files": [],
        "error": tier1_reason,
        "log_tail": log_tail,
    }


# ---------------------------------------------------------------------------
# CLI entry point — enables skill invocation via:
#   python3 -m claude.overnight.daytime_result_reader --feature {slug}
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        prog="python3 -m claude.overnight.daytime_result_reader",
        description="Classify a daytime dispatch outcome via 3-tier fallback.",
    )
    parser.add_argument(
        "--feature",
        required=True,
        help="Feature slug (subdirectory under lifecycle/).",
    )
    parser.add_argument(
        "--lifecycle-root",
        default=None,
        help="Path to the lifecycle/ directory (default: lifecycle/ relative to cwd).",
    )
    args = parser.parse_args()

    lifecycle_root = Path(args.lifecycle_root) if args.lifecycle_root else None
    result = classify_result(args.feature, lifecycle_root=lifecycle_root)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["outcome"] == "merged" else 1)
