"""Outcome routing layer extracted from batch_runner.py.

This module contains the outcome routing layer extracted from
batch_runner.py. This module must not import from
`claude.overnight.batch_runner` or `claude.overnight.orchestrator`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claude.overnight.batch_runner import BatchResult, BatchConfig

from claude.overnight.constants import CIRCUIT_BREAKER_THRESHOLD
from claude.overnight.types import FeatureResult


@dataclass
class OutcomeContext:
    batch_result: BatchResult
    lock: asyncio.Lock
    consecutive_pauses_ref: list[int]
    recovery_attempts_map: dict[str, int]
    worktree_paths: dict[str, Path]
    worktree_branches: dict[str, str]
    repo_path_map: dict[str, Path | None]
    integration_worktrees: dict[str, Path]
    integration_branches: dict[str, str]
    session_id: str
    backlog_ids: dict[str, int | None]
    feature_names: list[str]
    config: BatchConfig
