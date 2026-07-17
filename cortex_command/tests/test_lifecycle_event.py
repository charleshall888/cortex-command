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
            fields=[("str", "worktree_path", str(worktree_root))],
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

        exempt = {"plan_comparison", "clarify_critic", "pr_opened"}
        emitted = {ev for ev, _specs in _EVENT_SUBCOMMANDS.values()}
        assert emitted.isdisjoint(exempt), emitted & exempt
