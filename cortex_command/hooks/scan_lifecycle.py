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
import sys


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

    # Parsed for use by subsequent tasks; intentionally unused in the skeleton.
    _session_id = payload.get("session_id")
    _cwd = payload.get("cwd")

    return 0


if __name__ == "__main__":  # pragma: no cover - module CLI entry shim
    sys.exit(main(sys.argv[1:]))
