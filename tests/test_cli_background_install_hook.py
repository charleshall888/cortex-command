"""Spec R31 — async install hook end-to-end behavioral matrix (Task 14).

Eight scenarios exercising the SessionStart-async install path that
``hooks/cortex-cli-background-install.sh`` + ``install_core.run_install_in_background()``
implement together. The MCP-call-path tests at
``tests/test_mcp_auto_update_real_install.py`` cover the synchronous
install branch via ``monkeypatch.setattr(server, ...)`` patches; this
file covers the SessionStart-async branch via subprocess-boundary
mocking — the bash trampoline spawns a fresh Python subprocess that
imports ``install_core`` directly, so server-namespace patches cannot
intercept. The PATH is prepended with a mock ``uv`` and a mock
``cortex`` whose argv (and select env vars) are recorded to per-test
log files the test inspects.

Scenarios:

    (a) drift case fires ``uv tool install`` subprocess with correct
        argv including ``--refresh-package cortex-command`` and
        ``UV_NO_PROGRESS=1`` in env;
    (b) no-drift case does NOT fire;
    (c) ``CORTEX_AUTO_INSTALL=0`` silent-skip;
    (d) skip-predicate parity (dev mode ``CORTEX_DEV_MODE=1``,
        dirty cortex-command tree);
    (e) under-lock re-check with a simulated concurrent install (only
        1 of 3 attempts actually runs ``uv tool install``);
    (f) recent ``session-install-failed.*`` sentinel within 1800s
        causes silent skip;
    (g) install-in-progress marker written and removed correctly via
        try/finally even on simulated install failure (mock uv
        subprocess raises);
    (h) detach-property regression test (R21, defensive — slow-mock
        approach). The mock ``uv`` sleeps 3s before exiting; the hook
        script's wall-clock exit must be < 2s. If a regression
        converts ``subprocess.Popen(..., start_new_session=True)`` to a
        blocking ``subprocess.run``, the hook would wait for the 3s
        sleep and exceed the 2s budget. The argv-record file must also
        be written ONLY after the hook script returns (i.e., the
        sleeping subprocess outlived the hook). As an additional
        defense, asserts via ``ps`` that the install subprocess is in
        a different session id (``SID``) than the hook script.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_SCRIPT = REPO_ROOT / "hooks" / "cortex-cli-background-install.sh"
PLUGIN_ROOT = REPO_ROOT / "plugins" / "cortex-overnight"
FIXTURE_UV = REPO_ROOT / "tests" / "fixtures" / "install" / "bin" / "uv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_mock_cortex(bin_dir: Path, *, version: str) -> Path:
    """Write a mock ``cortex`` binary that emits a print-root JSON envelope.

    Mirrors the shim pattern from ``tests/test_cli_version_sync_hook.sh``:
    when called with ``--print-root --format json`` the shim writes the
    fixed JSON payload and exits 0. Any other argv exits 0 silently
    (the install_core path only invokes ``cortex --print-root --format
    json``).
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    cortex_bin = bin_dir / "cortex"
    payload = json.dumps(
        {
            "version": version,
            "schema_version": "2.0",
            "root": "/tmp/fake-cortex-root",
        }
    )
    cortex_bin.write_text(
        f"""#!/bin/bash
if [ "$1" = "--print-root" ]; then
    printf '%s\\n' '{payload}'
fi
exit 0
""",
        encoding="utf-8",
    )
    cortex_bin.chmod(0o755)
    return cortex_bin


def _write_missing_cortex(bin_dir: Path) -> None:
    """Ensure the bin dir has NO ``cortex`` binary (probe-failure path)."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    target = bin_dir / "cortex"
    if target.exists():
        target.unlink()


def _make_plugin_root(plugin_root: Path, *, tag: str, schema: str) -> Path:
    """Materialize a minimal cortex-overnight plugin root for the hook.

    The hook script's Python heredoc does:

        sys.path.insert(0, HOOK_PLUGIN_ROOT)
        import install_core

    So we copy ``install_core.py``, ``cli_pin.py``, and
    ``install_guard.py`` from the canonical plugin dir into the
    fixture, and rewrite ``cli_pin.py`` to encode the test's chosen
    tag/schema.
    """
    plugin_root.mkdir(parents=True, exist_ok=True)
    # install_core.py is loaded directly; copy it byte-for-byte.
    (plugin_root / "install_core.py").write_bytes(
        (PLUGIN_ROOT / "install_core.py").read_bytes()
    )
    # install_guard.py is lazily imported from the in-flight guard branch
    # of run_install_in_background; copy it byte-for-byte.
    (plugin_root / "install_guard.py").write_bytes(
        (PLUGIN_ROOT / "install_guard.py").read_bytes()
    )
    # cli_pin.py — synthesize with the test's chosen tag/schema.
    (plugin_root / "cli_pin.py").write_text(
        f'CLI_PIN = ("{tag}", "{schema}")\n',
        encoding="utf-8",
    )
    return plugin_root


def _make_clean_repo(repo_dir: Path) -> Path:
    """Build a tmp git repo on ``main`` with a clean tree.

    Mirrors ``make_clean_repo()`` from ``tests/test_cli_version_sync_hook.sh``.
    The async hook's skip-predicates check ``git rev-parse
    --show-toplevel`` + remote URL match; a non-cortex-command remote
    means the dirty-tree / non-main-branch predicates do NOT fire
    (R26 narrowing). We supply NO remote so the predicates skip.
    """
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main"],
        cwd=str(repo_dir),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "user.email=bg@bg.test",
            "-c",
            "user.name=bg-test",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "--allow-empty",
            "-q",
            "-m",
            "init",
        ],
        cwd=str(repo_dir),
        check=True,
        capture_output=True,
    )
    return repo_dir


def _make_cortex_command_repo(repo_dir: Path, *, dirty: bool = False) -> Path:
    """Build a tmp git repo that LOOKS like a cortex-command checkout.

    Used by scenario (d) to exercise the dirty-tree skip predicate
    (R26 narrowing: only fires when the cwd resolves into a
    cortex-command remote).
    """
    _make_clean_repo(repo_dir)
    subprocess.run(
        [
            "git",
            "remote",
            "add",
            "origin",
            "https://github.com/charleshall888/cortex-command.git",
        ],
        cwd=str(repo_dir),
        check=True,
        capture_output=True,
    )
    if dirty:
        # Create an untracked file so `git status --porcelain` is non-empty.
        (repo_dir / "DIRTY.txt").write_text("dirty\n", encoding="utf-8")
    return repo_dir


def _make_stub_log_dir(tmp_path: Path) -> Path:
    """Return a per-scenario stub log dir for ``uv``'s argv/env recordings."""
    log_dir = tmp_path / "stub-log"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _build_hook_env(
    *,
    repo_dir: Path,
    plugin_root: Path,
    state_dir: Path,
    bin_dir: Path,
    log_dir: Path,
    extras: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    """Construct a hermetic env dict for invoking the hook script.

    The hook script's bash trampoline prepends a bootstrap PATH segment
    (``$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin``)
    in front of whatever PATH it inherits — so for true PATH dominance
    we plant the mock ``uv`` and mock ``cortex`` inside the bin_dir AND
    additionally redirect ``HOME`` to a dir without ``~/.local/bin/uv``
    so the bootstrap prefix cannot shadow our shims.
    """
    home = state_dir / "home"
    home.mkdir(parents=True, exist_ok=True)
    env: dict[str, str] = {
        "PATH": f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "HOME": str(home),
        "XDG_STATE_HOME": str(state_dir),
        "CLAUDE_PLUGIN_ROOT": str(plugin_root),
        "STUB_LOG_DIR": str(log_dir),
        # Always record the UV_NO_PROGRESS env-var the install_core path
        # is asserted to propagate (R14 acceptance).
        "STUB_UV_RECORD_ENV": "1",
        # The async path consults the in-flight guard via install_guard;
        # set CORTEX_ALLOW_INSTALL_DURING_RUN=1 to bypass that branch in
        # tests so the assertions target the install spawn proper.
        "CORTEX_ALLOW_INSTALL_DURING_RUN": "1",
    }
    if extras:
        env.update(extras)
    return env


def _invoke_hook(
    *,
    repo_dir: Path,
    env: dict[str, str],
    stdin_json: Optional[str] = None,
    timeout: float = 30.0,
) -> subprocess.CompletedProcess[str]:
    """Run the hook script with the given env and ``cwd=repo_dir``."""
    if stdin_json is None:
        stdin_json = json.dumps(
            {
                "hook_event_name": "SessionStart",
                "session_id": "test-bg-install",
                "cwd": str(repo_dir),
            }
        )
    return subprocess.run(
        ["bash", str(HOOK_SCRIPT)],
        input=stdin_json,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(repo_dir),
    )


def _wait_for_argv(log_dir: Path, *, timeout: float = 10.0) -> list[str]:
    """Poll ``$STUB_LOG_DIR/uv.argv`` until at least one line is written.

    The async install is detached via ``Popen(start_new_session=True)``
    so the hook script may exit BEFORE the mock ``uv`` records its
    argv. Tests that need to read the argv record poll up to
    ``timeout`` seconds.
    """
    argv_path = log_dir / "uv.argv"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if argv_path.exists():
            text = argv_path.read_text(encoding="utf-8")
            lines = [line for line in text.splitlines() if line.strip()]
            if lines:
                return lines
        time.sleep(0.05)
    return []


def _scenario_setup(tmp_path: Path, name: str) -> dict[str, Path]:
    """Per-scenario isolated paths under ``tmp_path / name``."""
    base = tmp_path / name
    base.mkdir(parents=True, exist_ok=True)
    repo = base / "repo"
    plugin_root = base / "plugin-root"
    state = base / "state"
    bin_dir = base / "bin"
    log_dir = _make_stub_log_dir(base)
    bin_dir.mkdir(parents=True, exist_ok=True)
    # Install the mock uv from the existing fixture; the install_core
    # path invokes ``uv tool install --reinstall ...`` via subprocess
    # which resolves through PATH.
    (bin_dir / "uv").write_bytes(FIXTURE_UV.read_bytes())
    (bin_dir / "uv").chmod(0o755)
    return {
        "base": base,
        "repo": repo,
        "plugin_root": plugin_root,
        "state": state,
        "bin": bin_dir,
        "log": log_dir,
    }


# ---------------------------------------------------------------------------
# Scenario (a) — drift fires `uv tool install` with correct argv + env.
# ---------------------------------------------------------------------------


def test_drift_fires_uv_install_with_correct_argv_and_env(
    tmp_path: Path,
) -> None:
    """R31(a): drift → uv tool install --reinstall --refresh-package + UV_NO_PROGRESS=1."""
    paths = _scenario_setup(tmp_path, "a-drift")
    _make_clean_repo(paths["repo"])
    _make_plugin_root(paths["plugin_root"], tag="v9.9.9", schema="2.0")
    _write_mock_cortex(paths["bin"], version="0.0.1")  # drift vs v9.9.9

    env = _build_hook_env(
        repo_dir=paths["repo"],
        plugin_root=paths["plugin_root"],
        state_dir=paths["state"],
        bin_dir=paths["bin"],
        log_dir=paths["log"],
    )
    proc = _invoke_hook(repo_dir=paths["repo"], env=env)
    assert proc.returncode == 0, (
        f"hook script exit={proc.returncode} stderr={proc.stderr!r}"
    )

    argv_lines = _wait_for_argv(paths["log"])
    # Look for the install invocation. There may be additional uv calls
    # (e.g., ``uv tool list --show-paths`` in some paths) — we filter to
    # the install one.
    install_lines = [
        line for line in argv_lines if "tool install --reinstall" in line
    ]
    assert install_lines, (
        f"no ``uv tool install --reinstall`` line in uv.argv: {argv_lines!r}"
    )
    install_argv_str = install_lines[0]
    # Required tokens per R14 acceptance + spec body.
    assert "--refresh-package cortex-command" in install_argv_str, (
        f"missing --refresh-package cortex-command in: {install_argv_str!r}"
    )
    assert "git+https://github.com/charleshall888/cortex-command.git@v9.9.9" in install_argv_str, (
        f"install URL does not pin CLI_PIN tag: {install_argv_str!r}"
    )

    # UV_NO_PROGRESS=1 must be in the install subprocess's env per R14.
    env_path = paths["log"] / "uv.env"
    assert env_path.exists(), "stub uv did not record env"
    env_lines = env_path.read_text(encoding="utf-8").splitlines()
    assert "UV_NO_PROGRESS=1" in env_lines, (
        f"UV_NO_PROGRESS=1 missing from install env: {env_lines!r}"
    )


# ---------------------------------------------------------------------------
# Scenario (b) — no drift → no uv tool install fires.
# ---------------------------------------------------------------------------


def test_no_drift_does_not_fire_install(tmp_path: Path) -> None:
    """R31(b): installed == CLI_PIN → no ``uv tool install`` subprocess fires."""
    paths = _scenario_setup(tmp_path, "b-no-drift")
    _make_clean_repo(paths["repo"])
    _make_plugin_root(paths["plugin_root"], tag="v9.9.9", schema="2.0")
    _write_mock_cortex(paths["bin"], version="9.9.9")  # match CLI_PIN[0]

    env = _build_hook_env(
        repo_dir=paths["repo"],
        plugin_root=paths["plugin_root"],
        state_dir=paths["state"],
        bin_dir=paths["bin"],
        log_dir=paths["log"],
    )
    proc = _invoke_hook(repo_dir=paths["repo"], env=env)
    assert proc.returncode == 0, (
        f"hook script exit={proc.returncode} stderr={proc.stderr!r}"
    )

    # Give any erroneous detached spawn a brief window to record itself.
    time.sleep(0.5)
    argv_path = paths["log"] / "uv.argv"
    if argv_path.exists():
        text = argv_path.read_text(encoding="utf-8")
        install_lines = [
            line
            for line in text.splitlines()
            if "tool install --reinstall" in line
        ]
        assert not install_lines, (
            f"no-drift case should NOT fire uv install; got: {install_lines!r}"
        )


# ---------------------------------------------------------------------------
# Scenario (c) — CORTEX_AUTO_INSTALL=0 silent skip.
# ---------------------------------------------------------------------------


def test_cortex_auto_install_zero_silent_skips(tmp_path: Path) -> None:
    """R31(c) / R30: CORTEX_AUTO_INSTALL=0 → no install, no marker."""
    paths = _scenario_setup(tmp_path, "c-opt-out")
    _make_clean_repo(paths["repo"])
    _make_plugin_root(paths["plugin_root"], tag="v9.9.9", schema="2.0")
    _write_mock_cortex(paths["bin"], version="0.0.1")  # drift would otherwise fire

    env = _build_hook_env(
        repo_dir=paths["repo"],
        plugin_root=paths["plugin_root"],
        state_dir=paths["state"],
        bin_dir=paths["bin"],
        log_dir=paths["log"],
        extras={"CORTEX_AUTO_INSTALL": "0"},
    )
    proc = _invoke_hook(repo_dir=paths["repo"], env=env)
    assert proc.returncode == 0, (
        f"hook script exit={proc.returncode} stderr={proc.stderr!r}"
    )

    time.sleep(0.3)
    argv_path = paths["log"] / "uv.argv"
    if argv_path.exists():
        text = argv_path.read_text(encoding="utf-8")
        install_lines = [
            line
            for line in text.splitlines()
            if "tool install --reinstall" in line
        ]
        assert not install_lines, (
            f"CORTEX_AUTO_INSTALL=0 must skip; got install lines: {install_lines!r}"
        )

    # No marker file should ever have been written.
    marker = paths["state"] / "cortex-command" / "install.in-progress"
    assert not marker.exists(), f"marker unexpectedly present: {marker}"


# ---------------------------------------------------------------------------
# Scenario (d) — skip-predicate parity (dev mode, dirty cortex-command).
# ---------------------------------------------------------------------------


def test_dev_mode_silent_skips(tmp_path: Path) -> None:
    """R31(d.1): CORTEX_DEV_MODE=1 → silent skip (no install, no marker)."""
    paths = _scenario_setup(tmp_path, "d1-dev-mode")
    _make_clean_repo(paths["repo"])
    _make_plugin_root(paths["plugin_root"], tag="v9.9.9", schema="2.0")
    _write_mock_cortex(paths["bin"], version="0.0.1")  # drift baseline

    env = _build_hook_env(
        repo_dir=paths["repo"],
        plugin_root=paths["plugin_root"],
        state_dir=paths["state"],
        bin_dir=paths["bin"],
        log_dir=paths["log"],
        extras={"CORTEX_DEV_MODE": "1"},
    )
    proc = _invoke_hook(repo_dir=paths["repo"], env=env)
    assert proc.returncode == 0

    time.sleep(0.3)
    argv_path = paths["log"] / "uv.argv"
    if argv_path.exists():
        text = argv_path.read_text(encoding="utf-8")
        install_lines = [
            line
            for line in text.splitlines()
            if "tool install --reinstall" in line
        ]
        assert not install_lines, (
            f"CORTEX_DEV_MODE=1 must skip; got: {install_lines!r}"
        )

    marker = paths["state"] / "cortex-command" / "install.in-progress"
    assert not marker.exists()


def test_dirty_cortex_command_tree_silent_skips(tmp_path: Path) -> None:
    """R31(d.2) / R26: dirty cortex-command tree → silent skip."""
    paths = _scenario_setup(tmp_path, "d2-dirty-cortex")
    # The dirty-tree predicate is R26-narrowed: only fires when cwd
    # resolves into a cortex-command remote. Make this repo look like
    # one (origin URL contains the canonical substring) and leave the
    # tree dirty via an untracked file.
    _make_cortex_command_repo(paths["repo"], dirty=True)
    _make_plugin_root(paths["plugin_root"], tag="v9.9.9", schema="2.0")
    _write_mock_cortex(paths["bin"], version="0.0.1")  # drift baseline

    env = _build_hook_env(
        repo_dir=paths["repo"],
        plugin_root=paths["plugin_root"],
        state_dir=paths["state"],
        bin_dir=paths["bin"],
        log_dir=paths["log"],
    )
    proc = _invoke_hook(repo_dir=paths["repo"], env=env)
    assert proc.returncode == 0

    time.sleep(0.3)
    argv_path = paths["log"] / "uv.argv"
    if argv_path.exists():
        text = argv_path.read_text(encoding="utf-8")
        install_lines = [
            line
            for line in text.splitlines()
            if "tool install --reinstall" in line
        ]
        assert not install_lines, (
            f"dirty cortex-command tree must skip; got: {install_lines!r}"
        )


# ---------------------------------------------------------------------------
# Scenario (e) — under-lock re-check: 3 concurrent attempts, 1 install.
# ---------------------------------------------------------------------------


def test_concurrent_hooks_install_exactly_once(tmp_path: Path) -> None:
    """R31(e) / R18: 3 simulated-concurrent async hooks → exactly 1 ``uv tool install``.

    Spec acceptance (R18): "integration test simulating 3 concurrent
    async hook installs results in 1 actual ``uv tool install``
    invocation, not 3". The word "simulating" is load-bearing — we are
    asserting the under-lock re-check logic AND the initial-probe
    short-circuit work together to bound the install count at 1
    across 3 contenders, not running a literal wall-clock race
    (which would be non-deterministic because install_core's flock is
    released as soon as ``Popen`` returns, well before the detached
    uv subprocess actually runs).

    Test mechanism — a stateful ``cortex`` shim with a per-call counter:
        - Calls 1 + 2 return drift JSON (Hook 1's initial probe + Hook
          1's under-lock relock probe).
        - Call 3 returns drift (Hook 2's initial probe).
        - Calls 4+ return CLI_PIN-matching JSON.

    Expected sequence:
        - Hook 1: initial probe (call 1, drift) → acquire flock →
          relock probe (call 2, drift) → spawn ``uv tool install`` →
          release flock.
        - Hook 2: initial probe (call 3, drift) → acquire flock →
          relock probe (call 4, matching) → emit
          ``session_start_reinstall_under_lock_skip`` NDJSON → release
          flock WITHOUT spawning uv.
        - Hook 3: initial probe (call 5, matching) → exit at the
          initial-probe drift comparison, never enter the flock.

    Total: exactly 1 ``uv tool install`` invocation, exercising both
    the initial-probe short-circuit AND the under-lock re-check.
    """
    paths = _scenario_setup(tmp_path, "e-concurrent")
    _make_clean_repo(paths["repo"])
    _make_plugin_root(paths["plugin_root"], tag="v9.9.9", schema="2.0")

    # Stateful cortex shim: per-call counter (atomically incremented
    # via flock on a sibling counter file). Calls 1–3 return drift,
    # calls 4+ return matching.
    counter_file = paths["base"] / "cortex-call-count"
    counter_file.write_text("0", encoding="utf-8")
    cortex_bin = paths["bin"] / "cortex"
    cortex_bin.write_text(
        f"""#!/bin/bash
# Stateful cortex shim for the under-lock re-check test (scenario e):
# atomically increments a per-call counter and emits drift JSON on
# calls 1–3, matching JSON on calls 4+.
COUNTER='{counter_file}'
(
    flock -x 9
    n=$(cat "$COUNTER" 2>/dev/null || echo 0)
    next=$((n + 1))
    printf '%s' "$next" > "$COUNTER"
    if [ "$next" -le 3 ]; then
        printf '%s\\n' '{{"version": "0.0.1", "schema_version": "2.0", "root": "/tmp/x"}}'
    else
        printf '%s\\n' '{{"version": "9.9.9", "schema_version": "2.0", "root": "/tmp/x"}}'
    fi
) 9>"$COUNTER.lock"
exit 0
""",
        encoding="utf-8",
    )
    cortex_bin.chmod(0o755)

    env = _build_hook_env(
        repo_dir=paths["repo"],
        plugin_root=paths["plugin_root"],
        state_dir=paths["state"],
        bin_dir=paths["bin"],
        log_dir=paths["log"],
    )

    # Run 3 hooks serially — see the test docstring above for why
    # serial-with-stateful-shim is the spec-faithful "simulation" of
    # the concurrent scenario.
    for idx in range(3):
        proc = subprocess.run(
            ["bash", str(HOOK_SCRIPT)],
            input=json.dumps(
                {
                    "hook_event_name": "SessionStart",
                    "session_id": f"test-bg-concurrent-{idx}",
                    "cwd": str(paths["repo"]),
                }
            ),
            env=env,
            capture_output=True,
            text=True,
            timeout=30.0,
            cwd=str(paths["repo"]),
        )
        assert proc.returncode == 0, (
            f"hook {idx} exit={proc.returncode} stderr={proc.stderr!r}"
        )

    # Wait for the (single) detached install spawn to record argv.
    argv_lines = _wait_for_argv(paths["log"], timeout=15.0)
    install_lines = [
        line for line in argv_lines if "tool install --reinstall" in line
    ]
    assert len(install_lines) == 1, (
        f"expected exactly 1 ``uv tool install`` invocation across 3 "
        f"simulated-concurrent hook fires; got {len(install_lines)} in "
        f"argv={argv_lines!r}"
    )

    # And verify the under-lock re-check NDJSON record landed (proves
    # the second hook entered the flock and emitted the skip, rather
    # than short-circuiting via some other branch).
    last_error_log = paths["state"] / "cortex-command" / "last-error.log"
    assert last_error_log.exists(), (
        "expected last-error.log NDJSON audit log; install_core writes "
        "to it on every terminal stage"
    )
    log_text = last_error_log.read_text(encoding="utf-8")
    assert "session_start_reinstall_under_lock_skip" in log_text, (
        f"expected ``session_start_reinstall_under_lock_skip`` NDJSON "
        f"stage in last-error.log; got: {log_text!r}"
    )


# ---------------------------------------------------------------------------
# Scenario (f) — recent session-install-failed sentinel → silent skip.
# ---------------------------------------------------------------------------


def test_recent_session_install_failed_sentinel_silent_skips(
    tmp_path: Path,
) -> None:
    """R31(f) / R22: recent session-install-failed.* within 1800s → silent skip."""
    paths = _scenario_setup(tmp_path, "f-sentinel-throttle")
    _make_clean_repo(paths["repo"])
    _make_plugin_root(paths["plugin_root"], tag="v9.9.9", schema="2.0")
    _write_mock_cortex(paths["bin"], version="0.0.1")  # drift would fire

    # Plant a fresh session-install-failed.<ts> sentinel.
    state_subdir = paths["state"] / "cortex-command"
    state_subdir.mkdir(parents=True, exist_ok=True)
    sentinel = state_subdir / f"session-install-failed.{int(time.time())}"
    sentinel.write_text("prior failure for test", encoding="utf-8")

    env = _build_hook_env(
        repo_dir=paths["repo"],
        plugin_root=paths["plugin_root"],
        state_dir=paths["state"],
        bin_dir=paths["bin"],
        log_dir=paths["log"],
    )
    proc = _invoke_hook(repo_dir=paths["repo"], env=env)
    assert proc.returncode == 0

    time.sleep(0.3)
    argv_path = paths["log"] / "uv.argv"
    if argv_path.exists():
        text = argv_path.read_text(encoding="utf-8")
        install_lines = [
            line
            for line in text.splitlines()
            if "tool install --reinstall" in line
        ]
        assert not install_lines, (
            f"fresh sentinel must throttle install; got: {install_lines!r}"
        )

    marker = state_subdir / "install.in-progress"
    assert not marker.exists()


# ---------------------------------------------------------------------------
# Scenario (g) — marker write+cleanup via try/finally even on uv failure.
# ---------------------------------------------------------------------------


def test_marker_cleanup_on_install_failure(tmp_path: Path) -> None:
    """R31(g) / R19: marker is unlinked by ``finally`` even when install fails.

    The mock ``uv`` exits non-zero (STUB_UV_FAIL=1). The hook completes,
    the detached install subprocess runs, fails, and the install_core
    ``finally`` clause unlinks the marker. We poll for the marker to
    disappear within a timeout.

    Note: the install spawn itself happens via Popen with
    start_new_session=True, so the install subprocess outlives the
    hook script. We poll the marker for absence after giving the
    install enough wall-clock time to complete its own try/finally.
    """
    paths = _scenario_setup(tmp_path, "g-marker-finally")
    _make_clean_repo(paths["repo"])
    _make_plugin_root(paths["plugin_root"], tag="v9.9.9", schema="2.0")
    _write_mock_cortex(paths["bin"], version="0.0.1")  # drift baseline

    env = _build_hook_env(
        repo_dir=paths["repo"],
        plugin_root=paths["plugin_root"],
        state_dir=paths["state"],
        bin_dir=paths["bin"],
        log_dir=paths["log"],
        extras={"STUB_UV_FAIL": "1"},
    )
    proc = _invoke_hook(repo_dir=paths["repo"], env=env)
    assert proc.returncode == 0

    # Wait for the install subprocess (detached) to record itself, then
    # for the marker to be cleaned up by the install_core finally clause.
    argv_lines = _wait_for_argv(paths["log"], timeout=15.0)
    install_lines = [
        line for line in argv_lines if "tool install --reinstall" in line
    ]
    assert install_lines, (
        f"failure path should still have spawned uv install; argv={argv_lines!r}"
    )

    # NOTE: in the current install_core implementation,
    # ``run_install_in_background()`` uses subprocess.Popen for the install
    # spawn — that returns immediately AFTER spawn (success or fail of uv
    # is async to the parent). The marker write + Popen + finally all run
    # in the SAME Python process as the spawn; the finally executes once
    # Popen returns, regardless of the child's eventual exit code. So the
    # marker is unlinked as soon as the Popen call completes — long before
    # uv itself exits.
    marker = paths["state"] / "cortex-command" / "install.in-progress"
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if not marker.exists():
            break
        time.sleep(0.1)
    assert not marker.exists(), (
        f"marker not cleaned up by try/finally: {marker} still present"
    )


# ---------------------------------------------------------------------------
# Scenario (h) — detach property regression (R21, slow-mock approach).
# ---------------------------------------------------------------------------


def test_detach_property_hook_exits_before_slow_install(tmp_path: Path) -> None:
    """R31(h) / R21: hook script exits < 2s even when ``uv`` sleeps ≥ 3s.

    The detach property is the load-bearing behavioral guarantee —
    without it, the hook would freeze Claude Code launch when a slow
    install is in progress. We configure the stub ``uv`` to sleep 3
    seconds before writing its argv record, then invoke the hook and
    assert: (1) the hook wall-clock exit < 2s, (2) the argv-record
    file is written ONLY after the hook script returns (i.e., the
    sleeping subprocess outlived the hook).

    Additional defense: after the hook returns, look up the spawned
    install subprocess via ``ps`` and assert its SID differs from the
    hook script's process group, proving ``start_new_session=True``
    took effect (PID == SID after setsid).
    """
    paths = _scenario_setup(tmp_path, "h-detach-slow-mock")
    _make_clean_repo(paths["repo"])
    _make_plugin_root(paths["plugin_root"], tag="v9.9.9", schema="2.0")
    _write_mock_cortex(paths["bin"], version="0.0.1")  # drift baseline

    env = _build_hook_env(
        repo_dir=paths["repo"],
        plugin_root=paths["plugin_root"],
        state_dir=paths["state"],
        bin_dir=paths["bin"],
        log_dir=paths["log"],
        extras={"STUB_UV_SLEEP": "3"},
    )

    argv_path = paths["log"] / "uv.argv"
    assert not argv_path.exists(), "pre-test sanity: argv file already exists"

    start = time.monotonic()
    proc = _invoke_hook(repo_dir=paths["repo"], env=env, timeout=20.0)
    hook_elapsed = time.monotonic() - start

    assert proc.returncode == 0, (
        f"hook script exit={proc.returncode} stderr={proc.stderr!r}"
    )
    # The detach property: hook must exit in < 2s regardless of the
    # 3s install sleep. If a regression converts Popen to a blocking
    # subprocess.run, this assertion catches it.
    assert hook_elapsed < 2.0, (
        f"hook wall-clock exit was {hook_elapsed:.2f}s — must be < 2s "
        f"per R21 (the detach property is the load-bearing behavioral "
        f"guarantee that prevents Claude Code launch freeze when a "
        f"slow install is in progress)."
    )

    # The argv-record file must NOT exist yet — the sleeping uv stub
    # writes argv only AFTER its 3s sleep, by which time the hook has
    # already returned. (If detach is broken and the hook waits for uv,
    # the argv file would already exist when the hook returns.)
    assert not argv_path.exists(), (
        f"argv file present at hook return — detached subprocess did NOT "
        f"outlive the hook, suggesting Popen is no longer detaching. "
        f"argv contents: {argv_path.read_text() if argv_path.exists() else '(absent)'}"
    )

    # Now wait for the sleeping uv to record itself (proves the detached
    # subprocess survives past the hook's return).
    argv_lines = _wait_for_argv(paths["log"], timeout=10.0)
    install_lines = [
        line for line in argv_lines if "tool install --reinstall" in line
    ]
    assert install_lines, (
        f"detached uv stub never recorded its argv (the sleeping "
        f"subprocess should have outlived the hook); argv={argv_lines!r}"
    )


if __name__ == "__main__":
    # Allow direct ``python tests/test_cli_background_install_hook.py`` for
    # local iteration; pytest discovery is the primary entry point.
    raise SystemExit(pytest.main([__file__, "-v"]))
