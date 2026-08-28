"""Absence guard for the finalization-commit-step region of complete.md.

Slices the ``<!-- finalization-commit-step -->`` …
``<!-- /finalization-commit-step -->`` region out of the canonical
``skills/build/references/complete.md`` and asserts that a set of staging
patterns — each of which caused a real, named defect — stays out of it.

After #331 Phase 2 the Step-11a staging mechanics (the enumerated ``git add``,
the resolver lookup, the ``-u`` sweep, the "never directory-glob" warnings)
collapsed into the ``cortex-lifecycle-stage-artifacts --phase complete`` verb.
The region keeps only the residual control flow; the verb's behavioral
staged-set test (``tests/test_stage_artifacts.py``, Req 13) owns the
staging-discipline assertions that used to live here.

The companion positive-token test was deleted on 2026-08-28 under
``docs/policies.md`` § "No tests on skill prose": asserting that
``cortex-lifecycle-stage-artifacts``, ``git commit --only``, a halt clause and
a ``main``/``master`` advisory *appear* in the region could only be satisfied
by keeping those words, which is the gradient that grows skill prose. The
region is scoped rather than file-wide because these patterns may legitimately
appear elsewhere in complete.md.

Negative tokens (must NOT appear in the region):
- ``cortex-read-commit-artifacts`` — the commit-artifacts flag read folded INTO
  ``cortex-lifecycle-stage-artifacts`` (one round-trip instead of two); a
  separate binstub invocation here is the round-trip that was removed
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
- ``git diff --cached --quiet`` — previously asserted *present* as the
  stage-first idempotent guard, on the premise that the verb's ``signal`` was
  equivalent to its exit. #417 scoped the verb's read to its own paths, so the
  equivalence is false on a shared index: the unscoped exit goes 1 on a
  concurrent session's staging alone. Documenting it taught consumers to commit
  on a false positive

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


def test_finalization_commit_region_negative_tokens() -> None:
    """Forbidden tokens must NOT appear within the anchored region."""
    repo_root = _repo_root()
    complete_md = repo_root / "skills" / "build" / "references" / "complete.md"
    assert complete_md.exists(), f"complete.md missing at {complete_md}"

    region = _extract_region(complete_md.read_text(encoding="utf-8"))

    # #417: the verb's signal is scoped to its OWN paths, so it is NOT equivalent
    # to a whole-index 'git diff --cached --quiet'. On a trunk repo two lifecycles
    # share one index, and the unscoped exit goes 1 on a concurrent session's
    # staging alone — documenting the equivalence taught consumers to trust a
    # false positive and commit a sibling's in-flight work.
    # The commit-artifacts flag read folded INTO stage-artifacts (one
    # round-trip instead of two), so the region must route the verb's
    # config_disabled signal rather than invoke the standalone binstub.
    assert "cortex-read-commit-artifacts" not in region, (
        "finalization-commit-step region must NOT invoke "
        "cortex-read-commit-artifacts separately — "
        "cortex-lifecycle-stage-artifacts reads the flag itself"
    )
    assert "git diff --cached --quiet" not in region, (
        "finalization-commit-step region must NOT equate the verb's signal to "
        "'git diff --cached --quiet' (#417) — that exit reflects the whole shared "
        "index, while signal reflects only this verb's own staged paths"
    )

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
