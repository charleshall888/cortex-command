"""Plugin-mirror byte-parity test (defense-in-depth for AS-3).

The pre-commit hook (`.githooks/pre-commit`) regenerates plugin mirrors from
canonical sources via rsync on each canonical-touch commit. This test is the
INDEPENDENT CI-layer catch: if a developer skipped `just setup-githooks` and
the pre-commit hook never ran, drift between a canonical file and its plugin
mirror is still caught at test time.

Scope: the three canonical lifecycle reference files in scope for the
vertical-planning-adoption-as-replacement ticket. Each canonical file at
``skills/lifecycle/references/<name>.md`` is byte-compared against its
mirror at ``plugins/cortex-core/skills/lifecycle/references/<name>.md``.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL_DIR = REPO_ROOT / "skills" / "lifecycle" / "references"
MIRROR_DIR = (
    REPO_ROOT / "plugins" / "cortex-core" / "skills" / "lifecycle" / "references"
)

MIRRORED_FILENAMES = (
    "plan.md",
    "specify.md",
    "orchestrator-review.md",
)


@pytest.mark.parametrize("filename", MIRRORED_FILENAMES)
def test_plugin_mirror_matches_canonical(filename: str) -> None:
    """Mirror bytes must equal canonical bytes for ``filename``."""
    canonical_path = CANONICAL_DIR / filename
    mirror_path = MIRROR_DIR / filename

    assert canonical_path.is_file(), (
        f"canonical file missing: {canonical_path}"
    )
    assert mirror_path.is_file(), (
        f"plugin mirror missing: {mirror_path} "
        f"(expected mirror of {canonical_path})"
    )

    canonical_bytes = canonical_path.read_bytes()
    mirror_bytes = mirror_path.read_bytes()

    assert canonical_bytes == mirror_bytes, (
        f"plugin mirror drift detected: "
        f"{mirror_path} does not match canonical {canonical_path}. "
        f"Run `just setup-githooks` to enable the pre-commit drift hook, "
        f"or manually re-sync the mirror from the canonical source."
    )
