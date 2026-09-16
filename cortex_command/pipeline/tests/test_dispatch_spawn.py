"""Dispatch-level pins for the ``claude`` spawn seam.

Every test drives :func:`cortex_command.pipeline.dispatch.dispatch_task`
through the frame-level double in :mod:`cortex_command.tests._claude_double`
(patched over ``dispatch.run_claude``), never through a classifier call in
isolation, so a regression in how frames reach classification is visible here.

Covers spec R2 (argv), R9 (corpus isolation), R10 (every ``ERROR_RECOVERY`` key
reaches ``retry.retry_task`` and gets the action it names), R11 (the operator
message for an unspawnable CLI), R12 (API-fault halt chain), R13 (turn limit)
and R14 (failure diagnostics).
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import itertools
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import cortex_command.overnight.state as overnight_state_module
import cortex_command.pipeline.dispatch as dispatch
import cortex_command.pipeline.retry as retry
from cortex_command.claude_stream import ClaudeSpawnError
from cortex_command.tests._claude_double import (
    assistant_frame,
    fake_run_claude,
    rate_limit_frame,
    result_frame,
    system_frame,
)

FAKE_CLI = "/fake/bin/claude"
PROMPT = "TASK-SENTINEL: implement the widget exactly as specified"
SYSTEM_PROMPT = "SYSTEM-SENTINEL"
SIMPLE_MAX_TURNS = dispatch.TIER_CONFIG["simple"]["max_turns"]

_SUCCESS = {"frames": [assistant_frame("done"), result_frame()], "exit_code": 0}


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolate a dispatch: fake CLI path, tmp session dir, tmp worktree."""
    monkeypatch.setenv("CORTEX_CLAUDE_CLI_PATH", FAKE_CLI)
    monkeypatch.setattr(
        overnight_state_module,
        "session_dir",
        lambda session_id, lifecycle_root=None: tmp_path / "sessions" / session_id,
    )
    worktree = tmp_path / "wt" / "fix-failing-tests"
    worktree.mkdir(parents=True)
    return SimpleNamespace(tmp=tmp_path, worktree=worktree)


class _Scripted:
    """``run_claude`` stand-in serving one scripted run per call.

    Each run spec is a dict of :func:`fake_run_claude` keyword arguments; the
    last spec repeats once the list runs out. ``raise_mid_stream`` makes the
    run yield its frames and then raise that exception from ``frames()``.
    Every call's argv/prompt/cwd/env is recorded in ``calls``.
    """

    def __init__(self, *runs: dict[str, Any]) -> None:
        self.runs = list(runs)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv, *, prompt, cwd, env, on_stderr=None):
        spec = dict(self.runs[min(len(self.calls), len(self.runs) - 1)])
        raise_mid_stream: Optional[BaseException] = spec.pop("raise_mid_stream", None)
        capture: dict[str, Any] = {}
        run = fake_run_claude(**spec, capture=capture)(
            argv, prompt=prompt, cwd=cwd, env=env, on_stderr=on_stderr
        )
        self.calls.append(capture)
        if raise_mid_stream is not None:
            scripted_frames = list(spec.get("frames", ()))

            async def _frames():
                for frame in scripted_frames:
                    yield frame
                raise raise_mid_stream

            run.frames = _frames
        return run


def _dispatch(env, monkeypatch, *runs: dict[str, Any], **kwargs: Any):
    """Run one ``dispatch_task`` against scripted runs; return (result, scripted)."""
    scripted = _Scripted(*runs)
    monkeypatch.setattr(dispatch, "run_claude", scripted)
    call = {
        "feature": "feat",
        "task": PROMPT,
        "worktree_path": env.worktree,
        "complexity": "simple",
        "system_prompt": SYSTEM_PROMPT,
        "skill": "implement",
    }
    call.update(kwargs)
    result = asyncio.run(dispatch.dispatch_task(**call))
    return result, scripted


def _retry(env, monkeypatch, *runs: dict[str, Any], max_retries: int = 1):
    """Run ``retry.retry_task`` over the real dispatch with the double patched.

    Returns ``(retry_result, dispatch_kwargs, dispatch_results, scripted)``,
    one entry per dispatch attempt in the two lists.
    """
    scripted = _Scripted(*runs)
    monkeypatch.setattr(dispatch, "run_claude", scripted)
    # Unique diffs keep the circuit breaker out of the way; no real git.
    counter = itertools.count()
    monkeypatch.setattr(retry, "_get_worktree_diff", lambda _p: f"diff-{next(counter)}")
    monkeypatch.setattr(retry, "cleanup_stale_lock", lambda *a, **k: False)

    dispatch_kwargs: list[dict[str, Any]] = []
    dispatch_results: list[dispatch.DispatchResult] = []
    real_dispatch = retry.dispatch_task

    async def _spy(**kw):
        dispatch_kwargs.append(kw)
        res = await real_dispatch(**kw)
        dispatch_results.append(res)
        return res

    monkeypatch.setattr(retry, "dispatch_task", _spy)
    learnings = env.tmp / "learnings"
    learnings.mkdir(exist_ok=True)
    result = asyncio.run(
        retry.retry_task(
            feature="feat",
            task=PROMPT,
            worktree_path=env.worktree,
            complexity="simple",
            system_prompt=SYSTEM_PROMPT,
            learnings_dir=learnings,
            max_retries=max_retries,
            criticality="medium",
            skill="implement",
        )
    )
    return result, dispatch_kwargs, dispatch_results, scripted


def _flag_value(argv: list[str], flag: str) -> str:
    assert flag in argv, f"{flag} missing from argv {argv!r}"
    idx = argv.index(flag)
    assert idx + 1 < len(argv), f"{flag} has no value in argv {argv!r}"
    return argv[idx + 1]


# ---------------------------------------------------------------------------
# R2: every option reaches the CLI; the prompt travels on stdin
# ---------------------------------------------------------------------------


def test_argv_carries_every_dispatch_option(env, monkeypatch):
    result, scripted = _dispatch(
        env, monkeypatch, _SUCCESS, complexity="complex", criticality="high",
    )
    assert result.success, result.error_detail
    argv = scripted.calls[0]["argv"]
    tier = dispatch.TIER_CONFIG["complex"]

    assert argv[0] == FAKE_CLI
    assert "-p" in argv
    assert _flag_value(argv, "--output-format") == "stream-json"
    assert "--verbose" in argv
    assert _flag_value(argv, "--max-turns") == str(tier["max_turns"])
    assert float(_flag_value(argv, "--max-budget-usd")) == tier["max_budget_usd"]
    assert _flag_value(argv, "--permission-mode") == "bypassPermissions"
    assert _flag_value(argv, "--allowedTools") == "Read,Write,Edit,Bash,Glob,Grep"
    assert _flag_value(argv, "--system-prompt") == SYSTEM_PROMPT
    assert Path(_flag_value(argv, "--settings")).is_file()
    assert _flag_value(argv, "--effort") == dispatch.resolve_effort("complex", "high", "implement")
    assert scripted.calls[0]["cwd"] == str(env.worktree)


def test_prompt_goes_on_stdin_not_argv(env, monkeypatch):
    result, scripted = _dispatch(env, monkeypatch, _SUCCESS)
    assert result.success, result.error_detail
    call = scripted.calls[0]
    assert call["prompt"] == PROMPT
    assert not any("TASK-SENTINEL" in arg for arg in call["argv"])


# ---------------------------------------------------------------------------
# R9: only assistant text (and stderr) enters the keyword corpus
# ---------------------------------------------------------------------------


def test_system_frame_text_does_not_reach_keyword_corpus(env, monkeypatch):
    # The init frame's cwd names the worktree, and a hook frame carries
    # test-failure words; if either leaked into the corpus the run would
    # classify as agent_test_failure.
    run = {
        "frames": [
            system_frame(subtype="init", cwd="/wt/fix-failing-tests"),
            system_frame(subtype="hook_response", output="3 tests failed; pytest exit 1"),
        ],
        "exit_code": 1,
    }
    result, _ = _dispatch(env, monkeypatch, run)
    assert not result.success
    assert result.error_type != "agent_test_failure"


def test_rejected_rate_limit_frame_classifies_through_structured_status(env, monkeypatch):
    run = {"frames": [rate_limit_frame(status="rejected", rateLimitType="five_hour")], "exit_code": 1}
    result, _ = _dispatch(env, monkeypatch, run)
    assert result.error_type == "api_rate_limit"
    # No rate-limit words anywhere the corpus could have read them.
    text = (result.output + "\n" + (result.diagnostics.child_stderr or "")).lower()
    for phrase in dispatch._RATE_LIMIT_PATTERNS:
        assert phrase not in text


def test_allowed_rate_limit_frame_is_not_a_rate_limit(env, monkeypatch):
    run = {"frames": [rate_limit_frame(status="allowed", rateLimitType="five_hour")], "exit_code": 1}
    result, _ = _dispatch(env, monkeypatch, run)
    assert result.error_type == "task_failure"


# ---------------------------------------------------------------------------
# R10: each ERROR_RECOVERY key, driven through retry.retry_task
# ---------------------------------------------------------------------------

_RETRY_CASES = {
    "agent_timeout": {"frames": [assistant_frame("The command timed out after 600s.")], "exit_code": 1},
    "agent_test_failure": {"frames": [assistant_frame("3 tests failed in the suite.")], "exit_code": 1},
    "agent_confused": {"frames": [assistant_frame("I'm not sure which module you mean.")], "exit_code": 1},
    "task_failure": {"frames": [], "exit_code": 1},
    "turn_limit_exhausted": {
        "frames": [result_frame(is_error=True, stop_reason="tool_use", num_turns=SIMPLE_MAX_TURNS + 1)],
        "exit_code": 1,
    },
    "unknown": {
        "frames": [assistant_frame("working on it")],
        "exit_code": 0,
        "raise_mid_stream": RuntimeError("stream broke"),
    },
}

_PAUSE_CASES = {
    "agent_refusal": {"frames": [assistant_frame("I cannot make that change.")], "exit_code": 1},
    "infrastructure_failure": {
        "frames": [],
        "spawn_error": ClaudeSpawnError(FAKE_CLI, FileNotFoundError(2, "No such file or directory")),
    },
    "budget_exhausted": {
        "frames": [result_frame(is_error=True, subtype="error_max_budget_usd")],
        "exit_code": 1,
    },
    "api_rate_limit": {"frames": [rate_limit_frame(status="rejected")], "exit_code": 1},
    "api_unavailable": {
        "frames": [result_frame(is_error=True, subtype="success", terminal_reason="api_error")],
        "exit_code": 1,
    },
}


def test_cases_cover_every_error_recovery_key():
    covered = set(_RETRY_CASES) | set(_PAUSE_CASES) | {"effort_unsupported"}
    assert covered == set(dispatch.ERROR_RECOVERY)


@pytest.mark.parametrize("error_type", sorted(_RETRY_CASES))
def test_retry_keys_dispatch_a_second_attempt(env, monkeypatch, error_type):
    assert dispatch.ERROR_RECOVERY[error_type] == "retry"
    result, kwargs, results, _ = _retry(env, monkeypatch, _RETRY_CASES[error_type])
    assert results[0].error_type == error_type
    assert len(kwargs) == 2
    assert [k["attempt"] for k in kwargs] == [1, 2]
    assert result.attempts == 2
    assert not result.success


@pytest.mark.parametrize("error_type", sorted(_PAUSE_CASES))
def test_pause_keys_pause_after_one_attempt(env, monkeypatch, error_type):
    assert dispatch.ERROR_RECOVERY[error_type] in ("pause_human", "pause_session")
    result, kwargs, results, _ = _retry(env, monkeypatch, _PAUSE_CASES[error_type])
    assert results[0].error_type == error_type
    assert len(kwargs) == 1
    assert result.paused is True
    assert result.attempts == 1
    assert result.error_type == error_type


def test_effort_unsupported_clamps_second_dispatch_to_max(env, monkeypatch):
    rejected = {
        "frames": [],
        "exit_code": 1,
        "stderr_lines": ["error: option '--effort <level>' argument 'xhigh' is invalid."],
    }
    result, kwargs, results, scripted = _retry(env, monkeypatch, rejected, _SUCCESS)
    assert results[0].error_type == "effort_unsupported"
    assert len(kwargs) == 2
    assert kwargs[0]["effort_override"] is None
    assert kwargs[1]["effort_override"] == "max"
    assert _flag_value(scripted.calls[1]["argv"], "--effort") == "max"
    assert result.success


# ---------------------------------------------------------------------------
# R11: an unspawnable claude names the binary and says to install Claude Code
# ---------------------------------------------------------------------------


def test_nonexistent_cli_path_is_infrastructure_failure_with_install_hint(env, monkeypatch):
    missing = "/nonexistent/claude"
    monkeypatch.setenv("CORTEX_CLAUDE_CLI_PATH", missing)
    # The real run_claude: the spawn itself must fail.
    result = asyncio.run(
        dispatch.dispatch_task(
            feature="feat",
            task=PROMPT,
            worktree_path=env.worktree,
            complexity="simple",
            system_prompt=SYSTEM_PROMPT,
            skill="implement",
        )
    )
    assert result.error_type == "infrastructure_failure"
    assert missing in result.error_detail
    assert "install Claude Code" in result.error_detail


# ---------------------------------------------------------------------------
# R12: API-wide faults are named and halt the session; budget stays budget
# ---------------------------------------------------------------------------


def test_api_error_result_is_session_halting_not_budget(env, monkeypatch):
    from cortex_command.overnight import feature_executor

    run = {
        "frames": [result_frame(is_error=True, subtype="success", terminal_reason="api_error")],
        "exit_code": 1,
    }
    result, _ = _dispatch(env, monkeypatch, run)
    assert result.error_type != "budget_exhausted"
    assert result.error_type in feature_executor._SESSION_HALT_ERROR_TYPES
    assert result.error_type == "api_unavailable"


def test_budget_subtype_is_budget_exhausted(env, monkeypatch):
    run = {"frames": [result_frame(is_error=True, subtype="error_max_budget_usd")], "exit_code": 1}
    result, _ = _dispatch(env, monkeypatch, run)
    assert result.error_type == "budget_exhausted"


def _runner_round_loop_halt_predicates() -> list[ast.If]:
    """Return every ``if <x>.paused_reason in _SESSION_HALT_ERROR_TYPES:`` in
    ``runner.run`` whose body breaks the loop."""
    from cortex_command.overnight import runner

    tree = ast.parse(textwrap.dedent(inspect.getsource(runner.run)))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Attribute)
            and test.left.attr == "paused_reason"
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.In)
            and isinstance(test.comparators[0], ast.Name)
            and test.comparators[0].id == "_SESSION_HALT_ERROR_TYPES"
        ):
            continue
        if any(isinstance(n, ast.Break) for n in ast.walk(node)):
            found.append(node)
    return found


def test_api_error_halts_the_session_end_to_end(env, monkeypatch):
    """dispatch → retry → execute_feature → run_batch → state.paused_reason,
    then the predicate runner.run's round loop breaks on."""
    from cortex_command.overnight import orchestrator, runner
    from cortex_command.overnight.orchestrator import BatchConfig, run_batch
    from cortex_command.overnight.state import (
        OvernightFeatureStatus,
        OvernightState,
        load_state,
        save_state,
    )
    from cortex_command.pipeline.parser import FeaturePlan, FeatureTask

    tmp = env.tmp
    (tmp / "cortex" / "lifecycle").mkdir(parents=True)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp))
    monkeypatch.setattr(dispatch, "run_claude", _Scripted(_PAUSE_CASES["api_unavailable"]))
    monkeypatch.setattr(retry, "cleanup_stale_lock", lambda *a, **k: False)
    monkeypatch.setattr(retry, "_get_worktree_diff", lambda _p: "")

    state_path = tmp / "overnight-state.json"
    save_state(
        OvernightState(
            session_id="s1",
            plan_ref="plan.md",
            phase="executing",
            project_root=str(tmp),
            features={"feat-a": OvernightFeatureStatus(recovery_attempts=0)},
        ),
        state_path,
    )
    config = BatchConfig(
        batch_id=1,
        plan_path=tmp / "plan.md",
        overnight_events_path=tmp / "overnight-events.log",
        pipeline_events_path=tmp / "pipeline-events.log",
        overnight_state_path=state_path,
        result_dir=tmp,
    )

    feature = MagicMock()
    feature.name = "feat-a"
    master_plan = MagicMock()
    master_plan.features = [feature]
    worktree_info = MagicMock()
    worktree_info.path = env.worktree
    worktree_info.branch = "pipeline/feat-a"
    manager = MagicMock()
    manager.acquire = AsyncMock()
    manager.release = MagicMock()
    manager.stats = {}
    feature_plan = FeaturePlan(
        feature="feat-a",
        overview="overview",
        tasks=[FeatureTask(number=1, description="task", depends_on=[], files=[], complexity="simple")],
    )

    patches = [
        patch.object(orchestrator, "parse_master_plan", return_value=master_plan),
        patch.object(orchestrator, "create_worktree", return_value=worktree_info),
        patch.object(orchestrator, "load_throttle_config", return_value=MagicMock()),
        patch.object(orchestrator, "ConcurrencyManager", return_value=manager),
        patch.object(orchestrator, "overnight_log_event"),
        patch("cortex_command.overnight.outcome_router.apply_feature_result", new_callable=AsyncMock),
        patch("cortex_command.overnight.feature_executor.parse_feature_plan", return_value=feature_plan),
        patch("cortex_command.overnight.feature_executor._render_template", return_value="stub prompt"),
        patch("cortex_command.overnight.feature_executor.read_criticality", return_value="medium"),
        patch("cortex_command.overnight.feature_executor.overnight_log_event"),
        patch(
            "cortex_command.overnight.feature_executor.subprocess.run",
            side_effect=OSError("not a git repo"),
        ),
    ]
    for p in patches:
        p.start()
    try:
        batch_result = asyncio.run(run_batch(config))
    finally:
        for p in reversed(patches):
            p.stop()

    assert batch_result.global_abort_signal is True
    assert batch_result.abort_reason == "api_unavailable"

    state = runner.state_module.load_state(state_path)
    assert state.phase == "paused"
    assert state.paused_reason == "api_unavailable"
    # runner.run's round loop breaks on exactly this predicate.
    assert _runner_round_loop_halt_predicates(), "runner.run has no paused_reason halt break"
    assert state.paused_reason in runner._SESSION_HALT_ERROR_TYPES


# ---------------------------------------------------------------------------
# R13: turn-limit exhaustion
# ---------------------------------------------------------------------------


def test_tool_use_stop_past_max_turns_is_turn_limit_exhausted(env, monkeypatch):
    run = {
        "frames": [result_frame(is_error=True, stop_reason="tool_use", num_turns=SIMPLE_MAX_TURNS + 1)],
        "exit_code": 1,
    }
    result, _ = _dispatch(env, monkeypatch, run)
    assert result.error_type == "turn_limit_exhausted"


# ---------------------------------------------------------------------------
# R14: every failure path carries diagnostics
# ---------------------------------------------------------------------------


def test_result_frame_failure_carries_diagnostics(env, monkeypatch):
    run = {
        "frames": [result_frame(is_error=True, subtype="success", terminal_reason="api_error")],
        "exit_code": 1,
        "stderr_lines": ["upstream said no"],
    }
    result, _ = _dispatch(env, monkeypatch, run)
    assert not result.success
    assert result.diagnostics is not None
    assert result.diagnostics.exit_code == 1
    assert result.diagnostics.cwd == str(env.worktree)
    assert "upstream said no" in result.diagnostics.child_stderr


def test_nonzero_exit_without_result_carries_diagnostics(env, monkeypatch):
    run = {"frames": [], "exit_code": 2}
    result, _ = _dispatch(env, monkeypatch, run)
    assert not result.success
    assert result.diagnostics is not None
    assert result.diagnostics.exit_code == 2
    assert result.diagnostics.cwd == str(env.worktree)
