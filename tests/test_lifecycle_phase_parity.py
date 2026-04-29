#!/usr/bin/env python3
"""Three-layer parity tests for lifecycle phase detection (R12).

Layer 12a — Hook glue unit test
    Asserts byte-equality of the bash glue function `encode_phase`
    (defined in hooks/cortex-scan-lifecycle.sh) against the R3 normative
    wire-format encoding for a fixture matrix of (phase, checked, total,
    cycle) tuples.

Layers 12b (statusline vs canonical) and 12c (hook end-to-end) are
delivered by sibling tasks; this file is the home for those test
classes/functions when they land.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = REPO_ROOT / "hooks" / "cortex-scan-lifecycle.sh"


# Fixture matrix: (phase, checked, total, cycle, expected_emit)
# Verbatim from spec R12a (≥10 cases). Each tuple maps the canonical
# detector's dict shape (R1) to the glue function's wire-format string (R3).
GLUE_FIXTURES: list[tuple[str, int, int, int, str]] = [
    ("research", 0, 0, 1, "research"),
    ("implement", 0, 0, 1, "implement:0/0"),
    ("implement", 2, 5, 1, "implement:2/5"),
    ("implement-rework", 0, 0, 1, "implement-rework:1"),
    ("implement-rework", 3, 5, 2, "implement-rework:2"),
    ("review", 5, 5, 1, "review"),
    ("complete", 5, 5, 1, "complete"),
    ("escalated", 0, 0, 1, "escalated"),
    ("plan", 0, 0, 1, "plan"),
    ("specify", 0, 0, 1, "specify"),
]


def _extract_encode_phase_function() -> str:
    """Extract just the `encode_phase` bash function definition from the hook.

    Sourcing the entire hook is impractical: the hook reads stdin at the top
    and has executable side effects. Instead we slice out the function block
    by regex and execute it in isolation.
    """
    src = HOOK_PATH.read_text()
    match = re.search(
        r"^encode_phase\(\)\s*\{.*?^\}\s*$",
        src,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise RuntimeError(
            f"Could not locate encode_phase() in {HOOK_PATH}. "
            "Hook structure may have changed; update test extractor."
        )
    return match.group(0)


def _invoke_encode_phase(phase: str, checked: int, total: int, cycle: int) -> str:
    """Source the extracted glue fragment and call encode_phase, capturing stdout."""
    fragment = _extract_encode_phase_function()
    script = f"""
set -euo pipefail
{fragment}
encode_phase {phase!r} {int(checked)} {int(total)} {int(cycle)}
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )
    # Strip the trailing newline that `echo` always adds; preserve any
    # internal characters (the wire format never contains newlines).
    return proc.stdout.rstrip("\n")


@pytest.mark.parametrize(
    "phase,checked,total,cycle,expected",
    GLUE_FIXTURES,
    ids=[f"{p}-{c}/{t}-cycle{cy}" for p, c, t, cy, _ in GLUE_FIXTURES],
)
def test_hook_glue(
    phase: str,
    checked: int,
    total: int,
    cycle: int,
    expected: str,
) -> None:
    """R12a: bash `encode_phase` glue produces byte-equal R3 wire-format output."""
    actual = _invoke_encode_phase(phase, checked, total, cycle)
    assert actual == expected, (
        f"encode_phase({phase!r}, {checked}, {total}, {cycle}) "
        f"emitted {actual!r}, expected {expected!r}"
    )
