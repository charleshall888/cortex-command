"""PATH self-test for cortex-command entry points.

Enumerates the installed wheel's console_scripts entry points, subtracts those
listed in bin/.parity-exceptions.md (all categories are doctor-irrelevant),
then checks each remaining name against shutil.which() on the current PATH.

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
# Parity-exceptions parser (requirement 11)
# ---------------------------------------------------------------------------

# Canonical allowlist file path relative to the cortex-command source tree.
# When running from an installed wheel the file may not be reachable; the
# self-test treats a missing/malformed exceptions file as "no exceptions"
# (requirement spec edge-cases: over-enumerate is preferable to silent skip).
_ALLOWLIST_REL_PATH = "bin/.parity-exceptions.md"

# All three category enum values are doctor-irrelevant (Non-Requirements).
_DOCTOR_IRRELEVANT_CATEGORIES = frozenset(
    {"maintainer-only-tool", "library-internal", "deprecated-pending-removal"}
)

_ALLOWLIST_HEADER = ["script", "category", "rationale", "lifecycle_id", "added_date"]


def _parse_parity_exceptions(text: str) -> set[str]:
    """Return the set of script names listed in the parity-exceptions table.

    All entries whose category is in _DOCTOR_IRRELEVANT_CATEGORIES are
    returned. If the table is missing or malformed, returns an empty set
    (over-enumerate posture per requirement spec edge-cases).
    """
    exceptions: set[str] = set()
    saw_header = False
    saw_separator = False

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            if saw_separator:
                # End of table block — stop parsing.
                break
            saw_header = False
            saw_separator = False
            continue

        cells = [c.strip() for c in stripped.strip("|").split("|")]

        if not saw_header:
            normalized = [c.lower().strip("`") for c in cells]
            if normalized == _ALLOWLIST_HEADER:
                saw_header = True
            continue

        if not saw_separator:
            if all(set(c) <= set("-: ") and "-" in c for c in cells):
                saw_separator = True
            else:
                saw_header = False
            continue

        # Data row: expect 5 columns.
        if len(cells) != 5:
            continue

        script = cells[0].strip().strip("`").strip()
        category = cells[1].strip().strip("`").strip()

        if category in _DOCTOR_IRRELEVANT_CATEGORIES and script:
            exceptions.add(script)

    return exceptions


def _load_parity_exceptions() -> set[str]:
    """Load parity exceptions from bin/.parity-exceptions.md.

    Resolves the file relative to the installed package's location or CWD.
    Returns an empty set on any failure (over-enumerate posture).
    """
    # Strategy 1: use importlib.resources to find the package root.
    # The parity-exceptions file is not packaged as wheel data, so we fall
    # back to locating the source tree via the cortex_command package's __file__.
    try:
        import cortex_command
        pkg_file = getattr(cortex_command, "__file__", None)
        if pkg_file:
            # cortex_command/__init__.py -> cortex_command/ -> repo root
            pkg_dir = Path(pkg_file).parent
            repo_root = pkg_dir.parent
            candidate = repo_root / _ALLOWLIST_REL_PATH
            if candidate.is_file():
                text = candidate.read_text(encoding="utf-8")
                return _parse_parity_exceptions(text)
    except Exception:
        pass

    # Strategy 2: try CWD-relative path (useful when running from the source tree).
    try:
        candidate = Path(os.getcwd()) / _ALLOWLIST_REL_PATH
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8")
            return _parse_parity_exceptions(text)
    except Exception:
        pass

    # File not found or unreadable: return empty set (over-enumerate posture).
    return set()


# ---------------------------------------------------------------------------
# Entry-point enumeration (requirement 11)
# ---------------------------------------------------------------------------


def _get_expected_entry_points() -> set[str]:
    """Return the set of cortex console_scripts names that should be on PATH.

    = all entry_points(group='console_scripts') where name starts with 'cortex-'
      minus any name listed in bin/.parity-exceptions.md
    """
    from importlib.metadata import entry_points

    all_eps = entry_points(group="console_scripts")
    cortex_names = {ep.name for ep in all_eps if ep.name.startswith("cortex-")}
    exceptions = _load_parity_exceptions()
    return cortex_names - exceptions


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
