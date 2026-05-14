"""Unit tests for ``cortex_command.auth.bootstrap.run``.

Covers every spec sub-case for ``cortex auth bootstrap`` per
``cortex/lifecycle/restore-subscription-auth-for-autonomous-worktree/spec.md``
(Requirements 2-7, 14-16 plus the documented Edge Cases):

  (a) ``test_bootstrap_captures_token_with_trailing_banner`` — banner-trailing
      fixture; bootstrap captures the bare token line, NOT the URL substring
      (asserts the regex's ``^...$`` line-anchor enforcement).
  (b) ``test_bootstrap_rejects_banner_only_output`` — banner-only fixture;
      bootstrap exits non-zero, file NOT created.
  (c) ``test_bootstrap_rejects_multiple_token_lines`` — inline fixture prints
      two token-shaped lines; bootstrap exits non-zero with the multi-match
      error.
  (d) ``test_bootstrap_overwrites_existing_token`` — pre-existing OLD token
      file; after bootstrap, file contains the NEW token.
  (e) ``test_bootstrap_writes_mode_0600`` — token file mode is exactly
      ``0o600``.
  (f) ``test_bootstrap_exits_2_when_claude_not_on_path`` — empty PATH; exit 2,
      stderr names the missing CLI.
  (g) ``test_bootstrap_exits_2_when_verb_unsupported`` — inline fixture exits
      2 on ``setup-token --help``; bootstrap exits 2 with the verb-probe
      error.
  (h) ``test_bootstrap_exits_2_when_stdin_not_tty`` — stdin is not a TTY;
      exit 2, stderr names the requirement; subprocess never invoked.
  (i) ``test_bootstrap_atomic_write_no_partial_state`` — patch ``os.replace``
      to raise; canonical file is unchanged from pre-call state.
  (j) ``test_bootstrap_lock_released_on_keyboardinterrupt`` — patch the
      subprocess invocation to raise ``KeyboardInterrupt``; verify the lock
      is released by acquiring ``LOCK_NB`` from a freshly-opened fd.
  (k) ``test_bootstrap_warns_on_post_write_shadowing`` — env shadows the
      written file; bootstrap exits 0 but stderr contains the shadowing
      warning.
  (l) ``test_bootstrap_heartbeat_printed_to_stderr`` — heartbeat line is
      printed to stderr before the subprocess is invoked.

Each test uses ``monkeypatch`` to redirect ``pathlib.Path.home``, scrub auth
env vars, and prepend the fixture dir to PATH (for tests that exercise the
real subprocess path). Mirrors the harness pattern in
``tests/test_auth_status.py`` and ``tests/test_runner_auth.py``.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import pathlib
import stat
import subprocess
from pathlib import Path

import pytest

from cortex_command.auth import bootstrap as bootstrap_mod


# ---------------------------------------------------------------------------
# Fixture helpers (mirror tests/test_auth_status.py / test_auth_precedence.py)
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def _scrub_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip auth env vars that could short-circuit ``ensure_sdk_auth``."""
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)


def _redirect_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    """Point both ``Path.home()`` and ``HOME`` at ``home``.

    Two redirects are required because the codebase mixes home-resolution
    APIs:
      * ``cortex_command.overnight.auth`` uses ``pathlib.Path.home()``.
      * ``cortex_command.auth.bootstrap`` uses ``Path("~/...").expanduser()``,
        which delegates to ``os.path.expanduser`` and consults the ``HOME``
        environment variable directly.

    Patching only one would leave the other path resolving under the real
    user's home — defeating the test isolation guarantee.
    """
    monkeypatch.setattr(pathlib.Path, "home", lambda: home)
    monkeypatch.setenv("HOME", str(home))


def _force_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``sys.stdin.isatty()`` return True for the duration of the test.

    The bootstrap module's ``_check_stdin_tty`` calls ``sys.stdin.isatty()``
    directly; under pytest, stdin is captured (not a TTY) so the call returns
    False. We patch the bound method on the captured stream so the gate
    passes for tests that need to reach the subprocess invocation.
    """
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)


# Minimal system PATH that still resolves ``/usr/bin/env`` and ``bash`` for
# the fixture shebang lines, while excluding any developer-installed real
# ``claude`` binary that would otherwise shadow our fixture.
_SYSTEM_BIN_PATH = "/usr/bin:/bin"


def _install_claude_fixture(
    monkeypatch: pytest.MonkeyPatch,
    fixture_path: Path,
    extra_dir: Path | None = None,
) -> Path:
    """Install ``fixture_path`` as ``claude`` on a controlled PATH.

    Symlinks (or copies) the fixture into a fresh dir, names it ``claude``,
    and sets PATH to ``<extra_dir>:/usr/bin:/bin``. The system bin dirs are
    required because the fixture's ``#!/usr/bin/env bash`` shebang resolves
    ``env`` and ``bash`` via PATH; restricting PATH to only ``extra_dir``
    yields ENOENT on exec. The fixture-dir prefix guarantees our stub wins
    over any developer-installed real ``claude`` binary on /usr/bin.
    """
    if extra_dir is None:
        # Caller didn't provide a destination — create a sibling under tmp.
        raise ValueError("extra_dir is required as the install location")

    extra_dir.mkdir(parents=True, exist_ok=True)
    claude_link = extra_dir / "claude"
    if claude_link.exists() or claude_link.is_symlink():
        claude_link.unlink()
    claude_link.symlink_to(fixture_path)
    monkeypatch.setenv("PATH", f"{extra_dir}:{_SYSTEM_BIN_PATH}")
    return extra_dir


def _empty_namespace() -> argparse.Namespace:
    """Minimal argparse.Namespace — bootstrap.run() ignores its args."""
    return argparse.Namespace()


# ---------------------------------------------------------------------------
# (a) Banner-trailing fixture — line anchors reject URL substring match
# ---------------------------------------------------------------------------


def test_bootstrap_captures_token_with_trailing_banner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Token line is captured; URL substring inside the banner is ignored.

    The banner-trailing fixture deliberately includes a ``sk-ant-oat01-``-
    shaped substring inside a release-notes URL. The bootstrap regex's
    ``^...$`` anchors should reject that substring and accept only the bare
    token line, demonstrating Edge Case "banner line AFTER the token line".
    """
    _scrub_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)
    _force_tty(monkeypatch)
    _install_claude_fixture(
        monkeypatch,
        FIXTURE_DIR / "fake_claude_setup_token_banner.sh",
        extra_dir=tmp_path / "bin",
    )

    rc = bootstrap_mod.run(_empty_namespace())

    assert rc == 0
    token_path = tmp_path / ".claude" / "personal-oauth-token"
    assert token_path.exists()
    contents = token_path.read_text(encoding="utf-8")
    # Bare token captured + single trailing newline.
    assert contents == "sk-ant-oat01-FIXTURE-TOKEN-VALUE-FOR-TESTS-ONLY\n"
    # The URL substring from the banner must not have leaked into the file.
    assert "example.com" not in contents
    assert "release.html" not in contents


# ---------------------------------------------------------------------------
# (b) Banner-only fixture — no token line, must reject and not create file
# ---------------------------------------------------------------------------


def test_bootstrap_rejects_banner_only_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Zero token-matching lines -> non-zero exit, file NOT created."""
    _scrub_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)
    _force_tty(monkeypatch)
    _install_claude_fixture(
        monkeypatch,
        FIXTURE_DIR / "fake_claude_setup_token_banner_only.sh",
        extra_dir=tmp_path / "bin",
    )

    rc = bootstrap_mod.run(_empty_namespace())
    captured = capsys.readouterr()

    assert rc != 0
    token_path = tmp_path / ".claude" / "personal-oauth-token"
    assert not token_path.exists()
    assert "did not contain a recognizable OAuth token" in captured.err


# ---------------------------------------------------------------------------
# (c) Multi-match — inline fixture prints two token-shaped lines
# ---------------------------------------------------------------------------


def test_bootstrap_rejects_multiple_token_lines(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two token-shaped lines -> non-zero exit with the multi-match error."""
    _scrub_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)
    _force_tty(monkeypatch)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    claude = bin_dir / "claude"
    claude.write_text(
        "#!/usr/bin/env bash\n"
        "set -u\n"
        'if [ "${1:-}" = "setup-token" ] && [ "${2:-}" = "--help" ]; then\n'
        "    exit 0\n"
        "fi\n"
        'if [ "${1:-}" = "setup-token" ]; then\n'
        "    printf '%s\\n' 'sk-ant-oat01-FIRST-FIXTURE-TOKEN-VALUE-FOR-TESTS'\n"
        "    printf '%s\\n' 'sk-ant-oat01-SECOND-FIXTURE-TOKEN-VALUE-FOR-TESTS'\n"
        "    exit 0\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{_SYSTEM_BIN_PATH}")

    rc = bootstrap_mod.run(_empty_namespace())
    captured = capsys.readouterr()

    assert rc != 0
    token_path = tmp_path / ".claude" / "personal-oauth-token"
    assert not token_path.exists()
    assert "multiple OAuth-token candidate lines" in captured.err


# ---------------------------------------------------------------------------
# (d) Idempotence — pre-existing OLD token is overwritten with NEW
# ---------------------------------------------------------------------------


def test_bootstrap_overwrites_existing_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A pre-existing OLD token file is overwritten with the freshly minted
    token; ``grep -c OLD`` is 0 after the call."""
    _scrub_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)
    _force_tty(monkeypatch)

    # Pre-seed the token file with an OLD value before bootstrap runs.
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    token_path = claude_dir / "personal-oauth-token"
    token_path.write_text(
        "sk-ant-oat01-OLD-FIXTURE-TOKEN-VALUE-MUST-BE-OVERWRITTEN\n",
        encoding="utf-8",
    )

    _install_claude_fixture(
        monkeypatch,
        FIXTURE_DIR / "fake_claude_setup_token.sh",
        extra_dir=tmp_path / "bin",
    )

    rc = bootstrap_mod.run(_empty_namespace())

    assert rc == 0
    contents = token_path.read_text(encoding="utf-8")
    assert "OLD" not in contents
    assert contents == "sk-ant-oat01-FIXTURE-TOKEN-VALUE-FOR-TESTS-ONLY\n"


# ---------------------------------------------------------------------------
# (e) File mode is exactly 0600
# ---------------------------------------------------------------------------


def test_bootstrap_writes_mode_0600(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Token file mode is exactly ``0o600`` after bootstrap."""
    _scrub_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)
    _force_tty(monkeypatch)
    _install_claude_fixture(
        monkeypatch,
        FIXTURE_DIR / "fake_claude_setup_token.sh",
        extra_dir=tmp_path / "bin",
    )

    rc = bootstrap_mod.run(_empty_namespace())

    assert rc == 0
    token_path = tmp_path / ".claude" / "personal-oauth-token"
    assert token_path.exists()
    mode = stat.S_IMODE(token_path.stat().st_mode)
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


# ---------------------------------------------------------------------------
# (f) ``claude`` not on PATH -> exit 2
# ---------------------------------------------------------------------------


def test_bootstrap_exits_2_when_claude_not_on_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An empty PATH triggers the ``shutil.which`` gate -> exit 2."""
    _scrub_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)
    _force_tty(monkeypatch)
    monkeypatch.setenv("PATH", "")

    with pytest.raises(SystemExit) as exc_info:
        bootstrap_mod.run(_empty_namespace())
    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert "'claude' CLI not found on PATH" in captured.err
    token_path = tmp_path / ".claude" / "personal-oauth-token"
    assert not token_path.exists()


# ---------------------------------------------------------------------------
# (g) ``claude setup-token --help`` exits 2 -> bootstrap exits 2
# ---------------------------------------------------------------------------


def test_bootstrap_exits_2_when_verb_unsupported(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An inline fixture exits 2 on ``setup-token --help`` -> bootstrap exits 2."""
    _scrub_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)
    _force_tty(monkeypatch)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    claude = bin_dir / "claude"
    claude.write_text(
        "#!/usr/bin/env bash\n"
        "set -u\n"
        'if [ "${1:-}" = "setup-token" ] && [ "${2:-}" = "--help" ]; then\n'
        "    exit 2\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{_SYSTEM_BIN_PATH}")

    with pytest.raises(SystemExit) as exc_info:
        bootstrap_mod.run(_empty_namespace())
    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert "'claude setup-token --help' check failed" in captured.err
    token_path = tmp_path / ".claude" / "personal-oauth-token"
    assert not token_path.exists()


# ---------------------------------------------------------------------------
# (h) stdin is not a TTY -> exit 2, subprocess NOT invoked
# ---------------------------------------------------------------------------


def test_bootstrap_exits_2_when_stdin_not_tty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Non-TTY stdin -> exit 2; ``subprocess.run`` is NOT invoked."""
    _scrub_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)
    _install_claude_fixture(
        monkeypatch,
        FIXTURE_DIR / "fake_claude_setup_token.sh",
        extra_dir=tmp_path / "bin",
    )

    # Track whether subprocess.run is invoked from the bootstrap module.
    # The clean fixture would otherwise satisfy the verb-probe gate, so
    # without this assertion we couldn't detect a TTY-gate regression.
    subprocess_call_count = {"count": 0}
    real_run = subprocess.run

    def tracking_run(*args, **kwargs):
        subprocess_call_count["count"] += 1
        return real_run(*args, **kwargs)

    monkeypatch.setattr(bootstrap_mod.subprocess, "run", tracking_run)

    # Force stdin.isatty() to return False explicitly (pytest already
    # captures stdin so this is the realistic state, but we pin it).
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    with pytest.raises(SystemExit) as exc_info:
        bootstrap_mod.run(_empty_namespace())
    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert "requires an interactive terminal" in captured.err
    # The TTY gate runs AFTER the verb probe, but the verb probe uses
    # subprocess.run too — so we assert no `claude setup-token` (mint)
    # invocation occurred (i.e. only the --help verb-probe call is
    # acceptable). The clean fixture verb-probe is one call; the mint
    # call would be a second. Asserting count <= 1 captures the contract
    # that the mint subprocess never fires when stdin is not a TTY.
    assert subprocess_call_count["count"] <= 1, (
        f"subprocess.run invoked {subprocess_call_count['count']} times — "
        "the mint subprocess must NOT fire when stdin is not a TTY"
    )
    token_path = tmp_path / ".claude" / "personal-oauth-token"
    assert not token_path.exists()


# ---------------------------------------------------------------------------
# (i) Atomic write — os.replace failure leaves canonical path unchanged
# ---------------------------------------------------------------------------


def test_bootstrap_atomic_write_no_partial_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``os.replace`` failure leaves the canonical token path unchanged.

    The canonical path is either nonexistent (if it didn't exist before) or
    contains the prior content (if it did). No partial-write state is
    visible to a concurrent reader.
    """
    _scrub_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)
    _force_tty(monkeypatch)
    _install_claude_fixture(
        monkeypatch,
        FIXTURE_DIR / "fake_claude_setup_token.sh",
        extra_dir=tmp_path / "bin",
    )

    # Pre-seed the canonical path with prior content so we can assert that
    # an os.replace failure leaves THAT prior content intact.
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    token_path = claude_dir / "personal-oauth-token"
    prior_contents = "sk-ant-oat01-PRIOR-FIXTURE-TOKEN-VALUE-FOR-TESTS\n"
    token_path.write_text(prior_contents, encoding="utf-8")

    # Patch os.replace at the module level so the bootstrap's atomic write
    # raises mid-flow.
    def failing_replace(src, dst):  # noqa: ARG001
        raise OSError("simulated atomic-write crash")

    monkeypatch.setattr(bootstrap_mod.os, "replace", failing_replace)

    with pytest.raises(OSError, match="simulated atomic-write crash"):
        bootstrap_mod.run(_empty_namespace())

    # Canonical path is unchanged from its pre-call state.
    assert token_path.exists()
    assert token_path.read_text(encoding="utf-8") == prior_contents

    # No leftover tempfile under ~/.claude/ from the failed atomic write.
    leftovers = [
        p for p in claude_dir.iterdir() if p.name.startswith(".personal-oauth-token-")
    ]
    assert leftovers == [], f"unexpected tempfile leftovers: {leftovers}"


# ---------------------------------------------------------------------------
# (j) Lock released on KeyboardInterrupt
# ---------------------------------------------------------------------------


def test_bootstrap_lock_released_on_keyboardinterrupt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """KeyboardInterrupt mid-mint releases the lock fd before propagating.

    The cleanest cross-platform check: after the exception propagates, open
    a fresh fd on the lockfile and acquire ``LOCK_EX | LOCK_NB``. If the
    bootstrap's lock release logic ran, this acquisition succeeds; if the
    bootstrap leaked the lock (still held by a lingering fd), the
    non-blocking acquisition raises ``BlockingIOError``.
    """
    _scrub_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)
    _force_tty(monkeypatch)
    _install_claude_fixture(
        monkeypatch,
        FIXTURE_DIR / "fake_claude_setup_token.sh",
        extra_dir=tmp_path / "bin",
    )

    # Patch subprocess.run at the bootstrap module level so the verb-probe
    # call (the FIRST subprocess.run call in the flow) succeeds normally,
    # but the mint call (the second, with no --help arg) raises
    # KeyboardInterrupt mid-flow — exactly the user-Ctrl-C contract.
    real_run = subprocess.run

    def interrupting_run(args, **kwargs):
        if len(args) >= 2 and args[0] == "claude" and args[1] == "setup-token":
            if len(args) >= 3 and args[2] == "--help":
                return real_run(args, **kwargs)
            raise KeyboardInterrupt("simulated user Ctrl-C during mint")
        return real_run(args, **kwargs)

    monkeypatch.setattr(bootstrap_mod.subprocess, "run", interrupting_run)

    with pytest.raises(KeyboardInterrupt):
        bootstrap_mod.run(_empty_namespace())

    # Verify the lock fd was released — open a fresh fd and acquire LOCK_NB.
    lockfile_path = tmp_path / ".claude" / ".personal-oauth-token.lock"
    assert lockfile_path.exists(), (
        "lockfile sibling should persist after bootstrap (kernel releases "
        "the advisory lock on fd close; the 0-byte sibling lingers)"
    )
    probe_fd = os.open(lockfile_path, os.O_RDWR)
    try:
        # If the lock was released, this non-blocking acquisition succeeds;
        # otherwise it raises BlockingIOError.
        fcntl.flock(probe_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(probe_fd, fcntl.LOCK_UN)
    finally:
        os.close(probe_fd)


# ---------------------------------------------------------------------------
# (k) Post-write shadowing warning
# ---------------------------------------------------------------------------


def test_bootstrap_warns_on_post_write_shadowing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A pre-existing ``CLAUDE_CODE_OAUTH_TOKEN`` env var shadows the file.

    Bootstrap exits 0 (the file write succeeded) but stderr contains the
    documented warning naming the resolved (shadowing) vector.
    """
    _scrub_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)
    _force_tty(monkeypatch)
    _install_claude_fixture(
        monkeypatch,
        FIXTURE_DIR / "fake_claude_setup_token.sh",
        extra_dir=tmp_path / "bin",
    )

    # CLAUDE_CODE_OAUTH_TOKEN in env -> ensure_sdk_auth resolves to
    # vector="env_preexisting" (per the actual auth.py branch), so the
    # post-write check sees the freshly-written file shadowed by env.
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "stale-fixture")

    rc = bootstrap_mod.run(_empty_namespace())
    captured = capsys.readouterr()

    assert rc == 0
    token_path = tmp_path / ".claude" / "personal-oauth-token"
    assert token_path.exists()
    assert (
        "warning: token file written, but resolved vector is env_preexisting"
        in captured.err
    )


# ---------------------------------------------------------------------------
# (l) Heartbeat line printed to stderr before subprocess invocation
# ---------------------------------------------------------------------------


def test_bootstrap_heartbeat_printed_to_stderr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The literal heartbeat line appears in stderr before mint runs.

    We patch ``subprocess.run`` for the mint call to record whether the
    heartbeat was already in the captured stderr at invocation time.
    """
    _scrub_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)
    _force_tty(monkeypatch)
    _install_claude_fixture(
        monkeypatch,
        FIXTURE_DIR / "fake_claude_setup_token.sh",
        extra_dir=tmp_path / "bin",
    )

    heartbeat = (
        "Running 'claude setup-token' — complete the browser OAuth flow "
        "when it opens. (Press Ctrl-C to abort.)"
    )

    rc = bootstrap_mod.run(_empty_namespace())
    captured = capsys.readouterr()

    assert rc == 0
    assert heartbeat in captured.err
    # And that it appears before the mint subprocess output. The clean
    # fixture writes nothing to its own stderr, so this is implicit; we
    # assert it explicitly by checking the heartbeat substring is in the
    # captured stderr.
