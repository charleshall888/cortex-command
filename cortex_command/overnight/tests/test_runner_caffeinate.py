"""Tests for the runner-lifetime-bound ``caffeinate`` idle-sleep assertion.

Covers spec R4 / Task 2: the runner spawns ``caffeinate -i -w <runner_pid>``
as the **earliest action** in its process entry (before state load and
takeover-lock acquisition). The ``-i`` flag asserts no-idle-sleep; ``-w
<pid>`` binds caffeinate's lifetime to the runner so the assertion drops
only when the runner exits.

Two behavioral invariants under test:

* **Positive (lifetime binding).** The caffeinate child is still alive
  after the ``_SPAWN_HANDSHAKE_TIMEOUT_SECONDS`` window (so it is NOT the
  launcher-level / shim-owned assertion that the F3 bug dropped at
  handshake return), AND it exits once the runner exits.
* **Negative (process-tree contract).** caffeinate is NOT the session
  leader / ``Popen`` target and is NOT a child of the ~5s
  ``_spawn_runner_async`` shim — its parent is the runner pid and it is a
  distinct process from the session-leader-establishing spawn.

The production helper builds ``caffeinate -i -w <pid>``; the real
``caffeinate -w`` wait semantics are macOS-only, so these tests shim a
fake ``caffeinate`` on ``PATH`` that itself implements the ``-w <pid>``
wait (poll until the pid dies, then exit). This faithfully exercises the
production argv and the lifetime binding on any platform the suite runs.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from cortex_command.overnight import runner as runner_module
from cortex_command.overnight.cli_handler import _SPAWN_HANDSHAKE_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _install_fake_caffeinate(bin_dir: Path) -> Path:
    """Write a fake ``caffeinate`` onto ``PATH`` and return its path.

    The fake honors the production argv ``caffeinate -i -w <pid>`` by
    implementing the ``-w <pid>`` wait itself: it polls until ``<pid>``
    is no longer a live process, then exits. This makes the
    runner-lifetime binding observable on platforms (e.g. Linux) where
    the real ``caffeinate`` does not exist.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake = bin_dir / "caffeinate"
    fake.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import os
            import sys
            import time

            # Parse ``-i -w <pid>``: -i is the (no-op here) assertion flag,
            # -w binds lifetime to the given pid.
            watch_pid = None
            argv = sys.argv[1:]
            for i, tok in enumerate(argv):
                if tok == "-w" and i + 1 < len(argv):
                    watch_pid = int(argv[i + 1])
            if watch_pid is None:
                # No -w: a bare assertion would run forever; bound it so a
                # buggy spawn cannot leak a process across the test run.
                time.sleep(60)
                sys.exit(0)
            while True:
                try:
                    os.kill(watch_pid, 0)
                except ProcessLookupError:
                    break
                except PermissionError:
                    # pid exists but not ours — still alive, keep waiting.
                    pass
                time.sleep(0.05)
            sys.exit(0)
            """
        ),
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return fake


_RUNNER_STUB = textwrap.dedent(
    """\
    import os
    import sys
    import time
    from pathlib import Path

    from cortex_command.overnight import runner as runner_module

    handshake = Path(sys.argv[1])

    # This process plays the role of the runner: it was spawned with
    # ``start_new_session=True`` (so it is the session leader) and it
    # invokes the production helper directly as its earliest action.
    child = runner_module._spawn_caffeinate_bound_to_runner()

    payload = {
        "runner_pid": os.getpid(),
        "session_leader": os.getsid(0),
        "caffeinate_pid": (child.pid if child is not None else None),
    }
    import json
    handshake.write_text(json.dumps(payload), encoding="utf-8")

    # Idle until the parent kills us; the bound caffeinate child must
    # outlive the handshake window and then exit when we do.
    while True:
        time.sleep(0.2)
    """
)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _ppid_of(pid: int) -> int:
    """Return the parent pid of ``pid`` via psutil (portable)."""
    import psutil

    return psutil.Process(pid).ppid()


# ---------------------------------------------------------------------------
# Unit: the production helper builds the correct argv and binds to self.
# ---------------------------------------------------------------------------


def test_helper_spawns_caffeinate_with_assertion_and_lifetime_bind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_spawn_caffeinate_bound_to_runner`` runs ``caffeinate -i -w <self>``.

    The ``-i`` assertion flag must be present (a bare ``-w`` holds NO
    assertion and is wrong) and ``-w`` must bind to the calling process's
    own pid so the assertion lasts the runner's lifetime.
    """
    bin_dir = tmp_path / "bin"
    _install_fake_caffeinate(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    # Capture the argv the helper hands to Popen.
    captured: dict = {}
    real_popen = subprocess.Popen

    def _capture_popen(argv, *a, **kw):
        captured["argv"] = list(argv)
        return real_popen(argv, *a, **kw)

    monkeypatch.setattr(runner_module.subprocess, "Popen", _capture_popen)

    child = runner_module._spawn_caffeinate_bound_to_runner()
    try:
        assert child is not None
        argv = captured["argv"]
        assert argv[0] == "caffeinate"
        assert "-i" in argv  # the assertion (NOT a bare -w)
        assert "-w" in argv  # lifetime bind
        # ``-w`` value is THIS process's pid (the runner), not anything else.
        w_index = argv.index("-w")
        assert argv[w_index + 1] == str(os.getpid())
    finally:
        if child is not None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()


def test_helper_is_best_effort_when_caffeinate_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing ``caffeinate`` binary returns ``None`` and does not raise."""
    # Point PATH at an empty dir so the binary cannot be found.
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))

    # Should swallow the OSError and return None rather than crash.
    assert runner_module._spawn_caffeinate_bound_to_runner() is None


# ---------------------------------------------------------------------------
# Behavioral: alive past the handshake window, dies with the runner, and
# the process-tree negative invariant.
# ---------------------------------------------------------------------------


def test_caffeinate_outlives_handshake_and_dies_with_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end lifetime + process-tree contract for the bound child.

    Spawns a real "runner" subprocess as a session leader
    (``start_new_session=True``, mirroring the production
    ``_spawn_runner_async`` shim) that invokes the production helper. The
    test (playing the shim's role) then asserts:

    (a) the caffeinate child is still alive after the
        ``_SPAWN_HANDSHAKE_TIMEOUT_SECONDS`` window and exits when the
        runner exits; and
    (b) the negative invariant — caffeinate's parent is the runner pid,
        it is NOT the session leader / ``Popen`` target, and it is a
        distinct process from the session-leader-establishing spawn (the
        runner itself).
    """
    bin_dir = tmp_path / "bin"
    _install_fake_caffeinate(bin_dir)

    stub_path = tmp_path / "runner_stub.py"
    stub_path.write_text(_RUNNER_STUB, encoding="utf-8")
    handshake = tmp_path / "handshake.json"

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"

    # Spawn the runner as the session leader, exactly as the production
    # shim does at cli_handler.py: ``subprocess.Popen(start_new_session=True)``.
    runner = subprocess.Popen(
        [sys.executable, str(stub_path), str(handshake)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )
    caffeinate_pid = None
    try:
        # Wait for the runner to record its handshake payload.
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and not handshake.exists():
            time.sleep(0.05)
        assert handshake.exists(), "runner stub never wrote its handshake"

        import json

        payload = json.loads(handshake.read_text(encoding="utf-8"))
        runner_pid = payload["runner_pid"]
        caffeinate_pid = payload["caffeinate_pid"]
        assert caffeinate_pid is not None, "runner did not spawn caffeinate"

        # The runner is the session leader (it was spawned start_new_session).
        assert runner_pid == runner.pid

        # --- (a) Outlives the handshake window -------------------------
        # Sleep past the full handshake budget plus margin; the bound
        # child must NOT have dropped its assertion at handshake return.
        time.sleep(_SPAWN_HANDSHAKE_TIMEOUT_SECONDS + 1.0)
        assert _pid_alive(caffeinate_pid), (
            "caffeinate must outlive the handshake window — a shim-owned "
            "or launcher-level assertion would have dropped here (F3 bug)"
        )

        # --- (b) Negative process-tree invariant -----------------------
        # caffeinate's parent is the RUNNER, not the shim / this test.
        assert _ppid_of(caffeinate_pid) == runner_pid
        # caffeinate is NOT the session-leader / Popen-target spawn.
        assert caffeinate_pid != runner_pid
        assert caffeinate_pid != os.getpid()

        # --- (a, cont.) Dies when the runner exits ---------------------
        runner.terminate()
        runner.wait(timeout=10)

        # The bound caffeinate child must exit once the runner pid is gone.
        gone_deadline = time.monotonic() + 5.0
        while time.monotonic() < gone_deadline and _pid_alive(caffeinate_pid):
            time.sleep(0.05)
        assert not _pid_alive(caffeinate_pid), (
            "caffeinate must exit when the runner exits (-w lifetime bind)"
        )
    finally:
        if runner.poll() is None:
            runner.kill()
            try:
                runner.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        if caffeinate_pid is not None and _pid_alive(caffeinate_pid):
            try:
                os.kill(caffeinate_pid, 9)
            except ProcessLookupError:
                pass
