"""Resolve the best-available ``claude`` CLI for SDK dispatch (ADR-0014).

``claude-agent-sdk`` bundles its own ``claude`` binary and prefers it over the
operator's system install (``_find_cli`` is bundled-first). When the bundled
binary lags — e.g. 0.1.46 ships claude-code 2.1.69, which hard-rejects
``--effort xhigh`` — every ``(complex, high|critical)`` dispatch that resolves
to ``xhigh`` fails instantly. This module resolves the *newer of*
system-vs-bundled ``claude`` so cortex can pin it via
``ClaudeAgentOptions(cli_path=...)``, with a ``CORTEX_CLAUDE_CLI_PATH``
operator/test override that short-circuits resolution.

Design (see ADR-0014 and
``cortex/lifecycle/overnight-dispatch-sends-opus-only-xhigh/``):

- Returning ``None`` means "let the caller fall back to today's behavior"
  (SDK bundled-first / bare ``"claude"``), so pinning the result is safe in
  degraded environments.
- A transient ``--version`` probe flake must NOT silently select the older
  bundle (that would reproduce #313): when the system CLI is present but its
  version is unparseable, prefer the present system CLI anyway and do not
  memoize that probe-forced result, so a flake cannot pin a degraded choice for
  the process lifetime.

Leaf module: stdlib-only plus an optional package-relative SDK lookup. It must
not import ``cortex_command.pipeline.dispatch`` / ``overnight`` / ``discovery``
— those depend on it.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ENV_OVERRIDE = "CORTEX_CLAUDE_CLI_PATH"
_VERSION_TIMEOUT_S = 10
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


def _find_bundled_cli_path() -> Optional[str]:
    """Return the SDK-bundled ``claude`` via the package-relative path.

    ``<claude_agent_sdk pkg dir>/_bundled/claude`` is exactly what the SDK's own
    bundled-first selection computes. We do NOT call
    ``subprocess_cli._find_bundled_cli`` — verified it is an *instance method* of
    ``SubprocessCLITransport``, not a module-level function, so a module-level
    reference would be unreachable.
    """
    try:
        spec = importlib.util.find_spec("claude_agent_sdk")
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.origin:
        return None
    bundled = Path(spec.origin).parent / "_bundled" / "claude"
    return str(bundled) if bundled.exists() else None


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


def _probe_version(cli_path: str) -> Optional[tuple[int, ...]]:
    """Run ``<cli> --version`` (``CLAUDECODE`` cleared, bounded timeout).

    Any failure (missing binary, timeout, non-zero, unparseable) -> ``None``.
    """
    env = dict(os.environ)
    env["CLAUDECODE"] = ""  # avoid the SDK's nested-session guard
    try:
        proc = subprocess.run(
            [cli_path, "--version"],
            capture_output=True,
            text=True,
            env=env,
            timeout=_VERSION_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return _parse_cli_version(proc.stdout or "")


def _compute_best_cli() -> tuple[Optional[str], bool]:
    """Compute the prefer-newer result.

    Returns ``(path, memoizable)``. ``memoizable`` is ``False`` only when a probe
    flake forced a prefer-present-system result, so a transient failure does not
    pin a degraded choice.
    """
    system = _find_system_cli_path()
    bundled = _find_bundled_cli_path()

    if system is None and bundled is None:
        return None, True
    if system is None:
        return bundled, True
    if bundled is None:
        # System present, no bundled floor to compare against — prefer system.
        return system, True

    system_version = _probe_version(system)
    bundled_version = _probe_version(bundled)

    if system_version is not None and bundled_version is not None:
        return (system if system_version >= bundled_version else bundled), True

    # System present but its version is unparseable (timeout/parse flake):
    # prefer the present system CLI (almost-always-newer, the operator's
    # intended binary) rather than silently falling back to the stale bundle,
    # and do NOT memoize this probe-forced result.
    logger.warning(
        "cli_resolver: could not parse --version for system claude at %s "
        "(or for the bundled CLI); preferring the present system CLI without "
        "memoizing so a transient probe flake does not pin a degraded choice",
        system,
    )
    return system, False


def resolve_claude_cli() -> Optional[str]:
    """Resolve the absolute path of the best ``claude`` CLI to dispatch.

    Resolution order:

    1. ``CORTEX_CLAUDE_CLI_PATH`` env override — returned verbatim, never
       memoized (so per-test/per-operator env changes are honored).
    2. The memoized prior result, if present.
    3. Prefer-newer of system-vs-bundled; memoized unless a probe flake forced an
       indeterminate (prefer-present-system) result.

    Returns ``None`` when neither a system nor a bundled CLI is found — the
    caller then falls back to today's behavior (SDK bundled-first / bare
    ``"claude"``).
    """
    override = os.environ.get(_ENV_OVERRIDE)
    if override:
        return override

    global _cached_cli
    if _cached_cli is not _UNSET:
        return _cached_cli  # type: ignore[return-value]

    path, memoizable = _compute_best_cli()
    if memoizable:
        _cached_cli = path
    return path
