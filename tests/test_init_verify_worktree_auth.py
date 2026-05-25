"""Tests for ``cortex init --verify-worktree-auth`` (R20).

The read-only probe surface landed in Task 7 of the
``lifecycle-implement-auto-enter-worktree-via`` lifecycle. The lifecycle
skill's §1a path calls this subcommand before ``EnterWorktree``; on non-zero
exit, the skill routes to the ``cd``-shim fallback per R10.

Per R20, the three branches map to the documented exit codes:

  * ``test_absent_fence_exits_1``  — CLAUDE.md missing (or fence absent in an
                                     existing CLAUDE.md) → exit 1.
  * ``test_current_fence_exits_0`` — fence at the canonical version → exit 0.
  * ``test_stale_fence_exits_2``   — fence with ``version < canonical`` → exit 2.

The probe is read-only: each test asserts the on-disk CLAUDE.md bytes are
unchanged after the probe runs (the lifecycle skill relies on this — the
probe is called before every ``EnterWorktree`` invocation and must not
mutate user state). A fourth case covers the future-version branch
(``version > canonical``), which the implementation treats as "satisfies
the gate" so a newer-cortex install temporarily downgraded does not
silently fall through to the ``cd``-shim path.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from cortex_command.init import scaffold
from cortex_command.init.handler import main as init_main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_git_repo(path: Path) -> None:
    """Initialize a minimal git repo so the R2 git-repo gate passes."""
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(path),
        check=True,
        capture_output=True,
    )


def _verify_args(repo_path: Path) -> argparse.Namespace:
    """Build the ``argparse.Namespace`` for ``cortex init --verify-worktree-auth``.

    Mirrors the subparser surface attached in ``cortex_command/cli.py`` so
    the handler's attribute accesses resolve consistently.
    """
    return argparse.Namespace(
        path=str(repo_path),
        update=False,
        unregister=False,
        revoke_worktree_auth=False,
        verify_worktree_auth=True,
        force=False,
    )


# ---------------------------------------------------------------------------
# (a) absent fence → exit 1
# ---------------------------------------------------------------------------


class TestAbsentFence:
    """Both missing-file and present-without-fence variants exit 1."""

    def test_claude_md_missing_exits_1(self, tmp_path):
        """No CLAUDE.md file → exit 1 (probe treats absence as "not satisfied")."""
        _init_git_repo(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        assert not claude_md.exists()

        exit_code = init_main(_verify_args(tmp_path))

        assert exit_code == 1
        # Probe never creates the file.
        assert not claude_md.exists()

    def test_claude_md_present_without_fence_exits_1(self, tmp_path):
        """CLAUDE.md exists but has no fence sigil → exit 1; file byte-unchanged."""
        _init_git_repo(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        user_content = "# My project\n\nNo cortex fence here.\n"
        claude_md.write_text(user_content, encoding="utf-8")
        snapshot = claude_md.read_bytes()

        exit_code = init_main(_verify_args(tmp_path))

        assert exit_code == 1
        # Read-only invariant: the probe must not mutate the file.
        assert claude_md.read_bytes() == snapshot

    def test_claude_md_with_orphan_opening_sigil_exits_1(self, tmp_path):
        """Opening sigil with no closing sigil is "malformed" → treated as absent."""
        _init_git_repo(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        # Truncated/malformed fence: opening sigil but no closing sigil. The
        # parser returns None for this case (see _find_claude_md_auth_fence
        # — opening with no closing is treated as absent so the next ensure
        # run rewrites a clean fence). Construct the opening sigil from the
        # implementation's prefix constant so the test does not duplicate
        # the sigil literal verbatim.
        open_sigil = (
            f"{scaffold._CLAUDE_MD_AUTH_FENCE_OPEN_PREFIX} version=1 -->"
        )
        malformed = (
            "# Header\n\n"
            f"{open_sigil}\n"
            "## Lifecycle worktree authorization\n"
            "no closing sigil follows\n"
        )
        claude_md.write_text(malformed, encoding="utf-8")
        snapshot = claude_md.read_bytes()

        exit_code = init_main(_verify_args(tmp_path))

        assert exit_code == 1
        assert claude_md.read_bytes() == snapshot


# ---------------------------------------------------------------------------
# (b) current fence → exit 0
# ---------------------------------------------------------------------------


class TestCurrentFence:
    """A canonical-version fence satisfies the gate and the probe exits 0."""

    def test_current_fence_exits_0(self, tmp_path):
        """Fence at canonical version → exit 0; file byte-unchanged."""
        _init_git_repo(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        # Materialize the canonical fence via the production splice path so
        # the test exercises the same write format the probe will read.
        scaffold.ensure_claude_md_authorization(tmp_path)
        snapshot = claude_md.read_bytes()

        exit_code = init_main(_verify_args(tmp_path))

        assert exit_code == 0
        # Read-only invariant: probe must not mutate the file.
        assert claude_md.read_bytes() == snapshot

    def test_future_version_fence_exits_0(self, tmp_path):
        """``version > canonical`` is treated as "satisfies the gate" (R20).

        A future-version fence (e.g., consumer ran a newer cortex-command and
        then downgraded the SDK) is a superset commitment to the same
        authorization surface — the probe accepts it rather than spuriously
        routing the skill to the fallback path.
        """
        _init_git_repo(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        future_version = scaffold._CLAUDE_MD_AUTH_VERSION + 1
        # Render a fence at a future version using the same renderer so the
        # body stays consistent — only the version attribute changes.
        future_fence = scaffold._render_claude_md_auth_block(future_version)
        claude_md.write_text(future_fence, encoding="utf-8")
        snapshot = claude_md.read_bytes()

        exit_code = init_main(_verify_args(tmp_path))

        assert exit_code == 0
        assert claude_md.read_bytes() == snapshot


# ---------------------------------------------------------------------------
# (c) stale fence (version < canonical) → exit 2
# ---------------------------------------------------------------------------


class TestStaleFence:
    """A stale fence is detected as "present but needs refresh" → exit 2."""

    def test_stale_fence_exits_2(self, tmp_path):
        """``version=0`` is strictly less than canonical → exit 2; file unchanged."""
        _init_git_repo(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        # version=0 is guaranteed stale relative to canonical ≥ 1.
        stale_fence = scaffold._render_claude_md_auth_block(0)
        claude_md.write_text(stale_fence, encoding="utf-8")
        snapshot = claude_md.read_bytes()

        exit_code = init_main(_verify_args(tmp_path))

        assert exit_code == 2
        # Probe is read-only — caller (``cortex init`` default invocation) is
        # the surface that rewrites; the probe must never mutate.
        assert claude_md.read_bytes() == snapshot
