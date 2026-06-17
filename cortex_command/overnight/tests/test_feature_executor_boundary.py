"""Enforces that feature_executor.py does not import from batch_runner or
orchestrator — prevents circular imports.

Also covers the field-additive ``task_output`` diagnostics emit (R7): a
failing task's ``task_output`` event carries the stderr/exit_code/cwd fields
sourced from ``RetryResult.last_dispatch_diagnostics``; a successful task's
``task_output`` omits them (emitter omits when the bundle is ``None``)."""

import ast
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import cortex_command.overnight.feature_executor as feature_executor_module
from cortex_command.overnight.feature_executor import execute_feature
from cortex_command.overnight.orchestrator import BatchConfig
from cortex_command.pipeline.parser import FeaturePlan, FeatureTask
from cortex_command.pipeline.retry import RetryResult
from cortex_command.pipeline.dispatch import DispatchDiagnostics

_FEATURE_EXECUTOR_PATH = Path(__file__).resolve().parents[1] / "feature_executor.py"
_FORBIDDEN_PREFIXES = ("cortex_command.overnight.batch_runner", "cortex_command.overnight.orchestrator")


def _type_checking_guarded_linenos(tree: ast.Module) -> set[int]:
    """Return line numbers of import nodes inside `if TYPE_CHECKING:` guards.

    These are not runtime imports and do not create circular dependencies,
    so the boundary test excludes them.
    """
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Name)
            and node.test.id == "TYPE_CHECKING"
        ):
            for child in ast.walk(node):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    guarded.add(child.lineno)
    return guarded


class TestFeatureExecutorImportBoundary(unittest.TestCase):
    def test_no_forbidden_imports(self) -> None:
        source = _FEATURE_EXECUTOR_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        guarded = _type_checking_guarded_linenos(tree)
        violations: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.lineno in guarded:
                    continue
                module = node.module or ""
                for prefix in _FORBIDDEN_PREFIXES:
                    if module == prefix or module.startswith(prefix + "."):
                        violations.append(f"line {node.lineno}: from {module} import ...")
            elif isinstance(node, ast.Import):
                if node.lineno in guarded:
                    continue
                for alias in node.names:
                    for prefix in _FORBIDDEN_PREFIXES:
                        if alias.name == prefix or alias.name.startswith(prefix + "."):
                            violations.append(f"line {node.lineno}: import {alias.name}")
        if violations:
            self.fail(
                "feature_executor.py contains forbidden runtime imports:\n"
                + "\n".join(violations)
            )


def _extract_task_output_event(mock_log: MagicMock) -> dict:
    """Return the single ``task_output`` event dict passed to pipeline_log_event.

    ``pipeline_log_event(path, event_dict)`` — the event is the second
    positional arg. Fails the assertion if zero or more than one was emitted.
    """
    task_outputs = [
        c.args[1]
        for c in mock_log.call_args_list
        if len(c.args) >= 2
        and isinstance(c.args[1], dict)
        and c.args[1].get("event") == "task_output"
    ]
    assert len(task_outputs) == 1, (
        f"expected exactly one task_output event, got {len(task_outputs)}"
    )
    return task_outputs[0]


class TestTaskOutputDiagnosticsEmit(unittest.IsolatedAsyncioTestCase):
    """R7: the unconditional ``task_output`` event carries the failing
    dispatch's diagnostics as DISTINCT fields (child_stderr/exit_code/cwd),
    sourced from ``RetryResult.last_dispatch_diagnostics`` — never folded into
    ``output``. Field-additive: omitted entirely on the success path (bundle
    is ``None``)."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._tmp = Path(self._tmpdir.name)
        self._config = BatchConfig(
            batch_id=1,
            plan_path=self._tmp / "plan.md",
            overnight_events_path=self._tmp / "overnight.log",
            pipeline_events_path=self._tmp / "pipeline.log",
            overnight_state_path=self._tmp / "state.json",
        )
        self._feature_plan = FeaturePlan(
            feature="test-feat",
            overview="",
            tasks=[
                FeatureTask(
                    number=1,
                    description="do something",
                    depends_on=[],
                    files=["test.py"],
                    complexity="simple",
                )
            ],
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def _patches(self, retry_result, mock_log):
        """Patch the non-emit surface; pipeline_log_event is the caller-supplied
        MagicMock so the test inspects the emitted events. _handle_failed_task is
        stubbed to None on the failure path (yields status='paused') — the
        task_output emit already ran before triage."""
        return [
            patch.object(feature_executor_module, "load_state", side_effect=Exception("skip repair")),
            patch.object(feature_executor_module, "parse_feature_plan", return_value=self._feature_plan),
            patch.object(feature_executor_module, "retry_task", new=AsyncMock(return_value=retry_result)),
            patch.object(feature_executor_module, "_read_exit_report", return_value=("complete", None, None)),
            patch.object(feature_executor_module, "mark_task_done_in_plan"),
            patch.object(feature_executor_module, "pipeline_log_event", new=mock_log),
            patch.object(feature_executor_module, "overnight_log_event"),
            patch.object(feature_executor_module, "read_criticality", return_value="high"),
            patch.object(feature_executor_module, "_render_template", return_value="stub system prompt"),
            patch.object(
                feature_executor_module,
                "_handle_failed_task",
                new=AsyncMock(return_value=None),
            ),
            patch.object(
                subprocess,
                "run",
                return_value=MagicMock(returncode=0, stdout="0\n", stderr=""),
            ),
        ]

    async def test_failing_task_output_carries_diagnostics_fields(self):
        """A failing task's task_output event includes child_stderr/exit_code/cwd
        sourced from the bundle, distinct from (and not folded into) output."""
        diagnostics = DispatchDiagnostics(
            child_stderr="boom: traceback line\nProcessError: exit code 1",
            exit_code=1,
            cwd="/tmp/wt-123",
        )
        retry_result = RetryResult(
            success=False,
            attempts=2,
            final_output="",  # empty on crash — exactly the case this guards
            paused=False,
            idempotency_skipped=False,
            last_dispatch_diagnostics=diagnostics,
        )
        mock_log = MagicMock()
        patches = self._patches(retry_result, mock_log)
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10]:
            await execute_feature(
                feature="test-feat",
                worktree_path=self._tmp,
                config=self._config,
            )

        event = _extract_task_output_event(mock_log)
        self.assertEqual(event["child_stderr"], diagnostics.child_stderr)
        self.assertEqual(event["exit_code"], diagnostics.exit_code)
        self.assertEqual(event["cwd"], diagnostics.cwd)
        # Distinct fields — NOT folded into the (empty-on-crash) output.
        self.assertEqual(event["output"], "")

    async def test_successful_task_output_omits_diagnostics_fields(self):
        """A successful task's task_output omits the diagnostics fields entirely
        (field-additive: emitter omits when the bundle is None)."""
        retry_result = RetryResult(
            success=True,
            attempts=1,
            final_output="done",
            paused=False,
            idempotency_skipped=False,
            last_dispatch_diagnostics=None,
        )
        mock_log = MagicMock()
        patches = self._patches(retry_result, mock_log)
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10]:
            await execute_feature(
                feature="test-feat",
                worktree_path=self._tmp,
                config=self._config,
            )

        event = _extract_task_output_event(mock_log)
        self.assertNotIn("child_stderr", event)
        self.assertNotIn("exit_code", event)
        self.assertNotIn("cwd", event)
        self.assertEqual(event["output"], "done")


if __name__ == "__main__":
    unittest.main()
