"""The runner publishes the ``latest-overnight`` session pointer.

``cortex/lifecycle/sessions/latest-overnight`` had ten readers and no writer:
``cli_handler._auto_discover_state``, the dashboard poller's fallback state and
events paths, ``batch_runner``'s ``--state-path``/``--events-path`` defaults,
the morning-review skill's report lookup, and ``justfile``'s ``overnight-run``
recipe all resolve through it. Nothing created it, so each silently took a
fallback path or missed outright — after session overnight-2026-07-29-0145,
``/morning-review``'s first two report-location paths both missed and the skill
would have reported "no overnight session has been run" for a session that had
just completed.
"""

from __future__ import annotations

from pathlib import Path

from cortex_command.overnight.runner import _point_latest_overnight


def _sessions(tmp_path: Path, name: str = "overnight-2026-07-29-0145") -> Path:
    session_dir = tmp_path / "cortex" / "lifecycle" / "sessions" / name
    session_dir.mkdir(parents=True)
    (session_dir / "morning-report.md").write_text("# Morning Report\n")
    return session_dir


def test_pointer_is_created_and_resolves_to_the_session(tmp_path: Path) -> None:
    session_dir = _sessions(tmp_path)

    _point_latest_overnight(session_dir)

    link = session_dir.parent / "latest-overnight"
    assert link.is_symlink(), "readers probe is_symlink() before resolving"
    assert link.resolve() == session_dir.resolve()
    # The consumer-visible payload: the report lookup must land.
    assert (link / "morning-report.md").read_text() == "# Morning Report\n"


def test_pointer_is_relative_so_it_survives_a_moved_repo(tmp_path: Path) -> None:
    session_dir = _sessions(tmp_path)
    _point_latest_overnight(session_dir)
    link = session_dir.parent / "latest-overnight"

    import os

    assert not os.path.isabs(os.readlink(link)), (
        "an absolute link breaks when the repo is moved or copied"
    )

    moved = tmp_path.parent / (tmp_path.name + "-moved")
    os.rename(tmp_path, moved)
    try:
        moved_link = moved / "cortex" / "lifecycle" / "sessions" / "latest-overnight"
        assert (moved_link / "morning-report.md").exists()
    finally:
        os.rename(moved, tmp_path)


def test_pointer_is_repointed_on_a_later_session(tmp_path: Path) -> None:
    first = _sessions(tmp_path, "overnight-2026-07-28-1216")
    _point_latest_overnight(first)
    second = _sessions(tmp_path, "overnight-2026-07-29-0145")

    _point_latest_overnight(second)

    link = second.parent / "latest-overnight"
    assert link.resolve() == second.resolve()


def test_a_real_directory_at_the_path_is_left_alone(tmp_path: Path) -> None:
    """Best-effort: never destroy something that is not our pointer."""
    session_dir = _sessions(tmp_path)
    squatter = session_dir.parent / "latest-overnight"
    squatter.mkdir()
    (squatter / "keep.txt").write_text("do not delete me")

    _point_latest_overnight(session_dir)  # must not raise

    assert (squatter / "keep.txt").read_text() == "do not delete me"
