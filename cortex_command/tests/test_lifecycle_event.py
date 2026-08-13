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
import re
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
            fields=[("str", "worktree_path", "/tmp/xyz")],
        )

        log_path = root / "cortex" / "lifecycle" / "foo" / "events.log"
        assert log_path.exists(), "events.log was not created"
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1, f"expected 1 JSONL line, got {len(lines)}"

        row = json.loads(lines[0])
        assert row["event"] == "interactive_worktree_entered"
        assert row["feature"] == "foo"
        assert row["worktree_path"] == "/tmp/xyz"
        assert "ts" in row
        assert "schema_version" not in row

    def test_row_base_keys_present_no_legacy_keys(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The three base keys are present; legacy auto-keys are gone."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        log_event(event="interactive_worktree_entered", feature="bar")

        log_path = root / "cortex" / "lifecycle" / "bar" / "events.log"
        row = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        required_keys = {"ts", "event", "feature"}
        assert required_keys <= row.keys(), (
            f"missing keys: {required_keys - row.keys()}"
        )
        # No fields supplied → no extra keys auto-injected.
        assert "schema_version" not in row
        assert "worktree_path" not in row

    def test_no_fields_means_no_extra_keys(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without ``fields``, the row carries only the three base keys."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        log_event(event="interactive_worktree_entered", feature="nofields")

        log_path = root / "cortex" / "lifecycle" / "nofields" / "events.log"
        row = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert list(row.keys()) == ["ts", "event", "feature"]

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
            "--set", "worktree_path=/tmp/xyz",
        ])

        assert rc == 0
        log_path = root / "cortex" / "lifecycle" / "foo" / "events.log"
        assert log_path.exists()
        row = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert row["event"] == "interactive_worktree_entered"
        assert row["feature"] == "foo"
        assert row["worktree_path"] == "/tmp/xyz"
        assert "schema_version" not in row

    def test_cli_without_set_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``_run`` without ``--set`` fields records only the base keys."""
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
        assert "worktree_path" not in row

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
    """Verify the writer resolves the SAME log the served machine verbs do.

    This class pinned the opposite contract until #484 — the CWD winning over
    ``CORTEX_REPO_ROOT``, and a worktree CWD anchoring the write in the worktree.
    That is precisely what split a worktree-driven lifecycle across two logs:
    ``next``/``advance`` resolved the main root while this writer resolved the
    worktree, and neither verb said so. The anchor is now the pinned
    ``log_resolver``; a divergent CWD-anchored copy is *reported*, not written.
    """

    def test_env_pin_beats_the_worktree_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``CORTEX_REPO_ROOT`` wins — the overnight pin the machine verbs honour.

        The runner exports it precisely so every verb in the session agrees on
        one tree. A writer that ignored it wrote somewhere no reader looked.
        """
        worktree_root = _setup_worktree(tmp_path)
        inside = worktree_root / "subdir"
        inside.mkdir()
        monkeypatch.chdir(inside)

        main_repo = tmp_path / "main-repo"
        main_repo.mkdir()
        (main_repo / "cortex" / "lifecycle").mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(main_repo))

        log_event(
            event="interactive_worktree_entered",
            feature="myfeature",
            fields=[("str", "worktree_path", str(worktree_root))],
        )

        worktree_log = worktree_root / "cortex" / "lifecycle" / "myfeature" / "events.log"
        main_repo_log = main_repo / "cortex" / "lifecycle" / "myfeature" / "events.log"

        assert main_repo_log.exists(), "the env-pinned root is the one anchor"
        assert not worktree_log.exists(), (
            "a worktree-local copy is the split #484 removed"
        )

    def test_cwd_at_worktree_root_resolves_correctly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no env pin and an unreachable main root, the CWD tree still works.

        ``_setup_worktree``'s gitfile points at a path that does not exist, so
        the main-root parse yields no ``cortex/``-bearing candidate and the
        resolver falls back to the shared walk. A lifecycle is still writable —
        the anchor change must not make an ordinary tree unusable.
        """
        worktree_root = _setup_worktree(tmp_path)
        monkeypatch.chdir(worktree_root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        log_event(event="interactive_worktree_entered", feature="rootcwd")

        expected = worktree_root / "cortex" / "lifecycle" / "rootcwd" / "events.log"
        assert expected.exists()

    def test_write_from_a_real_worktree_lands_in_the_main_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The failure #484 observed: closing events written where no reader looks.

        A resolvable worktree — gitfile → admin dir → ``commondir`` → a main root
        that actually carries ``cortex/`` — is the shape a real session has. The
        write follows the ``commondir`` pointer rather than the CWD.
        """
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
        main = tmp_path / "main"
        admin = main / ".git" / "worktrees" / "wt1"
        admin.mkdir(parents=True)
        (admin / "commondir").write_text("../..\n", encoding="utf-8")
        (main / "cortex" / "lifecycle").mkdir(parents=True)

        wt = tmp_path / "wt"
        wt.mkdir()
        (wt / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
        (wt / "cortex" / "lifecycle").mkdir(parents=True)
        monkeypatch.chdir(wt)

        log_event(event="feature_complete", feature="closing")

        assert (main / "cortex" / "lifecycle" / "closing" / "events.log").exists()
        assert not (wt / "cortex" / "lifecycle" / "closing" / "events.log").exists()

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
                    fields=[("str", "worktree_path", f"/tmp/wt-{i}")],
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


# ---------------------------------------------------------------------------
# (d) Field-driven verb surface — --set / --set-json (R1, R2, R3)
# ---------------------------------------------------------------------------


class TestFieldDrivenRowShape:
    """R1: uniform ``{ts, event, feature, <ordered fields>}`` row."""

    def _read_row(self, root: Path, feature: str) -> dict:
        log_path = root / "cortex" / "lifecycle" / feature / "events.log"
        return json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

    def test_key_ordering_follows_argv(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Extra fields land after the base keys in argv order."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        rc = _run([
            "log",
            "--event", "phase_transition",
            "--feature", "f",
            "--set", "from=plan",
            "--set", "to=implement",
        ])
        assert rc == 0

        row = self._read_row(root, "f")
        assert list(row.keys()) == ["ts", "event", "feature", "from", "to"]
        assert row["event"] == "phase_transition"
        assert row["feature"] == "f"
        assert row["from"] == "plan"
        assert row["to"] == "implement"
        assert "schema_version" not in row
        assert "worktree_path" not in row

    def test_interleaved_set_and_set_json_preserve_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--set`` and ``--set-json`` share one ordered dest."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        rc = _run([
            "log",
            "--event", "batch_dispatch",
            "--feature", "f",
            "--set-json", "batch=2",
            "--set", "note=hi",
            "--set-json", "tasks=[1, 2]",
        ])
        assert rc == 0

        row = self._read_row(root, "f")
        assert list(row.keys()) == ["ts", "event", "feature", "batch", "note", "tasks"]
        assert row["batch"] == 2
        assert row["note"] == "hi"
        assert row["tasks"] == [1, 2]

    def test_duplicate_key_last_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A duplicate key takes the last-supplied value."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        rc = _run([
            "log",
            "--event", "e",
            "--feature", "f",
            "--set", "k=first",
            "--set", "k=second",
        ])
        assert rc == 0
        assert self._read_row(root, "f")["k"] == "second"


class TestCanonicalSerialization:
    """R2: spaced ``json.dumps`` defaults + ``%Y-%m-%dT%H:%M:%SZ`` timestamps."""

    def test_timestamp_is_second_precision_z(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``ts`` matches ``^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$`` (no clock patch)."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        rc = _run(["log", "--event", "phase_transition", "--feature", "f"])
        assert rc == 0

        line = (
            root / "cortex" / "lifecycle" / "f" / "events.log"
        ).read_text(encoding="utf-8").splitlines()[0]
        row = json.loads(line)
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", row["ts"]), row["ts"]

    def test_serialized_line_is_spaced(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The on-disk line uses spaced separators (``", "`` / ``": "``)."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        rc = _run([
            "log", "--event", "phase_transition", "--feature", "f",
            "--set", "from=plan",
        ])
        assert rc == 0

        line = (
            root / "cortex" / "lifecycle" / "f" / "events.log"
        ).read_text(encoding="utf-8").splitlines()[0]
        assert '"event": "phase_transition"' in line
        assert '"from": "plan"' in line
        assert '":"' not in line  # no compact separators survive


class TestFieldTypingGrammar:
    """R3: ``--set`` literal-string vs ``--set-json`` typed, with usage errors."""

    def _read_row(self, root: Path, feature: str) -> dict:
        log_path = root / "cortex" / "lifecycle" / feature / "events.log"
        return json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

    def test_set_json_number(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--set-json batch=3`` yields JSON number ``3``."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        rc = _run([
            "log", "--event", "batch_dispatch", "--feature", "f",
            "--set-json", "batch=3",
        ])
        assert rc == 0
        value = self._read_row(root, "f")["batch"]
        assert value == 3
        assert isinstance(value, int)

    def test_set_json_array(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--set-json tasks=[1, 2, 3]`` yields a JSON array."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        rc = _run([
            "log", "--event", "batch_dispatch", "--feature", "f",
            "--set-json", "tasks=[1, 2, 3]",
        ])
        assert rc == 0
        assert self._read_row(root, "f")["tasks"] == [1, 2, 3]

    def test_set_keeps_json_looking_string_literal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--set reason=null`` stays the string ``"null"``."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        rc = _run([
            "log", "--event", "e", "--feature", "f",
            "--set", "reason=null",
        ])
        assert rc == 0
        value = self._read_row(root, "f")["reason"]
        assert value == "null"
        assert isinstance(value, str)

    def test_set_splits_on_first_equals_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A value containing ``=`` (a URL) is preserved whole."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        rc = _run([
            "log", "--event", "e", "--feature", "f",
            "--set", "url=https://x?a=b",
        ])
        assert rc == 0
        assert self._read_row(root, "f")["url"] == "https://x?a=b"

    def test_set_empty_value(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--set reason=`` emits an empty string."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        rc = _run([
            "log", "--event", "e", "--feature", "f",
            "--set", "reason=",
        ])
        assert rc == 0
        assert self._read_row(root, "f")["reason"] == ""

    def test_set_without_equals_is_usage_error_no_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--set foo`` exits non-zero and writes no row."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        with pytest.raises(SystemExit) as exc:
            _run([
                "log", "--event", "e", "--feature", "f",
                "--set", "foo",
            ])
        assert exc.value.code != 0
        assert not (root / "cortex" / "lifecycle" / "f" / "events.log").exists()

    def test_set_json_malformed_is_usage_error_no_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--set-json k={bad`` exits non-zero and writes no row."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        with pytest.raises(SystemExit) as exc:
            _run([
                "log", "--event", "e", "--feature", "f",
                "--set-json", "k={bad",
            ])
        assert exc.value.code != 0
        assert not (root / "cortex" / "lifecycle" / "f" / "events.log").exists()

    def test_malformed_set_json_after_valid_writes_no_partial_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A later malformed ``--set-json`` aborts before any append."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        with pytest.raises(SystemExit) as exc:
            _run([
                "log", "--event", "e", "--feature", "f",
                "--set-json", "good=1",
                "--set-json", "bad={oops",
            ])
        assert exc.value.code != 0
        assert not (root / "cortex" / "lifecycle" / "f" / "events.log").exists()


# ---------------------------------------------------------------------------
# (e) Concurrency vs a bare appender — flock + O_APPEND (R4)
# ---------------------------------------------------------------------------


class TestVerbConcurrentWithBareAppender:
    """R4: the verb and a non-flock ``open(path, "a")`` appender coexist."""

    def test_verb_and_bare_append_all_rows_complete(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verb writes and bare appends run concurrently; every row parses."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        log_path = root / "cortex" / "lifecycle" / "concur" / "events.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        n = 20
        errors: list[object] = []

        def _verb_writer(i: int) -> None:
            try:
                rc = _run([
                    "log", "--event", f"verb_{i}", "--feature", "concur",
                    "--set-json", f"batch={i}",
                ])
                if rc != 0:
                    errors.append(("verb-rc", i, rc))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        def _bare_writer(i: int) -> None:
            try:
                line = json.dumps(
                    {"ts": "t", "event": f"bare_{i}", "feature": "concur"}
                ) + "\n"
                with open(log_path, "a", encoding="utf-8") as fh:
                    fh.write(line)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads: list[threading.Thread] = []
        for i in range(n):
            threads.append(threading.Thread(target=_verb_writer, args=(i,)))
            threads.append(threading.Thread(target=_bare_writer, args=(i,)))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"writers raised: {errors}"

        lines = [
            line
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(lines) == 2 * n, f"expected {2 * n} rows, got {len(lines)}"
        # Every row is a complete, independently parseable JSON object.
        for line in lines:
            json.loads(line)


# ---------------------------------------------------------------------------
# (f) High-level event subcommands — field-set ownership (ADR-0020)
# ---------------------------------------------------------------------------


class TestEventSubcommands:
    """Each high-level subcommand emits a row identical to its ``log`` form.

    The invariant guarded here is the migration's safety net: a subcommand's
    row must be key/value/type-identical (ts aside) to the raw
    ``log --event <name> --set…`` scaffold the skill prose used before. Byte
    order of extra fields is normalized per subcommand, so the comparison is on
    the parsed dict, not the serialized line.
    """

    def _read_row(self, root: Path, feature: str) -> dict:
        log_path = root / "cortex" / "lifecycle" / feature / "events.log"
        return json.loads(
            log_path.read_text(encoding="utf-8").splitlines()[0]
        )

    def _strip_ts(self, row: dict) -> dict:
        return {k: v for k, v in row.items() if k != "ts"}

    # (subcommand argv-tail, equivalent log argv-tail) — feature added per case.
    PARITY_CASES = [
        (
            ["phase-transition", "--from", "review", "--to", "complete"],
            ["log", "--event", "phase_transition",
             "--set", "from=review", "--set", "to=complete"],
        ),
        (
            ["phase-transition", "--from", "implement", "--to", "review",
             "--tier", "complex"],
            ["log", "--event", "phase_transition",
             "--set", "from=implement", "--set", "to=review",
             "--set", "tier=complex"],
        ),
        (
            ["plan-approved", "--dispatch-choice", "trunk"],
            ["log", "--event", "plan_approved",
             "--set", "dispatch_choice=trunk"],
        ),
        (
            ["feature-complete"],
            ["log", "--event", "feature_complete"],
        ),
        (
            ["feature-complete", "--tasks-total", "5",
             "--rework-cycles", "1", "--merge-anchor", "merge"],
            ["log", "--event", "feature_complete",
             "--set-json", "tasks_total=5", "--set-json", "rework_cycles=1",
             "--set", "merge_anchor=merge"],
        ),
        (
            ["spec-approved"],
            ["log", "--event", "spec_approved"],
        ),
        (
            ["review-verdict", "--verdict", "APPROVED", "--cycle", "2",
             "--drift", "detected"],
            ["log", "--event", "review_verdict",
             "--set", "verdict=APPROVED", "--set-json", "cycle=2",
             "--set", "requirements_drift=detected"],
        ),
        (
            ["lifecycle-start", "--tier", "complex", "--criticality", "high"],
            ["log", "--event", "lifecycle_start",
             "--set", "tier=complex", "--set", "criticality=high"],
        ),
        (
            ["feature-paused"],
            ["log", "--event", "feature_paused"],
        ),
        (
            ["drift-protocol-breach", "--state", "detected",
             "--suggestion", "missing", "--retries", "2"],
            ["log", "--event", "drift_protocol_breach",
             "--set", "state=detected", "--set", "suggestion=missing",
             "--set-json", "retries=2"],
        ),
        (
            ["criticality-override", "--from", "medium", "--to", "high"],
            ["log", "--event", "criticality_override",
             "--set", "from=medium", "--set", "to=high"],
        ),
        (
            ["batch-dispatch", "--batch", "0", "--tasks", '["3a", "3b"]'],
            ["log", "--event", "batch_dispatch",
             "--set-json", "batch=0", "--set-json", 'tasks=["3a", "3b"]'],
        ),
        (
            ["review-dispatched", "--cycle", "1", "--mode", "full",
             "--baseline-sha", "a" * 40],
            ["log", "--event", "review_dispatched",
             "--set-json", "cycle=1", "--set", "mode=full",
             "--set", "baseline_sha=" + "a" * 40],
        ),
    ]

    @pytest.mark.parametrize("new_tail,old_tail", PARITY_CASES)
    def test_subcommand_row_matches_log_form(
        self, new_tail, old_tail,
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        assert _run(new_tail + ["--feature", "f"]) == 0
        assert _run(old_tail + ["--feature", "f"]) == 0

        lines = (
            root / "cortex" / "lifecycle" / "f" / "events.log"
        ).read_text(encoding="utf-8").splitlines()
        new_row = self._strip_ts(json.loads(lines[0]))
        old_row = self._strip_ts(json.loads(lines[1]))
        assert new_row == old_row, (new_row, old_row)

    def test_json_fields_stay_typed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``--cycle`` / ``--batch`` / ``--retries`` emit ints, ``--tasks`` a list."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        assert _run([
            "batch-dispatch", "--feature", "f", "--batch", "3",
            "--tasks", '["a"]',
        ]) == 0
        row = self._read_row(root, "f")
        assert row["batch"] == 3 and isinstance(row["batch"], int)
        assert row["tasks"] == ["a"]

    def test_enum_typo_is_usage_error_no_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An out-of-enum ``--verdict`` exits non-zero and writes no row."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        with pytest.raises(SystemExit) as exc:
            _run([
                "review-verdict", "--feature", "f", "--verdict", "aproved",
                "--cycle", "1", "--drift", "none",
            ])
        assert exc.value.code != 0
        assert not (root / "cortex" / "lifecycle" / "f" / "events.log").exists()

    def test_optional_field_omitted_drops_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``feature-complete`` with no flags emits the bare 3-key close row."""
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        assert _run(["feature-complete", "--feature", "f"]) == 0
        row = self._read_row(root, "f")
        assert set(row) == {"ts", "event", "feature"}
        assert row["event"] == "feature_complete"

    def test_subcommand_table_covers_only_non_exempt_events(self) -> None:
        """The subcommand table never shadows an ADR-0020 hand-written event."""
        from cortex_command.lifecycle_event import _EVENT_SUBCOMMANDS

        exempt = {"clarify_critic", "pr_opened"}
        emitted = {ev for ev, _specs in _EVENT_SUBCOMMANDS.values()}
        assert emitted.isdisjoint(exempt), emitted & exempt


# ---------------------------------------------------------------------------
# (g) Override ``--reason`` clause validation on the typed verbs
# ---------------------------------------------------------------------------


class TestOverrideReasonClause:
    """``--reason`` on the two typed override verbs, end to end through argv.

    The clause predicate itself is unit-tested in ``tests/test_override_reason.py``;
    what is pinned here is the *binding* — that ``_clause_arg`` is actually wired
    onto both override verbs' ``--reason`` at parse time, so a bogus tag is
    refused before any row is built and a recognized tag is canonicalized on the
    way to disk.

    Every case runs against a throwaway project root with CWD moved into it:
    ``log_event`` resolves its log path from CWD, so a case left in the repo tree
    would append to the real ``cortex/lifecycle/``.
    """

    OVERRIDE_VERBS = ("criticality-override", "complexity-override")

    def _root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        root = _setup_cortex_root(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
        return root

    def _log_path(self, root: Path, feature: str = "f") -> Path:
        return root / "cortex" / "lifecycle" / feature / "events.log"

    def _read_row(self, root: Path, feature: str = "f", index: int = 0) -> dict:
        return json.loads(
            self._log_path(root, feature)
            .read_text(encoding="utf-8")
            .splitlines()[index]
        )

    @pytest.mark.parametrize("verb", OVERRIDE_VERBS)
    def test_bogus_clause_tag_rejected_on_both_axes(
        self, verb: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """R7: one vocabulary — ``design-fork:`` is refused on either axis.

        Exit 2 (argparse usage error) and no events.log at all, since the
        rejection happens before the row is built.
        """
        root = self._root(tmp_path, monkeypatch)

        with pytest.raises(SystemExit) as exc:
            _run([
                verb, "--feature", "f", "--from", "moderate", "--to", "complex",
                "--reason", "design-fork: two options",
            ])
        assert exc.value.code == 2
        assert not self._log_path(root).exists()

    def test_rejected_tag_leaves_the_log_byte_identical(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """R9: a refused ``--reason`` appends nothing to an existing log."""
        root = self._root(tmp_path, monkeypatch)

        assert _run([
            "criticality-override", "--feature", "f",
            "--from", "low", "--to", "high", "--reason", "exposure: prior row",
        ]) == 0
        before = self._log_path(root).read_bytes()

        with pytest.raises(SystemExit) as exc:
            _run([
                "criticality-override", "--feature", "f",
                "--from", "high", "--to", "critical", "--reason", "zzz: y",
            ])
        assert exc.value.code == 2
        assert self._log_path(root).read_bytes() == before

    def test_recognized_tag_is_canonicalized_on_disk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """R6: ``' Exposure: …'`` lands with the exact bytes ``exposure: ``."""
        root = self._root(tmp_path, monkeypatch)

        assert _run([
            "complexity-override", "--feature", "f",
            "--from", "simple", "--to", "moderate",
            "--reason", " Exposure: it feeds spec authoring",
        ]) == 0
        reason = self._read_row(root)["reason"]
        assert reason.startswith("exposure: "), reason
        assert reason == "exposure: it feeds spec authoring"

    def test_untagged_prose_is_stored_byte_for_byte(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """R6: a multi-word prefix claims no tag, so nothing is rewritten."""
        root = self._root(tmp_path, monkeypatch)

        assert _run([
            "criticality-override", "--feature", "f",
            "--from", "low", "--to", "medium",
            "--reason", "blast radius: unbounded",
        ]) == 0
        assert self._read_row(root)["reason"] == "blast radius: unbounded"

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_reason_drops_the_key_entirely(
        self, blank: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """R10: an empty or whitespace-only reason writes no ``reason`` key."""
        root = self._root(tmp_path, monkeypatch)

        assert _run([
            "criticality-override", "--feature", "f",
            "--from", "low", "--to", "medium", "--reason", blank,
        ]) == 0
        row = self._read_row(root)
        assert "reason" not in row, row
        assert set(row) == {"ts", "event", "feature", "from", "to"}

    def test_falsy_json_fields_still_emit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """R11: the blank-string drop must not swallow a legitimate ``0``."""
        root = self._root(tmp_path, monkeypatch)

        assert _run([
            "feature-complete", "--feature", "f",
            "--tasks-total", "0", "--rework-cycles", "0",
        ]) == 0
        row = self._read_row(root)
        assert row["tasks_total"] == 0 and isinstance(row["tasks_total"], int)
        assert row["rework_cycles"] == 0 and isinstance(row["rework_cycles"], int)

    def test_rejection_names_the_invoking_verb(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """R4: the diagnostic names this CLI and the offending tag, not refine.

        Asserted on substance only — the exact prefix shape is argparse's and is
        not this test's to pin.
        """
        self._root(tmp_path, monkeypatch)

        with pytest.raises(SystemExit):
            _run([
                "criticality-override", "--feature", "f",
                "--from", "low", "--to", "high", "--reason", "zzz: y",
            ])
        err = capsys.readouterr().err
        assert "cortex-lifecycle-event" in err, err
        assert "zzz" in err, err
        assert "cortex-refine" not in err, err
