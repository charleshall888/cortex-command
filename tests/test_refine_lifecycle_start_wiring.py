"""Static wiring test for the refine SKILL.md emit-lifecycle-start call site.

The refine skill is responsible for invoking `cortex-refine emit-lifecycle-start`
so that the session-start sentinel fires before any other event lands in
events.log. If a future refactor silently removes that invocation from
skills/refine/SKILL.md, the sentinel will never be emitted and the lifecycle
will start without a seed `lifecycle_start` row.

This test asserts the literal helper invocation string is still present in
the skill body, guarding against that regression.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def test_refine_skill_wires_emit_lifecycle_start() -> None:
    """skills/refine/SKILL.md must invoke `cortex-refine emit-lifecycle-start`."""
    repo_root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    skill_md = repo_root / "skills" / "refine" / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")
    assert "cortex-refine emit-lifecycle-start" in content, (
        "refine SKILL.md no longer invokes cortex-refine emit-lifecycle-start; "
        "the session-start sentinel will not fire"
    )
