"""Release-artifact invariants for ``CLI_PIN[0]`` tag-lockstep + wheel version.

This test enforces two invariants on release artifacts (spec R24):

(a) **CLI_PIN[0] tag-lockstep**: at any annotated tag matching ``v*.*.*``
    whose tag-date is later than the ``v1.0.2`` tag-date, the
    ``CLI_PIN[0]`` literal at ``plugins/cortex-overnight/server.py``
    equals the tag string. This is the property the auto-release
    workflow (``.github/workflows/auto-release.yml``, spec R19) maintains
    going forward, and the CI lint (release.yml, spec R18) enforces as
    defense-in-depth.

(b) **Wheel version matches HEAD's git-describe**: when HEAD is exactly
    at a tag, ``uv build --wheel`` of HEAD produces a wheel whose
    package version matches ``git describe --tags --exact-match HEAD``
    (with the leading ``v`` stripped). Between tags the wheel carries a
    hatch-vcs dev-version that does not equal the trailing
    ``v<tag>-<N>-g<sha>`` form, so this branch only asserts at exact-tag
    commits and skips otherwise. The wheel build can be slow and is
    marked ``@pytest.mark.slow``; opt in via ``pytest --run-slow``.

----------------------------------------------------------------------
Historical exclusions (date-scoping rationale)
----------------------------------------------------------------------

The CLI_PIN[0] tag-lockstep invariant was VIOLATED at the following
four historical tags, which predate the auto-release workflow that
enforces it:

    v0.1.0    — CLI_PIN[0] was "v0.1.0" but the propagation rule was
                not yet codified.
    v1.0.0    — CLI_PIN[0] did not propagate from the tag.
    v1.0.1    — CLI_PIN[0] did not propagate from the tag.
    v1.0.2    — CLI_PIN[0] did not propagate from the tag (the gap-A
                3-for-3 manual-step failure documented in spec §A).

The invariant only applies to tags created AFTER v1.0.2, when the
auto-release workflow + CI lint defense-in-depth pair land. We scope
by tagger-date strictly greater than ``v1.0.2``'s tagger-date rather
than by a hardcoded exclusion list so that test maintenance does not
have to track each historical violator individually — the date-window
captures the regime change cleanly.

Cross-refs: spec §R24, §R18 (CI lint), §R19 (auto-release workflow).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_PY_RELATIVE = "plugins/cortex-overnight/server.py"

#: The four historical tags that violated the CLI_PIN[0] tag-lockstep
#: invariant. These are documented as the rationale for date-scoping the
#: tag-walk in part (a); the test does not exclude them by name (the
#: date filter handles them implicitly), but their identities are
#: enumerated here so the rationale is auditable from the source.
#:
#: Spec acceptance R24 requires this file to mention all four tag
#: strings; the variable below carries them.
HISTORICAL_VIOLATING_TAGS = ("v0.1.0", "v1.0.0", "v1.0.1", "v1.0.2")

#: The boundary tag whose tag-date defines the lower bound of the
#: invariant window. Tags with ``taggerdate > tagger-date(BOUNDARY_TAG)``
#: are subject to the CLI_PIN[0] tag-lockstep invariant.
BOUNDARY_TAG = "v1.0.2"

#: Regex matching ``vX.Y.Z`` tags (the release-tag shape).
_TAG_SHAPE = re.compile(r"^v\d+\.\d+\.\d+$")

#: Regex matching the ``CLI_PIN`` declaration's first element. Format-
#: tolerant: handles single-/double-quoted strings and whitespace
#: variations. Pattern-anchored on ``^CLI_PIN\s*=\s*\(`` so a non-line-
#: anchored search works on either single- or multi-line tuple forms.
_CLI_PIN_RE = re.compile(
    r"""^CLI_PIN\s*=\s*\(\s*['"](?P<tag>v\d+\.\d+\.\d+)['"]""",
    re.MULTILINE,
)


def _run_git(*args: str) -> str:
    """Run ``git <args>`` from the repo root and return stripped stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _tagger_date_unix(tag: str) -> int:
    """Return the tagger-date of an annotated tag as a unix timestamp."""
    out = _run_git("for-each-ref", "--format=%(taggerdate:unix)", f"refs/tags/{tag}")
    if not out:
        pytest.skip(f"tag {tag!r} not present in this clone — cannot scope invariant")
    return int(out)


def _post_boundary_tags() -> list[tuple[str, int]]:
    """List ``(tag, taggerdate_unix)`` for tags later than the boundary tag.

    Iterates via ``git for-each-ref`` (single git invocation, CI-friendly,
    no network). Filters by tag-shape ``vX.Y.Z`` AND tag-date strictly
    greater than ``BOUNDARY_TAG``'s tag-date.
    """
    boundary_unix = _tagger_date_unix(BOUNDARY_TAG)
    raw = _run_git(
        "for-each-ref",
        "--format=%(refname:short) %(taggerdate:unix)",
        "refs/tags/v*",
    )
    results: list[tuple[str, int]] = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        tag, date_str = parts
        if not _TAG_SHAPE.match(tag):
            continue
        if not date_str.isdigit():
            continue
        ts = int(date_str)
        if ts > boundary_unix:
            results.append((tag, ts))
    return results


def _cli_pin_at_tag(tag: str) -> str:
    """Read ``CLI_PIN[0]`` from ``server.py`` at the given tag.

    Uses ``git show <tag>:<path>`` so the working tree is not touched.
    Returns the matched tag string. Fails the test loudly on 0-or-≥2
    matches in the file at that revision (the same fail-loud contract
    as ``bin/cortex-rewrite-cli-pin``, spec R19.5).
    """
    blob = _run_git("show", f"{tag}:{SERVER_PY_RELATIVE}")
    matches = _CLI_PIN_RE.findall(blob)
    assert len(matches) == 1, (
        f"expected exactly one CLI_PIN literal in {SERVER_PY_RELATIVE} at "
        f"tag {tag!r}, found {len(matches)}: {matches!r}"
    )
    return matches[0]


def test_cli_pin_tag_lockstep_at_post_boundary_tags() -> None:
    """Part (a): CLI_PIN[0] equals the tag string at every post-boundary tag.

    Walks every annotated ``vX.Y.Z`` tag whose tagger-date is strictly
    greater than ``BOUNDARY_TAG``'s tagger-date, reads the ``CLI_PIN[0]``
    literal at that tag's tree, and asserts it equals the tag string.

    When no post-boundary tags exist (the state immediately after this
    test lands but before the first v2.0.0 release), the test passes
    trivially — the invariant has no in-window subjects yet, and the
    auto-release workflow will create the first one.
    """
    post_boundary = _post_boundary_tags()
    violations: list[tuple[str, str]] = []
    for tag, _ts in post_boundary:
        pinned = _cli_pin_at_tag(tag)
        if pinned != tag:
            violations.append((tag, pinned))
    assert not violations, (
        "CLI_PIN[0] drift at post-boundary tags (spec R24, R18): "
        + ", ".join(f"{tag} pins {pinned!r}" for tag, pinned in violations)
    )


def test_historical_violating_tags_are_excluded_by_date_window() -> None:
    """Sanity-check that the date-window excludes the four historical violators.

    Defensive check that the date-scoping logic is correctly bounded:
    each of the four documented historical violators
    (``v0.1.0``, ``v1.0.0``, ``v1.0.1``, ``v1.0.2``) must NOT appear in
    the post-boundary list. If this assertion ever flips, the scoping
    is wrong and part (a) above would start failing on grandfathered
    state.
    """
    post_boundary_tags = {tag for tag, _ts in _post_boundary_tags()}
    grandfathered = set(HISTORICAL_VIOLATING_TAGS) & post_boundary_tags
    assert not grandfathered, (
        f"historical violating tags leaked past the date-window: {grandfathered!r}; "
        f"the boundary {BOUNDARY_TAG!r} should exclude all of "
        f"{HISTORICAL_VIOLATING_TAGS!r}"
    )


@pytest.mark.slow
def test_wheel_package_version_matches_git_describe(tmp_path: Path) -> None:
    """Part (b): wheel's package version matches ``git describe`` at HEAD.

    Builds a wheel from HEAD via ``uv build --wheel`` into ``tmp_path``
    and asserts the wheel filename's version segment matches
    ``git describe --tags --exact-match HEAD`` (with the leading ``v``
    stripped).

    Skipped when HEAD is not at an exact tag, because hatch-vcs emits a
    dev-version (e.g. ``1.0.3.dev184``) between tags that does not equal
    the trailing ``v<tag>-<N>-g<sha>`` form of ``git describe``.

    Marked ``@pytest.mark.slow`` because ``uv build --wheel`` runs the
    full hatch build pipeline (typically 30-90 seconds). Opt in via
    ``pytest --run-slow`` or ``just test -- --run-slow``. Manual
    verification path when the slow marker is skipped:

        $ uv build --wheel
        $ ls dist/*.whl  # filename's version segment must match
        $ git describe --tags --exact-match HEAD  # with 'v' stripped
    """
    exact_tag_result = subprocess.run(
        ["git", "describe", "--tags", "--exact-match", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if exact_tag_result.returncode != 0:
        pytest.skip(
            "HEAD is not at an exact tag; hatch-vcs dev-versions do not "
            "equal git-describe's v<tag>-<N>-g<sha> form. Skipping per R24 "
            "scoping; the invariant applies at release-tag commits only."
        )
    exact_tag = exact_tag_result.stdout.strip()
    expected_version = exact_tag.removeprefix("v")

    out_dir = tmp_path / "dist"
    build_result = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert build_result.returncode == 0, (
        f"uv build --wheel failed:\nstdout:\n{build_result.stdout}\n"
        f"stderr:\n{build_result.stderr}"
    )
    wheels = sorted(out_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, found {wheels!r}"
    # Wheel filenames are `<name>-<version>-<python>-<abi>-<platform>.whl`.
    wheel_name = wheels[0].name
    parts = wheel_name.split("-")
    assert len(parts) >= 2, f"unexpected wheel filename shape: {wheel_name!r}"
    package_version = parts[1]
    assert package_version == expected_version, (
        f"wheel package version {package_version!r} does not match "
        f"git describe {exact_tag!r} (stripped: {expected_version!r}); "
        f"hatch-vcs versioning is misconfigured or the tag is not "
        f"reachable from HEAD"
    )
