"""R10 integration test: every ``lifecycle/<slug>`` citation resolves.

Walks every git-tracked ``*.md`` via ``git ls-files '*.md'`` (no filesystem
walk; no separate exclusion list), applies the five citation-form regexes
defined in ``lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/spec.md``
§"Slug-and-citation grammar", and asserts each extracted slug exists at
either ``lifecycle/<slug>/`` or ``lifecycle/archive/<slug>/``.

Coverage assertions guard against regex-bug false-passes:

  - ``total_resolved >= 50`` — repo currently has well above this count.
  - Each of the five forms has ``>= 1`` match.

A negative-case parametrized variant runs the same resolver over
``tests/fixtures/lifecycle_references/broken-citation.md`` and proves the
resolver detects the deliberately-broken citation. The main test skips
the fixture path so its deliberately-broken slug does not fail the run.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = "tests/fixtures/lifecycle_references/"

# Five citation-form regexes from spec §"Slug-and-citation grammar".
# Order matters when applied to a single span: more-specific forms must
# match before less-specific. Within this test each form is applied
# independently to count per-form occurrences.
SLUG_PATTERN = r"[a-z0-9][a-z0-9-]*"

FORM_REGEXES: dict[str, re.Pattern[str]] = {
    "slash-path": re.compile(
        rf"(?:^|[^A-Za-z0-9_/-])lifecycle/(?P<slug>{SLUG_PATTERN})(?:/[\w./-]+)?"
    ),
    "wikilink-with-path": re.compile(
        rf"\[\[lifecycle/(?P<slug>{SLUG_PATTERN})(?:/[^\]\|#]+)(?:#[^\]\|]+)?(?:\|[^\]]+)?\]\]"
    ),
    "wikilink-slug-only": re.compile(
        rf"\[\[lifecycle/(?P<slug>{SLUG_PATTERN})(?:#[^\]\|]+)?(?:\|[^\]]+)?\]\]"
    ),
    "wikilink-md-suffix": re.compile(
        rf"\[\[lifecycle/(?P<slug>{SLUG_PATTERN})\.md(?:#[^\]\|]+)?(?:\|[^\]]+)?\]\]"
    ),
}

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _slug_resolves(slug: str) -> bool:
    """Return True if a top-level or archived dir exists for ``slug``."""
    return (
        (REPO_ROOT / "lifecycle" / slug).is_dir()
        or (REPO_ROOT / "lifecycle" / "archive" / slug).is_dir()
    )


def _extract_lifecycle_slug_from_frontmatter(text: str, path: str) -> str | None:
    """Parse frontmatter and return ``lifecycle_slug`` value if a non-empty
    scalar string. Returns None for null/empty/absent. Raises with a
    ``malformed lifecycle_slug:`` message for list/non-string values."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    if "lifecycle_slug" not in fm:
        return None
    value = fm["lifecycle_slug"]
    if value is None:
        return None
    if isinstance(value, str):
        if value == "":
            return None
        return value
    raise AssertionError(f"malformed lifecycle_slug: {path} -> {value!r}")


def _extract_references(
    text: str, path: str
) -> tuple[list[tuple[str, str, int]], list[tuple[str, str, int]]]:
    """Return (resolved, broken) lists of (slug, form, line_no) tuples."""
    resolved: list[tuple[str, str, int]] = []
    broken: list[tuple[str, str, int]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for form, pattern in FORM_REGEXES.items():
            for match in pattern.finditer(line):
                slug = match.group("slug")
                if _slug_resolves(slug):
                    resolved.append((slug, form, line_no))
                else:
                    broken.append((slug, form, line_no))
    # Frontmatter lifecycle_slug field
    slug = _extract_lifecycle_slug_from_frontmatter(text, path)
    if slug is not None:
        # Find the line number of the lifecycle_slug field for diagnostics.
        line_no = next(
            (
                i
                for i, line in enumerate(text.splitlines(), start=1)
                if line.strip().startswith("lifecycle_slug:")
            ),
            0,
        )
        if _slug_resolves(slug):
            resolved.append((slug, "lifecycle_slug-frontmatter", line_no))
        else:
            broken.append((slug, "lifecycle_slug-frontmatter", line_no))
    return resolved, broken


def _git_tracked_md_files() -> list[str]:
    """Return git-tracked ``*.md`` paths relative to repo root."""
    result = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [p for p in result.stdout.splitlines() if p.strip()]


def test_every_lifecycle_reference_resolves() -> None:
    """Walk every git-tracked ``*.md`` and assert each ``lifecycle/<slug>``
    reference resolves to either ``lifecycle/<slug>/`` or
    ``lifecycle/archive/<slug>/``. Coverage gates: ``total_resolved >= 50``
    and ``>= 1`` match per form."""
    paths = _git_tracked_md_files()
    per_form: dict[str, int] = {form: 0 for form in FORM_REGEXES}
    per_form["lifecycle_slug-frontmatter"] = 0
    total_resolved = 0
    broken_all: list[tuple[str, str, str, int]] = []  # (path, slug, form, line)

    for path in paths:
        # Skip the negative-case fixture so its deliberately-broken slug
        # does not fail the main run; the parametrized variant tests it.
        if FIXTURE_DIR in path:
            continue
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        resolved, broken = _extract_references(text, path)
        for slug, form, _ in resolved:
            per_form[form] += 1
            total_resolved += 1
        for slug, form, line_no in broken:
            broken_all.append((path, slug, form, line_no))

    if broken_all:
        msg = "\n".join(
            f"  {path}:{line_no}:{slug} ({form})"
            for path, slug, form, line_no in broken_all
        )
        raise AssertionError(
            f"{len(broken_all)} unresolved lifecycle/<slug> citation(s):\n{msg}"
        )

    assert total_resolved >= 50, f"resolved only {total_resolved}"
    for form, count in per_form.items():
        assert count >= 1, f"no matches for form {form}"


def test_negative_case_fixture_detects_broken_citation() -> None:
    """Parametrized negative-case variant: run the resolver over the
    fixture and assert the deliberately-broken slug is detected."""
    fixture_path = REPO_ROOT / FIXTURE_DIR / "broken-citation.md"
    text = fixture_path.read_text(encoding="utf-8")
    resolved, broken = _extract_references(text, str(fixture_path))
    broken_slugs = {slug for slug, _, _ in broken}
    assert "this-slug-does-not-exist" in broken_slugs, (
        f"negative-case fixture failed to detect broken citation; "
        f"resolved={resolved} broken={broken}"
    )
