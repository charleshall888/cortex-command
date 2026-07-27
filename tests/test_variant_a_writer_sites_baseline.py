"""Characterization tests pinning current (pre-refactor) writer-site behavior.

Spec R5 — Phase 1. Each test pins the resolved write target for one of the
four ticket-named writer sites that are NOT reachable from
``implement.md``/``complete.md`` and are therefore NOT modified by Phase 3:

  Site A — ``cortex_command/refine.py:117``
    CWD-pinned: ``Path("cortex/lifecycle") / slug / "events.log"`` is a bare
    relative path; it resolves to ``{CWD}/cortex/lifecycle/{slug}/events.log``.
    A mid-session ``cd`` changes where the write lands.

  Site B — ``cortex_command/critical_review.py:340-349,375-416,318-322``
    env-pinned: when ``--lifecycle-root`` is omitted the default falls through
    to ``_default_lifecycle_root()`` → ``_git_toplevel()`` → ``git rev-parse
    --show-toplevel``.  The write destination is anchored to the active git
    worktree, not to the naked process CWD.

  Site C — ``bin/cortex-complexity-escalator:265,296``
    CWD-pinned: the script constructs
    ``Path(args.lifecycle_dir) / feature / "events.log"`` where
    ``args.lifecycle_dir`` defaults to the bare string ``"cortex/lifecycle"``;
    this resolves relative to the process CWD at invocation time.

  Site D — ``cortex_command/discovery.py:189-197``
    env-pinned: ``resolve_events_log_path(topic, repo_root)`` takes an
    explicit ``repo_root`` argument and constructs an absolute path from it.
    The function does not consult CWD at all.

Pattern: ``tmp_path`` + ``monkeypatch.chdir`` / ``monkeypatch.setenv`` per
case, matching the env-var assertion structure in
``cortex_command/tests/test_common.py:55-56``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import cortex_command.lifecycle.complexity_escalator as _escalator_module

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
ESCALATOR_SCRIPT = REPO_ROOT / "bin" / "cortex-complexity-escalator"


@pytest.fixture(scope="module")
def escalator_module():
    """Return the complexity_escalator Python module for unit tests."""
    return _escalator_module


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ===========================================================================
# Site A — refine.py:117 (CWD-pinned)
# ===========================================================================


class TestRefineEmitLifecycleStartCwdPinned:
    """Pin current write-target resolution for ``cortex_command/refine.py:117``.

    Acceptance: with default args, the events.log write lands in
    ``{CWD}/cortex/lifecycle/{slug}/events.log`` (bare relative path).
    """

    def test_write_lands_under_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """events.log is created at CWD/cortex/lifecycle/{slug}/events.log."""
        from cortex_command.refine import main as refine_main

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        rc = refine_main(
            [
                "emit-lifecycle-start",
                "--lifecycle-slug",
                "my-feature",
            ]
        )
        assert rc == 0

        expected = tmp_path / "cortex" / "lifecycle" / "my-feature" / "events.log"
        assert expected.exists(), f"expected write at {expected}"

    def test_write_does_not_land_outside_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CWD change redirects the write; an alternate CWD produces a different path.

        Two separate invocations with different CWDs write to different
        locations — confirming the bare-relative-path behavior.
        """
        from cortex_command.refine import main as refine_main

        cwd_a = tmp_path / "dir-a"
        cwd_b = tmp_path / "dir-b"
        cwd_a.mkdir()
        cwd_b.mkdir()
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        monkeypatch.chdir(cwd_a)
        assert refine_main(["emit-lifecycle-start", "--lifecycle-slug", "feat"]) == 0

        monkeypatch.chdir(cwd_b)
        assert refine_main(["emit-lifecycle-start", "--lifecycle-slug", "feat"]) == 0

        expected_a = cwd_a / "cortex" / "lifecycle" / "feat" / "events.log"
        expected_b = cwd_b / "cortex" / "lifecycle" / "feat" / "events.log"
        assert expected_a.exists(), "first write should land under dir-a"
        assert expected_b.exists(), "second write should land under dir-b"

    def test_write_event_content(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Written event is a valid lifecycle_start row at CWD-relative path."""
        from cortex_command.refine import main as refine_main

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        assert (
            refine_main(["emit-lifecycle-start", "--lifecycle-slug", "slug-x"]) == 0
        )

        events_log = tmp_path / "cortex" / "lifecycle" / "slug-x" / "events.log"
        rows = _read_jsonl(events_log)
        assert len(rows) == 1
        row = rows[0]
        assert row["event"] == "lifecycle_start"
        assert row["feature"] == "slug-x"


# ===========================================================================
# Site B — critical_review.py:340-349,375-416,318-322 (env-pinned via git)
# ===========================================================================



class TestComplexityEscalatorCwdPinned:
    """Pin current write-target resolution for ``bin/cortex-complexity-escalator``.

    With the default ``--lifecycle-dir cortex/lifecycle`` (bare relative),
    the write lands at ``{CWD}/cortex/lifecycle/{feature}/events.log``.
    """

    def test_default_lifecycle_dir_resolves_relative_to_cwd(
        self,
        escalator_module,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """events.log created at CWD/cortex/lifecycle/{feature}/events.log."""
        feature = "esc-feature"
        feature_dir = tmp_path / "cortex" / "lifecycle" / feature
        feature_dir.mkdir(parents=True)

        # Two qualifying bullets to trigger escalation.
        (feature_dir / "research.md").write_text(
            "## Open Questions\n- q1?\n- q2?\n", encoding="utf-8"
        )

        result = subprocess.run(
            [sys.executable, "-m", "cortex_command.lifecycle.complexity_escalator", feature, "--gate", "research_open_questions"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "Escalating" in result.stdout

        expected = tmp_path / "cortex" / "lifecycle" / feature / "events.log"
        assert expected.exists(), f"expected write at {expected}"

    def test_cwd_change_redirects_write(
        self,
        tmp_path: Path,
    ) -> None:
        """Write lands under whichever CWD the script is invoked from.

        Two invocations from different CWDs produce events.log files in
        those respective directories, confirming CWD-pinning.
        """
        feature = "esc-feature"

        for sub in ("cwd-x", "cwd-y"):
            cwd = tmp_path / sub
            feature_dir = cwd / "cortex" / "lifecycle" / feature
            feature_dir.mkdir(parents=True)
            (feature_dir / "research.md").write_text(
                "## Open Questions\n- q1?\n- q2?\n", encoding="utf-8"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cortex_command.lifecycle.complexity_escalator",
                    feature,
                    "--gate",
                    "research_open_questions",
                ],
                cwd=str(cwd),
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stderr
            events_log = cwd / "cortex" / "lifecycle" / feature / "events.log"
            assert events_log.exists(), f"expected write under {cwd}"

    def test_explicit_lifecycle_dir_overrides_default(
        self,
        tmp_path: Path,
    ) -> None:
        """When ``--lifecycle-dir`` is supplied explicitly the write lands there.

        The bare-default is ``cortex/lifecycle``; supplying an absolute path
        for ``--lifecycle-dir`` shows the write follows the argument, not CWD.
        This pins the current API surface.
        """
        feature = "esc-feature"
        explicit_dir = tmp_path / "custom" / "lifecycle"
        feature_dir = explicit_dir / feature
        feature_dir.mkdir(parents=True)
        (feature_dir / "research.md").write_text(
            "## Open Questions\n- q1?\n- q2?\n", encoding="utf-8"
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "cortex_command.lifecycle.complexity_escalator",
                feature,
                "--gate",
                "research_open_questions",
                "--lifecycle-dir",
                str(explicit_dir),
            ],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        events_log = feature_dir / "events.log"
        assert events_log.exists(), f"expected write at {events_log}"
        rows = _read_jsonl(events_log)
        assert len(rows) == 1
        assert rows[0]["event"] == "complexity_override"


# ===========================================================================
# Site D — discovery.py:189-197 (env-pinned via explicit repo_root arg)
# ===========================================================================


class TestDiscoveryResolveEventsLogPathEnvPinned:
    """Pin current write-target resolution for ``cortex_command/discovery.py:189-197``.

    ``resolve_events_log_path(topic, repo_root)`` takes an explicit
    ``repo_root`` and builds an absolute path from it.  CWD is irrelevant.
    """

    def test_path_resolves_from_explicit_repo_root_not_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returned path is rooted at ``repo_root``, independent of CWD."""
        from cortex_command.discovery import resolve_events_log_path

        repo_root = tmp_path / "my-repo"
        repo_root.mkdir()

        # CWD is a completely different directory.
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        monkeypatch.chdir(other_dir)
        monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)

        result = resolve_events_log_path("my-topic", repo_root)

        expected = repo_root / "cortex" / "research" / "my-topic" / "events.log"
        assert result == expected

    def test_cwd_change_does_not_affect_resolved_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same repo_root + topic always returns the same path regardless of CWD.

        Changing CWD between calls must not alter the resolved path, confirming
        that the function is not CWD-sensitive (env-pinned via explicit arg).
        """
        from cortex_command.discovery import resolve_events_log_path

        repo_root = tmp_path / "stable-repo"
        repo_root.mkdir()
        monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)

        cwd_a = tmp_path / "cwd-a"
        cwd_b = tmp_path / "cwd-b"
        cwd_a.mkdir()
        cwd_b.mkdir()

        monkeypatch.chdir(cwd_a)
        path_a = resolve_events_log_path("stable-topic", repo_root)

        monkeypatch.chdir(cwd_b)
        path_b = resolve_events_log_path("stable-topic", repo_root)

        assert path_a == path_b
        assert str(path_a).startswith(str(repo_root))

    def test_lifecycle_session_routes_to_lifecycle_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When LIFECYCLE_SESSION_ID is set (and .session matches), routes to lifecycle.

        Pins the env-variable-aware routing behavior that already exists in
        ``resolve_events_log_path``.  The resolved path uses the explicit
        ``repo_root``, not CWD.
        """
        from cortex_command.discovery import resolve_events_log_path

        repo_root = tmp_path / "my-repo"
        lifecycle_dir = repo_root / "cortex" / "lifecycle" / "active-feature"
        lifecycle_dir.mkdir(parents=True)

        session_id = "test-session-id-abc"
        (lifecycle_dir / ".session").write_text(session_id, encoding="utf-8")

        monkeypatch.setenv("LIFECYCLE_SESSION_ID", session_id)
        monkeypatch.chdir(tmp_path)  # CWD is repo root, not the lifecycle dir

        result = resolve_events_log_path("ignored-topic", repo_root)

        expected = lifecycle_dir / "events.log"
        assert result == expected
