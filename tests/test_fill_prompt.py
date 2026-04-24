"""Exercise the fill_prompt() function from cortex_command.overnight.fill_prompt.

Per R7a, the Python port of fill_prompt() performs the six single-brace token
substitutions against the orchestrator-round.md template. These tests call the
function directly (no bash source-extract) to verify the substitution contract.
"""

from __future__ import annotations

import re
from pathlib import Path

from cortex_command.overnight.fill_prompt import fill_prompt


STUB_SESSION_DIR = Path("/tmp/overnight-2026-04-21-stub")
STUB_PLAN_PATH = STUB_SESSION_DIR / "overnight-plan.md"
STUB_STATE_PATH = STUB_SESSION_DIR / "overnight-state.json"
STUB_EVENTS_PATH = STUB_SESSION_DIR / "overnight-events.log"


def _run_fill_prompt() -> str:
    return fill_prompt(
        round_number=1,
        state_path=STUB_STATE_PATH,
        plan_path=STUB_PLAN_PATH,
        events_path=STUB_EVENTS_PATH,
        session_dir=STUB_SESSION_DIR,
        tier="simple",
    )


def test_fill_prompt_substitutes_session_plan_path():
    """R7c: {session_plan_path} and {plan_path} are fully substituted (not present in output)."""
    out = _run_fill_prompt()
    assert "{session_plan_path}" not in out, (
        "{session_plan_path} token survived fill_prompt — fill_prompt did not substitute the renamed key"
    )
    assert "{plan_path}" not in out, (
        "{plan_path} token survived fill_prompt — stale single-brace token remains somewhere in the template"
    )


def test_fill_prompt_substitutes_plan_path_value():
    """R7d: the stub PLAN_PATH value appears at least 3 times (three session-level occurrences)."""
    out = _run_fill_prompt()
    plan_path_value = "/tmp/overnight-2026-04-21-stub/overnight-plan.md"
    count = out.count(plan_path_value)
    assert count >= 3, (
        f"expected stub PLAN_PATH value to appear >=3 times, got {count}"
    )


def test_fill_prompt_preserves_per_feature_double_brace():
    """R7e: {{feature_slug}} appears at least once (double-brace per-feature tokens survive)."""
    out = _run_fill_prompt()
    assert "{{feature_slug}}" in out, (
        "{{feature_slug}} double-brace token not found — per-feature token shape may have regressed"
    )


def test_fill_prompt_contains_substitution_contract():
    """R7f: <substitution_contract> block is present in the rendered prompt."""
    out = _run_fill_prompt()
    assert "<substitution_contract>" in out, (
        "<substitution_contract> block not found in rendered prompt — R6 instruction block missing"
    )


def test_fill_prompt_no_single_brace_per_feature_tokens():
    """R7h: no single-brace per-feature tokens leak through (catches partial rename)."""
    out = _run_fill_prompt()
    assert "{slug}" not in out, (
        "{slug} single-brace token found in output — a per-feature rename site was missed"
    )
    assert "{spec_path}" not in out, (
        "{spec_path} single-brace token found in output — per-feature spec_path rename incomplete"
    )
    assert re.search(r'"\{feature\}"', out) is None, (
        '"{feature}" (quoted single-brace) found in output — line 261 dispatch-block rename incomplete'
    )
