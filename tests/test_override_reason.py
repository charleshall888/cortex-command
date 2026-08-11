"""Unit pins for the shared override-reason clause vocabulary.

`cortex_command/override_reason.py` is the one definition of "what a clause tag
is" that both override-row writers (`refine.py`'s `reconcile-clarify` and
`lifecycle_event.py`'s typed override verbs) import. Its interesting behavior is
invisible to the `reconcile-clarify` end-to-end suite: every reason literal there
is a valid lowercase tag, a single-token bogus tag, `plain text`, or `""`, so not
one of them changes verdict under the widened matching or the canonicalizer. This
module pins that behavior at the module boundary instead.

Red against the pre-change predicate: the superseded `refine.py` predicate matched
the raw pre-colon prefix against the allowed set with no `.strip()` and no
`.lower()`, so `"Exposure: x"` and `" exposure: x"` were REJECTED and
`"blast radius: unbounded"` was rejected as a bogus tag rather than carried through
as prose. The tagged-acceptance and untagged-prose cases below therefore fail
against it. That expectation is recorded here rather than asserted, since the old
predicate no longer exists to run against.
"""

from __future__ import annotations

import pytest

from cortex_command.override_reason import (
    ALLOWED_REASON_CLAUSES,
    canonicalize_reason,
    claimed_tag,
    reason_clause_ok,
)

# Reasons that DO claim a clause tag, paired with the tag they claim. Covers the
# widened matching: leading capital, leading whitespace, no space after the colon,
# an empty body, and a body carrying further colons.
TAGGED = [
    ("exposure: x", "exposure"),
    ("Exposure: x", "exposure"),
    (" exposure: x", "exposure"),
    ("other:x", "other"),
    ("exposure:", "exposure"),
    ("exposure: it feeds A: B", "exposure"),
]

# Reasons that claim NO tag and are carried through as free prose. The first three
# contain a colon but a multi-word prefix; the rest have no colon at all, or are
# empty/absent.
UNTAGGED = [
    "blast radius: unbounded",
    "Chose high: consumer-facing",
    "see research.md line 40: the fork",
    "plain text",
    "",
    None,
]

# Reasons that claim a single-token tag outside the vocabulary.
REJECTED = [
    "zzz: y",
    "zzz:",
    "design-fork: two options",
]


@pytest.mark.parametrize(("value", "tag"), TAGGED, ids=[repr(v) for v, _ in TAGGED])
def test_tagged_reason_claims_its_canonical_tag(value: str, tag: str) -> None:
    """A recognized tag is claimed case- and whitespace-insensitively."""
    assert claimed_tag(value) == tag
    assert tag in ALLOWED_REASON_CLAUSES


@pytest.mark.parametrize(("value", "tag"), TAGGED, ids=[repr(v) for v, _ in TAGGED])
def test_tagged_reason_is_accepted(value: str, tag: str, capsys) -> None:
    """A recognized tag passes the gate silently."""
    assert reason_clause_ok("--tier-reason", value, "cortex-probe") is True
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("value", UNTAGGED, ids=[repr(v) for v in UNTAGGED])
def test_untagged_prose_claims_no_tag(value: str | None) -> None:
    """Prose whose pre-colon prefix is multi-word (or absent) claims no tag."""
    assert claimed_tag(value) is None


@pytest.mark.parametrize("value", UNTAGGED, ids=[repr(v) for v in UNTAGGED])
def test_untagged_prose_is_accepted(value: str | None, capsys) -> None:
    """Untagged prose passes the gate silently — it is never parsed as a tag."""
    assert reason_clause_ok("--tier-reason", value, "cortex-probe") is True
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("value", REJECTED, ids=[repr(v) for v in REJECTED])
def test_out_of_vocabulary_tag_claims_that_tag(value: str) -> None:
    """A single-token prefix is claimed as a tag even when unrecognized."""
    tag = claimed_tag(value)
    assert tag is not None
    assert tag not in ALLOWED_REASON_CLAUSES


@pytest.mark.parametrize("value", REJECTED, ids=[repr(v) for v in REJECTED])
def test_out_of_vocabulary_tag_is_rejected(value: str, capsys) -> None:
    """An unrecognized tag is refused, with the offending tag named on stderr."""
    assert reason_clause_ok("--tier-reason", value, "cortex-probe") is False
    err = capsys.readouterr().err
    assert repr(claimed_tag(value)) in err


def test_rejection_names_only_the_prog_it_was_handed(capsys) -> None:
    """The diagnostic carries the invoking prog and no other program name."""
    assert reason_clause_ok("--tier-reason", "zzz: y", "cortex-probe") is False
    err = capsys.readouterr().err
    assert "cortex-probe" in err
    for other in ("cortex-refine", "cortex-lifecycle-event", "cortex-lifecycle"):
        assert other not in err


def test_canonicalize_lowercases_and_strips_the_tag() -> None:
    """A recognized tag is rewritten to its canonical lowercase, unpadded form."""
    out = canonicalize_reason(" Exposure: it feeds spec authoring")
    assert out.startswith("exposure: ")
    assert out == "exposure: it feeds spec authoring"


def test_canonicalize_leaves_untagged_prose_byte_identical() -> None:
    """Prose claiming no tag is returned byte-for-byte unchanged."""
    value = "blast radius: unbounded"
    assert canonicalize_reason(value) == value


def test_canonicalize_leaves_an_inner_colon_body_untouched() -> None:
    """Only the tag is rewritten; a body carrying further colons survives."""
    value = "exposure: it feeds A: B"
    assert canonicalize_reason(value) == value
