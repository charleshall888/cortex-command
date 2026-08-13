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
    "## Prior-Cycle Checklist",
    "## Out-of-Scope Findings",
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
    assert "DEGRADED" not in err
    # Nothing to archive: there is no review.md at all on a first dispatch.
    assert list(d.glob("review-cycle-*.md")) == []
    assert "archived none" in err
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


# --- #485: a mis-derived cycle cannot destroy the prior review ---------------

def test_a_review_present_at_cycle_one_is_archived_not_left_exposed(
    repo, monkeypatch, capsys
):
    """The archive fires on the file's existence, never on the derived cycle.

    A ``review.md`` sitting there at "cycle 1" is the contradiction #485 is
    about: either the cycle was mis-derived (the observed case — a stale log
    under-counted the rework rows) or a partial write is being re-dispatched.
    Both readings agree the file must survive the reviewer that is about to
    overwrite it, so the old ``cycle < 2`` guard had no safe branch.
    """
    slug = "feat"
    original = _review_text(["the defect cycle 1 caught"], cycle=1)
    d = _make_lifecycle(repo, slug, review=original)  # no rows → derives cycle 1

    code, out, err = _run(repo, slug, monkeypatch, capsys)

    assert code == 0
    assert "cycle 1" in out  # the derivation itself is unchanged
    # The artifact's own verdict block names the archive when the cycle cannot.
    archive = d / "review-cycle-1.md"
    assert archive.read_text(encoding="utf-8") == original
    assert (d / "review.md").read_text(encoding="utf-8") == original
    assert archive.name in err


def test_an_unnumbered_review_at_cycle_one_still_gets_a_copy(
    repo, monkeypatch, capsys
):
    """No parseable verdict block → a fixed fallback name, still archived.

    The name is the only thing lost when the cycle is unknowable; the copy is
    not, and the copy is the part whose absence is unrecoverable.
    """
    slug = "feat"
    original = "# Review\n\nNo fenced verdict block here at all.\n"
    d = _make_lifecycle(repo, slug, review=original)

    code, _, _ = _run(repo, slug, monkeypatch, capsys)

    assert code == 0
    assert (d / "review-cycle-prior.md").read_text(encoding="utf-8") == original


def test_rerunning_a_cycle_one_archive_adds_no_second_file(
    repo, monkeypatch, capsys
):
    """Convergence now keys off content, because the name keys off the cycle.

    An unconditional archive whose idempotency depended on the derived cycle
    would grow the tree on every re-dispatch — trading a data-loss bug for a
    litter bug. The byte-identity check is what makes the retry a no-op.
    """
    slug = "feat"
    _make_lifecycle(repo, slug, review=_review_text(["issue"], cycle=1))
    d = repo / "cortex" / "lifecycle" / slug

    _run(repo, slug, monkeypatch, capsys)
    after_first = _tree_digest(d)
    _run(repo, slug, monkeypatch, capsys)

    assert _tree_digest(d) == after_first


def test_an_occupied_archive_name_never_overwrites_a_different_review(
    repo, monkeypatch, capsys
):
    """Different content under the preferred name gets a suffix, not a clobber."""
    slug = "feat"
    earlier = _review_text(["an earlier, different review"], cycle=1)
    current = _review_text(["the review being displaced now"], cycle=1)
    d = _make_lifecycle(
        repo, slug, review=current, files={"review-cycle-1.md": earlier}
    )

    code, _, _ = _run(repo, slug, monkeypatch, capsys)

    assert code == 0
    assert (d / "review-cycle-1.md").read_text(encoding="utf-8") == earlier
    assert (d / "review-cycle-1-a.md").read_text(encoding="utf-8") == current


def test_an_unarchivable_review_refuses_rather_than_serving_a_brief(
    repo, monkeypatch, capsys
):
    """Serving the brief is what licenses the overwrite, so it must not be served.

    Failing open here would hand the reviewer a writable ``review.md`` whose only
    copy does not exist — the exact loss the archive prevents, reached through
    the fail-open path instead of the cycle guard.
    """
    slug = "feat"
    original = _review_text(["irreplaceable finding"], cycle=1)
    d = _make_lifecycle(repo, slug, review=original)

    def _boom(*_args, **_kwargs):
        raise OSError("no space left on device")

    monkeypatch.setattr(review_brief.shutil, "copy2", _boom)

    code, out, err = _run(repo, slug, monkeypatch, capsys)

    assert code == 1
    assert out == ""  # no brief at all
    assert "REFUSED" in err
    assert (d / "review.md").read_text(encoding="utf-8") == original


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


# --- the dispatch row records the mode actually served ----------------------

def _dispatched_rows(d: Path) -> list[dict]:
    """The ``review_dispatched`` rows in the lifecycle's events.log, in order."""
    rows = []
    for raw in (d / "events.log").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line:
            row = json.loads(line)
            if row.get("event") == "review_dispatched":
                rows.append(row)
    return rows


def _typed_mode_choices() -> tuple[str, ...]:
    """``--mode``'s allowed values, read from the typed subcommand table itself.

    Derived rather than restated so the row this verb appends cannot drift out
    of the vocabulary ``cortex-lifecycle-event review-dispatched`` accepts.
    """
    from cortex_command import lifecycle_event

    _, specs = lifecycle_event._EVENT_SUBCOMMANDS["review-dispatched"]
    choices = next(spec[4] for spec in specs if spec[0] == "--mode")
    assert choices, "review-dispatched --mode declares no choices"
    return tuple(choices)


def test_a_degraded_rework_records_the_full_mode_it_actually_served(
    repo, monkeypatch, capsys
):
    """A rework that falls through to a full brief must not record ``rework``."""
    slug = "feat"
    sha = _head(repo)
    d = _make_lifecycle(
        repo, slug, rows=[_verdict_row(slug), _dispatched_row(slug, 1, sha)]
    )

    code, out, err = _run(repo, slug, monkeypatch, capsys)

    _assert_degraded(code, out, err, "missing or unreadable")
    cycle2 = [r for r in _dispatched_rows(d) if r["cycle"] == 2]
    assert len(cycle2) == 1, _dispatched_rows(d)
    assert cycle2[0]["mode"] == "full", (
        "a degraded dispatch served a full brief but recorded "
        f"{cycle2[0]['mode']!r}"
    )
    assert cycle2[0]["baseline_sha"] == sha
    assert cycle2[0]["mode"] in _typed_mode_choices()


def test_a_served_rework_records_the_rework_mode(repo, monkeypatch, capsys):
    slug = "feat"
    sha = _head(repo)
    d = _make_lifecycle(
        repo,
        slug,
        rows=[_verdict_row(slug), _dispatched_row(slug, 1, sha)],
        review=_review_text(["issue one"]),
    )

    code, _out, _err = _run(repo, slug, monkeypatch, capsys)

    assert code == 0
    cycle2 = [r for r in _dispatched_rows(d) if r["cycle"] == 2]
    assert len(cycle2) == 1, _dispatched_rows(d)
    assert cycle2[0]["mode"] == "rework"
    assert cycle2[0]["mode"] in _typed_mode_choices()


def test_a_redispatched_degraded_cycle_appends_no_second_row(
    repo, monkeypatch, capsys
):
    """Idempotency survives the move: one row per cycle, the original preserved."""
    slug = "feat"
    sha = _head(repo)
    d = _make_lifecycle(
        repo, slug, rows=[_verdict_row(slug), _dispatched_row(slug, 1, sha)]
    )

    first_code, _, _ = _run(repo, slug, monkeypatch, capsys)
    after_first = _dispatched_rows(d)
    second_code, _, _ = _run(repo, slug, monkeypatch, capsys)

    assert (first_code, second_code) == (3, 3)
    assert _dispatched_rows(d) == after_first
    assert len([r for r in after_first if r["cycle"] == 2]) == 1
