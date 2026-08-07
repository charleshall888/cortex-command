"""CLI-layer tests for cortex_command.lifecycle.review_brief.

Pins requirements 1, 2, 5, 6 and 19 of
``cortex/lifecycle/a-rework-re-review-re-reads/spec.md`` — the archive step, the
mode discriminant, and the fail-open contract. The pure builder layer is pinned
elsewhere; everything here goes through ``main()``.

Each test builds a throwaway project root with a real ``git init`` tree, because
the verb shells out to ``git rev-parse`` / ``git diff`` and resolves its project
root by walking up from the CWD. Nothing touches the repo's own ``cortex/``.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from cortex_command import common
from cortex_command.lifecycle import review_brief
from cortex_command.lifecycle.counters import count_rework_cycles


# --- harness ----------------------------------------------------------------

# Isolate the fixture repo from the developer's global/system gitconfig (a
# global ``core.hooksPath`` would otherwise fire this repo's hooks in tmp_path).
_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "HOME": "/nonexistent-fixture-home",
    "PATH": "/usr/bin:/bin:/usr/local/bin",
}


def _git(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        env=_GIT_ENV,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A resolved project root: a git repo with one commit and a ``cortex/`` dir."""
    root = (tmp_path / "proj").resolve()
    (root / "cortex" / "lifecycle").mkdir(parents=True)
    _git(["init", "-b", "main"], root)
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    _git(["add", "README.md"], root)
    _git(["commit", "-m", "Seed"], root)
    return root


def _head(root: Path) -> str:
    return _git(["rev-parse", "HEAD"], root)


def _verdict_row(slug: str, verdict: str = "CHANGES_REQUESTED") -> dict:
    return {
        "ts": "2026-08-07T00:00:00Z",
        "event": "review_verdict",
        "feature": slug,
        "verdict": verdict,
    }


def _dispatched_row(slug: str, cycle: int, sha: str) -> dict:
    return {
        "ts": "2026-08-07T00:00:00Z",
        "event": "review_dispatched",
        "feature": slug,
        "cycle": cycle,
        "mode": "full",
        "baseline_sha": sha,
    }


def _review_text(issues, *, carried=(), cycle: int = 1) -> str:
    """A review artifact carrying a well-formed fenced Verdict block."""
    lines = [f"# Review — cycle {cycle}", ""]
    for name in carried:
        lines += [
            f"### Requirement: {name}",
            "",
            f"PASS — carried forward from cycle {cycle - 1}; holds while the loader is unchanged",
            "",
        ]
    lines += [
        "```json",
        json.dumps(
            {
                "verdict": "CHANGES_REQUESTED",
                "cycle": cycle,
                "issues": list(issues),
                "requirements_drift": "none",
            },
            indent=2,
        ),
        "```",
        "",
    ]
    return "\n".join(lines)


def _make_lifecycle(root: Path, slug: str, *, rows=(), review=None, files=None) -> Path:
    d = root / "cortex" / "lifecycle" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "events.log").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    if review is not None:
        (d / "review.md").write_text(review, encoding="utf-8")
    for name, text in (files or {}).items():
        (d / name).write_text(text, encoding="utf-8")
    return d


def _run(root: Path, slug: str, monkeypatch, capsys):
    """Invoke the verb against *root*'s temp lifecycle tree; return (code, out, err)."""
    monkeypatch.chdir(root)
    code = review_brief.main(
        ["--feature", slug, "--lifecycle-dir", str(root / "cortex" / "lifecycle")]
    )
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _tree_digest(d: Path) -> list[tuple[str, str]]:
    """``find <d> -type f | sort`` plus a per-file checksum."""
    return sorted(
        (
            str(p.relative_to(d)),
            hashlib.sha256(p.read_bytes()).hexdigest(),
        )
        for p in d.rglob("*")
        if p.is_file()
    )


# Markers that may appear only in a rework-scoped brief. The fail-open contract
# forbids every one of them, so a degraded run emitting any is a violation.
_SCOPED_MARKERS = (
    "rework re-review (scoped)",
    "## Reading scope",
    "## Prior-cycle checklist",
    "## Out-of-scope findings",
    "## Test baseline",
    "## Carry-forward",
    review_brief.REUSE_BASELINE,
    review_brief.RE_RUN,
)

# Markers the full brief always carries.
_FULL_MARKERS = ("full review", "## Scope", "Stage 1 — spec compliance")


def _assert_full_brief(out: str) -> None:
    for marker in _FULL_MARKERS:
        assert marker in out, f"full brief missing {marker!r}"
    for marker in _SCOPED_MARKERS:
        assert marker not in out, f"full brief leaked scoped marker {marker!r}"


def _assert_degraded(code: int, out: str, err: str, reason_fragment: str) -> None:
    """Requirement 19: exit 3, a full brief on stdout, the reason on stderr."""
    assert code == 3
    _assert_full_brief(out)
    assert "Degraded dispatch." in out
    assert reason_fragment in out
    assert err.startswith("DEGRADED: ")
    assert reason_fragment in err


# --- requirement 1: the prior review is archived, not destroyed --------------

def test_cycle_one_dispatch_archives_nothing_and_serves_full_brief(
    repo, monkeypatch, capsys
):
    slug = "feat"
    d = _make_lifecycle(repo, slug)

    code, out, err = _run(repo, slug, monkeypatch, capsys)

    assert code == 0
    assert err == ""
    assert list(d.glob("review-cycle-*.md")) == []
    assert "cycle 1" in out
    _assert_full_brief(out)


def test_cycle_two_dispatch_copies_review_byte_identically(repo, monkeypatch, capsys):
    slug = "feat"
    sha = _head(repo)
    original = _review_text(["issue one", "issue two", "issue three"])
    d = _make_lifecycle(
        repo,
        slug,
        rows=[_verdict_row(slug), _dispatched_row(slug, 1, sha)],
        review=original,
    )
    original_bytes = (d / "review.md").read_bytes()

    code, out, _ = _run(repo, slug, monkeypatch, capsys)

    assert code == 0
    archive = d / "review-cycle-1.md"
    assert archive.is_file()
    # Copied, never moved: the archive is byte-identical and review.md survives.
    assert archive.read_bytes() == original_bytes
    assert (d / "review.md").read_bytes() == original_bytes
    assert "rework re-review (scoped)" in out


# --- requirement 2: no-clobber, retry-safe -----------------------------------

def test_running_twice_produces_an_identical_tree(repo, monkeypatch, capsys):
    slug = "feat"
    sha = _head(repo)
    d = _make_lifecycle(
        repo,
        slug,
        rows=[_verdict_row(slug), _dispatched_row(slug, 1, sha)],
        review=_review_text(["issue one", "issue two"]),
    )

    first_code, _, _ = _run(repo, slug, monkeypatch, capsys)
    after_first = _tree_digest(d)
    second_code, _, _ = _run(repo, slug, monkeypatch, capsys)
    after_second = _tree_digest(d)

    assert (first_code, second_code) == (0, 0)
    assert after_second == after_first


def test_preexisting_archive_checksum_is_unchanged(repo, monkeypatch, capsys):
    slug = "feat"
    sha = _head(repo)
    archived = _review_text(["archived issue"])
    d = _make_lifecycle(
        repo,
        slug,
        rows=[_verdict_row(slug), _dispatched_row(slug, 1, sha)],
        review=_review_text(["a different, later issue"]),
        files={"review-cycle-1.md": archived},
    )
    before = hashlib.sha256((d / "review-cycle-1.md").read_bytes()).hexdigest()

    code, out, _ = _run(repo, slug, monkeypatch, capsys)

    assert code == 0
    after = hashlib.sha256((d / "review-cycle-1.md").read_bytes()).hexdigest()
    assert after == before
    # The checklist came from the untouched archive, not from review.md.
    assert "archived issue" in out
    assert "a different, later issue" not in out


# --- requirement 6: the discriminant is count_rework_cycles ------------------

def test_one_changes_requested_row_yields_rework_despite_reduced_cycle(
    repo, monkeypatch, capsys
):
    slug = "feat"
    sha = _head(repo)
    d = _make_lifecycle(
        repo,
        slug,
        rows=[_verdict_row(slug), _dispatched_row(slug, 1, sha)],
        review=_review_text(["issue one"]),
    )

    # The two counters genuinely disagree: this is what requirement 6 pins.
    assert count_rework_cycles(d / "events.log") == 1
    assert common.detect_lifecycle_phase(d)["cycle"] == 1

    code, out, _ = _run(repo, slug, monkeypatch, capsys)

    assert code == 0
    assert f"# Reviewer brief — {slug} · cycle 2 · rework re-review (scoped)" in out


# --- requirement 5: both modes exit 0 and name the review artifact ----------

def test_both_modes_exit_zero_and_name_the_review_artifact_path(
    repo, monkeypatch, capsys
):
    sha = _head(repo)
    full_dir = _make_lifecycle(repo, "full-feat")
    rework_dir = _make_lifecycle(
        repo,
        "rework-feat",
        rows=[_verdict_row("rework-feat"), _dispatched_row("rework-feat", 1, sha)],
        review=_review_text(["issue one"]),
    )

    full_code, full_out, _ = _run(repo, "full-feat", monkeypatch, capsys)
    rework_code, rework_out, _ = _run(repo, "rework-feat", monkeypatch, capsys)

    assert (full_code, rework_code) == (0, 0)
    assert "full review" in full_out
    assert "rework re-review (scoped)" in rework_out
    assert str((full_dir / "review.md").resolve()) in full_out
    assert str((rework_dir / "review.md").resolve()) in rework_out


# --- requirement 19: fail open to a full review, never an empty checklist ----

def test_degrades_when_the_prior_archive_is_missing(repo, monkeypatch, capsys):
    slug = "feat"
    sha = _head(repo)
    # Neither review.md nor the archive is on disk, so there is nothing to
    # archive and nothing to read: the deleted-archive case.
    _make_lifecycle(repo, slug, rows=[_verdict_row(slug), _dispatched_row(slug, 1, sha)])

    code, out, err = _run(repo, slug, monkeypatch, capsys)

    _assert_degraded(code, out, err, "missing or unreadable")


def test_degrades_when_the_archive_verdict_is_unparseable(repo, monkeypatch, capsys):
    slug = "feat"
    sha = _head(repo)
    _make_lifecycle(
        repo,
        slug,
        rows=[_verdict_row(slug), _dispatched_row(slug, 1, sha)],
        review=_review_text(["issue one"]),
        files={"review-cycle-1.md": "# Review\n\nNo fenced verdict block here.\n"},
    )

    code, out, err = _run(repo, slug, monkeypatch, capsys)

    _assert_degraded(code, out, err, "no parseable")


def test_degrades_when_the_archive_issues_array_is_empty(repo, monkeypatch, capsys):
    slug = "feat"
    sha = _head(repo)
    _make_lifecycle(
        repo,
        slug,
        rows=[_verdict_row(slug), _dispatched_row(slug, 1, sha)],
        review=_review_text(["issue one"]),
        files={"review-cycle-1.md": _review_text([])},
    )

    code, out, err = _run(repo, slug, monkeypatch, capsys)

    _assert_degraded(code, out, err, "empty issues array")


def test_degrades_when_no_prior_dispatch_row_supplies_a_baseline(
    repo, monkeypatch, capsys
):
    slug = "feat"
    # A CHANGES_REQUESTED row but no review_dispatched row: nothing supplies the
    # commit range, so a scoped brief cannot honestly be built.
    _make_lifecycle(
        repo,
        slug,
        rows=[_verdict_row(slug)],
        review=_review_text(["issue one"]),
        files={"review-cycle-1.md": _review_text(["issue one"])},
    )

    code, out, err = _run(repo, slug, monkeypatch, capsys)

    _assert_degraded(code, out, err, "no review_dispatched row for cycle 1")
