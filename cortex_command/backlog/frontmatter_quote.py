#!/usr/bin/env python3
"""Key-scoped, single-scalar YAML-safe quoter for hand-rolled frontmatter writes.

Tool-managed backlog/lifecycle frontmatter is emitted by per-key line editors
(deliberately — to preserve the ordered-block + inline-array + bare-``null``
shape that PyYAML's block dumper cannot reproduce). That writer boundary erases
Python type: every value arrives as ``str`` (and the ``None`` path arrives as
the literal ``"null"``). A bare-numeric string slug therefore type-leaks —
``lifecycle_slug: 378`` reads back as ``int`` under ``yaml.safe_load`` and
crashes the served resolve path.

The fix is a *key-scoped* quoter, NOT a ``safe_dump``-style "quote anything that
would mis-resolve" rule: dates (``updated``/``created``) and the ``null``
sentinel also mis-resolve under YAML 1.1 yet MUST stay bare. Because the writer
boundary erases Python type, intent is carried by the **key**, not inferred from
the value — so only keys on ``STRING_INTENDED_KEYS`` are quoted, and only when
the value would otherwise mis-resolve (except the ``None`` sentinel, which stays
bare even on an allowlisted key to preserve the resolver's null-fallback).

Implemented as a single-scalar line edit (an escaped YAML double-quoted scalar),
NOT a ``yaml.safe_dump`` block round-trip. See cortex/lifecycle/378/spec.md
req-1 and the proposed ADR-0027 (frontmatter-scalar-write-contract).
"""

from __future__ import annotations

import yaml

# Keys whose values are string-intended slugs / paths / id-strings. Only these
# get YAML-safe quoting; every other key (the ``updated``/``created`` dates, the
# ``null`` sentinel, ``blocked-by``/``parent_backlog_id`` ints) is emitted bare,
# unchanged. Extend this set — do NOT widen it to "all keys" — when a new
# string-intended, numeric-looking field is added (ADR-0027: a new field left
# off the list re-exposes the type-leak bug; widening to all keys would quote
# dates and the null sentinel, which the resolver needs bare).
STRING_INTENDED_KEYS: frozenset[str] = frozenset(
    {"lifecycle_slug", "feature", "parent", "spec"}
)

# Canonical YAML null tokens. On an allowlisted key these stay bare so the
# resolver's null-fallback is preserved (a genuine string value ``"null"`` is
# not a real case for these keys, and ``update_item.py`` emits the literal
# ``"null"`` for a ``None`` field). The empty string is deliberately NOT here —
# it mis-resolves to null and MUST be quoted (``""``).
_YAML_NULL_TOKENS: frozenset[str] = frozenset({"null", "Null", "NULL", "~"})

# YAML 1.1 boolean tokens, including the short ``y``/``n`` variants that PyYAML's
# default resolver reads as plain strings. The spec requires these quoted on
# allowlisted keys; force-quoting is harmless (``"y"`` round-trips to ``"y"``)
# and defends against a stricter YAML 1.1 reader than PyYAML.
_YAML11_BOOL_TOKENS: frozenset[str] = frozenset(
    {
        "y", "Y", "n", "N",
        "yes", "Yes", "YES", "no", "No", "NO",
        "true", "True", "TRUE", "false", "False", "FALSE",
        "on", "On", "ON", "off", "Off", "OFF",
    }
)

# Single-char double-quoted escapes; other C0 control chars fall through to
# ``\xHH`` in ``_double_quote``.
_DQ_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\x00": "\\0",
}


def _double_quote(value: str) -> str:
    """Return *value* as an escaped YAML double-quoted scalar.

    The result round-trips through ``yaml.safe_load`` to the exact original
    string. Escapes ``"``, ``\\``, newlines, and control characters.
    """
    out = []
    for ch in value:
        esc = _DQ_ESCAPES.get(ch)
        if esc is not None:
            out.append(esc)
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\x{ord(ch):02x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _mis_resolves(value: str) -> bool:
    """True when bare *value* would not round-trip as the exact string *value*.

    Covers the YAML 1.1 ambiguous forms (int/float/bool/sexagesimal/hex/octal/
    ``.inf``/``.nan``/empty/leading-indicator/inline-``#``) by asking the actual
    reader (``yaml.safe_load``) whether the parse differs, or fails outright. The
    short ``y``/``n`` bool variants (which PyYAML reads as strings) are forced
    via ``_YAML11_BOOL_TOKENS``. Characters that cannot appear bare (``"``,
    ``\\``, control chars, newlines) always force quoting.
    """
    if value in _YAML11_BOOL_TOKENS:
        return True
    if any(ch in '"\\' or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        return True
    try:
        return yaml.safe_load(value) != value
    except yaml.YAMLError:
        return True


def quote_scalar(key: str, value: str) -> str:
    """Render *value* as the YAML scalar text to place after ``{key}: ``.

    Key-scoped: only keys in ``STRING_INTENDED_KEYS`` are quoted, and only when
    *value* would mis-resolve — except the ``None`` sentinel (``null``/``~``),
    which stays bare even on an allowlisted key. Keys outside the allowlist, and
    already-safe values, are returned unchanged (bare).

    *value* is the already-stringified scalar the caller would otherwise
    interpolate directly after ``{key}: `` (the ``None`` path arrives as the
    literal ``"null"``).
    """
    if key not in STRING_INTENDED_KEYS:
        return value
    if value in _YAML_NULL_TOKENS:
        return value
    if _mis_resolves(value):
        return _double_quote(value)
    return value
