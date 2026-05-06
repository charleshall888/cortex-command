"""Dual-source byte-parity pytest with sentinel-mutation gate (spec R7).

Defense-in-depth check that the canonical ``skills/<name>/...`` files and their
plugin-tree mirrors under ``plugins/<plugin>/skills/<name>/...`` remain byte-
identical. Catches mutations of either side that bypass the pre-commit Phase 4
drift check (e.g. via ``--no-verify``).

The ``PLUGINS`` constant below MUST stay aligned with the ``SKILLS=(...)``
arrays in the ``justfile`` ``build-plugin`` recipe (``grep -n 'SKILLS=(' justfile``
to locate them). If the lists drift, the per-plugin file counts will diverge
from the recipe's actual output and parity will silently break for the
unlisted skills.

Discovery:
    1. Glob ``skills/*/SKILL.md``, ``skills/*/references/*.md``, and
       ``skills/*/assets/*.md`` from the repo root.
    2. For each canonical path, route it to the plugin whose SKILLS tuple
       contains the second path component (the skill name). Files whose skill
       name is not in any SKILLS tuple produce no test (defensive — no
       orphans exist in the current tree).
    3. Mirror path is ``plugins/<plugin>/<canonical_path>``.

Two collected test groups:
    - ``test_dual_source_byte_parity`` — one parametrized case per
      (plugin, canonical) pair; reads both files via ``Path.read_bytes()`` and
      calls the pure ``assert_byte_parity`` helper.
    - ``test_assert_pytest_fails_on_mutation`` — sentinel that picks the first
      sorted pair, mutates the mirror bytes IN MEMORY (no filesystem write),
      and asserts ``assert_byte_parity`` raises ``AssertionError``. This proves
      the parity helper actually fails on mismatch on every run, with no
      crash-safety concerns since nothing on disk changes.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent

# Keep aligned with justfile `build-plugin` recipe SKILLS=(...) arrays.
# Resolve via: grep -n "SKILLS=(" justfile
PLUGINS: dict[str, tuple[str, ...]] = {
    "cortex-core": (
        "commit",
        "pr",
        "lifecycle",
        "backlog",
        "requirements",
        "research",
        "discovery",
        "refine",
        "dev",
        "diagnose",
        "critical-review",
    ),
    "cortex-overnight": (
        "overnight",
        "morning-review",
    ),
}


def assert_byte_parity(canonical_bytes: bytes, mirror_bytes: bytes) -> None:
    """Pure helper: raise AssertionError if the two byte strings differ.

    No I/O. The file-pair test reads files into bytes and calls this; the
    sentinel mutates bytes in memory and calls this. Keeping the comparison
    in a pure function is what makes the sentinel crash-safe.
    """
    if canonical_bytes != mirror_bytes:
        raise AssertionError(
            f"byte-parity mismatch: canonical={len(canonical_bytes)} bytes, "
            f"mirror={len(mirror_bytes)} bytes"
        )


def _discover_pairs() -> list[tuple[str, Path, Path]]:
    """Return sorted list of (plugin, canonical_path, mirror_path) tuples."""
    skill_to_plugin: dict[str, str] = {}
    for plugin, skills in PLUGINS.items():
        for skill in skills:
            skill_to_plugin[skill] = plugin

    skills_dir = REPO_ROOT / "skills"
    canonical_paths: list[Path] = []
    canonical_paths.extend(skills_dir.glob("*/SKILL.md"))
    canonical_paths.extend(skills_dir.glob("*/references/*.md"))
    canonical_paths.extend(skills_dir.glob("*/assets/*.md"))

    pairs: list[tuple[str, Path, Path]] = []
    for canonical in canonical_paths:
        # canonical is .../skills/<skill>/...
        rel = canonical.relative_to(REPO_ROOT)
        skill_name = rel.parts[1]
        plugin = skill_to_plugin.get(skill_name)
        if plugin is None:
            # Defensive: skill not in any plugin's SKILLS array.
            continue
        mirror = REPO_ROOT / "plugins" / plugin / rel
        pairs.append((plugin, canonical, mirror))

    pairs.sort(key=lambda t: (t[0], str(t[1])))
    return pairs


_PAIRS: list[tuple[str, Path, Path]] = _discover_pairs()


@pytest.mark.parametrize(
    ("plugin", "canonical", "mirror"),
    _PAIRS,
    ids=[f"{plugin}::{canonical.relative_to(REPO_ROOT)}" for plugin, canonical, mirror in _PAIRS],
)
def test_dual_source_byte_parity(plugin: str, canonical: Path, mirror: Path) -> None:
    assert canonical.is_file(), f"canonical missing: {canonical}"
    assert mirror.is_file(), f"mirror missing: {mirror}"
    canonical_bytes = canonical.read_bytes()
    mirror_bytes = mirror.read_bytes()
    assert_byte_parity(canonical_bytes, mirror_bytes)


def test_assert_pytest_fails_on_mutation() -> None:
    """Sentinel-mutation gate (spec R7c): prove parity helper fails on mismatch.

    Picks the first sorted (plugin, canonical, mirror) pair, mutates the
    mirror bytes in memory by appending one byte, and asserts that
    ``assert_byte_parity`` raises ``AssertionError``. No filesystem writes —
    the sentinel is crash-safe by construction.
    """
    assert _PAIRS, "no dual-source pairs discovered; cannot run sentinel"
    _plugin, canonical, mirror = _PAIRS[0]
    canonical_bytes = canonical.read_bytes()
    mirror_bytes = mirror.read_bytes()
    mutated_mirror_bytes = mirror_bytes + b"\x00"
    with pytest.raises(AssertionError):
        assert_byte_parity(canonical_bytes, mutated_mirror_bytes)
