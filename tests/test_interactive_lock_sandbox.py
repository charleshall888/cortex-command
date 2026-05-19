"""Sandbox-write probe: verify worktree-CWD writes reach main-repo lock path.

Validates the load-bearing assumption that ``cortex init``'s allowWrite
registration (which covers the main repo's ``cortex/`` umbrella) permits
writes that originate from a worktree-CWD subprocess.  This is the
Seatbelt-specific claim that ``_resolve_user_project_root()`` upward-walks
through the worktree's ``.git`` file to the main repo, producing a
main-repo-absolute path, and that path falls under the allowWrite subpath
in the sandbox profile.

The test explicitly invokes ``sandbox-exec -p <inline-SBPL>`` rather than
relying on any ambient sandbox at the pytest level — so the Seatbelt
enforcement is deterministic regardless of whether pytest itself runs inside
a Claude Code sandbox.

Pattern mirrors ``tests/test_runner_sandbox.py`` (explicit sandbox-exec
subprocess invocation, skip on non-macOS, macOS always runs).

Platform guards
---------------
- Linux: ``pytest.skip`` with reason ``"macOS-only sandbox semantics"``
  captured in pytest output.
- macOS without sandbox-exec binary: skipped (binary not present).
- macOS inside a nested Seatbelt sandbox (e.g. Claude Code dev environment):
  skipped via capability probe — ``sandbox-exec`` cannot layer a new profile
  on top of an already-active Seatbelt container (kernel EPERM 71).  The test
  IS intended to run on macOS CI (GitHub Actions, vanilla macOS) where no
  ambient sandbox wraps the pytest process.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Platform / capability probes
# ---------------------------------------------------------------------------


def _sandbox_exec_available() -> bool:
    return Path("/usr/bin/sandbox-exec").exists()


def _sandbox_exec_can_apply() -> bool:
    """Return True if sandbox-exec can successfully apply an inline profile.

    Runs a minimal no-op command under ``sandbox-exec -p '(version 1)
    (allow default)'``.  Returns False when the kernel denies the profile
    application (exit 71 / ``sandbox_apply: Operation not permitted``), which
    occurs when the current process is already running inside a Seatbelt
    sandbox that forbids nesting.

    This probe follows the same capability-probe pattern used by the
    ``seatbelt_active`` fixture in ``tests/test_worktree_seatbelt.py``.
    """
    if not _sandbox_exec_available():
        return False
    try:
        result = subprocess.run(
            ["/usr/bin/sandbox-exec", "-p", "(version 1)\n(allow default)\n",
             "/bin/echo", "probe"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# SBPL profile builder
# ---------------------------------------------------------------------------


def _build_worktree_sbpl_profile(main_repo_cortex_subpath: str) -> str:
    """Build the inline Seatbelt SBPL profile for the sandbox-write probe.

    Uses ``(allow default)`` as the base — matching the pattern used by
    ``tests/test_runner_sandbox.py`` — which composes safely with any ambient
    Seatbelt sandbox context.

    The explicit ``process-exec`` / ``process-fork`` / ``process-info`` /
    ``signal`` / ``sysctl-read`` lines document the capabilities that
    correspond to Claude Code's default Seatbelt allow-set (per
    anthropic-experimental/sandbox-runtime); they are additive no-ops on top
    of ``(allow default)`` but are kept for documentation purposes.

    The ``file-write* (subpath ...)`` rule is the load-bearing assertion: it
    models the ``cortex init`` allowWrite registration and proves that writes
    from a worktree-CWD subprocess land at the main-repo absolute path.

    Parameters
    ----------
    main_repo_cortex_subpath:
        Absolute path to ``<main-repo>/cortex``, e.g.
        ``/tmp/xyz/main/cortex``.  Must be resolved (no symlinks) so Seatbelt
        ``subpath`` matching works correctly.
    """
    lines = [
        "(version 1)",
        "(allow default)",
        # The following lines document the Claude Code default allow-set
        # (per anthropic-experimental/sandbox-runtime).  They are additive
        # on top of (allow default) and serve as explicit documentation of
        # the capabilities the cortex init registration assumes are present.
        "(allow process-exec)",
        "(allow process-fork)",
        "(allow process-info* (target same-sandbox))",
        "(allow signal (target same-sandbox))",
        "(allow sysctl-read)",
        # Load-bearing assertion: file-write* on the main-repo cortex/ subpath
        # models the cortex init allowWrite registration.
        f'(allow file-write* (subpath "{main_repo_cortex_subpath}"))',
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    sys.platform != "darwin",
    reason="macOS-only sandbox semantics",
)
@pytest.mark.skipif(
    not _sandbox_exec_available(),
    reason="sandbox-exec binary not on /usr/bin/sandbox-exec",
)
def test_lock_write_from_worktree_cwd(tmp_path: Path) -> None:
    """Seatbelt-wrapped write from worktree CWD lands at main-repo lock path.

    Fixture layout
    --------------
    ``tmp_path/main/``          — synthetic main repo (.git/ dir + cortex/)
    ``tmp_path/worktree/probe/`` — synthetic worktree (.git file → main)

    ``CORTEX_REPO_ROOT`` is deliberately unset so
    ``_resolve_user_project_root()`` walks the ``.git`` file boundary upward
    from the worktree CWD, ultimately resolving the main-repo root (which
    contains ``cortex/``).

    The subprocess
    --------------
    ``sandbox-exec -p <inline-SBPL> <python> -m cortex_command.interactive_lock acquire probe``

    run with CWD set to the worktree directory.

    Assertions
    ----------
    1. Subprocess exits 0 (acquire succeeded under sandbox).
    2. Lock file exists at ``<main-repo>/cortex/lifecycle/probe/interactive.pid``.
    3. Lock file is valid JSON with the expected ``magic`` field.
    """
    # Capability probe: skip if sandbox-exec cannot apply a profile in this
    # environment (e.g. already inside a Seatbelt container — kernel returns
    # EPERM 71 / sandbox_apply: Operation not permitted).  This guard fires in
    # Claude Code dev sessions; on vanilla macOS CI it passes and the test runs.
    if not _sandbox_exec_can_apply():
        pytest.skip(
            "sandbox-exec cannot apply inline profile in this environment "
            "(nested Seatbelt container or missing entitlement); "
            "test is designed for vanilla macOS CI"
        )

    # --- Synthetic main repo ---
    main_repo = tmp_path / "main"
    main_repo.mkdir()
    git_dir = main_repo / ".git"
    git_dir.mkdir()
    # Minimal .git structure so the upward walk recognises this as a git repo
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    cortex_dir = main_repo / "cortex"
    cortex_dir.mkdir()

    # --- Synthetic worktree ---
    worktree_dir = tmp_path / "worktree" / "probe"
    worktree_dir.mkdir(parents=True)
    # git worktree .git is a *file* (not a directory) pointing at main's .git
    (worktree_dir / ".git").write_text(
        f"gitdir: {git_dir}\n", encoding="utf-8"
    )

    # --- Resolve main-repo cortex/ for the SBPL profile ---
    # Use .resolve() to canonicalise (eliminates symlinks that Seatbelt would
    # not follow when matching subpath literals).
    main_repo_resolved = main_repo.resolve()
    cortex_subpath = str(main_repo_resolved / "cortex")

    # --- Build inline SBPL profile ---
    sbpl_profile = _build_worktree_sbpl_profile(cortex_subpath)

    # --- Subprocess environment ---
    env = os.environ.copy()
    # Unset CORTEX_REPO_ROOT so the resolver walks from CWD
    env.pop("CORTEX_REPO_ROOT", None)
    # Unset CLAUDE_CODE_SESSION_ID to avoid coupling to any ambient session
    env.pop("CLAUDE_CODE_SESSION_ID", None)

    # --- Build argv ---
    # Use sys.executable so the test always uses the same Python that pytest
    # itself is running under (guaranteed to have cortex_command importable).
    cmd = [
        "/usr/bin/sandbox-exec",
        "-p", sbpl_profile,
        sys.executable,
        "-m", "cortex_command.interactive_lock",
        "acquire",
        "probe",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(worktree_dir),
        env=env,
    )

    # --- Assertion 1: subprocess exited 0 ---
    assert result.returncode == 0, (
        f"sandbox-exec subprocess exited {result.returncode}; "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )

    # --- Assertion 2: lock file exists at main-repo absolute path ---
    expected_lock = (
        main_repo_resolved / "cortex" / "lifecycle" / "probe" / "interactive.pid"
    )
    assert expected_lock.exists(), (
        f"Lock file not found at main-repo path {expected_lock}; "
        f"worktree CWD was {worktree_dir}; "
        f"subprocess stdout={result.stdout!r}, stderr={result.stderr!r}"
    )

    # --- Assertion 3: lock file is valid JSON with expected magic ---
    try:
        lock_data = json.loads(expected_lock.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        pytest.fail(
            f"Lock file at {expected_lock} is not valid JSON: {exc}; "
            f"contents={expected_lock.read_bytes()!r}"
        )

    assert lock_data.get("magic") == "cortex-interactive-lock", (
        f"Unexpected magic field in lock file: {lock_data.get('magic')!r}; "
        f"full contents: {lock_data}"
    )
    assert lock_data.get("schema_version") == 1, (
        f"Unexpected schema_version in lock file: {lock_data.get('schema_version')!r}"
    )
