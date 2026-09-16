"""Resolve the operator's ``claude`` CLI for direct subprocess dispatch.

cortex spawns the operator's own ``claude`` binary directly (see ADR-0038).
This module finds it: ``shutil.which`` on ``PATH``, then a short list of
non-``PATH`` fallbacks for environments
(e.g. Dock-launched sessions that inherit launchd's minimal ``PATH``) where
``claude`` is installed but not reachable via ``PATH``. A
``CORTEX_CLAUDE_CLI_PATH`` operator/test override short-circuits resolution.

Design:

- Returning ``None`` means no ``claude`` is installed anywhere this module
  knows to look; the caller fails loudly rather than silently falling back to
  a bare ``"claude"`` on ``PATH``.
- The resolved path is memoized for the process lifetime once found. The env
  override is never memoized, so per-test/per-operator env changes are
  honored immediately.

Leaf module: stdlib-only. It must not import
``cortex_command.pipeline.dispatch`` / ``overnight`` / ``discovery`` — those
depend on it.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Optional

_ENV_OVERRIDE = "CORTEX_CLAUDE_CLI_PATH"
_SYSTEM_FALLBACKS = (
    "~/.local/bin/claude",
    "/usr/local/bin/claude",
    "~/.claude/local/claude",
)

# Sentinel distinguishes "not yet computed" from a legitimately-cached ``None``.
_UNSET = object()
_cached_cli: object = _UNSET


def _reset_cli_cache() -> None:
    """Test seam: clear the memoized resolution."""
    global _cached_cli
    _cached_cli = _UNSET


def _find_system_cli_path() -> Optional[str]:
    """Return the system ``claude`` path: ``shutil.which`` then known fallbacks."""
    found = shutil.which("claude")
    if found:
        return found
    for candidate in _SYSTEM_FALLBACKS:
        path = Path(candidate).expanduser()
        if path.exists():
            return str(path)
    return None


def _parse_cli_version(output: str) -> Optional[tuple[int, ...]]:
    """Parse the leading dotted-int run of ``--version`` output.

    ``"2.1.186 (Claude Code)"`` -> ``(2, 1, 186)``; unparseable -> ``None``.
    """
    if not output:
        return None
    match = re.match(r"\s*(\d+(?:\.\d+)*)", output)
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _compute_best_cli() -> Optional[str]:
    """Return the operator's system ``claude`` path, or ``None`` if absent."""
    return _find_system_cli_path()


def resolve_claude_cli() -> Optional[str]:
    """Resolve the absolute path of the ``claude`` CLI to dispatch.

    Resolution order:

    1. ``CORTEX_CLAUDE_CLI_PATH`` env override — returned verbatim, never
       memoized (so per-test/per-operator env changes are honored).
    2. The memoized prior result, if present.
    3. The system ``claude`` (``PATH`` then ``_SYSTEM_FALLBACKS``); memoized
       once computed.

    Returns ``None`` when no ``claude`` is found anywhere this module knows
    to look — the caller fails loudly rather than falling back to a bare
    ``"claude"`` on ``PATH``.
    """
    override = os.environ.get(_ENV_OVERRIDE)
    if override:
        return override

    global _cached_cli
    if _cached_cli is not _UNSET:
        return _cached_cli  # type: ignore[return-value]

    path = _compute_best_cli()
    _cached_cli = path
    return path
