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
