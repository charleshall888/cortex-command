#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "mcp>=1.27,<2",
#     "pydantic>=2.5,<3",
# ]
# ///
"""Plugin-bundled cortex-overnight MCP server (PEP 723 single-file).

This module is the canonical location for the cortex MCP server. It
intentionally has zero ``cortex_command.*`` imports (R1 architectural
invariant): the only contract with the cortex CLI is
``subprocess.run(cortex_argv) + versioned JSON``.

Task 5 stands up the skeleton: the PEP 723 frontmatter (above), the
confused-deputy startup check (R17), the FastMCP/Server instance, and
stdio transport. No tools are wired here — they arrive in Task 6.

The confused-deputy check fires unconditionally at module import time
(top-level code, after imports, before MCP server instantiation) so the
test in ``tests/test_mcp_subprocess_contract.py`` can verify it without
needing to actually start the MCP server.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _enforce_plugin_root() -> None:
    """R17 — confused-deputy mitigation.

    Verify, at startup, that this file lives under the resolved
    ``${CLAUDE_PLUGIN_ROOT}``. On mismatch (or absent env var), refuse
    to start: print ``"plugin path mismatch"`` to stderr and exit
    non-zero. This prevents an attacker who can override
    ``CLAUDE_PLUGIN_ROOT`` from pointing uvx at arbitrary Python.
    """

    plugin_root_env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not plugin_root_env:
        print(
            "plugin path mismatch (CLAUDE_PLUGIN_ROOT not set)",
            file=sys.stderr,
        )
        sys.exit(1)

    file_path = Path(__file__).resolve()
    plugin_root = Path(plugin_root_env).resolve()

    if not file_path.is_relative_to(plugin_root):
        print(
            f"plugin path mismatch (file={file_path} root={plugin_root})",
            file=sys.stderr,
        )
        sys.exit(1)


# Fail-fast: enforce the confused-deputy invariant at import time, before
# any MCP machinery is instantiated. Tests rely on this firing during a
# bare ``uv run --script server.py`` invocation.
_enforce_plugin_root()


# Import MCP machinery lazily so the confused-deputy check above runs
# first (and so static imports of this file do not require ``mcp`` to
# be present, which matters for test discovery on machines where the
# PEP 723 deps haven't been resolved yet).
from mcp.server.fastmcp import FastMCP  # noqa: E402

server = FastMCP("cortex-overnight")
"""Stdio FastMCP instance. Tool handlers land in Task 6."""


def main() -> None:
    """Entrypoint for ``uv run --script server.py``.

    Runs the FastMCP stdio transport. No tools are registered yet —
    Task 6 wires the five overnight tool handlers.
    """

    server.run()


if __name__ == "__main__":
    main()
