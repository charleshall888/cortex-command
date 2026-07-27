"""Static wiring test for the refine seed (``lifecycle_start``) call chain.

The refine skill must cause a seed ``lifecycle_start`` row to land before any
other event in events.log. That seed moved from a standalone
``cortex-refine emit-lifecycle-start`` invocation in the skill body into the
composite ``cortex-refine start`` verb, which resolves the item, reads the
backend, and seeds in one round-trip.

The invariant is unchanged, so this test guards both ends of the new chain:
the skill still invokes the entry verb, and that verb still performs the seed.
Pinning only the skill string would let a refactor gut ``_cmd_start``'s seed
call without failing anything.
"""

from __future__ import annotations

import inspect
import subprocess
from pathlib import Path

from cortex_command import refine as refine_mod


def test_refine_skill_wires_start_verb() -> None:
    """skills/refine/SKILL.md must invoke the `cortex-refine start` entry verb."""
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
    assert "cortex-refine start" in content, (
        "refine SKILL.md no longer invokes `cortex-refine start`; "
        "the session-start sentinel will not fire"
    )


def test_start_verb_seeds_lifecycle_start() -> None:
    """`cortex-refine start` must still emit the seed row itself."""
    source = inspect.getsource(refine_mod._cmd_start)
    assert "_cmd_emit_lifecycle_start" in source, (
        "cortex-refine start no longer calls _cmd_emit_lifecycle_start; the "
        "seed lifecycle_start row would never be written"
    )
