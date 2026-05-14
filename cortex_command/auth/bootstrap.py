"""Implementation of ``cortex auth bootstrap``.

This module currently implements Task 2 of the
``restore-subscription-auth-for-autonomous-worktree`` feature: pre-flight
gates that must succeed before any state-changing work runs. The actual
``claude setup-token`` invocation, atomic write, and lock handling land
in Task 3 (see
``cortex/lifecycle/restore-subscription-auth-for-autonomous-worktree/spec.md``).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys


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


def run(_args: argparse.Namespace) -> int:
    """Entry point for ``cortex auth bootstrap``."""

    _check_claude_on_path()
    _probe_setup_token_verb()
    _check_stdin_tty()
    _print_heartbeat()

    print("error: not implemented (mint phase pending)", file=sys.stderr)
    return 2
