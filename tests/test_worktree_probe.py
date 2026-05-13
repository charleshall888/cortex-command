"""Tests for probe_worktree_writable() (R8).

Covers three cases:
    (i)   Writable root — probe succeeds, no artifacts left behind.
    (ii)  Sandbox-blocked root (read-only path) — probe fails with cause
          naming sandbox.
    (iii) Fixture git repo with a tracked .vscode/ directory — git worktree
          add fails; probe result names hardcoded deny.
"""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest

from cortex_command.pipeline.worktree import ProbeResult, probe_worktree_writable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_git_repo(path: Path) -> str:
    """Initialize a git repo with an initial empty commit.

    Returns the default branch name (e.g. 'main' or 'master').
    """
    subprocess.run(
        ["git", "init"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(path),
    )
    subprocess.run(
        [
            "git",
            "-c", "commit.gpgsign=false",
            "-c", "user.email=test@test.com",
            "-c", "user.name=Test",
            "commit",
            "--allow-empty",
            "-m", "init",
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(path),
    )
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(path),
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# (i) Writable root — success
# ---------------------------------------------------------------------------


class TestProbeWritableRootSuccess:
    """Probe succeeds when the root is writable and git-worktree-add-capable."""

    def test_success_returns_ok_true(self, tmp_path):
        """Probe a writable root inside a fresh git repo; expect ok=True."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)

        worktree_root = repo / "probe-root"
        result = probe_worktree_writable(worktree_root)

        assert isinstance(result, ProbeResult)
        assert result.ok is True
        assert result.cause is None
        assert result.remediation_hint is None

    def test_success_leaves_no_artifacts(self, tmp_path):
        """No probe artifacts remain after a successful probe."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)

        worktree_root = repo / "probe-root"
        probe_worktree_writable(worktree_root)

        # The probe root itself may be created, but no cortex-probe-* entries
        # should remain.
        if worktree_root.exists():
            remaining = list(worktree_root.iterdir())
            probe_artifacts = [p for p in remaining if "cortex-probe-" in p.name]
            assert probe_artifacts == [], (
                f"Probe artifacts remain: {probe_artifacts}"
            )


# ---------------------------------------------------------------------------
# (ii) Sandbox-blocked root — filesystem write denied
# ---------------------------------------------------------------------------


class TestProbeSandboxBlockedRoot:
    """Probe fails with cause='sandbox_blocked' when writes are denied."""

    def test_readonly_root_returns_sandbox_blocked(self, tmp_path):
        """Simulate a sandbox-blocked root using a read-only directory."""
        # Create a read-only directory to simulate a sandbox deny.
        blocked_root = tmp_path / "blocked"
        blocked_root.mkdir()
        blocked_root.chmod(0o555)  # r-xr-xr-x: no write bit

        try:
            result = probe_worktree_writable(blocked_root)
        finally:
            # Restore permissions so tmp_path cleanup can remove it.
            blocked_root.chmod(0o755)

        assert isinstance(result, ProbeResult)
        assert result.ok is False
        assert result.cause == "sandbox_blocked"
        assert result.remediation_hint is not None
        assert len(result.remediation_hint) > 0

    def test_sandbox_blocked_remediation_hint_mentions_allowwrite(self, tmp_path):
        """Remediation hint for sandbox-blocked case mentions allowWrite."""
        blocked_root = tmp_path / "blocked2"
        blocked_root.mkdir()
        blocked_root.chmod(0o555)

        try:
            result = probe_worktree_writable(blocked_root)
        finally:
            blocked_root.chmod(0o755)

        assert result.ok is False
        assert result.remediation_hint is not None
        # Hint should guide the user toward fixing sandbox config.
        hint_lower = result.remediation_hint.lower()
        assert "allowwrite" in hint_lower or "sandbox" in hint_lower or "cortex init" in hint_lower


# ---------------------------------------------------------------------------
# (iii) Fixture repo with tracked .vscode/ — git worktree add blocked
# ---------------------------------------------------------------------------


class TestProbeHardcodedDenyVscode:
    """Probe detects git worktree add failures caused by hardcoded-deny paths."""

    def test_vscode_root_returns_hardcoded_deny(self, tmp_path, monkeypatch):
        """Simulate git worktree add failure for a .vscode/ path.

        We mock subprocess.run so that the `git worktree add` call fails with
        a non-zero exit code (as if the sandbox denied it), while the
        filesystem write check (check a) succeeds. This exercises the
        hardcoded-deny branch without needing actual Claude Code sandbox
        infrastructure.
        """
        import subprocess as _subprocess
        from unittest.mock import patch

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)

        # The probe root is inside a .vscode-like path.
        vscode_root = repo / ".vscode" / "worktrees"

        # Patch subprocess.run to let filesystem ops through but fail
        # `git worktree add`.
        original_run = _subprocess.run

        def patched_run(cmd, *args, **kwargs):
            if isinstance(cmd, list) and len(cmd) >= 3 and cmd[:3] == ["git", "worktree", "add"]:
                from subprocess import CompletedProcess
                return CompletedProcess(
                    args=cmd,
                    returncode=128,
                    stdout="",
                    stderr=(
                        "fatal: '/path/.vscode/worktrees/cortex-probe-xxxx' is under "
                        "a restricted path blocked by the sandbox"
                    ),
                )
            return original_run(cmd, *args, **kwargs)

        with patch("cortex_command.pipeline.worktree.subprocess.run", side_effect=patched_run):
            result = probe_worktree_writable(vscode_root)

        assert isinstance(result, ProbeResult)
        assert result.ok is False
        assert result.cause == "hardcoded_deny"
        assert result.remediation_hint is not None

    def test_hardcoded_deny_remediation_hint_mentions_vscode(self, tmp_path):
        """Remediation hint for hardcoded deny mentions .vscode/.idea workaround."""
        import subprocess as _subprocess
        from unittest.mock import patch

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)

        vscode_root = repo / ".vscode" / "worktrees"

        original_run = _subprocess.run

        def patched_run(cmd, *args, **kwargs):
            if isinstance(cmd, list) and len(cmd) >= 3 and cmd[:3] == ["git", "worktree", "add"]:
                from subprocess import CompletedProcess
                return CompletedProcess(
                    args=cmd,
                    returncode=128,
                    stdout="",
                    stderr="fatal: restricted path",
                )
            return original_run(cmd, *args, **kwargs)

        with patch("cortex_command.pipeline.worktree.subprocess.run", side_effect=patched_run):
            result = probe_worktree_writable(vscode_root)

        assert result.ok is False
        assert result.cause == "hardcoded_deny"
        assert result.remediation_hint is not None
        # Hint should mention the upstream issue or a workaround.
        hint_lower = result.remediation_hint.lower()
        assert (
            "vscode" in hint_lower
            or "hardcoded" in hint_lower
            or "sparse" in hint_lower
            or "51303" in hint_lower
        )

    def test_hardcoded_deny_with_real_vscode_repo(self, tmp_path):
        """Fixture repo with tracked .vscode/ dir: git worktree add fails.

        Creates an actual git repo with a committed .vscode/ directory.
        The probe root is placed inside .vscode/ so `git worktree add`
        targets a path within the tracked .vscode directory — simulating the
        consumer-repo condition described in R8's context note.

        Note: On machines without the actual Claude Code sandbox, `git worktree
        add` does NOT fail due to `.vscode/` presence — the hardcoded deny is
        a Claude Code sandbox behavior, not native git behavior. We therefore
        mock subprocess.run to simulate the sandbox deny while still using a
        real git repo fixture to exercise the full code path up to the mock.
        """
        import subprocess as _subprocess
        from unittest.mock import patch

        repo = tmp_path / "fixture-repo"
        repo.mkdir()
        _init_git_repo(repo)

        # Track a .vscode/ directory in the repo (mirroring a consumer repo).
        vscode_dir = repo / ".vscode"
        vscode_dir.mkdir()
        (vscode_dir / "settings.json").write_text('{"editor.tabSize": 4}')
        subprocess.run(
            ["git", "add", ".vscode/"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(repo),
        )
        subprocess.run(
            [
                "git",
                "-c", "commit.gpgsign=false",
                "-c", "user.email=test@test.com",
                "-c", "user.name=Test",
                "commit",
                "-m", "track .vscode",
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(repo),
        )

        # Probe root is inside the tracked .vscode/ directory.
        probe_root = vscode_dir / "worktrees"

        original_run = _subprocess.run

        def patched_run(cmd, *args, **kwargs):
            if isinstance(cmd, list) and len(cmd) >= 3 and cmd[:3] == ["git", "worktree", "add"]:
                from subprocess import CompletedProcess
                return CompletedProcess(
                    args=cmd,
                    returncode=128,
                    stdout="",
                    stderr="fatal: .vscode is a restricted path",
                )
            return original_run(cmd, *args, **kwargs)

        with patch("cortex_command.pipeline.worktree.subprocess.run", side_effect=patched_run):
            result = probe_worktree_writable(probe_root)

        assert result.ok is False
        assert result.cause == "hardcoded_deny"


# ---------------------------------------------------------------------------
# ProbeResult shape contract
# ---------------------------------------------------------------------------


class TestProbeResultShape:
    """Verify ProbeResult dataclass has the required fields."""

    def test_probe_result_has_ok_field(self):
        r = ProbeResult(ok=True, cause=None, remediation_hint=None)
        assert r.ok is True

    def test_probe_result_has_cause_field(self):
        r = ProbeResult(ok=False, cause="sandbox_blocked", remediation_hint="hint")
        assert r.cause == "sandbox_blocked"

    def test_probe_result_has_remediation_hint_field(self):
        r = ProbeResult(ok=False, cause="hardcoded_deny", remediation_hint="fix it")
        assert r.remediation_hint == "fix it"

    def test_probe_result_success_shape(self):
        r = ProbeResult(ok=True, cause=None, remediation_hint=None)
        assert r.ok is True
        assert r.cause is None
        assert r.remediation_hint is None
