"""Regression tests for dead-code cleanup: judgment.md and JUDGMENT_FAILED removal.

Ensures three cleanup deliverables remain enforced:
  (1) claude/overnight/prompts/judgment.md is deleted
  (2) JUDGMENT_FAILED is no longer an attribute of the events module
  (3) log_event("judgment_failed", ...) raises ValueError

Also includes a sync test ensuring every string-literal log_event call
in the overnight codebase uses a registered EVENT_TYPES value.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cortex_command.overnight import events
from cortex_command.overnight.events import EVENT_TYPES, log_event

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


def test_all_log_event_calls_registered():
    """Every string-literal log_event call in overnight files must use a registered type."""
    overnight_dir = REPO_ROOT / "claude" / "overnight"

    # Patterns for extracting string-literal event type arguments
    sh_pattern = re.compile(r'log_event "([^"]+)"')
    py_log_event_pattern = re.compile(r'log_event\("([^"]+)"')
    py_overnight_pattern = re.compile(r'overnight_log_event\("([^"]+)"')

    found_literals: list[tuple[str, str]] = []  # (file_path, event_type)

    for path in sorted(overnight_dir.rglob("*.sh")):
        text = path.read_text(encoding="utf-8")
        for match in sh_pattern.finditer(text):
            found_literals.append((str(path.relative_to(REPO_ROOT)), match.group(1)))

    for path in sorted(overnight_dir.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in py_log_event_pattern.finditer(text):
            found_literals.append((str(path.relative_to(REPO_ROOT)), match.group(1)))
        for match in py_overnight_pattern.finditer(text):
            found_literals.append((str(path.relative_to(REPO_ROOT)), match.group(1)))

    # Sanity: we should find at least one literal (runner.sh has many)
    assert found_literals, "Expected to find log_event string literals in overnight files"

    unregistered = [
        (f, evt) for f, evt in found_literals if evt not in EVENT_TYPES
    ]
    assert not unregistered, (
        "Found log_event calls with unregistered event types:\n"
        + "\n".join(f"  {f}: {evt!r}" for f, evt in unregistered)
    )
