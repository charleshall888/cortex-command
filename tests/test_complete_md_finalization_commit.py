"""Scoped structural guard test for the finalization-commit-step region.

Slices the ``<!-- finalization-commit-step -->`` …
``<!-- /finalization-commit-step -->`` region out of the canonical
``skills/lifecycle/references/complete.md`` and asserts:

Positive tokens (all must be present in the region):
- ``cortex-read-commit-artifacts`` — binstub invocation
- ``/cortex-core:commit`` — commit skill invocation
- ``git diff --cached --quiet`` — stage-first idempotent guard
- Enumerated lifecycle-path staging (R5 requirement)
- ``cortex/backlog/`` — backlog directory-scoped staging
- A halt-on-failure clause for non-zero commit exit
- A ``main`` / ``master`` non-default-branch advisory (R13)

Negative tokens (must NOT appear in the region):
- ``git push`` — pushing is not part of the finalization commit step
- ``gh pr create`` — PR creation is not part of the finalization commit step
- ``git add cortex/lifecycle/`` — R5-forbidden directory-glob staging pattern
  (the region must use enumerated filenames, not a directory-scoped add
  on the lifecycle dir; a bare presence check would miss a glob-plus-prose-
  mention bypass)

Scoping to the anchored region is required because ``git push`` and
``gh pr create`` may legitimately appear elsewhere in complete.md (e.g.
Steps 3–5), and a whole-file check would produce false negatives.
"""

from __future__ import annotations

import pathlib


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1]


def _extract_region(text: str) -> str:
    """Return the text between the finalization-commit-step anchor markers.

    Raises AssertionError if either marker is missing, ensuring a missing
    anchor fails loudly rather than vacuously passing.
    """
    open_marker = "<!-- finalization-commit-step -->"
    close_marker = "<!-- /finalization-commit-step -->"

    start = text.find(open_marker)
    assert start != -1, (
        f"Opening anchor '{open_marker}' not found in complete.md — "
        "the finalization-commit-step region must be present"
    )

    end = text.find(close_marker, start)
    assert end != -1, (
        f"Closing anchor '{close_marker}' not found in complete.md after "
        "the opening anchor — the region must be properly closed"
    )

    region = text[start : end + len(close_marker)]
    assert region.strip(), (
        "The finalization-commit-step region is empty — expected substantive content"
    )
    return region


def test_finalization_commit_region_positive_tokens() -> None:
    """All required tokens must be present within the anchored region."""
    repo_root = _repo_root()
    complete_md = repo_root / "skills" / "lifecycle" / "references" / "complete.md"
    assert complete_md.exists(), f"complete.md missing at {complete_md}"

    region = _extract_region(complete_md.read_text(encoding="utf-8"))

    assert "cortex-read-commit-artifacts" in region, (
        "finalization-commit-step region must invoke the cortex-read-commit-artifacts binstub"
    )
    assert "/cortex-core:commit" in region, (
        "finalization-commit-step region must invoke /cortex-core:commit"
    )
    assert "git diff --cached --quiet" in region, (
        "finalization-commit-step region must include the stage-first idempotent guard "
        "'git diff --cached --quiet'"
    )

    # Enumerated lifecycle-path staging (R5): individual filenames must be present
    enumerated_files = [
        "research.md",
        "spec.md",
        "plan.md",
        "review.md",
        "index.md",
        "events.log",
    ]
    for fname in enumerated_files:
        assert fname in region, (
            f"finalization-commit-step region must stage '{fname}' by enumerated path (R5)"
        )

    # Backlog directory-scoped staging must be present
    assert "cortex/backlog/" in region, (
        "finalization-commit-step region must stage cortex/backlog/ for the backlog write-back"
    )

    # Halt-on-failure clause: commit failure must stop progress
    region_lower = region.lower()
    halt_tokens = ("stop", "halt", "do not")
    assert any(t in region_lower for t in halt_tokens), (
        f"finalization-commit-step region must encode a halt-on-failure clause "
        f"(one of {halt_tokens})"
    )

    # Non-default-branch advisory (R13): must mention main and master
    assert "main" in region, (
        "finalization-commit-step region must reference 'main' in the branch advisory (R13)"
    )
    assert "master" in region, (
        "finalization-commit-step region must reference 'master' in the branch advisory (R13)"
    )


def test_finalization_commit_region_negative_tokens() -> None:
    """Forbidden tokens must NOT appear within the anchored region."""
    repo_root = _repo_root()
    complete_md = repo_root / "skills" / "lifecycle" / "references" / "complete.md"
    assert complete_md.exists(), f"complete.md missing at {complete_md}"

    region = _extract_region(complete_md.read_text(encoding="utf-8"))

    assert "git push" not in region, (
        "finalization-commit-step region must not contain 'git push' — "
        "pushing is not part of the finalization commit step"
    )
    assert "gh pr create" not in region, (
        "finalization-commit-step region must not contain 'gh pr create' — "
        "PR creation is not part of the finalization commit step"
    )

    # R5-forbidden directory-glob: 'git add cortex/lifecycle/' must not appear.
    # The region stages lifecycle artifacts by enumerated filenames only; a
    # directory-glob would sweep in un-gitignored residue. A bare presence
    # check on the full file would miss this because the glob might appear
    # elsewhere in prose; we scope to the region to guard against a
    # glob-plus-prose-mention bypass.
    assert "git add cortex/lifecycle/" not in region, (
        "finalization-commit-step region must not contain 'git add cortex/lifecycle/' — "
        "R5 requires enumerated filenames, not a directory-scoped add on the lifecycle dir"
    )
