"""Cortex command-line entry point.

This module implements the ``cortex`` console script wired up by
``[project.scripts]`` in ``pyproject.toml``. Each subcommand is currently a
stub that fails loud (exit 2 with a stderr message) so users discover which
surfaces are not yet implemented. Real implementations land in follow-up
tickets.
"""

from __future__ import annotations

import argparse
import sys


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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex",
        description="Cortex Command CLI — orchestrates overnight runs, MCP server, and setup.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    overnight = subparsers.add_parser(
        "overnight",
        help="Run the autonomous overnight session",
        description="Launch or manage the overnight autonomous runner.",
    )
    overnight.set_defaults(func=_make_stub("overnight"))

    mcp_server = subparsers.add_parser(
        "mcp-server",
        help="Start the Cortex MCP server",
        description="Serve Cortex tools over the Model Context Protocol.",
    )
    mcp_server.set_defaults(func=_make_stub("mcp-server"))

    setup = subparsers.add_parser(
        "setup",
        help="Deploy Cortex config into the current environment",
        description="Install symlinks, hooks, and global utilities for Cortex Command.",
    )
    setup.set_defaults(func=_make_stub("setup"))

    init = subparsers.add_parser(
        "init",
        help="Initialize Cortex scaffolding in a project",
        description="Create the directory layout and starter files needed for Cortex Command.",
    )
    init.set_defaults(func=_make_stub("init"))

    upgrade = subparsers.add_parser(
        "upgrade",
        help="Upgrade the installed Cortex tool",
        description="Upgrade the Cortex Command tool and refresh deployed artifacts.",
    )
    upgrade.set_defaults(func=_make_stub("upgrade"))

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
