"""R8/R9 throttled-update-check + skip-predicate tests (Task 7) plus
R10/R11 upgrade-orchestration tests (Task 8).

Task 7 spec-named acceptance tests:

* ``test_throttle_cache_first_call_runs_ls_remote``       — R8 first-call.
* ``test_throttle_cache_subsequent_call_skips_ls_remote`` — R8 throttle.
* ``test_skip_predicate_dev_mode_suppresses_ls_remote``   — R9 (a) bypass.
* ``test_skip_predicate_dev_mode_tool_call_still_executes``
                                                          — R9 transparency.

Task 8 spec-named acceptance tests:

* ``test_upgrade_orchestration_invocation_order``         — R10 invocation order.
* ``test_concurrent_upgrade_only_one_subprocess_runs``    — R11 cross-process.
* ``test_concurrent_upgrade_both_processes_return_success``
                                                          — R11 contention loser.

Future tasks (9/10/11) will add verification probe, schema-floor gate,
and NDJSON failure-surface tests to this same file.
"""

from __future__ import annotations

import importlib.util
import json
import multiprocessing
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


# ---------------------------------------------------------------------------
# R10/R11 — upgrade orchestration with flock + post-flock re-verify (Task 8)
# ---------------------------------------------------------------------------


def _make_upgrade_recorder(
    *,
    pre_flock_remote_sha: str = "b" * 40,
    post_flock_remote_sha: str = "b" * 40,
    post_flock_local_head: str = "a" * 40,
    upgrade_returncode: int = 0,
    upgrade_stderr: str = "",
    status_porcelain: str = "",
    branch: str = "main",
):
    """Build a fake ``subprocess.run`` recorder for upgrade-orchestration tests.

    Distinguishes two phases of ``git ls-remote`` calls by call-count:
    the first ls-remote (pre-flock, from ``_maybe_check_upstream``)
    returns ``pre_flock_remote_sha``; the second (post-flock fresh
    re-verify) returns ``post_flock_remote_sha``.

    Returns ``(fake_run, calls_list)``. The recorder dispatches by argv
    prefix:

    * ``["git", "ls-remote", ...]``                — pre/post sha by count.
    * ``["git", "-C", *, "rev-parse", "HEAD"]``    — ``post_flock_local_head``.
    * ``["git", "-C", *, "rev-parse", "--abbrev-ref", "HEAD"]``
                                                   — ``branch``.
    * ``["git", "-C", *, "status", "--porcelain"]`` — ``status_porcelain``.
    * ``["cortex", "upgrade"]``                    — ``upgrade_returncode``.
    * ``["cortex", ...]``                          — empty success.
    """
    calls: list[list[str]] = []
    ls_remote_count = {"n": 0}

    def _fake_run(argv, **kwargs):
        calls.append(list(argv))
        if argv[:2] == ["git", "ls-remote"]:
            ls_remote_count["n"] += 1
            sha = (
                pre_flock_remote_sha
                if ls_remote_count["n"] == 1
                else post_flock_remote_sha
            )
            return _completed(stdout=f"{sha}\tHEAD\n")
        if (
            len(argv) >= 5
            and argv[0] == "git"
            and argv[1] == "-C"
            and argv[3] == "rev-parse"
            and argv[4] == "HEAD"
        ):
            return _completed(stdout=f"{post_flock_local_head}\n")
        if (
            len(argv) >= 6
            and argv[0] == "git"
            and argv[1] == "-C"
            and argv[3] == "rev-parse"
            and argv[4] == "--abbrev-ref"
        ):
            return _completed(stdout=f"{branch}\n")
        if (
            len(argv) >= 5
            and argv[0] == "git"
            and argv[1] == "-C"
            and argv[3] == "status"
            and argv[4] == "--porcelain"
        ):
            return _completed(stdout=status_porcelain)
        if argv[:2] == ["cortex", "upgrade"]:
            return _completed(
                stdout="",
                stderr=upgrade_stderr,
                returncode=upgrade_returncode,
            )
        if argv[:1] == ["cortex"]:
            # Default cortex tool dispatch — return a parseable status
            # payload for use by `_delegate_overnight_status` etc.
            return _completed(
                stdout=json.dumps(
                    {
                        "version": "1.0",
                        "session_id": "test-session",
                        "phase": "executing",
                        "current_round": 1,
                        "features": {},
                    }
                )
            )
        return _completed(stdout="", returncode=0)

    return _fake_run, calls


def _upgrade_calls(calls: list[list[str]]) -> list[list[str]]:
    """Return only the ``cortex upgrade`` invocations from the recorder."""
    return [c for c in calls if c[:2] == ["cortex", "upgrade"]]


def test_upgrade_orchestration_invocation_order(
    server_module, tmp_path: Path
) -> None:
    """R10 acceptance: argv order is ls-remote → upgrade → probe → tool call.

    Spec R10 acceptance:
    ``test_upgrade_orchestration_invocation_order``.

    With upstream advance detected and skip predicates not firing, the
    ``_delegate_overnight_status`` dispatch must:

    1. Run ``git ls-remote`` (pre-flock, via ``_maybe_check_upstream``).
    2. Run ``cortex upgrade`` (under the flock).
    3. Run the verification probe (R12, Task 9 placeholder).
    4. Run the user-intended tool call
       (``cortex overnight status --format json``).

    Steps 2 and 3's relative position is asserted via mock; step 1 and
    step 4 are asserted via argv shape from the recorder.
    """
    # Pre-flock remote_sha differs from primed head_sha → upstream
    # advance detected. Post-flock remote_sha differs from local HEAD
    # → upgrade is not skipped as redundant.
    fake_run, calls = _make_upgrade_recorder(
        pre_flock_remote_sha="b" * 40,
        post_flock_remote_sha="c" * 40,
        post_flock_local_head="a" * 40,
    )

    # Point the discovery cache at a real tmp dir so the lock file path
    # under ``$cortex_root/.git/cortex-update.lock`` is creatable.
    cortex_root = tmp_path / "cortex"
    (cortex_root / ".git").mkdir(parents=True)
    server_module._CORTEX_ROOT_CACHE = {
        "version": "1.0",
        "root": str(cortex_root),
        "remote_url": "git@github.com:user/cortex-command.git",
        "head_sha": "a" * 40,
    }

    probe_calls: list[int] = []

    def _record_probe() -> bool:
        probe_calls.append(len(calls))  # remember the call-count
        return True

    with (
        patch.object(server_module.subprocess, "run", side_effect=fake_run),
        patch.object(
            server_module, "_run_verification_probe", side_effect=_record_probe
        ),
    ):
        result = server_module._delegate_overnight_status(
            server_module.StatusInput(session_id=None)
        )

    # Sanity: dispatch returned a StatusOutput (not a fall-through error).
    assert isinstance(result, server_module.StatusOutput)

    # Locate each marker call's index in the recorded argv list.
    ls_remote_idx = next(
        i for i, c in enumerate(calls) if c[:2] == ["git", "ls-remote"]
    )
    upgrade_idx = next(
        i for i, c in enumerate(calls) if c[:2] == ["cortex", "upgrade"]
    )
    user_call_idx = next(
        i
        for i, c in enumerate(calls)
        if c[:1] == ["cortex"]
        and len(c) >= 4
        and c[1] == "overnight"
        and c[2] == "status"
    )

    # Verification probe was called between upgrade and user tool call.
    # ``probe_calls[0]`` is the call-count at probe time; it must be
    # greater than ``upgrade_idx`` and less than or equal to ``user_call_idx``.
    assert probe_calls, "verification probe was not invoked"
    probe_callcount_at_invoke = probe_calls[0]

    # Argv order assertion: ls-remote BEFORE upgrade BEFORE user tool call.
    assert ls_remote_idx < upgrade_idx, (
        f"`git ls-remote` must precede `cortex upgrade`; "
        f"got ls_remote_idx={ls_remote_idx}, upgrade_idx={upgrade_idx}; "
        f"calls={calls}"
    )
    assert upgrade_idx < user_call_idx, (
        f"`cortex upgrade` must precede user tool call; "
        f"got upgrade_idx={upgrade_idx}, user_call_idx={user_call_idx}; "
        f"calls={calls}"
    )
    # Probe fired AFTER upgrade and BEFORE user tool call.
    assert probe_callcount_at_invoke > upgrade_idx, (
        f"verification probe must fire after upgrade; "
        f"probe_callcount_at_invoke={probe_callcount_at_invoke} "
        f"upgrade_idx={upgrade_idx}; calls={calls}"
    )
    assert probe_callcount_at_invoke <= user_call_idx, (
        f"verification probe must fire before user tool call; "
        f"probe_callcount_at_invoke={probe_callcount_at_invoke} "
        f"user_call_idx={user_call_idx}; calls={calls}"
    )


def test_upgrade_orchestration_post_flock_skip_when_local_caught_up(
    server_module, tmp_path: Path
) -> None:
    """Post-flock re-verify: skip redundant upgrade when local matches remote.

    Spec Technical Constraints "R11 post-acquire HEAD re-verification
    reference point": after acquiring the lock, the MCP runs a fresh
    ``git ls-remote`` and ``git rev-parse HEAD`` and compares them to
    each other. If they match (another MCP already applied the update
    during the flock wait), the redundant ``cortex upgrade`` is skipped
    and the cache is invalidated.
    """
    # Pre-flock: remote ahead of primed local (triggers _maybe_check_upstream
    # → True, entering orchestration). Post-flock: fresh remote == fresh local.
    fake_run, calls = _make_upgrade_recorder(
        pre_flock_remote_sha="b" * 40,
        post_flock_remote_sha="d" * 40,
        post_flock_local_head="d" * 40,  # local has caught up to fresh remote
    )

    cortex_root = tmp_path / "cortex"
    (cortex_root / ".git").mkdir(parents=True)
    server_module._CORTEX_ROOT_CACHE = {
        "version": "1.0",
        "root": str(cortex_root),
        "remote_url": "git@github.com:user/cortex-command.git",
        "head_sha": "a" * 40,
    }

    with patch.object(
        server_module.subprocess, "run", side_effect=fake_run
    ):
        server_module._maybe_run_upgrade()

    # Crucial: NO `cortex upgrade` invocation despite pre-flock advance.
    assert _upgrade_calls(calls) == [], (
        f"redundant `cortex upgrade` was invoked despite local already "
        f"matching fresh upstream; got {calls}"
    )
    # Cache must be invalidated so the next tool call re-checks.
    assert server_module._UPDATE_CHECK_CACHE == {}


# ---------------------------------------------------------------------------
# Cross-process flock contention (R11)
# ---------------------------------------------------------------------------


def _concurrent_upgrade_worker(
    cortex_root_str: str,
    remote_url: str,
    head_sha: str,
    advanced_head_sha: str,
    plugin_root: str,
    output_path: str,
    barrier_path: str,
    upgrade_marker_path: str,
    advance_signal_path: str,
) -> None:
    """Variant of the worker that simulates ``cortex upgrade`` advancing HEAD.

    The first worker to enter ``cortex upgrade`` writes
    ``advanced_head_sha`` to ``advance_signal_path`` (mocking the
    upgrade actually bumping the local HEAD). The post-flock fresh
    ``git rev-parse HEAD`` mock reads from this file: if it exists, it
    returns ``advanced_head_sha``; otherwise it returns ``head_sha``.
    The post-flock fresh ``git ls-remote`` always returns
    ``advanced_head_sha`` (the upstream the upgrade caught up to).

    Effect: the first worker upgrades; the second worker, on flock
    acquisition, sees fresh-local-HEAD == fresh-remote-sha and skips
    the redundant invocation per spec.
    """
    import importlib.util
    import json as _json
    import os as _os
    import sys as _sys
    import time as _time
    from pathlib import Path as _Path
    from unittest.mock import patch as _patch

    server_path = _Path(plugin_root) / "server.py"
    _os.environ["CLAUDE_PLUGIN_ROOT"] = plugin_root

    spec = importlib.util.spec_from_file_location(
        "cortex_plugin_server_worker", server_path
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    _sys.modules["cortex_plugin_server_worker"] = mod
    spec.loader.exec_module(mod)

    mod._CORTEX_ROOT_CACHE = {
        "version": "1.0",
        "root": cortex_root_str,
        "remote_url": remote_url,
        "head_sha": head_sha,
    }

    upgrade_invoked_here = {"v": False}

    def _fake_run(argv, **kwargs):
        if argv[:2] == ["git", "ls-remote"]:
            # Post-flock fresh ls-remote: always return the advanced sha
            # (the upstream the upgrade brought us to).
            return subprocess.CompletedProcess(
                args=list(argv),
                returncode=0,
                stdout=advanced_head_sha + "\tHEAD\n",
                stderr="",
            )
        if (
            len(argv) >= 5
            and argv[0] == "git"
            and argv[1] == "-C"
            and argv[3] == "rev-parse"
            and argv[4] == "HEAD"
        ):
            # Post-flock fresh local HEAD: if a worker has already
            # "applied" the upgrade (signalled via `advance_signal_path`),
            # return the advanced sha so the redundant-skip branch fires.
            if _os.path.exists(advance_signal_path):
                return subprocess.CompletedProcess(
                    args=list(argv),
                    returncode=0,
                    stdout=advanced_head_sha + "\n",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=list(argv),
                returncode=0,
                stdout=head_sha + "\n",
                stderr="",
            )
        if argv[:2] == ["cortex", "upgrade"]:
            upgrade_invoked_here["v"] = True
            with open(upgrade_marker_path, "a", encoding="utf-8") as fh:
                fh.write(f"{_os.getpid()}\n")
            # Simulate the upgrade actually advancing local HEAD by
            # writing the signal file BEFORE returning.
            with open(advance_signal_path, "w", encoding="utf-8") as fh:
                fh.write(advanced_head_sha)
            _time.sleep(0.3)
            return subprocess.CompletedProcess(
                args=list(argv), returncode=0, stdout="", stderr=""
            )
        return subprocess.CompletedProcess(
            args=list(argv), returncode=0, stdout="", stderr=""
        )

    with open(barrier_path, "a", encoding="utf-8") as fh:
        fh.write(f"{_os.getpid()}\n")
    deadline = _time.monotonic() + 10.0
    while _time.monotonic() < deadline:
        with open(barrier_path, encoding="utf-8") as fh:
            content = fh.read()
        if len([line for line in content.splitlines() if line.strip()]) >= 2:
            break
        _time.sleep(0.02)

    payload = mod._CORTEX_ROOT_CACHE
    error: str | None = None
    try:
        with _patch.object(mod.subprocess, "run", side_effect=_fake_run):
            mod._orchestrate_upgrade(payload)
    except BaseException as exc:  # noqa: BLE001
        error = f"{exc.__class__.__name__}: {exc}"

    with open(output_path, "w", encoding="utf-8") as fh:
        _json.dump(
            {
                "pid": _os.getpid(),
                "upgrade_invoked": upgrade_invoked_here["v"],
                "error": error,
            },
            fh,
        )


def test_concurrent_upgrade_only_one_subprocess_runs(
    server_module, tmp_path: Path
) -> None:
    """R11 acceptance: only ONE ``cortex upgrade`` runs across two processes.

    Spec R11 acceptance:
    ``test_concurrent_upgrade_only_one_subprocess_runs``.

    Two real OS processes contend on the real lock file. The first
    worker acquires the flock and "applies" the upgrade (the worker
    fixture writes the advanced HEAD sha to ``advance_signal_path``,
    simulating ``cortex upgrade`` actually bumping local HEAD). The
    second worker, on flock acquisition, runs the post-flock fresh
    re-verify: ``git ls-remote`` returns the advanced sha; ``git
    rev-parse HEAD`` (mocked to read ``advance_signal_path``) also
    returns the advanced sha. Per spec Technical Constraints "R11
    post-acquire HEAD re-verification reference point", the second
    worker observes ``fresh_remote_sha == fresh_local_head`` and skips
    the redundant ``cortex upgrade`` invocation.

    Strict assertion: ``upgrade_marker_path`` contains exactly ONE PID
    line.

    NB: ``fcntl.flock`` is process-scoped on macOS/Linux; threads share
    lock ownership and a thread-based test cannot exercise contention.
    Per the task brief, this test uses ``multiprocessing.Process``.
    """
    cortex_root = tmp_path / "cortex"
    (cortex_root / ".git").mkdir(parents=True)
    head_sha = "a" * 40
    advanced_head_sha = "f" * 40
    remote_url = "git@github.com:user/cortex-command.git"
    plugin_root = str(PLUGIN_ROOT)

    output_a = tmp_path / "result-a.json"
    output_b = tmp_path / "result-b.json"
    barrier = tmp_path / "barrier.txt"
    upgrade_marker = tmp_path / "upgrade-marker.txt"
    advance_signal = tmp_path / "advance-signal.txt"

    ctx = multiprocessing.get_context("fork")
    p_a = ctx.Process(
        target=_concurrent_upgrade_worker,
        args=(
            str(cortex_root),
            remote_url,
            head_sha,
            advanced_head_sha,
            plugin_root,
            str(output_a),
            str(barrier),
            str(upgrade_marker),
            str(advance_signal),
        ),
    )
    p_b = ctx.Process(
        target=_concurrent_upgrade_worker,
        args=(
            str(cortex_root),
            remote_url,
            head_sha,
            advanced_head_sha,
            plugin_root,
            str(output_b),
            str(barrier),
            str(upgrade_marker),
            str(advance_signal),
        ),
    )

    p_a.start()
    p_b.start()
    p_a.join(timeout=60)
    p_b.join(timeout=60)

    assert p_a.exitcode == 0, f"worker A exited {p_a.exitcode}"
    assert p_b.exitcode == 0, f"worker B exited {p_b.exitcode}"

    marker_content = upgrade_marker.read_text(encoding="utf-8") if (
        upgrade_marker.exists()
    ) else ""
    pid_lines = [
        line for line in marker_content.splitlines() if line.strip()
    ]
    assert len(pid_lines) == 1, (
        f"only ONE worker should invoke `cortex upgrade` (the other "
        f"hits the post-flock redundant-skip branch); "
        f"got {len(pid_lines)} PID lines: {pid_lines!r}"
    )


def test_concurrent_upgrade_both_processes_return_success(
    server_module, tmp_path: Path
) -> None:
    """R11 acceptance: the loser of the flock contention proceeds correctly.

    Spec R11 acceptance:
    ``test_concurrent_upgrade_both_threads_return_success`` (the spec
    text says "threads"; the spec's Task 8 brief amends this to two
    real OS processes since flock is process-scoped).

    Both workers must exit cleanly (no exceptions, exit code 0). The
    loser of the flock contention waits, acquires, observes the
    "already applied" state, and returns without raising.
    """
    cortex_root = tmp_path / "cortex"
    (cortex_root / ".git").mkdir(parents=True)
    head_sha = "a" * 40
    advanced_head_sha = "f" * 40
    remote_url = "git@github.com:user/cortex-command.git"
    plugin_root = str(PLUGIN_ROOT)

    output_a = tmp_path / "result-a.json"
    output_b = tmp_path / "result-b.json"
    barrier = tmp_path / "barrier.txt"
    upgrade_marker = tmp_path / "upgrade-marker.txt"
    advance_signal = tmp_path / "advance-signal.txt"

    ctx = multiprocessing.get_context("fork")
    p_a = ctx.Process(
        target=_concurrent_upgrade_worker,
        args=(
            str(cortex_root),
            remote_url,
            head_sha,
            advanced_head_sha,
            plugin_root,
            str(output_a),
            str(barrier),
            str(upgrade_marker),
            str(advance_signal),
        ),
    )
    p_b = ctx.Process(
        target=_concurrent_upgrade_worker,
        args=(
            str(cortex_root),
            remote_url,
            head_sha,
            advanced_head_sha,
            plugin_root,
            str(output_b),
            str(barrier),
            str(upgrade_marker),
            str(advance_signal),
        ),
    )

    p_a.start()
    p_b.start()
    p_a.join(timeout=60)
    p_b.join(timeout=60)

    assert p_a.exitcode == 0
    assert p_b.exitcode == 0

    result_a = json.loads(output_a.read_text(encoding="utf-8"))
    result_b = json.loads(output_b.read_text(encoding="utf-8"))

    assert result_a["error"] is None, f"worker A: {result_a['error']}"
    assert result_b["error"] is None, f"worker B: {result_b['error']}"

    # Exactly one worker invoked `cortex upgrade`; both reported clean.
    invoked_workers = sum(
        1
        for r in (result_a, result_b)
        if r["upgrade_invoked"]
    )
    assert invoked_workers == 1, (
        f"exactly one worker must have invoked the upgrade; "
        f"got {invoked_workers}"
    )
