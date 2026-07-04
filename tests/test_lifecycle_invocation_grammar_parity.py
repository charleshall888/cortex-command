"""Docs-derived drift-guard for the /cortex-core:lifecycle invocation grammar.

This test scrapes the advertised ``/cortex-core:lifecycle <form>`` occurrences
from the LIVE doc bytes (``skills/lifecycle/SKILL.md`` + ``references/*.md``),
normalizes their placeholders to concrete test tokens, feeds each through
``cortex_command.lifecycle.parse_args.parse``, and asserts each classifies to
the ``mode`` its SHAPE intends (a small independent shape->mode oracle). A doc
that gains a form the parser mis-handles — or a parser change that breaks an
advertised form — fails the gate. Plus a mode-coverage check that every
``KNOWN_MODES`` literal has a routing-table row in SKILL.md Step 1.

Scope honesty (the residual the structural parser does not close): the oracle is
keyed on the CURRENT closed reserved/phase grammar, so a genuinely NEW reserved
verb added to a doc would be classified ``feature`` by BOTH the oracle and the
parser (they agree -> green). Catching that requires updating the oracle and the
grammar together; the docs->parser direction is enforced here only for the
forms the oracle understands. See negative control (ii).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cortex_command.lifecycle.parse_args import KNOWN_MODES, PHASE_TOKENS, parse


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_MD = REPO_ROOT / "skills" / "lifecycle" / "SKILL.md"
REFERENCES_DIR = REPO_ROOT / "skills" / "lifecycle" / "references"

# Capture 1-2 argument tokens after the command. Tokens exclude whitespace,
# backticks, and double-quotes (the inline-code / quoted-string delimiters), so
# a bare ``/cortex-core:lifecycle`` mention with no argument (e.g.
# "does not exit `/cortex-core:lifecycle`") yields no match and is dropped. The
# {1,2} bound keeps reserved two-token forms (``wontfix <slug>``) intact rather
# than degrading them to their lone first word.
_FORM_RE = re.compile(r"/cortex-core:lifecycle((?:[ \t]+[^\s`\"]+){1,2})")

# Placeholder -> canonical concrete test token. ``<phase>``/``{{phase}}`` map to
# a real phase token so a ``<feature> <phase>`` form parses with a valid word #2.
_NORMALIZE = {
    "<slug>": "test-slug",
    "{{slug}}": "test-slug",
    "<feature>": "test-feature",
    "{{feature}}": "test-feature",
    "{feature}": "test-feature",
    "<phase>": "plan",
    "{{phase}}": "plan",
}


def _normalize_token(tok: str) -> str:
    # Strip trailing sentence/markdown punctuation (but not the ``>`` that
    # closes a ``<placeholder>``) before the exact-match placeholder lookup.
    stripped = tok.rstrip(",.;:)")
    return _NORMALIZE.get(stripped, stripped)


def _scrape_forms(text: str) -> list[list[str]]:
    forms: list[list[str]] = []
    for m in _FORM_RE.finditer(text):
        raw = m.group(1).split()[:2]
        forms.append([_normalize_token(t) for t in raw])
    return forms


def _all_forms() -> list[list[str]]:
    files = [SKILL_MD] + sorted(REFERENCES_DIR.glob("*.md"))
    forms: list[list[str]] = []
    for f in files:
        forms.extend(_scrape_forms(f.read_text()))
    return forms


def _expected_mode(tokens: list[str]) -> str:
    """Independent shape->mode oracle (not a copy of parse(); a parser
    regression on any advertised form is caught by the disagreement)."""
    first = tokens[0].lower()
    has_second = len(tokens) >= 2
    if first == "wontfix":
        return "wontfix" if has_second else "error"
    if first == "resume":
        return "resume" if has_second else "empty"
    if first == "complete":
        return "complete" if has_second else "phase"
    if first in PHASE_TOKENS and not has_second:
        return "phase"
    return "feature"


def _assert_form_classifies(tokens, parse_fn, expected_mode: str) -> None:
    arguments = " ".join(tokens)
    got = parse_fn(arguments)["mode"]
    if got != expected_mode:
        raise AssertionError(
            f"form {arguments!r}: parser produced mode={got!r}, expected {expected_mode!r}"
        )


def test_grammar_advertised_forms_classify() -> None:
    forms = _all_forms()
    # Vacuous-pass guard: an empty scrape (regex broke) would let the loop below
    # pass with zero assertions. Guard against that specific hole only — NOT a
    # content-count floor, which fires on legitimate doc trims.
    assert forms, "scraped no forms — scraper regex broke"
    for tokens in forms:
        _assert_form_classifies(tokens, parse, _expected_mode(tokens))


def test_grammar_reserved_two_token_forms_captured_intact() -> None:
    # The reserved verbs must be scraped WITH their slug, not degraded to the
    # lone reserved word (which would classify to error/empty/phase, mismatching
    # the two-token oracle). Proves the capture-width fix holds against live docs.
    forms = _all_forms()
    reserved_two_token = [
        f for f in forms if f and f[0].lower() in ("wontfix", "resume", "complete") and len(f) >= 2
    ]
    assert reserved_two_token, "no reserved two-token forms scraped — capture degraded to lone words"


def test_state_coverage_every_known_state_has_a_routing_row() -> None:
    # Step 1 now routes on cortex-lifecycle-resolve's `state` (parse-args `mode`
    # is internal to that verb). The live contract: every state the verb can
    # emit must be documented in Step 1, or the skill has a routing gap.
    from cortex_command.lifecycle.resolve import KNOWN_STATES

    text = SKILL_MD.read_text()
    step1 = text.split("## Step 1", 1)[1].split("## Step 2", 1)[0]
    missing = [s for s in KNOWN_STATES if f"`{s}`" not in step1]
    assert not missing, f"Step 1 missing routing coverage for states: {missing}"


# --- negative controls -----------------------------------------------------

def test_negative_control_parser_regression_is_caught() -> None:
    # (i) A parser that drops the complete-reserved handling disagrees with the
    # oracle for the advertised `complete <slug>` form -> the check raises.
    def broken_parse(arguments: str) -> dict:
        d = parse(arguments)
        if d["mode"] == "complete":
            return {"mode": "feature", "feature": d["feature"], "phase": ""}
        return d

    with pytest.raises(AssertionError):
        _assert_form_classifies(["complete", "test-slug"], broken_parse, "complete")


def test_negative_control_doc_form_without_parser_support_is_caught() -> None:
    # (ii) A doc advertising a form whose INTENDED mode the parser does not
    # produce is caught when the oracle encodes that intent. `abandon <slug>`
    # advertised as a wontfix alias: the real parser returns `feature`, so the
    # mismatch raises — the docs->parser recurrence direction. (A brand-new verb
    # with no oracle entry is the documented residual; see module docstring.)
    with pytest.raises(AssertionError):
        _assert_form_classifies(["abandon", "test-slug"], parse, "wontfix")
