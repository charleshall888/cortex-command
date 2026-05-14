"""R23 — real-install integration test with per-branch assertion contracts.

Six explicit per-branch assertions for the R4 ``_ensure_cortex_installed``
auto-update flow under non-editable wheel install (T11 + T12). Each test
function exercises exactly one branch of the version-comparison + R13
schema-floor surface and asserts the expected stage/NDJSON/stderr
output:

    (a) ``test_baseline_install_reports_package_version`` — build wheel
        at synthetic v0.1.0 via ``HATCH_BUILD_HOOK_VCS_FALLBACK_VERSION``
        env-var, install via ``uv tool install``, assert
        ``cortex --print-root --format json`` reports
        ``version="0.1.0"`` AND ``schema_version="2.0"``.
    (b) ``test_synthetic_v_0_2_0_wheel_builds`` — build a v0.2.0 wheel
        via the same env-var override. Asserts hatch-vcs auto-versioning
        accepts arbitrary tags.
    (c) ``test_version_mismatch_fires_reinstall`` — install v0.1.0,
        rewrite the loaded plugin module's ``CLI_PIN = ("v0.2.0", "2.0")``,
        invoke ``_ensure_cortex_installed()``, assert the reinstall fires
        with stage exactly ``version_mismatch_reinstall`` (NOT
        ``version_mismatch_reinstall_parse_failure``), and the post-install
        ``cortex --print-root`` reports ``version="0.2.0"``.
    (d) ``test_matching_version_passes_through`` — install v0.1.0, set
        ``CLI_PIN`` to match, invoke ``_ensure_cortex_installed()``,
        assert no ``version_mismatch_*`` stage fired AND no reinstall
        was attempted.
    (e) ``test_active_session_blocks_reinstall`` — write an
        ``active-session.json`` pointer + ``runner.pid`` payload (with
        the runner magic constant, schema_version=1, and a live pid
        owned by the test process), set ``CLI_PIN`` to a mismatched
        version, invoke ``_ensure_cortex_installed()``, assert the
        reinstall does NOT fire AND an NDJSON record with stage exactly
        ``version_mismatch_blocked_by_inflight_session`` lands under
        the test-controlled XDG_STATE_HOME.
    (f) ``test_r13_schema_floor_emits_remediation_stderr`` — source-edit
        ``cortex_command/overnight/cli_handler.py:_JSON_SCHEMA_VERSION``
        to ``"1.0"`` (the R13 schema floor lives in a Python module
        constant, NOT a hatch-vcs-derivable value), ``uv build --wheel``,
        install, invoke ``_schema_floor_violated()`` against the
        installed CLI's print-root payload, assert stderr contains both
        literal substrings ``"Schema-floor violation: installed CLI
        schema_version="`` and ``"uv tool install --reinstall git+"``.

All six tests are marked ``@pytest.mark.slow`` (opt-in via ``--run-slow``)
and ``@pytest.mark.serial`` (must not run in parallel — each test spawns
real subprocesses against shared filesystem state).

**Fails-loud surfaces**: The canonical fixture template at
``tests/test_no_clone_install.py:84-92`` silently skips when
``uv build --wheel`` panics in the ``system-configuration`` /
``Tokio executor failed`` crate (sandboxed CI without PyPI/GitHub
egress). Per the spec's "fails-loud" mandate, **this file overrides
that behavior**: the egress-panic case routes to ``pytest.fail(...)``
NOT ``pytest.skip(...)`` so an overnight runner without network access
reports the gap explicitly rather than silently passing.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import psutil
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "cortex-overnight"
SERVER_PATH = PLUGIN_ROOT / "server.py"


# ---------------------------------------------------------------------------
# Fails-loud surfaces — overrides for the canonical fixture-template's
# silent skip-on-egress-panic case.
# ---------------------------------------------------------------------------

# Substrings emitted by ``uv build --wheel`` when the system-configuration
# crate's tokio executor panics due to blocked PyPI/GitHub egress. The
# canonical fixture template at ``tests/test_no_clone_install.py:84-92``
# silently skips on these — but per the R23 fails-loud mandate, we route
# them to ``pytest.fail`` so sandboxed CI reports the gap explicitly.
#
# Note: literal substrings ``system-configuration`` and
# ``Tokio executor failed`` must appear in this file for the verification
# grep at the bottom of the task description.
_EGRESS_PANIC_MARKERS = ("system-configuration", "Tokio executor failed")


def _fail_loud_if_uv_unavailable() -> None:
    """``pytest.fail`` (NOT ``pytest.skip``) when ``uv`` is not on PATH."""
    if shutil.which("uv") is None:
        pytest.fail(
            "uv tool unavailable; integration test cannot run as "
            "agent-verifiable acceptance"
        )


def _fails_loud_on_egress_panic(
    proc: subprocess.CompletedProcess, *, context: str
) -> None:
    """Route ``uv build`` egress panics to ``pytest.fail`` not ``pytest.skip``.

    The canonical fixture template at ``tests/test_no_clone_install.py:84-92``
    silently skips on these markers. This helper enforces fails-loud
    per the R23 acceptance gate so an overnight runner without network
    egress reports the gap explicitly rather than silently passing.
    """
    if proc.returncode == 0:
        return
    combined = f"{proc.stdout}\n{proc.stderr}"
    for marker in _EGRESS_PANIC_MARKERS:
        if marker in combined:
            pytest.fail(
                f"{context}: `uv build --wheel` panicked with "
                f"{marker!r}; running in a sandbox that blocks "
                f"PyPI/GitHub egress. Per R23 fails-loud, this is a "
                f"hard failure (NOT a skip) so the acceptance gate "
                f"reports the gap.\n"
                f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
            )
    pytest.fail(
        f"{context}: `uv build --wheel` exited "
        f"{proc.returncode}\nstdout={proc.stdout!r}\n"
        f"stderr={proc.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Wheel builders — synthetic version via HATCH_BUILD_HOOK_VCS_FALLBACK_VERSION.
# ---------------------------------------------------------------------------


def _build_wheel(
    *,
    version: str,
    out_dir: Path,
    cache_dir: Path,
    extra_env: Optional[dict[str, str]] = None,
    repo_src: Optional[Path] = None,
) -> Path:
    """Build a wheel from ``repo_src`` (default REPO_ROOT) at synthetic ``version``.

    Uses ``HATCH_BUILD_HOOK_VCS_FALLBACK_VERSION`` to override hatch-vcs's
    git-derived PEP 440 version. The output wheel lands in ``out_dir``.

    Returns the wheel path. Calls ``pytest.fail`` on any build failure,
    including the egress-panic case the canonical fixture template
    silently skips.
    """
    src = repo_src if repo_src is not None else REPO_ROOT
    env = os.environ.copy()
    # hatch-vcs honors this env var when set; the resulting wheel's
    # ``importlib.metadata`` package version equals ``version``.
    env["HATCH_BUILD_HOOK_VCS_FALLBACK_VERSION"] = version
    env["SETUPTOOLS_SCM_PRETEND_VERSION"] = version  # belt-and-braces
    env["UV_CACHE_DIR"] = str(cache_dir)
    if extra_env:
        env.update(extra_env)

    proc = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out_dir)],
        cwd=str(src),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    _fails_loud_on_egress_panic(proc, context=f"_build_wheel(version={version!r})")

    wheels = sorted(out_dir.glob("cortex_command-*.whl"))
    if not wheels:
        pytest.fail(
            f"`uv build --wheel` produced no cortex_command-*.whl in "
            f"{out_dir}; stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
        )
    return wheels[-1]


def _install_wheel(
    *,
    wheel_path: Path,
    tool_dir: Path,
    bin_dir: Path,
    cache_dir: Path,
) -> dict[str, str]:
    """``uv tool install --reinstall <wheel>`` into an isolated env.

    Returns the env dict for subsequent ``cortex …`` invocations.
    """
    tool_dir.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["UV_TOOL_DIR"] = str(tool_dir)
    env["UV_TOOL_BIN_DIR"] = str(bin_dir)
    env["UV_CACHE_DIR"] = str(cache_dir)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"

    proc = subprocess.run(
        ["uv", "tool", "install", "--reinstall", str(wheel_path)],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        combined = f"{proc.stdout}\n{proc.stderr}"
        for marker in _EGRESS_PANIC_MARKERS:
            if marker in combined:
                pytest.fail(
                    f"`uv tool install --reinstall {wheel_path.name}` "
                    f"panicked with {marker!r} (egress-blocked sandbox). "
                    f"Per R23 fails-loud, this is a hard failure.\n"
                    f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
                )
        pytest.fail(
            f"`uv tool install --reinstall {wheel_path.name}` failed: "
            f"exit={proc.returncode}\n"
            f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
        )
    return env


def _invoke_cortex_print_root(env: dict[str, str]) -> dict:
    """Run ``cortex --print-root --format json`` in ``env`` and return payload."""
    cortex_bin = Path(env["UV_TOOL_BIN_DIR"]) / "cortex"
    assert cortex_bin.exists(), f"cortex console script missing: {cortex_bin}"
    proc = subprocess.run(
        [str(cortex_bin), "--print-root", "--format", "json"],
        cwd=str(REPO_ROOT),  # so _resolve_user_project_root() succeeds
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, (
        f"`cortex --print-root --format json` exit {proc.returncode}\n"
        f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# Plugin server loader.
# ---------------------------------------------------------------------------


def _load_fresh_server_module(module_name: str):
    """Import server.py as a fresh module under a unique name.

    Each test loads a fresh copy so monkey-patches to ``CLI_PIN`` (and
    other module-level state) don't leak across tests.

    Also ensures the plugin's vendored ``install_guard`` sibling is
    importable — the version-mismatch branch lazy-imports it before
    consulting the in-flight guard, and the test process's sys.path
    does not include PLUGIN_ROOT by default.
    """
    os.environ["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    if str(PLUGIN_ROOT) not in sys.path:
        sys.path.insert(0, str(PLUGIN_ROOT))
    spec = importlib.util.spec_from_file_location(module_name, SERVER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Phase (a) — baseline install reports synthetic package version + schema.
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.serial
def test_baseline_install_reports_package_version(tmp_path: Path) -> None:
    """R23 (a) — wheel-installed CLI at synthetic v0.1.0 reports correct envelope."""
    _fail_loud_if_uv_unavailable()

    wheel_dir = tmp_path / "wheels_a"
    tool_dir = tmp_path / "uv_tools_a"
    bin_dir = tmp_path / "uv_bin_a"
    cache_dir = tmp_path / "uv_cache_a"

    wheel = _build_wheel(version="0.1.0", out_dir=wheel_dir, cache_dir=cache_dir)
    assert "cortex_command-0.1.0-" in wheel.name, (
        f"wheel filename does not embed synthetic version 0.1.0: {wheel.name}"
    )

    env = _install_wheel(
        wheel_path=wheel,
        tool_dir=tool_dir,
        bin_dir=bin_dir,
        cache_dir=cache_dir,
    )
    payload = _invoke_cortex_print_root(env)

    assert payload.get("version") == "0.1.0", (
        f"print-root version != '0.1.0': {payload!r}"
    )
    assert payload.get("schema_version") == "2.0", (
        f"print-root schema_version != '2.0': {payload!r}"
    )


# ---------------------------------------------------------------------------
# Phase (b) — synthetic v0.2.0 wheel builds.
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.serial
def test_synthetic_v_0_2_0_wheel_builds(tmp_path: Path) -> None:
    """R23 (b) — hatch-vcs accepts synthetic v0.2.0 override and builds a wheel."""
    _fail_loud_if_uv_unavailable()

    wheel_dir = tmp_path / "wheels_b"
    cache_dir = tmp_path / "uv_cache_b"

    wheel = _build_wheel(version="0.2.0", out_dir=wheel_dir, cache_dir=cache_dir)
    assert "cortex_command-0.2.0-" in wheel.name, (
        f"wheel filename does not embed synthetic version 0.2.0: {wheel.name}"
    )
    assert wheel.is_file(), f"wheel path not a file: {wheel}"


# ---------------------------------------------------------------------------
# Phase (c) — version-mismatch reinstall fires with the correct stage.
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.serial
def test_version_mismatch_fires_reinstall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R23 (c) — version-mismatch branch fires reinstall with stage = ``version_mismatch_reinstall``.

    Builds v0.1.0 + v0.2.0 wheels, installs v0.1.0, rewrites the loaded
    plugin module's ``CLI_PIN`` to ``("v0.2.0", "2.0")``, and spies on
    ``_run_install_and_verify`` to capture the stage. The reinstall is
    redirected to install the pre-built v0.2.0 wheel rather than
    invoking ``git+...@v0.2.0`` (no network egress required).
    """
    _fail_loud_if_uv_unavailable()

    wheel_dir = tmp_path / "wheels_c"
    tool_dir = tmp_path / "uv_tools_c"
    bin_dir = tmp_path / "uv_bin_c"
    cache_dir = tmp_path / "uv_cache_c"
    state_dir = tmp_path / "state_c"
    state_dir.mkdir()

    # Redirect XDG_STATE_HOME + HOME so NDJSON + sentinel writes land
    # under tmp_path.
    monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))
    monkeypatch.setenv("HOME", str(state_dir))
    monkeypatch.delenv("CORTEX_AUTO_INSTALL", raising=False)

    wheel_v1 = _build_wheel(
        version="0.1.0", out_dir=wheel_dir, cache_dir=cache_dir
    )
    wheel_v2 = _build_wheel(
        version="0.2.0", out_dir=wheel_dir, cache_dir=cache_dir
    )

    install_env = _install_wheel(
        wheel_path=wheel_v1,
        tool_dir=tool_dir,
        bin_dir=bin_dir,
        cache_dir=cache_dir,
    )

    # Sanity: pre-mismatch the installed CLI reports v0.1.0.
    pre_payload = _invoke_cortex_print_root(install_env)
    assert pre_payload.get("version") == "0.1.0"

    # Load a fresh server module and rewrite CLI_PIN.
    server = _load_fresh_server_module("cortex_plugin_server_c")
    monkeypatch.setattr(server, "CLI_PIN", ("v0.2.0", "2.0"))
    monkeypatch.setattr(server, "MCP_REQUIRED_CLI_VERSION", "2.0")

    # Spy on _run_install_and_verify to capture the stage argument the
    # version-comparison branch hands in. Replace the body with a call
    # to ``uv tool install --reinstall <local v0.2.0 wheel>`` (no
    # git-egress required).
    captured_stages: list[str] = []

    def _spy_install(*, stage: str) -> None:
        captured_stages.append(stage)
        proc = subprocess.run(
            ["uv", "tool", "install", "--reinstall", str(wheel_v2)],
            env={
                **os.environ,
                "UV_TOOL_DIR": str(tool_dir),
                "UV_TOOL_BIN_DIR": str(bin_dir),
                "UV_CACHE_DIR": str(cache_dir),
                "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            },
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, (
            f"spy reinstall failed: exit={proc.returncode}\n"
            f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
        )

    monkeypatch.setattr(server, "_run_install_and_verify", _spy_install)

    # Patch shutil.which inside the server module to return the
    # tempdir-installed cortex (cortex IS on PATH, so the branch flows
    # through the version-comparison path, NOT first-install).
    cortex_bin = bin_dir / "cortex"

    real_run = subprocess.run

    def _run_with_temp_path(argv, **kwargs):
        kw_env = kwargs.pop("env", None)
        env = kw_env if kw_env is not None else os.environ.copy()
        env = dict(env)
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
        return real_run(argv, env=env, **kwargs)

    with (
        patch.object(server.shutil, "which", return_value=str(cortex_bin)),
        patch.object(server.subprocess, "run", side_effect=_run_with_temp_path),
    ):
        server._ensure_cortex_installed()

    assert captured_stages == ["version_mismatch_reinstall"], (
        f"expected exactly one reinstall with stage "
        f"'version_mismatch_reinstall' (NOT '_parse_failure'); "
        f"captured: {captured_stages!r}"
    )

    # Verify the post-install CLI reports v0.2.0.
    post_payload = _invoke_cortex_print_root(install_env)
    assert post_payload.get("version") == "0.2.0", (
        f"post-reinstall version != '0.2.0': {post_payload!r}"
    )


# ---------------------------------------------------------------------------
# Phase (d) — matching version short-circuits (no reinstall, no NDJSON).
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.serial
def test_matching_version_passes_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R23 (d) — matching installed-version + CLI_PIN does NOT reinstall."""
    _fail_loud_if_uv_unavailable()

    wheel_dir = tmp_path / "wheels_d"
    tool_dir = tmp_path / "uv_tools_d"
    bin_dir = tmp_path / "uv_bin_d"
    cache_dir = tmp_path / "uv_cache_d"
    state_dir = tmp_path / "state_d"
    state_dir.mkdir()

    monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))
    monkeypatch.setenv("HOME", str(state_dir))
    monkeypatch.delenv("CORTEX_AUTO_INSTALL", raising=False)

    wheel = _build_wheel(version="0.1.0", out_dir=wheel_dir, cache_dir=cache_dir)
    install_env = _install_wheel(
        wheel_path=wheel,
        tool_dir=tool_dir,
        bin_dir=bin_dir,
        cache_dir=cache_dir,
    )

    payload = _invoke_cortex_print_root(install_env)
    assert payload.get("version") == "0.1.0"

    server = _load_fresh_server_module("cortex_plugin_server_d")
    # CLI_PIN matches installed version — branch should short-circuit
    # and NOT call _run_install_and_verify.
    monkeypatch.setattr(server, "CLI_PIN", ("v0.1.0", "2.0"))
    monkeypatch.setattr(server, "MCP_REQUIRED_CLI_VERSION", "2.0")

    install_called: list[str] = []

    def _spy_install(*, stage: str) -> None:
        install_called.append(stage)

    monkeypatch.setattr(server, "_run_install_and_verify", _spy_install)

    cortex_bin = bin_dir / "cortex"
    real_run = subprocess.run

    def _run_with_temp_path(argv, **kwargs):
        kw_env = kwargs.pop("env", None)
        env = kw_env if kw_env is not None else os.environ.copy()
        env = dict(env)
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
        return real_run(argv, env=env, **kwargs)

    with (
        patch.object(server.shutil, "which", return_value=str(cortex_bin)),
        patch.object(server.subprocess, "run", side_effect=_run_with_temp_path),
    ):
        server._ensure_cortex_installed()

    assert install_called == [], (
        f"matching-version branch must NOT reinstall; "
        f"captured stages: {install_called!r}"
    )

    # Defense in depth: no NDJSON ``version_mismatch_*`` record landed
    # under XDG_STATE_HOME's last-error.log.
    last_error_log = state_dir / "cortex-command" / "last-error.log"
    if last_error_log.is_file():
        log_text = last_error_log.read_text(encoding="utf-8")
        assert "version_mismatch" not in log_text, (
            f"no-mismatch branch unexpectedly emitted an NDJSON record "
            f"under stage version_mismatch_*: log={log_text!r}"
        )


# ---------------------------------------------------------------------------
# Phase (e) — active overnight session blocks the reinstall.
# ---------------------------------------------------------------------------


def _live_start_time_iso() -> str:
    """Return this test process's create_time as ISO-8601 (UTC).

    The plugin's coarse ``_plugin_pid_verifier`` checks magic +
    schema_version + ``os.kill(pid, 0)`` + a non-empty ``ps -p <pid>``
    response. It does not bit-exact-match start_time. But the canonical
    CLI-side ``verify_runner_pid`` (and the install_guard's vendored
    sibling pid_verifier contract) requires start_time, so we supply a
    real psutil.create_time() epoch — critical-review correction in the
    task brief.
    """
    epoch = psutil.Process(os.getpid()).create_time()
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


@pytest.mark.slow
@pytest.mark.serial
def test_active_session_blocks_reinstall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R23 (e) — in-flight overnight session blocks reinstall on version-mismatch.

    Writes an active-session pointer + runner.pid with the runner magic
    constant, schema_version=1, the test's own pid, and the test
    process's psutil create_time. Sets up a version-mismatch
    (CLI_PIN != installed version) and asserts:

    1. ``_run_install_and_verify`` is NOT called (reinstall blocked).
    2. An NDJSON record with stage exactly
       ``version_mismatch_blocked_by_inflight_session`` lands in the
       test-controlled XDG_STATE_HOME's last-error.log.
    """
    _fail_loud_if_uv_unavailable()

    wheel_dir = tmp_path / "wheels_e"
    tool_dir = tmp_path / "uv_tools_e"
    bin_dir = tmp_path / "uv_bin_e"
    cache_dir = tmp_path / "uv_cache_e"
    state_dir = tmp_path / "state_e"
    home_dir = tmp_path / "home_e"
    state_dir.mkdir()
    home_dir.mkdir()

    monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.delenv("CORTEX_AUTO_INSTALL", raising=False)
    monkeypatch.delenv("CORTEX_ALLOW_INSTALL_DURING_RUN", raising=False)

    wheel = _build_wheel(version="0.1.0", out_dir=wheel_dir, cache_dir=cache_dir)
    install_env = _install_wheel(
        wheel_path=wheel,
        tool_dir=tool_dir,
        bin_dir=bin_dir,
        cache_dir=cache_dir,
    )

    # Plumb the live in-flight session pointer + runner.pid under the
    # HOME-redirected ``Path.home()/.local/share/overnight-sessions/``
    # path that ``_plugin_active_session_path`` returns.
    session_id = "session-test-r23-e"
    session_dir = tmp_path / "sessions" / session_id
    session_dir.mkdir(parents=True)

    start_time = _live_start_time_iso()
    runner_pid_payload = {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": os.getpid(),
        "pgid": os.getpid(),
        "start_time": start_time,
        "session_id": session_id,
        "session_dir": str(session_dir),
        "repo_path": str(session_dir),
    }
    (session_dir / "runner.pid").write_text(
        json.dumps(runner_pid_payload), encoding="utf-8"
    )

    active_dir = home_dir / ".local" / "share" / "overnight-sessions"
    active_dir.mkdir(parents=True)
    (active_dir / "active-session.json").write_text(
        json.dumps(
            {
                **runner_pid_payload,
                "phase": "executing",
            }
        ),
        encoding="utf-8",
    )

    server = _load_fresh_server_module("cortex_plugin_server_e")
    # Force a version mismatch — CLI_PIN points at v0.2.0 while
    # installed is v0.1.0.
    monkeypatch.setattr(server, "CLI_PIN", ("v0.2.0", "2.0"))
    monkeypatch.setattr(server, "MCP_REQUIRED_CLI_VERSION", "2.0")

    install_called: list[str] = []

    def _spy_install(*, stage: str) -> None:
        install_called.append(stage)

    monkeypatch.setattr(server, "_run_install_and_verify", _spy_install)

    cortex_bin = bin_dir / "cortex"
    real_run = subprocess.run

    def _run_with_temp_path(argv, **kwargs):
        kw_env = kwargs.pop("env", None)
        env = kw_env if kw_env is not None else os.environ.copy()
        env = dict(env)
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
        return real_run(argv, env=env, **kwargs)

    with (
        patch.object(server.shutil, "which", return_value=str(cortex_bin)),
        patch.object(server.subprocess, "run", side_effect=_run_with_temp_path),
    ):
        server._ensure_cortex_installed()

    assert install_called == [], (
        f"in-flight guard must block reinstall; captured stages: "
        f"{install_called!r}"
    )

    # NDJSON record with the blocked-by-inflight stage must land under
    # the redirected XDG_STATE_HOME.
    last_error_log = state_dir / "cortex-command" / "last-error.log"
    assert last_error_log.is_file(), (
        f"NDJSON log missing at {last_error_log}; state_dir contents: "
        f"{list(state_dir.rglob('*'))}"
    )
    log_lines = [
        line for line in last_error_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    blocked_records = [
        json.loads(line)
        for line in log_lines
        if json.loads(line).get("stage")
        == "version_mismatch_blocked_by_inflight_session"
    ]
    assert len(blocked_records) >= 1, (
        f"expected at least one NDJSON record with stage "
        f"'version_mismatch_blocked_by_inflight_session'; log: {log_lines!r}"
    )


# ---------------------------------------------------------------------------
# Phase (f) — R13 schema-floor violation emits the stderr remediation.
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.serial
def test_r13_schema_floor_emits_remediation_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """R23 (f) — schema-floor violation under wheel install emits stderr remediation.

    ``_JSON_SCHEMA_VERSION`` is a Python module constant in
    ``cortex_command/overnight/cli_handler.py`` — NOT a hatch-vcs-derived
    value, so the HATCH_BUILD_HOOK_VCS_FALLBACK_VERSION env-var override
    cannot reach it. Per the task brief's critical-review correction, we
    instead:

    1. Snapshot the repo tree into a per-test source dir.
    2. Source-edit ``cortex_command/overnight/cli_handler.py`` to set
       ``_JSON_SCHEMA_VERSION = "1.0"``.
    3. Run ``uv build --wheel`` from that source dir at synthetic
       v0.1.0.
    4. Install the wheel into the tmpdir-isolated uv-tool env.
    5. Invoke ``_schema_floor_violated`` against the print-root payload
       (with ``MCP_REQUIRED_CLI_VERSION="2.0"``); under wheel install
       (no ``.git`` at the CLI's reported root) the helper emits the
       single-line stderr remediation rather than entering the dead
       orchestration path.
    6. Assert the stderr message contains both literal substrings.
    """
    _fail_loud_if_uv_unavailable()

    wheel_dir = tmp_path / "wheels_f"
    tool_dir = tmp_path / "uv_tools_f"
    bin_dir = tmp_path / "uv_bin_f"
    cache_dir = tmp_path / "uv_cache_f"
    src_dir = tmp_path / "repo_src_f"

    # Snapshot the repo tree (skipping uninteresting heavyweight dirs)
    # into src_dir so the source-edit doesn't mutate REPO_ROOT.
    def _ignore(_directory: str, names: list[str]) -> list[str]:
        return [
            n for n in names
            if n in (
                ".git",
                "node_modules",
                "dist",
                "build",
                ".venv",
                ".pytest_cache",
                "__pycache__",
                ".tox",
            )
        ]

    shutil.copytree(REPO_ROOT, src_dir, ignore=_ignore, symlinks=True)
    # hatch-vcs requires a git dir or the env-var override; we use the
    # env-var override below in _build_wheel.

    cli_handler = src_dir / "cortex_command" / "overnight" / "cli_handler.py"
    text = cli_handler.read_text(encoding="utf-8")
    new_text = text.replace(
        '_JSON_SCHEMA_VERSION = "2.0"',
        '_JSON_SCHEMA_VERSION = "1.0"',
        1,
    )
    assert new_text != text, (
        f"source-edit of _JSON_SCHEMA_VERSION did not find the literal "
        f'`_JSON_SCHEMA_VERSION = "2.0"` in {cli_handler}'
    )
    cli_handler.write_text(new_text, encoding="utf-8")

    wheel = _build_wheel(
        version="0.1.0",
        out_dir=wheel_dir,
        cache_dir=cache_dir,
        repo_src=src_dir,
    )
    install_env = _install_wheel(
        wheel_path=wheel,
        tool_dir=tool_dir,
        bin_dir=bin_dir,
        cache_dir=cache_dir,
    )

    payload = _invoke_cortex_print_root(install_env)
    # Confirm the source-edit actually flowed into the installed wheel.
    assert payload.get("schema_version") == "1.0", (
        f"installed CLI reports schema_version != '1.0'; the source-edit "
        f"did not flow into the wheel: {payload!r}"
    )

    # Load a fresh server module; force MCP_REQUIRED_CLI_VERSION to 2.0
    # so the floor is violated by the installed CLI's reported 1.0.
    server = _load_fresh_server_module("cortex_plugin_server_f")
    # The discovery payload's ``root`` is the user-project root reported
    # by the wheel-installed CLI. Confirm it is NOT a git dir (wheel
    # install path) so _schema_floor_violated's wheel-install branch is
    # the one that fires.
    project_root = Path(payload["root"])
    has_dot_git = (project_root / ".git").is_dir()

    # If the test happens to run under a project root with .git, force
    # the wheel-install branch by pointing root at a fresh tmp dir
    # without .git. The helper does NOT touch the filesystem there
    # other than the .git probe.
    if has_dot_git:
        synth_root = tmp_path / "non_git_root_f"
        synth_root.mkdir()
        payload = dict(payload)
        payload["root"] = str(synth_root)

    # Override MCP_REQUIRED_CLI_VERSION to 2.0 (above the installed
    # CLI's 1.0). CLI_PIN is left unchanged — only the major-bump
    # comparison matters here.
    object.__setattr__(server, "MCP_REQUIRED_CLI_VERSION", "2.0")

    # Invoke _schema_floor_violated directly. Per the helper's wheel-
    # install branch, it prints the remediation message to stderr and
    # returns False so the caller skips the dead orchestration path.
    capsys.readouterr()  # drain any prior stderr captured by pytest
    server._schema_floor_violated(payload)
    captured = capsys.readouterr()

    assert "Schema-floor violation: installed CLI schema_version=" in captured.err, (
        f"stderr missing 'Schema-floor violation: installed CLI "
        f"schema_version=' literal; captured stderr: {captured.err!r}"
    )
    assert "uv tool install --reinstall git+" in captured.err, (
        f"stderr missing 'uv tool install --reinstall git+' literal; "
        f"captured stderr: {captured.err!r}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--run-slow"])
