#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "mcp>=1.27,<2",
# ]
# ///
"""R18 sandbox empirical probe — minimal MCP server.

Spec reference: lifecycle/decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration/spec.md R18.

This MCP server exposes a single tool, `run_probe`, that exercises the four
sandbox-sensitive operations R10–R14 will perform from MCP tool handler context:
    1. Filesystem write to `$cortex_root/.git/.cortex-write-probe` via Path.touch().
    2. fcntl.flock(LOCK_EX) acquisition + release on `$cortex_root/.git/cortex-update.lock`.
    3. `uv tool install -e <cortex_root> --force` and verification of the resulting
       writes at `~/.local/share/uv/tools/cortex-command/lib/` and `~/.local/bin/cortex`.
    4. `cortex --print-root` and `cortex overnight status --format json <empty>` against
       an empty/unknown session id; both must exit 0 with parseable JSON.

CRITICAL: this probe MUST be launched as an MCP server by Claude Code's
MCP-launch path (e.g., registered in .mcp.json, then invoked via the
`run_probe` tool from a real Claude Code session). It MUST NOT be invoked via
Claude Code's `Bash` tool — that inherits a different sandbox surface and the
results would not reflect the production R10–R14 execution context.

Usage (manual user step):
    1. Register this server in your Claude Code session, e.g. by adding to
       a `.mcp.json` (project-local or global):
           {
             "mcpServers": {
               "r18-probe": {
                 "command": "uv",
                 "args": [
                   "run",
                   "--script",
                   "/Users/charlie.hall/Workspaces/cortex-command/lifecycle/decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration/probe-mcp.py"
                 ]
               }
             }
           }
       (Or use `claude mcp add` equivalent.)
    2. Restart Claude Code so the MCP server registers.
    3. Invoke the `run_probe` tool (no arguments needed; defaults are correct
       for the user's environment). Optionally pass `cortex_root` to override.
    4. Paste the returned JSON into `sandbox-probe-result.md`'s
       Operation Results section, then set the verdict.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP


DEFAULT_CORTEX_ROOT = "/Users/charlie.hall/Workspaces/cortex-command"

mcp = FastMCP("r18-probe")


def _resolve_cortex_root(override: str | None) -> str:
    if override:
        return override
    env_root = os.environ.get("CORTEX_COMMAND_ROOT")
    if env_root:
        return env_root
    return DEFAULT_CORTEX_ROOT


def _op1_filesystem_write(cortex_root: str) -> dict[str, Any]:
    """Op 1: Path(f'{cortex_root}/.git/.cortex-write-probe').touch()."""
    result: dict[str, Any] = {"op": 1, "name": "filesystem_write_to_dot_git"}
    try:
        probe_path = Path(cortex_root) / ".git" / ".cortex-write-probe"
        probe_path.touch()
        result["status"] = "ok"
        result["path"] = str(probe_path)
        result["error"] = None
    except Exception as exc:  # noqa: BLE001 — capture every failure mode
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _op2_flock(cortex_root: str) -> dict[str, Any]:
    """Op 2: fcntl.flock(LOCK_EX) on cortex-update.lock, then release."""
    result: dict[str, Any] = {"op": 2, "name": "flock_acquire_release"}
    lock_path = Path(cortex_root) / ".git" / "cortex-update.lock"
    fd = None
    try:
        # Ensure parent .git/ exists; lock_path itself is created with O_CREAT.
        flags = os.O_RDWR | os.O_CREAT
        fd = os.open(str(lock_path), flags, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            result["status"] = "ok"
            result["path"] = str(lock_path)
            result["error"] = None
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    except Exception as exc:  # noqa: BLE001
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
    return result


def _op3_uv_tool_install(cortex_root: str) -> dict[str, Any]:
    """Op 3: `uv tool install -e <cortex_root> --force`, verify install paths."""
    result: dict[str, Any] = {"op": 3, "name": "uv_tool_install_force"}
    try:
        proc = subprocess.run(
            ["uv", "tool", "install", "-e", str(cortex_root), "--force"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        result["exit_code"] = proc.returncode
        result["stdout"] = proc.stdout
        result["stderr"] = proc.stderr
        lib_path = os.path.expanduser("~/.local/share/uv/tools/cortex-command/lib")
        bin_path = os.path.expanduser("~/.local/bin/cortex")
        result["lib_exists"] = os.path.exists(lib_path)
        result["bin_exists"] = os.path.exists(bin_path)
        result["lib_path"] = lib_path
        result["bin_path"] = bin_path
        if proc.returncode == 0 and result["lib_exists"] and result["bin_exists"]:
            result["status"] = "ok"
            result["error"] = None
        else:
            result["status"] = "error"
            result["error"] = (
                f"exit={proc.returncode}, "
                f"lib_exists={result['lib_exists']}, "
                f"bin_exists={result['bin_exists']}"
            )
    except Exception as exc:  # noqa: BLE001
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _op4_cortex_subprocess() -> dict[str, Any]:
    """Op 4: cortex --print-root AND cortex overnight status --format json <empty>."""
    result: dict[str, Any] = {"op": 4, "name": "cortex_subprocess_post_upgrade"}
    sub_results: dict[str, Any] = {}

    # Op 4a: cortex --print-root
    try:
        proc_a = subprocess.run(
            ["cortex", "--print-root"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        sub_results["print_root"] = {
            "exit_code": proc_a.returncode,
            "stdout": proc_a.stdout,
            "stderr": proc_a.stderr,
        }
    except Exception as exc:  # noqa: BLE001
        sub_results["print_root"] = {
            "exit_code": None,
            "stdout": None,
            "stderr": None,
            "error": f"{type(exc).__name__}: {exc}",
        }

    # Op 4b: cortex overnight status --format json <empty session id>
    # Use the literal empty string as the session id per task brief.
    try:
        proc_b = subprocess.run(
            ["cortex", "overnight", "status", "--format", "json", ""],
            capture_output=True,
            text=True,
            timeout=10,
        )
        sub_results["overnight_status"] = {
            "exit_code": proc_b.returncode,
            "stdout": proc_b.stdout,
            "stderr": proc_b.stderr,
        }
    except Exception as exc:  # noqa: BLE001
        sub_results["overnight_status"] = {
            "exit_code": None,
            "stdout": None,
            "stderr": None,
            "error": f"{type(exc).__name__}: {exc}",
        }

    result["sub_results"] = sub_results

    a_ok = sub_results.get("print_root", {}).get("exit_code") == 0
    b_ok = sub_results.get("overnight_status", {}).get("exit_code") == 0
    if a_ok and b_ok:
        result["status"] = "ok"
        result["error"] = None
    else:
        result["status"] = "error"
        result["error"] = (
            f"print_root_exit={sub_results.get('print_root', {}).get('exit_code')}, "
            f"overnight_status_exit={sub_results.get('overnight_status', {}).get('exit_code')}"
        )
    return result


def _compute_verdict(ops: list[dict[str, Any]]) -> str:
    statuses = [op.get("status") for op in ops]
    if all(s == "ok" for s in statuses):
        return "PASS"
    if all(s == "error" for s in statuses):
        return "FAIL"
    # Mixed — per R18, treat PARTIAL as FAIL for R10–R14 scoping, but report
    # PARTIAL accurately so the user sees the breakdown.
    if any(s == "ok" for s in statuses) and any(s == "error" for s in statuses):
        return "PARTIAL"
    return "FAIL"


@mcp.tool()
def run_probe(cortex_root: str | None = None) -> dict[str, Any]:
    """Run the four R18 sandbox probe operations sequentially.

    Args:
        cortex_root: Optional override for the cortex repo root. Falls back to
            the CORTEX_COMMAND_ROOT env var, then to the default
            /Users/charlie.hall/Workspaces/cortex-command.

    Returns:
        A structured dict with per-operation results, the resolved cortex_root,
        and a final verdict (PASS / FAIL / PARTIAL).
    """
    resolved_root = _resolve_cortex_root(cortex_root)
    ops = [
        _op1_filesystem_write(resolved_root),
        _op2_flock(resolved_root),
        _op3_uv_tool_install(resolved_root),
        _op4_cortex_subprocess(),
    ]
    verdict = _compute_verdict(ops)
    return {
        "cortex_root": resolved_root,
        "operations": ops,
        "verdict": verdict,
        "verdict_legend": {
            "PASS": "all four operations succeeded",
            "FAIL": "all four operations failed (or any sandbox/TCC block)",
            "PARTIAL": "mixed; treated as FAIL for R10–R14 scoping",
        },
        "next_step": (
            "Paste this JSON into sandbox-probe-result.md's Operation Results "
            "section, then replace the literal 'PENDING' verdict line with "
            "one of PASS / FAIL / PARTIAL on its own line."
        ),
    }


if __name__ == "__main__":
    mcp.run()
