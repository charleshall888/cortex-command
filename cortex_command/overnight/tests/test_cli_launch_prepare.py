"""Handler tests for ``cortex overnight launch`` / ``prepare`` (Task 15, R18).

These two verbs promote the planning helpers
(``select_overnight_batch``, ``render_session_plan``,
``validate_target_repos``, ``bootstrap_session``, ``extract_batch_specs``)
to a stable CLI surface so the ``/overnight`` skill flow no longer shells
into internal Python APIs (prohibited by the bare-Python-import gate). This
module asserts the verb-deployment contract:

  - ``launch`` is the mutating umbrella verb — select → validate repos →
    render → bootstrap → extract — and returns a structured envelope
    describing the bootstrapped session. It does NOT log ``session_start``:
    the runner logs exactly one fire-time ``session_start`` at session start
    (R11), so pre-logging here would double-/triple-log.
  - ``prepare`` is read-only — select → render — and emits the rendered plan
    as JSON WITHOUT mutating any state (no bootstrap, no worktree, no
    telemetry).

The planning helpers are monkeypatched at their source-module attributes so
the tests are hermetic: no real worktree is created and no real backlog is
read. The handlers import those helpers lazily as
``backlog_module``/``plan_module``, so patching the source module attribute
is the seam the lazy import resolves through.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from cortex_command.overnight import backlog as backlog_module
from cortex_command.overnight import cli_handler
from cortex_command.overnight import events as events_module
from cortex_command.overnight import plan as plan_module
from cortex_command.overnight.backlog import BacklogItem, Batch, SelectionResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_selection() -> SelectionResult:
    """Build a minimal SelectionResult with one batch of two items."""
    items = [
        BacklogItem(
            id=101,
            title="First feature",
            status="backlog",
            priority="high",
            type="feature",
        ),
        BacklogItem(
            id=102,
            title="Second feature",
            status="backlog",
            priority="medium",
            type="bug",
        ),
    ]
    batch = Batch(items=items, batch_context="auth, ui", batch_id=1)
    return SelectionResult(
        batches=[batch],
        ineligible=[],
        summary="Selected 2 items in 1 batches",
        intra_session_deps={},
    )


def _prepare_args(*, fmt: str = "json", backlog_dir: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        backlog_dir=backlog_dir,
        time_limit_hours=6,
        batch_size_cap=5,
        format=fmt,
    )


def _launch_args(
    *,
    fmt: str = "json",
    backlog_dir: str | None = None,
    only: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        backlog_dir=backlog_dir,
        time_limit_hours=6,
        batch_size_cap=5,
        format=fmt,
        only=only,
    )


def _curated_selection() -> SelectionResult:
    """A 3-feature selection where ``gamma`` is intra-session-blocked by ``beta``.

    Two batches: {alpha, beta} in round 1, {gamma} in round 2. Slugs are pinned
    via ``lifecycle_slug`` so ``resolve_slug()`` is deterministic, and
    ``intra_session_deps`` records gamma→beta so the dependency-closure path is
    exercisable.
    """
    alpha = BacklogItem(
        id=1, title="Alpha", status="backlog", priority="high",
        type="feature", lifecycle_slug="alpha",
    )
    beta = BacklogItem(
        id=2, title="Beta", status="backlog", priority="medium",
        type="feature", lifecycle_slug="beta",
    )
    gamma = BacklogItem(
        id=3, title="Gamma", status="backlog", priority="low",
        type="feature", lifecycle_slug="gamma",
    )
    return SelectionResult(
        batches=[
            Batch(items=[alpha, beta], batch_context="x", batch_id=1),
            Batch(items=[gamma], batch_context="y", batch_id=2),
        ],
        ineligible=[],
        summary="Selected 3 items in 2 batches",
        intra_session_deps={"gamma": ["beta"]},
    )


# ---------------------------------------------------------------------------
# filter_selection_to_curated_set — pure post-filter helper (#323)
# ---------------------------------------------------------------------------


def test_curated_subset_restricts_to_kept_slugs() -> None:
    """A curated subset keeps only the named slugs and drops emptied batches."""
    restricted, error = backlog_module.filter_selection_to_curated_set(
        _curated_selection(), ["alpha"]
    )
    assert error is None
    kept = {
        item.resolve_slug() for b in restricted.batches for item in b.items
    }
    assert kept == {"alpha"}
    # The beta/gamma batch (and gamma's now-irrelevant dep) are dropped.
    assert restricted.intra_session_deps == {}


def test_curated_closed_set_keeps_dependent_and_blocker() -> None:
    """Keeping both a dependent and its in-session blocker is dependency-closed."""
    restricted, error = backlog_module.filter_selection_to_curated_set(
        _curated_selection(), ["beta", "gamma"]
    )
    assert error is None
    kept = {
        item.resolve_slug() for b in restricted.batches for item in b.items
    }
    assert kept == {"beta", "gamma"}
    assert restricted.intra_session_deps == {"gamma": ["beta"]}


def test_curated_drop_blocker_keep_dependent_refuses() -> None:
    """Dropping an in-session blocker but keeping its dependent fails loud."""
    restricted, error = backlog_module.filter_selection_to_curated_set(
        _curated_selection(), ["gamma"]
    )
    assert restricted is None
    assert error is not None
    assert error["error"] == "dependency_not_closed"
    assert "beta" in error["blockers"]
    assert "gamma" in error["dependents"]
    assert "beta" in error["message"]


def test_curated_unknown_slug_refuses() -> None:
    """A curated slug absent from the launch-time selection is surfaced, not dropped."""
    restricted, error = backlog_module.filter_selection_to_curated_set(
        _curated_selection(), ["nonexistent"]
    )
    assert restricted is None
    assert error is not None
    assert error["error"] == "ineligible_slug"
    assert "nonexistent" in error["slugs"]


# ---------------------------------------------------------------------------
# prepare — read-only, renders plan JSON, mutates nothing
# ---------------------------------------------------------------------------


def test_prepare_renders_plan_json_without_mutating_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """``prepare`` emits the rendered plan JSON and never bootstraps/mutates."""
    selection = _make_selection()
    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda *a, **k: tmp_path)
    monkeypatch.setattr(
        backlog_module, "select_overnight_batch", lambda **kw: selection
    )
    monkeypatch.setattr(
        plan_module,
        "render_session_plan",
        lambda selection, time_limit_hours: "# Overnight Session Plan\n\nrendered",
    )

    # Tripwires: prepare must NOT call any mutating helper.
    def _boom(*a, **kw):  # pragma: no cover - asserts non-invocation
        raise AssertionError("prepare must not mutate state")

    monkeypatch.setattr(plan_module, "bootstrap_session", _boom)
    monkeypatch.setattr(plan_module, "extract_batch_specs", _boom)
    monkeypatch.setattr(events_module, "log_event", _boom)

    rc = cli_handler.handle_prepare(_prepare_args(fmt="json"))
    captured = capsys.readouterr()

    assert rc == 0, f"expected exit 0; stderr={captured.err!r}"
    payload = json.loads(captured.out.strip())
    assert payload["schema_version"] == "2.0"
    assert payload["prepared"] is True
    assert payload["plan_markdown"] == "# Overnight Session Plan\n\nrendered"
    # Structured selection summary is rendered for the Approve gate.
    assert payload["selection"]["selected_count"] == 2
    assert payload["selection"]["batch_count"] == 1
    assert payload["selection"]["batches"][0]["items"][0]["id"] == 101

    # No session directory was created under the repo (no mutation).
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    assert not sessions_root.exists()


def test_prepare_selection_failure_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A selection exception surfaces as a non-zero exit with an error envelope."""
    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda *a, **k: tmp_path)

    def _raise(**kw):
        raise ValueError("malformed frontmatter")

    monkeypatch.setattr(backlog_module, "select_overnight_batch", _raise)

    rc = cli_handler.handle_prepare(_prepare_args(fmt="json"))
    captured = capsys.readouterr()

    assert rc == 1
    payload = json.loads(captured.out.strip())
    assert payload["error"] == "selection_failed"


# ---------------------------------------------------------------------------
# launch — mutating umbrella verb, returns a structured envelope
# ---------------------------------------------------------------------------


def test_launch_returns_structured_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """``launch`` fuses select→validate→render→bootstrap→extract.

    It deliberately does NOT log ``session_start`` at prep time — the runner
    logs exactly one fire-time ``session_start`` (R11).
    """
    selection = _make_selection()
    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda *a, **k: tmp_path)
    monkeypatch.setattr(
        backlog_module, "select_overnight_batch", lambda **kw: selection
    )
    monkeypatch.setattr(
        plan_module,
        "render_session_plan",
        lambda selection, time_limit_hours: "# plan\n",
    )
    monkeypatch.setattr(plan_module, "validate_target_repos", lambda sel: [])

    # Stub bootstrap_session: return a state-like object plus a real on-disk
    # session dir mirroring what the real helper persists.
    session_id = "overnight-2026-06-01-2200"
    state_dir = tmp_path / "cortex" / "lifecycle" / "sessions" / session_id
    state_dir.mkdir(parents=True, exist_ok=True)
    worktree_path = str(tmp_path / "worktree")

    class _FakeState:
        def __init__(self) -> None:
            self.session_id = session_id
            self.features = {"first-feature": object(), "second-feature": object()}
            self.worktree_path = worktree_path

    fake_state = _FakeState()

    bootstrap_calls: list = []

    def _fake_bootstrap(sel, plan_content, project_root=None):
        bootstrap_calls.append((sel, plan_content, project_root))
        return (fake_state, state_dir)

    monkeypatch.setattr(plan_module, "bootstrap_session", _fake_bootstrap)

    extract_calls: list = []

    def _fake_extract(state, root):
        extract_calls.append((state, root))
        return [Path("cortex/lifecycle/first-feature/spec.md")]

    monkeypatch.setattr(plan_module, "extract_batch_specs", _fake_extract)

    # Tripwire: launch must NOT pre-log session_start (R11). Record any
    # log_event call so we can assert no session_start was written.
    log_calls: list = []

    def _fake_log(*, event, round, details=None, log_path=None):
        log_calls.append((event, round, details, log_path))

    monkeypatch.setattr(events_module, "log_event", _fake_log)

    rc = cli_handler.handle_launch(_launch_args(fmt="json"))
    captured = capsys.readouterr()

    assert rc == 0, f"expected exit 0; stderr={captured.err!r}"
    payload = json.loads(captured.out.strip())
    assert payload["schema_version"] == "2.0"
    assert payload["launched"] is True
    assert payload["session_id"] == session_id
    assert payload["state_dir"] == str(state_dir)
    assert payload["state_path"] == str(state_dir / "overnight-state.json")
    assert payload["worktree_path"] == worktree_path
    assert payload["extracted_specs"] == ["cortex/lifecycle/first-feature/spec.md"]
    assert payload["selection"]["selected_count"] == 2
    # No prep-time telemetry warning is emitted (launch logs nothing).
    assert "telemetry_warning" not in payload

    # The umbrella verb actually drove each fused step.
    assert len(bootstrap_calls) == 1
    assert bootstrap_calls[0][2] == tmp_path  # project_root forwarded
    assert extract_calls and extract_calls[0][1] == Path(worktree_path)
    # launch does NOT pre-log session_start — the runner logs it at fire (R11).
    assert not any(call[0] == "session_start" for call in log_calls)


def test_launch_aborts_before_mutation_on_invalid_repos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A non-empty repo-validation list aborts before bootstrap_session runs."""
    selection = _make_selection()
    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda *a, **k: tmp_path)
    monkeypatch.setattr(
        backlog_module, "select_overnight_batch", lambda **kw: selection
    )
    monkeypatch.setattr(
        plan_module,
        "render_session_plan",
        lambda selection, time_limit_hours: "# plan\n",
    )
    monkeypatch.setattr(
        plan_module, "validate_target_repos", lambda sel: ["~/broken-repo"]
    )

    def _boom(*a, **kw):  # pragma: no cover - asserts non-invocation
        raise AssertionError("bootstrap must not run when repos are invalid")

    monkeypatch.setattr(plan_module, "bootstrap_session", _boom)

    rc = cli_handler.handle_launch(_launch_args(fmt="json"))
    captured = capsys.readouterr()

    assert rc == 1
    payload = json.loads(captured.out.strip())
    assert payload["error"] == "invalid_target_repos"
    assert payload["repos"] == ["~/broken-repo"]


def test_launch_nothing_ready_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """An empty selection (zero batches) is a non-zero 'nothing ready' result."""
    empty = SelectionResult(batches=[], ineligible=[], summary="nothing")
    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda *a, **k: tmp_path)
    monkeypatch.setattr(
        backlog_module, "select_overnight_batch", lambda **kw: empty
    )

    def _boom(*a, **kw):  # pragma: no cover
        raise AssertionError("bootstrap must not run with nothing ready")

    monkeypatch.setattr(plan_module, "bootstrap_session", _boom)

    rc = cli_handler.handle_launch(_launch_args(fmt="json"))
    captured = capsys.readouterr()

    assert rc == 1
    payload = json.loads(captured.out.strip())
    assert payload["error"] == "nothing_ready"


# ---------------------------------------------------------------------------
# launch --only — curated frozen-list handoff (#323)
# ---------------------------------------------------------------------------


def _patch_launch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    selection: SelectionResult,
) -> list:
    """Patch the full launch pipeline; return the list capturing bootstrap calls.

    The bootstrap fake derives its features from the selection it receives, so a
    test can assert that exactly the curated subset flowed through to bootstrap.
    """
    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda *a, **k: tmp_path)
    monkeypatch.setattr(
        backlog_module, "select_overnight_batch", lambda **kw: selection
    )
    monkeypatch.setattr(
        plan_module, "render_session_plan", lambda selection, time_limit_hours: "# plan\n"
    )
    monkeypatch.setattr(plan_module, "validate_target_repos", lambda sel: [])

    session_id = "overnight-2026-06-30-2200"
    state_dir = tmp_path / "cortex" / "lifecycle" / "sessions" / session_id
    state_dir.mkdir(parents=True, exist_ok=True)
    worktree_path = str(tmp_path / "worktree")

    bootstrap_calls: list = []

    def _fake_bootstrap(sel, plan_content, project_root=None):
        bootstrap_calls.append(sel)
        feats = {
            item.resolve_slug(): object()
            for b in sel.batches
            for item in b.items
        }

        class _FakeState:
            def __init__(self) -> None:
                self.session_id = session_id
                self.features = feats
                self.worktree_path = worktree_path

        return (_FakeState(), state_dir)

    monkeypatch.setattr(plan_module, "bootstrap_session", _fake_bootstrap)
    monkeypatch.setattr(plan_module, "extract_batch_specs", lambda state, root: [])
    monkeypatch.setattr(
        events_module, "log_event", lambda **kw: None
    )
    return bootstrap_calls


def test_launch_only_executes_curated_subset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """``--only alpha`` bootstraps exactly {alpha}, excluding beta/gamma (R2/R5)."""
    bootstrap_calls = _patch_launch_pipeline(monkeypatch, tmp_path, _curated_selection())

    rc = cli_handler.handle_launch(_launch_args(fmt="json", only="alpha"))
    captured = capsys.readouterr()

    assert rc == 0, f"expected exit 0; stderr={captured.err!r}"
    assert len(bootstrap_calls) == 1
    bootstrapped_slugs = {
        item.resolve_slug() for b in bootstrap_calls[0].batches for item in b.items
    }
    assert bootstrapped_slugs == {"alpha"}
    payload = json.loads(captured.out.strip())
    assert payload["selection"]["selected_count"] == 1


def test_launch_only_none_is_full_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Absent ``--only`` (None), launch bootstraps the full selection unchanged (R2b)."""
    bootstrap_calls = _patch_launch_pipeline(monkeypatch, tmp_path, _curated_selection())

    rc = cli_handler.handle_launch(_launch_args(fmt="json", only=None))
    captured = capsys.readouterr()

    assert rc == 0, f"expected exit 0; stderr={captured.err!r}"
    bootstrapped_slugs = {
        item.resolve_slug() for b in bootstrap_calls[0].batches for item in b.items
    }
    assert bootstrapped_slugs == {"alpha", "beta", "gamma"}


def test_launch_only_empty_returns_nothing_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """An empty ``--only`` (operator removed everything) refuses with nothing_ready."""
    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda *a, **k: tmp_path)
    monkeypatch.setattr(
        backlog_module, "select_overnight_batch", lambda **kw: _curated_selection()
    )

    def _boom(*a, **kw):  # pragma: no cover - asserts non-invocation
        raise AssertionError("bootstrap must not run on an empty curated set")

    monkeypatch.setattr(plan_module, "bootstrap_session", _boom)

    rc = cli_handler.handle_launch(_launch_args(fmt="json", only="  "))
    captured = capsys.readouterr()

    assert rc == 1
    payload = json.loads(captured.out.strip())
    assert payload["error"] == "nothing_ready"


def test_launch_only_dependency_not_closed_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """``--only gamma`` (drops blocker beta) refuses fail-loud before mutation (R3)."""
    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda *a, **k: tmp_path)
    monkeypatch.setattr(
        backlog_module, "select_overnight_batch", lambda **kw: _curated_selection()
    )

    def _boom(*a, **kw):  # pragma: no cover - asserts non-invocation
        raise AssertionError("bootstrap must not run on a non-closed curated set")

    monkeypatch.setattr(plan_module, "bootstrap_session", _boom)
    monkeypatch.setattr(plan_module, "validate_target_repos", _boom)

    rc = cli_handler.handle_launch(_launch_args(fmt="json", only="gamma"))
    captured = capsys.readouterr()

    assert rc == 1
    payload = json.loads(captured.out.strip())
    assert payload["error"] == "dependency_not_closed"
    assert "beta" in payload["blockers"]
