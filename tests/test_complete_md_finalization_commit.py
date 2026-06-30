"""Scoped structural guard test for the finalization-commit-step region.

Slices the ``<!-- finalization-commit-step -->`` …
``<!-- /finalization-commit-step -->`` region out of the canonical
``skills/lifecycle/references/complete.md`` and asserts:

After #331 Phase 2 the Step-11a staging mechanics (the enumerated ``git add``,
the resolver lookup, the ``-u`` sweep, the "never directory-glob" warnings)
collapsed into the ``cortex-lifecycle-stage-artifacts --phase complete`` verb.
The region keeps only the residual control flow; the verb's behavioral staged-set
test (``tests/test_stage_artifacts.py``, Req 13) owns the staging-discipline
assertions that used to live here.

Positive tokens (all must be present in the region):
- ``cortex-lifecycle-stage-artifacts`` — the staging verb the enumerated
  ``git add`` / resolver lookup / ``-u`` sweep collapsed into (Req 14)
- ``cortex-read-commit-artifacts`` — binstub invocation (Flag Check stays prose)
- ``/cortex-core:commit`` — commit skill invocation
- ``git diff --cached --quiet`` — the stage-first idempotent guard; the verb's
  ``signal`` is documented as equivalent to this exit, and it stays prose
  control flow (not absorbed by the verb)
- A halt-on-failure clause for a non-zero commit/stage exit
- A ``main`` / ``master`` non-default-branch advisory (R13)

The staging-mechanics tokens that moved into the verb are no longer asserted
here: the enumerated lifecycle filenames, ``Suggested Requirements Update``, and
``cortex-resolve-backlog-item`` (dropped — the verb owns them), and
``git add -u cortex/backlog/`` (flipped to a *negative* token below — the bug-2
``-u`` sweep was narrowed away, Req 11).

Negative tokens (must NOT appear in the region):
- ``git push`` — pushing is not part of the finalization commit step
- ``gh pr create`` — PR creation is not part of the finalization commit step
- ``git add cortex/lifecycle/`` — R5-forbidden directory-glob staging pattern
  (the region must use enumerated filenames, not a directory-scoped add
  on the lifecycle dir; a bare presence check would miss a glob-plus-prose-
  mention bypass)
- ``git add -u cortex/requirements/`` / bare ``git add cortex/requirements/``
  — defect 2 forbids a directory-scoped requirements add (sweeps unrelated
  in-flight edits); only the exact review.md-recorded ``File`` path is staged
- ``git add cortex/backlog/`` (unscoped, bare) — defect 3 forbids the
  directory-sweep that captured unrelated untracked tickets
- ``git add -u cortex/backlog/`` — the bug-2 ``-u`` sweep: previously asserted
  *present*, now forbidden in the prose (the narrowed two-explicit-path staging
  moved into the verb; the over-broad sweep was dropped, Req 11)
- ``cortex/backlog/*-`` — the tail-anchored slug-glob matches zero files
  (the lifecycle slug is a truncated prefix of the backlog filename slug);
  the resolver's ``filename`` is used instead

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

    # Req 14: the Step-11a staging mechanics collapsed into the verb invocation.
    assert "cortex-lifecycle-stage-artifacts" in region, (
        "finalization-commit-step region must invoke the "
        "'cortex-lifecycle-stage-artifacts' staging verb (Req 14) — the "
        "enumerated git-add / resolver lookup / -u sweep collapsed into it"
    )

    assert "cortex-read-commit-artifacts" in region, (
        "finalization-commit-step region must invoke the cortex-read-commit-artifacts binstub"
    )
    assert "/cortex-core:commit" in region, (
        "finalization-commit-step region must invoke /cortex-core:commit"
    )
    assert "git diff --cached --quiet" in region, (
        "finalization-commit-step region must include the stage-first idempotent guard "
        "'git diff --cached --quiet' (the verb's signal is equivalent to this exit; "
        "the guard stays prose control flow)"
    )

    # NOTE: the enumerated lifecycle filenames, 'Suggested Requirements Update',
    # and 'cortex-resolve-backlog-item' staging-mechanics tokens moved into the
    # stage-artifacts verb (Req 14) and are now pinned by the verb's behavioral
    # staged-set test (tests/test_stage_artifacts.py, Req 13). 'git add -u
    # cortex/backlog/' flipped to a negative token (bug-2, Req 11) — see below.

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

    # Defect 2: directory-scoped requirements staging is forbidden — it would
    # sweep unrelated in-flight cortex/requirements/ edits into the commit.
    assert "git add -u cortex/requirements/" not in region, (
        "finalization-commit-step region must not contain "
        "'git add -u cortex/requirements/' — defect 2 forbids a directory-scoped "
        "requirements add; stage only the exact review.md-recorded File path"
    )
    assert "git add cortex/requirements/" not in region, (
        "finalization-commit-step region must not contain the bare "
        "'git add cortex/requirements/' — defect 2 forbids a directory-scoped "
        "requirements add; stage only the exact review.md-recorded File path"
    )

    # Defect 3: the unscoped bare backlog directory-sweep is forbidden (it
    # captured unrelated untracked tickets). After #331 Phase 2 the narrowed
    # backlog staging lives in the verb, so no bare 'git add cortex/backlog/'
    # appears in the prose either.
    assert "git add cortex/backlog/" not in region, (
        "finalization-commit-step region must not contain the unscoped "
        "'git add cortex/backlog/' — defect 3 forbids the directory-sweep that "
        "captured unrelated untracked tickets; the narrowed staging is in the verb"
    )

    # Bug-2 flip (Req 11): 'git add -u cortex/backlog/' was previously asserted
    # PRESENT (the -u tracked-modified sweep). The sweep over-captured unrelated
    # dirty tickets (cross-session contamination), so it was dropped and the
    # backlog write-back narrowed to two explicit paths inside the verb. The
    # over-broad -u sweep must no longer appear in the prose.
    assert "git add -u cortex/backlog/" not in region, (
        "finalization-commit-step region must not contain "
        "'git add -u cortex/backlog/' — the bug-2 -u sweep was narrowed away "
        "(Req 11); the verb stages the resolved ticket file + index.md explicitly"
    )

    # Defect 3: the tail-anchored slug-glob matches zero files and must not be
    # used; the resolver's filename is the correct mechanism.
    assert "cortex/backlog/*-" not in region, (
        "finalization-commit-step region must not contain a tail-anchored "
        "'cortex/backlog/*-' slug-glob — it matches zero files because the "
        "lifecycle slug is a truncated prefix of the backlog filename slug; "
        "use the resolver's 'filename' instead"
    )
