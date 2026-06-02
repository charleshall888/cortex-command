"""Shared glob-membership matcher for the lint checkers' ``--staged`` path.

This is the single canonical implementation of the ``**``=zero-or-more-segments
glob-membership decision used by every ``--staged`` corpus-membership test in
the pre-commit checker family (``parity_check``, ``prescriptive_prose``,
``bare_python_import``, ``contract``, and — via an inline parity-pinned copy —
the standalone ``bin/cortex-check-events-registry``).

The matcher treats each glob's ``**`` as *zero or more* path segments, so a
single ``dir/**/*.ext`` glob admits ``dir/foo.ext`` (depth-1, zero mid-dirs),
``dir/a/foo.ext`` (depth-2), and ``dir/a/b/foo.ext`` (depth-≥3) uniformly.
This is the behavior ``Path.match`` does NOT provide — it treats ``**`` as
exactly one segment on every supported Python — and the silent under-scan that
caused was the bug this module exists to kill.

**stdlib-only and Python-3.12-safe.** The translation is a hand-rolled ``re``
glob→regex; it deliberately uses neither the ``PurePath`` full-match method nor
the ``glob`` translate helper (both Python 3.13+ only), so it behaves
identically on 3.12 (the floor of ``requires-python``) and 3.13+. That ``glob``
translate helper (with ``recursive=True, include_hidden=True``) is a valid
behavioral *oracle* for tests on 3.13+, but it MUST NOT be called here at
runtime.

Input contract: callers pass a raw POSIX relative string from git
``--name-only`` (no leading ``./``, no trailing slash, forward slashes).
"""

from __future__ import annotations

import functools
import re
from collections.abc import Sequence


@functools.lru_cache(maxsize=None)
def _glob_to_regex(glob: str) -> re.Pattern[str]:
    """Translate one scan-scope glob to a compiled regex.

    ``**`` is treated as *zero or more* path segments, so ``skills/**/*.md``
    matches both ``skills/foo.md`` (depth-1, zero mid-dirs) and
    ``skills/a/b/foo.md`` (depth-≥3).  Safe on Python 3.12+: does not use
    ``PurePath`` pattern methods added in 3.13, and avoids the bare-``**``
    semantics of ``Path.match`` / ``root.glob`` which vary by version and treat
    ``**`` as exactly one segment on 3.12.

    Cached because the same handful of module-level glob constants are
    re-translated across every staged path the checkers test.
    """

    def _esc_segment(s: str) -> str:
        """Regex-escape a glob segment, then convert ``*`` → ``[^/]*``."""
        return re.escape(s).replace(r"\*", "[^/]*")

    if glob.endswith("/**"):
        # e.g. "hooks/**" → match anything (at any depth) under hooks/
        prefix = re.escape(glob[:-3])
        return re.compile(rf"^{prefix}/.+$")

    if "**" not in glob:
        # No wildcard — exact match with single-* support.
        return re.compile(rf"^{_esc_segment(glob)}$")

    # Glob contains **/ (zero-or-more path segments).
    # Split on "**/" to get anchored prefix/suffix pieces; each piece may
    # still contain single-* wildcards.
    segments = glob.split("**/")
    regex_parts = [_esc_segment(s) for s in segments]
    # "**/" between two parts → zero or more "<name>/" repetitions.
    pattern = "(?:[^/]+/)*".join(regex_parts)
    return re.compile(rf"^{pattern}$")


def matches_any_glob(rel_path: str, globs: Sequence[str]) -> bool:
    """Return True iff *rel_path* matches any glob in *globs*.

    *rel_path* is a repo-relative POSIX string; *globs* is a re-iterable
    sequence of scan-scope glob patterns (callers pass module-level
    ``tuple[str, ...]`` constants). A one-shot generator MUST NOT be passed —
    membership would silently return False on reuse; the ``Sequence`` annotation
    documents the re-iterability requirement.
    """
    return any(_glob_to_regex(glob).match(rel_path) for glob in globs)
