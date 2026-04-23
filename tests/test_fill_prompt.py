"""Exercise the real fill_prompt() shell function from cortex_command/overnight/runner.sh.

The function is extracted and sourced in isolation so runner.sh's top-level
script initialization (arg parsing, state-JSON reads, realpath on STATE_PATH)
does not run. Per R7a, the shell function body itself is executed — not a
Python copy of the substitution logic.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REAL_REPO_ROOT = Path(__file__).resolve().parent.parent
RUNNER_SH = REAL_REPO_ROOT / "claude" / "overnight" / "runner.sh"
PROMPT_TEMPLATE = REAL_REPO_ROOT / "claude" / "overnight" / "prompts" / "orchestrator-round.md"


def _extract_fill_prompt(runner_path: Path) -> str:
    lines = runner_path.read_text().splitlines()
    start = end = None
    for i, line in enumerate(lines):
        if line.startswith("fill_prompt() {"):
            start = i
        elif start is not None and line == "}":
            end = i
            break
    assert start is not None and end is not None, "fill_prompt() function not found in runner.sh"
    return "\n".join(lines[start : end + 1])


def _run_fill_prompt() -> str:
    stub_session_dir = "/tmp/overnight-2026-04-21-stub"
    stub_env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "PLAN_PATH": f"{stub_session_dir}/overnight-plan.md",
        "STATE_PATH": f"{stub_session_dir}/overnight-state.json",
        "SESSION_DIR": stub_session_dir,
        "EVENTS_PATH": f"{stub_session_dir}/overnight-events.log",
        "TIER": "simple",
        "PROMPT_TEMPLATE": str(PROMPT_TEMPLATE),
        "TEMPLATE": str(PROMPT_TEMPLATE),
    }
    body = _extract_fill_prompt(RUNNER_SH)
    script = body + "\nfill_prompt 1\n"
    result = subprocess.run(
        ["bash", "-c", script],
        env=stub_env,
        cwd=str(REAL_REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_fill_prompt_substitutes_session_plan_path():
    """R7c: {session_plan_path} and {plan_path} are fully substituted (not present in output)."""
    out = _run_fill_prompt()
    assert "{session_plan_path}" not in out, (
        "{session_plan_path} token survived fill_prompt — runner.sh did not substitute the renamed key"
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
