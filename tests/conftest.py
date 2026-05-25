from __future__ import annotations

import hashlib
import pathlib

import pytest
import yaml


def pytest_addoption(parser):
    parser.addoption("--run-slow", action="store_true", default=False, help="Run tests marked @pytest.mark.slow that invoke live models")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-slow"):
        return
    skip_slow = pytest.mark.skip(reason="opt-in via --run-slow")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)


def repo_root() -> pathlib.Path:
    """Return the cortex-command repository root (parent of ``tests/``)."""
    return pathlib.Path(__file__).resolve().parent.parent


def enumerate_skills(
    root: pathlib.Path,
    glob_pattern: str,
    dedupe_by_content: bool = False,
) -> list[pathlib.Path]:
    """Enumerate SKILL.md paths under ``root`` matching ``glob_pattern``.

    Always deduplicates by ``Path.resolve()`` for symlink safety. When
    ``dedupe_by_content`` is True, additionally deduplicates byte-identical
    files via SHA-256 of their bytes — needed for plugin mirrors that are
    regular-file copies of canonical SKILL.md sources.
    """
    seen_paths: set[pathlib.Path] = set()
    results: list[pathlib.Path] = []
    for path in root.glob(glob_pattern):
        resolved = path.resolve()
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        results.append(path)

    if dedupe_by_content:
        seen_hashes: set[str] = set()
        deduped: list[pathlib.Path] = []
        for path in results:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            deduped.append(path)
        results = deduped

    return sorted(results)


def enumerate_canonical_skills() -> list[pathlib.Path]:
    """Enumerate canonical ``skills/<name>/SKILL.md`` files."""
    return enumerate_skills(repo_root() / "skills", "*/SKILL.md")


def enumerate_plugin_skills() -> list[pathlib.Path]:
    """Enumerate ``plugins/<plugin>/skills/<name>/SKILL.md`` files.

    Byte-identical mirrors of canonical SKILL.md (e.g. the cortex-core
    plugin's regular-file copies) are deduplicated by content hash so
    cap-breach failures fan out to a single message rather than two.
    """
    return enumerate_skills(
        repo_root() / "plugins",
        "*/skills/*/SKILL.md",
        dedupe_by_content=True,
    )


# ---------------------------------------------------------------------------
# Shared backlog-resolution corpus + helper
#
# Promoted from tests/test_resolve_backlog_item.py (Task 5,
# unified-backlog-lifecycle-slug-resolver-extend) so the new
# tests/test_update_item_resolution.py (Task 7) can import the same
# inputs and the same minimal-item builder without copy-paste drift.
#
# Promotion is verbatim — no entries are dropped or rewritten. The
# helper that was named `_make_item` is exposed publicly as `make_item`
# (no leading underscore) so cross-file imports are idiomatic.
# ---------------------------------------------------------------------------


BACKLOG_RESOLUTION_CORPUS: list[str] = [
    # --- Numeric IDs (unpadded) ---
    "1",    # item 001: Fix overnight watchdog to kill entire process group on stall
    "6",    # item 006: Make `just setup` additive by default
    "176",  # item 176: this feature ticket (Lifecycle adopts cortex-resolve-backlog-item)
    # --- Numeric IDs (zero-padded) ---
    "006",  # zero-padded: resolves same as "6" via int() comparison
    "027",  # item 027: Fix next_question_id() race condition in deferral.py
    "082",  # item 082: Adapt harness to Opus 4.7 (prompt delta + capability adoption)
    # --- Kebab slugs ---
    "make-just-setup-additive",  # exact kebab stem of item 006
    "fix-overnight-watchdog-to-kill-entire-process-group-on-stall",  # full kebab item 001
    # --- Title fuzzy matches ---
    "overnight watchdog",           # matches item 001 via title phrase
    "additive by default",          # matches item 006 via title phrase
    # --- Uppercase inputs ---
    "WATCHDOG",   # case-insensitive match → item 001 (Predicate A fires via lower())
    "OVERNIGHT",  # ambiguous — multiple items contain 'overnight' (exit 2)
    "CLAUDE",     # ambiguous — multiple items reference CLAUDE (exit 2)
    # --- Predicate-A candidates (punctuation/special chars in titles) ---
    "`just setup`",     # Pred-A candidate 1: backtick — item 006
    "next_question_id()",  # Pred-A candidate 2: parens + underscore — item 027
    "runner.pid",          # Pred-A candidate 3: dot identifier — item 149
    # --- Ambiguous-multi inputs (exit 2) ---
    "fix",       # matches dozens of 'fix' items (ambiguous)
    "add",       # matches dozens of 'add' items (ambiguous)
    "overnight", # matches many overnight-related items (ambiguous)
    # --- No-match inputs (exit 3) ---
    "xyzzy-nonexistent-99999",  # no item with this pattern
    "quantum-flux-capacitor",   # no item with this pattern
    # --- Empty-after-slugify (exit 64) ---
    "!!!",  # all special chars → slugify gives "" → exit 64
]


@pytest.fixture
def backlog_resolution_corpus() -> list[str]:
    """Pytest fixture re-export of ``BACKLOG_RESOLUTION_CORPUS``.

    Tests may either import the module-level constant directly or pull it in
    as a fixture argument; both surface the same list object.
    """
    return BACKLOG_RESOLUTION_CORPUS


def make_item(
    backlog_dir: pathlib.Path,
    filename: str,
    title: str,
    extra: str = "",
) -> pathlib.Path:
    """Write a minimal backlog item under ``backlog_dir`` and return its Path.

    Promoted from ``tests/test_resolve_backlog_item.py`` (Task 5) so the new
    ``tests/test_update_item_resolution.py`` (Task 7) can build fixture items
    using the same helper. Verbatim behavior — frontmatter is a single
    ``title:`` line plus the caller-supplied ``extra`` lines.
    """
    path = backlog_dir / filename
    frontmatter = f"---\ntitle: {title!r}\n{extra}---\n"
    path.write_text(frontmatter, encoding="utf-8")
    return path


def parse_skill_frontmatter(skill_path: pathlib.Path) -> dict:
    """Parse the ``---``-delimited YAML frontmatter at the top of a SKILL.md.

    Returns ``{}`` if the file has no frontmatter block. Uses stdlib-style
    ``yaml.safe_load`` (PyYAML; already a project dependency for tests).
    """
    text = skill_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    # Split on the leading delimiter, then find the closing delimiter.
    # Lines after the first --- up to the next --- form the YAML block.
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    closing_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            closing_idx = idx
            break
    if closing_idx is None:
        return {}
    yaml_block = "\n".join(lines[1:closing_idx])
    parsed = yaml.safe_load(yaml_block)
    if not isinstance(parsed, dict):
        return {}
    return parsed
