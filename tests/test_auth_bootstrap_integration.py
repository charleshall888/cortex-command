"""Integration smoke test for ``cortex auth bootstrap`` (Task 11 / Requirement 13).

Exercises the full ``cli.py → bootstrap.py → auth.py`` chain end-to-end at the
Python / argparse-dispatch level, without ``pty.openpty()``. Two coverage
boundaries:

  (1) ``test_bootstrap_tty_rejection_via_subprocess`` — spawns
      ``python -m cortex_command.cli auth bootstrap`` with ``stdin=DEVNULL`` and
      asserts the TTY gate rejects with exit 2 and the expected stderr
      message. Exercises the cli.py argparse subparser dispatch + bootstrap.py
      TTY gate via a real subprocess.

  (2) ``test_bootstrap_full_chain_writes_token_and_resolves_oauth_file`` —
      patches ``pathlib.Path.home`` (and ``HOME`` env var, per Task 9 learnings)
      to a tmp dir, lifts the TTY gate by patching ``sys.stdin.isatty``,
      installs the Task-8 fake ``claude`` fixture on PATH, then invokes
      ``cli.main(["auth", "bootstrap"])`` directly. Asserts:
        * ``~/.claude/personal-oauth-token`` exists with mode 0o600 and the
          expected content.
        * ``ensure_sdk_auth`` resolves to ``vector="oauth_file"``.
        * ``cli.main(["auth", "status"])`` prints ``vector: oauth_file`` and
          does NOT print a ``shadowed:`` line.

Marked ``@pytest.mark.serial`` because the in-process test mutates global state
(``pathlib.Path.home``, ``sys.stdin.isatty``, env vars, PATH) and the
subprocess test spawns a real subprocess.

The ``[sys.executable, "-m", "cortex_command.cli"]`` invocation pattern follows
the precedent established in ``tests/test_cli_dashboard.py``,
``tests/test_cortex_overnight_security.py``,
``tests/test_runner_followup_commit.py``, and
``tests/test_cli_mcp_server_deprecated.py``.
"""

from __future__ import annotations

import os
import pathlib
import stat
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.serial


# ---------------------------------------------------------------------------
# Fixture helpers — mirror the patterns in tests/test_auth_bootstrap.py
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

# Minimal system PATH that resolves ``/usr/bin/env`` and ``bash`` for the
# fixture's ``#!/usr/bin/env bash`` shebang. Restricting PATH to ONLY the
# fixture directory yields ENOENT on exec (kernel exec needs ``/usr/bin/env``
# and ``bash`` resolvable somewhere on PATH).
_SYSTEM_BIN_PATH = "/usr/bin:/bin"

EXPECTED_TOKEN = "sk-ant-oat01-FIXTURE-TOKEN-VALUE-FOR-TESTS-ONLY"


def _scrub_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip auth env vars that could short-circuit ``ensure_sdk_auth``."""
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)


def _redirect_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    """Point both ``Path.home()`` and ``HOME`` at ``home``.

    Both redirects are required because ``cortex_command/auth/bootstrap.py``
    uses ``Path("~/...").expanduser()`` (consults ``$HOME``) while
    ``cortex_command/overnight/auth.py`` uses ``Path.home()``. See the
    ``_redirect_home`` docstring in ``tests/test_auth_bootstrap.py`` for the
    longer rationale.
    """
    monkeypatch.setattr(pathlib.Path, "home", lambda: home)
    monkeypatch.setenv("HOME", str(home))


def _install_claude_fixture(
    monkeypatch: pytest.MonkeyPatch,
    fixture_path: Path,
    install_dir: Path,
) -> Path:
    """Install ``fixture_path`` as ``claude`` on a controlled PATH.

    Symlinks the fixture into ``install_dir`` under the name ``claude`` and
    sets ``PATH=<install_dir>:/usr/bin:/bin``. Returns the install dir.
    """
    install_dir.mkdir(parents=True, exist_ok=True)
    claude_link = install_dir / "claude"
    if claude_link.exists() or claude_link.is_symlink():
        claude_link.unlink()
    claude_link.symlink_to(fixture_path)
    monkeypatch.setenv("PATH", f"{install_dir}:{_SYSTEM_BIN_PATH}")
    return install_dir


# ---------------------------------------------------------------------------
# (1) Subprocess test — TTY rejection via real ``python -m cortex_command.cli``
# ---------------------------------------------------------------------------


def test_bootstrap_tty_rejection_via_subprocess(tmp_path: Path) -> None:
    """``cortex auth bootstrap`` with stdin=DEVNULL exits 2 with the TTY error.

    Spawns a real subprocess via ``python -m cortex_command.cli`` to exercise
    the cli.py argparse subparser dispatch + bootstrap.py TTY gate without
    relying on ``pty.openpty()``.
    """
    install_dir = tmp_path / "bin"
    install_dir.mkdir(parents=True, exist_ok=True)
    claude_link = install_dir / "claude"
    claude_link.symlink_to(FIXTURE_DIR / "fake_claude_setup_token.sh")

    test_env = os.environ.copy()
    # Redirect HOME so any token-write attempt (which must NOT happen because
    # the TTY gate fires first) lands in the test's tmp dir.
    test_env["HOME"] = str(tmp_path)
    # Prepend the fixture dir but keep /usr/bin:/bin so the fixture's
    # ``#!/usr/bin/env bash`` shebang resolves (per the Task-9 learning).
    test_env["PATH"] = f"{install_dir}:{_SYSTEM_BIN_PATH}"
    # Strip auth env vars so the subprocess can't short-circuit on a
    # developer-set token before the TTY gate fires.
    for var in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
        test_env.pop(var, None)

    completed = subprocess.run(
        [sys.executable, "-m", "cortex_command.cli", "auth", "bootstrap"],
        stdin=subprocess.DEVNULL,
        env=test_env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 2, (
        f"expected exit code 2, got {completed.returncode}; "
        f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
    )
    assert "requires an interactive terminal" in completed.stderr, (
        f"stderr missing TTY-rejection message: {completed.stderr!r}"
    )
    # The token file must NOT have been written — the TTY gate fires before
    # any mint subprocess invocation.
    token_path = tmp_path / ".claude" / "personal-oauth-token"
    assert not token_path.exists(), (
        f"token file should not exist after TTY rejection; found at {token_path}"
    )


# ---------------------------------------------------------------------------
# (2) In-process test — full cli → bootstrap → auth → status chain
# ---------------------------------------------------------------------------


def test_bootstrap_full_chain_writes_token_and_resolves_oauth_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End-to-end: cli bootstrap writes the file; auth resolves to oauth_file;
    cli status reports vector=oauth_file with no shadowing.

    Invokes ``cli.main(["auth", "bootstrap"])`` and ``cli.main(["auth",
    "status"])`` directly so the test exercises the same argparse subparser
    dispatch the console-script entry uses, without paying the cost of (or
    risking staleness in) the ``uv tool install`` shim layer. Per the spec's
    Requirement 13, this is "end-to-end at the Python level".
    """
    from cortex_command import cli as cli_mod
    from cortex_command.overnight import auth as overnight_auth_mod

    _scrub_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)

    # Lift the TTY gate — pytest captures stdin so isatty() returns False; the
    # subprocess test above already covers the rejection path.
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    _install_claude_fixture(
        monkeypatch,
        FIXTURE_DIR / "fake_claude_setup_token.sh",
        install_dir=tmp_path / "bin",
    )

    # ---- Phase 1: bootstrap writes the token file ----
    rc_bootstrap = cli_mod.main(["auth", "bootstrap"])
    assert rc_bootstrap == 0, f"expected bootstrap exit 0, got {rc_bootstrap}"

    token_path = tmp_path / ".claude" / "personal-oauth-token"
    assert token_path.exists(), f"token file not created at {token_path}"

    mode = stat.S_IMODE(token_path.stat().st_mode)
    assert mode == 0o600, f"expected mode 0o600, got {oct(mode)}"

    contents = token_path.read_text(encoding="utf-8")
    assert contents == EXPECTED_TOKEN + "\n", (
        f"unexpected token file contents: {contents!r}"
    )

    # Drain bootstrap's captured stderr (heartbeat + ensure_sdk_auth message)
    # so the status-phase capsys read below sees only status output.
    capsys.readouterr()

    # ---- Phase 2: ensure_sdk_auth resolves to oauth_file ----
    # bootstrap's post-write shadowing check writes CLAUDE_CODE_OAUTH_TOKEN
    # into os.environ as part of resolving the oauth_file branch. Strip it so
    # this independent ensure_sdk_auth invocation re-resolves from the file
    # instead of short-circuiting on the env var (which would resolve to
    # ``env_preexisting``, masking the file-resolution path the test exists
    # to verify).
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

    info = overnight_auth_mod.ensure_sdk_auth(event_log_path=None)
    assert info["vector"] == "oauth_file", (
        f"expected vector=oauth_file, got vector={info['vector']!r}; "
        f"message={info.get('message')!r}"
    )

    # Drain any stderr emitted by ensure_sdk_auth so the status-phase capsys
    # read sees only the status handler's stdout.
    capsys.readouterr()

    # ---- Phase 3: cortex auth status reports oauth_file with no shadowing ----
    # Strip CLAUDE_CODE_OAUTH_TOKEN again — the ensure_sdk_auth call above
    # re-wrote it into os.environ. status.py's _capture_env_state would
    # otherwise observe the auto-populated env var as "shadowing", which is
    # the exact failure mode this test guards against.
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

    rc_status = cli_mod.main(["auth", "status"])
    assert rc_status == 0, f"expected status exit 0, got {rc_status}"

    captured = capsys.readouterr()
    assert "vector: oauth_file" in captured.out, (
        f"status stdout missing 'vector: oauth_file': {captured.out!r}"
    )
    assert "shadowed:" not in captured.out, (
        f"status stdout unexpectedly contains 'shadowed:': {captured.out!r}"
    )
