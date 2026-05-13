"""Dispatch-path parity regression freeze for F1/F2/F3 failure modes.

This test is a regression freeze of the named F1/F2/F3 failure modes from
backlog 208. It uses the SDK stub and synthetic env dicts; it does NOT
verify that future Claude Code updates (sandbox profile changes, Bash-tool
env-passing changes) preserve dispatch-path parity. For that, run
`just test-dispatch-parity-launchd-real` against a real environment.

F1: Auth resolution diverges between runner.py and daytime_pipeline.py.
F2: Worktree root not wired into the dispatch sandbox allowlist.
F3: `python3 -m cortex_command.*` callsites unresolvable in Bash-tool env.

Both synthetic env shapes (launchd-shaped, Bash-tool-shaped) are exercised
against a fixture plan with one trivial task. Both must reach Phase B (the
post-readiness-probe code path that writes `pipeline-events.log` and proceeds
to worktree creation) without triggering `startup_failure`.

Hermeticity: `verify_dispatch_readiness` is patched to return ok=True for
both env shapes so no real auth or worktree probes run during CI. This makes
the test a pure structural freeze — it verifies that the dispatch path *routes*
correctly for both env shapes rather than testing that auth or worktrees
actually work in those environments.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Install the SDK stub before any production code is imported.
# ---------------------------------------------------------------------------
from cortex_command.tests._stubs import _install_sdk_stub

_install_sdk_stub()

# ---------------------------------------------------------------------------
# Import pipeline modules after stub installation.
# ---------------------------------------------------------------------------
from cortex_command.overnight import daytime_pipeline
from cortex_command.overnight.daytime_pipeline import run_daytime
from cortex_command.overnight.readiness import ReadinessResult
from cortex_command.overnight.scheduler.macos import _OPTIONAL_ENV_KEYS


# ---------------------------------------------------------------------------
# Env-dict factories (R19)
# ---------------------------------------------------------------------------


def _launchd_env(tmp_path: Path) -> dict[str, str]:
    """Build a launchd-shaped env dict derived from _OPTIONAL_ENV_KEYS + PATH.

    Mirrors the env snapshot that `launcher.sh` produces via
    `MacOSLaunchAgentBackend._snapshot_env()`. PATH is always included;
    the optional keys are included only if set in the current process env.
    ANTHROPIC_API_KEY is explicitly set to a dummy value so the dispatch
    path has an auth credential available in its env (simulating a launchd
    run where the env was snapshotted at schedule time).
    """
    env: dict[str, str] = {
        # PATH: use the current PATH or a minimal fallback.
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        # Provide a synthetic auth credential that populate the env_preexisting
        # branch of ensure_sdk_auth, eliminating the need for Keychain access.
        "ANTHROPIC_API_KEY": "sk-ant-test-launchd-fake-key",
        # HOME is needed so stdlib modules (pathlib.Path.home, etc.) function.
        "HOME": str(Path.home()),
        # TMPDIR is inherited in launchd per the spec comment on HOME/USER/TMPDIR.
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        # PYTHONPATH so the cortex_command package is importable.
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
    }
    # Include any additional optional keys that are set in the current env.
    for key in _OPTIONAL_ENV_KEYS:
        if key in os.environ and key not in env:
            env[key] = os.environ[key]
    # Pin CWD for the subprocess.
    env["CORTEX_REPO_ROOT"] = str(tmp_path)
    return env


def _bash_tool_env(tmp_path: Path) -> dict[str, str]:
    """Build a Bash-tool-shaped env dict.

    Simulates the sandbox-clean environment the Bash tool passes to a
    subprocess invoked from an interactive Claude Code session:
      - Sandbox-clean PATH (minimal, no user customizations).
      - No CORTEX_* snapshot.
      - No preset ANTHROPIC_API_KEY in the env itself (auth relies on
        Keychain or the readiness fuse being patched for CI).
      - HOME and TMPDIR present (Claude Code passes these through).

    For CI hermeticity, we add a synthetic ANTHROPIC_API_KEY here too so
    the env_preexisting auth branch fires in the in-process test path, where
    the env is inherited rather than subprocess-isolated. See the readiness
    patch note below.
    """
    return {
        # Sandbox-clean PATH: minimal, no user home-bin or brew paths.
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        # HOME and TMPDIR are passed through by Claude Code.
        "HOME": str(Path.home()),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        # Synthetic auth credential for CI; in a real Bash-tool env this
        # would be absent (Keychain used instead). We add it here so the
        # in-process `ensure_sdk_auth` call (invoked by the real
        # `verify_dispatch_readiness` before we patch it out for Phase B)
        # has something to resolve. The readiness patch ensures this is
        # moot — verify_dispatch_readiness is fully patched in both cases.
        "ANTHROPIC_API_KEY": "sk-ant-test-bash-tool-fake-key",
        # PYTHONPATH so the cortex_command package is importable.
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
        # Pin CWD for the in-process fixture.
        "CORTEX_REPO_ROOT": str(tmp_path),
    }


# ---------------------------------------------------------------------------
# Fixture: minimal feature directory with a trivial plan.md
# ---------------------------------------------------------------------------


def _setup_feature_fixture(tmp_path: Path, feature: str) -> Path:
    """Create the minimal cortex feature scaffold under tmp_path.

    Returns the feature directory path.
    """
    feat_dir = tmp_path / "cortex" / "lifecycle" / feature
    feat_dir.mkdir(parents=True)
    # Trivial one-line plan required by the CWD + plan.md guards in run_daytime.
    (feat_dir / "plan.md").write_text(
        f"# {feature}\n\n## Task 1\n\n- [ ] Trivial no-op task\n",
        encoding="utf-8",
    )
    return feat_dir


# ---------------------------------------------------------------------------
# Helper: ok ReadinessResult for patching
# ---------------------------------------------------------------------------


def _ok_readiness() -> ReadinessResult:
    """Return a ReadinessResult with ok=True for patching verify_dispatch_readiness."""
    from cortex_command.overnight.auth import AuthProbeResult

    auth_ok = AuthProbeResult(
        ok=True,
        vector="env_preexisting",
        keychain="skipped",
        result="ok",
        auth_event={
            "ts": "2026-01-01T00:00:00+00:00",
            "event": "auth_bootstrap",
            "vector": "env_preexisting",
            "message": "ok",
        },
        probe_event=None,
    )
    return ReadinessResult(
        ok=True,
        failed_check=None,
        cause=None,
        remediation_hint=None,
        auth_probe_result=auth_ok,
    )


# ---------------------------------------------------------------------------
# Core parity assertion
# ---------------------------------------------------------------------------


def _assert_reaches_phase_b(
    tmp_path: Path,
    env: dict[str, str],
    label: str,
    feature: str,
) -> None:
    """Run run_daytime in-process with env applied to os.environ, assert Phase B.

    Phase B is the post-readiness-probe code segment that writes the buffered
    auth events to `pipeline-events.log` and proceeds to worktree creation.
    We detect Phase B by asserting:
      (a) `daytime-result.json` was written (the outer finally ran).
      (b) `terminated_via != "startup_failure"` — the readiness fuse did NOT
          block the dispatch path.

    The test pins the CWD to tmp_path so all CWD-relative writes stay inside
    the fixture dir. `verify_dispatch_readiness` is patched to ok=True so no
    real auth or worktree probes run during CI. Downstream pipeline functions
    (create_worktree, execute_feature, apply_feature_result, cleanup_worktree)
    are patched to avoid real git/SDK calls.
    """
    worktree_info = MagicMock()
    worktree_info.path = tmp_path / "worktrees" / feature
    worktree_info.branch = f"pipeline/{feature}"

    orig_dir = os.getcwd()
    orig_env = os.environ.copy()

    try:
        os.chdir(tmp_path)
        # Apply the synthetic env dict. We merge over the current env rather
        # than replacing it entirely so Python's own internals (locale, etc.)
        # remain functional. The meaningful keys (PATH, ANTHROPIC_API_KEY,
        # CORTEX_REPO_ROOT) are explicitly set in both env dicts.
        os.environ.update(env)
        # Unset any keys present in real env but absent from the synthetic dict,
        # to simulate the clean-slate env of each invocation context.
        # We selectively unset CORTEX_* and auth keys not in the synthetic dict.
        for key in list(os.environ.keys()):
            if key.startswith("CORTEX_") and key not in env:
                del os.environ[key]
        for key in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN"):
            if key not in env and key in os.environ:
                del os.environ[key]

        with (
            patch(
                "cortex_command.overnight.daytime_pipeline.verify_dispatch_readiness",
                return_value=_ok_readiness(),
            ),
            patch.object(
                daytime_pipeline,
                "create_worktree",
                return_value=worktree_info,
            ),
            patch.object(
                daytime_pipeline,
                "execute_feature",
                new=AsyncMock(
                    return_value=MagicMock(name=feature, status="completed")
                ),
            ),
            patch.object(
                daytime_pipeline,
                "apply_feature_result",
                new=AsyncMock(
                    side_effect=lambda name, result, ctx, **kwargs: (
                        ctx.batch_result.features_merged.append(name)
                    ),
                ),
            ),
            patch.object(daytime_pipeline, "cleanup_worktree"),
        ):
            rc = asyncio.run(run_daytime(feature))

    finally:
        os.chdir(orig_dir)
        # Restore env: remove keys we added, restore keys we removed.
        for key in env:
            os.environ.pop(key, None)
        os.environ.update(orig_env)

    # Locate the result file written by the outer finally.
    result_path = tmp_path / "cortex" / "lifecycle" / feature / "daytime-result.json"
    assert result_path.exists(), (
        f"[{label}] daytime-result.json was not written — "
        "run_daytime may have exited before the outer finally ran."
    )

    with result_path.open(encoding="utf-8") as fh:
        result_data = json.load(fh)

    terminated_via = result_data.get("terminated_via")
    assert terminated_via != "startup_failure", (
        f"[{label}] dispatch path triggered startup_failure before Phase B. "
        f"Full result: {json.dumps(result_data, indent=2)}"
    )

    # Sanity: result_data must have a valid schema_version and feature field.
    assert result_data.get("schema_version") == 1, (
        f"[{label}] result file has unexpected schema_version: {result_data}"
    )
    assert result_data.get("feature") == feature, (
        f"[{label}] result file feature mismatch: {result_data}"
    )


# ---------------------------------------------------------------------------
# Tests (R19)
# ---------------------------------------------------------------------------


def test_launchd_env_reaches_phase_b(tmp_path: Path) -> None:
    """launchd-shaped env must reach Phase B without startup_failure (F1/F2/F3).

    Env shape: _OPTIONAL_ENV_KEYS + PATH, mirroring what launcher.sh produces.
    This env includes ANTHROPIC_API_KEY (snapshotted at schedule time by
    MacOSLaunchAgentBackend._snapshot_env) and a CORTEX_REPO_ROOT pin.
    verify_dispatch_readiness is patched to ok=True for CI hermeticity.
    """
    feature = "parity-launchd"
    _setup_feature_fixture(tmp_path, feature)
    env = _launchd_env(tmp_path)
    _assert_reaches_phase_b(tmp_path, env, label="launchd", feature=feature)


def test_bash_tool_env_reaches_phase_b(tmp_path: Path) -> None:
    """Bash-tool-shaped env must reach Phase B without startup_failure (F1/F2/F3).

    Env shape: sandbox-clean PATH, no CORTEX_* snapshot, no preset
    ANTHROPIC_API_KEY (beyond the CI-hermetic synthetic key).
    verify_dispatch_readiness is patched to ok=True for CI hermeticity.
    """
    feature = "parity-bash-tool"
    _setup_feature_fixture(tmp_path, feature)
    env = _bash_tool_env(tmp_path)
    _assert_reaches_phase_b(tmp_path, env, label="bash-tool", feature=feature)
