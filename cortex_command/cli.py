"""Cortex command-line entry point.

This module implements the ``cortex`` console script wired up by
``[project.scripts]`` in ``pyproject.toml``. Subcommands not yet
implemented are stubbed to fail loud (exit 2 with a stderr message) so
users discover which surfaces are not yet implemented. The ``overnight``
subcommand is fully wired to :mod:`cortex_command.overnight.cli_handler`
per R1-R4 / R20.
"""

from __future__ import annotations

import argparse
import sys

from cortex_command.init.handler import main as init_main


EPILOG = """\
Notes:
  * The `cortex` command invokes `uv run` against the user's current project,
    not the tool's own virtualenv. Run it from inside the project whose
    dependencies you want resolved.
  * Adding or changing `[project.scripts]` entries requires reinstalling the
    tool with `uv tool install -e . --force` so the console scripts are
    regenerated.
  * First-time setup also requires running `uv tool update-shell` once so the
    uv-managed bin directory is on PATH.
"""


def _make_stub(name: str):
    """Build a stub handler that reports the command is not yet implemented."""

    def _stub(_args: argparse.Namespace) -> int:
        print(f"not yet implemented: cortex {name}", file=sys.stderr)
        sys.exit(2)

    return _stub


# ---------------------------------------------------------------------------
# Overnight dispatchers — lazy-import cli_handler so `--help` invocations
# stay fast and don't pay the cost of the orchestration graph.
# ---------------------------------------------------------------------------

def _dispatch_overnight_start(args: argparse.Namespace) -> int:
    from cortex_command.overnight import cli_handler

    return cli_handler.handle_start(args)


def _dispatch_overnight_status(args: argparse.Namespace) -> int:
    from cortex_command.overnight import cli_handler

    return cli_handler.handle_status(args)


def _dispatch_overnight_cancel(args: argparse.Namespace) -> int:
    from cortex_command.overnight import cli_handler

    return cli_handler.handle_cancel(args)


def _dispatch_overnight_logs(args: argparse.Namespace) -> int:
    from cortex_command.overnight import cli_handler

    return cli_handler.handle_logs(args)


def _dispatch_mcp_server(_args: argparse.Namespace) -> int:
    """Launch the stdio MCP control-plane server (R1).

    Imports :mod:`cortex_command.mcp_server.server` lazily so ``cortex
    --help`` and other subcommands do not pay the ``mcp`` SDK import
    cost. Blocks until the transport closes.
    """

    from cortex_command.mcp_server.server import build_server

    build_server().run(transport="stdio")
    return 0


def _dispatch_upgrade(args: argparse.Namespace) -> int:
    import os
    import subprocess
    from pathlib import Path

    cortex_root = os.environ.get("CORTEX_COMMAND_ROOT") or str(Path.home() / ".cortex")
    try:
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cortex_root,
            check=True,
            capture_output=True,
            text=True,
        )
        if dirty.stdout.strip():
            print(
                f"uncommitted changes in {cortex_root}; commit or stash before upgrading",
                file=sys.stderr,
            )
            return 1
        subprocess.run(
            ["git", "-C", cortex_root, "pull", "--ff-only"],
            check=True,
        )
        # --force regenerates console scripts per the EPILOG note (see cli.py:21-23).
        subprocess.run(
            ["uv", "tool", "install", "-e", cortex_root, "--force"],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"command failed: {' '.join(exc.cmd)}", file=sys.stderr)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex",
        description="Cortex Command CLI — orchestrates overnight runs and the MCP server.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    # -------------------------------------------------------------------
    # cortex overnight — R1-R4 subcommand surface.
    # -------------------------------------------------------------------
    overnight = subparsers.add_parser(
        "overnight",
        help="Run the autonomous overnight session",
        description="Launch or manage the overnight autonomous runner.",
    )
    overnight_sub = overnight.add_subparsers(
        dest="overnight_command",
        required=True,
        metavar="<subcommand>",
    )

    # cortex overnight start (R1)
    start = overnight_sub.add_parser(
        "start",
        help="Start an overnight session",
        description="Start the autonomous overnight round-dispatch loop.",
    )
    start.add_argument(
        "--state",
        type=str,
        default=None,
        help="Path to overnight-state.json (default: auto-discover in cwd's repo)",
    )
    start.add_argument(
        "--time-limit",
        dest="time_limit",
        type=int,
        default=None,
        help="Wall-clock budget in seconds (default: no limit)",
    )
    start.add_argument(
        "--max-rounds",
        dest="max_rounds",
        type=int,
        default=None,
        help="Round-count budget (default: current_round + 10)",
    )
    start.add_argument(
        "--tier",
        choices=("simple", "complex"),
        default="simple",
        help="Throttle tier passed to the orchestrator and batch_runner",
    )
    start.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Simulate without spawning agents; rejects state with pending features",
    )
    start.set_defaults(func=_dispatch_overnight_start)

    # cortex overnight status (R2)
    status = overnight_sub.add_parser(
        "status",
        help="Print session status",
        description="Print the current overnight session status.",
    )
    status.add_argument(
        "--format",
        choices=("human", "json"),
        default="human",
        help="Output format (default: human)",
    )
    status.add_argument(
        "--session-dir",
        dest="session_dir",
        type=str,
        default=None,
        help="Override the session directory (default: active-session pointer)",
    )
    status.set_defaults(func=_dispatch_overnight_status)

    # cortex overnight cancel (R3)
    cancel = overnight_sub.add_parser(
        "cancel",
        help="Cancel an active session",
        description="Cancel the active overnight session via SIGTERM to its PGID.",
    )
    cancel.add_argument(
        "session_id",
        nargs="?",
        default=None,
        help="Session-id to cancel (default: active-session pointer)",
    )
    cancel.add_argument(
        "--session-dir",
        dest="session_dir",
        type=str,
        default=None,
        help="Override the session directory (default: active-session pointer)",
    )
    cancel.set_defaults(func=_dispatch_overnight_cancel)

    # cortex overnight logs (R4)
    logs = overnight_sub.add_parser(
        "logs",
        help="Read session logs",
        description="Read events.log / agent-activity.jsonl / escalations.jsonl.",
    )
    logs.add_argument(
        "session_id",
        nargs="?",
        default=None,
        help="Session-id to read (default: active-session pointer)",
    )
    logs.add_argument(
        "--tail",
        type=int,
        default=20,
        help="Read the last N lines when no --since cursor is given (default: 20)",
    )
    logs.add_argument(
        "--since",
        type=str,
        default=None,
        help="Cursor: RFC3339 timestamp or @<byte-offset>",
    )
    logs.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Cap on total returned lines (default: 500)",
    )
    logs.add_argument(
        "--files",
        choices=("events", "agent-activity", "escalations"),
        default="events",
        help="Log stream to read (default: events)",
    )
    logs.add_argument(
        "--session-dir",
        dest="session_dir",
        type=str,
        default=None,
        help="Override the session directory (default: active-session pointer)",
    )
    logs.set_defaults(func=_dispatch_overnight_logs)

    # -------------------------------------------------------------------
    # Remaining stubs — not yet implemented.
    # -------------------------------------------------------------------
    mcp_server = subparsers.add_parser(
        "mcp-server",
        help="Start the Cortex MCP server",
        description=(
            "Serve the Cortex overnight control-plane tools over the "
            "Model Context Protocol via stdio. Intended to be launched "
            "by a Claude Code client via `claude mcp add` or the "
            "cortex-overnight-integration plugin, not run interactively."
        ),
    )
    mcp_server.set_defaults(func=_dispatch_mcp_server)

    init = subparsers.add_parser(
        "init",
        help="Initialize Cortex scaffolding in a project",
        description="Create the directory layout and starter files needed for Cortex Command.",
    )
    init.add_argument(
        "--path",
        default=None,
        help="Target repo root (defaults to CWD)",
    )
    init_verbs = init.add_mutually_exclusive_group()
    init_verbs.add_argument(
        "--update",
        action="store_true",
        help="Refresh managed files in an already-initialized repo",
    )
    init_verbs.add_argument(
        "--force",
        action="store_true",
        help="Overwrite managed files, including local edits",
    )
    init_verbs.add_argument(
        "--unregister",
        action="store_true",
        help="Remove the repo from the Cortex registry without modifying files",
    )
    init.set_defaults(func=init_main)

    upgrade = subparsers.add_parser(
        "upgrade",
        help="Upgrade the installed Cortex tool",
        description="Upgrade the Cortex Command tool and refresh deployed artifacts.",
    )
    upgrade.set_defaults(func=_dispatch_upgrade)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point invoked by the ``cortex`` console script."""

    parser = _build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if not getattr(args, "func", None):
        parser.print_help(sys.stderr)
        return 2

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
