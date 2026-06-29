"""Unit tests for cortex_command.lifecycle.parse_args.

Test names embed ``grammar`` / ``edge`` so the spec's
``pytest ... -k grammar`` / ``-k edge`` acceptance selectors resolve.
"""

import pytest

from cortex_command.lifecycle.parse_args import KNOWN_MODES, parse


# --- grammar: the full reserved set + the unaffected default form ----------

@pytest.mark.parametrize(
    "arguments, expected",
    [
        # reserved verbs invert order: word #2 is the target.
        ("wontfix add-foo", {"mode": "wontfix", "feature": "add-foo", "phase": ""}),
        ("resume add-foo", {"mode": "resume", "feature": "add-foo", "phase": ""}),
        (
            "complete add-foo",
            {"mode": "complete", "feature": "add-foo", "phase": "complete"},
        ),
        # case-insensitive first word.
        ("WONTFIX add-foo", {"mode": "wontfix", "feature": "add-foo", "phase": ""}),
        # bare phase tokens (sole word) -> feature-required fallback.
        ("plan", {"mode": "phase", "feature": "", "phase": "plan"}),
        ("review", {"mode": "phase", "feature": "", "phase": "review"}),
        ("complete", {"mode": "phase", "feature": "", "phase": "complete"}),
        # normal <feature> [phase] is unaffected.
        ("my-feature", {"mode": "feature", "feature": "my-feature", "phase": ""}),
        (
            "my-feature plan",
            {"mode": "feature", "feature": "my-feature", "phase": "plan"},
        ),
        # numeric slug (a backlog id used as a slug) is a valid feature.
        ("329", {"mode": "feature", "feature": "329", "phase": ""}),
    ],
)
def test_grammar_reserved_and_default(arguments, expected):
    assert parse(arguments) == expected


def test_grammar_every_returned_mode_is_known():
    samples = [
        "",
        "wontfix add-foo",
        "wontfix",
        "resume add-foo",
        "resume",
        "complete add-foo",
        "complete",
        "plan",
        "my-feature",
        "Some prose intent here",
        "#wontfix",
    ]
    for s in samples:
        assert parse(s)["mode"] in KNOWN_MODES


# --- edge cases ------------------------------------------------------------

def test_edge_hash_sigil_suppresses_reserved_match():
    # #wontfix is a literal feature slug, NOT the wontfix verb route.
    assert parse("#wontfix") == {
        "mode": "feature",
        "feature": "wontfix",
        "phase": "",
    }


def test_edge_hash_sigil_on_id():
    assert parse("#001") == {"mode": "feature", "feature": "001", "phase": ""}


def test_edge_reserved_word_alone_is_not_a_feature():
    # wontfix with no slug is an error, never a feature named "wontfix".
    assert parse("wontfix") == {"mode": "error", "feature": "", "phase": ""}


def test_edge_resume_alone_falls_back_to_scan():
    assert parse("resume") == {"mode": "empty", "feature": "", "phase": ""}


def test_edge_prose_first_word_needs_derivation():
    assert parse("Add a widget to the dashboard") == {
        "mode": "needs-derivation",
        "feature": "",
        "phase": "",
    }


def test_edge_empty_arguments():
    assert parse("") == {"mode": "empty", "feature": "", "phase": ""}
    assert parse("   ") == {"mode": "empty", "feature": "", "phase": ""}
