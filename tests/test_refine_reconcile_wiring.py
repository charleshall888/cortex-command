"""Static wiring test for the refine SKILL.md reconcile-clarify call site.

Standalone `/cortex-core:refine` seeds events.log with a `lifecycle_start`
row *before* Clarify runs, so the seed reflects the backlog's pre-Clarify
tier/criticality. The refine skill must invoke `cortex-refine reconcile-clarify`
at Spec-phase entry — *before* delegating to specify.md — so the §3a/§3b
tier/criticality reads (which live inside the delegated specify.md) observe
the Clarify-assessed values rather than the stale seed.

This test asserts both:
  1. The literal `cortex-refine reconcile-clarify` invocation is present.
  2. It is positioned *before* the §5 `specify.md` delegation line, which
     structurally enforces the ordering guarantee (reconcile precedes §3a,
     the earliest tier/criticality read) rather than relying on prose alone.

Note: `specify.md` is also mentioned earlier in the Research §2a bypass note,
so we anchor on the §5 delegation phrase (`specify.md` and follow it`), not
the bare first occurrence of `specify.md`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# The §5 delegation line — unique to the Spec-phase `Read ... specify.md and
# follow it (its full protocol)` delegation, distinct from the earlier
# Research-bypass mention of specify.md.
_DELEGATION_ANCHOR = "specify.md` and follow it"


def _skill_md() -> str:
    repo_root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    return (repo_root / "skills" / "refine" / "SKILL.md").read_text(encoding="utf-8")


def test_refine_skill_wires_reconcile_clarify() -> None:
    """skills/refine/SKILL.md must invoke `cortex-refine reconcile-clarify`."""
    content = _skill_md()
    assert "cortex-refine reconcile-clarify" in content, (
        "refine SKILL.md no longer invokes cortex-refine reconcile-clarify; "
        "standalone /refine will skip the §3b critical-review gate for "
        "Clarify-assessed complex/high features"
    )


def test_reconcile_clarify_precedes_specify_delegation() -> None:
    """reconcile-clarify must appear before the §5 specify.md delegation.

    The §3a/§3b tier/criticality reads live inside the delegated specify.md,
    so reconcile must run first. Anchoring on the delegation phrase (not the
    bare first `specify.md`) binds the requirement to the §5 delegation that
    triggers those reads.
    """
    content = _skill_md()
    assert _DELEGATION_ANCHOR in content, (
        "could not find the §5 specify.md delegation line; anchor may have "
        "drifted"
    )
    assert content.index("cortex-refine reconcile-clarify") < content.index(
        _DELEGATION_ANCHOR
    ), (
        "cortex-refine reconcile-clarify must be positioned before the §5 "
        "specify.md delegation so it precedes the §3a/§3b tier/criticality reads"
    )
