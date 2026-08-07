"""Refine owns its lifecycle's session marker and index (#427).

Three refine-phase defects shared one shape: a verb invoked during
Clarify/Research/Spec depended on state only the build phase created, and each
failed quietly — exit 0, no stderr, a plausible-looking result.

The load-bearing one: `cortex-critical-review-write-residue --session-id`
resolves a feature through the lifecycle's session marker, which only
`cortex-lifecycle-enter` wrote. `/cortex-core:refine` never calls `enter`, so
every spec-phase critical review — which `specify.md` *mandates* for complex,
medium-or-higher-criticality features — resolved to nothing and discarded its
B-class findings at exit 0, while telling the operator there was "no active
lifecycle context" from inside a populated one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command import refine as refine_module
from cortex_command.critical_review import write_residue_cli
from cortex_command.lifecycle import session_marker
from cortex_command.lifecycle.load_requirements_cli import resolve as load_requirements

SESSION = "session-abc-123"


def _write_backlog(
    root: Path,
    filename: str = "404-render-perf-spike.md",
    tags: str = "['render', 'perf', 'tooling']",
    lifecycle_slug: str = "render-perf-spike",
) -> Path:
    backlog_dir = root / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True, exist_ok=True)
    path = backlog_dir / filename
    path.write_text(
        "---\n"
        "uuid: 11111111-2222-3333-4444-555555555555\n"
        "title: Render perf spike\n"
        f"lifecycle_slug: {lifecycle_slug}\n"
        f"tags: {tags}\n"
        "status: backlog\n"
        "---\n\n# Body\n",
        encoding="utf-8",
    )
    return path


def _start(root: Path, monkeypatch: pytest.MonkeyPatch, reference: str = "404",
           session: str | None = SESSION) -> dict:
    monkeypatch.chdir(root)
    if session is None:
        monkeypatch.delenv(session_marker.SESSION_ID_ENV, raising=False)
    else:
        monkeypatch.setenv(session_marker.SESSION_ID_ENV, session)
    rc = refine_module.main(["start", reference])
    assert rc == 0
    return rc


# ---------------------------------------------------------------------------
# Defect 1 — the session marker
# ---------------------------------------------------------------------------


def test_refine_start_records_the_session_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_backlog(tmp_path)
    _start(tmp_path, monkeypatch)

    envelope = json.loads(capsys.readouterr().out.strip())
    assert envelope["state"] == "ready"
    assert envelope["session_recorded"] is True
    marker = tmp_path / "cortex" / "lifecycle" / "render-perf-spike" / ".session"
    assert marker.read_text().strip() == SESSION


def test_residue_resolves_a_refine_started_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The reported reproduction, end to end.

    Before the fix this returned `{"state": "no-context"}` at exit 0 with
    LIFECYCLE_SESSION_ID correctly set and a populated lifecycle on disk, and
    the review's B-class findings were gone.
    """
    _write_backlog(tmp_path)
    _start(tmp_path, monkeypatch)
    capsys.readouterr()

    resolved = write_residue_cli._resolve_feature(SESSION, tmp_path)

    assert resolved.status == "ok", resolved.note
    assert resolved.feature == "render-perf-spike"


def test_residue_reports_unowned_not_no_context(tmp_path: Path) -> None:
    """A populated lifecycle nobody marked is `unowned`, not `no-context`.

    The two are different failures and only one is the operator's problem.
    Collapsing them told an operator standing inside a lifecycle that there was
    none, which is what made the dropped findings so hard to notice.
    """
    lifecycle = tmp_path / "cortex" / "lifecycle" / "some-feature"
    lifecycle.mkdir(parents=True)
    (lifecycle / "events.log").write_text("{}\n", encoding="utf-8")

    resolved = write_residue_cli._resolve_feature(SESSION, tmp_path)

    assert resolved.status == "unowned"
    assert "NOT persisted" in resolved.note
    assert "no active lifecycle context" not in resolved.note


def test_infrastructure_dirs_do_not_count_as_lifecycles(tmp_path: Path) -> None:
    """`sessions/` and friends must not turn `no-context` into `unowned`.

    `cortex/lifecycle/sessions/` is telemetry, created as an import side effect,
    so it can exist in a repo that has never run a lifecycle. Counting it made
    the verb report `unowned` — "lifecycle directories exist but none is owned
    by this session" — for a repo with no lifecycles at all, which is the same
    class of misleading diagnosis the `unowned` arm was added to end.
    """
    for name in ("sessions", "deferred", "archive"):
        (tmp_path / "cortex" / "lifecycle" / name).mkdir(parents=True)
    (tmp_path / "cortex" / "lifecycle" / "sessions" / "some-uuid").mkdir()

    assert session_marker.has_any_lifecycle(tmp_path) is False
    assert write_residue_cli._resolve_feature(SESSION, tmp_path).status == "no-context"

    # ...but a real feature directory beside them still counts.
    feature = tmp_path / "cortex" / "lifecycle" / "real-feature"
    feature.mkdir()
    (feature / "events.log").write_text("{}\n", encoding="utf-8")
    assert session_marker.has_any_lifecycle(tmp_path) is True
    assert write_residue_cli._resolve_feature(SESSION, tmp_path).status == "unowned"


def test_residue_still_reports_no_context_with_no_lifecycle(tmp_path: Path) -> None:
    """The legitimate skip is preserved — a conversation-context review.

    This arm must stay quiet; the fix must separate it from the refine-phase
    case rather than making both loud.
    """
    resolved = write_residue_cli._resolve_feature(SESSION, tmp_path)

    assert resolved.status == "no-context"
    assert resolved.note.endswith("no active lifecycle context.")


def test_residue_honours_the_session_owner_marker(tmp_path: Path) -> None:
    """`.session-owner` resolves too — the third-copy divergence is closed.

    `discovery` read both marker names while the residue writer globbed
    `.session` only; a lifecycle carrying just the chain-migrated name was
    invisible to one of them.
    """
    lifecycle = tmp_path / "cortex" / "lifecycle" / "chain-migrated"
    lifecycle.mkdir(parents=True)
    (lifecycle / ".session-owner").write_text(SESSION, encoding="utf-8")

    resolved = write_residue_cli._resolve_feature(SESSION, tmp_path)

    assert resolved.status == "ok"
    assert resolved.feature == "chain-migrated"


def test_residue_reports_ambiguous_on_multiple_owners(tmp_path: Path) -> None:
    for slug in ("feature-one", "feature-two"):
        d = tmp_path / "cortex" / "lifecycle" / slug
        d.mkdir(parents=True)
        (d / ".session").write_text(SESSION, encoding="utf-8")

    resolved = write_residue_cli._resolve_feature(SESSION, tmp_path)

    assert resolved.status == "ambiguous"


def test_marker_is_not_double_counted_when_both_names_agree(tmp_path: Path) -> None:
    """Both marker names on one lifecycle is one match, not an `ambiguous` pair."""
    d = tmp_path / "cortex" / "lifecycle" / "both-markers"
    d.mkdir(parents=True)
    (d / ".session").write_text(SESSION, encoding="utf-8")
    (d / ".session-owner").write_text(SESSION, encoding="utf-8")

    assert session_marker.resolve_features_by_session(tmp_path, SESSION) == [
        "both-markers"
    ]
    assert write_residue_cli._resolve_feature(SESSION, tmp_path).status == "ok"


def test_refine_start_without_a_session_id_still_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The marker is a local convenience — its absence must not fail entry."""
    _write_backlog(tmp_path)
    _start(tmp_path, monkeypatch, session=None)

    envelope = json.loads(capsys.readouterr().out.strip())
    assert envelope["state"] == "ready"
    assert envelope["session_recorded"] is False


# ---------------------------------------------------------------------------
# Defect 2 — the index, and the requirements coverage it feeds
# ---------------------------------------------------------------------------


def test_refine_start_creates_the_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_backlog(tmp_path)
    _start(tmp_path, monkeypatch)

    envelope = json.loads(capsys.readouterr().out.strip())
    assert envelope["index"] == "created"
    index = tmp_path / "cortex" / "lifecycle" / "render-perf-spike" / "index.md"
    assert index.is_file()
    assert "render" in index.read_text()


def test_requirements_coverage_is_verified_after_refine_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Clarify's requirements-alignment rating is made against real coverage.

    Before the fix the index could not exist until `enter`, so a fresh refine
    rated coverage from a loader run that could only report UNVERIFIED — and
    that rating feeds the critical-review gate. What refine owns is the index
    existing by the time Clarify reads it; *which* area docs that index then
    selects is the loader's contract, pinned in
    ``tests/test_load_requirements_cli.py``.
    """
    (tmp_path / "cortex" / "requirements").mkdir(parents=True)
    (tmp_path / "cortex" / "requirements" / "project.md").write_text(
        "# Project\n\n"
        "## Conditional Loading\n\n"
        "- render → cortex/requirements/engineering-rendering-perf.md\n"
        "- tooling → cortex/requirements/engineering-quality-gates.md\n",
        encoding="utf-8",
    )
    for name in ("engineering-rendering-perf.md", "engineering-quality-gates.md"):
        (tmp_path / "cortex" / "requirements" / name).write_text("# doc\n", encoding="utf-8")
    _write_backlog(tmp_path)

    # Before: no lifecycle at all — the note must say coverage is unverified,
    # not that the feature has no area docs.
    lines_before, note_before, coverage_before = load_requirements(
        tmp_path, "render-perf-spike"
    )
    assert lines_before == ["cortex/requirements/project.md"]
    assert "UNVERIFIED" in note_before
    assert coverage_before == "no-area"

    _start(tmp_path, monkeypatch)
    capsys.readouterr()

    _, note_after, _ = load_requirements(tmp_path, "render-perf-spike")

    # The index now exists, so coverage is a determined result rather than an
    # unverified one — whatever tier it lands in.
    assert (tmp_path / "cortex" / "lifecycle" / "render-perf-spike" / "index.md").is_file()
    assert "UNVERIFIED" not in (note_after or "")


def test_refine_start_is_idempotent_on_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Re-running start neither duplicates the index nor loses the marker."""
    _write_backlog(tmp_path)
    _start(tmp_path, monkeypatch)
    first = json.loads(capsys.readouterr().out.strip())
    index = tmp_path / "cortex" / "lifecycle" / "render-perf-spike" / "index.md"
    body = index.read_text()

    _start(tmp_path, monkeypatch)
    second = json.loads(capsys.readouterr().out.strip())

    assert first["index"] == "created"
    assert second["index"] == "skipped"
    assert index.read_text() == body
    assert second["session_recorded"] is True


# ---------------------------------------------------------------------------
# Slug guard — refine builds filesystem paths from an attacker-influencable slug
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_slug", ["../../escaped", "..", "a/b", "a\\b", ""])
@pytest.mark.parametrize(
    "argv",
    [
        ["start", "no-such-ticket", "--lifecycle-slug", "{slug}"],
        ["emit-lifecycle-start", "--lifecycle-slug", "{slug}",
         "--backend", "cortex-backlog"],
        ["reconcile-clarify", "--lifecycle-slug", "{slug}",
         "--backend", "cortex-backlog"],
    ],
    ids=["start", "emit-lifecycle-start", "reconcile-clarify"],
)
def test_unsafe_slug_is_refused_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_slug: str, argv: list[str],
) -> None:
    """Every refine arm that writes must reject a traversal slug first.

    The slug arrives from `--lifecycle-slug` or from a backlog item's
    `lifecycle_slug:` frontmatter, and each arm builds a path from it. Refine was
    the one lifecycle-writing surface carrying no guard, so `--lifecycle-slug
    ../../escaped` wrote `events.log` (and, once refine started recording it, the
    session marker) outside `cortex/lifecycle/` entirely.
    """
    (tmp_path / "cortex" / "backlog").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(session_marker.SESSION_ID_ENV, SESSION)
    canary = tmp_path / "escaped"

    rc = refine_module.main([a.format(slug=bad_slug) for a in argv])

    if bad_slug == "" and argv[0] == "start":
        # An empty --lifecycle-slug is "not supplied", not a bad slug: start
        # falls through to its needs-slug arm and asks the caller to derive one.
        # It still writes nothing, which is what this test is really guarding.
        assert rc == 0
    else:
        assert rc == 2
    assert not canary.exists()
    # Nothing was written anywhere outside the backlog dir we created.
    assert not (tmp_path / "cortex" / "lifecycle").exists()


def test_write_session_refuses_a_traversal_slug(tmp_path: Path) -> None:
    """The shared writer guards itself, so a caller that forgets cannot escape."""
    with pytest.raises(ValueError, match="unsafe feature slug"):
        session_marker.write_session(tmp_path, "../escaped", SESSION)
    assert not (tmp_path / "escaped").exists()


def test_write_session_accepts_a_normal_slug(tmp_path: Path) -> None:
    """Discriminator: the guard rejects traversal, not ordinary slugs."""
    path = session_marker.write_session(tmp_path, "render-perf-spike", SESSION)
    assert path.read_text() == SESSION
    assert path == tmp_path / "cortex" / "lifecycle" / "render-perf-spike" / ".session"
