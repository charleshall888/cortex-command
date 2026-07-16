"""Positive-assertion pin: dormant lifecycle.config.md keys stay commented.

Rationale and inventory source of truth: ``cortex_command.lifecycle_config``
(backlog #372 dormant-config audit) — ``_DORMANT_KEYS`` (currently
``default-tier``, ``default-criticality``, ``skip-specify``, ``skip-review``)
names config keys documented in the shipped template but honored by no
consumer today. Task 1 commented all four out of every shipped copy of the
frontmatter; this module pins that state so it cannot silently regress —
by deletion, by an emptied frontmatter block, or by activation.

Why positive assertion and not intersection-emptiness: an emptiness-only
check (``set(parsed) & _DORMANT_KEYS == set()``) passes on a gutted
template. Verified fail-open without the extra clauses:
``_extract_frontmatter_text('---\\n---\\n')`` -> ``''`` ->
``yaml.safe_load('')`` -> ``None`` -> ``set(None or {}) & _DORMANT_KEYS``
-> ``set()`` -> passes even though the whole frontmatter block was deleted.
So ``_assert_dormant_keys_commented`` below asserts three clauses per
region:

  (a) the frontmatter region is non-empty;
  (b) no ``_DORMANT_KEYS`` member is a *live* (parsed) key;
  (c) every ``_DORMANT_KEYS`` member appears as a commented line in the
      region (a plain ``key not in parsed`` intersection check can't tell
      "correctly commented" apart from "deleted outright", and silently
      stops covering a key the moment it is activated — moved out of
      ``_DORMANT_KEYS`` into ``_LIVE_CODE_KEYS`` — which is exactly when
      ``lifecycle_config.py``'s "any activation must be loud and
      deliberate" contract (epic #371's activation guard) needs the test
      to fail loudly instead of quietly).

Note: ``_extract_frontmatter_text`` returns ``None`` when a file has no
frontmatter delimiters at all (as opposed to ``''`` for an emptied-but-
present block). ``assert region`` below treats both as failing clause (a),
so this predicate never reaches ``yaml.safe_load(None)`` in practice; that
call would raise ``AttributeError`` (a loud error, not a silent pass) if it
ever did, so the missing-delimiters edge needs no extra guard.

Sentinel design mirrors ``tests/test_lifecycle_config_parity.py:102-140``:
the four negative/positive cases below run the shared predicate over
synthetic in-memory frontmatter text and never mutate a shipped template.
"""

from __future__ import annotations

import pathlib
import re

import pytest
import yaml

from cortex_command.lifecycle_config import _DORMANT_KEYS, _extract_frontmatter_text

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# The three independently-shipped frontmatter copies (ADR-0017 parity set),
# plus the cortex-core plugin mirror. The mirror is included deliberately:
# the pre-commit drift hook that keeps it in sync is procedural and
# `--no-verify`-bypassable, not a content invariant, so it gets its own
# direct assertion rather than relying on the hook alone.
TEMPLATE_PATHS = (
    REPO_ROOT / "cortex_command" / "init" / "templates" / "cortex" / "lifecycle.config.md",
    REPO_ROOT / "skills" / "lifecycle" / "assets" / "lifecycle.config.md",
    REPO_ROOT / "plugins" / "cortex-core" / "skills" / "lifecycle" / "assets" / "lifecycle.config.md",
)


def _assert_dormant_keys_commented(region: str | None) -> None:
    """Pure predicate: raise AssertionError unless all three clauses hold.

    Shared by the path-parametrized test (real shipped templates) and the
    sentinel tests (synthetic in-memory frontmatter) so the sentinels
    exercise the exact production check, not a look-alike.
    """
    # (a) frontmatter region is non-empty (also covers a None region).
    assert region, "frontmatter region is empty or absent"

    # (b) no dormant key is live (parsed).
    parsed = yaml.safe_load(region)
    live_keys = set(parsed or {})
    live_dormant = live_keys & _DORMANT_KEYS
    assert not live_dormant, f"dormant key(s) shipped live: {sorted(live_dormant)}"

    # (c) every dormant key is present as a commented line.
    missing = [
        key
        for key in sorted(_DORMANT_KEYS)
        if not re.search(rf"^\s*#\s*{re.escape(key)}\s*:", region, re.MULTILINE)
    ]
    assert not missing, f"dormant key(s) missing a commented line: {missing}"


@pytest.mark.parametrize(
    "path",
    TEMPLATE_PATHS,
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_dormant_keys_stay_commented_in_shipped_template(path: pathlib.Path) -> None:
    """Every shipped lifecycle.config.md copy keeps all four dormant keys
    commented-out, and the frontmatter block itself is still present."""
    assert path.is_file(), f"template missing: {path}"
    region = _extract_frontmatter_text(path.read_text(encoding="utf-8"))
    _assert_dormant_keys_commented(region)


def test_sentinel_live_dormant_key_fails() -> None:
    """A dormant key shipped live (uncommented) fails clause (b)."""
    region = "skip-specify: true\nbranch-mode: trunk\n"
    with pytest.raises(AssertionError):
        _assert_dormant_keys_commented(region)


def test_sentinel_all_dormant_keys_commented_passes() -> None:
    """All four dormant keys present as commented lines, region non-empty:
    the predicate accepts it (nothing raised) — the positive control that
    proves the other three sentinels are failing for the right reason."""
    region = (
        "# default-tier:           # simple | complex\n"
        "# default-criticality:    # low | medium | high | critical\n"
        "# skip-specify:           # true | false\n"
        "# skip-review:            # true | false\n"
        "branch-mode: trunk\n"
    )
    _assert_dormant_keys_commented(region)  # must not raise


def test_sentinel_emptied_region_fails() -> None:
    """An emptied frontmatter region (block present, contents deleted)
    fails clause (a) — this is the case an intersection-only check would
    silently pass, per the module docstring's fail-open trace."""
    with pytest.raises(AssertionError):
        _assert_dormant_keys_commented("")


def test_sentinel_absent_dormant_key_fails() -> None:
    """A dormant key missing entirely (neither live nor commented) fails
    clause (c) — the load-bearing clause: an intersection-only pin cannot
    distinguish this from "correctly commented", and this is exactly the
    shape activation day takes (the key quietly stops appearing at all)."""
    region = (
        "# default-tier:           # simple | complex\n"
        "# default-criticality:    # low | medium | high | critical\n"
        "# skip-specify:           # true | false\n"
        # skip-review is absent entirely (not commented, not live).
        "branch-mode: trunk\n"
    )
    with pytest.raises(AssertionError):
        _assert_dormant_keys_commented(region)
