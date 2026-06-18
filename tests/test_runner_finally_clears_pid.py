"""Task 7: a non-signaled runner exit best-effort clears ``runner.pid``.

A silent (non-signaled SIGKILL/OOM-style) crash or an unhandled exception
that exits the round loop must not leave a stale ``runner.pid`` behind
while ``overnight-state.json`` stays ``phase: executing`` — that masks the
stuck state from out-of-process observers. The signal path already clears
the pid in ``_cleanup`` and the clean path in ``_post_loop``; this test
guards the third path: the ``finally`` block in :func:`runner.run` now
best-effort clears the pid (CAS on ``session_id``) so a crash-driven
loop-exit also leaves no stale pid.

The authoritative clear remains the out-of-process recovery core (a later
task); this is defense-in-depth on the runner side.

Why not drive the full ``runner.run`` in-process: ``_start_session``
records ``start_time = datetime.now()`` and ``ipc.verify_runner_pid``
requires that to match ``psutil.Process(pid).create_time()`` within ±2s.
That only holds for a *freshly spawned* runner process — never for the
long-lived pytest process driving ``run`` after the suite has been running
for a while (its create_time is far in the past). So this test exercises
the finally's exact behavior directly: it (1) reproduces the operation the
finally performs (the session-scoped CAS ``clear_runner_pid``) against a
genuinely-live ``runner.pid`` and asserts no stale pid survives, and (2)
asserts the ``run`` ``finally`` is actually wired to perform that clear, so
removing the call regresses this test.
"""

from __future__ import annotations

import ast
import inspect
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psutil

from cortex_command.overnight import ipc, runner


def _live_start_time_iso() -> str:
    """Return this process's ``create_time`` as an ISO-8601 string.

    Using the real create_time (not ``datetime.now()``) makes
    ``verify_runner_pid`` genuinely pass regardless of how long the test
    process has been alive.
    """
    epoch = psutil.Process(os.getpid()).create_time()
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _write_live_runner_pid(session_dir: Path, session_id: str) -> dict:
    """Write a ``runner.pid`` for ``session_id`` that verifies as live.

    Returns the payload that was written so callers can re-check it with
    ``verify_runner_pid`` after the clear.
    """
    payload = {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": os.getpid(),
        "pgid": os.getpgrp(),
        "start_time": _live_start_time_iso(),
        "session_id": session_id,
        "session_dir": str(session_dir),
        "repo_path": str(session_dir),
    }
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "runner.pid").write_text(json.dumps(payload), encoding="utf-8")
    return payload


def test_finally_clear_removes_live_pid_for_owning_session(tmp_path: Path) -> None:
    """The finally's session-scoped CAS clear removes the owner's pid.

    Reproduces the exact operation ``run``'s ``finally`` performs on a
    non-signaled exit: ``ipc.clear_runner_pid(session_dir,
    expected_session_id=session_id)``. Starting from a genuinely-live
    ``runner.pid`` (so ``verify_runner_pid`` is True up front), after the
    clear the file is absent and ``verify_runner_pid`` no longer returns
    True for the on-disk artifact — an out-of-process observer sees no
    stale pid.
    """
    session_id = "overnight-2026-04-24-crash"
    session_dir = tmp_path / "lifecycle" / "sessions" / session_id

    payload = _write_live_runner_pid(session_dir, session_id)

    # Precondition: the pid is genuinely live before the crash-cleanup.
    on_disk = ipc.read_runner_pid(session_dir)
    assert on_disk is not None
    assert ipc.verify_runner_pid(on_disk) is True

    # The operation the finally performs on a non-signaled exit.
    ipc.clear_runner_pid(session_dir, expected_session_id=session_id)

    # End state: no stale pid survives.
    assert not (session_dir / "runner.pid").exists()
    assert ipc.read_runner_pid(session_dir) is None
    # verify_runner_pid on the (now-absent) on-disk artifact yields no live
    # claim: read returns None, so an observer sees no stale pid.
    assert ipc.read_runner_pid(session_dir) is None
    # The payload itself is unchanged in memory; the point is the file is
    # gone — re-reading it as an observer would returns nothing.
    assert payload["session_id"] == session_id


def test_finally_clear_is_a_noop_for_a_foreign_owner(tmp_path: Path) -> None:
    """The session-scoped CAS does not clobber another session's claim.

    A non-signaled exit using ``expected_session_id`` must NOT remove a
    ``runner.pid`` owned by a *different* session (the takeover-transition
    safety the CAS provides). This guards against the finally being made
    unconditional.
    """
    session_dir = tmp_path / "lifecycle" / "sessions" / "session-A"
    _write_live_runner_pid(session_dir, "session-A")

    # A stale displaced owner ("session-B") tries to clear on its exit.
    ipc.clear_runner_pid(session_dir, expected_session_id="session-B")

    # session-A's claim survives untouched.
    survivor = ipc.read_runner_pid(session_dir)
    assert survivor is not None
    assert survivor.get("session_id") == "session-A"


def test_run_finally_is_wired_to_clear_runner_pid() -> None:
    """``run``'s ``finally`` performs the best-effort pid clear.

    Wiring guard: parse ``run`` and assert its ``finally`` body contains a
    call to ``ipc.clear_runner_pid`` passing ``expected_session_id`` (the
    session-scoped CAS form). Removing the clear from the finally — the
    regression this whole task defends against — fails this test.

    A source/AST assertion is used here (rather than driving ``run``
    end-to-end) because ``verify_runner_pid``'s ±2s create_time match
    cannot hold for the long-lived pytest process, making a faithful
    in-process ``run`` drive infeasible; the behavioral contract of the
    clear itself is covered by the tests above.
    """
    source = inspect.getsource(runner.run)
    tree = ast.parse(source)

    func = tree.body[0]
    assert isinstance(func, ast.FunctionDef)

    # Collect Try nodes that have a finalbody (the ``finally`` block).
    finally_calls: list[ast.Call] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Try) and node.finalbody:
            for stmt in node.finalbody:
                for inner in ast.walk(stmt):
                    if isinstance(inner, ast.Call):
                        finally_calls.append(inner)

    def _is_clear_runner_pid(call: ast.Call) -> bool:
        callee = call.func
        if not (
            isinstance(callee, ast.Attribute)
            and callee.attr == "clear_runner_pid"
        ):
            return False
        # Must pass the session-scoped CAS keyword (expected_session_id),
        # not the unconditional form.
        return any(
            kw.arg == "expected_session_id" for kw in call.keywords
        )

    assert any(_is_clear_runner_pid(c) for c in finally_calls), (
        "run()'s finally must call "
        "ipc.clear_runner_pid(..., expected_session_id=...) so a "
        "non-signaled exit best-effort clears the stale runner.pid"
    )
