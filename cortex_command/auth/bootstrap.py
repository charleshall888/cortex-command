"""Stub for ``cortex auth bootstrap``.

The full implementation (see Phase 1 of
``cortex/lifecycle/restore-subscription-auth-for-autonomous-worktree/spec.md``)
will wrap ``claude setup-token``, atomically write the minted token to
``~/.claude/personal-oauth-token`` under an ``fcntl`` lock, and surface
shadowing diagnostics. Until those subsequent tasks land, this scaffolded
entry point fails loud so callers can confirm the subparser is wired
without triggering partial behavior.
"""

from __future__ import annotations

import argparse
import sys


def run(_args: argparse.Namespace) -> int:
    """Entry point for ``cortex auth bootstrap`` (scaffolding stub)."""

    print("error: not implemented", file=sys.stderr)
    return 2
