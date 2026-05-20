"""Stub for cortex-resolve-backlog-item (promoted in a later task).

This module exists so ``pyproject.toml``'s ``[project.scripts]`` entry can
be pre-allocated without breaking wheel installation. ``main()`` exits
``70`` (per the installation-integrity-layer-bash-to-entry plan) rather
than raising, so any intermediate commit remains installable and the
entry point is discoverable by ``importlib.metadata.entry_points``.
"""

from __future__ import annotations

import sys
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    """Pre-allocation stub — real port lands in a later task."""
    sys.stderr.write(
        "cortex-resolve-backlog-item: stub entry point; real port lands in "
        "a later task of installation-integrity-layer-bash-to-entry.\n"
    )
    sys.exit(70)
