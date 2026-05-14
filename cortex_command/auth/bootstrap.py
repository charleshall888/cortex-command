"""Implementation of ``cortex auth bootstrap``.

This module implements the full bootstrap flow for
``restore-subscription-auth-for-autonomous-worktree``:

* **Pre-flight gates** (Task 2) — ``claude`` on PATH, ``setup-token --help``
  verb probe, stdin TTY, heartbeat line.
* **Mint + write** (Task 3) — sibling-lockfile flock, ``claude setup-token``
  invocation, regex-validated single-token capture, atomic write to
  ``~/.claude/personal-oauth-token`` with mode ``0o600``.
* **Post-write shadowing diagnostic** (Task 4) — re-runs the auth resolution
  chain via ``ensure_sdk_auth(event_log_path=None)`` and warns if a
  higher-precedence vector will silently override the freshly-written token.

See ``cortex/lifecycle/restore-subscription-auth-for-autonomous-worktree/spec.md``
for the full requirements (R2–R7, R14, R15, R16) this module satisfies.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from cortex_command.common import durable_fsync


# CONTRACT: This regex pins the assumed output shape of Anthropic's
# ``claude setup-token`` CLI — a single line containing a token of the form
# ``sk-ant-oat<digits>-<base64url-ish-suffix>``. Drift in token-prefix format
# (e.g. ``sk-ant-oat02-`` becoming ``sk-ant-oa3-``), banner placement in the
# CLI's stdout, or the addition of unrelated lines that happen to start with
# ``sk-ant-oat`` is the most likely cause of bootstrap failures. If
# ``cortex auth bootstrap`` starts emitting "did not contain a recognizable
# OAuth token" or "multiple OAuth-token candidate lines" errors, audit the
# Anthropic CLI release notes for output-shape changes and update this regex.
_TOKEN_RE = re.compile(r"^sk-ant-oat[0-9]+-[A-Za-z0-9_-]{20,}$")


def _check_claude_on_path() -> None:
    """Exit 2 if the ``claude`` CLI is not resolvable on PATH."""

    if shutil.which("claude") is None:
        print(
            "error: 'claude' CLI not found on PATH. "
            "Install Claude Code from https://code.claude.com and retry.",
            file=sys.stderr,
        )
        sys.exit(2)


def _probe_setup_token_verb() -> None:
    """Exit 2 if ``claude setup-token --help`` fails or times out."""

    try:
        completed = subprocess.run(
            ["claude", "setup-token", "--help"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        returncode_repr = "timeout"
    else:
        if completed.returncode == 0:
            return
        returncode_repr = str(completed.returncode)

    print(
        f"error: 'claude setup-token --help' check failed "
        f"(got {returncode_repr}). The verb may be unsupported, "
        "deprecated, or 'claude' may be misinstalled. Upgrade Claude "
        "Code and retry; if the issue persists run 'claude --help' to "
        "verify the verb exists.",
        file=sys.stderr,
    )
    sys.exit(2)


def _check_stdin_tty() -> None:
    """Exit 2 if stdin is not attached to a TTY."""

    if not sys.stdin.isatty():
        print(
            "error: 'cortex auth bootstrap' requires an interactive "
            "terminal (stdin is not a TTY). Run from an interactive "
            "shell.",
            file=sys.stderr,
        )
        sys.exit(2)


def _print_heartbeat() -> None:
    """Print the user-facing heartbeat line before the OAuth flow starts."""

    print(
        "Running 'claude setup-token' — complete the browser OAuth flow "
        "when it opens. (Press Ctrl-C to abort.)",
        file=sys.stderr,
        flush=True,
    )


def _token_path() -> Path:
    """Return the canonical ``~/.claude/personal-oauth-token`` path."""

    return Path("~/.claude/personal-oauth-token").expanduser()


def _claude_dir() -> Path:
    """Return the canonical ``~/.claude/`` directory path."""

    return Path("~/.claude").expanduser()


def _lockfile_path() -> Path:
    """Return the sibling lockfile path.

    Sibling-of-target naming so the lock survives the ``os.replace`` inode
    swap performed during atomic write of the token file. Mirrors the
    pattern in ``cortex_command/init/settings_merge.py:_lockfile_path``.
    """

    return _claude_dir() / ".personal-oauth-token.lock"


def _atomic_write_token(token: str) -> None:
    """Atomically write ``<token>\\n`` to ``~/.claude/personal-oauth-token``.

    Writes via tempfile-in-same-directory + ``os.replace`` so the canonical
    path is either unchanged or contains the complete new token (never a
    partial). Mode ``0o600`` is set on the tempfile **before** the rename so
    the canonical path never appears world-readable, even momentarily.
    """

    target = _token_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}-",
        suffix=".tmp",
    )
    closed = False
    try:
        os.write(fd, (token + "\n").encode("utf-8"))
        durable_fsync(fd)
        os.fchmod(fd, 0o600)
        os.close(fd)
        closed = True
        os.replace(tmp_path, target)
    except BaseException:
        if not closed:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _mint_and_write() -> int:
    """Run ``claude setup-token``, parse, and atomically write the token.

    Caller has already invoked the pre-flight gates and printed the
    heartbeat. This function performs the lock acquisition, subprocess
    invocation, output parsing, and atomic write. Returns an exit code.
    """

    # Reject pre-existing directory shape before any locking — destructive
    # remediation (rmtree) is intentionally NOT automated; surface a clear
    # error so the user removes it manually.
    token_target = _token_path()
    if token_target.exists() and token_target.is_dir():
        print(
            f"error: {token_target} exists as a directory; refusing to "
            "overwrite. Remove the directory manually (e.g. "
            f"'rmdir {token_target}' if empty, or inspect its contents "
            "first) and retry.",
            file=sys.stderr,
        )
        return 2

    # Ensure ~/.claude/ exists with mode 0o755 before opening the lockfile —
    # os.open(..., O_CREAT) inside a missing parent directory would fail.
    claude_dir = _claude_dir()
    claude_dir.mkdir(mode=0o755, parents=True, exist_ok=True)

    lockfile_path = _lockfile_path()
    lock_fd = os.open(
        lockfile_path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600
    )
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        # `start_new_session=False` is the default; specified explicitly
        # so the SIGINT-propagation contract is documented in code: the
        # `claude` child shares the parent's process group, so terminal
        # Ctrl-C reaches both processes. `stderr=None` inherits parent
        # stderr so the user sees the OAuth URL the CLI prints; this is
        # mutually exclusive with `capture_output=True` (which forces
        # stderr=PIPE) — DO NOT swap to `capture_output`.
        completed = subprocess.run(
            ["claude", "setup-token"],
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            check=False,
            start_new_session=False,
        )

        if completed.returncode != 0:
            print(
                f"error: 'claude setup-token' exited with code "
                f"{completed.returncode}; no token written. Common "
                "causes: the verb may have been renamed or its output "
                "format changed in your installed Claude Code version; "
                "run 'claude --help' to verify and consider upgrading.",
                file=sys.stderr,
            )
            return completed.returncode

        # Scan all non-blank lines for token matches (per spec R3 — the
        # "last non-blank line" heuristic is defeated by trailing upgrade
        # banners).
        matches = [
            line
            for line in (completed.stdout or "").splitlines()
            if _TOKEN_RE.match(line.strip()) is not None
        ]
        # Re-strip captured matches to discard accidental surrounding
        # whitespace; the regex is anchored, so .strip() preserves the
        # match payload.
        matches = [m.strip() for m in matches]

        if len(matches) == 0:
            print(
                "error: claude setup-token output did not contain a "
                "recognizable OAuth token (output format may have "
                "changed)",
                file=sys.stderr,
            )
            return 2

        if len(matches) > 1:
            print(
                "error: claude setup-token output contained multiple "
                "OAuth-token candidate lines; refusing to guess",
                file=sys.stderr,
            )
            return 2

        _atomic_write_token(matches[0])
        return 0
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


def _warn_if_shadowed() -> None:
    """Warn (non-fatally) if a higher-precedence auth vector shadows the file.

    Re-runs the SDK auth resolution chain via
    :func:`cortex_command.overnight.auth.ensure_sdk_auth` (with
    ``event_log_path=None`` so the routine call's status line goes to stderr,
    not an event log) and inspects the resolved vector. If any vector other
    than ``oauth_file`` wins, the freshly-minted token sitting in
    ``~/.claude/personal-oauth-token`` will be silently overridden — the user
    needs to know.

    Bootstrap still exits 0; the file write itself succeeded. The warning is
    purely informational. Import is lazy (inside the function) to keep the
    package's import-time cost low, mirroring the pattern in
    ``cortex_command/auth/status.py``.
    """

    # Lazy import: keeps top-of-module import cost low and matches the
    # convention established in cortex_command/auth/status.py:167.
    from cortex_command.overnight.auth import ensure_sdk_auth

    info = ensure_sdk_auth(event_log_path=None)
    vector = info.get("vector")
    if vector != "oauth_file":
        print(
            f"warning: token file written, but resolved vector is "
            f"{vector} — your fresh subscription token will be shadowed "
            f"by {vector}. Run 'cortex auth status' to investigate.",
            file=sys.stderr,
        )


def run(_args: argparse.Namespace) -> int:
    """Entry point for ``cortex auth bootstrap``."""

    _check_claude_on_path()
    _probe_setup_token_verb()
    _check_stdin_tty()
    _print_heartbeat()

    exit_code = _mint_and_write()
    if exit_code == 0:
        # Post-write shadowing diagnostic (Requirement 16). Runs ONLY on
        # successful write; on failure the file state is unchanged so there
        # is no fresh token to be shadowed. Warning is non-fatal — bootstrap
        # still exits 0 because the file write itself succeeded.
        _warn_if_shadowed()
    return exit_code
