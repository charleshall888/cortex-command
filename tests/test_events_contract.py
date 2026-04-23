"""Contract test: every log_event( call in orchestrator-round.md uses a registered event type.

Scans the orchestrator prompt for log_event( calls, extracts the first positional
argument (an event-type constant name), resolves it against the events module, and
asserts the resolved value is present in EVENT_TYPES.

This catches the drift class of bug where a new event constant is added to the prompt
but forgotten in events.py (which raises ValueError at runtime on the LLM side).
"""

from __future__ import annotations

import re
from pathlib import Path

from cortex_command.overnight import events
from cortex_command.overnight.events import EVENT_TYPES

REPO_ROOT = Path(__file__).parent.parent
PROMPT_PATH = REPO_ROOT / "cortex_command" / "overnight" / "prompts" / "orchestrator-round.md"

# Matches log_event( followed by the first argument (constant name or string literal)
_CALL_RE = re.compile(r'log_event\(\s*([A-Z_]+|"[^"]+"|\'[^\']+\')')


def test_orchestrator_prompt_log_event_calls_registered():
    """All log_event( calls in orchestrator-round.md must reference registered event types."""
    text = PROMPT_PATH.read_text(encoding="utf-8")

    found: list[str] = []
    for match in _CALL_RE.finditer(text):
        found.append(match.group(1))

    assert found, "Expected at least one log_event( call in orchestrator-round.md"

    unregistered: list[str] = []
    for arg in found:
        if arg.startswith(('"', "'")):
            # String literal — compare directly
            event_type = arg.strip("\"'")
        else:
            # Constant name — resolve via the events module
            event_type = getattr(events, arg, None)
            if event_type is None:
                unregistered.append(f"{arg!r} (constant not found in events module)")
                continue

        if event_type not in EVENT_TYPES:
            unregistered.append(f"{arg!r} -> {event_type!r} (not in EVENT_TYPES)")

    assert not unregistered, (
        "log_event( calls in orchestrator-round.md reference unregistered event types:\n"
        + "\n".join(f"  {entry}" for entry in unregistered)
    )
