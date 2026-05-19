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
