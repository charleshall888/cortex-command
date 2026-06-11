"""L1 surface ratchet — guard against frontmatter description regrowth.

Baselines sourced from ``cortex/lifecycle/harness-token-efficiency-trim/evidence.json``
→ ``l1_surface_baseline`` (snapshot taken after the harness-token-efficiency-trim trims
landed).  Hardcoded here so the test has zero dependency on lifecycle artifacts at
runtime.

Ratchet direction: equal-or-lower passes; any skill that EXCEEDS its baseline fails.
When this test fails, point the investigator at the deferred L1 cap-policy backlog
ticket (cortex/backlog/295-automate-dependency-bump-tooling-and-broaden-transitive-
drift-protection-deferred-from-291.md) and reduce the frontmatter until it is at or
below the baseline.

Spec: cortex/lifecycle/harness-token-efficiency-trim/spec.md R5, R6f.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
UTILITY = REPO_ROOT / "bin" / "cortex-measure-l1-surface"

# Baselines from evidence.json → l1_surface_baseline (harness-token-efficiency-trim).
# Do NOT raise these values without a documented justification and lifecycle artifact.
# When any skill exceeds its baseline, investigate and reduce rather than bumping here.
# Deferred cap-policy ticket: cortex/backlog/295-automate-dependency-bump-tooling-and-
# broaden-transitive-drift-protection-deferred-from-291.md
_BASELINES: dict[str, int] = {
    "backlog": 319,
    "backlog-author": 427,
    "commit": 208,
    "critical-review": 795,
    "dev": 285,
    "diagnose": 294,
    "discovery": 932,
    "interview": 758,
    "lifecycle": 890,
    "morning-review": 320,
    "overnight": 314,
    "pr": 237,
    "refine": 644,
    "requirements": 231,
    "requirements-gather": 498,
    "requirements-write": 685,
    "research": 502,
    "total": 8339,
}


def _utility_rows() -> dict[str, int]:
    """Run the utility and parse stdout into ``{skill_name: bytes}``."""
    proc = subprocess.run(
        [str(UTILITY)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    out: dict[str, int] = {}
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        name, count = parts
        out[name] = int(count)
    return out


# Parametrize one case per skill plus the total row.
_RATCHET_CASES = sorted(_BASELINES.keys())


@pytest.fixture(scope="module")
def utility_rows() -> dict[str, int]:
    """Run the utility once per module and share the result across all cases."""
    return _utility_rows()


@pytest.mark.parametrize("name", _RATCHET_CASES)
def test_l1_surface_within_baseline(name: str, utility_rows: dict[str, int]) -> None:
    """Each skill's L1 surface must be at or below its recorded baseline.

    Failure means frontmatter has grown above the ratchet.  Reduce the
    description/when_to_use text rather than raising the baseline here.
    See the deferred cap-policy backlog ticket for the planned automated
    enforcement path.
    """
    assert name in utility_rows, (
        f"utility output missing row for {name!r}; known rows: {sorted(utility_rows)}"
    )
    actual = utility_rows[name]
    baseline = _BASELINES[name]
    assert actual <= baseline, (
        f"L1 surface ratchet breach for {name!r}: "
        f"actual={actual} bytes > baseline={baseline} bytes "
        f"(delta=+{actual - baseline}). "
        "Reduce frontmatter description/when_to_use rather than raising the baseline. "
        "Cap-policy backlog: cortex/backlog/295-automate-dependency-bump-tooling-and-"
        "broaden-transitive-drift-protection-deferred-from-291.md"
    )
