"""Validation-gate tests for the no-clone install migration (R6b, R6e).

Two distinct surfaces are validated here:

* ``test_target_state`` — **target state**: builds the wheel via ``uv
  build``, installs it into a tmpdir-isolated ``uv tool`` env, and probes
  the wheel-installed CLI end-to-end. The probes confirm that
  ``cortex --print-root --format json`` emits the v1.1 envelope and that
  every package-internal ``importlib.resources`` lookup (the six sites
  from Tasks 2/3) resolves cleanly under non-editable wheel install. This
  is the gate that catches ``Path(__file__)`` regressions that silently
  break under a non-editable install but still pass under editable
  install (the lifecycle-115 failure mode).

* ``test_mcp_first_install_hook`` — **transition mechanism**: exercises
  ``plugins/cortex-overnight/server.py:_ensure_cortex_installed``
  with mocked ``subprocess.run`` and ``shutil.which`` to verify the hook's
  control flow without doing a real ``uv tool install``. Asserts: (1) the
  ``uv tool install --reinstall git+...@<CLI_PIN[0]>`` invocation fires
  on cortex-absent; (2) post-install verification with ``cortex
  --print-root --format json`` is invoked; (3) on simulated install
  failure a sentinel is written under the test-controlled
  ``XDG_STATE_HOME``; (4) a second invocation within 60s reads the
  sentinel and raises without re-attempting the install.

Pattern reference: ``tests/test_cli_upgrade.py:37-84`` (subprocess mock
pattern) and ``tests/test_cli_print_root.py`` (CLI-via-subprocess
invocation pattern).
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "cortex-overnight"
SERVER_PATH = PLUGIN_ROOT / "server.py"


# ---------------------------------------------------------------------------
# Module-scoped wheel build fixture (R6b).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the wheel once per session and yield the wheel path.

    Uses ``uv build --wheel`` against the repo root. The wheel lands in
    ``<repo>/dist/`` per hatch's default. Skips the test if ``uv`` is
    unavailable on PATH (the migration depends on it; CI hosts that lack
    uv cannot exercise the target-state surface).
    """
    if shutil.which("uv") is None:
        pytest.skip("`uv` not on PATH; cannot build wheel for target-state probe")

    out_dir = tmp_path_factory.mktemp("wheel_dist")
    proc = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out_dir)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        # Sandboxes that block egress (no PyPI / no GitHub) cause uv to
        # panic in the system-configuration crate before reporting the
        # actual network error. Detect that signature and skip rather
        # than failing — the test exercises wheel-install behavior, which
        # cannot run without network access.
        combined = f"{proc.stdout}\n{proc.stderr}"
        if (
            "Tokio executor failed" in combined
            or "system-configuration" in combined
        ):
            pytest.skip(
                "`uv build --wheel` requires network access; running in a "
                "sandbox that blocks PyPI/GitHub egress (uv panicked in "
                "system-configuration crate)."
            )
        pytest.fail(
            f"`uv build --wheel` failed: exit={proc.returncode}\n"
            f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
        )

    wheels = sorted(out_dir.glob("cortex_command-*.whl"))
    if not wheels:
        pytest.fail(
            f"`uv build --wheel` produced no cortex_command-*.whl in {out_dir}"
        )
    # Most-recent build wins — there is normally exactly one wheel per
    # version, but tolerate accidental leftovers.
    return wheels[-1]


# ---------------------------------------------------------------------------
# Helper: install the wheel into an isolated uv-tool env.
# ---------------------------------------------------------------------------


def _install_wheel_isolated(wheel_path: Path, tmp_path: Path) -> dict[str, str]:
    """``uv tool install --reinstall <wheel>`` into a tmpdir-isolated env.

    Returns the env dict (``UV_TOOL_DIR`` + ``UV_TOOL_BIN_DIR`` + a
    ``PATH`` prepended with the bin dir) callers should pass to
    subsequent ``cortex …`` subprocess invocations so the installed shim
    is found ahead of any system-wide install.
    """
    tool_dir = tmp_path / "uv_tools"
    bin_dir = tmp_path / "uv_bin"
    tool_dir.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["UV_TOOL_DIR"] = str(tool_dir)
    env["UV_TOOL_BIN_DIR"] = str(bin_dir)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"

    proc = subprocess.run(
        ["uv", "tool", "install", "--reinstall", str(wheel_path)],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        pytest.fail(
            f"`uv tool install --reinstall {wheel_path.name}` failed: "
            f"exit={proc.returncode}\n"
            f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
        )
    return env


# ---------------------------------------------------------------------------
# test_target_state — R6b.
# ---------------------------------------------------------------------------


# The six package-internal sites converted in Tasks 2 and 3.
# Each tuple is (package, resource_name) — exactly the form
# ``importlib.resources.files(package).joinpath(resource)`` consumes.
PACKAGE_INTERNAL_SITES: list[tuple[str, str]] = [
    ("cortex_command.init.templates", "cortex/lifecycle.config.md"),
    ("cortex_command.overnight.prompts", "repair-agent.md"),
    ("cortex_command.pipeline.prompts", "review.md"),
    ("cortex_command.overnight.prompts", "batch-brain.md"),
    ("cortex_command.pipeline.prompts", "implement.md"),
    ("cortex_command.dashboard.templates", "base.html"),
]


def _python_inside_uv_tool(tool_dir: Path) -> Path:
    """Return the ``python`` interpreter path for the cortex-command tool env.

    ``uv tool install`` lays out the env at
    ``${UV_TOOL_DIR}/<package>/bin/python`` (POSIX) or
    ``${UV_TOOL_DIR}\\<package>\\Scripts\\python.exe`` (Windows). We
    target POSIX layout because the cortex codebase only supports
    macOS/Linux.
    """
    candidates = [
        tool_dir / "cortex-command" / "bin" / "python",
        tool_dir / "cortex-command" / "bin" / "python3",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    # Fall back to scanning under tool_dir/cortex-command/bin/.
    bin_dir = tool_dir / "cortex-command" / "bin"
    if bin_dir.is_dir():
        for entry in bin_dir.iterdir():
            if entry.name.startswith("python"):
                return entry
    pytest.fail(
        f"could not locate python interpreter inside uv tool env at {tool_dir}"
    )


def test_target_state(built_wheel: Path, tmp_path: Path) -> None:
    """R6b — wheel-installed CLI works under non-editable install.

    Builds the wheel, installs it into a tmpdir-isolated ``uv tool`` env,
    then probes:

    1. ``cortex --print-root --format json`` exits 0 and emits parseable
       JSON containing the v1.1 envelope keys.
    2. ``importlib.resources.files("cortex_command.overnight.prompts")``
       can read ``orchestrator-round.md`` (non-empty content).
    3. Each of the six package-internal sites from
       :data:`PACKAGE_INTERNAL_SITES` resolves under the wheel install.
    """
    env = _install_wheel_isolated(built_wheel, tmp_path)
    cortex_bin = Path(env["UV_TOOL_BIN_DIR"]) / "cortex"
    assert cortex_bin.exists(), (
        f"`cortex` console script missing after install: {cortex_bin}"
    )

    # ------------------------------------------------------------------
    # Probe 1: cortex --print-root --format json
    # ------------------------------------------------------------------
    # Use the repo root as CWD so ``_resolve_user_project_root()`` finds
    # the project root via the lifecycle/+backlog/ sanity check (the
    # wheel install does not bring the user project with it).
    print_root_proc = subprocess.run(
        [str(cortex_bin), "--print-root", "--format", "json"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert print_root_proc.returncode == 0, (
        f"`cortex --print-root --format json` exit "
        f"{print_root_proc.returncode}\n"
        f"stdout={print_root_proc.stdout!r}\n"
        f"stderr={print_root_proc.stderr!r}"
    )
    payload: dict[str, Any] = json.loads(print_root_proc.stdout)
    for key in ("version", "root", "remote_url", "head_sha"):
        assert key in payload, (
            f"missing key {key!r} in --print-root payload: {payload!r}"
        )
    # version is the v1.1 envelope (additive: package_root is also
    # present, but R6b's listed required keys are the four above).
    assert isinstance(payload["version"], str)
    assert payload["version"].startswith("1."), (
        f"version field does not start with '1.': {payload['version']!r}"
    )

    # ------------------------------------------------------------------
    # Probe 2: importlib.resources lookup of orchestrator-round.md.
    # Run inside the installed env's interpreter so we exercise the
    # wheel-extracted package layout, not the editable copy.
    # ------------------------------------------------------------------
    python_bin = _python_inside_uv_tool(Path(env["UV_TOOL_DIR"]))
    inline_probe = (
        "import importlib.resources, sys\n"
        "content = importlib.resources.files("
        "'cortex_command.overnight.prompts')"
        ".joinpath('orchestrator-round.md').read_text(encoding='utf-8')\n"
        "assert content, 'orchestrator-round.md is empty'\n"
        "sys.stdout.write(str(len(content)))\n"
    )
    probe_proc = subprocess.run(
        [str(python_bin), "-c", inline_probe],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert probe_proc.returncode == 0, (
        f"orchestrator-round.md probe failed: exit={probe_proc.returncode}\n"
        f"stdout={probe_proc.stdout!r}\nstderr={probe_proc.stderr!r}"
    )
    assert int(probe_proc.stdout.strip()) > 0

    # ------------------------------------------------------------------
    # Probe 3: parameterized over the six package-internal sites
    # converted in Tasks 2 and 3. Each must resolve under the wheel.
    # ------------------------------------------------------------------
    for package, resource_name in PACKAGE_INTERNAL_SITES:
        site_probe = (
            "import importlib.resources, sys\n"
            f"resource = importlib.resources.files({package!r})"
            f".joinpath({resource_name!r})\n"
            "assert resource.is_file(), f'not a file: {resource}'\n"
            "content = resource.read_text(encoding='utf-8')\n"
            "assert content, 'empty content'\n"
            "sys.stdout.write('ok')\n"
        )
        site_proc = subprocess.run(
            [str(python_bin), "-c", site_probe],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert site_proc.returncode == 0, (
            f"importlib.resources lookup failed for "
            f"{package}/{resource_name}: exit={site_proc.returncode}\n"
            f"stdout={site_proc.stdout!r}\nstderr={site_proc.stderr!r}"
        )
        assert site_proc.stdout.strip() == "ok"


# ---------------------------------------------------------------------------
# test_mcp_first_install_hook — R6e.
# ---------------------------------------------------------------------------


def _load_server_module():
    """Import ``plugins/cortex-overnight/server.py`` as a module.

    Sets ``CLAUDE_PLUGIN_ROOT`` so the confused-deputy guard at the top
    of the file accepts the load. Mirrors the loader pattern used in
    ``tests/test_mcp_cortex_cli_missing.py`` and
    ``tests/test_mcp_subprocess_contract.py``.
    """
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


def _success_completed(stdout: str, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=stdout,
        stderr=stderr,
    )


def _fail_completed(stderr: str = "uv tool install: simulated failure") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="",
        stderr=stderr,
    )


def _print_root_success_stdout() -> str:
    return json.dumps(
        {
            "version": "0.1.0",
            "schema_version": "2.0",
            "root": "/fake/user/project",
            "package_root": "/fake/site-packages/cortex_command",
            "remote_url": "git@github.com:user/cortex-command.git",
            "head_sha": "0" * 40,
        }
    )


def test_mcp_first_install_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R6e — `_ensure_cortex_installed` control-flow under cortex-absent.

    Asserts (with `subprocess.run` mocked):

    1. The hook calls ``uv tool install --reinstall git+...@<CLI_PIN[0]>``
       when ``shutil.which("cortex")`` returns None.
    2. Post-install verification calls ``cortex --print-root --format
       json``.
    3. On simulated install failure a sentinel
       ``${XDG_STATE_HOME}/cortex-command/install-failed.*`` is written.
    4. A second `_ensure_cortex_installed()` call within 60s reads the
       sentinel and raises ``CortexInstallFailed`` *without* re-attempting
       the install (no second ``uv tool install …`` call is dispatched).
    """
    # Isolate XDG_STATE_HOME / HOME so sentinel + last-error.log paths
    # land under tmp_path. Setting both belt-and-braces because the hook
    # falls back to ``$HOME/.local/state`` when XDG_STATE_HOME is absent.
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    # Ensure CORTEX_AUTO_INSTALL=0 is NOT set — that would short-circuit
    # the hook before it does anything interesting.
    monkeypatch.delenv("CORTEX_AUTO_INSTALL", raising=False)

    server = _load_server_module()

    # ------------------------------------------------------------------
    # Phase 1: simulate install failure (uv tool install returns
    # non-zero). Verify the install was attempted, no post-install
    # verification fired, sentinel was written, and the second call
    # short-circuits via the sentinel.
    # ------------------------------------------------------------------
    fail_run = MagicMock(return_value=_fail_completed())

    # `shutil.which` is referenced from the server module's namespace
    # (``import shutil`` at the top of server.py); patch the bound name.
    with patch.object(server, "shutil") as mock_shutil_phase1, patch.object(
        server.subprocess, "run", fail_run
    ):
        mock_shutil_phase1.which = MagicMock(return_value=None)
        with pytest.raises(server.CortexInstallFailed):
            server._ensure_cortex_installed()

    # Assertion 1: uv tool install --reinstall git+...@<tag> was invoked.
    install_argv_seen = [c.args[0] for c in fail_run.call_args_list]
    expected_install_prefix = [
        "uv",
        "tool",
        "install",
        "--reinstall",
    ]
    install_calls = [
        argv for argv in install_argv_seen
        if isinstance(argv, list) and argv[: len(expected_install_prefix)]
        == expected_install_prefix
    ]
    assert install_calls, (
        f"`uv tool install --reinstall …` was not invoked; "
        f"observed argvs: {install_argv_seen}"
    )
    # The git URL trailer must reference CLI_PIN[0].
    final_arg = install_calls[0][-1]
    assert final_arg.startswith("git+"), (
        f"unexpected final argv element: {final_arg!r}"
    )
    assert final_arg.endswith(f"@{server.CLI_PIN[0]}"), (
        f"install URL does not pin CLI_PIN[0] ({server.CLI_PIN[0]!r}); "
        f"final arg: {final_arg!r}"
    )

    # Assertion 3: sentinel ``install-failed.*`` exists under XDG_STATE_HOME.
    state_dir = tmp_path / "cortex-command"
    sentinels = list(state_dir.glob("install-failed.*"))
    assert sentinels, (
        f"no install-failed.* sentinel under {state_dir} after simulated "
        f"install failure; dir contents: {list(state_dir.iterdir())}"
    )

    # ------------------------------------------------------------------
    # Phase 2: a second invocation within the 60s window must raise
    # without re-attempting ``uv tool install``. We patch with a fresh
    # mock so any new call would be visible.
    # ------------------------------------------------------------------
    fresh_run = MagicMock()  # raises AttributeError if called with no spec
    fresh_run.return_value = _success_completed("")
    with patch.object(server, "shutil") as mock_shutil_phase2, patch.object(
        server.subprocess, "run", fresh_run
    ):
        mock_shutil_phase2.which = MagicMock(return_value=None)
        with pytest.raises(server.CortexInstallFailed):
            server._ensure_cortex_installed()

    # Assertion 4: no fresh ``uv tool install`` invocation in phase 2.
    fresh_install_calls = [
        c for c in fresh_run.call_args_list
        if isinstance(c.args[0], list)
        and c.args[0][: len(expected_install_prefix)]
        == expected_install_prefix
    ]
    assert not fresh_install_calls, (
        f"second _ensure_cortex_installed() call within 60s re-attempted "
        f"`uv tool install`; calls: {fresh_run.call_args_list}"
    )

    # ------------------------------------------------------------------
    # Phase 3: success path — verify post-install verification calls
    # ``cortex --print-root --format json``. Use a brand-new XDG_STATE_HOME
    # so the prior sentinel does not short-circuit this phase.
    # ------------------------------------------------------------------
    fresh_state_home = tmp_path / "phase3"
    fresh_state_home.mkdir()
    monkeypatch.setenv("XDG_STATE_HOME", str(fresh_state_home))
    monkeypatch.setenv("HOME", str(fresh_state_home))

    # R15 (T11): post-install verification now invokes ``cortex`` via the
    # absolute path resolved by ``uv tool list --show-paths`` (NOT bare
    # PATH). The mock ``uv tool list --show-paths`` stdout uses the line
    # format ``- cortex (/abs/path)`` consumed by
    # ``_resolve_installed_cortex_path()``.
    mock_cortex_abs_path = "/tmp/uv-tools/cortex/bin/cortex"
    success_outputs = [
        # Call 1: uv tool install --reinstall git+...@v0.1.0 — succeeds.
        _success_completed("installed cortex-command vX.Y.Z"),
        # Call 2: uv tool list --show-paths — succeeds and emits the
        # ``- cortex (<abs path>)`` line parsed by
        # ``_resolve_installed_cortex_path()``.
        _success_completed(
            "cortex-command v0.1.0\n"
            f"- cortex ({mock_cortex_abs_path})\n"
        ),
        # Call 3: <abs path> --print-root --format json — succeeds with
        # v1.1 JSON envelope.
        _success_completed(_print_root_success_stdout()),
    ]
    success_run = MagicMock(side_effect=success_outputs)
    with patch.object(server, "shutil") as mock_shutil_phase3, patch.object(
        server.subprocess, "run", success_run
    ):
        mock_shutil_phase3.which = MagicMock(return_value=None)
        server._ensure_cortex_installed()  # must not raise

    # Assertion 1 (success path): install argv shape matches.
    success_argvs = [c.args[0] for c in success_run.call_args_list]
    assert (
        success_argvs[0][: len(expected_install_prefix)]
        == expected_install_prefix
    ), f"phase-3 first call was not `uv tool install --reinstall`: {success_argvs[0]!r}"
    assert success_argvs[0][-1].endswith(f"@{server.CLI_PIN[0]}"), (
        f"phase-3 install URL does not pin CLI_PIN[0]: {success_argvs[0]!r}"
    )

    # Assertion 2a (success path, R15): ``uv tool list --show-paths`` is
    # invoked between the install and the verification probe to resolve
    # the absolute cortex path.
    expected_resolve_argv = ["uv", "tool", "list", "--show-paths"]
    assert success_argvs[1] == expected_resolve_argv, (
        f"phase-3 second call was not `uv tool list --show-paths`: "
        f"{success_argvs[1]!r}"
    )

    # Assertion 2b (success path, R15): post-install verification call
    # uses the *absolute* path resolved from ``uv tool list
    # --show-paths`` (NOT bare ``cortex`` on PATH).
    expected_verify_argv = [
        mock_cortex_abs_path,
        "--print-root",
        "--format",
        "json",
    ]
    assert success_argvs[2] == expected_verify_argv, (
        f"phase-3 third call was not `<abs path> --print-root --format "
        f"json`: {success_argvs[2]!r}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
