"""cortex-lifecycle-init-ensure — skill-helper: run ``cortex init --ensure`` in-process.

Structural-separation form of the lifecycle wiring per CLAUDE.md's principle
"structural separation over prose-only enforcement for sequential gates".  The
skill calls this console-script rather than composing a Bash invocation, so the
in-process delegate to :func:`cortex_command.init.handler.main` is encoded in
Python control flow, not in prose the model must re-interpret.

Usage::

    cortex-lifecycle-init-ensure          # normal invocation
    python3 -m cortex_command.lifecycle.init_ensure

Exit codes mirror ``cortex init --ensure``:
    0 -- success / no-op (or CORTEX_AUTO_ENSURE=0 opt-out).
    2 -- user-correctable gate failure (uninitialized repo, foreign content,
         marker corruption, install lock).
    1 -- unexpected runtime failure.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for ``cortex-lifecycle-init-ensure``.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]`` when ``None``).

    Returns:
        Exit code: 0 on success/no-op, 2 on user-correctable gate failure,
        1 on unexpected runtime failure.
    """
    # Parse a minimal --help so the console-script isn't entirely opaque.
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-init-ensure",
        description=(
            "Skill-helper: invoke ``cortex init --ensure`` in-process before "
            "lifecycle phase dispatch.  Honors CORTEX_AUTO_ENSURE=0."
        ),
        add_help=True,
    )
    # parse_known_args so unrecognized flags surface a clean error rather than
    # crashing into the handler.
    _ns, unknown = parser.parse_known_args(argv)
    if unknown:
        parser.error(f"unrecognized arguments: {' '.join(unknown)}")

    # Delegate to the in-process handler.  Import style is intentionally
    # ``from cortex_command.init import handler`` (module reference, not the
    # function directly) so Task 9's tests can monkeypatch handler.main without
    # reaching through an already-bound local name.
    from cortex_command.init import handler  # noqa: PLC0415

    ns = argparse.Namespace(
        ensure=True,
        update=False,
        force=False,
        unregister=False,
        path=None,
    )
    return handler.main(ns)


if __name__ == "__main__":
    sys.exit(main())
