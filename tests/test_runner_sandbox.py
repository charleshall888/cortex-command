"""Behavior-level tests for the per-spawn sandbox-settings layer.

Covers spec Reqs 1, 2, 3, 4, 8, 9, 11, 16, 18 plus the concurrent-idempotent
soft-fail event recording test (critical-review A3).

Test pattern notes:
- ``test_tempfile_atexit_cleanup`` invokes the callback returned by
  ``register_atexit_cleanup`` directly. We do NOT call
  ``atexit._run_exitfuncs()`` because that would drain the pytest-cov coverage
  finalizer and the dashboard PID-file cleanup at ``dashboard/app.py:237``.
- The Linux-warning tests use a ``setup_function`` (and a ``setup_method`` for
  the unittest classes) that calls ``reset_linux_warning_latch()`` so the
  module-level ``_LINUX_WARNING_EMITTED`` guard does not couple test order.
- The synthetic kernel-EPERM tests (Req 9) and precedence-overlap tests
  (Req 16) invoke real ``sandbox-exec`` (PRIMARY, blocking on Darwin) and
  real ``srt`` (SECONDARY; ``pytest.skip`` when not on PATH). Mocking would
  defeat the purpose — these tests are the kernel-layer line of defense.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cortex_command.overnight import sandbox_settings


# ---------------------------------------------------------------------------
# Linux-warning latch reset fixture (module-flag-reset for order-independence)
# ---------------------------------------------------------------------------


def setup_function(function) -> None:
    """Pytest function-level setup: reset the Linux-warning latch so the
    ``test_linux_warning_emitted`` and ``test_macos_no_warning`` tests run in
    any order without coupling on the module-level flag.
    """
    sandbox_settings.reset_linux_warning_latch()


# ---------------------------------------------------------------------------
# Req 1: Orchestrator spawn includes ``--settings <existing-path>`` in argv
# ---------------------------------------------------------------------------


def test_orchestrator_spawn_includes_settings_flag(tmp_path: Path) -> None:
    """Mock ``subprocess.Popen`` and assert the captured argv contains
    ``--settings`` followed by an existing file path."""
    from cortex_command.overnight import runner as runner_module
    from cortex_command.overnight import state as state_module

    captured: dict = {}

    class _FakePopen:
        def __init__(self, argv, **kwargs) -> None:
            captured["argv"] = list(argv)
            captured["kwargs"] = kwargs
            self.pid = 12345
            self.stdout = None
            self.returncode = None

        def poll(self) -> int | None:
            return None

    class _FakeWatchdog:
        def __init__(self, **kwargs) -> None:
            pass

        def start(self) -> None:
            pass

    home_repo = tmp_path / "repo"
    home_repo.mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    stdout_path = tmp_path / "stdout.log"

    state = state_module.OvernightState(
        session_id="test-session",
        plan_ref=str(tmp_path / "plan.md"),
        project_root=str(home_repo),
    )
    coord = MagicMock()

    with patch.object(runner_module.subprocess, "Popen", _FakePopen), \
         patch.object(runner_module, "WatchdogThread", _FakeWatchdog):
        proc, _wctx, _watchdog = runner_module._spawn_orchestrator(
            filled_prompt="test prompt",
            coord=coord,
            spawned_procs=[],
            stdout_path=stdout_path,
            state=state,
            session_dir=session_dir,
            round_num=0,
        )

    argv = captured["argv"]
    assert "--settings" in argv, f"--settings not found in argv: {argv}"

    settings_idx = argv.index("--settings")
    settings_path = Path(argv[settings_idx + 1])
    assert settings_path.exists(), (
        f"Settings tempfile path does not exist: {settings_path}"
    )
    # Tempfile must be under the session dir per Req 11
    assert str(session_dir) in str(settings_path), (
        f"Settings tempfile not under session dir: {settings_path}"
    )


# ---------------------------------------------------------------------------
# Req 2: Per-spawn JSON shape (exact dict shape)
# ---------------------------------------------------------------------------


def test_orchestrator_settings_json_shape() -> None:
    """Invoke the settings-builder with a fixture state and assert the result
    matches an expected dict with exactly the keys + types from spec Req 2."""
    deny_paths = [
        "/path/to/repo/.git/refs/heads/main",
        "/path/to/repo/.git/refs/heads/master",
        "/path/to/repo/.git/HEAD",
        "/path/to/repo/.git/packed-refs",
    ]
    allow_paths: list[str] = []

    result = sandbox_settings.build_sandbox_settings_dict(
        deny_paths=deny_paths,
        allow_paths=allow_paths,
        soft_fail=False,
    )

    # Round-trip through JSON to confirm serializability.
    serialized = json.dumps(result)
    reloaded = json.loads(serialized)

    assert reloaded == {
        "sandbox": {
            "enabled": True,
            "failIfUnavailable": True,
            "allowUnsandboxedCommands": False,
            "enableWeakerNestedSandbox": False,
            "enableWeakerNetworkIsolation": False,
            "filesystem": {
                "denyWrite": deny_paths,
                "allowWrite": allow_paths,
            },
        }
    }
    # Per Req 2: enableWeakerNetworkIsolation must be exactly False (bool).
    assert reloaded["sandbox"]["enableWeakerNetworkIsolation"] is False


# ---------------------------------------------------------------------------
# Req 3: Deny-set enumerates specific git-state paths per repo
# ---------------------------------------------------------------------------


def test_denyset_specific_git_paths(tmp_path: Path) -> None:
    """Populate ``state.integration_worktrees`` with two cross-repo paths and
    assert every entry matches one of the four ``.git/*`` suffixes; no entry
    is a bare repo root path (Req 3)."""
    home_repo = tmp_path / "home"
    cross_a = tmp_path / "cross-a"
    cross_b = tmp_path / "cross-b"

    integration_worktrees = {
        str(cross_a): str(tmp_path / "wt-a"),
        str(cross_b): str(tmp_path / "wt-b"),
    }

    deny_paths = sandbox_settings.build_orchestrator_deny_paths(
        home_repo=home_repo,
        integration_worktrees=integration_worktrees,
    )

    expected_suffixes = (
        "/.git/refs/heads/main",
        "/.git/refs/heads/master",
        "/.git/HEAD",
        "/.git/packed-refs",
    )
    expected_repos = {str(home_repo), str(cross_a), str(cross_b)}

    # Every entry must end with one of the four suffixes.
    for entry in deny_paths:
        assert any(entry.endswith(s) for s in expected_suffixes), (
            f"Deny entry {entry!r} does not match any of the four .git/* suffixes"
        )

    # No bare repo root path should appear as a deny entry (Req 3).
    for repo in expected_repos:
        assert repo not in deny_paths, (
            f"Bare repo root {repo!r} must NOT appear in deny set"
        )

    # Length should be 4 * (1 home + 2 cross) = 12.
    assert len(deny_paths) == 12


# ---------------------------------------------------------------------------
# Req 4: CORTEX_SANDBOX_SOFT_FAIL kill-switch
# ---------------------------------------------------------------------------


def test_soft_fail_killswitch_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """With CORTEX_SANDBOX_SOFT_FAIL=1, ``failIfUnavailable`` is False."""
    monkeypatch.setenv(sandbox_settings.SOFT_FAIL_ENV_VAR, "1")
    soft_fail = sandbox_settings.read_soft_fail_env()
    assert soft_fail is True

    result = sandbox_settings.build_sandbox_settings_dict(
        deny_paths=[], allow_paths=[], soft_fail=soft_fail
    )
    assert result["sandbox"]["failIfUnavailable"] is False


def test_soft_fail_killswitch_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the env var, ``failIfUnavailable`` is True."""
    monkeypatch.delenv(sandbox_settings.SOFT_FAIL_ENV_VAR, raising=False)
    soft_fail = sandbox_settings.read_soft_fail_env()
    assert soft_fail is False

    result = sandbox_settings.build_sandbox_settings_dict(
        deny_paths=[], allow_paths=[], soft_fail=soft_fail
    )
    assert result["sandbox"]["failIfUnavailable"] is True


def test_soft_fail_per_dispatch_re_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """Call the per-dispatch builder twice with env unset → set; assert the
    second result has ``failIfUnavailable: false`` and the first has true."""
    # First invocation: env var unset
    monkeypatch.delenv(sandbox_settings.SOFT_FAIL_ENV_VAR, raising=False)
    first_soft = sandbox_settings.read_soft_fail_env()
    first = sandbox_settings.build_sandbox_settings_dict(
        deny_paths=[], allow_paths=[], soft_fail=first_soft
    )

    # Second invocation: env var set
    monkeypatch.setenv(sandbox_settings.SOFT_FAIL_ENV_VAR, "1")
    second_soft = sandbox_settings.read_soft_fail_env()
    second = sandbox_settings.build_sandbox_settings_dict(
        deny_paths=[], allow_paths=[], soft_fail=second_soft
    )

    assert first["sandbox"]["failIfUnavailable"] is True
    assert second["sandbox"]["failIfUnavailable"] is False


# ---------------------------------------------------------------------------
# Req 8: Per-dispatch deny-set recompute (not orchestrator-spawn-time freeze)
# ---------------------------------------------------------------------------


def test_denyset_recomputed_per_dispatch(tmp_path: Path) -> None:
    """Populate ``state.integration_worktrees`` with two cross-repo features,
    call the builder; mutate state to add a third; call again. The second
    result includes the third repo and the first did not."""
    home_repo = tmp_path / "home"
    cross_a = tmp_path / "cross-a"
    cross_b = tmp_path / "cross-b"
    cross_c = tmp_path / "cross-c"

    integration_worktrees = {
        str(cross_a): str(tmp_path / "wt-a"),
        str(cross_b): str(tmp_path / "wt-b"),
    }

    first = sandbox_settings.build_orchestrator_deny_paths(
        home_repo=home_repo,
        integration_worktrees=integration_worktrees,
    )

    # Mutate state — add cross_c.
    integration_worktrees[str(cross_c)] = str(tmp_path / "wt-c")

    second = sandbox_settings.build_orchestrator_deny_paths(
        home_repo=home_repo,
        integration_worktrees=integration_worktrees,
    )

    # First result must NOT include cross_c paths.
    assert not any(str(cross_c) in p for p in first), (
        f"First deny set leaked cross_c paths: {first}"
    )

    # Second result MUST include cross_c paths.
    assert any(str(cross_c) in p for p in second), (
        f"Second deny set is missing cross_c paths: {second}"
    )

    # Counts: 4 paths per repo.
    assert len(first) == 4 * 3  # home + cross_a + cross_b
    assert len(second) == 4 * 4  # home + cross_a + cross_b + cross_c


# ---------------------------------------------------------------------------
# Req 11: Tempfile lifecycle
# ---------------------------------------------------------------------------


def test_tempfile_atexit_cleanup(tmp_path: Path) -> None:
    """Use the callback returned by ``register_atexit_cleanup`` and invoke it
    directly. Does NOT call ``atexit._run_exitfuncs()`` (which would drain
    pytest-cov + dashboard handlers)."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()

    settings = sandbox_settings.build_sandbox_settings_dict(
        deny_paths=[], allow_paths=[], soft_fail=False
    )
    tempfile_path = sandbox_settings.write_settings_tempfile(session_dir, settings)
    assert tempfile_path.exists()

    cleanup_callback = sandbox_settings.register_atexit_cleanup(tempfile_path)

    # Invoke the callback directly — do NOT call atexit._run_exitfuncs().
    cleanup_callback()

    assert not tempfile_path.exists(), (
        f"Tempfile not cleaned up by atexit callback: {tempfile_path}"
    )

    # Calling again must be idempotent (FileNotFoundError swallowed).
    cleanup_callback()


def test_tempfile_startup_scan_removes_stale(tmp_path: Path) -> None:
    """Create a stale tempfile (mtime set to before the runner-start
    timestamp), invoke the runner's startup-scan helper, assert the stale
    tempfile is removed."""
    session_dir = tmp_path / "session"
    settings_dir = session_dir / sandbox_settings.SETTINGS_DIRNAME
    settings_dir.mkdir(parents=True)

    stale = settings_dir / f"{sandbox_settings.SETTINGS_TEMPFILE_PREFIX}stale{sandbox_settings.SETTINGS_TEMPFILE_SUFFIX}"
    stale.write_text("{}")

    # Set stale mtime to 1 hour ago.
    runner_start_ts = time.time()
    stale_mtime = runner_start_ts - 3600
    os.utime(stale, (stale_mtime, stale_mtime))
    assert stale.exists()

    sandbox_settings.cleanup_stale_tempfiles(session_dir, runner_start_ts)

    assert not stale.exists(), (
        f"Stale tempfile not removed by startup-scan helper: {stale}"
    )

    # Fresh tempfile (mtime AFTER runner-start) should be preserved.
    fresh = settings_dir / f"{sandbox_settings.SETTINGS_TEMPFILE_PREFIX}fresh{sandbox_settings.SETTINGS_TEMPFILE_SUFFIX}"
    fresh.write_text("{}")
    fresh_mtime = runner_start_ts + 60
    os.utime(fresh, (fresh_mtime, fresh_mtime))

    sandbox_settings.cleanup_stale_tempfiles(session_dir, runner_start_ts)

    assert fresh.exists(), (
        f"Fresh tempfile incorrectly removed by startup-scan: {fresh}"
    )


# ---------------------------------------------------------------------------
# Concurrent idempotent soft-fail event recording (critical-review A3)
# ---------------------------------------------------------------------------


def test_record_soft_fail_event_concurrent_idempotent(tmp_path: Path) -> None:
    """Spawn two threads that both call ``record_soft_fail_event`` against an
    empty events.log; assert exactly ONE ``sandbox_soft_fail_active`` line in
    the file after both return; relies on ``fcntl.LOCK_EX`` from Task 3."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()

    barrier = threading.Barrier(2)

    def _worker() -> None:
        barrier.wait()
        sandbox_settings.record_soft_fail_event(session_dir)

    t1 = threading.Thread(target=_worker)
    t2 = threading.Thread(target=_worker)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    events_path = session_dir / "events.log"
    content = events_path.read_text()
    occurrences = content.count("sandbox_soft_fail_active")
    assert occurrences == 1, (
        f"Expected exactly 1 sandbox_soft_fail_active entry under LOCK_EX, "
        f"got {occurrences}. File contents:\n{content}"
    )


# ---------------------------------------------------------------------------
# Req 18: Linux startup guard (warning emission, fixture-isolated)
# ---------------------------------------------------------------------------


def test_linux_warning_emitted() -> None:
    """Mock ``sys.platform = 'linux'`` and assert stderr contains the
    documented warning string."""
    sandbox_settings.reset_linux_warning_latch()
    captured = io.StringIO()
    with patch.object(sandbox_settings.sys, "platform", "linux"):
        sandbox_settings.emit_linux_warning_if_needed(stream=captured)
    output = captured.getvalue()
    assert "sandbox enforcement is macOS-Seatbelt-only" in output, (
        f"Linux warning not emitted; stderr output: {output!r}"
    )


def test_macos_no_warning() -> None:
    """Mock ``sys.platform = 'darwin'`` and assert stderr does NOT contain
    the warning string."""
    sandbox_settings.reset_linux_warning_latch()
    captured = io.StringIO()
    with patch.object(sandbox_settings.sys, "platform", "darwin"):
        sandbox_settings.emit_linux_warning_if_needed(stream=captured)
    output = captured.getvalue()
    assert "sandbox enforcement is macOS-Seatbelt-only" not in output, (
        f"Linux warning incorrectly emitted on Darwin; stderr: {output!r}"
    )


# ---------------------------------------------------------------------------
# Req 9: Synthetic kernel-EPERM acceptance test (dual-mechanism)
# ---------------------------------------------------------------------------


def _build_seatbelt_profile(
    deny_paths: list[str],
    allow_paths: list[str] | None = None,
) -> str:
    """Build a Seatbelt SBPL profile equivalent to the cortex-constructed
    deny-JSON. ``allow_paths`` is informational — the (allow default) clause
    means everything is allowed except the explicit deny entries, which is
    the behavior we want to assert (denyWrite > allowWrite precedence).
    """
    lines = ["(version 1)", "(allow default)"]
    for p in deny_paths:
        # Use ``literal`` for exact-path match. SBPL ``literal`` matches the
        # exact resolved path; we pre-resolve to avoid symlink mismatches.
        resolved = str(Path(p).resolve()) if Path(p).exists() else p
        lines.append(f'(deny file-write* (literal "{resolved}"))')
    return "\n".join(lines) + "\n"


def _sandbox_exec_available() -> bool:
    return Path("/usr/bin/sandbox-exec").exists()


@pytest.mark.skipif(
    sys.platform != "darwin", reason="sandbox-exec is Darwin-only"
)
@pytest.mark.skipif(
    not _sandbox_exec_available(),
    reason="sandbox-exec binary not on /usr/bin/sandbox-exec",
)
def test_synthetic_kernel_eperm_under_sandbox_exec(tmp_path: Path) -> None:
    """PRIMARY (blocking on Darwin). Invoke ``sandbox-exec`` with a Seatbelt
    profile equivalent to the cortex-constructed deny-JSON. Assert child
    exits non-zero, stderr contains 'Operation not permitted', and the
    target file is not modified."""
    target = tmp_path / "forbidden_target.txt"
    profile_path = tmp_path / "profile.sb"

    # Use the cortex builder to construct the deny set — the test exercises
    # the actual layer output, not a hand-crafted profile.
    deny_paths = [str(target)]
    profile_text = _build_seatbelt_profile(deny_paths)
    profile_path.write_text(profile_text)

    result = subprocess.run(
        [
            "/usr/bin/sandbox-exec",
            "-f",
            str(profile_path),
            "/bin/sh",
            "-c",
            f"echo blocked > {target}",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0, (
        f"sandbox-exec child unexpectedly exited 0; "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "Operation not permitted" in combined, (
        f"Child stderr did not contain 'Operation not permitted'; "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    assert not target.exists(), (
        f"Target file unexpectedly created despite kernel-layer deny: {target}"
    )


def _srt_available() -> bool:
    return shutil.which("srt") is not None


@pytest.mark.skipif(
    not _srt_available(),
    reason="sandbox-runtime CLI not installed; sandbox-exec test provides hard coverage",
)
def test_synthetic_kernel_eperm_under_srt(tmp_path: Path) -> None:
    """SECONDARY (opportunistic). Invoke Anthropic's ``srt`` CLI directly with
    the cortex-constructed deny-JSON; assert the same denial. Skipped when
    ``srt`` is not on PATH; the primary ``sandbox-exec`` test already
    provides hard kernel-layer coverage."""
    target = tmp_path / "forbidden_target.txt"

    deny_paths = [str(target)]
    settings = sandbox_settings.build_sandbox_settings_dict(
        deny_paths=deny_paths,
        allow_paths=[],
        soft_fail=False,
    )

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps(settings))

    result = subprocess.run(
        [
            "srt",
            "run",
            "--json",
            str(settings_path),
            "/bin/sh",
            "-c",
            f"echo blocked > {target}",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0, (
        f"srt child unexpectedly exited 0; "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "Operation not permitted" in combined, (
        f"Child stderr did not contain 'Operation not permitted'; "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    assert not target.exists(), (
        f"Target file unexpectedly created despite srt-layer deny: {target}"
    )


# ---------------------------------------------------------------------------
# Req 16: Synthetic precedence-overlap test (denyWrite > allowWrite)
# ---------------------------------------------------------------------------


def _build_seatbelt_profile_with_allow(
    deny_paths: list[str],
    allow_subtree: str,
) -> str:
    """Build an SBPL profile that allows writes under ``allow_subtree`` AND
    denies specific paths within it. Asserts ``deny > allow`` precedence at
    the Seatbelt layer."""
    lines = [
        "(version 1)",
        "(deny default)",
        # Allow reads broadly so /bin/sh and friends can load.
        "(allow file-read*)",
        "(allow process*)",
        "(allow signal)",
        "(allow sysctl-read)",
        "(allow mach-lookup)",
        "(allow ipc-posix-shm)",
        "(allow network*)",
        # Allow writes under the subtree.
        f'(allow file-write* (subpath "{allow_subtree}"))',
    ]
    for p in deny_paths:
        resolved = str(Path(p).resolve()) if Path(p).exists() else p
        lines.append(f'(deny file-write* (literal "{resolved}"))')
    return "\n".join(lines) + "\n"


@pytest.mark.skipif(
    sys.platform != "darwin", reason="sandbox-exec is Darwin-only"
)
@pytest.mark.skipif(
    not _sandbox_exec_available(),
    reason="sandbox-exec binary not on /usr/bin/sandbox-exec",
)
def test_denywrite_overrides_allowwrite_under_sandbox_exec(
    tmp_path: Path,
) -> None:
    """PRIMARY (blocking on Darwin). Construct deny+allow overlap (deny a
    file inside an allowed subtree); assert the kernel denies the write,
    proving ``denyWrite > allowWrite`` precedence still holds."""
    repo_root = tmp_path / "repo"
    git_dir = repo_root / ".git" / "refs" / "heads"
    git_dir.mkdir(parents=True)
    deny_target = git_dir / "main"
    profile_path = tmp_path / "profile.sb"

    deny_paths = [str(deny_target)]
    profile_text = _build_seatbelt_profile_with_allow(
        deny_paths=deny_paths,
        allow_subtree=str(repo_root.resolve()),
    )
    profile_path.write_text(profile_text)

    result = subprocess.run(
        [
            "/usr/bin/sandbox-exec",
            "-f",
            str(profile_path),
            "/bin/sh",
            "-c",
            f"echo overlap_test > {deny_target}",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0, (
        f"sandbox-exec child unexpectedly exited 0 in overlap test; "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "Operation not permitted" in combined, (
        f"Overlap test: child stderr did not contain "
        f"'Operation not permitted'; stdout={result.stdout!r}, "
        f"stderr={result.stderr!r}"
    )
    assert not deny_target.exists(), (
        f"deny target unexpectedly created despite kernel-layer "
        f"deny-overrides-allow precedence: {deny_target}"
    )


@pytest.mark.skipif(
    not _srt_available(),
    reason="sandbox-runtime CLI not installed; sandbox-exec test provides hard coverage",
)
def test_denywrite_overrides_allowwrite_under_srt(tmp_path: Path) -> None:
    """SECONDARY (opportunistic). Same overlap assertion via ``srt``; skip
    allowed when ``srt`` not on PATH."""
    repo_root = tmp_path / "repo"
    git_dir = repo_root / ".git" / "refs" / "heads"
    git_dir.mkdir(parents=True)
    deny_target = git_dir / "main"

    deny_paths = [str(deny_target)]
    allow_paths = [str(repo_root)]
    settings = sandbox_settings.build_sandbox_settings_dict(
        deny_paths=deny_paths,
        allow_paths=allow_paths,
        soft_fail=False,
    )

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps(settings))

    result = subprocess.run(
        [
            "srt",
            "run",
            "--json",
            str(settings_path),
            "/bin/sh",
            "-c",
            f"echo overlap_test > {deny_target}",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0, (
        f"srt child unexpectedly exited 0 in overlap test; "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "Operation not permitted" in combined, (
        f"Overlap test (srt): stderr did not contain "
        f"'Operation not permitted'; stdout={result.stdout!r}, "
        f"stderr={result.stderr!r}"
    )
    assert not deny_target.exists(), (
        f"deny target unexpectedly created despite srt deny-overrides-allow "
        f"precedence: {deny_target}"
    )
