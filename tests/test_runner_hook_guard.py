"""Runner-startup hook-guard verification tests (lifecycle ticket 128, Req 4).

Covers the four behavior arms of the ``cortex overnight start`` hook
verification gate:

  (a) ``overnight_hook_required: true`` + hook missing →
      ``_verify_hook_guard`` returns an error string containing the
      ``"hook guard not installed"`` substring.
  (b) ``overnight_hook_required: true`` + hook present, executable, with
      the Phase 0 sentinel string → returns ``None``.
  (c) ``overnight_hook_required`` absent / false → returns ``None``
      (verification skipped).
  (d) End-to-end ``handle_start`` integration: ``overnight_hook_required:
      true`` + hook missing + invocation through ``handle_start`` →
      returns ``1`` with ``"hook guard not installed"`` on stderr, AND
      ``runner_module.run`` is NOT invoked.

Case (d) closes the verification gap where Task 3's grep-only check
cannot distinguish a live call from a dead one.

Test scaffolding follows the ``_git`` + ``_init_repo`` helper pattern
from ``tests/test_runner_followup_commit.py:40-60``.
"""

from __future__ import annotations

import argparse
import stat
import subprocess
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers (mirrors tests/test_runner_followup_commit.py:40-60)
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git",
         "-c", "user.email=t@t",
         "-c", "user.name=T",
         "-c", "commit.gpgsign=false",
         *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
    )


def _init_repo(path: Path) -> str:
    """Initialize a git repo and return the default branch name."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init")
    # Bake identity into local config so subsequent git commits inside the
    # repo (without -c flags) still succeed.
    _git(path, "config", "user.email", "t@t")
    _git(path, "config", "user.name", "T")
    _git(path, "config", "commit.gpgsign", "false")
    _git(path, "commit", "--allow-empty", "-m", "init")
    rev = _git(path, "rev-parse", "--abbrev-ref", "HEAD")
    return rev.stdout.strip()


def _write_lifecycle_config(repo: Path, *, required: bool | None) -> None:
    """Write ``lifecycle.config.md`` with ``overnight_hook_required`` set.

    ``required=True`` writes the field as ``true``; ``required=False``
    writes it as ``false``; ``required=None`` omits the field entirely
    (case (c) skip path).
    """
    if required is None:
        body = "---\n# no overnight_hook_required field\n---\n"
    else:
        body = (
            "---\n"
            f"overnight_hook_required: {'true' if required else 'false'}\n"
            "---\n"
        )
    (repo / "lifecycle.config.md").write_text(body, encoding="utf-8")


def _install_phase0_hook(repo: Path) -> Path:
    """Install a minimal pre-commit hook with the Phase 0 sentinel.

    Creates ``.githooks/pre-commit`` containing the sentinel string
    ``Phase 0 — overnight main-branch guard``, marks it executable, and
    sets ``core.hooksPath = .githooks`` in the repo's local config.
    Returns the hook file path.
    """
    hooks_dir = repo / ".githooks"
    hooks_dir.mkdir(exist_ok=True)
    pre_commit = hooks_dir / "pre-commit"
    pre_commit.write_text(
        "#!/bin/bash\n"
        "# Phase 0 — overnight main-branch guard\n"
        "exit 0\n"
    )
    pre_commit.chmod(pre_commit.stat().st_mode | stat.S_IEXEC)
    _git(repo, "config", "core.hooksPath", str(hooks_dir))
    return pre_commit


# ---------------------------------------------------------------------------
# (a) field=true + hook missing → returns error string with substring
# ---------------------------------------------------------------------------


def test_verify_hook_guard_field_true_hook_missing_returns_error(tmp_path: Path):
    """Field ``true`` + no hook installed → error string returned."""
    from cortex_command.overnight.cli_handler import _verify_hook_guard

    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_lifecycle_config(repo, required=True)
    # No hook installed: core.hooksPath unset, no .githooks dir.

    result = _verify_hook_guard(repo)

    assert result is not None, (
        "expected error string when overnight_hook_required=true and hook missing; "
        "got None"
    )
    assert "hook guard not installed" in result, (
        f"expected 'hook guard not installed' substring in error; got: {result!r}"
    )


# ---------------------------------------------------------------------------
# (b) field=true + hook present and correct → returns None
# ---------------------------------------------------------------------------


def test_verify_hook_guard_field_true_hook_present_returns_none(tmp_path: Path):
    """Field ``true`` + hook installed with sentinel → returns ``None``."""
    from cortex_command.overnight.cli_handler import _verify_hook_guard

    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_lifecycle_config(repo, required=True)
    _install_phase0_hook(repo)

    result = _verify_hook_guard(repo)

    assert result is None, (
        f"expected None when hook is properly installed; got: {result!r}"
    )


# ---------------------------------------------------------------------------
# (c) field absent/false → returns None (skipped)
# ---------------------------------------------------------------------------


def test_verify_hook_guard_field_absent_returns_none(tmp_path: Path):
    """Field absent in lifecycle.config.md → verification skipped."""
    from cortex_command.overnight.cli_handler import _verify_hook_guard

    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_lifecycle_config(repo, required=None)
    # Hook intentionally NOT installed — verification must skip regardless.

    result = _verify_hook_guard(repo)

    assert result is None, (
        f"expected None when overnight_hook_required field is absent; "
        f"got: {result!r}"
    )


# ---------------------------------------------------------------------------
# (d) end-to-end handle_start integration: gate trips, runner.run NOT called
# ---------------------------------------------------------------------------


def test_handle_start_hook_missing_refuses_and_does_not_invoke_runner(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    """End-to-end: ``handle_start`` returns 1, stderr names the failure,
    and ``runner_module.run`` is NEVER invoked.

    Closes the verification gap where Task 3's grep-only check cannot
    distinguish live wiring from dead code: this test exercises the
    actual ``handle_start`` call path and asserts the mocked
    ``runner_module.run`` was never invoked.
    """
    from cortex_command.overnight import cli_handler

    repo = tmp_path / "repo"
    _init_repo(repo)
    _write_lifecycle_config(repo, required=True)
    # No hook installed — gate must trip.

    # Minimum state file so ``handle_start``'s state-existence check
    # doesn't short-circuit before reaching the hook-guard call.
    session_dir = repo / "lifecycle" / "sessions" / "overnight-test"
    session_dir.mkdir(parents=True)
    state_path = session_dir / "overnight-state.json"
    state_path.write_text("{}", encoding="utf-8")

    # Mock _resolve_repo_path so handle_start sees our ephemeral repo.
    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda: repo
    )

    # Mock runner_module.run so we can assert it was NOT called. Use a
    # sentinel that records invocation; test fails if it's ever entered.
    invocations: list[tuple] = []

    def _fake_run(**kwargs):
        invocations.append(("called", kwargs))
        return 0

    monkeypatch.setattr(cli_handler.runner_module, "run", _fake_run)

    args = argparse.Namespace(
        state=str(state_path),
        time_limit=None,
        max_rounds=None,
        tier="simple",
        dry_run=False,
        format="human",
    )

    rc = cli_handler.handle_start(args)

    assert rc == 1, f"expected exit code 1 from refused start; got: {rc}"

    captured = capsys.readouterr()
    assert "hook guard not installed" in captured.err, (
        f"expected 'hook guard not installed' substring on stderr; got: "
        f"{captured.err!r}"
    )

    assert not invocations, (
        f"runner_module.run must NOT be invoked when the hook gate trips; "
        f"got invocations: {invocations!r}"
    )
