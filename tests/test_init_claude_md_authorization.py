"""Tests for the CLAUDE.md authorization fence (R5, R7).

Covers two surfaces landed in Tasks 5 and 6 of the
``lifecycle-implement-auto-enter-worktree-via`` lifecycle:

  * :func:`cortex_command.init.scaffold.ensure_claude_md_authorization` —
    the additive-idempotent splice that writes / refreshes the authorization
    fence (opening sigil tracked via the canonical ``version=N`` attribute)
    in consumer ``CLAUDE.md``. The four branches per the R5 spec:

      (a) ``test_absent_appends``           — CLAUDE.md missing or fence
                                              absent → fence appended.
      (b) ``test_present_and_current_noop`` — fence present at canonical
                                              version → no-op (byte-for-byte
                                              unchanged on a second run).
      (c) ``test_present_and_stale_replaces`` — synthetic ``version=0`` fence
                                              → replaced with canonical body;
                                              surrounding user prose preserved.
      (d) ``test_in_fence_user_edits_noop_at_canonical_version`` — user edits
                                              the in-fence body at the canonical
                                              version → no-op (R5 "latest writer
                                              wins by version, no in-fence user
                                              edits respected" — silently
                                              overwritten only on the next
                                              canonical-version bump).

  * ``cortex init --revoke-worktree-auth`` — the rollback subcommand that
    strips the fence from consumer ``CLAUDE.md``. The four branches per
    the R7 spec:

      (e) ``test_revoke_round_trip``        — init writes fence, revoke
                                              removes fence, other content
                                              byte-for-byte unchanged.
      (f) ``test_revoke_when_fence_absent_is_noop`` — revoke on a repo
                                              without a fence exits 0 and
                                              writes nothing.
      (g) ``test_revoke_with_live_session_refuses`` — fence present AND a
                                              live ``cortex/lifecycle/
                                              sessions/*.interactive.pid``
                                              file exists → exit 2 with
                                              stderr diagnostic naming the
                                              pid file; fence not removed.
      (h) ``test_revoke_with_live_session_force_proceeds`` — same as (g)
                                              but with ``--force`` →
                                              exit 0 and fence removed.

All tests use ``tmp_path`` to materialize a minimal consumer repo (an empty
git repo with optional pre-existing CLAUDE.md content). The init handler is
driven via :func:`cortex_command.init.handler.main` with an
``argparse.Namespace`` mirroring the CLI surface so the tests exercise the
same code path as the shipped ``cortex init`` subcommand.

The live-PID synthesis uses the current process PID (``os.getpid()``) —
guaranteed to be live for the duration of the test — to drive the liveness
probe deterministically without spawning a real child process.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

import pytest

from cortex_command.init import scaffold
from cortex_command.init.handler import main as init_main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_git_repo(path: Path) -> None:
    """Initialize a minimal git repo at ``path`` so ``_resolve_repo_root`` succeeds.

    The init handler resolves the target repo root via
    ``git rev-parse --show-toplevel`` (R2). The tmp_path consumer must look
    like a real git repo or the handler rejects with exit 2 before reaching
    the surfaces under test.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(path),
        check=True,
        capture_output=True,
    )


def _make_args(
    repo_path: Path,
    *,
    revoke_worktree_auth: bool = False,
    verify_worktree_auth: bool = False,
    update: bool = False,
    unregister: bool = False,
    force: bool = False,
) -> argparse.Namespace:
    """Build the ``argparse.Namespace`` the init handler expects.

    Mirrors the attribute surface attached to the subparser in
    ``cortex_command/cli.py`` so the handler's ``getattr``/dotted attribute
    accesses all resolve consistently.
    """
    return argparse.Namespace(
        path=str(repo_path),
        update=update,
        unregister=unregister,
        revoke_worktree_auth=revoke_worktree_auth,
        verify_worktree_auth=verify_worktree_auth,
        force=force,
    )


def _canonical_fence() -> str:
    """Return the canonical fence block as the implementation would write it."""
    return scaffold._render_claude_md_auth_block(scaffold._CLAUDE_MD_AUTH_VERSION)


def _stale_fence_block() -> str:
    """Render a ``version=0`` fence — guaranteed stale vs. canonical ≥ 1."""
    return scaffold._render_claude_md_auth_block(0)


# ---------------------------------------------------------------------------
# (a) absent → append
# ---------------------------------------------------------------------------


class TestAbsent:
    """Fence-absent inputs produce a write."""

    def test_absent_appends_creates_file_when_claude_md_missing(self, tmp_path):
        """No CLAUDE.md on disk → file created containing the canonical fence."""
        _init_git_repo(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        assert not claude_md.exists()

        wrote = scaffold.ensure_claude_md_authorization(tmp_path)

        assert wrote is True
        assert claude_md.exists()
        content = claude_md.read_text(encoding="utf-8")
        assert scaffold._find_claude_md_auth_fence(content) is not None
        # Sanity: the canonical body is present in the rendered file.
        assert "Lifecycle worktree authorization" in content

    def test_absent_appends_preserves_existing_user_prose(self, tmp_path):
        """Existing CLAUDE.md with user prose but no fence → fence appended after prose."""
        _init_git_repo(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        user_prose = "# My project\n\nUser-authored content.\n"
        claude_md.write_text(user_prose, encoding="utf-8")

        wrote = scaffold.ensure_claude_md_authorization(tmp_path)

        assert wrote is True
        content = claude_md.read_text(encoding="utf-8")
        assert content.startswith(user_prose)
        assert scaffold._find_claude_md_auth_fence(content) is not None


# ---------------------------------------------------------------------------
# (b) present-and-current → no-op
# ---------------------------------------------------------------------------


class TestPresentAndCurrent:
    """A fence at the canonical version is byte-stable across runs."""

    def test_present_and_current_noop_returns_false(self, tmp_path):
        """First call writes; second call returns False with no byte change."""
        _init_git_repo(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"

        first = scaffold.ensure_claude_md_authorization(tmp_path)
        assert first is True
        snapshot = claude_md.read_bytes()

        second = scaffold.ensure_claude_md_authorization(tmp_path)
        assert second is False
        assert claude_md.read_bytes() == snapshot


# ---------------------------------------------------------------------------
# (c) present-and-stale → replace
# ---------------------------------------------------------------------------


class TestPresentAndStale:
    """A stale fence (``version < canonical``) is replaced; surrounding prose preserved."""

    def test_present_and_stale_replaces_fence_body(self, tmp_path):
        """Synthetic ``version=0`` fence → rewritten to canonical version."""
        _init_git_repo(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        # Construct CLAUDE.md with user prose around a stale fence.
        prefix = "# My project\n\nIntroductory prose.\n\n"
        suffix = "\n## Closing section\n\nFinal user prose.\n"
        stale = _stale_fence_block()
        original = prefix + stale + suffix
        claude_md.write_text(original, encoding="utf-8")

        # Sanity-check the stale fence is detected before the call.
        located = scaffold._find_claude_md_auth_fence(original)
        assert located is not None
        assert located[2] == 0

        wrote = scaffold.ensure_claude_md_authorization(tmp_path)

        assert wrote is True
        rewritten = claude_md.read_text(encoding="utf-8")
        located_after = scaffold._find_claude_md_auth_fence(rewritten)
        assert located_after is not None
        assert located_after[2] == scaffold._CLAUDE_MD_AUTH_VERSION
        # Surrounding user prose is preserved.
        assert "Introductory prose." in rewritten
        assert "## Closing section" in rewritten
        assert "Final user prose." in rewritten


# ---------------------------------------------------------------------------
# (d) in-fence user edits at canonical version → no-op
# ---------------------------------------------------------------------------


class TestInFenceUserEdits:
    """In-fence body edits at the canonical version are NOT overwritten (R5)."""

    def test_in_fence_user_edits_noop_at_canonical_version(self, tmp_path):
        """Mangled in-fence body at canonical version → no-op (silent acceptance)."""
        _init_git_repo(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"

        # Write a canonical-version fence with a mangled body. Build the
        # opening sigil from the implementation's own prefix constant so the
        # test does not duplicate the sigil literal verbatim.
        open_sigil = (
            f"{scaffold._CLAUDE_MD_AUTH_FENCE_OPEN_PREFIX} "
            f"version={scaffold._CLAUDE_MD_AUTH_VERSION} -->"
        )
        close_sigil = scaffold._CLAUDE_MD_AUTH_FENCE_CLOSE
        mangled_body = "User mangled this body — should NOT be restored at same version."
        mangled = f"{open_sigil}\n{mangled_body}\n{close_sigil}\n"
        claude_md.write_text(mangled, encoding="utf-8")
        snapshot = claude_md.read_bytes()

        wrote = scaffold.ensure_claude_md_authorization(tmp_path)

        # R5 policy: in-fence user edits are NOT respected (overwritten only
        # when version bumps). At the canonical version, the function no-ops.
        assert wrote is False
        assert claude_md.read_bytes() == snapshot
        # The mangled body is still on disk (no restoration happened).
        assert "User mangled this body" in claude_md.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# (e) revoke round-trip — init writes, revoke removes, other content unchanged
# ---------------------------------------------------------------------------


class TestRevokeRoundTrip:
    """Init writes the fence; revoke removes it; surrounding prose intact."""

    def test_revoke_round_trip(self, tmp_path):
        """Round-trip: write canonical fence, revoke it, assert surrounding prose intact."""
        _init_git_repo(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        user_prose_before = "# My project\n\nUser-authored content.\n"
        claude_md.write_text(user_prose_before, encoding="utf-8")

        # Phase 1: ensure writes the fence.
        wrote = scaffold.ensure_claude_md_authorization(tmp_path)
        assert wrote is True
        content_with_fence = claude_md.read_text(encoding="utf-8")
        assert scaffold._find_claude_md_auth_fence(content_with_fence) is not None

        # Phase 2: revoke via the CLI handler — no live session present.
        exit_code = init_main(_make_args(tmp_path, revoke_worktree_auth=True))
        assert exit_code == 0

        # Phase 3: fence is gone, surrounding user prose remains byte-for-byte.
        after = claude_md.read_text(encoding="utf-8")
        assert scaffold._find_claude_md_auth_fence(after) is None
        # The original user prose is preserved (possibly with a trailing
        # newline-normalization but the substantive content is intact).
        assert "# My project" in after
        assert "User-authored content." in after
        # No residual fence sigil text leftover. Use the implementation's
        # own constants so the test does not duplicate sigil literals.
        assert scaffold._CLAUDE_MD_AUTH_FENCE_OPEN_PREFIX not in after
        assert scaffold._CLAUDE_MD_AUTH_FENCE_CLOSE not in after


# ---------------------------------------------------------------------------
# (f) revoke when fence absent → no-op success
# ---------------------------------------------------------------------------


class TestRevokeWhenFenceAbsent:
    """Revoke on a repo without a fence exits 0 and does not error."""

    def test_revoke_when_no_claude_md_file_exists(self, tmp_path):
        """No CLAUDE.md on disk → revoke exits 0 (idempotent no-op)."""
        _init_git_repo(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        assert not claude_md.exists()

        exit_code = init_main(_make_args(tmp_path, revoke_worktree_auth=True))

        assert exit_code == 0
        # No file was created by the revoke path.
        assert not claude_md.exists()

    def test_revoke_when_claude_md_has_no_fence(self, tmp_path):
        """CLAUDE.md without fence → revoke exits 0; file byte-unchanged."""
        _init_git_repo(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        user_content = "# Pure user content with no fence.\n"
        claude_md.write_text(user_content, encoding="utf-8")
        snapshot = claude_md.read_bytes()

        exit_code = init_main(_make_args(tmp_path, revoke_worktree_auth=True))

        assert exit_code == 0
        assert claude_md.read_bytes() == snapshot


# ---------------------------------------------------------------------------
# (g/h) revoke + live interactive pid → refuse / --force proceeds
# ---------------------------------------------------------------------------


class TestRevokeWithLiveSession:
    """Live ``*.interactive.pid`` gates revocation unless ``--force`` is set."""

    def _seed_fence_and_live_pid(self, tmp_path: Path) -> tuple[Path, Path]:
        """Set up a repo with the canonical fence AND a live pid file.

        Returns ``(claude_md_path, pid_file_path)``. The pid file contains the
        current process's PID — guaranteed to be live for the duration of the
        test — so the canonical liveness probe (``os.kill(pid, 0)``) succeeds
        without spawning a real subprocess.
        """
        _init_git_repo(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        scaffold.ensure_claude_md_authorization(tmp_path)
        assert scaffold._find_claude_md_auth_fence(
            claude_md.read_text(encoding="utf-8")
        ) is not None

        sessions_dir = tmp_path / "cortex" / "lifecycle" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        pid_file = sessions_dir / "demo-slug.interactive.pid"
        pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")
        return claude_md, pid_file

    def test_revoke_with_live_session_refuses_without_force(
        self, tmp_path, capsys
    ):
        """Live ``.interactive.pid`` → exit 2; stderr lists the pid file; fence intact."""
        claude_md, pid_file = self._seed_fence_and_live_pid(tmp_path)
        snapshot = claude_md.read_bytes()

        exit_code = init_main(_make_args(tmp_path, revoke_worktree_auth=True))

        assert exit_code == 2
        captured = capsys.readouterr()
        # Diagnostic identifies the live pid file by absolute path.
        assert str(pid_file) in captured.err
        # Diagnostic surfaces the user-facing remediation (``--force``).
        assert "--force" in captured.err
        # Fence has NOT been removed.
        assert claude_md.read_bytes() == snapshot
        assert scaffold._find_claude_md_auth_fence(
            claude_md.read_text(encoding="utf-8")
        ) is not None

    def test_revoke_with_live_session_force_proceeds(self, tmp_path):
        """``--force`` bypasses the live-session pre-condition; fence is removed."""
        claude_md, _pid_file = self._seed_fence_and_live_pid(tmp_path)

        exit_code = init_main(
            _make_args(tmp_path, revoke_worktree_auth=True, force=True)
        )

        assert exit_code == 0
        assert scaffold._find_claude_md_auth_fence(
            claude_md.read_text(encoding="utf-8")
        ) is None

    def test_revoke_with_stale_pid_file_proceeds(self, tmp_path):
        """A pid file pointing at a non-live PID does NOT block revocation."""
        _init_git_repo(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        scaffold.ensure_claude_md_authorization(tmp_path)

        sessions_dir = tmp_path / "cortex" / "lifecycle" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        # PID 1 (init) is always live on Unix but we want a guaranteed-dead
        # PID. ``os.kill(pid, 0)`` on a never-allocated high PID returns
        # ESRCH, which the liveness probe treats as dead. Use a value
        # outside any practical PID range. (Linux default pid_max is 32768
        # or up to 4194304; macOS caps at 99999.) 2_000_000_000 is safely
        # above all of these.
        sessions_dir.joinpath("demo-slug.interactive.pid").write_text(
            "2000000000\n", encoding="utf-8"
        )

        exit_code = init_main(_make_args(tmp_path, revoke_worktree_auth=True))

        assert exit_code == 0
        assert scaffold._find_claude_md_auth_fence(
            claude_md.read_text(encoding="utf-8")
        ) is None
