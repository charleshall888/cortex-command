"""Clause vocabulary for override ``--reason``/``--*-reason`` values.

This module exists so the two surfaces that write override rows —
``cortex_command/refine.py``'s ``reconcile-clarify`` and
``cortex_command/lifecycle_event.py``'s typed override verbs — can share one
definition of what a clause tag is. ``refine.py:29`` already imports from
``lifecycle_event``, so the shared predicate cannot live in either writer
without a cycle; it lives here instead, beneath both.

**Keep this module stdlib-only.** It must import no ``cortex_command`` module,
because any such import is what would reintroduce that cycle.
"""

from __future__ import annotations

import sys


# Optional clause tags an override reason may lead with. A free-text reason is
# still accepted verbatim (a reason with no ``:`` is never parsed), but when a
# clause IS claimed it must be one the corpus can tally — an open vocabulary
# makes `reason.split(":")[0]` a histogram of typos rather than of axes.
ALLOWED_REASON_CLAUSES: frozenset[str] = frozenset(
    {"reversibility", "exposure", "consequence", "other"}
)
BAD_REASON_CLAUSE_MSG = (
    "{prog}: {flag} {value!r}: clause tag {tag!r} is not one of: {allowed}"
)


def claimed_tag(value: str | None) -> str | None:
    """The clause tag a reason claims, or ``None`` when it claims none.

    A tag is claimed only when the text before the FIRST colon is, after
    ``.strip()``, non-empty and free of whitespace — a single token. The
    returned tag is that token lowercased, so ``Exposure: x`` and
    ``exposure: x`` claim the same tag.

    ``None`` therefore covers three shapes, all of which are untagged prose
    written verbatim: no colon at all, an empty prefix (``": x"``), and a
    multi-word prefix (``"blast radius: unbounded"``).
    """
    if value is None or ":" not in value:
        return None
    prefix = value.split(":", 1)[0].strip()
    if not prefix or any(ch.isspace() for ch in prefix):
        return None
    return prefix.lower()


def reason_clause_ok(flag: str, value: str | None, prog: str) -> bool:
    """Whether an override reason's clause tag, if any, is acceptable.

    Non-raising by design: it prints :data:`BAD_REASON_CLAUSE_MSG` to stderr
    and returns ``False`` only when a tag is claimed and falls outside
    :data:`ALLOWED_REASON_CLAUSES`. Callers validating two reasons run both
    calls unconditionally so a caller that got both tags wrong sees both
    diagnostics in one run.
    """
    tag = claimed_tag(value)
    if tag is None or tag in ALLOWED_REASON_CLAUSES:
        return True
    print(
        BAD_REASON_CLAUSE_MSG.format(
            prog=prog,
            flag=flag,
            value=value,
            tag=tag,
            allowed=", ".join(sorted(ALLOWED_REASON_CLAUSES)),
        ),
        file=sys.stderr,
    )
    return False


def canonicalize_reason(value: str) -> str:
    """Lowercase a recognized clause tag, leaving everything else byte-identical.

    Only the tag is rewritten: the body after the first colon is carried
    through unmodified, so a body containing further colons (``"exposure: it
    feeds A: B"``) survives untouched. A reason claiming no recognized tag is
    returned unchanged.
    """
    tag = claimed_tag(value)
    if tag is None or tag not in ALLOWED_REASON_CLAUSES:
        return value
    body = value.split(":", 1)[1]
    return f"{tag}:{body}"
