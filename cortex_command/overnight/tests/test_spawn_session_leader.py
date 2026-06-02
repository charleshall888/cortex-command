"""Phase-1 session-leader detach guard (R2, R3).

Platform-agnostic guard (NOT ``skipUnless(darwin)``) that spawns the
runner through the PRODUCTION detach path —
:func:`cli_handler._spawn_runner_async`'s
``subprocess.Popen(..., start_new_session=True)`` — and asserts the
spawned runner is a session leader that would survive launchd's
process-group SIGTERM:

  * ``os.getsid(pid) == pid``  — the child is its own session leader
    (``start_new_session=True`` ran ``setsid()`` in the child);
  * ``os.getsid(pid) != os.getsid(0)`` — the child's session differs
    from the parent test process's session, so a signal scoped to the
    parent's session/process-group does not reach the runner.

``os.getsid(pid) == pid`` alone is a POSIX-invariant proxy that holds
for ANY ``start_new_session=True`` child (including a faked one). The
join that ties this session-leader property to the REAL launcher
invocation lives in ``test_launcher_argv.py``'s routing test
(``handle_start`` dispatches the no-``--launchd`` launcher argv to
``_spawn_runner_async``). Together they prove the launcher routes to the
async-spawn path AND that path yields a session leader.

Runs via ``just test`` anywhere the suite runs. NOT wired into GitHub
Actions today (``validate.yml`` runs only skill + callgraph validators);
CI-wiring is an out-of-scope follow-up.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from cortex_command.overnight import cli_handler


def _write_minimal_state(session_dir: Path, session_id: str) -> Path:
    session_dir.mkdir(parents=True, exist_ok=True)
    state_path = session_dir / "overnight-state.json"
    state_path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "phase": "executing",
                "plan_ref": "cortex/lifecycle/overnight-plan.md",
                "current_round": 1,
                "started_at": "2026-04-26T00:00:00+00:00",
                "updated_at": "2026-04-26T00:00:00+00:00",
                "features": {},
            }
        ),
        encoding="utf-8",
    )
    return state_path


def _fake_runner_source(session_dir: Path) -> str:
    """A controllable runner that writes ``runner.pid`` then sleeps.

    It records its own pid so the handshake's liveness probe verifies and
    ``_spawn_runner_async`` returns ``started: True`` with the real pid —
    which we then probe for session-leader status. It sleeps long enough
    to remain alive while we read ``os.getsid(pid)``.
    """
    pid_path = session_dir / "runner.pid"
    return (
        "import json, os, time\n"
        f"payload = {{'schema_version': 1, 'magic': 'cortex-runner-v1', "
        f"'pid': os.getpid(), 'pgid': os.getpgid(os.getpid()), "
        f"'start_time': '2026-04-26T00:00:00+00:00', "
        f"'session_id': {session_dir.name!r}, "
        f"'session_dir': {str(session_dir)!r}, 'repo_path': '/tmp'}}\n"
        f"with open({str(pid_path)!r}, 'w', encoding='utf-8') as f:\n"
        "    json.dump(payload, f)\n"
        "    f.flush()\n"
        "    os.fsync(f.fileno())\n"
        "time.sleep(30)\n"
    )


class TestSpawnSessionLeader(unittest.TestCase):
    """The production detach path yields a runner that is a session leader."""

    def test_spawned_runner_is_session_leader(self) -> None:
        with TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            session_id = "session-leader-test"
            session_dir = tmp / "sessions" / session_id
            state_path = _write_minimal_state(session_dir, session_id)

            script = _fake_runner_source(session_dir)

            # Route the real ``_spawn_runner_async`` Popen at a
            # controllable runner that claims runner.pid then sleeps. This
            # still exercises the production ``start_new_session=True``
            # detach — the property under test (session-leader status) is
            # a property of that Popen call, not of the runner's payload.
            original_build = cli_handler._build_async_spawn_argv

            def fake_argv(args, sp):  # type: ignore[no-untyped-def]
                return [sys.executable, "-c", script]

            args = argparse.Namespace(
                state=str(state_path),
                time_limit=None,
                max_rounds=None,
                tier="simple",
                dry_run=False,
                format="json",
                launchd=False,
            )

            pid: int | None = None
            try:
                cli_handler._build_async_spawn_argv = fake_argv  # type: ignore[assignment]
                result = cli_handler._spawn_runner_async(
                    state_path=state_path,
                    session_dir=session_dir,
                    repo_path=tmp,
                    args=args,
                )
                self.assertTrue(
                    result.get("started"),
                    f"production spawn did not start; result={result!r}",
                )
                pid = result.get("pid")
                self.assertIsInstance(pid, int)

                # The runner is its own session leader.
                self.assertEqual(
                    os.getsid(pid),
                    pid,
                    "spawned runner is not a session leader "
                    "(os.getsid(pid) != pid) — start_new_session did not "
                    "create a new session",
                )
                # Its session differs from the parent test process's, so a
                # process-group/session-scoped SIGTERM aimed at the parent
                # does not reach the runner.
                self.assertNotEqual(
                    os.getsid(pid),
                    os.getsid(0),
                    "spawned runner shares the parent's session — it would "
                    "be reaped by a signal scoped to the parent's session",
                )
            finally:
                cli_handler._build_async_spawn_argv = original_build  # type: ignore[assignment]
                if isinstance(pid, int):
                    try:
                        os.killpg(os.getpgid(pid), signal.SIGKILL)
                    except (ProcessLookupError, OSError):
                        pass
                # Best-effort sweep in case the pid was never returned.
                subprocess.run(
                    ["pkill", "-f", "session-leader-test"],
                    check=False,
                )


if __name__ == "__main__":
    unittest.main()
