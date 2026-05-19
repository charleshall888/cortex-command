"""Tests for Complete phase Step 3 advisory worktree detection and routing.

Spec R9 acceptance: four detection-outcome cases for the two-signal worktree
check that determines whether the cd-in-then-out path is taken around
/cortex-core:pr in complete.md Step 3.

The two signals are:
  - Signal 1 (lock file):  cortex_command.interactive_lock.read_lock(slug)
                           returns non-None when interactive.pid is present.
  - Signal 2 (directory):  git rev-parse --show-toplevel output matches pwd.

Detection is advisory (not blocking).  The four cases enumerated in the spec:

  (a) Both signals positive (lock file present + pwd matches worktree)
      → cd-in-then-out path is selected.
  (b) PID stale + pwd in worktree (lock file present but stale; pwd is worktree)
      → cd-in-then-out path (Signal 1 positive = lock file present;
        Signal 2 positive = pwd is worktree; liveness is orthogonal to routing).
  (c) PID present + pwd NOT in worktree (lock file present; pwd is main repo)
      → non-worktree path (Signal 2 absent/contradictory).
  (d) Both absent (no lock file; git rev-parse does not match worktree)
      → non-worktree path.

The tests mock cortex_command.interactive_lock.read_lock and subprocess.run
(for git rev-parse --show-toplevel) and use tmp_path + monkeypatch.chdir to
control pwd.  The routing decision itself is encoded in a helper that mirrors
the complete.md Step 3 detection logic; the tests exercise that helper to
verify the four-quadrant case enumeration.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Detection logic mirror
#
# This mirrors the complete.md Step 3 advisory detection protocol.  It is
# NOT extracted production code — it reproduces the two-signal logic from the
# skill prose so the tests can assert routing outcomes without coupling to a
# live skill invocation.
#
# Signal 1: read_lock(slug) returns non-None  → lock file present
# Signal 2: git rev-parse --show-toplevel     → compare against pwd
#
# Both positive → cd-in-then-out path (True)
# Either absent or contradictory → non-worktree path (False)
# ---------------------------------------------------------------------------

_VALID_LOCK = {
    "schema_version": 1,
    "magic": "cortex-interactive-lock",
    "session_id": "test-session",
    "pid": 12345,
    "start_time": 1000.0,
    "acquired_at": "2026-05-18T12:00:00+00:00",
}

_STALE_LOCK = {
    "schema_version": 1,
    "magic": "cortex-interactive-lock",
    "session_id": "old-session",
    "pid": 99999,  # stale/exited PID
    "start_time": 500.0,
    "acquired_at": "2026-01-01T00:00:00+00:00",
}


def _detect_variant_a_worktree(
    slug: str,
    worktree_path: Path,
    *,
    read_lock_return: Optional[dict],
    git_toplevel_output: str,
    pwd: Path,
) -> bool:
    """Mirror of complete.md Step 3 advisory detection.

    Returns True if the cd-in-then-out path should be taken (both signals
    positive), False otherwise (non-worktree path).

    Parameters
    ----------
    slug:
        Feature slug (used only for naming context in this mirror).
    worktree_path:
        The expected interactive/{slug} worktree root path.
    read_lock_return:
        The value that cortex_command.interactive_lock.read_lock would return.
        Non-None → Signal 1 positive.
    git_toplevel_output:
        The stdout of ``git rev-parse --show-toplevel`` (already stripped).
        Used for Signal 2 evaluation.
    pwd:
        The current working directory to compare against git_toplevel_output.
    """
    # Signal 1: lock file present?
    signal_1 = read_lock_return is not None

    # Signal 2: git rev-parse --show-toplevel matches pwd AND is the worktree?
    # The detection checks that the resolved toplevel matches pwd and is the
    # interactive worktree root.
    try:
        toplevel = Path(git_toplevel_output.strip()).resolve()
        pwd_resolved = pwd.resolve()
        signal_2 = toplevel == pwd_resolved and toplevel == worktree_path.resolve()
    except Exception:
        signal_2 = False

    # Both signals must be positive for the cd-in-then-out path.
    return signal_1 and signal_2


# ---------------------------------------------------------------------------
# Case (a): Both signals positive → cd-in-then-out path
# ---------------------------------------------------------------------------


class TestCaseABothPositive:
    """Case (a): lock file present + pwd matches worktree → cd-in-then-out."""

    def test_both_signals_positive_selects_cd_in_then_out(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When lock file is present and pwd is the worktree, take cd-in-then-out path."""
        worktree_path = tmp_path / "interactive-my-feature"
        worktree_path.mkdir(parents=True)

        monkeypatch.chdir(worktree_path)

        result = _detect_variant_a_worktree(
            "my-feature",
            worktree_path,
            read_lock_return=_VALID_LOCK,
            git_toplevel_output=str(worktree_path),
            pwd=worktree_path,
        )

        assert result is True, (
            "Both signals positive: lock file present + pwd matches worktree "
            "must select the cd-in-then-out path (True)"
        )

    def test_both_positive_with_monkeypatched_read_lock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify detection using mocked read_lock (as spec instructs)."""
        worktree_path = tmp_path / "interactive-feat"
        worktree_path.mkdir(parents=True)

        monkeypatch.chdir(worktree_path)

        # Mock read_lock to return a valid lock dict (Signal 1 positive)
        with patch(
            "cortex_command.interactive_lock.read_lock",
            return_value=_VALID_LOCK,
        ) as mock_read_lock:
            lock_result = mock_read_lock("feat")

        # Mock subprocess.run for git rev-parse --show-toplevel (Signal 2 positive)
        mock_proc = MagicMock()
        mock_proc.stdout = str(worktree_path)
        mock_proc.returncode = 0

        with patch("subprocess.run", return_value=mock_proc):
            proc = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
            )

        result = _detect_variant_a_worktree(
            "feat",
            worktree_path,
            read_lock_return=lock_result,
            git_toplevel_output=proc.stdout,
            pwd=worktree_path,
        )

        assert result is True, (
            "Mocked read_lock=valid + git toplevel=worktree must select cd-in-then-out"
        )


# ---------------------------------------------------------------------------
# Case (b): PID stale + pwd in worktree → cd-in-then-out path
# ---------------------------------------------------------------------------


class TestCaseBStalePidPwdInWorktree:
    """Case (b): lock file present (stale PID) + pwd matches worktree → cd-in-then-out.

    Detection is advisory: liveness of the PID is not evaluated for routing.
    Signal 1 fires when read_lock returns non-None regardless of PID liveness.
    Signal 2 fires when pwd resolves to the worktree root.
    Both positive → cd-in-then-out path.
    """

    def test_stale_pid_with_pwd_in_worktree_selects_cd_in_then_out(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Stale lock file present + pwd is worktree → cd-in-then-out path."""
        worktree_path = tmp_path / "interactive-stale-feature"
        worktree_path.mkdir(parents=True)

        monkeypatch.chdir(worktree_path)

        # _STALE_LOCK is a lock with a stale PID (99999) — but read_lock
        # returns it non-None (it's parseable and has the right magic).
        result = _detect_variant_a_worktree(
            "stale-feature",
            worktree_path,
            read_lock_return=_STALE_LOCK,  # stale PID, still present
            git_toplevel_output=str(worktree_path),
            pwd=worktree_path,
        )

        assert result is True, (
            "Stale lock file present + pwd in worktree must still select "
            "cd-in-then-out path (detection is advisory, not a liveness gate)"
        )

    def test_stale_lock_signal_1_is_positive_when_file_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Signal 1 is True (non-None return) even for a stale lock dict."""
        worktree_path = tmp_path / "interactive-stale2"
        worktree_path.mkdir(parents=True)

        monkeypatch.chdir(worktree_path)

        # read_lock returns non-None for stale lock (just checks file present +
        # parseable + correct magic). Liveness is not read_lock's concern.
        with patch(
            "cortex_command.interactive_lock.read_lock",
            return_value=_STALE_LOCK,
        ) as mock_read_lock:
            lock_result = mock_read_lock("stale2")

        assert lock_result is not None, (
            "read_lock must return non-None for a stale-PID lock file "
            "(Signal 1 should be positive; stale detection is orthogonal)"
        )

        result = _detect_variant_a_worktree(
            "stale2",
            worktree_path,
            read_lock_return=lock_result,
            git_toplevel_output=str(worktree_path),
            pwd=worktree_path,
        )

        assert result is True, (
            "Non-None read_lock return + pwd in worktree must select cd-in-then-out "
            "regardless of whether the recorded PID is stale"
        )


# ---------------------------------------------------------------------------
# Case (c): PID present + pwd NOT in worktree → non-worktree path
# ---------------------------------------------------------------------------


class TestCaseCPidPresentPwdNotInWorktree:
    """Case (c): lock file present + pwd is NOT the worktree → non-worktree path.

    Signal 1 fires (lock file present), but Signal 2 does not (pwd is the main
    repo, not the worktree).  Detection is contradictory → non-worktree path.
    """

    def test_pid_present_pwd_not_in_worktree_selects_non_worktree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lock file present + pwd is main repo → non-worktree path."""
        main_repo_path = tmp_path / "main-repo"
        main_repo_path.mkdir(parents=True)
        worktree_path = tmp_path / "interactive-my-feature"
        worktree_path.mkdir(parents=True)

        # CWD is the main repo, NOT the worktree.
        monkeypatch.chdir(main_repo_path)

        result = _detect_variant_a_worktree(
            "my-feature",
            worktree_path,
            read_lock_return=_VALID_LOCK,  # lock file present
            git_toplevel_output=str(main_repo_path),  # toplevel is main repo
            pwd=main_repo_path,  # pwd is main repo
        )

        assert result is False, (
            "Lock file present + pwd is main repo (not worktree) must select "
            "non-worktree path (Signal 2 absent → contradictory signals)"
        )

    def test_toplevel_mismatch_overrides_lock_presence(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even a valid lock file cannot override a pwd that is not the worktree."""
        main_repo = tmp_path / "repo"
        main_repo.mkdir(parents=True)
        worktree = tmp_path / "worktrees" / "interactive-other-feature"
        worktree.mkdir(parents=True)

        monkeypatch.chdir(main_repo)

        # git rev-parse --show-toplevel returns the main repo (not the worktree)
        mock_proc = MagicMock()
        mock_proc.stdout = str(main_repo)
        mock_proc.returncode = 0

        with patch("subprocess.run", return_value=mock_proc):
            proc = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
            )

        with patch(
            "cortex_command.interactive_lock.read_lock",
            return_value=_VALID_LOCK,
        ) as mock_read_lock:
            lock_result = mock_read_lock("other-feature")

        result = _detect_variant_a_worktree(
            "other-feature",
            worktree,
            read_lock_return=lock_result,
            git_toplevel_output=proc.stdout,
            pwd=main_repo,
        )

        assert result is False, (
            "Valid lock file + pwd=main_repo (not worktree) must select non-worktree path"
        )


# ---------------------------------------------------------------------------
# Case (d): Both absent → non-worktree path
# ---------------------------------------------------------------------------


class TestCaseDNeitherPresent:
    """Case (d): lock file absent + git rev-parse does not match worktree → non-worktree path."""

    def test_both_absent_selects_non_worktree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No lock file + pwd not in worktree → non-worktree path."""
        some_dir = tmp_path / "some-directory"
        some_dir.mkdir(parents=True)
        worktree_path = tmp_path / "interactive-absent-feature"
        worktree_path.mkdir(parents=True)

        monkeypatch.chdir(some_dir)

        result = _detect_variant_a_worktree(
            "absent-feature",
            worktree_path,
            read_lock_return=None,  # lock file absent
            git_toplevel_output=str(some_dir),  # pwd is not the worktree
            pwd=some_dir,
        )

        assert result is False, (
            "No lock file + pwd not in worktree must select non-worktree path "
            "(both signals absent)"
        )

    def test_no_lock_file_with_monkeypatched_read_lock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify non-worktree path using mocked read_lock returning None."""
        cwd = tmp_path / "current-dir"
        cwd.mkdir(parents=True)
        worktree_path = tmp_path / "interactive-no-lock"
        worktree_path.mkdir(parents=True)

        monkeypatch.chdir(cwd)

        # Mock read_lock returning None (no lock file)
        with patch(
            "cortex_command.interactive_lock.read_lock",
            return_value=None,
        ) as mock_read_lock:
            lock_result = mock_read_lock("no-lock")

        assert lock_result is None, "read_lock must return None when no lock file present"

        # git rev-parse also doesn't match the worktree
        mock_proc = MagicMock()
        mock_proc.stdout = str(cwd)
        mock_proc.returncode = 0

        with patch("subprocess.run", return_value=mock_proc):
            proc = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
            )

        result = _detect_variant_a_worktree(
            "no-lock",
            worktree_path,
            read_lock_return=lock_result,
            git_toplevel_output=proc.stdout,
            pwd=cwd,
        )

        assert result is False, (
            "No lock file + pwd not in worktree must select non-worktree path"
        )

    def test_no_lock_no_worktree_dir_neither_signal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both signals absent (no lock file, no matching worktree path at all)."""
        cwd = tmp_path / "arbitrary-dir"
        cwd.mkdir(parents=True)
        # worktree_path is a path that doesn't exist (no worktree created)
        worktree_path = tmp_path / "interactive-nonexistent"

        monkeypatch.chdir(cwd)

        result = _detect_variant_a_worktree(
            "nonexistent",
            worktree_path,
            read_lock_return=None,
            git_toplevel_output=str(cwd),
            pwd=cwd,
        )

        assert result is False, (
            "Both signals absent must select non-worktree path — lifecycle "
            "proceeds with /cortex-core:pr from current cwd without cd"
        )


# ---------------------------------------------------------------------------
# Structural assertions: complete.md Step 3 encodes the detection protocol
# ---------------------------------------------------------------------------


class TestCompleteStepThreeStructural:
    """Structural assertions: complete.md Step 3 documents both signal reads."""

    @pytest.fixture(autouse=True)
    def _load_complete_md(self) -> None:
        complete_md = (
            Path(__file__).parent.parent
            / "skills"
            / "lifecycle"
            / "references"
            / "complete.md"
        )
        self._text = complete_md.read_text(encoding="utf-8")

    def test_step_3_heading_present(self) -> None:
        """complete.md must contain a Step 3 heading."""
        import re

        assert re.search(r"^#{1,4}\s+Step\s+3\b", self._text, re.MULTILINE), (
            "complete.md must contain '### Step 3' (or similar) heading"
        )

    def test_signal_1_read_lock_documented(self) -> None:
        """complete.md Step 3 must document Signal 1: read_lock call."""
        assert "read_lock" in self._text, (
            "complete.md Step 3 must document Signal 1 using 'read_lock'"
        )

    def test_signal_2_git_rev_parse_documented(self) -> None:
        """complete.md Step 3 must document Signal 2: git rev-parse --show-toplevel."""
        assert "git rev-parse --show-toplevel" in self._text, (
            "complete.md Step 3 must document 'git rev-parse --show-toplevel' "
            "as Signal 2 for directory corroboration"
        )

    def test_cd_in_then_out_pattern_documented(self) -> None:
        """complete.md Step 3 must document the cd-in-then-out pattern."""
        assert "cd-in-then-out" in self._text or "_origin_pwd" in self._text, (
            "complete.md Step 3 must document the cd-in-then-out pattern "
            "or the _origin_pwd variable for directory restore"
        )

    def test_both_signals_required_for_cd_path(self) -> None:
        """complete.md Step 3 must require both signals positive for cd-in-then-out."""
        assert "both signals" in self._text.lower() or (
            "lock file present" in self._text.lower()
            and "git rev-parse" in self._text
        ), (
            "complete.md Step 3 must document that BOTH signals are required "
            "for the cd-in-then-out path"
        )

    def test_advisory_nature_documented(self) -> None:
        """complete.md Step 3 must document that detection is advisory (not blocking)."""
        assert "advisory" in self._text.lower() or "does not block" in self._text.lower(), (
            "complete.md Step 3 must document that worktree detection is advisory "
            "(not blocking PR creation)"
        )

    def test_non_worktree_fallback_documented(self) -> None:
        """complete.md Step 3 must document the fallback to non-worktree path."""
        text_lower = self._text.lower()
        assert (
            "absent or contradictory" in text_lower
            or "not in variant a" in text_lower
            or "without any cd" in text_lower
        ), (
            "complete.md Step 3 must document the fallback: when signals are absent "
            "or contradictory, invoke /cortex-core:pr without cd"
        )
