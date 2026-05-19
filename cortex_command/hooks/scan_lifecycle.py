"""SessionStart lifecycle scanner.

Implements the ``cortex hooks scan-lifecycle`` subcommand. Reads a Claude
Code SessionStart hook JSON payload on stdin (containing ``session_id``
and ``cwd``), then performs lifecycle-state detection, session-state
mutation, phase encoding, and ``hookSpecificOutput`` emission to inject
lifecycle context into the session.

This module is the Python port of ``hooks/cortex-scan-lifecycle.sh`` per
the resolve-cortex-interpreter-via-cli feature. The skeleton currently
parses input and exits 0 with no output; subsequent tasks fill in the
behavior progressively.

Imports of ``cortex_command.common`` and other intra-package modules are
kept inside the functions that need them (lazy-load discipline per the
overnight precedent at ``cortex_command/cli.py:48-66``), so ``--help``
and trivial dispatch paths do not pay the cost of the full package graph.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path


def _encode_phase(phase: str, checked: int, total: int, cycle: int) -> str:
    """Encode (phase, checked, total, cycle) into the wire-format string.

    Mirrors the bash ``encode_phase`` helper at
    ``hooks/cortex-scan-lifecycle.sh`` lines 184-200. Pure function: no
    I/O, no side effects. Downstream code consumes the encoded string to
    produce phase labels like ``"Phase: Implement (3/5 tasks done)"``.

    Encoding rules per R3:

    * ``phase == "implement"`` and ``total > 0``  -> ``"implement:<checked>/<total>"``
    * ``phase == "implement"`` and ``total == 0`` -> ``"implement:0/0"``
    * ``phase == "implement-rework"``             -> ``"implement-rework:<cycle>"``
    * any other phase                             -> bare ``phase`` string

    Parameters
    ----------
    phase:
        Lifecycle phase identifier (e.g. ``"research"``, ``"implement"``,
        ``"implement-rework"``).
    checked:
        Number of completed implementation tasks.
    total:
        Total implementation tasks.
    cycle:
        Implement-rework cycle index.

    Returns
    -------
    str
        The wire-format encoded phase string.
    """

    if phase == "implement":
        if total > 0:
            return f"implement:{checked}/{total}"
        return "implement:0/0"
    if phase == "implement-rework":
        return f"implement-rework:{cycle}"
    return phase


def _phase_label(encoded_phase: str) -> str:
    """Translate an encoded phase string into a human-readable label.

    Mirrors the bash ``phase_label`` helper at
    ``hooks/cortex-scan-lifecycle.sh`` lines 204-218. Pure function: no
    I/O, no side effects. Consumed by the ``additionalContext`` emitter
    to produce strings like ``"Phase: Implement (3/5 tasks done)"``.

    Mapping rules:

    * ``"research"``                  -> ``"Research"``
    * ``"specify"``                   -> ``"Specify"``
    * ``"plan"``                      -> ``"Plan"``
    * ``"implement:<x>/<y>"``         -> ``"Implement (<x>/<y> tasks done)"``
    * ``"implement-rework:<n>"``      -> ``"Implement — rework (review cycle <n>)"``
    * ``"review"``                    -> ``"Review"``
    * ``"escalated"``                 -> ``"Escalated (REJECTED — needs user direction)"``
    * ``"complete:awaiting-merge"``   -> ``"Complete (awaiting merge)"``
    * ``"complete"``                  -> ``"Complete"``
    * any other phase                 -> the encoded phase string verbatim

    Parameters
    ----------
    encoded_phase:
        Wire-format phase string as produced by :func:`_encode_phase`.

    Returns
    -------
    str
        The human-readable phase label.
    """

    if encoded_phase == "research":
        return "Research"
    if encoded_phase == "specify":
        return "Specify"
    if encoded_phase == "plan":
        return "Plan"
    if encoded_phase.startswith("implement:"):
        progress = encoded_phase[len("implement:") :]
        return f"Implement ({progress} tasks done)"
    if encoded_phase.startswith("implement-rework:"):
        cycle = encoded_phase[len("implement-rework:") :]
        return f"Implement — rework (review cycle {cycle})"
    if encoded_phase == "review":
        return "Review"
    if encoded_phase == "escalated":
        return "Escalated (REJECTED — needs user direction)"
    if encoded_phase == "complete:awaiting-merge":
        return "Complete (awaiting merge)"
    if encoded_phase == "complete":
        return "Complete"
    return encoded_phase


def _interrupted_hint(encoded_phase: str, active_feature: str) -> str:
    """Return a one-line interrupted-state hint, or empty when not applicable.

    Mirrors the bash interrupted-state hint emission at
    ``hooks/cortex-scan-lifecycle.sh`` lines 378-398. Pure function: no
    I/O, no side effects. The caller appends the returned hint to the
    ``additionalContext`` block on its own line; an empty string signals
    "no hint applicable" (no extra line should be emitted).

    Hint rules:

    * ``"implement:<checked>/<total>"`` with ``0 < checked < total``
      -> "Interrupted: implementation in progress ..." hint.
    * ``"implement:<checked>/<total>"`` with ``checked == 0`` or
      ``checked >= total`` -> empty (not-started or fully-done).
    * ``"implement-rework:<cycle>"`` -> "Interrupted: review cycle ..." hint.
    * ``"escalated"`` -> "Action needed: review returned REJECTED ..." hint.
    * any other phase -> empty.

    Parameters
    ----------
    encoded_phase:
        Wire-format phase string as produced by :func:`_encode_phase`.
    active_feature:
        Feature slug of the active lifecycle, used to render the
        ``/cortex-core:lifecycle <feature>`` resume command and the
        ``cortex/lifecycle/<feature>/review.md`` artifact path.

    Returns
    -------
    str
        The hint line (no trailing newline), or an empty string when no
        interrupted-state hint applies.
    """

    if encoded_phase.startswith("implement:"):
        progress = encoded_phase[len("implement:") :]
        if "/" not in progress:
            return ""
        checked_str, _, total_str = progress.partition("/")
        try:
            checked = int(checked_str)
            total = int(total_str)
        except ValueError:
            return ""
        if checked > 0 and checked < total:
            return (
                f"Interrupted: implementation in progress "
                f"({checked} of {total} tasks done). "
                f"Resume with /cortex-core:lifecycle {active_feature}."
            )
        return ""
    if encoded_phase.startswith("implement-rework:"):
        cycle = encoded_phase[len("implement-rework:") :]
        return (
            f"Interrupted: review cycle {cycle} returned CHANGES_REQUESTED. "
            f"Re-enter implementation to address feedback. "
            f"Resume with /cortex-core:lifecycle {active_feature}."
        )
    if encoded_phase == "escalated":
        return (
            f"Action needed: review returned REJECTED. See "
            f"cortex/lifecycle/{active_feature}/review.md for analysis."
        )
    return ""


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``cortex hooks scan-lifecycle``.

    Reads a SessionStart hook JSON payload on stdin, parses
    ``session_id`` and ``cwd``, and (in the completed implementation)
    emits a ``hookSpecificOutput`` block on stdout that injects
    lifecycle context for the active feature.

    Parameters
    ----------
    argv:
        Optional command-line argument list. Reserved for future use;
        the skeleton currently ignores it.

    Returns
    -------
    int
        Process exit code. ``0`` indicates the hook ran successfully
        (whether or not it emitted context); nonzero is reserved for
        genuine internal errors per the spec.
    """

    del argv  # Reserved for future use.

    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return 0

    if not raw.strip():
        return 0

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0

    if not isinstance(payload, dict):
        return 0

    session_id_raw = payload.get("session_id") or ""
    if not isinstance(session_id_raw, str):
        session_id_raw = ""
    session_id = session_id_raw

    cwd_raw = payload.get("cwd")
    if not isinstance(cwd_raw, str) or not cwd_raw:
        cwd_raw = os.getcwd()
    cwd = Path(cwd_raw)

    # --- Session identity injection (bash precedent lines 7-13) ---
    # Emit before the cwd/lifecycle early-exit so non-cortex sessions still
    # propagate LIFECYCLE_SESSION_ID for downstream hook invocations.
    if session_id:
        env_file = os.environ.get("CLAUDE_ENV_FILE")
        if env_file:
            export_line = (
                f"export LIFECYCLE_SESSION_ID={shlex.quote(session_id)}\n"
            )
            try:
                with open(env_file, "a", encoding="utf-8") as fh:
                    fh.write(export_line)
            except OSError:
                # Best-effort: parity with bash, which would surface a
                # redirection failure but not abort the hook chain.
                pass
        else:
            print(
                "[scan-lifecycle] CLAUDE_ENV_FILE not set; "
                "cannot inject LIFECYCLE_SESSION_ID",
                file=sys.stderr,
            )

    # --- cwd/lifecycle early-exit (bash precedent lines 26-29) ---
    # Non-cortex repos: silently exit 0 with no stdout. The wrapper at
    # hooks/cortex-scan-lifecycle.sh does its own pre-check; this is
    # defense-in-depth for the direct-invocation path.
    if not (cwd / "cortex" / "lifecycle").is_dir():
        return 0

    return 0


if __name__ == "__main__":  # pragma: no cover - module CLI entry shim
    sys.exit(main(sys.argv[1:]))
