"""Prior-cycle review archives: staged at `complete`, invisible to phase detection.

Pins spec #455 requirements 3 and 4 for the ``review-cycle-{N}.md`` archives the
review-brief verb writes at every rework dispatch.

* **Req 4** (``test_complete_*``) — ``stage_artifacts``'s explicit allowlist covers
  the archives, so a completing commit carries them. Asserted three ways against a
  real git fixture repo: the verb's self-reported ``staged_paths``, the live index
  (``git status --porcelain`` shows no untracked ``review-cycle-*.md``), and
  ``git log --name-only`` for the resulting commit — the spec's own acceptance
  wording. A no-archive control pins that the paths appear only when the files do.

* **Req 3** (``test_phase_*``) — the current cycle stays at ``review.md``, so adding
  archives beside it must not move the detected phase. Covered at both the
  ``detect_lifecycle_phase`` level and through the phase-emitting CLI, over the three
  states a lifecycle can actually be in while archives exist: ``implement-rework``
  (cycle-2 dispatch has copied cycle 1, the reviewer has not overwritten
  ``review.md`` yet), ``escalated:rework-cap:2`` (cycle 2 also came back
  CHANGES_REQUESTED), and ``complete`` (cycle 2 approved).

* **Capture rig** (``test_captures_*``) — the evidence side of the same staging
  engine. ``review.md`` and the scoped brief a rework cycle produces are archived
  under ``cortex/lifecycle/{slug}/captures/``, and the phase artifacts cite them by
  path; ``_capture_files`` is appended *outside* the per-phase branch in
  ``collect_paths``, so the claim these tests pin is that a capture reaches
  ``staged_paths`` at **every** phase the verb accepts, not just ``complete``. The
  nested-file and dot-entry cases pin the two enumeration rules the docstring
  states, and a no-captures control keeps the assertion discriminating.

**Memoization hazard, and how these tests defeat it.** ``detect_lifecycle_phase``
memoizes on ``(feature_dir_str, *five _stat_key tuples)``, and ``review.md`` is one of
those five (``common.py:484``). Writing ``review-cycle-1.md`` changes *none* of those
components, so a naive same-directory before/after comparison would be served from the
lru cache and pass without re-deriving anything. Two independent defeats are used:
the parametrized detector and CLI tests compare **two distinct directories** (distinct
``feature_dir_str`` ⇒ guaranteed cache miss), and
``test_phase_same_tree_rederives_after_cache_clear`` does the literal same-tree
before/after with an explicit ``cache_clear()`` plus a ``cache_info().misses``
assertion proving the second call actually recomputed. That test also asserts the
hazard itself — ``_stat_key(review.md)`` is byte-identical before and after the archive
lands — so the reason the clear is needed is pinned rather than assumed.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from cortex_command import common
from cortex_command.common import detect_lifecycle_phase
from cortex_command.lifecycle import resolve as resolve_mod
from cortex_command.lifecycle.stage_artifacts import stage

SLUG = "archived-feature"
LC = f"cortex/lifecycle/{SLUG}"

# The cached inner detector, exposed on the public API for introspection.
_INNER = detect_lifecycle_phase.__wrapped__


# ---------------------------------------------------------------------------
# Real-git harness (same shape as tests/test_stage_artifacts.py:76-107)
# ---------------------------------------------------------------------------


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "commit.gpgsign",
        "GIT_CONFIG_VALUE_0": "false",
        "GIT_CONFIG_KEY_1": "tag.gpgsign",
        "GIT_CONFIG_VALUE_1": "false",
    }
    env.pop("GIT_DIR", None)
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=check,
        capture_output=True,
        text=True,
        env=env,
    )


def _new_repo(root: Path) -> None:
    _git("init", "-b", "main", ".", cwd=root)
    _git("config", "core.hooksPath", "/dev/null", cwd=root)
    _git("config", "commit.gpgsign", "false", cwd=root)
    _git("config", "tag.gpgsign", "false", cwd=root)
    _git("config", "user.name", "Test", cwd=root)
    _git("config", "user.email", "test@example.com", cwd=root)


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _porcelain(root: Path, pathspec: str) -> list[str]:
    out = _git("status", "--porcelain", "--", pathspec, cwd=root).stdout
    return [line for line in out.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Content builders
# ---------------------------------------------------------------------------


def _review(verdict: str, cycle: int) -> str:
    return (
        f"# Review: {SLUG}\n\n## Verdict\n\n"
        f'```json\n{{"verdict": "{verdict}", "cycle": {cycle}, "issues": []}}\n```\n'
    )


def _events(review_verdicts: int) -> str:
    """A log with NO state-establishing machine row, so the phase resolves via
    the artifact fallback — the only path ``review.md`` participates in, and
    therefore the only one where an archive could plausibly perturb the answer."""
    rows = [{"event": "lifecycle_started", "feature": SLUG}]
    rows += [{"event": "review_verdict", "feature": SLUG}] * review_verdicts
    return "".join(json.dumps(r) + "\n" for r in rows)


def _write_lifecycle(
    root: Path,
    slug: str,
    *,
    verdict: str,
    review_verdicts: int,
    archives: int,
) -> Path:
    """Write a lifecycle tree at ``cortex/lifecycle/<slug>/`` and return its dir.

    ``archives`` prior-cycle files are written alongside ``review.md`` (never
    instead of it — the copy-not-move invariant requirement 1 pins).
    """
    lc = f"cortex/lifecycle/{slug}"
    _write(root, f"{lc}/research.md", "research\n")
    _write(root, f"{lc}/spec.md", "spec\n")
    _write(root, f"{lc}/plan.md", "- **Status**: [x] done\n")
    _write(root, f"{lc}/index.md", "index\n")
    _write(root, f"{lc}/review.md", _review(verdict, review_verdicts or 1))
    _write(root, f"{lc}/events.log", _events(review_verdicts))
    for n in range(1, archives + 1):
        _write(root, f"{lc}/review-cycle-{n}.md", _review("CHANGES_REQUESTED", n))
    return root / lc


# The three states a lifecycle can actually occupy while archives exist on disk.
# id -> (verdict in review.md, review_verdict row count, expected phase)
_PHASE_CASES = [
    ("implement-rework", "CHANGES_REQUESTED", 1, "implement-rework"),
    ("rework-cap", "CHANGES_REQUESTED", 2, "escalated:rework-cap:2"),
    ("complete", "APPROVED", 2, "complete"),
]


# ---------------------------------------------------------------------------
# Req 4 — archives are committed
# ---------------------------------------------------------------------------


def test_complete_stages_review_cycle_archives(tmp_path: Path) -> None:
    """`--phase complete` stages every archive, and the commit carries them."""
    root = tmp_path
    _new_repo(root)
    _write(root, "README.md", "base\n")
    _git("add", "README.md", cwd=root)
    _git("commit", "-m", "Initial commit", cwd=root)

    _write_lifecycle(root, SLUG, verdict="APPROVED", review_verdicts=2, archives=2)

    result = stage("complete", SLUG, root)

    # 1. The verb's self-report names both archives.
    for n in (1, 2):
        assert f"{LC}/review-cycle-{n}.md" in result["staged_paths"]
    # The copy-not-move invariant: review.md is staged alongside them.
    assert f"{LC}/review.md" in result["staged_paths"]
    assert result["signal"] == "staged"

    # 2. Spec acceptance: no untracked review-cycle-*.md remains.
    untracked = [
        line for line in _porcelain(root, f"{LC}/") if line.startswith("??")
    ]
    assert untracked == [], f"archives left untracked: {untracked}"

    # 3. Spec acceptance: git log --name-only for the completing commit lists them.
    _git("commit", "-m", "Complete the feature", cwd=root)
    committed = _git("log", "--name-only", "--format=", "-1", cwd=root).stdout.split()
    for n in (1, 2):
        assert f"{LC}/review-cycle-{n}.md" in committed


def test_complete_without_archives_names_none(tmp_path: Path) -> None:
    """Discriminating control: the archive paths appear only when the files do."""
    root = tmp_path
    _new_repo(root)
    _write(root, "README.md", "base\n")
    _git("add", "README.md", cwd=root)
    _git("commit", "-m", "Initial commit", cwd=root)

    _write_lifecycle(root, SLUG, verdict="APPROVED", review_verdicts=1, archives=0)

    result = stage("complete", SLUG, root)

    assert not [p for p in result["staged_paths"] if "review-cycle-" in p]
    assert f"{LC}/review.md" in result["staged_paths"]


# ---------------------------------------------------------------------------
# Capture rig — captures/ reaches staged_paths at every phase
# ---------------------------------------------------------------------------

# The phases ``--phase`` accepts. ``collect_paths`` appends ``_capture_files``
# after the per-phase branch, so all three must carry a capture.
_STAGING_PHASES = ["complete", "plan", "refine"]


def _repo_with_lifecycle(root: Path, **kwargs) -> None:
    """Init a repo with one committed file and an uncommitted lifecycle tree."""
    _new_repo(root)
    _write(root, "README.md", "base\n")
    _git("add", "README.md", cwd=root)
    _git("commit", "-m", "Initial commit", cwd=root)
    _write_lifecycle(root, SLUG, **kwargs)


@pytest.mark.parametrize("phase", _STAGING_PHASES)
def test_captures_reach_staged_paths(tmp_path: Path, phase: str) -> None:
    """A file under ``captures/`` is staged, at every phase the verb accepts.

    The evidence is what the phase's own prose cites by path, so a capture that
    does not stage leaves a committed artifact pointing at an uncommitted file.
    Asserted against a real git index — the verb's self-report and
    ``git status --porcelain`` must agree that nothing was left untracked.
    """
    root = tmp_path
    _repo_with_lifecycle(
        root, verdict="CHANGES_REQUESTED", review_verdicts=1, archives=1
    )
    capture = f"{LC}/captures/review-cycle-2-brief.md"
    _write(root, capture, "# Scoped rework brief\n")

    result = stage(phase, SLUG, root)

    assert capture in result["staged_paths"], result["staged_paths"]
    assert result["signal"] == "staged"
    # Scoped to captures/ — the non-capture allowlist differs per phase (``plan``
    # and ``refine`` stage no review.md), and that is not what this test pins.
    untracked = [
        line for line in _porcelain(root, f"{LC}/captures/") if line.startswith("??")
    ]
    assert untracked == [], f"capture left untracked: {untracked}"

    _git("commit", "-m", "Record the capture", cwd=root)
    committed = _git("log", "--name-only", "--format=", "-1", cwd=root).stdout.split()
    assert capture in committed


@pytest.mark.parametrize("phase", _STAGING_PHASES)
def test_captures_absent_stages_no_capture_path(tmp_path: Path, phase: str) -> None:
    """Discriminating control: no ``captures/`` tree, no capture path staged."""
    root = tmp_path
    _repo_with_lifecycle(
        root, verdict="CHANGES_REQUESTED", review_verdicts=1, archives=1
    )

    result = stage(phase, SLUG, root)

    assert not [p for p in result["staged_paths"] if "/captures/" in p]


def test_captures_recurse_but_skip_dot_entries(tmp_path: Path) -> None:
    """Nested captures stage; dot-entries at any level never do.

    Pins both enumeration rules ``_capture_files`` documents — the tree is walked
    with ``rglob`` so a manifest in a subdirectory is carried, while any
    dot-prefixed path component keeps local-only session markers untrackable.
    """
    root = tmp_path
    _repo_with_lifecycle(root, verdict="APPROVED", review_verdicts=2, archives=1)
    nested = f"{LC}/captures/cycle-2/review.md"
    _write(root, nested, "# Archived review\n")
    _write(root, f"{LC}/captures/.session-owner", "local-only\n")
    _write(root, f"{LC}/captures/.hidden/manifest.json", "{}\n")

    result = stage("complete", SLUG, root)

    assert nested in result["staged_paths"]
    assert not [p for p in result["staged_paths"] if "/." in p]


# ---------------------------------------------------------------------------
# Req 3 — archives do not move the detected phase
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case_id,verdict,verdicts,expected",
    _PHASE_CASES,
    ids=[c[0] for c in _PHASE_CASES],
)
def test_phase_invariant_to_archives(
    tmp_path: Path, case_id: str, verdict: str, verdicts: int, expected: str
) -> None:
    """Same tree content, with and without archives, resolves to the same phase.

    The two lifecycles live in **distinct directories**, so ``feature_dir_str``
    differs and the lru cache cannot serve the second call from the first.
    """
    bare = _write_lifecycle(
        tmp_path, "bare", verdict=verdict, review_verdicts=verdicts, archives=0
    )
    archived = _write_lifecycle(
        tmp_path, "archived", verdict=verdict, review_verdicts=verdicts, archives=2
    )

    without = detect_lifecycle_phase(bare)
    with_archives = detect_lifecycle_phase(archived)

    assert without["phase"] == expected
    # Full-dict equality: route, paused, checked, total and cycle must all hold.
    assert with_archives == without


@pytest.mark.parametrize(
    "case_id,verdict,verdicts,expected",
    _PHASE_CASES,
    ids=[c[0] for c in _PHASE_CASES],
)
def test_phase_invariant_through_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case_id: str,
    verdict: str,
    verdicts: int,
    expected: str,
) -> None:
    """The phase-emitting CLI (`cortex-lifecycle-resolve`) agrees, archives or not.

    NOTE: the spec's requirement-3 acceptance names ``cortex-lifecycle-state``,
    which emits ``{criticality, tier}`` and no phase at all — see this module's
    exit report. ``cortex-lifecycle-resolve`` is the CLI that surfaces the
    detected phase (``resolve.py:277-289``), so it is the one exercised here.
    """
    _write_lifecycle(
        tmp_path, "bare", verdict=verdict, review_verdicts=verdicts, archives=0
    )
    _write_lifecycle(
        tmp_path, "archived", verdict=verdict, review_verdicts=verdicts, archives=2
    )
    # Keep the invocation telemetry out of the real repo (it resolves its write
    # target from the git toplevel of the cwd, and no-ops without a session id).
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    monkeypatch.chdir(tmp_path)

    def _run(slug: str) -> dict:
        assert resolve_mod.main([slug]) == 0
        return json.loads(capsys.readouterr().out)

    without = _run("bare")
    with_archives = _run("archived")

    assert without["state"] == "resume"
    assert without["phase"] == expected
    for key in ("phase", "route", "paused", "checked", "total", "cycle"):
        assert with_archives[key] == without[key], key


def test_phase_same_tree_rederives_after_cache_clear(tmp_path: Path) -> None:
    """The literal before/after-an-archive-step comparison, on one directory.

    Guards the memoization trap head-on: the archive is asserted invisible to
    ``review.md``'s cache key, the cache is then cleared, and the post-archive
    call is asserted to have *missed* — so the equality below is a real
    re-derivation, not a replayed answer.
    """
    feature_dir = _write_lifecycle(
        tmp_path, SLUG, verdict="CHANGES_REQUESTED", review_verdicts=1, archives=0
    )

    before = detect_lifecycle_phase(feature_dir)
    assert before["phase"] == "implement-rework"

    key_before = common._stat_key(feature_dir / "review.md")
    (feature_dir / "review-cycle-1.md").write_text(_review("CHANGES_REQUESTED", 1))
    key_after = common._stat_key(feature_dir / "review.md")
    # The hazard itself: the archive perturbs no component of the cache key,
    # so a same-process re-call would otherwise be served from the cache.
    assert key_after == key_before

    _INNER.cache_clear()
    after = detect_lifecycle_phase(feature_dir)
    # Exactly one miss since the clear — the answer was genuinely recomputed.
    assert _INNER.cache_info().misses == 1
    assert _INNER.cache_info().hits == 0

    assert after == before
