"""Classify a /cortex-core:lifecycle invocation string.

``parse()`` returns ``{"mode": ..., "feature": ..., "phase": ...}`` and is
consumed by the ``cortex-lifecycle-resolve`` façade verb (its former console
wrapper, ``cortex-lifecycle-parse-args``, was retired by #405). This is the
structural source of truth for the invocation grammar that SKILL.md Step 1
used to parse in prose. The model still finishes the irreducible prose->slug
derivation (signalled by ``mode == "needs-derivation"``).

Grammar (canonical parse order):
    empty-check -> #-sigil handling -> reserved-word match -> slug/prose-derive

Reserved first-words {wontfix, resume, complete} INVERT the default
``<feature> [phase]`` order: word #2 is the target. ``complete <slug>`` also
sets ``phase=complete``. A leading ``#`` suppresses reserved-matching (the
documented "this is a literal id" sigil), so ``#wontfix`` is the feature slug
``wontfix``, not the verb route.

The ``phase`` slot only ever carries a member of the phase vocabulary (#402):
a word-2 token outside it — trailing natural language like ``356 resume
implementing`` — is never threaded as a route. Dropped tokens are reported in
an ``ignored_tokens`` list (present only when non-empty) so the caller can
surface what the grammar discarded rather than silently eating a typo'd phase.
"""

from __future__ import annotations

import re
from typing import List, Optional

# Closed set of mode values the parser can emit. Asserted for coverage by
# tests/test_lifecycle_invocation_grammar_parity.py (every literal must have a
# handler branch documented in SKILL.md Step 1).
KNOWN_MODES = (
    "wontfix",
    "resume",
    "complete",
    "phase",
    "feature",
    "needs-derivation",
    "empty",
    "error",
)

# Reserved first-words that take a slug as word #2 (inverting the default order).
RESERVED_WORDS = ("wontfix", "resume", "complete")

# Bare phase tokens. ``complete`` is also a phase token but is handled in the
# reserved branch (it takes a slug); the rest only get the feature-required
# fallback when they appear as a sole word.
PHASE_TOKENS = ("research", "specify", "plan", "implement", "review")

# Same charset as cortex_command.common.slugify produces. The parser only
# classifies — it does not slugify — so the pattern is inlined rather than
# imported.
_VALID_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# The full phase vocabulary a word-2 override may carry. ``complete`` doubles as
# a phase here even though it is reserved-matched as word #1.
_OVERRIDE_PHASES = PHASE_TOKENS + ("complete",)


def _result(
    mode: str, feature: str = "", phase: str = "", ignored: Optional[List[str]] = None
) -> dict:
    out = {"mode": mode, "feature": feature, "phase": phase}
    if ignored:
        out["ignored_tokens"] = list(ignored)
    return out


def _phase_and_ignored(rest: List[str]) -> tuple:
    """Split the tokens after the feature into (phase, ignored). Only a member
    of the phase vocabulary becomes the override (lowercased); anything else —
    and everything after a valid override — is ignored, never a route (#402)."""
    if not rest:
        return "", []
    head = rest[0].lower()
    if head in _OVERRIDE_PHASES:
        return head, list(rest[1:])
    return "", list(rest)


def parse(arguments: str) -> dict:
    """Classify a raw ``$ARGUMENTS`` string into ``{mode, feature, phase}``."""
    tokens = (arguments or "").split()
    if not tokens:
        return _result("empty")

    first = tokens[0]
    second = tokens[1] if len(tokens) >= 2 else ""

    # #-sigil: suppress reserved-matching, treat word #1 as a literal id/slug.
    if first.startswith("#"):
        target = first[1:]
        if _VALID_SLUG.match(target):
            phase, ignored = _phase_and_ignored(tokens[1:])
            return _result("feature", feature=target, phase=phase, ignored=ignored)
        return _result("needs-derivation")

    low = first.lower()

    # Reserved first-words invert the default order (word #2 is the target).
    if low == "wontfix":
        if second:
            return _result("wontfix", feature=second, ignored=tokens[2:])
        return _result("error")
    if low == "resume":
        # resume with no slug falls back to the incomplete-lifecycle scan.
        if second:
            return _result("resume", feature=second, ignored=tokens[2:])
        return _result("empty")
    if low == "complete":
        if second:
            return _result(
                "complete", feature=second, phase="complete", ignored=tokens[2:]
            )
        return _result("phase", phase="complete")

    # Bare phase token (sole word) -> feature-required fallback.
    if low in PHASE_TOKENS and len(tokens) == 1:
        return _result("phase", phase=low)

    # Default <feature> [phase]: word #1 is the feature, word #2 an override
    # only when it is a phase token (#402) — never trailing natural language.
    if _VALID_SLUG.match(first):
        phase, ignored = _phase_and_ignored(tokens[1:])
        return _result("feature", feature=first, phase=phase, ignored=ignored)
    return _result("needs-derivation")
