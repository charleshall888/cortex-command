"""Parity tests for the in-flight install guard's vendored core (R25).

The ``check_in_flight_install_core`` function in
``cortex_command/install_guard.py`` is the source-of-truth implementation
of the active-session liveness check used by the pre-install guard. The
function is vendored byte-identically into
``plugins/cortex-overnight/install_guard.py`` so the plugin's PEP 723
venv (stdlib + mcp + pydantic, no psutil) can honor R28 by supplying its
own pid-verifier callable. ``.githooks/pre-commit`` + ``just
sync-install-guard --check`` enforce source identity at commit time;
this test enforces the same identity at run time, plus decision parity
across a fixture matrix.

Test layout (per spec R25 + critical-review carve-out finding):

* **Source-identity** (1 case): ``inspect.getsource`` of both
  ``check_in_flight_install_core`` definitions returns byte-identical
  strings.
* **Core-level parity** (8 parameterized cases): the same
  ``active-session.json`` fixture and the same pid-verifier callable
  are passed to both implementations; both must return identical results
  (``None`` or the same reason-string). Cases mirror R25's enumerated
  matrix:
    (i) no active-session.json,
    (ii) live pid,
    (iii) dead pid,
    (iv) recycled pid (pid alive but start_time mismatch),
    (v) ``CORTEX_ALLOW_INSTALL_DURING_RUN=1`` + live,
    (vi) ``CORTEX_RUNNER_CHILD=1`` + live,
    (vii) ``PYTEST_CURRENT_TEST`` set + live,
    (viii) ``"pytest" in sys.modules`` + live.
  Cases (v)–(viii) set the env var/module-presence signal but invoke
  the core directly — the core is stdlib-only and does not read env
  vars; the parity assertion is that BOTH cores agree on the decision
  given the same inputs. Wrapper-level carve-out evaluation is exercised
  separately below.
* **Wrapper-level parity** (4 parameterized cases): the CLI-side
  wrapper ``check_in_flight_install`` is exercised with each of the
  env-var permutations from the carve-out matrix; the plugin side's
  "equivalent" is invoking the core directly (the plugin's
  ``install_guard.py`` is the bare vendored core — no wrapper carve-outs
  live there). Parity here means: both flows agree on whether the
  install is blocked. The CLI wrapper's only env-var carve-out is
  ``CORTEX_ALLOW_INSTALL_DURING_RUN``; the other three env signals do
  NOT short-circuit the wrapper, which is itself the parity result this
  test pins down — if a future change adds a fictional carve-out, the
  parity assertion will fail and force the spec narrative and code to
  reconcile.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Optional

import psutil
import pytest

from cortex_command import install_guard as cli_guard


REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_GUARD_PATH = (
    REPO_ROOT / "plugins" / "cortex-overnight" / "install_guard.py"
)


def _load_plugin_guard_module():
    """Load the vendored plugin-side install_guard.py as a standalone module.

    Importing via path-based ``importlib`` (rather than via
    ``sys.path.insert``) keeps the test hermetic — the plugin module is
    bound to a unique module name so it cannot collide with the
    canonical ``cortex_command.install_guard`` already imported above.
    """
    spec = importlib.util.spec_from_file_location(
        "plugin_install_guard_under_test",
        PLUGIN_GUARD_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Could not load plugin install_guard from {PLUGIN_GUARD_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


plugin_guard = _load_plugin_guard_module()


# ---------------------------------------------------------------------------
# (a) Source-identity test
# ---------------------------------------------------------------------------

def test_check_in_flight_install_core_source_identity() -> None:
    """The two ``check_in_flight_install_core`` sources are byte-identical.

    ``.githooks/pre-commit`` enforces this at commit time via
    ``just sync-install-guard --check``; this test enforces the same
    identity at runtime so a developer running tests against an
    out-of-sync vendored sibling sees the failure immediately.
    """
    canonical_src = inspect.getsource(cli_guard.check_in_flight_install_core)
    vendored_src = inspect.getsource(plugin_guard.check_in_flight_install_core)
    assert canonical_src == vendored_src, (
        "check_in_flight_install_core sources have drifted between "
        f"{cli_guard.__file__} and {PLUGIN_GUARD_PATH}. Run "
        "`just sync-install-guard` to regenerate the vendored sibling."
    )


# ---------------------------------------------------------------------------
# Fixtures shared by core- and wrapper-level parity tests
# ---------------------------------------------------------------------------

CARVE_OUT_ENV_VARS = (
    "CORTEX_ALLOW_INSTALL_DURING_RUN",
    "CORTEX_RUNNER_CHILD",
    "PYTEST_CURRENT_TEST",
)


@pytest.fixture
def isolated_active_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Redirect ``_ACTIVE_SESSION_PATH`` on both modules into ``tmp_path``.

    The CLI wrapper consults ``cli_guard._ACTIVE_SESSION_PATH``. The
    plugin-side module does not own a wrapper, so it never reads a
    module-level path constant directly — its callers pass the path
    in. For symmetry and to keep both core invocations using the same
    tmp-path filesystem, we publish the path as a return value from
    this fixture.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    active_path = (
        fake_home
        / ".local"
        / "share"
        / "overnight-sessions"
        / "active-session.json"
    )
    monkeypatch.setattr(cli_guard, "_ACTIVE_SESSION_PATH", active_path)
    yield active_path


@pytest.fixture(autouse=True)
def _clear_carve_out_env(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Strip carve-out env vars before each test for a clean slate.

    ``PYTEST_CURRENT_TEST`` is set by pytest itself per-test; restoring
    it after the test exits is not necessary because pytest re-stamps
    it on each test entry. We delete here so any parameterized test
    that expects the var unset starts from a known state — the test
    that needs it set explicitly sets it via ``monkeypatch.setenv``.
    """
    for var in CARVE_OUT_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    yield


def _live_start_time_iso() -> str:
    """ISO-8601 (UTC) ``create_time`` for the current test process."""
    epoch = psutil.Process(os.getpid()).create_time()
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _write_active_pointer(
    active_path: Path,
    session_id: str,
    session_dir: Path,
    phase: str,
    pid: int,
    start_time: str,
) -> None:
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "magic": "cortex-runner-v1",
                "pid": pid,
                "pgid": pid,
                "start_time": start_time,
                "session_id": session_id,
                "session_dir": str(session_dir),
                "repo_path": str(session_dir),
                "phase": phase,
            }
        ),
        encoding="utf-8",
    )


def _write_runner_pid(
    session_dir: Path,
    session_id: str,
    pid: int,
    start_time: str,
) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "runner.pid").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "magic": "cortex-runner-v1",
                "pid": pid,
                "pgid": pid,
                "start_time": start_time,
                "session_id": session_id,
                "session_dir": str(session_dir),
                "repo_path": str(session_dir),
            }
        ),
        encoding="utf-8",
    )


def _setup_live_inflight(
    active_path: Path,
    tmp_path: Path,
    session_id: str = "session-parity-live-20260513",
) -> Path:
    """Write a pointer + runner.pid that point at THIS pytest process.

    The CLI pid-verifier (psutil-backed) and the shared in-tree
    pid-verifier produced for the plugin side will both verify TRUE
    against this fixture because the pid is alive and the
    ``start_time`` matches.
    """
    session_dir = tmp_path / "sessions" / session_id
    start_time = _live_start_time_iso()
    _write_active_pointer(
        active_path,
        session_id=session_id,
        session_dir=session_dir,
        phase="executing",
        pid=os.getpid(),
        start_time=start_time,
    )
    _write_runner_pid(
        session_dir,
        session_id=session_id,
        pid=os.getpid(),
        start_time=start_time,
    )
    return session_dir


def _shared_pid_verifier(pid_data: dict) -> bool:
    """psutil-backed pid verifier reused by both core invocations.

    The CLI wrapper supplies a psutil-backed verifier internally; for
    core-level parity the test passes the SAME verifier callable to
    both sides so any decision difference must come from the core
    logic itself, not from a verifier mismatch. This isolates the
    parity assertion to the byte-vendored core surface.

    Mirrors ``cortex_command.overnight.ipc.verify_runner_pid`` to keep
    the test independent of test-time changes there; the canonical
    ipc.verify_runner_pid is already exercised by
    ``tests/test_install_inflight_guard.py``.
    """
    if not isinstance(pid_data, dict):
        return False
    if pid_data.get("magic") != "cortex-runner-v1":
        return False
    pid = pid_data.get("pid")
    start_time_str = pid_data.get("start_time")
    if not isinstance(pid, int) or not isinstance(start_time_str, str):
        return False
    try:
        recorded_epoch = datetime.fromisoformat(
            start_time_str.replace("Z", "+00:00")
        ).timestamp()
    except (ValueError, TypeError):
        return False
    try:
        actual_epoch = psutil.Process(pid).create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    except Exception:
        return False
    return abs(actual_epoch - recorded_epoch) <= 2.0


# ---------------------------------------------------------------------------
# (b) Core-level decision parity (8 cases)
# ---------------------------------------------------------------------------

def _run_both_cores(
    active_path: Path,
    pid_verifier: Callable[[dict], bool],
) -> tuple[Optional[str], Optional[str]]:
    """Invoke both vendored cores against identical inputs.

    Returns (cli_result, plugin_result). Parity tests assert these are
    equal — be it both ``None`` or both the same reason-string.
    """
    cli_result = cli_guard.check_in_flight_install_core(
        active_path, pid_verifier=pid_verifier
    )
    plugin_result = plugin_guard.check_in_flight_install_core(
        active_path, pid_verifier=pid_verifier
    )
    return cli_result, plugin_result


def _scenario_no_active_session(
    active_path: Path, tmp_path: Path
) -> None:
    """(i) No active-session.json — both implementations short-circuit."""
    # Make sure the path does not exist.
    if active_path.exists():
        active_path.unlink()


def _scenario_live_pid(active_path: Path, tmp_path: Path) -> None:
    """(ii) Pointer + runner.pid both point at this live test pid."""
    _setup_live_inflight(active_path, tmp_path)


def _scenario_dead_pid(active_path: Path, tmp_path: Path) -> None:
    """(iii) Pointer says executing; runner.pid points at PID 0 (dead)."""
    session_id = "session-parity-dead-20260513"
    session_dir = tmp_path / "sessions" / session_id
    _write_active_pointer(
        active_path,
        session_id=session_id,
        session_dir=session_dir,
        phase="executing",
        pid=0,
        start_time="1970-01-01T00:00:00+00:00",
    )
    _write_runner_pid(
        session_dir,
        session_id=session_id,
        pid=0,
        start_time="1970-01-01T00:00:00+00:00",
    )


def _scenario_recycled_pid(active_path: Path, tmp_path: Path) -> None:
    """(iv) Pointer/pid say a real pid but with a wrong start_time.

    The pid verifier's start_time tolerance is ±2s. We record an
    epoch that is far in the past, so even though ``os.kill(pid, 0)``
    would succeed, the verifier rejects on start_time mismatch.
    """
    session_id = "session-parity-recycled-20260513"
    session_dir = tmp_path / "sessions" / session_id
    # Bogus start_time far enough in the past to bust the ±2s tolerance.
    bogus_start = "2000-01-01T00:00:00+00:00"
    _write_active_pointer(
        active_path,
        session_id=session_id,
        session_dir=session_dir,
        phase="executing",
        pid=os.getpid(),
        start_time=bogus_start,
    )
    _write_runner_pid(
        session_dir,
        session_id=session_id,
        pid=os.getpid(),
        start_time=bogus_start,
    )


def _scenario_allow_env_live(active_path: Path, tmp_path: Path) -> None:
    """(v) ``CORTEX_ALLOW_INSTALL_DURING_RUN=1`` + live pid.

    The env var is set on the test process by the caller; the core
    itself does NOT read env vars (it is stdlib-only and takes
    callables, not env). Parity is therefore: both cores see the
    live-pid case and both block. Wrapper-level coverage below
    asserts that the CLI wrapper's env-var carve-out fires.
    """
    _setup_live_inflight(active_path, tmp_path)


def _scenario_runner_child_env_live(
    active_path: Path, tmp_path: Path
) -> None:
    """(vi) ``CORTEX_RUNNER_CHILD=1`` + live — env-only, core unchanged."""
    _setup_live_inflight(active_path, tmp_path)


def _scenario_pytest_current_test_env_live(
    active_path: Path, tmp_path: Path
) -> None:
    """(vii) ``PYTEST_CURRENT_TEST`` set + live — env-only, core unchanged."""
    _setup_live_inflight(active_path, tmp_path)


def _scenario_pytest_in_sys_modules_live(
    active_path: Path, tmp_path: Path
) -> None:
    """(viii) ``"pytest" in sys.modules`` + live.

    ``pytest`` is always in ``sys.modules`` while this test runs, so
    setup is identical to the live-pid case. Parity is what we test:
    both cores see the same inputs and decide the same thing.
    """
    assert "pytest" in sys.modules  # sanity — pytest is loaded.
    _setup_live_inflight(active_path, tmp_path)


CORE_PARITY_SCENARIOS = [
    (
        "no_active_session",
        _scenario_no_active_session,
        None,
    ),
    (
        "live_pid",
        _scenario_live_pid,
        {"CORTEX_ALLOW_INSTALL_DURING_RUN": None},
    ),
    (
        "dead_pid",
        _scenario_dead_pid,
        None,
    ),
    (
        "recycled_pid",
        _scenario_recycled_pid,
        None,
    ),
    (
        "allow_env_live",
        _scenario_allow_env_live,
        {"CORTEX_ALLOW_INSTALL_DURING_RUN": "1"},
    ),
    (
        "runner_child_env_live",
        _scenario_runner_child_env_live,
        {"CORTEX_RUNNER_CHILD": "1"},
    ),
    (
        "pytest_current_test_env_live",
        _scenario_pytest_current_test_env_live,
        {"PYTEST_CURRENT_TEST": "tests/test_install_guard_parity.py::dummy"},
    ),
    (
        "pytest_in_sys_modules_live",
        _scenario_pytest_in_sys_modules_live,
        None,
    ),
]


@pytest.mark.parametrize(
    "scenario_name,scenario_fn,env_overrides",
    CORE_PARITY_SCENARIOS,
    ids=[c[0] for c in CORE_PARITY_SCENARIOS],
)
def test_core_decision_parity(
    scenario_name: str,
    scenario_fn: Callable[[Path, Path], None],
    env_overrides: Optional[dict],
    isolated_active_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Both vendored cores must produce identical decisions per scenario.

    Source-identity (the test above) is necessary but not sufficient:
    if a future refactor accidentally diverges the runtime behavior
    via, e.g., import-time module state, the source-identity test
    could still pass while this decision-parity test catches the
    drift.
    """
    if env_overrides:
        for key, value in env_overrides.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)

    scenario_fn(isolated_active_path, tmp_path)
    cli_result, plugin_result = _run_both_cores(
        isolated_active_path, _shared_pid_verifier
    )

    # Drain capsys so any stderr self-heal warnings emitted by the core
    # do not leak between parameterized invocations.
    capsys.readouterr()

    assert cli_result == plugin_result, (
        f"Core parity mismatch in scenario {scenario_name!r}: "
        f"CLI returned {cli_result!r}, plugin returned {plugin_result!r}."
    )


# ---------------------------------------------------------------------------
# (c) Wrapper-level parity across env-var carve-outs (≥4 cases)
# ---------------------------------------------------------------------------

WRAPPER_PARITY_SCENARIOS = [
    # (id, env-overrides, expected-wrapper-blocks).
    #
    # ``CORTEX_ALLOW_INSTALL_DURING_RUN=1`` is the documented bypass:
    # the wrapper returns without invoking the core. Both sides agree
    # — install proceeds.
    (
        "allow_env_bypasses",
        {"CORTEX_ALLOW_INSTALL_DURING_RUN": "1"},
        False,
    ),
    # ``CORTEX_RUNNER_CHILD=1`` is NOT a wrapper carve-out (per the
    # current CLI wrapper code). The wrapper blocks on a live runner
    # regardless. Plugin side has no wrapper, so its decision is the
    # core's decision — also blocked. Parity holds: both block.
    (
        "runner_child_does_not_bypass",
        {"CORTEX_RUNNER_CHILD": "1"},
        True,
    ),
    # ``PYTEST_CURRENT_TEST`` is NOT a wrapper carve-out. Same
    # reasoning: both sides block.
    (
        "pytest_current_test_does_not_bypass",
        {"PYTEST_CURRENT_TEST": "tests/test_install_guard_parity.py::dummy"},
        True,
    ),
    # No carve-out env vars set: the live-runner pointer must cause
    # the wrapper to raise. Pinning this case in the wrapper-level
    # matrix anchors the "default blocks" behavior alongside the
    # carve-out permutations so a future regression cannot silently
    # disable the guard.
    (
        "no_carve_out_blocks",
        {},
        True,
    ),
]


@pytest.mark.parametrize(
    "scenario_id,env_overrides,expected_blocks",
    WRAPPER_PARITY_SCENARIOS,
    ids=[s[0] for s in WRAPPER_PARITY_SCENARIOS],
)
def test_wrapper_decision_parity(
    scenario_id: str,
    env_overrides: dict,
    expected_blocks: bool,
    isolated_active_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI wrapper and the plugin-side core agree on each carve-out.

    Plugin-side "wrapper" is the core invocation: the plugin's
    ``install_guard.py`` is the bare vendored core (no wrapper-level
    carve-outs). This test asserts that the CLI wrapper's carve-out
    evaluation order produces a decision that matches what the plugin
    side does — i.e., env vars that the CLI wrapper bypasses on must
    also unblock the plugin side (vacuously, since the plugin side
    sees only the core's view).

    Concretely: for ``CORTEX_ALLOW_INSTALL_DURING_RUN=1`` the CLI
    wrapper short-circuits before invoking the core, so the plugin's
    core call must also resolve to "not blocked" — which it does iff
    the active-session pointer is absent OR the runner is dead.
    Because the plugin core sees a live pointer + live pid in these
    fixtures, parity in the bypass case requires the plugin side to
    have its OWN bypass path. The plugin-side install path is not yet
    wired (T12 in the spec) so the plugin's effective answer is the
    core's raw answer; the only env-var carve-out that the CLI wrapper
    honors and the plugin side can match by virtue of identical core
    behavior is the "no carve-out / blocked" case. This test pins
    that asymmetry down so any future plugin-side wrapper added in
    T12 must explicitly mirror the CLI wrapper's carve-outs OR this
    parity test will fail and force the reconciliation.
    """
    # Set up a live in-flight pointer/runner.pid so the core would
    # normally block.
    _setup_live_inflight(isolated_active_path, tmp_path)

    # Apply env overrides for this scenario.
    for key, value in env_overrides.items():
        monkeypatch.setenv(key, value)

    # Wrapper-level: invoke the CLI wrapper. argv is set to a
    # non-cancel-force invocation so the cancel-bypass does not fire.
    monkeypatch.setattr(sys, "argv", ["cortex", "upgrade"])

    cli_raised = False
    try:
        cli_guard.check_in_flight_install()
    except SystemExit:
        cli_raised = True

    # Plugin-side "equivalent": invoke the vendored core directly with
    # the same active-session path and a psutil-backed verifier. The
    # plugin's PEP 723 venv supplies its own verifier in production;
    # for parity we use the same callable on both sides so the
    # comparison isolates the wrapper carve-out behavior.
    plugin_core_reason = plugin_guard.check_in_flight_install_core(
        isolated_active_path, pid_verifier=_shared_pid_verifier
    )
    plugin_blocks = plugin_core_reason is not None

    # Assert the expected wrapper-level decision.
    assert cli_raised is expected_blocks, (
        f"Wrapper decision mismatch in scenario {scenario_id!r}: "
        f"expected blocks={expected_blocks}, cli_raised={cli_raised}."
    )

    # Assert wrapper/core parity in the cases where the CLI wrapper
    # does not bypass: there, both sides must agree (both block).
    # In the explicit-bypass case (``CORTEX_ALLOW_INSTALL_DURING_RUN=1``)
    # the CLI wrapper deliberately diverges from the bare-core view —
    # the plugin has no wrapper-level carve-out today, so this case
    # documents the asymmetry rather than asserting parity. Once T12
    # adds a plugin-side wrapper, this branch can be tightened.
    if env_overrides.get("CORTEX_ALLOW_INSTALL_DURING_RUN") == "1":
        # Documented asymmetry: CLI wrapper bypasses, plugin core
        # still blocks (the plugin has no wrapper yet). Parity here
        # is at the documented-behavior level.
        assert plugin_blocks is True, (
            "Plugin core unexpectedly returned None under live in-flight"
            " setup — fixture is wrong."
        )
    else:
        assert cli_raised is plugin_blocks, (
            f"Wrapper/core parity mismatch in scenario {scenario_id!r}: "
            f"cli_raised={cli_raised}, plugin_blocks={plugin_blocks}."
        )
