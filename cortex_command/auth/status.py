"""Stub for ``cortex auth status``.

The full implementation (see Phase 1 of
``cortex/lifecycle/restore-subscription-auth-for-autonomous-worktree/spec.md``)
will invoke :func:`cortex_command.overnight.auth.ensure_sdk_auth` and
report the resolved auth vector — including shadowed-vector diagnostics
when a higher-precedence vector is masking a configured lower-precedence
one. Until that lands, this scaffolded entry point fails loud so the
subparser wiring can be verified without producing misleading output.
"""

from __future__ import annotations

import argparse
import sys


def run(_args: argparse.Namespace) -> int:
    """Entry point for ``cortex auth status`` (scaffolding stub)."""

    print("error: not implemented", file=sys.stderr)
    return 2
