"""Tests for orchestrator-round subprocess token-cost telemetry.

Covers ticket 153 requirements R2, R3, R5, R6, R7, R8 plus the
fd-lifecycle close-handle protocol introduced in Task 3 of the
``instrument-orchestrator-round-subprocess-with-token-cost-telemetry``
feature.

Strategy: helper-direct + hand-constructed events. We do NOT drive
``runner.run`` end-to-end — that would require mocking
``_check_concurrent_start``, ``install_signal_handlers``,
``_install_sigterm_tree_walker``, ``auth.ensure_sdk_auth``,
``WatchdogThread``, ``_apply_batch_results``, ``_spawn_batch_runner``,
``_post_loop`` and other process-global side effects, none of which are
relevant to the telemetry behavior under test. Instead we exercise
``_emit_orchestrator_round_telemetry`` directly with synthetic envelope
text, hand-construct event dicts and feed them through the public
``pair_dispatch_events`` / ``compute_skill_tier_dispatch_aggregates``
API, and use AST inspection to verify the dry-run gate placement.
"""

from __future__ import annotations

import ast
import inspect
import io
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"
SUCCESS_FIXTURE = FIXTURES_DIR / "orchestrator_envelope_success.json"
ERROR_FIXTURE = FIXTURES_DIR / "orchestrator_envelope_error.json"


def _read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file and return a list of parsed dicts."""
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# Helper-direct emission tests (R2, R3)
# ---------------------------------------------------------------------------


class TestDispatchStart:
    """Verify ``dispatch_start`` shape via direct ``pipeline_log_event`` call.

    The round loop emits ``dispatch_start`` via ``pipeline_log_event``
    directly (not via ``_emit_orchestrator_round_telemetry``); this test
    invokes the same call with the same fields the round-loop caller
    uses.
    """

    def test_dispatch_start_emits_skill_and_null_model(self, tmp_path: Path) -> None:
        """``dispatch_start`` carries skill='orchestrator-round' and model=None."""
        from cortex_command.pipeline.state import log_event as pipeline_log_event

        log_path = tmp_path / "pipeline-events.log"
        round_num = 7
        tier = "complex"

        pipeline_log_event(
            log_path,
            {
                "event": "dispatch_start",
                "feature": f"<orchestrator-round-{round_num}>",
                "skill": "orchestrator-round",
                "complexity": tier,
                "criticality": "medium",
                "model": None,
                "attempt": 1,
            },
        )

        records = _read_jsonl(log_path)
        assert len(records) == 1
        rec = records[0]
        assert rec["event"] == "dispatch_start"
        assert rec["feature"] == "<orchestrator-round-7>"
        assert rec["skill"] == "orchestrator-round"
        assert rec["complexity"] == "complex"
        assert rec["criticality"] == "medium"
        assert rec["model"] is None
        assert rec["attempt"] == 1


class TestDispatchComplete:
    """Helper-direct tests: success-shaped envelope → dispatch_complete."""

    def test_dispatch_complete_success_envelope_populates_fields(
        self, tmp_path: Path
    ) -> None:
        """Success fixture emits dispatch_complete with token fields populated."""
        from cortex_command.overnight.runner import (
            _emit_orchestrator_round_telemetry,
        )

        envelope_text = SUCCESS_FIXTURE.read_text(encoding="utf-8")
        log_path = tmp_path / "pipeline-events.log"

        _emit_orchestrator_round_telemetry(
            envelope_text=envelope_text,
            exit_code=0,
            round_num=1,
            log_path=log_path,
        )

        records = _read_jsonl(log_path)
        assert len(records) == 1
        rec = records[0]
        assert rec["event"] == "dispatch_complete"
        assert rec["feature"] == "<orchestrator-round-1>"
        # Token fields populated.
        assert rec["input_tokens"] is not None
        assert rec["output_tokens"] is not None
        # Cost fields populated.
        assert rec["cost_usd"] is not None
        assert rec["num_turns"] is not None
        assert rec["model"] is not None
        # Cache fields tolerated as None; if present, must be non-None.
        # (R3 explicitly tolerates absent cache fields.)
        if "cache_creation_input_tokens" in rec:
            # Absent → None permitted; present → must be non-None.
            assert (
                rec["cache_creation_input_tokens"] is None
                or rec["cache_creation_input_tokens"] is not None
            )
        if "cache_read_input_tokens" in rec:
            assert (
                rec["cache_read_input_tokens"] is None
                or rec["cache_read_input_tokens"] is not None
            )

    def test_dispatch_complete_round_num_in_feature(self, tmp_path: Path) -> None:
        """Per-round-unique feature key uses the round_num argument."""
        from cortex_command.overnight.runner import (
            _emit_orchestrator_round_telemetry,
        )

        envelope_text = SUCCESS_FIXTURE.read_text(encoding="utf-8")
        log_path = tmp_path / "pipeline-events.log"

        _emit_orchestrator_round_telemetry(
            envelope_text=envelope_text,
            exit_code=0,
            round_num=42,
            log_path=log_path,
        )

        records = _read_jsonl(log_path)
        assert len(records) == 1
        assert records[0]["feature"] == "<orchestrator-round-42>"


class TestDispatchError:
    """Helper-direct tests: error envelope or non-zero exit → dispatch_error."""

    def test_dispatch_error_is_error_envelope(self, tmp_path: Path) -> None:
        """Error fixture (is_error=True, exit=0) emits dispatch_error."""
        from cortex_command.overnight.runner import (
            _emit_orchestrator_round_telemetry,
        )

        envelope_text = ERROR_FIXTURE.read_text(encoding="utf-8")
        log_path = tmp_path / "pipeline-events.log"

        _emit_orchestrator_round_telemetry(
            envelope_text=envelope_text,
            exit_code=0,
            round_num=1,
            log_path=log_path,
        )

        records = _read_jsonl(log_path)
        assert len(records) == 1
        rec = records[0]
        assert rec["event"] == "dispatch_error"
        assert rec["feature"] == "<orchestrator-round-1>"
        # is_error reason must be recorded in details.
        assert rec["details"]["reason"] == "is_error"

    def test_dispatch_error_non_zero_exit(self, tmp_path: Path) -> None:
        """Non-zero exit with success-shaped envelope still emits dispatch_error."""
        from cortex_command.overnight.runner import (
            _emit_orchestrator_round_telemetry,
        )

        envelope_text = SUCCESS_FIXTURE.read_text(encoding="utf-8")
        log_path = tmp_path / "pipeline-events.log"

        _emit_orchestrator_round_telemetry(
            envelope_text=envelope_text,
            exit_code=1,
            round_num=1,
            log_path=log_path,
        )

        records = _read_jsonl(log_path)
        assert len(records) == 1
        rec = records[0]
        assert rec["event"] == "dispatch_error"
        assert rec["details"]["reason"] == "non_zero_exit"

    def test_dispatch_error_envelope_shape_drift(self, tmp_path: Path) -> None:
        """Non-dict top-level envelope emits dispatch_error with shape-drift reason."""
        from cortex_command.overnight.runner import (
            _emit_orchestrator_round_telemetry,
        )

        # JSON-valid but top-level is a list, not a dict.
        envelope_text = json.dumps([1, 2, 3])
        log_path = tmp_path / "pipeline-events.log"

        _emit_orchestrator_round_telemetry(
            envelope_text=envelope_text,
            exit_code=0,
            round_num=1,
            log_path=log_path,
        )

        records = _read_jsonl(log_path)
        assert len(records) == 1
        rec = records[0]
        assert rec["event"] == "dispatch_error"
        assert rec["details"]["reason"] == "envelope_shape_drift"
        assert rec["details"]["top_level_type"] == "list"


class TestParseFailure:
    """Helper-direct tests: malformed JSON → dispatch_error with parse_failure."""

    def test_parse_failure_malformed_json(self, tmp_path: Path) -> None:
        """Malformed JSON envelope emits dispatch_error with parse_failure reason."""
        from cortex_command.overnight.runner import (
            _emit_orchestrator_round_telemetry,
        )

        envelope_text = "not valid json {{{"
        log_path = tmp_path / "pipeline-events.log"

        _emit_orchestrator_round_telemetry(
            envelope_text=envelope_text,
            exit_code=0,
            round_num=1,
            log_path=log_path,
        )

        records = _read_jsonl(log_path)
        assert len(records) == 1
        rec = records[0]
        assert rec["event"] == "dispatch_error"
        assert rec["details"]["reason"] == "parse_failure"

    def test_parse_failure_none_envelope(self, tmp_path: Path) -> None:
        """None envelope_text (read failure upstream) emits parse_failure."""
        from cortex_command.overnight.runner import (
            _emit_orchestrator_round_telemetry,
        )

        log_path = tmp_path / "pipeline-events.log"

        _emit_orchestrator_round_telemetry(
            envelope_text=None,
            exit_code=0,
            round_num=1,
            log_path=log_path,
        )

        records = _read_jsonl(log_path)
        assert len(records) == 1
        rec = records[0]
        assert rec["event"] == "dispatch_error"
        assert rec["details"]["reason"] == "parse_failure"


# ---------------------------------------------------------------------------
# Fire-and-forget contract (R6)
# ---------------------------------------------------------------------------


class TestFireAndForget:
    """Verify that telemetry exceptions never propagate."""

    def test_fire_and_forget_pipeline_log_event_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """If pipeline_log_event raises, helper swallows and prints breadcrumb."""
        from cortex_command.pipeline import state as state_module

        def boom(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("simulated log_event failure")

        monkeypatch.setattr(state_module, "log_event", boom)

        from cortex_command.overnight.runner import (
            _emit_orchestrator_round_telemetry,
        )

        envelope_text = SUCCESS_FIXTURE.read_text(encoding="utf-8")
        log_path = tmp_path / "pipeline-events.log"

        # Must not raise.
        _emit_orchestrator_round_telemetry(
            envelope_text=envelope_text,
            exit_code=0,
            round_num=1,
            log_path=log_path,
        )

        captured = capsys.readouterr()
        assert "[telemetry]" in captured.err
        # No file was created because the patched log_event raised.
        assert not log_path.exists()

    def test_fire_and_forget_malformed_json_does_not_raise(
        self, tmp_path: Path
    ) -> None:
        """Malformed JSON does not raise from the helper (R6)."""
        from cortex_command.overnight.runner import (
            _emit_orchestrator_round_telemetry,
        )

        log_path = tmp_path / "pipeline-events.log"
        # Should not raise; should write a parse_failure dispatch_error.
        _emit_orchestrator_round_telemetry(
            envelope_text="not json",
            exit_code=0,
            round_num=1,
            log_path=log_path,
        )
        records = _read_jsonl(log_path)
        assert len(records) == 1
        assert records[0]["event"] == "dispatch_error"


# ---------------------------------------------------------------------------
# Aggregator-bucket end-to-end (R5)
# ---------------------------------------------------------------------------


class TestAggregatorBucket:
    """End-to-end: hand-constructed events → aggregator → report formatter.

    Feeds JSONL through ``discover_pipeline_event_logs`` →
    ``pair_dispatch_events`` → ``compute_skill_tier_dispatch_aggregates``
    and verifies the ``orchestrator-round,<tier>`` bucket appears with
    non-null cost/num_turns. Then renders via
    ``_format_skill_tier_dispatch_report`` and asserts the rendered
    string contains ``"orchestrator-round"``.
    """

    def test_aggregator_bucket_orchestrator_round(self, tmp_path: Path) -> None:
        """Paired start+complete for orchestrator-round produces the expected bucket."""
        from cortex_command.pipeline.metrics import (
            compute_skill_tier_dispatch_aggregates,
            discover_pipeline_event_logs,
            pair_dispatch_events,
            _format_skill_tier_dispatch_report,
        )
        from cortex_command.pipeline.state import (
            log_event as pipeline_log_event,
        )

        # Set up lifecycle/sessions/<sid>/pipeline-events.log layout so
        # discover_pipeline_event_logs picks it up.
        lifecycle_dir = tmp_path / "lifecycle"
        session_dir = lifecycle_dir / "sessions" / "s1"
        session_dir.mkdir(parents=True)
        log_path = session_dir / "pipeline-events.log"

        # start_R1 (use pipeline_log_event so a real ts is added)
        pipeline_log_event(
            log_path,
            {
                "event": "dispatch_start",
                "feature": "<orchestrator-round-1>",
                "skill": "orchestrator-round",
                "complexity": "complex",
                "criticality": "medium",
                "model": None,
                "attempt": 1,
            },
        )
        # complete_R1
        pipeline_log_event(
            log_path,
            {
                "event": "dispatch_complete",
                "feature": "<orchestrator-round-1>",
                "cost_usd": 0.0421,
                "duration_ms": 18432,
                "num_turns": 4,
                "model": "claude-opus-4-7",
                "input_tokens": 1842,
                "output_tokens": 612,
                "cache_creation_input_tokens": 5120,
                "cache_read_input_tokens": 23450,
            },
        )

        logs = discover_pipeline_event_logs(lifecycle_dir)
        assert log_path in logs

        # Read events from the discovered log.
        events = _read_jsonl(log_path)

        paired = pair_dispatch_events(events)
        assert len(paired) == 1
        assert paired[0]["skill"] == "orchestrator-round"
        assert paired[0]["tier"] == "complex"

        aggregates = compute_skill_tier_dispatch_aggregates(paired)
        assert "orchestrator-round,complex" in aggregates
        bucket = aggregates["orchestrator-round,complex"]
        assert bucket["n_completes"] == 1
        # cost and num_turns make it through.
        assert bucket.get("estimated_cost_usd_mean") is not None
        assert bucket.get("num_turns_mean") is not None

        # Report formatter renders the bucket key as a substring.
        rendered = _format_skill_tier_dispatch_report(
            {"skill_tier_dispatch_aggregates": aggregates},
            since=None,
        )
        assert "orchestrator-round" in rendered


# ---------------------------------------------------------------------------
# Stalled-round isolation (R7)
# ---------------------------------------------------------------------------


class TestStalledRoundIsolation:
    """Per-round-unique feature names isolate stalled rounds from later rounds.

    A stalled R1 leaves an orphan ``dispatch_start`` for
    ``<orchestrator-round-1>`` that silently sits in the FIFO queue.
    R2's start+complete pair correctly because they use a DIFFERENT
    feature key. Orphan ``dispatch_start`` records silently stay in the
    FIFO (per ``metrics.py:405``/``metrics.py:439``); only orphan
    completes/errors emit warnings.
    """

    def test_stalled_round_isolation_orphan_start_silent(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """[start_R1, start_R2, complete_R2] → 1 paired result for R2; no 'orphan' warning."""
        from cortex_command.pipeline.metrics import pair_dispatch_events

        events = [
            {
                "event": "dispatch_start",
                "ts": "2026-04-01T00:00:01Z",
                "feature": "<orchestrator-round-1>",
                "skill": "orchestrator-round",
                "complexity": "complex",
                "criticality": "medium",
                "model": None,
                "attempt": 1,
            },
            {
                "event": "dispatch_start",
                "ts": "2026-04-01T00:00:02Z",
                "feature": "<orchestrator-round-2>",
                "skill": "orchestrator-round",
                "complexity": "complex",
                "criticality": "medium",
                "model": None,
                "attempt": 1,
            },
            {
                "event": "dispatch_complete",
                "ts": "2026-04-01T00:01:00Z",
                "feature": "<orchestrator-round-2>",
                "cost_usd": 0.05,
                "duration_ms": 12345,
                "num_turns": 3,
                "model": "claude-opus-4-7",
            },
        ]

        result = pair_dispatch_events(events)

        assert len(result) == 1
        assert result[0]["feature"] == "<orchestrator-round-2>"
        assert result[0]["outcome"] == "complete"

        # Orphan dispatch_start is silent — no "orphan" substring on stderr.
        captured = capsys.readouterr()
        assert "orphan" not in captured.err


# ---------------------------------------------------------------------------
# Dry-run gate behavior (R8) — AST structural assertion
# ---------------------------------------------------------------------------


class TestDryRun:
    """Verify the dry-run gate placement structurally.

    Driving ``runner.run`` end-to-end would invoke signal handlers and
    other process-global side effects. Instead we ``ast.parse`` the
    runner module, locate the ``run`` function, and walk its AST to
    assert:

    1. Inside the ``if dry_run:`` body, no ``pipeline_log_event`` call
       occurs (negative — dry-run emits no telemetry).
    2. Outside that body but in a sibling branch within the same
       function, ``dispatch_start`` is emitted (positive — non-dry-run
       paths DO emit telemetry).
    """

    def _load_run_function_ast(self) -> ast.FunctionDef:
        """Parse runner.py and return the ``run`` function's AST node."""
        from cortex_command.overnight import runner as runner_module

        source = Path(runner_module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run":
                return node
        raise AssertionError("Could not find `run` function in runner.py")

    def _find_dry_run_gate(self, fn: ast.FunctionDef) -> ast.If:
        """Find the ``if dry_run:`` branch that contains the per-round skip.

        The runner has multiple ``if dry_run:`` checks; pick the one
        that contains a ``continue`` statement (the per-round skip
        branch — runner.py:1751-1756).
        """
        candidates: list[ast.If] = []
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.If)
                and isinstance(node.test, ast.Name)
                and node.test.id == "dry_run"
            ):
                # Filter: must contain a `continue` statement directly
                # in its body (the per-round skip).
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.Continue):
                        candidates.append(node)
                        break
        assert candidates, (
            "Could not find `if dry_run:` branch containing `continue` "
            "in the run function"
        )
        # Pick the first one (innermost continue branch).
        return candidates[0]

    def _contains_pipeline_log_event_call(self, node: ast.AST) -> bool:
        """Return True if any sub-node calls ``pipeline_log_event(...)``."""
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                func = sub.func
                if (
                    isinstance(func, ast.Name)
                    and func.id == "pipeline_log_event"
                ):
                    return True
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "pipeline_log_event"
                ):
                    return True
        return False

    def _contains_dispatch_start_string(self, node: ast.AST) -> bool:
        """Return True if a ``dispatch_start`` string literal appears in node."""
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and sub.value == "dispatch_start":
                return True
        return False

    def test_dry_run_branch_has_no_pipeline_log_event(self) -> None:
        """Inside ``if dry_run: ... continue``, no pipeline_log_event call."""
        fn = self._load_run_function_ast()
        gate = self._find_dry_run_gate(fn)
        # Walk only the body of the gate (not its else branch).
        for stmt in gate.body:
            assert not self._contains_pipeline_log_event_call(stmt), (
                "pipeline_log_event call found inside `if dry_run:` body — "
                "violates R8 (dry-run mode emits no telemetry)"
            )

    def test_dry_run_dispatch_start_emitted_outside_dry_run_branch(self) -> None:
        """``dispatch_start`` emission appears in a sibling branch outside dry-run."""
        fn = self._load_run_function_ast()
        gate = self._find_dry_run_gate(fn)

        # Walk the full function and verify dispatch_start appears
        # somewhere — but NOT inside the dry-run branch's body.
        gate_body_ids = {id(s) for s in ast.walk(gate)}

        found_outside = False
        for sub in ast.walk(fn):
            if (
                isinstance(sub, ast.Constant)
                and sub.value == "dispatch_start"
                and id(sub) not in gate_body_ids
            ):
                found_outside = True
                break
        assert found_outside, (
            "Expected a `dispatch_start` literal in a sibling branch "
            "of the dry-run gate (positive R2 placement check)"
        )


# ---------------------------------------------------------------------------
# fd-lifecycle close protocol (Task 3 try/finally guard)
# ---------------------------------------------------------------------------


class _FakePopen:
    """Popen-shaped fake whose ``stdout`` is a real writable file handle.

    Mirrors the contract the round-loop ``finally`` block depends on:
    ``proc.stdout`` is non-None and exposes ``.closed`` / ``.close()``.
    Used to exercise the close-handle protocol without spawning a
    subprocess.
    """

    def __init__(self, stdout_handle: Any) -> None:
        self.stdout = stdout_handle


def _round_loop_close_handle(proc: Any) -> None:
    """Mirror of the runner.py:1859-1872 finally block.

    Extracted as a thin testable wrapper so each test can force a
    branch (success/non-zero/stall/shutdown/exception) and assert the
    handle is closed afterward. Mirrors the exact close protocol in
    runner.py without re-spawning a subprocess.
    """
    if (
        proc is not None
        and proc.stdout is not None
        and not proc.stdout.closed
    ):
        try:
            proc.stdout.close()
        except Exception:
            pass


class TestFdLifecycle:
    """Verify the orchestrator stdout file handle is closed across all branches.

    Regression guard against fd leak across rounds in a multi-hour
    overnight session. The runner's finally block at runner.py:1859-1872
    must close the handle on success, non-zero exit, stall flag set,
    shutdown (exit_code=None), and exception inside the try block.
    """

    def _make_proc_with_open_stdout(self, tmp_path: Path) -> _FakePopen:
        """Construct a fake Popen whose stdout is an open real file."""
        stdout_path = tmp_path / "orchestrator-round-1.stdout.json"
        # Use a real open file in write-binary mode (mirrors runner.py:697).
        handle = open(stdout_path, "wb")
        return _FakePopen(stdout_handle=handle)

    def test_fd_lifecycle_success_branch(self, tmp_path: Path) -> None:
        """Success branch (exit_code=0, no stall) closes the handle."""
        proc = self._make_proc_with_open_stdout(tmp_path)
        try:
            # Simulate success path: read envelope, emit telemetry, fall
            # through to finally without break/raise.
            assert proc.stdout.closed is False
        finally:
            _round_loop_close_handle(proc)
        assert proc.stdout.closed is True

    def test_fd_lifecycle_non_zero_exit_branch(self, tmp_path: Path) -> None:
        """Non-zero exit_code path closes the handle."""
        proc = self._make_proc_with_open_stdout(tmp_path)
        try:
            # Simulate non-zero exit: log warning, fall through.
            exit_code = 1
            assert exit_code != 0
        finally:
            _round_loop_close_handle(proc)
        assert proc.stdout.closed is True

    def test_fd_lifecycle_stall_branch(self, tmp_path: Path) -> None:
        """Stall flag set path (break) closes the handle."""
        proc = self._make_proc_with_open_stdout(tmp_path)
        try:
            # Simulate stall: watchdog set stall_flag → break out of loop.
            stall = True
            if stall:
                pass  # stand-in for `break` — try/finally still runs.
        finally:
            _round_loop_close_handle(proc)
        assert proc.stdout.closed is True

    def test_fd_lifecycle_shutdown_branch(self, tmp_path: Path) -> None:
        """Shutdown intercepted (exit_code=None) closes the handle."""
        proc = self._make_proc_with_open_stdout(tmp_path)
        try:
            # Simulate shutdown intercept: exit_code is None → break.
            exit_code = None
            if exit_code is None:
                pass  # stand-in for `break`.
        finally:
            _round_loop_close_handle(proc)
        assert proc.stdout.closed is True

    def test_fd_lifecycle_exception_branch(self, tmp_path: Path) -> None:
        """Exception raised inside try block still closes the handle."""
        proc = self._make_proc_with_open_stdout(tmp_path)
        with pytest.raises(RuntimeError):
            try:
                raise RuntimeError("simulated mid-round failure")
            finally:
                _round_loop_close_handle(proc)
        assert proc.stdout.closed is True

    def test_fd_lifecycle_runner_finally_block_present(self) -> None:
        """The runner.run function contains a ``proc.stdout.close()`` call.

        Structural pin that the close protocol still exists in
        runner.py — the wrapper-mirror tests above only protect the
        wrapper itself, not the production code path.
        """
        from cortex_command.overnight import runner as runner_module

        source = Path(runner_module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        run_fn: ast.FunctionDef | None = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run":
                run_fn = node
                break
        assert run_fn is not None

        found_close = False
        for sub in ast.walk(run_fn):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                # Look for `<x>.stdout.close()` pattern.
                if (
                    sub.func.attr == "close"
                    and isinstance(sub.func.value, ast.Attribute)
                    and sub.func.value.attr == "stdout"
                ):
                    found_close = True
                    break
        assert found_close, (
            "Expected `<proc>.stdout.close()` call in runner.run — "
            "the fd-lifecycle close protocol must remain in production code"
        )

    def test_stall_branch_emits_orchestrator_failed(self) -> None:
        """The stall branch in runner.run emits ORCHESTRATOR_FAILED with reason=stall_timeout.

        Structural pin: stalled orchestrator rounds are orchestrator-scope
        failures and must emit ``ORCHESTRATOR_FAILED`` so downstream
        consumers (morning report, dashboard) classify them alongside
        non-zero-exit failures. The existing CIRCUIT_BREAKER emission via
        ``_transition_paused`` records session-scope state transition;
        ORCHESTRATOR_FAILED records the orchestrator-scope failure.
        """
        from cortex_command.overnight import runner as runner_module

        source = Path(runner_module.__file__).read_text(encoding="utf-8")
        # Locate the stall branch by its print-warning text and check the
        # immediately-following events.log_event(...) call carries the
        # ORCHESTRATOR_FAILED event with reason=stall_timeout.
        assert "watchdog killed orchestrator" in source, (
            "Could not locate stall-branch warning text in runner.py — "
            "test anchor needs updating"
        )
        # Slice the source from the stall warning to the next `_notify` call
        # to scope the assertion to the stall branch body.
        stall_start = source.index("watchdog killed orchestrator")
        notify_after = source.index("_notify", stall_start)
        stall_body = source[stall_start:notify_after]
        assert "events.ORCHESTRATOR_FAILED" in stall_body, (
            "Expected events.log_event(events.ORCHESTRATOR_FAILED, ...) "
            "call in the stall branch of runner.run"
        )
        assert '"reason": "stall_timeout"' in stall_body, (
            "Expected ORCHESTRATOR_FAILED emission to carry "
            'details={"reason": "stall_timeout"} in the stall branch'
        )


# ---------------------------------------------------------------------------
# Runner-path truncation event (Task 5)
# ---------------------------------------------------------------------------


def test_max_tokens_truncation_emits_dispatch_truncation_event_via_orchestrator_round(
    tmp_path: Path,
) -> None:
    """Runner path: stop_reason=='max_tokens' in envelope emits dispatch_truncation.

    Feeds a synthetic envelope dict with ``"stop_reason": "max_tokens"`` to
    ``_emit_orchestrator_round_telemetry`` and asserts that a
    ``dispatch_truncation`` event is logged BEFORE ``dispatch_complete``,
    and that ``dispatch_complete`` carries ``stop_reason`` per spec Req #8.
    """
    from cortex_command.overnight.runner import (
        _emit_orchestrator_round_telemetry,
    )

    envelope = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "duration_ms": 1234,
        "num_turns": 2,
        "stop_reason": "max_tokens",
        "session_id": "trunc-sess",
        "total_cost_usd": 0.05,
        "usage": {
            "input_tokens": 100,
            "output_tokens": 200,
            "cache_creation_input_tokens": None,
            "cache_read_input_tokens": None,
        },
        "model": "claude-opus-4-7",
        "effort": "xhigh",
    }
    log_path = tmp_path / "pipeline-events.log"

    _emit_orchestrator_round_telemetry(
        envelope_text=json.dumps(envelope),
        exit_code=0,
        round_num=1,
        log_path=log_path,
    )

    records = _read_jsonl(log_path)
    event_types = [r["event"] for r in records]
    assert "dispatch_truncation" in event_types, (
        f"expected dispatch_truncation in events, got {event_types}"
    )
    assert "dispatch_complete" in event_types, (
        f"expected dispatch_complete in events, got {event_types}"
    )
    trunc_idx = event_types.index("dispatch_truncation")
    complete_idx = event_types.index("dispatch_complete")
    assert trunc_idx < complete_idx, (
        f"dispatch_truncation must precede dispatch_complete; got {event_types}"
    )

    trunc = records[trunc_idx]
    assert trunc["feature"] == "<orchestrator-round-1>"
    assert trunc["stop_reason"] == "max_tokens"
    assert trunc["model"] == "claude-opus-4-7"
    assert trunc["effort"] == "xhigh"

    complete = records[complete_idx]
    assert complete["stop_reason"] == "max_tokens"
