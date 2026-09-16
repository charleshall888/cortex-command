"""Unit tests for dispatch.py budget-exhausted path, rate-limit classification,
stderr accumulator integration, and per-spawn sandbox-settings tempfile wiring
(spec Reqs 5, 6, 15).

These tests use asyncio.run() inside synchronous test methods because
pytest-asyncio is not a project dependency.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cortex_command.pipeline.dispatch as _dispatch_module  # noqa: E402
from cortex_command.tests._claude_double import fake_run_claude, result_frame  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dispatch_with(double, **dispatch_kwargs):
    """Run ``dispatch_task`` with ``run_claude`` replaced by ``double``.

    Pins the resolved CLI path so the dispatch never depends on a ``claude``
    being installed on the test host.
    """
    kwargs = {
        "task": "do something",
        "worktree_path": Path("/tmp"),
        "complexity": "simple",
        "system_prompt": "test",
        "skill": "implement",
    }
    kwargs.update(dispatch_kwargs)

    async def _run():
        return await _dispatch_module.dispatch_task(**kwargs)

    with patch.object(_dispatch_module, "run_claude", double):
        with patch.object(_dispatch_module, "resolve_claude_cli", return_value="/fake/claude"):
            return asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 1: budget-exhausted dispatch path
# ---------------------------------------------------------------------------

class TestBudgetExhaustedDispatchPath(unittest.TestCase):
    """dispatch_task returns success=False / error_type=budget_exhausted when
    the result frame carries subtype error_max_budget_usd."""

    def test_budget_exhausted_returns_failure_result(self):
        double = fake_run_claude(
            [result_frame(is_error=True, subtype="error_max_budget_usd", total_cost_usd=0.01)],
            exit_code=1,
        )
        result = _dispatch_with(double, feature="budget-test")
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "budget_exhausted")


# ---------------------------------------------------------------------------
# Test 2: rate-limit classify_failure
# ---------------------------------------------------------------------------

class TestRateLimitClassifyFailure(unittest.TestCase):
    """classify_failure returns api_rate_limit when a failed run's corpus
    contains a rate-limit keyword pattern."""

    def test_rate_limit_error_in_output_returns_api_rate_limit(self):
        result = _dispatch_module.classify_failure(
            1, None, None, "rate_limit_error in response", None,
        )
        self.assertEqual(result, "api_rate_limit")


# ---------------------------------------------------------------------------
# Test 3: stderr accumulator integration
# ---------------------------------------------------------------------------

class TestStderrAccumulatorIntegration(unittest.TestCase):
    """dispatch_task classifies error as api_rate_limit when stderr lines
    contain a rate-limit keyword and claude exits non-zero."""

    def test_stderr_rate_limit_line_yields_api_rate_limit_error_type(self):
        double = fake_run_claude(
            [],
            exit_code=1,
            stderr_lines=["rate limit error received from API"],
        )
        result = _dispatch_with(double, feature="stderr-test")
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "api_rate_limit")


# ---------------------------------------------------------------------------
# Test 3b: dispatch_error payload captures child stderr + exit code (R1)
# ---------------------------------------------------------------------------

class TestDispatchErrorCapturesStderrAndExitCode(unittest.TestCase):
    """On a non-zero exit, the emitted ``dispatch_error`` event payload carries
    the real child stderr (accumulated in ``_stderr_lines`` through the
    ``on_stderr`` callback) plus the child's exit_code.

    A regression that drops the real child stderr — emitting an empty or
    placeholder-only payload — must fail this test.
    """

    def test_nonzero_exit_payload_has_seeded_stderr_and_exit_code(self):
        marker = "CORTEX_TEST_STDERR_MARKER_xyz"

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "events.log"
            double = fake_run_claude(
                [],
                exit_code=1,
                stderr_lines=[f"{marker}: child exited abnormally"],
            )
            result = _dispatch_with(
                double, feature="stderr-capture-test", log_path=log_path,
            )

            self.assertFalse(result.success)

            events = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            errors = [e for e in events if e.get("event") == "dispatch_error"]
            self.assertEqual(len(errors), 1, f"expected one dispatch_error event, got {events!r}")
            payload = errors[0]

            # The exact seeded marker (redaction does not transform this line)
            # survives into the emitted child_stderr field.
            self.assertIn(
                marker,
                payload.get("child_stderr", ""),
                f"seeded stderr marker missing from dispatch_error payload: {payload!r}",
            )
            # A non-null exit_code is recorded.
            self.assertIsNotNone(payload.get("exit_code"))
            self.assertEqual(payload["exit_code"], 1)


# ---------------------------------------------------------------------------
# Helpers for sandbox-settings dispatch tests (Req 5, 6, 15)
# ---------------------------------------------------------------------------


def _capture_dispatch_spawn(monkeypatch_env: dict) -> dict:
    """Run ``dispatch_task`` against the frame double; return what it spawned.

    The double yields a single successful result frame so the dispatch
    returns success, and records the ``argv``/``env`` handed to
    ``run_claude``.

    Args:
        monkeypatch_env: Mapping of env vars to set for the duration of the call.

    Returns:
        Dict with ``argv``, ``env``, ``settings_path`` (the value following
        ``--settings`` in argv, or None) and ``settings_path_contents`` keys.
    """
    captured: dict = {}
    double = fake_run_claude([result_frame(total_cost_usd=0.0)], capture=captured)

    # A CORTEX_REPO_ROOT without a repo marker is rejected (ADR-0013) and the
    # root falls back to the cwd walk — the live repo — so the sandbox sidecar
    # and settings tempfile would land in the real cortex/lifecycle/sessions/.
    # Give the pinned root the cortex/ marker so the pin is honoured.
    if "CORTEX_REPO_ROOT" in monkeypatch_env:
        (Path(monkeypatch_env["CORTEX_REPO_ROOT"]) / "cortex").mkdir(exist_ok=True)

    # Apply env overrides.
    saved_env: dict[str, str | None] = {}
    for k, v in monkeypatch_env.items():
        saved_env[k] = os.environ.get(k)
        os.environ[k] = v
    try:
        _dispatch_with(
            double,
            feature="sandbox-test",
            worktree_path=Path(tempfile.gettempdir()),
        )
    finally:
        for k, prev in saved_env.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev

    argv = captured["argv"]
    settings_path = None
    if "--settings" in argv:
        idx = argv.index("--settings")
        if idx + 1 < len(argv):
            settings_path = argv[idx + 1]
    captured["settings_path"] = settings_path
    if settings_path is not None and Path(settings_path).exists():
        captured["settings_path_contents"] = json.loads(
            Path(settings_path).read_text(encoding="utf-8")
        )
    else:
        captured["settings_path_contents"] = None
    return captured


# ---------------------------------------------------------------------------
# Test 4 (spec Req 5): settings tempfile is used and has correct shape
# ---------------------------------------------------------------------------


def test_settings_tempfile_used(tmp_path):
    """Dispatch a feature against the frame double, assert the spawned argv
    carries ``--settings <path>`` naming a file that exists, and its JSON
    contents contain the documented sandbox shape (spec Req 5)."""
    # CORTEX_REPO_ROOT alongside the session id (the sibling pattern below):
    # dispatch resolves its sandbox-deny-list sidecar directory from the repo
    # root independently of tmp_path, so the session id alone leaves the
    # sidecar in the live cortex/lifecycle/sessions/ tree.
    captured = _capture_dispatch_spawn(
        {
            "LIFECYCLE_SESSION_ID": f"test-{tmp_path.name}",
            "CORTEX_REPO_ROOT": str(tmp_path),
        }
    )

    settings_path = captured["settings_path"]
    assert settings_path is not None, (
        f"argv must carry --settings <path>; got {captured['argv']!r}"
    )
    assert Path(settings_path).exists(), (
        f"Settings tempfile must exist on disk: {settings_path}"
    )

    contents = captured["settings_path_contents"]
    assert contents is not None
    sandbox = contents.get("sandbox")
    assert isinstance(sandbox, dict), f"Expected sandbox dict, got {type(sandbox)}"

    # Required keys per spec Req 2/Req 5.
    assert sandbox.get("enabled") is True
    assert "failIfUnavailable" in sandbox
    assert sandbox.get("allowUnsandboxedCommands") is False
    assert sandbox.get("enableWeakerNestedSandbox") is False
    assert sandbox.get("enableWeakerNetworkIsolation") is False

    fs = sandbox.get("filesystem")
    assert isinstance(fs, dict), f"Expected filesystem dict, got {type(fs)}"
    assert "denyWrite" in fs, "filesystem.denyWrite key required"
    assert "allowWrite" in fs, "filesystem.allowWrite key required"


# ---------------------------------------------------------------------------
# Test 5 (spec Req 5): dispatched env locks TMPDIR
# ---------------------------------------------------------------------------


def test_dispatched_env_locks_tmpdir(tmp_path, monkeypatch):
    """Assert the env handed to ``run_claude`` contains TMPDIR with a
    non-empty value (spec Req 5/Req 10 — locked into dispatched-agent env to
    prevent unset-fallback to /tmp/).

    The child env now inherits the parent environment, so TMPDIR is removed
    from the parent first: otherwise an inherited TMPDIR would satisfy the
    assertion even if dispatch stopped locking it.
    """
    monkeypatch.delenv("TMPDIR", raising=False)
    captured = _capture_dispatch_spawn(
        {
            "LIFECYCLE_SESSION_ID": f"test-{tmp_path.name}",
            "CORTEX_REPO_ROOT": str(tmp_path),
        }
    )

    env = captured["env"]
    assert isinstance(env, dict), f"Expected env dict, got {type(env)}"
    assert "TMPDIR" in env, f"env must contain TMPDIR; got keys: {list(env)}"
    tmpdir_value = env["TMPDIR"]
    assert tmpdir_value, f"TMPDIR must be non-empty; got {tmpdir_value!r}"


# ---------------------------------------------------------------------------
# Test 6 (spec Req 6): no project-settings blob injection
# ---------------------------------------------------------------------------


def test_no_blob_injection(tmp_path):
    """Write a fixture .claude/settings.local.json containing hooks/env,
    dispatch a feature, assert the ``--settings`` file's JSON does NOT
    contain "hooks" or "env" keys after json.loads (spec Req 6)."""
    # Create a fixture .claude/settings.local.json in tmp_path.
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings_local = claude_dir / "settings.local.json"
    settings_local.write_text(
        json.dumps({"hooks": {"PostToolUse": []}, "env": {"FOO": "BAR"}}),
        encoding="utf-8",
    )

    # Run dispatch from tmp_path so _load_project_settings would naturally pick
    # up this fixture if it were still being force-injected.
    captured = _capture_dispatch_spawn(
        {
            "LIFECYCLE_SESSION_ID": f"test-{tmp_path.name}",
            "CORTEX_REPO_ROOT": str(tmp_path),
        }
    )

    contents = captured["settings_path_contents"]
    # Settings file is used (per Req 5); it must NOT contain hooks or env keys
    # at top level.
    assert contents is not None, "settings tempfile contents missing"
    assert "hooks" not in contents, (
        f"settings tempfile must NOT contain 'hooks' key; got: {sorted(contents)}"
    )
    assert "env" not in contents, (
        f"settings tempfile must NOT contain 'env' key; got: {sorted(contents)}"
    )


if __name__ == "__main__":
    unittest.main()
