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


def _dispatch_overnight_list_sessions(args: argparse.Namespace) -> int:
    from cortex_command.overnight import cli_handler

    return cli_handler.handle_list_sessions(args)


_MCP_SERVER_DEPRECATION_BASE = (
    "cortex mcp-server is removed; install the cortex-overnight-integration "
    "plugin (/plugin install cortex-overnight-integration@cortex-command) "
    "and update your .mcp.json to point at uv run ${CLAUDE_PLUGIN_ROOT}/server.py"
)

_MCP_SERVER_RESTART_ADVISORY = (
    " Restart Claude Code after editing your .mcp.json — existing sessions "
    "will not pick up the change automatically."
)

_MCP_SERVER_T12_VERDICT_PATH = (
    "lifecycle/decouple-mcp-server-from-cli-python-imports-own-auto-update-"
    "orchestration/plugin-refresh-semantics.md"
)


def _read_t12_restart_required() -> bool:
    """Return True iff T12's verdict indicates session-restart-required.

    Locates ``plugin-refresh-semantics.md`` relative to the resolved
    ``cortex_root`` and parses the trailing ``## Verdict`` section. Any
    error (file missing, parse failure, root unresolvable) yields False so
    the deprecation stub still emits the baseline message.
    """

    import os
    from pathlib import Path

    try:
        override = os.environ.get("CORTEX_COMMAND_ROOT")
        if override:
            root = Path(override)
        else:
            try:
                import cortex_command

                pkg_file = getattr(cortex_command, "__file__", None)
                if pkg_file:
                    candidate = Path(pkg_file).resolve().parent.parent
                    if (candidate / "pyproject.toml").is_file():
                        root = candidate
                    else:
                        root = Path.home() / ".cortex"
                else:
                    root = Path.home() / ".cortex"
            except Exception:
                root = Path.home() / ".cortex"

        verdict_file = root / _MCP_SERVER_T12_VERDICT_PATH
        if not verdict_file.is_file():
            return False
        text = verdict_file.read_text(encoding="utf-8")
        # Find the last "## Verdict" section and read the verdict line that
        # follows it (the conventional shape — see plugin-refresh-semantics.md).
        marker = "## Verdict"
        idx = text.rfind(marker)
        if idx < 0:
            return False
        tail = text[idx + len(marker):]
        for line in tail.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            return stripped == "session_restart_required"
        return False
    except Exception:
        return False


def _dispatch_mcp_server(_args: argparse.Namespace) -> int:
    """Deprecation stub for the removed ``cortex mcp-server`` verb (R7).

    The MCP server now ships as a plugin-bundled PEP 723 single-file at
    ``plugins/cortex-overnight-integration/server.py`` invoked via
    ``uv run ${CLAUDE_PLUGIN_ROOT}/server.py`` from the plugin's ``.mcp.json``.
    A user who manually runs ``cortex mcp-server`` from a terminal sees this
    migration message in their shell. Claude Code does NOT surface MCP-server
    stderr to users (verified via Claude Code GitHub issues #25751, #34744,
    #17653) — the failure is shown as a generic "MCP server failed" status —
    so this stderr message is a terminal-debugging channel, not a Claude
    Code UI channel.
    """

    message = _MCP_SERVER_DEPRECATION_BASE
    if _read_t12_restart_required():
        message = message + _MCP_SERVER_RESTART_ADVISORY
    print(message, file=sys.stderr)
    return 1


def _resolve_cortex_root() -> str:
    """Resolve the absolute path to the Cortex Command checkout (R3, R16).

    Discovery chain:
      1. ``CORTEX_COMMAND_ROOT`` env var (override).
      2. Editable-install ``.pth`` resolution — the ``cortex_command`` package
         is imported from the checkout, so ``cortex_command.__file__`` points
         into the editable source tree; its parent's parent is the repo root.
      3. ``$HOME/.cortex`` default.
      4. Hard-fail with a clear stderr message if none of the above resolve
         to an existing directory.
    """

    import os
    from pathlib import Path

    override = os.environ.get("CORTEX_COMMAND_ROOT")
    if override:
        return str(Path(override).resolve())

    try:
        import cortex_command

        pkg_file = getattr(cortex_command, "__file__", None)
        if pkg_file:
            candidate = Path(pkg_file).resolve().parent.parent
            if (candidate / "pyproject.toml").is_file():
                return str(candidate)
    except Exception:  # pragma: no cover - defensive: import-time edge cases
        pass

    home_default = Path.home() / ".cortex"
    if home_default.is_dir():
        return str(home_default)

    print(
        "cortex: unable to resolve cortex_root; set CORTEX_COMMAND_ROOT or "
        "install via `uv tool install -e <path>`",
        file=sys.stderr,
    )
    sys.exit(1)


def _dispatch_print_root(_args: argparse.Namespace) -> int:
    """Emit versioned JSON describing this Cortex install (R3, R16).

    The JSON shape — ``version``, ``root``, ``remote_url``, ``head_sha`` — is
    forever-public-API: append-only after publication; existing fields never
    change semantics or types without a major bump.
    """

    import json
    import subprocess

    root = _resolve_cortex_root()

    # Per spec Technical Constraints, no `check=True` on shell-outs here.
    remote_proc = subprocess.run(
        ["git", "-C", root, "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    remote_url = remote_proc.stdout.strip() if remote_proc.returncode == 0 else ""

    head_proc = subprocess.run(
        ["git", "-C", root, "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    head_sha = head_proc.stdout.strip() if head_proc.returncode == 0 else ""

    payload = {
        "version": "1.0",
        "root": root,
        "remote_url": remote_url,
        "head_sha": head_sha,
    }
    print(json.dumps(payload))
    return 0


def _dispatch_upgrade(args: argparse.Namespace) -> int:
    import os
    import subprocess
    from pathlib import Path

    from cortex_command.install_guard import check_in_flight_install

    check_in_flight_install()

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
    # Post-upgrade migration notice (R7 / Task 14). Proactive channel for
    # users who upgrade before noticing that their .mcp.json still points at
    # the removed `cortex mcp-server` verb.
    print(
        "Note: if you have a stale .mcp.json from before this upgrade, "
        "update it to point at uv run ${CLAUDE_PLUGIN_ROOT}/server.py — "
        "see docs/mcp-contract.md.",
        file=sys.stderr,
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex",
        description="Cortex Command CLI — orchestrates overnight runs and the MCP server.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Top-level --print-root flag (R3, R16) — emits versioned JSON to stdout
    # describing this Cortex install. Forever-public-API: append-only.
    parser.add_argument(
        "--print-root",
        dest="print_root",
        action="store_true",
        help="Print versioned JSON {version, root, remote_url, head_sha} and exit",
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
    start.add_argument(
        "--format",
        choices=("human", "json"),
        default="human",
        help="Output format (default: human). 'json' emits versioned JSON on collisions.",
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
    cancel.add_argument(
        "--format",
        choices=("human", "json"),
        default="human",
        help="Output format (default: human)",
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
    logs.add_argument(
        "--format",
        choices=("human", "json"),
        default="human",
        help="Output format (default: human)",
    )
    logs.set_defaults(func=_dispatch_overnight_logs)

    # cortex overnight list-sessions (R2 — MCP support verb)
    list_sessions = overnight_sub.add_parser(
        "list-sessions",
        help="List active and recent overnight sessions",
        description=(
            "List overnight sessions discovered under "
            "lifecycle/sessions/. Active sessions (planning, executing, "
            "paused) and recent sessions (complete) are partitioned in "
            "the JSON output."
        ),
    )
    list_sessions.add_argument(
        "--status",
        action="append",
        choices=("planning", "executing", "paused", "complete"),
        default=None,
        help="Filter by phase; repeatable (default: include all phases)",
    )
    list_sessions.add_argument(
        "--since",
        type=str,
        default=None,
        help="Only include sessions whose updated_at is at or after this ISO-8601 timestamp",
    )
    list_sessions.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Cap on the number of recent (non-active) sessions to return (default: 10)",
    )
    list_sessions.add_argument(
        "--format",
        choices=("human", "json"),
        default="human",
        help="Output format (default: human)",
    )
    list_sessions.set_defaults(func=_dispatch_overnight_list_sessions)

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

    # Intercept --print-root before subcommand dispatch (R3).
    if getattr(args, "print_root", False):
        return _dispatch_print_root(args)

    if not getattr(args, "func", None):
        parser.print_help(sys.stderr)
        return 2

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
