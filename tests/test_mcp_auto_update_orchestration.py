"""R8/R9 throttled-update-check + skip-predicate tests (Task 7).

The four spec-named acceptance tests live here:

* ``test_throttle_cache_first_call_runs_ls_remote``       — R8 first-call.
* ``test_throttle_cache_subsequent_call_skips_ls_remote`` — R8 throttle.
* ``test_skip_predicate_dev_mode_suppresses_ls_remote``   — R9 (a) bypass.
* ``test_skip_predicate_dev_mode_tool_call_still_executes``
                                                          — R9 transparency.

Plus suggested coverage for predicates (b) dirty tree and (c) feature
branch.

Future tasks (8/9/10/11) will add upgrade-orchestration, verification
probe, schema-floor gate, and NDJSON failure-surface tests to this same
file.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = (
    REPO_ROOT
    / "plugins"
    / "cortex-overnight-integration"
    / "server.py"
)
PLUGIN_ROOT = SERVER_PATH.parent


# ---------------------------------------------------------------------------
# Module loader: import server.py as a regular module for in-process tests.
# Mirrors tests/test_mcp_subprocess_contract.py:_load_server_module so the
# confused-deputy startup-check at the top of server.py accepts the load.
# ---------------------------------------------------------------------------


def _load_server_module():
    """Import ``plugins/cortex-overnight-integration/server.py`` as a module."""
    if "cortex_plugin_server" in sys.modules:
        return sys.modules["cortex_plugin_server"]
    os.environ["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    spec = importlib.util.spec_from_file_location(
        "cortex_plugin_server", SERVER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["cortex_plugin_server"] = module
    spec.loader.exec_module(module)
    return module


def _completed(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    """Build a fake :class:`subprocess.CompletedProcess` for mocks."""
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


# ---------------------------------------------------------------------------
# Fixture: load the module once, reset all module-level state between tests.
# ---------------------------------------------------------------------------


@pytest.fixture
def server_module(monkeypatch: pytest.MonkeyPatch):
    """Load server.py and reset its caches + skip latch per test.

    Also primes the discovery cache (``_get_cortex_root_payload``) with
    a deterministic fake payload so individual tests do not need to
    mock ``cortex --print-root`` themselves. Tests that want to
    exercise the discovery shell-out can override the monkeypatch.

    The skip-predicate latch (``_SKIP_REASON_LOGGED``) is also cleared
    so each test starts from a clean stderr-logging slate.

    ``CORTEX_DEV_MODE`` is unset (and restored on teardown) so an
    inherited environment variable does not leak between tests.
    """

    mod = _load_server_module()

    # Reset module-level caches.
    mod._UPDATE_CHECK_CACHE.clear()
    mod._SKIP_REASON_LOGGED.clear()
    mod._CORTEX_ROOT_CACHE = None
    mod._STATUS_LEGACY_VERSION_WARNED = False

    # Prime the discovery cache with a stable payload so tool-dispatch
    # tests don't need to mock `cortex --print-root` themselves.
    fake_payload = {
        "version": "1.0",
        "root": "/fake/cortex/root",
        "remote_url": "git@github.com:user/cortex-command.git",
        "head_sha": "a" * 40,
    }
    mod._CORTEX_ROOT_CACHE = fake_payload

    # Ensure CORTEX_DEV_MODE is not inherited from the outer shell.
    monkeypatch.delenv("CORTEX_DEV_MODE", raising=False)

    yield mod

    # Teardown: clear again so a future test loading the same module
    # doesn't inherit our state.
    mod._UPDATE_CHECK_CACHE.clear()
    mod._SKIP_REASON_LOGGED.clear()
    mod._CORTEX_ROOT_CACHE = None


# ---------------------------------------------------------------------------
# `subprocess.run` recording shim — matches argv prefixes to canned
# outputs and records every call so tests can assert call counts and
# argv shapes. Predicates (b) and (c) shell out to `git status` and
# `git rev-parse`; we default both to "clean tree, on main" so the
# happy path falls through to `git ls-remote`.
# ---------------------------------------------------------------------------


def _make_subprocess_recorder(
    *,
    ls_remote_sha: str = "b" * 40,  # default: differs from head_sha (advance)
    status_porcelain: str = "",
    branch: str = "main",
    raise_on_ls_remote: BaseException | None = None,
):
    """Build a fake ``subprocess.run`` recorder.

    Returns ``(fake_run, calls_list)`` where ``calls_list`` accumulates
    every argv passed to the shim. The shim dispatches by argv prefix:

    * ``["git", "ls-remote", ...]``                 → recorded line.
    * ``["git", "-C", *, "status", "--porcelain"]`` → ``status_porcelain``.
    * ``["git", "-C", *, "rev-parse", ...]``        → ``branch + "\n"``.
    * other                                         → empty success.
    """
    calls: list[list[str]] = []

    def _fake_run(argv, **kwargs):
        calls.append(list(argv))
        if argv[:2] == ["git", "ls-remote"]:
            if raise_on_ls_remote is not None:
                raise raise_on_ls_remote
            return _completed(stdout=f"{ls_remote_sha}\tHEAD\n")
        if (
            len(argv) >= 5
            and argv[0] == "git"
            and argv[1] == "-C"
            and argv[3] == "status"
            and argv[4] == "--porcelain"
        ):
            return _completed(stdout=status_porcelain)
        if (
            len(argv) >= 5
            and argv[0] == "git"
            and argv[1] == "-C"
            and argv[3] == "rev-parse"
        ):
            return _completed(stdout=f"{branch}\n")
        # Default for any other call (tool-dispatch shell-outs etc.):
        # return success with empty stdout.
        return _completed(stdout="", returncode=0)

    return _fake_run, calls


def _ls_remote_calls(calls: list[list[str]]) -> list[list[str]]:
    """Return only the ``git ls-remote`` invocations from the recorder."""
    return [c for c in calls if c[:2] == ["git", "ls-remote"]]


# ---------------------------------------------------------------------------
# R8 — throttled update check
# ---------------------------------------------------------------------------


def test_throttle_cache_first_call_runs_ls_remote(server_module) -> None:
    """First call per cache key runs ``git ls-remote``.

    Spec R8 acceptance: ``test_throttle_cache_first_call_runs_ls_remote``.
    """
    fake_run, calls = _make_subprocess_recorder()

    with patch.object(server_module.subprocess, "run", side_effect=fake_run):
        result = server_module._maybe_check_upstream()

    ls_calls = _ls_remote_calls(calls)
    assert len(ls_calls) == 1, (
        f"expected exactly one `git ls-remote` invocation; got {ls_calls}"
    )
    # Default recorder returns a sha that differs from the primed
    # head_sha, so the helper reports upstream-ahead.
    assert result is True


def test_throttle_cache_subsequent_call_skips_ls_remote(
    server_module,
) -> None:
    """Second call within the same lifetime reads the cached boolean.

    Spec R8 acceptance:
    ``test_throttle_cache_subsequent_call_skips_ls_remote``.
    """
    fake_run, calls = _make_subprocess_recorder()

    with patch.object(server_module.subprocess, "run", side_effect=fake_run):
        first = server_module._maybe_check_upstream()
        second = server_module._maybe_check_upstream()

    ls_calls = _ls_remote_calls(calls)
    assert len(ls_calls) == 1, (
        f"expected exactly ONE `git ls-remote` across two helper calls; "
        f"got {len(ls_calls)}: {ls_calls}"
    )
    assert first is True
    assert second is True


def test_throttle_cache_when_upstream_matches_local(server_module) -> None:
    """When the upstream sha matches local head_sha, helper returns False.

    Suggested coverage (not in the four spec-named tests but exercises
    the cache-set branch's other state).
    """
    matching_sha = server_module._CORTEX_ROOT_CACHE["head_sha"]
    fake_run, calls = _make_subprocess_recorder(ls_remote_sha=matching_sha)

    with patch.object(server_module.subprocess, "run", side_effect=fake_run):
        result = server_module._maybe_check_upstream()

    assert result is False
    assert len(_ls_remote_calls(calls)) == 1


def test_throttle_cache_invalidation_helper_clears_cache(
    server_module,
) -> None:
    """``_invalidate_update_cache()`` clears the in-memory cache.

    Task 7 ships this as a no-op stub; calling it after a populated
    cache should evict so the next ``_maybe_check_upstream`` re-shells.
    Tasks 8/10/11 will wire actual call sites.
    """
    fake_run, calls = _make_subprocess_recorder()

    with patch.object(server_module.subprocess, "run", side_effect=fake_run):
        server_module._maybe_check_upstream()
        server_module._invalidate_update_cache()
        server_module._maybe_check_upstream()

    # Two ls-remote invocations because invalidate cleared the cache.
    assert len(_ls_remote_calls(calls)) == 2


# ---------------------------------------------------------------------------
# R9 — skip predicates
# ---------------------------------------------------------------------------


def test_skip_predicate_dev_mode_suppresses_ls_remote(
    server_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``CORTEX_DEV_MODE=1`` short-circuits before any subprocess shell-out.

    Spec R9 acceptance:
    ``test_skip_predicate_dev_mode_suppresses_ls_remote``.
    """
    monkeypatch.setenv("CORTEX_DEV_MODE", "1")

    fake_run, calls = _make_subprocess_recorder()

    with patch.object(server_module.subprocess, "run", side_effect=fake_run):
        result = server_module._maybe_check_upstream()

    assert result is None
    assert _ls_remote_calls(calls) == [], (
        f"expected zero `git ls-remote` calls under CORTEX_DEV_MODE=1; "
        f"got {calls}"
    )
    # Predicate (a) must short-circuit BEFORE (b) and (c), so no
    # `git status` or `git rev-parse` either.
    assert calls == [], (
        f"CORTEX_DEV_MODE=1 must short-circuit before any subprocess "
        f"shell-out; got {calls}"
    )


def test_skip_predicate_dev_mode_tool_call_still_executes(
    server_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The user's intended tool call still runs when the predicate fires.

    Spec R9 acceptance:
    ``test_skip_predicate_dev_mode_tool_call_still_executes``.

    Calls ``overnight_status`` with the predicate firing; asserts a
    StatusOutput is returned (the tool-call path is not blocked by the
    skip predicate).
    """
    monkeypatch.setenv("CORTEX_DEV_MODE", "1")

    status_payload = json.dumps(
        {
            "session_id": "alpha",
            "phase": "executing",
            "current_round": 1,
            "features": {},
        }
    )
    calls: list[list[str]] = []

    def _fake_run(argv, **kwargs):
        calls.append(list(argv))
        # The discovery cache is pre-primed by the fixture, so the
        # only subprocess invocation under CORTEX_DEV_MODE=1 is the
        # `cortex overnight status --format json` tool call itself.
        if argv[:1] == ["cortex"]:
            return _completed(stdout=status_payload)
        # Should not happen under CORTEX_DEV_MODE=1, but be defensive.
        return _completed(stdout="")

    with patch.object(server_module.subprocess, "run", side_effect=_fake_run):
        result = server_module._delegate_overnight_status(
            server_module.StatusInput(session_id=None)
        )

    assert isinstance(result, server_module.StatusOutput)
    assert result.phase == "executing"
    # No `git ls-remote` triggered by the wired update-check entry point.
    assert _ls_remote_calls(calls) == []


def test_skip_predicate_dirty_tree_suppresses_ls_remote(
    server_module,
) -> None:
    """``git status --porcelain`` non-empty suppresses the upstream check.

    Suggested coverage for spec R9 predicate (b).
    """
    fake_run, calls = _make_subprocess_recorder(
        status_porcelain=" M some_file.py\n"
    )

    with patch.object(server_module.subprocess, "run", side_effect=fake_run):
        result = server_module._maybe_check_upstream()

    assert result is None
    assert _ls_remote_calls(calls) == []
    # Predicate (b) shells out to `git status`; assert it ran.
    status_calls = [
        c for c in calls if len(c) >= 4 and c[3] == "status"
    ]
    assert len(status_calls) == 1


def test_skip_predicate_feature_branch_suppresses_ls_remote(
    server_module,
) -> None:
    """A non-``main`` branch suppresses the upstream check.

    Suggested coverage for spec R9 predicate (c).
    """
    fake_run, calls = _make_subprocess_recorder(branch="feature/xyz")

    with patch.object(server_module.subprocess, "run", side_effect=fake_run):
        result = server_module._maybe_check_upstream()

    assert result is None
    assert _ls_remote_calls(calls) == []
    # Predicate (c) shells out to `git rev-parse`; assert it ran.
    revparse_calls = [
        c for c in calls if len(c) >= 4 and c[3] == "rev-parse"
    ]
    assert len(revparse_calls) == 1


def test_skip_reason_latched_to_one_stderr_log(
    server_module,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Each distinct skip reason is logged to stderr at most once.

    Per spec R9: "log skip reason once to stderr (per-process latch)".
    """
    monkeypatch.setenv("CORTEX_DEV_MODE", "1")
    fake_run, _ = _make_subprocess_recorder()

    with patch.object(server_module.subprocess, "run", side_effect=fake_run):
        server_module._maybe_check_upstream()
        server_module._maybe_check_upstream()
        server_module._maybe_check_upstream()

    err = capsys.readouterr().err
    # Count occurrences of the skip-reason marker; should be exactly 1.
    occurrences = err.count("CORTEX_DEV_MODE=1")
    assert occurrences == 1, (
        f"expected the skip reason 'CORTEX_DEV_MODE=1' to be logged "
        f"exactly once; got {occurrences} occurrences in stderr={err!r}"
    )


# ---------------------------------------------------------------------------
# Cache-key shape (R8 multi-fork-installs)
# ---------------------------------------------------------------------------


def test_throttle_cache_key_includes_cortex_root_and_remote(
    server_module,
) -> None:
    """Cache keys are ``(cortex_root, remote_url, "HEAD")``.

    Two different cortex_root payloads must each pay the ls-remote cost
    independently (multi-fork-install case from spec R8).
    """
    fake_run, calls = _make_subprocess_recorder()

    payload_a = {
        "version": "1.0",
        "root": "/fork-a/cortex",
        "remote_url": "git@github.com:user-a/cortex.git",
        "head_sha": "a" * 40,
    }
    payload_b = {
        "version": "1.0",
        "root": "/fork-b/cortex",
        "remote_url": "git@github.com:user-b/cortex.git",
        "head_sha": "a" * 40,
    }

    with patch.object(server_module.subprocess, "run", side_effect=fake_run):
        server_module._maybe_check_upstream(payload_a)
        server_module._maybe_check_upstream(payload_b)

    # Two distinct cache keys → two ls-remote calls.
    assert len(_ls_remote_calls(calls)) == 2


def test_ls_remote_failure_does_not_cache(server_module) -> None:
    """`git ls-remote` timeout/error does not poison the cache.

    Spec Edge Cases: "git ls-remote timeout / network failure: skip
    predicate fires implicitly; cached attempt; user's tool call
    proceeds against on-disk CLI. Re-tries on next MCP server
    startup." We interpret "Re-tries on next MCP server startup" as
    "no negative caching within the lifetime", so a subsequent
    helper call retries.
    """
    fake_run, calls = _make_subprocess_recorder(
        raise_on_ls_remote=subprocess.TimeoutExpired(
            cmd=["git", "ls-remote"], timeout=5
        )
    )

    with patch.object(server_module.subprocess, "run", side_effect=fake_run):
        first = server_module._maybe_check_upstream()
        second = server_module._maybe_check_upstream()

    assert first is None
    assert second is None
    # Both calls retried — no negative caching.
    assert len(_ls_remote_calls(calls)) == 2
