"""Shared backlog utilities for cortex-command.

This package consolidates readiness logic that was previously duplicated
across ``cortex_command.overnight.backlog.filter_ready`` and
``backlog/generate_index.py``.

Re-exports the public helpers from :mod:`cortex_command.backlog.readiness`
so callers can write::

    from cortex_command.backlog import is_item_ready, partition_ready
"""

from __future__ import annotations

from cortex_command.backlog.readiness import (  # noqa: F401
    ReadinessPartition,
    is_item_ready,
    partition_ready,
)

__all__ = ["ReadinessPartition", "is_item_ready", "partition_ready"]
