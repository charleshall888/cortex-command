"""Tests for cortex_command.lifecycle_event — cortex-lifecycle-event log CLI.

Covers:
(a) Basic append: the ``log`` subcommand appends a valid JSONL row with expected
    schema fields to ``{resolved-root}/cortex/lifecycle/{feature}/events.log``.
(b) CWD-based resolution: when CWD is inside a worktree (fake ``.git`` file),
    the events.log path resolves to the worktree base, not ``CORTEX_REPO_ROOT``.
(c) Concurrent invocations do not interleave JSONL records (flock contract).

This test file also satisfies spec R3's acceptance criterion (the CLI is the
"refactored writer site" with the non-None ``worktree_root``-equivalent test).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from cortex_command.common import CortexProjectRootError
from cortex_command.lifecycle_event import _run, log_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_cortex_root(base: Path) -> Path:
    """Create a minimal cortex project tree under *base* and return *base*."""
    (base / "cortex" / "lifecycle").mkdir(parents=True, exist_ok=True)
    return base


def _setup_worktree(base: Path) -> Path:
    """Create a fake git worktree under *base*.

    The worktree root contains:
    - a ``cortex/lifecycle/`` directory (simulates the worktree having its own
      cortex project tree, as required by Variant A)
    - a ``.git`` file (not directory — the worktree-shaped marker)

    Returns the worktree root.
    """
    worktree_root = base / "worktree"
    worktree_root.mkdir()
    (worktree_root / "cortex" / "lifecycle").mkdir(parents=True, exist_ok=True)
    (worktree_root / ".git").write_text(
        "gitdir: /some/main/repo/.git/worktrees/wt\n"
    )
    return worktree_root


# ---------------------------------------------------------------------------
# (a) Basic append — expected JSONL schema
# ---------------------------------------------------------------------------


class TestLogEventBasicAppend:
    """Basic append behavior via the ``log_event`` Python API."""

    def test_appends_jsonl_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A single ``log_event`` call creates events.log with one valid JSONL row."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        log_event(
            event="interactive_worktree_entered",
            feature="foo",
            worktree_path="/tmp/xyz",
        )

        log_path = root / "cortex" / "lifecycle" / "foo" / "events.log"
        assert log_path.exists(), "events.log was not created"
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1, f"expected 1 JSONL line, got {len(lines)}"

        row = json.loads(lines[0])
        assert row["schema_version"] == 1
        assert row["event"] == "interactive_worktree_entered"
        assert row["feature"] == "foo"
        assert row["worktree_path"] == "/tmp/xyz"
        assert "ts" in row

    def test_row_schema_fields_complete(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All five required schema fields are present in the emitted row."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        log_event(event="interactive_worktree_entered", feature="bar")

        log_path = root / "cortex" / "lifecycle" / "bar" / "events.log"
        row = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        required_keys = {"schema_version", "ts", "event", "feature", "worktree_path"}
        assert required_keys <= row.keys(), (
            f"missing keys: {required_keys - row.keys()}"
        )

    def test_worktree_path_none_serialises_as_null(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``worktree_path=None`` serialises as JSON ``null``."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        log_event(event="interactive_worktree_entered", feature="nulltest")

        log_path = root / "cortex" / "lifecycle" / "nulltest" / "events.log"
        row = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert row["worktree_path"] is None

    def test_multiple_calls_append_multiple_rows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Subsequent ``log_event`` calls append additional rows."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        log_event(event="interactive_worktree_entered", feature="multi")
        log_event(event="feature_complete", feature="multi")

        log_path = root / "cortex" / "lifecycle" / "multi" / "events.log"
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "interactive_worktree_entered"
        assert json.loads(lines[1])["event"] == "feature_complete"

    def test_events_log_path_under_feature_slug(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """events.log lands at ``<root>/cortex/lifecycle/<slug>/events.log``."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        log_event(event="interactive_worktree_entered", feature="my-feature-slug")

        expected = root / "cortex" / "lifecycle" / "my-feature-slug" / "events.log"
        assert expected.exists()


# ---------------------------------------------------------------------------
# (a) Basic append — CLI entry point (_run)
# ---------------------------------------------------------------------------


class TestCliRun:
    """Tests for the ``_run`` entry point (simulates ``cortex-lifecycle-event log``)."""

    def test_cli_appends_event(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``_run`` with ``log`` subcommand appends a JSONL row."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        rc = _run([
            "log",
            "--event", "interactive_worktree_entered",
            "--feature", "foo",
            "--worktree-path", "/tmp/xyz",
        ])

        assert rc == 0
        log_path = root / "cortex" / "lifecycle" / "foo" / "events.log"
        assert log_path.exists()
        row = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert row["event"] == "interactive_worktree_entered"
        assert row["feature"] == "foo"
        assert row["worktree_path"] == "/tmp/xyz"
        assert row["schema_version"] == 1

    def test_cli_without_worktree_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``_run`` without ``--worktree-path`` records ``null``."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        rc = _run([
            "log",
            "--event", "interactive_worktree_entered",
            "--feature", "bar",
        ])

        assert rc == 0
        log_path = root / "cortex" / "lifecycle" / "bar" / "events.log"
        row = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert row["worktree_path"] is None

    def test_cli_returns_1_when_no_cortex_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``_run`` returns exit code 1 when the root cannot be resolved."""
        # Place a .git directory to terminate the walk without finding cortex/
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        rc = _run([
            "log",
            "--event", "interactive_worktree_entered",
            "--feature", "orphan",
        ])

        assert rc == 1


# ---------------------------------------------------------------------------
# (b) CWD-based resolution — worktree root preferred over CORTEX_REPO_ROOT
# ---------------------------------------------------------------------------


class TestCwdResolution:
    """Verify that the CWD-based resolver ignores CORTEX_REPO_ROOT.

    Satisfies spec R3's acceptance criterion: the CLI is the "refactored writer
    site" with a non-None worktree_root-equivalent test — the root is resolved
    from the physical CWD, not the env var.
    """

    def test_resolves_to_worktree_base_ignoring_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """events.log lands in the worktree when CWD is inside a worktree.

        CORTEX_REPO_ROOT points to a separate main-repo directory; the
        cwd-based resolver must ignore it and resolve from the physical CWD.
        """
        worktree_root = _setup_worktree(tmp_path)

        # CWD is inside the worktree (a subdirectory)
        inside = worktree_root / "subdir"
        inside.mkdir()
        monkeypatch.chdir(inside)

        # CORTEX_REPO_ROOT points to an unrelated main repo
        main_repo = tmp_path / "main-repo"
        main_repo.mkdir()
        (main_repo / "cortex" / "lifecycle").mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(main_repo))

        log_event(
            event="interactive_worktree_entered",
            feature="myfeature",
            worktree_path=str(worktree_root),
        )

        # events.log must land in the worktree, NOT in main_repo
        worktree_log = worktree_root / "cortex" / "lifecycle" / "myfeature" / "events.log"
        main_repo_log = main_repo / "cortex" / "lifecycle" / "myfeature" / "events.log"

        assert worktree_log.exists(), "events.log was not written to the worktree"
        assert not main_repo_log.exists(), (
            "events.log was incorrectly written to CORTEX_REPO_ROOT target"
        )

    def test_cwd_at_worktree_root_resolves_correctly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CWD at the worktree root itself (not a subdirectory) resolves correctly."""
        worktree_root = _setup_worktree(tmp_path)
        monkeypatch.chdir(worktree_root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        log_event(event="interactive_worktree_entered", feature="rootcwd")

        expected = worktree_root / "cortex" / "lifecycle" / "rootcwd" / "events.log"
        assert expected.exists()

    def test_env_set_but_cwd_determines_target(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CORTEX_REPO_ROOT is set but CWD determines where the event lands."""
        worktree_root = _setup_worktree(tmp_path)
        monkeypatch.chdir(worktree_root)

        # CORTEX_REPO_ROOT points elsewhere; must be ignored by _from_cwd resolver
        other_root = tmp_path / "other-repo"
        other_root.mkdir()
        (other_root / "cortex" / "lifecycle").mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(other_root))

        log_event(event="interactive_worktree_entered", feature="envtest")

        worktree_log = worktree_root / "cortex" / "lifecycle" / "envtest" / "events.log"
        other_log = other_root / "cortex" / "lifecycle" / "envtest" / "events.log"

        assert worktree_log.exists()
        assert not other_log.exists()

    def test_raises_when_no_cortex_ancestor_in_cwd_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Raises CortexProjectRootError when CWD tree has no cortex/ ancestor."""
        # No cortex/ directory, but has .git file to terminate the walk
        (tmp_path / ".git").write_text("gitdir: /some/other/.git/worktrees/wt\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        with pytest.raises(CortexProjectRootError):
            log_event(event="interactive_worktree_entered", feature="nope")


# ---------------------------------------------------------------------------
# (c) Concurrent invocations — flock contract
# ---------------------------------------------------------------------------


class TestConcurrentAppend:
    """Verify that concurrent log_event calls do not interleave JSONL records."""

    def test_concurrent_writes_produce_complete_lines(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """N concurrent threads each write one event; all N rows are valid JSONL.

        Verifies the basic flock contract: no partial or interleaved records.
        Each thread's log_event call must produce exactly one complete,
        independently parseable JSON object on its own line.
        """
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        n_threads = 20
        errors: list[Exception] = []

        def _write(i: int) -> None:
            try:
                log_event(
                    event=f"concurrent_event_{i}",
                    feature="concurrent-test",
                    worktree_path=f"/tmp/wt-{i}",
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_write, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"threads raised exceptions: {errors}"

        log_path = root / "cortex" / "lifecycle" / "concurrent-test" / "events.log"
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        lines = [line for line in content.splitlines() if line.strip()]

        assert len(lines) == n_threads, (
            f"expected {n_threads} lines, got {len(lines)}: {content!r}"
        )

        # Every line must be a valid, independently parseable JSON object
        for line in lines:
            row = json.loads(line)
            assert row["schema_version"] == 1
            assert "event" in row
            assert "feature" in row
            assert row["feature"] == "concurrent-test"
            assert "ts" in row

    def test_concurrent_writes_all_events_recorded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All N distinct event names appear exactly once in the log."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        n_threads = 10
        errors: list[Exception] = []

        def _write(i: int) -> None:
            try:
                log_event(
                    event=f"event_{i:03d}",
                    feature="distinct-events",
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_write, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors

        log_path = root / "cortex" / "lifecycle" / "distinct-events" / "events.log"
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == n_threads

        recorded_events = {json.loads(line)["event"] for line in lines}
        expected_events = {f"event_{i:03d}" for i in range(n_threads)}
        assert recorded_events == expected_events, (
            f"missing events: {expected_events - recorded_events}"
        )
