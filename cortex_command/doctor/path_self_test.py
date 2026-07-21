"""PATH self-test for cortex-command entry points.

Enumerates the installed wheel's console_scripts entry points, then checks
each name against shutil.which() on the current PATH.

When one or more expected entry points are absent, emits a SessionStart
additionalContext advisory on stdout. All error paths exit 0 silently —
this is a best-effort secondary advisory channel; the primary remediation is
Task 3's wrapper exit-2 message at command-not-found time.

Skip predicates (requirement 13):
  (a) CORTEX_DEV_MODE=1 is set
  (b) $CWD/pyproject.toml contains a line matching ^name\\s*=\\s*"cortex-command"
  (c) importlib.metadata raises or python3 is unavailable

Public entry point: main(argv=None) -> int  (always returns 0)
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Advisory message template (requirement 12 — factual phrasing, no imperatives)
# ---------------------------------------------------------------------------

_ADVISORY_TEMPLATE = (
    "The following cortex entry points are not on PATH: {missing}. "
    "The installed wheel may be stale; running "
    "'uv tool install --reinstall --refresh git+...' will refresh."
)

# ---------------------------------------------------------------------------
# Dogfooder / dev-mode skip predicates (requirement 13)
# ---------------------------------------------------------------------------


def _is_dev_mode() -> bool:
    """Return True when CORTEX_DEV_MODE=1 is set in the environment."""
    return os.environ.get("CORTEX_DEV_MODE", "") == "1"


def _is_cortex_command_source_tree() -> bool:
    """Return True when CWD/pyproject.toml names cortex-command.

    Requirement 13(b): the line must match ^name\\s*=\\s*"cortex-command".
    """
    pyproject = Path(os.getcwd()) / "pyproject.toml"
    if not pyproject.is_file():
        return False
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return False
    pattern = re.compile(r'^name\s*=\s*"cortex-command"', re.MULTILINE)
    return bool(pattern.search(text))


def _should_skip() -> bool:
    """Return True when any dogfooder/dev-mode skip predicate fires."""
    return _is_dev_mode() or _is_cortex_command_source_tree()


# ---------------------------------------------------------------------------
# Entry-point enumeration (requirement 11)
# ---------------------------------------------------------------------------


def _get_expected_entry_points() -> set[str]:
    """Return the set of cortex console_scripts names that should be on PATH.

    = all entry_points(group='console_scripts') where name starts with
    'cortex-'. (The former subtraction of bin/.parity-exceptions.md entries
    retired with the parity linter (#407); all console scripts ship in the
    same wheel, so over-enumeration cannot produce a false advisory in a
    consistent install.)
    """
    from importlib.metadata import entry_points

    all_eps = entry_points(group="console_scripts")
    return {ep.name for ep in all_eps if ep.name.startswith("cortex-")}


# ---------------------------------------------------------------------------
# PATH check (requirement 3 in the self-test logic)
# ---------------------------------------------------------------------------


def _find_missing(expected: set[str]) -> list[str]:
    """Return sorted list of names from expected that are absent from PATH."""
    return sorted(name for name in expected if shutil.which(name) is None)


# ---------------------------------------------------------------------------
# Advisory emission (requirement 12)
# ---------------------------------------------------------------------------


def _emit_advisory(missing: list[str]) -> None:
    """Write the additionalContext JSON envelope to stdout."""
    message = _ADVISORY_TEMPLATE.format(missing=", ".join(missing))
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": message,
        }
    }
    print(json.dumps(payload))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001
    """PATH self-test entry point. Returns 0 unconditionally on all paths.

    argv is accepted for console_scripts compatibility but ignored.
    """
    try:
        # Skip predicates (requirement 13a and 13b).
        if _should_skip():
            return 0

        expected = _get_expected_entry_points()
        missing = _find_missing(expected)

        if missing:
            _emit_advisory(missing)

    except Exception:
        # Requirement 14: all error paths exit 0 silently.
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
