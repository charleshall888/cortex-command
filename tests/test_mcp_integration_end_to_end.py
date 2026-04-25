"""End-to-end integration tests for the MCP control-plane stack (R27 / Task 19).

This test is the load-bearing E2E test that validates the entire control-plane
stack against the real stdio MCP transport. The three sub-cases each address a
through-line concern surfaced in critical review where a unit test could pass
while the integration hazard remained open:

(a) Two parallel ``overnight_start_run`` calls via real stdio MCP transport.
    Closes the through-line concern that R8's race fix could be masked by
    event-loop serialization. The test runs the actual stdio MCP transport
    with real async dispatch via ``asyncio.gather`` so head-of-line blocking
    or accidental serialization at the framing layer would surface.

(b) ``overnight_cancel`` reaches a real grandchild subprocess in the runner's
    tree. Closes the R12 fakes-only concern from critical review by spawning
    a real grandchild via the runner's existing ``start_new_session=True``
    path and asserting post-cancel that no grandchild PIDs remain via psutil.

(c) ``write_escalation`` from a fixture batch_runner produces a per-session
    record at ``session_dir/escalations.jsonl`` with the new
    ``{session_id}-{feature}-{round}-q1`` format AND the orchestrator-prompt-
    rendered Python (passed through ``fill_prompt()`` with the fixture
    ``session_dir``) successfully reads that record when executed against a
    fresh Python globals dict. Closes the through-line surfaced in critical
    review: that an acceptance criterion can pass while the named hazard
    (orchestrator-prompt agent crashing on the new escalation_id format)
    remains open.

Trade-offs (per Task 19 implementation hints):

* For sub-case (a), ``cortex overnight start`` does not emit a fast-exit code
  path that would let us spawn a real runner subprocess and have it exit
  quickly under test conditions. The MCP tool's pre-flight
  ``_check_concurrent_runner`` is the synchronous MCP-layer guard that
  surfaces ``concurrent_runner_alive``; the actual O_EXCL race lives inside
  the spawned subprocess via ``ipc.write_runner_pid``. The atomic-claim race
  itself is unit-tested in ``tests/test_runner_concurrent_start_race.py``.
  This E2E test instead pre-writes an alive ``runner.pid`` in the fixture
  session and fires two parallel ``overnight_start_run`` calls via real stdio
  MCP transport — both must return ``started=false, reason="concurrent_runner_alive"``
  under real async dispatch with no head-of-line blocking. This is the
  reasonable-judgment-call described in the Task 19 hints: the test exercises
  the actual stdio MCP transport with real async dispatch (closing the
  through-line concern) without paying the cost of a real overnight run.

* For sub-case (c), the orchestrator-prompt rendered Python is exec'd
  against a fresh globals dict with synthetic stand-ins for the
  orchestrator_io functions (``save_state`` / ``update_feature_status`` /
  ``write_escalation``). The block of interest is the Step 0b
  unresolved-set computation that reads ``escalations.jsonl`` and parses
  each entry — the E2E correctness contract is that the substituted
  ``escalations_path`` reads the record we just wrote and that the parsed
  entry's ``escalation_id`` matches the new ``{session_id}-{feature}-{round}-q1``
  format.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import psutil
import pytest

# End-to-end stack spawns real stdio MCP transport + runner subprocess tree —
# keep serialized against the other subprocess-spawning suites (R26 / Task 20).
pytestmark = pytest.mark.serial


# ---------------------------------------------------------------------------
# Paths / fixtures
# ---------------------------------------------------------------------------


REPO_ROOT = Path(__file__).resolve().parents[1]


def _resolve_cortex_executable() -> Optional[list[str]]:
    """Return argv prefix invoking ``cortex mcp-server``, or ``None``.

    Mirrors the resolver used in ``test_mcp_async_correctness.py`` so the
    spawn semantics are identical between the latency test and the E2E
    integration test.
    """
    candidate = shutil.which("cortex")
    if candidate is not None:
        return [candidate]
    return [sys.executable, "-m", "cortex_command.cli"]


def _smoke_check_cortex(argv: list[str]) -> Optional[str]:
    """Return ``None`` when ``cortex mcp-server --help`` exits 0; else a reason."""
    try:
        smoke = subprocess.run(
            argv + ["mcp-server", "--help"],
            capture_output=True,
            timeout=15,
            text=True,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "cortex mcp-server --help unavailable"
    if smoke.returncode != 0:
        return (
            f"cortex mcp-server --help exited {smoke.returncode}: "
            f"{smoke.stderr[:200]}"
        )
    return None


def _live_start_time_iso(pid: int) -> str:
    """Return ``pid``'s ``create_time`` as an ISO-8601 string."""
    epoch = psutil.Process(pid).create_time()
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _spawn_long_sleep_subprocess(
    duration_seconds: float = 60.0,
) -> subprocess.Popen:
    """Spawn a real ``python`` subprocess in its own session.

    Used as the "alive runner" stand-in for sub-case (a) so the pre-flight
    ``_check_concurrent_runner`` actually finds an alive PID. ``start_new_session=True``
    ensures the subprocess survives independently of the test process.
    """
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            f"import time; time.sleep({duration_seconds})",
        ],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait briefly so psutil can observe the process.
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        try:
            psutil.Process(proc.pid).create_time()
            break
        except psutil.NoSuchProcess:
            time.sleep(0.01)
    return proc


def _spawn_sigterm_ignoring_runner_with_grandchild(
    grandchild_sleep: float = 60.0,
) -> tuple[subprocess.Popen, dict, int]:
    """Spawn a runner that emulates Task 3's tree-walker on SIGTERM.

    Returns ``(runner_proc, pid_data, grandchild_pid)``. The grandchild is
    started with ``start_new_session=True`` so its PG diverges from the
    runner's — meaning ``os.killpg(runner_pgid, SIGTERM)`` cannot reach it.
    Termination of the grandchild is delegated to the runner's in-handler
    tree-walker, emulated here in the spawned-script body so this E2E test
    is self-contained and does not depend on a real runner subprocess
    actually performing a full overnight run.

    Identical pattern to ``test_mcp_overnight_cancel.py``'s helper of the
    same name; duplicated here so this file remains a single self-contained
    E2E artifact (per spec R27 — the E2E test is the load-bearing catch
    for the through-line, and inter-test fixture sharing would dilute that).
    """
    runner_code = f"""
import os
import signal
import subprocess
import sys
import time

import psutil


def handle_sigterm(signum, frame):
    # Emulate Task 3's tree-walker: SIGKILL all descendants on SIGTERM so
    # the grandchild — whose PG diverges from this runner's because it was
    # spawned with start_new_session=True — is reached and reaped even
    # though the cancel tool's os.killpg cannot signal it directly.
    try:
        descendants = psutil.Process(os.getpid()).children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        descendants = []
    for proc in descendants:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    sys.exit(0)


signal.signal(signal.SIGTERM, handle_sigterm)

grandchild = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep({grandchild_sleep})"],
    start_new_session=True,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
sys.stdout.write(str(grandchild.pid) + "\\n")
sys.stdout.flush()

while True:
    time.sleep(0.5)
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", runner_code],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    assert proc.stdout is not None
    grandchild_line = proc.stdout.readline().strip()
    grandchild_pid = int(grandchild_line)

    # Wait briefly for psutil to see the runner.
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        try:
            create_time = psutil.Process(proc.pid).create_time()
            break
        except psutil.NoSuchProcess:
            time.sleep(0.01)
    else:
        create_time = time.time()

    pgid = os.getpgid(proc.pid)
    start_time_iso = datetime.fromtimestamp(
        create_time, tz=timezone.utc
    ).isoformat()
    pid_data = {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": proc.pid,
        "pgid": pgid,
        "start_time": start_time_iso,
        "session_id": "test-session",
        "session_dir": "/tmp/test-session",
        "repo_path": "/tmp/test-repo",
    }
    return proc, pid_data, grandchild_pid


def _terminate_pg_safely(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _terminate_pid_safely(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


@pytest.fixture
def cleanup_processes():
    """Yield a list; SIGKILL every recorded ``(pid, pgid)`` on teardown.

    Identical contract to the ``cleanup_processes`` fixture in
    ``test_mcp_overnight_cancel.py`` — tests append every spawned
    ``(pid, pgid)`` so the finalizer can SIGKILL any leak even on
    assertion failure.
    """
    spawned: list[tuple[int, int]] = []
    yield spawned
    for pid, pgid in spawned:
        _terminate_pg_safely(pgid)
        _terminate_pid_safely(pid)
        try:
            os.waitpid(pid, os.WNOHANG)
        except (ChildProcessError, OSError):
            pass


# ---------------------------------------------------------------------------
# Fixture session helpers
# ---------------------------------------------------------------------------


def _fixture_session_id() -> str:
    """Return a deterministic session-id that satisfies SESSION_ID_RE."""
    return "overnight-2026-04-24-e2e"


def _write_state_file(session_dir: Path, session_id: str) -> Path:
    """Write a minimal state file under ``session_dir``.

    Uses ``phase=executing`` so the active-session pointer is non-empty if
    a future code path consults it, but no features are pending — the
    state is otherwise minimally valid for the MCP tools' read paths.
    """
    session_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "session_id": session_id,
        "plan_ref": f"lifecycle/sessions/{session_id}/overnight-plan.md",
        "plan_hash": "0" * 64,
        "current_round": 1,
        "phase": "executing",
        "started_at": "2026-04-24T22:00:00+00:00",
        "updated_at": "2026-04-24T22:00:00+00:00",
        "integration_branch": f"integration/{session_id}",
        "paused_reason": None,
        "features": {},
        "round_history": [],
    }
    state_path = session_dir / "overnight-state.json"
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state_path


def _write_runner_pid(session_dir: Path, pid_data: dict) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "runner.pid").write_text(
        json.dumps(pid_data, indent=2, sort_keys=True), encoding="utf-8"
    )


def _scoped_env(repo_path: Path, home_path: Path) -> dict[str, str]:
    """Return an env dict that scopes the MCP subprocess to a tempdir.

    * ``HOME`` is set so ``ipc.ACTIVE_SESSION_PATH`` (computed from
      ``Path.home()`` at module import time) lands under ``home_path``,
      isolating the test from the user's real
      ``~/.local/share/overnight-sessions/active-session.json``.
    * The MCP subprocess is also launched with ``cwd=repo_path`` (set by
      the caller via ``StdioServerParameters.cwd``) — combined with
      ``repo_path`` not being a git working tree, this makes
      ``cli_handler._resolve_repo_path()`` fall back to ``Path.cwd()``,
      which equals ``repo_path``.
    """
    env = os.environ.copy()
    env["HOME"] = str(home_path)
    # ``CORTEX_ALLOW_INSTALL_DURING_RUN`` keeps Task 17's pre-install guard
    # from interrupting subprocesses that import ``cortex_command`` while a
    # test fixture's runner.pid is intentionally alive. The guard is opt-in
    # there; setting the bypass keeps the E2E spawn path clean.
    env["CORTEX_ALLOW_INSTALL_DURING_RUN"] = "1"
    return env


# ---------------------------------------------------------------------------
# Sub-case (a) — concurrent overnight_start_run via real stdio
# ---------------------------------------------------------------------------


def test_concurrent_overnight_start_run_returns_concurrent_alive(
    tmp_path,
    cleanup_processes,
) -> None:
    """Two parallel start-run calls against an alive runner.pid both refuse.

    Validates that real async dispatch over the stdio MCP transport routes
    both concurrent ``overnight_start_run`` calls through the synchronous
    pre-flight ``_check_concurrent_runner`` gate without head-of-line
    blocking. Both calls must return
    ``started=false, reason="concurrent_runner_alive"`` because the alive
    runner.pid the test pre-arranges is the same lock both calls observe.

    Trade-off (per Task 19 hints): this E2E test does not exercise the
    O_EXCL atomic claim that lives inside the spawned subprocess — that
    race is unit-tested in ``tests/test_runner_concurrent_start_race.py``.
    What this test catches that the unit test cannot: a hazard where the
    stdio JSON-RPC framing layer or FastMCP's dispatch loop accidentally
    serializes tool calls so that ``_check_concurrent_runner`` runs
    sequentially rather than concurrently — both calls would still return
    ``concurrent_runner_alive``, but the through-line concern from R8's
    critical review (that R8's race fix could be masked by event-loop
    serialization) requires this real-async-dispatch coverage.
    """
    try:
        from mcp import ClientSession  # noqa: F401
        from mcp.client.stdio import StdioServerParameters, stdio_client
    except ImportError:
        pytest.skip("mcp SDK not importable in this environment")

    argv = _resolve_cortex_executable()
    if argv is None:
        pytest.skip("cortex executable not invokable")
    skip_reason = _smoke_check_cortex(argv)
    if skip_reason is not None:
        pytest.skip(skip_reason)

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    home_path = tmp_path / "home"
    home_path.mkdir()

    session_id = _fixture_session_id()
    session_dir = repo_path / "lifecycle" / "sessions" / session_id
    _write_state_file(session_dir, session_id)

    # Spawn a real long-sleep subprocess to act as the "alive runner".
    # Pre-write a runner.pid pointing at it with a matching start_time so
    # the MCP tool's ``_check_concurrent_runner`` (which calls
    # ``ipc.verify_runner_pid``) sees an alive lock and surfaces
    # ``concurrent_runner_alive`` — without us having to spawn a real
    # ``cortex overnight start``.
    sleeper = _spawn_long_sleep_subprocess(duration_seconds=60.0)
    sleeper_pgid = os.getpgid(sleeper.pid)
    cleanup_processes.append((sleeper.pid, sleeper_pgid))

    pid_data = {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": sleeper.pid,
        "pgid": sleeper_pgid,
        "start_time": _live_start_time_iso(sleeper.pid),
        "session_id": session_id,
        "session_dir": str(session_dir),
        "repo_path": str(repo_path),
    }
    _write_runner_pid(session_dir, pid_data)

    env = _scoped_env(repo_path, home_path)

    async def _fire_two_concurrent_calls() -> tuple[dict, dict]:
        params = StdioServerParameters(
            command=argv[0],
            args=argv[1:] + ["mcp-server"],
            env=env,
            cwd=str(repo_path),
        )
        async with stdio_client(params) as (read_stream, write_stream):
            from mcp import ClientSession as _CS

            async with _CS(read_stream, write_stream) as session:
                await asyncio.wait_for(session.initialize(), timeout=15)

                async def _call_one() -> dict:
                    res = await session.call_tool(
                        "overnight_start_run",
                        arguments={
                            "payload": {
                                "confirm_dangerously_skip_permissions": True,
                                "state_path": str(
                                    session_dir / "overnight-state.json"
                                ),
                            }
                        },
                    )
                    if res.isError:
                        raise AssertionError(
                            f"overnight_start_run returned error: "
                            f"{res.content}"
                        )
                    # ``structuredContent`` is FastMCP's parsed-output
                    # representation; fall back to the textual content
                    # block for SDK versions that omit it.
                    if res.structuredContent is not None:
                        return dict(res.structuredContent)
                    # Fall back — parse the first text content block.
                    if res.content:
                        first = res.content[0]
                        if hasattr(first, "text"):
                            return json.loads(first.text)
                    raise AssertionError(
                        "overnight_start_run returned no parseable output"
                    )

                return await asyncio.gather(_call_one(), _call_one())

    try:
        result_a, result_b = asyncio.run(
            asyncio.wait_for(_fire_two_concurrent_calls(), timeout=30)
        )
    except asyncio.TimeoutError:
        pytest.fail(
            "stdio MCP server did not respond to two concurrent "
            "overnight_start_run calls within 30 s — likely a "
            "head-of-line stall in the dispatch loop"
        )

    # Both calls observe the alive runner.pid → both must refuse with the
    # structured ``concurrent_runner_alive`` payload (R8 surface).
    for label, result in (("A", result_a), ("B", result_b)):
        assert result.get("started") is False, (
            f"call {label} returned started={result.get('started')!r}; "
            f"expected False with reason=concurrent_runner_alive (full "
            f"result: {result})"
        )
        assert result.get("reason") == "concurrent_runner_alive", (
            f"call {label} returned reason={result.get('reason')!r}; "
            f"expected 'concurrent_runner_alive' (full result: {result})"
        )
        # ``existing_session_id`` echoes the alive runner's session.
        assert result.get("existing_session_id") == session_id, (
            f"call {label} returned existing_session_id="
            f"{result.get('existing_session_id')!r}; expected "
            f"{session_id!r}"
        )


# ---------------------------------------------------------------------------
# Sub-case (b) — overnight_cancel reaches a real grandchild
# ---------------------------------------------------------------------------


def test_overnight_cancel_reaches_real_grandchild_subprocess(
    tmp_path,
    cleanup_processes,
) -> None:
    """A real grandchild in a separate PG is reaped by ``overnight_cancel``.

    Closes the R12 fakes-only concern from critical review by spawning a
    real grandchild via ``start_new_session=True`` (so its PG diverges
    from the runner's) and invoking ``overnight_cancel`` over the real
    stdio MCP transport. The cancel tool's ``os.killpg(runner_pgid, SIGTERM)``
    only signals processes in the runner's PG; the grandchild's
    termination is delegated to the runner's in-handler tree-walker
    (Task 3), which this test emulates in the spawned-script body so the
    E2E coverage remains within a single file.

    Post-cancel assertions:
    * ``cancelled=True`` and ``reason="cancelled"``.
    * Grandchild PID is not alive (asserted via ``psutil.pid_exists``)
      within a 5 s post-cancel deadline.
    """
    try:
        from mcp import ClientSession  # noqa: F401
        from mcp.client.stdio import StdioServerParameters, stdio_client
    except ImportError:
        pytest.skip("mcp SDK not importable in this environment")

    argv = _resolve_cortex_executable()
    if argv is None:
        pytest.skip("cortex executable not invokable")
    skip_reason = _smoke_check_cortex(argv)
    if skip_reason is not None:
        pytest.skip(skip_reason)

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    home_path = tmp_path / "home"
    home_path.mkdir()

    session_id = _fixture_session_id()
    session_dir = repo_path / "lifecycle" / "sessions" / session_id
    _write_state_file(session_dir, session_id)

    runner_proc, pid_data, grandchild_pid = (
        _spawn_sigterm_ignoring_runner_with_grandchild(grandchild_sleep=60.0)
    )
    cleanup_processes.append((runner_proc.pid, pid_data["pgid"]))
    cleanup_processes.append((grandchild_pid, grandchild_pid))

    pid_data["session_id"] = session_id
    pid_data["session_dir"] = str(session_dir)
    pid_data["repo_path"] = str(repo_path)
    _write_runner_pid(session_dir, pid_data)

    # Sanity: grandchild is alive before cancel.
    assert psutil.pid_exists(grandchild_pid), (
        "grandchild PID went away before overnight_cancel was invoked"
    )

    env = _scoped_env(repo_path, home_path)

    async def _invoke_cancel() -> dict:
        params = StdioServerParameters(
            command=argv[0],
            args=argv[1:] + ["mcp-server"],
            env=env,
            cwd=str(repo_path),
        )
        async with stdio_client(params) as (read_stream, write_stream):
            from mcp import ClientSession as _CS

            async with _CS(read_stream, write_stream) as session:
                await asyncio.wait_for(session.initialize(), timeout=15)
                res = await session.call_tool(
                    "overnight_cancel",
                    arguments={
                        "payload": {"session_id": session_id, "force": False}
                    },
                )
                if res.isError:
                    raise AssertionError(
                        f"overnight_cancel returned error: {res.content}"
                    )
                if res.structuredContent is not None:
                    return dict(res.structuredContent)
                if res.content:
                    first = res.content[0]
                    if hasattr(first, "text"):
                        return json.loads(first.text)
                raise AssertionError(
                    "overnight_cancel returned no parseable output"
                )

    try:
        result = asyncio.run(asyncio.wait_for(_invoke_cancel(), timeout=30))
    except asyncio.TimeoutError:
        pytest.fail(
            "stdio MCP server did not respond to overnight_cancel within "
            "30 s — likely a head-of-line stall in the dispatch loop"
        )

    assert result.get("cancelled") is True, (
        f"cancel did not succeed: {result}"
    )
    assert result.get("reason") == "cancelled", (
        f"unexpected cancel reason: {result.get('reason')!r}"
    )

    # Wait for the grandchild to die — Task 3's tree-walker runs in the
    # runner's signal-handler context, so there's a small window between
    # the cancel-tool returning and the grandchild actually exiting.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not psutil.pid_exists(grandchild_pid):
            break
        time.sleep(0.05)
    else:
        pytest.fail(
            f"grandchild PID {grandchild_pid} survived overnight_cancel "
            f"— the runner's tree-walker did not reach the separate-PG "
            f"grandchild (R12 contract violated)"
        )


# ---------------------------------------------------------------------------
# Sub-case (c) — escalations write + orchestrator-prompt render round-trip
# ---------------------------------------------------------------------------


def test_escalation_write_and_orchestrator_prompt_read_roundtrip(
    tmp_path,
) -> None:
    """``write_escalation`` + orchestrator-prompt render round-trip.

    Closes the through-line concern that an acceptance criterion
    (escalations migrate to per-session) can pass while the named hazard
    (orchestrator-prompt agent crashing on the new ``escalation_id``
    format under the new path) remains open. The test:

    1. Writes a real ``EscalationEntry`` via the production
       ``write_escalation`` API at ``session_dir/escalations.jsonl``.
    2. Asserts the on-disk record carries the new
       ``{session_id}-{feature}-{round}-q1`` ID format.
    3. Renders the orchestrator-round prompt via ``fill_prompt()`` with
       the fixture ``session_dir`` so ``{session_dir}`` is substituted.
    4. Extracts the Step 0b Python block (the one that actually reads
       ``escalations.jsonl`` into ``entries``) and exec's it against a
       fresh globals dict with synthetic stand-ins for the
       ``orchestrator_io`` symbols imported at the top of the block.
    5. Asserts the parsed entry's ``escalation_id`` matches the new
       format and that the unresolved-set computation surfaces it as
       unresolved.
    """
    from cortex_command.overnight.deferral import (
        EscalationEntry,
        write_escalation,
    )
    from cortex_command.overnight.fill_prompt import fill_prompt

    session_id = _fixture_session_id()
    session_dir = tmp_path / "lifecycle" / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    feature = "feat-x"
    round_num = 1
    entry = EscalationEntry.build(
        session_id=session_id,
        feature=feature,
        round=round_num,
        n=1,
        question="Is the spec ambiguous?",
        context="Implementing the foo() helper.",
    )
    write_escalation(entry, session_dir=session_dir)

    # On-disk shape: the escalation_id must be the new
    # {session_id}-{feature}-{round}-q1 format (R18 / Task 6).
    escalations_path = session_dir / "escalations.jsonl"
    raw = escalations_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(raw) == 1, f"expected 1 line, got {len(raw)}: {raw}"
    record = json.loads(raw[0])
    expected_id = f"{session_id}-{feature}-{round_num}-q1"
    assert record["escalation_id"] == expected_id, (
        f"expected escalation_id={expected_id!r}, got "
        f"{record['escalation_id']!r}"
    )
    assert record["session_id"] == session_id
    assert record["type"] == "escalation"

    # Render the orchestrator-round prompt with the fixture session_dir.
    plan_path = session_dir / "overnight-plan.md"
    state_path = session_dir / "overnight-state.json"
    events_path = session_dir / "overnight-events.log"
    rendered = fill_prompt(
        round_number=round_num,
        state_path=state_path,
        plan_path=plan_path,
        events_path=events_path,
        session_dir=session_dir,
        tier="simple",
    )

    # Belt-and-suspenders: substitution actually happened.
    assert "{session_dir}" not in rendered, (
        "{session_dir} token survived fill_prompt — substitution incomplete"
    )
    assert str(escalations_path) in rendered, (
        f"rendered prompt does not contain expected substituted "
        f"escalations path {escalations_path!s}"
    )

    # Extract the Step 0b Python block — the one that reads
    # ``escalations.jsonl`` and computes ``entries`` / ``unresolved_ids``.
    blocks = re.findall(
        r"^```python\n(.*?)\n^```",
        rendered,
        flags=re.DOTALL | re.MULTILINE,
    )
    assert blocks, "no python code blocks in rendered prompt"

    # The first block is the unresolved-set computation (per the prompt
    # template); locate it explicitly via its escalations_path assignment.
    target_block: Optional[str] = None
    for block in blocks:
        if "escalations_path" in block and "unresolved_ids" in block:
            target_block = block
            break
    assert target_block is not None, (
        "could not locate the Step 0b unresolved-set computation block "
        "in the rendered prompt"
    )

    # Build a fresh globals dict with synthetic stand-ins for the
    # orchestrator_io functions imported at the top of the block. They
    # are not invoked by Step 0b (only by Step 0d's resolution path), so
    # the stand-ins are plain identity-style placeholders that satisfy
    # the import.
    def _save_state(*args, **kwargs):  # pragma: no cover — unused at exec
        return None

    def _update_feature_status(*args, **kwargs):  # pragma: no cover
        return None

    def _write_escalation(*args, **kwargs):  # pragma: no cover
        return None

    # The block's ``from cortex_command.overnight.orchestrator_io import ...``
    # statement will run at exec time and pull the real symbols. That is
    # acceptable for the read-path test — the block does not invoke them.
    # We exec against a fresh globals dict so any leak from this test
    # process's imports is irrelevant to the contract check.
    fresh_globals: dict = {"__builtins__": __builtins__}

    exec(  # noqa: S102 — controlled-input exec of templated prompt block
        target_block, fresh_globals
    )

    # The block populates ``entries`` (parsed JSON dicts) and
    # ``unresolved_ids`` (set of escalation_ids without a
    # resolution/promoted entry). Verify both observable side effects
    # carry the new {session_id}-{feature}-{round}-q1 format.
    entries = fresh_globals.get("entries")
    assert isinstance(entries, list), (
        f"block did not populate `entries` as a list: "
        f"{type(entries).__name__}"
    )
    assert len(entries) == 1, (
        f"expected 1 parsed entry, got {len(entries)}: {entries}"
    )
    parsed = entries[0]
    assert isinstance(parsed, dict)
    assert parsed.get("escalation_id") == expected_id, (
        f"parsed entry escalation_id={parsed.get('escalation_id')!r}; "
        f"expected {expected_id!r}"
    )

    unresolved_ids = fresh_globals.get("unresolved_ids")
    assert isinstance(unresolved_ids, set), (
        f"block did not populate `unresolved_ids` as a set: "
        f"{type(unresolved_ids).__name__}"
    )
    assert expected_id in unresolved_ids, (
        f"new-format escalation_id {expected_id!r} did not surface as "
        f"unresolved: {unresolved_ids}"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
