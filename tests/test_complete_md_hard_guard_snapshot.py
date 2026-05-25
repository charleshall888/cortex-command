"""Snapshot test for the Step 8 hard-guard paragraph in complete.md.

Guards the load-bearing user-facing string that fires when a Complete-phase
session is running from inside the target worktree. The hard guard teaches
two exit paths to the user: `ExitWorktree action="keep"` (preferred when
EnterWorktree session state is live) and `cd $(git rev-parse --show-toplevel)`
(works in both same-session and cross-session contexts). See R13 in
`cortex/lifecycle/lifecycle-implement-auto-enter-worktree-via/spec.md`.

The test reads the hard-guard paragraph from `complete.md` (the bytes between
the `**Hard guard**:` heading and the next `**` bold header) and asserts
byte-equality with the fixture at `tests/fixtures/complete_md_hard_guard.txt`.

Update protocol: if intentional edits to the hard-guard prose land, update
the fixture file at `tests/fixtures/complete_md_hard_guard.txt` in the same
commit. The fixture exists to catch silent drift; the byte-equality check is
intentional.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPLETE_MD = REPO_ROOT / "skills" / "lifecycle" / "references" / "complete.md"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "complete_md_hard_guard.txt"


def _extract_hard_guard_paragraph(text: str) -> str:
    """Return the bytes of the hard-guard paragraph in ``complete.md``.

    The paragraph spans from the ``**Hard guard**:`` heading (inclusive) up to
    (but not including) the next bold-header line such as ``**Prefix check**:``.
    """
    start = text.index("**Hard guard**:")
    rest = text[start:]
    # Skip past the opening ``**`` of the Hard guard heading, then find the
    # next bold-header marker preceded by a blank line.
    match = re.search(r"\n\n\*\*", rest[2:])
    assert match is not None, "could not locate end-of-paragraph boundary"
    end = match.start() + 2 + 1  # include the trailing newline before the blank line
    return rest[:end]


def test_hard_guard_paragraph_matches_fixture() -> None:
    actual = _extract_hard_guard_paragraph(COMPLETE_MD.read_text())
    expected = FIXTURE.read_text()
    assert actual == expected, (
        "Step 8 hard-guard paragraph in "
        f"{COMPLETE_MD.relative_to(REPO_ROOT)} drifted from fixture at "
        f"{FIXTURE.relative_to(REPO_ROOT)}. If the edit is intentional, "
        "update the fixture file in the same commit."
    )
