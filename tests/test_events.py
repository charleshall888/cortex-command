"""Regression tests for dead-code cleanup: judgment.md and JUDGMENT_FAILED removal.

Ensures three cleanup deliverables remain enforced:
  (1) claude/overnight/prompts/judgment.md is deleted
  (2) JUDGMENT_FAILED is no longer an attribute of the events module
  (3) log_event("judgment_failed", ...) raises ValueError
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude.overnight import events
from claude.overnight.events import log_event

REPO_ROOT = Path(__file__).parent.parent


def test_judgment_md_deleted():
    """judgment.md must not exist in the repository."""
    assert not (REPO_ROOT / "claude/overnight/prompts/judgment.md").exists()


def test_judgment_failed_constant_removed():
    """JUDGMENT_FAILED must not be an attribute of the events module."""
    assert not hasattr(events, "JUDGMENT_FAILED")


def test_judgment_failed_raises_value_error(tmp_path):
    """log_event must reject 'judgment_failed' as an unknown event type."""
    with pytest.raises(ValueError, match="Unknown event type"):
        log_event("judgment_failed", round=1, log_path=tmp_path / "test-events.log")
