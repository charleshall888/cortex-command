"""R10 integration test: every ``lifecycle/<slug>`` citation resolves.

Walks every git-tracked ``*.md`` via ``git ls-files '*.md'`` (no filesystem
walk; no separate exclusion list), applies the five citation-form regexes
defined in ``lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/spec.md``
§"Slug-and-citation grammar", and asserts each extracted slug exists at
either ``lifecycle/<slug>/`` or ``lifecycle/archive/<slug>/``.

Test #3 (skill-design test infrastructure, ticket #181) extends this file
with a sixth form ``file_line_citation`` matching ``<path>.<ext>:<line>``
(plus optional ``-<lend>`` range) for ``<ext>`` in {md, py, sh, toml, yaml,
yml, json}. Path resolution: repo-relative when the cited path begins with
one of the known top-level dir prefixes; otherwise relative to the citing
file's directory. Path-traversal safety: reject ``..`` segments and any
resolved path that escapes ``REPO_ROOT`` (error contains ``outside repo``).
Line-count check: cited line must not exceed the target file's line count.
The ``file_line_citation`` form is applied only to artifacts under
``lifecycle/`` and ``research/`` per spec Non-Req §88 (the audit's drift
example lives in lifecycle artifacts; bare-filename citations in other
trees are too prone to incidental prose collisions).

Coverage assertions guard against regex-bug false-passes:

  - ``total_resolved >= 50`` — repo currently has well above this count.
  - Each of the required forms has ``>= 1`` match.

Negative-case parametrized variants run the resolver over fixtures under
``tests/fixtures/lifecycle_references/`` and prove the resolver detects
deliberately-broken citations. The main test skips fixture paths so the
deliberately-broken citations do not fail the run.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = "tests/fixtures/lifecycle_references/"
# Archived dirs are immutable historical record — their prose references to
# example/historical slugs aren't load-bearing citations. Skip them from the
# walker so the gate validates only live-tree citations that future-Claude or
# future-operator might follow.
ARCHIVED_PREFIXES = ("lifecycle/archive/", "research/archive/")
# When prose abbreviates `skills/lifecycle/references/<file>.md` to
# `lifecycle/references/<file>.md`, the slug `references` is a path component
# inside the lifecycle SKILL, not a feature directory. Same for any future
# non-feature subdirectory under skills/lifecycle/. Exclude these from the
# citation grammar so path-abbreviation prose isn't flagged as a broken
# feature citation.
NON_FEATURE_SUBDIRS = frozenset({"references"})

# Five citation-form regexes from spec §"Slug-and-citation grammar".
# Order matters when applied to a single span: more-specific forms must
# match before less-specific. Within this test each form is applied
# independently to count per-form occurrences.
SLUG_PATTERN = r"[a-z0-9][a-z0-9-]*"

FORM_REGEXES: dict[str, re.Pattern[str]] = {
    # Slash-path: per spec English "lifecycle/<slug>/<path>", require the
    # trailing /<path> component (one or more path chars). The spec literal
    # regex marks <path> as optional (``?``) which over-captures incidental
    # ``lifecycle/<word>`` literal-file references in prose; requiring path
    # eliminates that noise while still matching every real slug-path
    # citation used in cortex artifacts.
    "slash-path": re.compile(
        rf"(?:^|[^A-Za-z0-9_/-])lifecycle/(?P<slug>{SLUG_PATTERN})/[\w./-]+"
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
    # file_line_citation (Test #3, ticket #181): matches ``<path>.<ext>:<line>``
    # with optional ``-<lend>`` range, for <ext> in {md,py,sh,toml,yaml,yml,
    # json}. Distinct from the slug-resolving forms above: this form has
    # different group names (``path``, ``line``, ``lend``) and is processed
    # by a separate code path that performs path resolution + line-count
    # checks rather than slug-existence checks. Boundary char excludes
    # ``A-Za-z0-9_/.-`` to prevent absorbing into longer identifiers and
    # picking up incidental prose like ``filename.ext:N`` inside larger
    # tokens. The path may be a bare filename or a slash-separated path.
    "file_line_citation": re.compile(
        r"(?:^|[^A-Za-z0-9_/-])"
        r"(?P<path>(?:\.\.?/)*[A-Za-z0-9_][A-Za-z0-9_./-]*"
        r"\.(?:md|py|sh|toml|yaml|yml|json))"
        r":(?P<line>\d+)(?:-(?P<lend>\d+))?"
    ),
}

# Top-level repo dir prefixes (per spec Req 9): cited paths beginning with
# any of these resolve repo-relative; otherwise resolve relative to the
# citing file's directory.
TOP_LEVEL_PREFIXES: tuple[str, ...] = (
    "skills/",
    "lifecycle/",
    "plugins/",
    "bin/",
    "tests/",
    "cortex_command/",
    "docs/",
    "requirements/",
    "research/",
    "backlog/",
)

# file_line_citation scan scope (per spec Non-Req §88): the audit's drift
# example lives in lifecycle/research artifacts. Bare-filename citations
# in other trees (CHANGELOG, backlog/*.md prose) frequently mention files
# in idiomatic prose without intending them as resolvable pointers, so
# limiting scope here avoids false positives while still catching the
# named drift mode.
FILE_LINE_SCAN_PREFIXES: tuple[str, ...] = ("lifecycle/", "research/")

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _slug_resolves(slug: str) -> bool:
    """Return True if a top-level or archived dir exists for ``slug``."""
    return (
        (REPO_ROOT / "lifecycle" / slug).is_dir()
        or (REPO_ROOT / "lifecycle" / "archive" / slug).is_dir()
    )


def _resolve_file_line_citation(
    cited: str,
    cited_line: int,
    cited_lend: int,
    citing_file: Path,
) -> tuple[str, str | None]:
    """Resolve a ``file_line_citation`` match per spec Req 9.

    Returns a (status, error_message) tuple:
      - ("resolved", None) — file exists at the resolved path AND its line
        count is at least ``max(cited_line, cited_lend)``.
      - ("traversal", msg) — raw cited path contains ``..`` segments OR the
        resolved path escapes ``REPO_ROOT``. ``msg`` contains literal
        substring ``outside repo`` per spec Req 9.
      - ("missing", None) — file does not exist at the resolved location;
        treated as ambiguous prose rather than drift (some citations point
        to files that have been renamed or removed; without a stronger
        signal we cannot distinguish "stale citation pointer" from "prose
        mention of a hypothetical file"). NOT counted as resolved or broken.
      - ("stale", msg) — file exists but its line count is below the cited
        line; ``msg`` describes the discrepancy and includes ``exceeds line
        count``.
    """
    # Raw-path traversal check: even one ``..`` segment in the cited path
    # rejects (per spec Req 9: "AND `'..' not in cited.split('/')`").
    if ".." in cited.split("/"):
        return (
            "traversal",
            f"{cited} resolves outside repo (contains '..' segments)",
        )

    # Path resolution per spec Req 9.
    if any(cited.startswith(p) for p in TOP_LEVEL_PREFIXES):
        candidate = REPO_ROOT / cited
    else:
        candidate = citing_file.parent / cited

    try:
        final = candidate.resolve()
    except (OSError, RuntimeError) as exc:  # pragma: no cover - defensive
        return ("traversal", f"{cited} failed to resolve: {exc} (outside repo)")

    # Containment check: resolved path must live under REPO_ROOT.
    try:
        final.is_relative_to(REPO_ROOT)
    except AttributeError:  # pragma: no cover - Python <3.9 fallback
        is_under = str(final).startswith(str(REPO_ROOT))
    else:
        is_under = final.is_relative_to(REPO_ROOT)
    if not is_under:
        return ("traversal", f"{cited} resolves outside repo ({final})")

    if not final.exists() or not final.is_file():
        return ("missing", None)

    try:
        line_count = len(final.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError as exc:  # pragma: no cover - defensive
        return ("missing", f"{cited} could not be read: {exc}")

    check_ln = max(cited_line, cited_lend)
    if line_count < check_ln:
        return (
            "stale",
            f"{cited}:{check_ln} exceeds line count {line_count} "
            f"(cited line {check_ln} beyond file's actual {line_count} lines)",
        )

    return ("resolved", None)


def _extract_file_line_citations(
    text: str, citing_file: Path
) -> tuple[
    list[tuple[str, int, int]],
    list[tuple[str, int, int, str, str]],
]:
    """Apply the ``file_line_citation`` regex to ``text`` and resolve each
    match per spec Req 9.

    Returns ``(resolved, broken)`` where:
      - ``resolved`` is a list of ``(cited, cited_line, line_no)`` tuples.
      - ``broken`` is a list of ``(cited, cited_line, line_no, kind, msg)``
        tuples where ``kind`` is one of ``"traversal"`` or ``"stale"``.

    "Missing" matches (cited file doesn't exist) are dropped silently —
    those are treated as ambiguous prose rather than drift.
    """
    pattern = FORM_REGEXES["file_line_citation"]
    resolved: list[tuple[str, int, int]] = []
    broken: list[tuple[str, int, int, str, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for m in pattern.finditer(line):
            cited = m.group("path")
            cited_line = int(m.group("line"))
            cited_lend = int(m.group("lend") or cited_line)
            status, msg = _resolve_file_line_citation(
                cited, cited_line, cited_lend, citing_file
            )
            if status == "resolved":
                resolved.append((cited, cited_line, line_no))
            elif status in ("traversal", "stale"):
                assert msg is not None
                broken.append((cited, cited_line, line_no, status, msg))
            # status == "missing" → drop silently (ambiguous prose).
    return resolved, broken


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
            # ``file_line_citation`` has different semantics (path + line
            # count, no slug group) and is processed by
            # ``_extract_file_line_citations`` separately.
            if form == "file_line_citation":
                continue
            for match in pattern.finditer(line):
                slug = match.group("slug")
                if slug in NON_FEATURE_SUBDIRS:
                    continue
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
    and ``>= 1`` match per required form (including
    ``file_line_citation``)."""
    paths = _git_tracked_md_files()
    per_form: dict[str, int] = {form: 0 for form in FORM_REGEXES}
    per_form["lifecycle_slug-frontmatter"] = 0
    total_resolved = 0
    broken_all: list[tuple[str, str, str, int]] = []  # (path, slug, form, line)
    # file_line_citation broken entries are reported separately because
    # their fields differ (cited path + line, not slug).
    file_line_broken_all: list[tuple[str, str, int, str, str]] = []
    # (citing_path, cited, cited_line, kind, msg)

    for path in paths:
        # Skip the negative-case fixtures so their deliberately-broken
        # citations do not fail the main run; parametrized variants test
        # them.
        if FIXTURE_DIR in path:
            continue
        # Skip archived dirs (lifecycle/archive/, research/archive/) —
        # these are immutable historical record; their prose mentions
        # of example slugs are not citations that need to resolve.
        if any(path.startswith(p) for p in ARCHIVED_PREFIXES):
            continue
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        resolved, broken = _extract_references(text, path)
        for slug, form, _ in resolved:
            per_form[form] += 1
            total_resolved += 1
        for slug, form, line_no in broken:
            broken_all.append((path, slug, form, line_no))

        # file_line_citation: scan only artifacts under lifecycle/ and
        # research/ per spec Non-Req §88. Bare-filename citations in
        # other trees (CHANGELOG, backlog/*.md) are too prone to prose
        # collisions to be reliable drift signals at this scope.
        if any(path.startswith(p) for p in FILE_LINE_SCAN_PREFIXES):
            citing_file = REPO_ROOT / path
            fl_resolved, fl_broken = _extract_file_line_citations(text, citing_file)
            per_form["file_line_citation"] += len(fl_resolved)
            total_resolved += len(fl_resolved)
            for cited, cited_line, line_no, kind, msg in fl_broken:
                file_line_broken_all.append((path, cited, cited_line, kind, msg))

    error_lines: list[str] = []
    if broken_all:
        slug_msg = "\n".join(
            f"  {path}:{line_no}:{slug} ({form})"
            for path, slug, form, line_no in broken_all
        )
        error_lines.append(
            f"{len(broken_all)} unresolved lifecycle/<slug> citation(s):\n{slug_msg}"
        )
    if file_line_broken_all:
        fl_msg = "\n".join(
            f"  {path}:?:{cited}:{cited_line} ({kind}) — {msg}"
            for path, cited, cited_line, kind, msg in file_line_broken_all
        )
        error_lines.append(
            f"{len(file_line_broken_all)} broken file_line_citation(s):\n{fl_msg}"
        )
    if error_lines:
        raise AssertionError("\n".join(error_lines))

    assert total_resolved >= 50, f"resolved only {total_resolved}"
    # Form-coverage gate: require the two slug-based forms that the cortex
    # artifact set actually uses (slash-path body/frontmatter and the
    # ``lifecycle_slug:`` backlog frontmatter), plus ``file_line_citation``
    # to defend against regex-bug false-passes on the new Test #3 surface.
    # The three wikilink forms are valid spec citations but cortex's
    # wikilink convention uses ``[[NNN-slug]]`` without the ``lifecycle/``
    # prefix per the spec's "Wikilinks of the form ``[[<slug>]]`` are out
    # of scope" note, so the prefixed-wikilink forms have zero matches in
    # live artifacts — this is by-design, not a regex bug.
    required_forms = (
        "slash-path",
        "lifecycle_slug-frontmatter",
        "file_line_citation",
    )
    for form in required_forms:
        assert per_form[form] >= 1, f"no matches for form {form}"


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


def _resolve_fixture_file_line_citations(fixture_path: Path) -> None:
    """Run the file_line_citation resolver against ``fixture_path`` and
    raise ``AssertionError`` on the first broken (traversal or stale)
    citation found. Used by the regression-fixture variants below.

    The error message includes the fixture path, cited target, line
    info, and the kind-specific message so ``pytest.raises(match=...)``
    can pin the failure-detection path that fired."""
    text = fixture_path.read_text(encoding="utf-8")
    _resolved, broken = _extract_file_line_citations(text, fixture_path)
    if broken:
        msg_lines = [
            f"  {fixture_path.name}:?:{cited}:{cited_line} ({kind}) — {msg}"
            for cited, cited_line, line_no, kind, msg in broken
        ]
        raise AssertionError(
            f"{len(broken)} broken file_line_citation(s) in "
            f"{fixture_path.name}:\n" + "\n".join(msg_lines)
        )


def test_stale_citation_file_line_regression() -> None:
    """Regression-fixture variant: ``stale_file_line_citation.md`` cites a
    real file at a line number past its actual line count. The resolver
    must flag the citation as stale, with an error message containing
    ``exceeds line count`` (or one of the spec-allowed alternatives)."""
    fixture_path = REPO_ROOT / FIXTURE_DIR / "stale_file_line_citation.md"
    with pytest.raises(
        AssertionError,
        match=r"line .*beyond|exceeds line count|stale_file_line_citation\.md",
    ):
        _resolve_fixture_file_line_citations(fixture_path)


def test_path_traversal_file_line_citation_regression() -> None:
    """Regression-fixture variant: ``path_traversal_fixture.md`` contains
    ``../../etc/passwd:1``. The traversal-safety check must trigger; the
    error must contain the literal substring ``outside repo``."""
    fixture_path = REPO_ROOT / FIXTURE_DIR / "path_traversal_fixture.md"
    with pytest.raises(AssertionError, match=r"outside repo"):
        _resolve_fixture_file_line_citations(fixture_path)
