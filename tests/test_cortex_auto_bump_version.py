"""Unit tests for ``bin/cortex-auto-bump-version`` (spec R20).

The acceptance criterion calls for ≥10 cases. The tests are split between:

  * Pure-logic tests against the helper's ``classify_messages``/``decide``
    functions — these execute fast and don't need a real git repo. They
    cover the marker-precedence matrix and the standalone-vs-prose regex
    contract.

  * Fixture-replay tests that spin up a temporary git repo, plant a tag and
    commit history, and exec the script via ``subprocess.run``. These
    exercise the actual ``git describe`` / ``git log --format=%B%x00``
    integration end-to-end (including the squash-merge body case).

Together the file declares 13 test functions, exceeding the spec's ≥10
"PASSED lines" floor.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "bin" / "cortex-auto-bump-version"


def _load_script_module():
    """Load the script as an importable module for direct function tests.

    The script lacks a ``.py`` extension (it's a deployed bin/ command), so
    we instantiate the source-file loader explicitly rather than relying on
    ``spec_from_file_location``'s extension-based suffix dispatch (which
    returns ``None`` for non-``.py`` paths).
    """
    loader = importlib.machinery.SourceFileLoader(
        "cortex_auto_bump_version", str(SCRIPT_PATH)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


MOD = _load_script_module()


# ---------------------------------------------------------------------------
# Pure-logic tests (classify_messages / decide / bump_tag)
# ---------------------------------------------------------------------------


def test_classify_no_markers_returns_patch():
    """No markers in any message → default patch bump."""
    assert MOD.classify_messages(["fix: typo", "docs: update"]) == "patch"


def test_classify_minor_marker_standalone_subject():
    """`[release-type: minor]` standalone in subject line picks minor."""
    msg = "[release-type: minor]\n\nbody text here"
    assert MOD.classify_messages([msg]) == "minor"


def test_classify_major_marker_standalone_in_body():
    """`[release-type: major]` standalone in body line picks major."""
    msg = "Refactor envelope schema\n\n[release-type: major]\n\nDetails…"
    assert MOD.classify_messages([msg]) == "major"


def test_classify_skip_marker_wins_over_major():
    """Skip precedence: explicit skip beats explicit major in same range."""
    msgs = [
        "Add feature X\n\n[release-type: major]",
        "Tweak skip-worthy doc\n\n[release-type: skip]",
    ]
    assert MOD.classify_messages(msgs) == "skip"


def test_classify_breaking_fallback_fires_major_without_explicit_marker():
    """BREAKING: standalone line in body triggers major when no marker set."""
    msg = "Restructure plugin loader\n\nBREAKING: removes legacy path"
    assert MOD.classify_messages([msg]) == "major"


def test_classify_breaking_change_form_also_fires_fallback():
    """`BREAKING CHANGE:` (with space) is accepted alongside `BREAKING:`."""
    msg = "Restructure plugin loader\n\nBREAKING CHANGE: removes legacy path"
    assert MOD.classify_messages([msg]) == "major"


def test_classify_prose_embedded_marker_does_not_fire():
    """Marker mentioned inline in prose must NOT trip the regex.

    The standalone-line contract is the load-bearing constraint — a commit
    discussing the marker convention in a sentence (rather than declaring
    one) must still default to patch.
    """
    msg = (
        "docs: explain the [release-type: major] convention\n\n"
        "Authors add a `[release-type: major]` line on its own to bump."
    )
    assert MOD.classify_messages([msg]) == "patch"


def test_classify_breaking_token_inside_prose_does_not_fire():
    """`BREAKING:` mentioned mid-sentence does NOT fire the fallback.

    The regex anchors at line-start (``(?im)^\\s*BREAKING…``), so a phrase
    like "discusses breaking: behavior" mid-line is ignored.
    """
    msg = "docs: clarify that breaking: changes need markers"
    assert MOD.classify_messages([msg]) == "patch"


def test_classify_mixed_minor_and_breaking_promotes_to_major():
    """Defense-in-depth: explicit minor + BREAKING: body → major (safety).

    BREAKING in a body carrying an explicit minor marker reads as the
    author misjudging severity; the fallback promotes to major.
    """
    msgs = ["feat: extend API\n\n[release-type: minor]\n\nBREAKING: drops X"]
    assert MOD.classify_messages(msgs) == "major"


def test_bump_tag_patch_increment():
    assert MOD.bump_tag("v1.0.2", "patch") == "v1.0.3"


def test_bump_tag_minor_zeroes_patch():
    assert MOD.bump_tag("v1.0.2", "minor") == "v1.1.0"


def test_bump_tag_major_zeroes_minor_and_patch():
    assert MOD.bump_tag("v1.0.2", "major") == "v2.0.0"


def test_decide_empty_messages_returns_no_bump():
    """HEAD == latest tag (no new commits) → ``no-bump\\n`` per spec (vi)."""
    assert MOD.decide("v1.0.2", [], "deadbeef") == "no-bump\n"


def test_decide_skip_marker_returns_no_bump():
    """Skip marker present → ``no-bump\\n`` per spec (vi)."""
    msgs = ["Release v1.0.2\n\n[release-type: skip]"]
    assert MOD.decide("v1.0.2", msgs, "deadbeef") == "no-bump\n"


def test_decide_no_tags_with_commits_emits_default_tag():
    """No tags but commits exist → ``v0.1.0\\n`` per spec (i) default."""
    msgs = ["Initial commit\n"]
    assert MOD.decide(None, msgs, "deadbeef") == "v0.1.0\n"


# ---------------------------------------------------------------------------
# Fixture-replay tests (real git repo, real subprocess invocation)
# ---------------------------------------------------------------------------


def _init_git_repo(tmp_path: Path) -> None:
    """Init a minimal git repo at ``tmp_path``. Quiet, no signing."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        # Defensively neuter any user-level config that might inject hooks
        # or signing.
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(tmp_path)],
        check=True, env=env,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "commit.gpgsign", "false"],
        check=True, env=env,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "tag.gpgsign", "false"],
        check=True, env=env,
    )


def _commit(tmp_path: Path, filename: str, message: str) -> str:
    """Make a commit with ``message`` (multi-line OK). Returns the sha."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    (tmp_path / filename).write_text(filename, encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", filename],
        check=True, env=env,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", message],
        check=True, env=env,
    )
    out = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True, env=env, capture_output=True, text=True,
    )
    return out.stdout.strip()


def _tag(tmp_path: Path, tag: str) -> None:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    subprocess.run(
        ["git", "-C", str(tmp_path), "tag", tag],
        check=True, env=env,
    )


def _run_script(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    """Run the helper script with cwd=tmp_path."""
    env = {
        **os.environ,
        # The cortex-log-invocation shim is fail-open; suppress its session
        # writes during tests by leaving LIFECYCLE_SESSION_ID unset.
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    env.pop("LIFECYCLE_SESSION_ID", None)
    return subprocess.run(
        [str(SCRIPT_PATH), *args],
        cwd=str(tmp_path), capture_output=True, text=True, env=env,
    )


def test_script_no_commits_since_tag_emits_no_bump(tmp_path: Path):
    """HEAD == latest-tag → no-bump (spec vi)."""
    _init_git_repo(tmp_path)
    _commit(tmp_path, "a.txt", "initial commit")
    _tag(tmp_path, "v1.0.2")
    result = _run_script(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "no-bump\n"


def test_script_squash_merge_body_marker_is_detected(tmp_path: Path):
    """Squash-merge simulation: marker lives in the merge commit's body.

    Mimics GitHub's squash-merge UX where per-commit markers are concatenated
    into the merge commit's body. Spec calls this out as the canonical
    R20-step-ii rationale for using --format=%B (full message) rather than
    --format=%s (subject-only).
    """
    _init_git_repo(tmp_path)
    _commit(tmp_path, "a.txt", "initial commit")
    _tag(tmp_path, "v1.0.2")
    # Squash-merge style: PR title as subject, per-commit subjects as body.
    msg = (
        "Add envelope schema (#213)\n"
        "\n"
        "* refactor envelope structure\n"
        "\n"
        "  [release-type: major]\n"
        "\n"
        "* update consumers\n"
    )
    _commit(tmp_path, "b.txt", msg)
    result = _run_script(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "v2.0.0\n"


def test_script_dry_run_produces_same_output(tmp_path: Path):
    """--dry-run is read-only with identical stdout to the default mode."""
    _init_git_repo(tmp_path)
    _commit(tmp_path, "a.txt", "initial commit")
    _tag(tmp_path, "v1.0.2")
    _commit(tmp_path, "b.txt", "fix: cosmetic typo")
    plain = _run_script(tmp_path)
    dry = _run_script(tmp_path, "--dry-run")
    assert plain.returncode == 0 and dry.returncode == 0
    assert plain.stdout == "v1.0.3\n"
    assert dry.stdout == plain.stdout


def test_script_default_patch_bump(tmp_path: Path):
    """Commits since tag with no markers → patch bump."""
    _init_git_repo(tmp_path)
    _commit(tmp_path, "a.txt", "initial commit")
    _tag(tmp_path, "v1.0.2")
    _commit(tmp_path, "b.txt", "fix: small bug")
    _commit(tmp_path, "c.txt", "docs: tweak phrasing")
    result = _run_script(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "v1.0.3\n"


def test_script_explicit_minor_marker_in_subject(tmp_path: Path):
    """`[release-type: minor]` standalone as commit subject → minor bump."""
    _init_git_repo(tmp_path)
    _commit(tmp_path, "a.txt", "initial commit")
    _tag(tmp_path, "v1.0.2")
    _commit(tmp_path, "b.txt", "[release-type: minor]")
    result = _run_script(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "v1.1.0\n"


def test_script_skip_marker_short_circuits_to_no_bump(tmp_path: Path):
    """Skip marker present in any commit since tag → no-bump."""
    _init_git_repo(tmp_path)
    _commit(tmp_path, "a.txt", "initial commit")
    _tag(tmp_path, "v1.0.2")
    _commit(
        tmp_path, "b.txt",
        "Release v1.0.2 follow-up\n\n[release-type: skip]\n",
    )
    result = _run_script(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "no-bump\n"


def test_script_prose_embedded_marker_does_not_fire(tmp_path: Path):
    """Marker mentioned in prose (not standalone) → patch default."""
    _init_git_repo(tmp_path)
    _commit(tmp_path, "a.txt", "initial commit")
    _tag(tmp_path, "v1.0.2")
    _commit(
        tmp_path, "b.txt",
        "docs: add note about [release-type: major] convention\n\n"
        "Maintainers add `[release-type: major]` lines to bump major.\n",
    )
    result = _run_script(tmp_path)
    assert result.returncode == 0, result.stderr
    # Patch bump, NOT major — the marker was prose-embedded, not standalone.
    assert result.stdout == "v1.0.3\n"
